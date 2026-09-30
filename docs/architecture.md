# Architecture

## 1. Overview

LawSchool is a two-tier web application: a React SPA and a Django REST API, with
PostgreSQL as the system of record, Redis for cache/broker, Celery for background
work, Razorpay for payments and Cloudflare Stream for video.

```
                    Internet
                       │
                       ▼
                Cloudflare/CDN
                       │
                       ▼
                 Nginx / LB
                       │
              ┌────────┴────────┐
              ▼                 ▼
          React App         Django API
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                PostgreSQL      Redis        Cloudflare
                                  │            Stream
                                  ▼
                               Celery
                                  │
                                  ▼
                            Background Jobs
```

## 2. Layering

The backend is deliberately layered. Each concern has exactly one home, which is
what makes the security properties reviewable.

| Layer       | Location                                | Responsibility                                                        |
| ----------- | --------------------------------------- | --------------------------------------------------------------------- |
| Models      | `apps/*/models.py`                      | domain relationships, DB constraints, indexes, trivial invariants     |
| Selectors   | `apps/*/selectors.py`                   | complex/tuned reads with explicit `select_related`/`prefetch_related` |
| Serializers | `apps/*/serializers.py`                 | input validation, output shaping                                      |
| Services    | `apps/*/services.py`                    | business rules, transactions, orchestration                           |
| Permissions | `apps/core/permissions.py`              | role + object-level authorization                                     |
| Views       | `apps/*/views.py`                       | HTTP orchestration only                                               |
| Tasks       | `apps/*/tasks.py`, `apps/core/tasks.py` | asynchronous and periodic work                                        |

### Why services instead of fat views

A permission check and a payment verification must behave identically whether they
are reached from an HTTP view, a Celery task, a management command or the Django
admin. Putting the rule in a service makes that automatic; putting it in a view
means the next caller silently bypasses it. `issue_playback_token` and
`verify_payment` are the clearest examples — both are the _only_ way to reach the
sensitive operation, and both are called from more than one entry point.

### Views are thin

`CourseListView.list()` paginates first and then computes progress for that page
only. It contains no business rule; it sequences a selector, a service and a
serializer.

## 3. Request lifecycle

A request for course content:

```
HTTP request
   │
   ├─ Nginx: TLS, static files, gzip, request limits
   │
   ├─ Django SecurityMiddleware / CORS / CSRF
   │
   ├─ DRF authentication (JWT access token)
   │      └─ apps.users.backends.EmailBackend + SimpleJWT
   │
   ├─ Throttling (scoped: auth / payment / playback / progress / webhook)
   │
   ├─ View
   │      ├─ selector  → tuned queryset (no N+1)
   │      ├─ permission → role/object check
   │      ├─ service    → entitlement decision, transaction if stateful
   │      └─ serializer → shape the response
   │
   ├─ Exception handler → uniform {"error": {...}} envelope
   │
   └─ Response
```

## 4. Entitlement: the single authorization chokepoint

`apps/subscriptions/services.py` is the one module allowed to decide whether a user
may consume content.

```python
can_user_access_course(user, course)   # course-level
can_user_access_lesson(user, lesson)   # lesson-level (previews override)
can_user_access_video(user, video)     # video-level (delegates to the lesson)
```

Resolution order:

1. Not authenticated → **deny** (`authentication_required`)
2. Admin, or the instructor who owns the course → **allow**
3. Course not `PUBLISHED` → **deny** (`not_published`)
4. Course `unlock_rule == FREE` → **allow**
5. An `ACTIVE` subscription whose date window contains _now_ and whose plan covers
   the course → **allow**
6. Otherwise → **deny** (`subscription_required` / `subscription_expired` /
   `not_in_plan`)

The decision is returned as an `AccessDecision` carrying a machine-readable
`reason`, so the UI can render "Buy", "Renew", or "Not in your plan" instead of a
generic 403.

### The date window is enforced in SQL, not by the status column

```python
.filter(status=ACTIVE, start_date__lte=now)
.filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
```

A row whose `status` still says `ACTIVE` but whose `end_date` has passed is treated
as expired. The hourly `expire_subscriptions` job corrects the stored status, but
correctness does not depend on that job having run — a stale column can never grant
access.

### Caching with complete invalidation

Entitlement answers are cached for 60 seconds under three key families:

- `entitlement:has_sub:<user>` — coarse "has any subscription"
- `entitlement:courses:<user>` — bulk id set for list pages
- `entitlement:dec:<generation>:<user>:<course>` — per-course decision

The per-course key embeds a **generation counter** that is bumped on every
subscription state change. Bumping orphans every previously written per-course
entry at once, which is what makes invalidation complete without having to
enumerate an unknown set of course keys. (Omitting this was a real bug the test
suite caught: the bulk set refreshed while the per-course answer stayed stale,
letting a lapsed student keep watching for up to the TTL.)

## 5. Asynchronous work

Celery exists for work that is _not_ required to answer an HTTP request.

| Task                               | Trigger      | Why async                    |
| ---------------------------------- | ------------ | ---------------------------- |
| `expire_subscriptions`             | beat, hourly | batch update + notifications |
| `send_expiry_reminders`            | beat, daily  | email fan-out                |
| `reconcile_payments`               | beat, 15 min | external API calls           |
| `sync_pending_videos`              | beat, 10 min | external API calls           |
| `retry_failed_notification_emails` | beat, hourly | retry loop                   |
| `recalculate_leaderboard_task`     | beat, daily  | full-table aggregation       |
| `finish_quiz_leaderboards`         | on grading   | keeps the request path short |

**Nothing in this list is needed for correctness of a response.** That is the test
for whether something belongs in Celery. Payment verification, entitlement checks
and quiz scoring must return immediately and are therefore synchronous.

## 6. Error handling

One envelope for every error, produced by
`apps/core/exceptions.lawschool_exception_handler`:

```json
{
  "error": {
    "code": "subscription_required",
    "message": "An active subscription is required for this course.",
    "details": null
  }
}
```

Domain exceptions map onto HTTP semantics via `status_code`:

| Exception                  | Status | Use                        |
| -------------------------- | ------ | -------------------------- |
| `PaymentError`             | 400    | bad payment request        |
| `EntitlementError`         | 403    | no right to this content   |
| `VideoNotReadyError`       | 409    | asset still encoding       |
| `PlaybackUnavailableError` | 503    | server cannot mint a token |
| `ConflictError`            | 409    | state conflict             |

`PlaybackUnavailableError` deserves its own note. A missing or rotated Cloudflare
signing key is an **operational** problem, not the student's. It is logged with a
full traceback and returned as a 503 with no internal detail. Before this was
handled explicitly it escaped as an unhandled 500 whose traceback leaked into the
error page; three regression tests now pin the behaviour.

## 7. Frontend architecture

```
main.jsx
  └── AuthProvider (session, tokens, role helpers)
  └── UIProvider   (toasts, global UI state)
        └── BrowserRouter → AppRoutes
              └── Layout (Navbar, Outlet, Footer, ToastHost)
                    └── lazy-loaded page
```

| Concern                             | Location                                         |
| ----------------------------------- | ------------------------------------------------ |
| HTTP + token refresh                | `services/apiClient.js`                          |
| One module per API area             | `services/authService.js`, `courseService.js`, … |
| Session + role helpers              | `context/AuthContext.jsx`                        |
| Data fetching + loading/error state | `hooks/useAsync.js`                              |
| Payment checkout flow               | `hooks/useCheckout.js`                           |
| Progress heartbeat                  | `hooks/useVideoProgress.js`                      |
| Route protection                    | `components/RouteGuards.jsx`                     |

**All routes below the shell are lazily loaded**, so the landing page does not ship
the quiz engine or the admin tables.

### Route guards are UX, not security

`RequireAuth` and `RequireRole` prevent a user from landing on a page they cannot
use. They are explicitly documented as _not_ being the security boundary: a student
who edits the router state or calls the API directly still receives 401/403,
because the API re-derives every authorization decision. The frontend test suite
asserts the UX behaviour and says so in a comment; the backend suite proves the
security.

## 8. Key decisions and trade-offs

**Custom user with email as the identifier.** `USERNAME_FIELD = "email"` removes an
entire class of "which field do I log in with" bugs and matches how the platform is
sold. Trade-off: existing username-based tooling and some third-party packages
assume `username`, so a compatibility property is provided.

**UUID primary keys on domain objects, readable slugs for courses.** Sections and
lessons are addressed by UUID so they cannot be enumerated (`/lessons/1`, `/2`, …).
Courses keep slugs because shareable URLs matter more there than opacity. The
cost is slightly larger indexes and URLs.

**`ordering` integer + unique constraint, not an ordered-model library.** Sections
and lessons are edited rarely and read constantly. A plain integer with
`UniqueConstraint(parent, ordering)` is cheaper and more predictable than a
library-maintained tree, and the constraint makes duplicate positions impossible
rather than merely discouraged.

**Denormalised course aggregates.** `duration_minutes` and `lesson_count` are
recomputed on lesson save (`Course.refresh_aggregates`) so course lists need no
join at all. Trade-off: one extra aggregate per write, which is negligible against
a join on every list read.

**A derived `LeaderboardEntry` table.** The alternative — a `GROUP BY` over
`QuizAttempt` and `VideoProgress` on every leaderboard page — scans the two largest
tables in the system. A small indexed table makes the leaderboard `O(page_size)`,
and the full recomputation is a nightly job. Trade-off: a row can be stale until
the next grading event or the nightly rebuild, which is acceptable for a
leaderboard and unacceptable for a payment, which is why payments are never
denormalised.

**Cloudflare Stream instead of self-hosted video.** Encoding, storage and
worldwide delivery are the expensive parts of video, and they are not the
platform's differentiator. Trade-off: a hard dependency on a third party for the
core product, mitigated by keeping the authorization decision entirely in Django
so the provider never becomes the access-control layer.

**Redis is an optimisation, never a correctness requirement.** Entitlement and
quiz answers always re-read the database; the cache only shortens the path. A
`CACHE_BACKEND=locmem` switch lets the API run with no Redis at all, which keeps
local setup to one command and makes the test suite independent of infrastructure.

## 9. Scaling path

The backend is stateless, so horizontal scaling is a matter of running more
workers behind the load balancer.

| Bottleneck              | First move                                     | Then                                            |
| ----------------------- | ---------------------------------------------- | ----------------------------------------------- |
| API request volume      | more Gunicorn workers / replicas               | read replica for list endpoints                 |
| Playback token requests | raise `CLOUDFLARE_PLAYBACK_TOKEN_TTL` modestly | dedicated cache cluster                         |
| Leaderboard reads       | already `O(page_size)`; cache top-100 for 60s  | materialised view                               |
| Video bandwidth         | Cloudflare absorbs it                          | multi-provider delivery                         |
| Background jobs         | more Celery workers                            | split queues by task class                      |
| Write load              | tune indexes, batch tasks                      | partition `VideoProgress`/`QuizAttempt` by time |

The stateless design is what makes this list short: no session affinity, no
in-process state, no local file writes.

## 10. Related documents

- [api.md](api.md) — endpoint reference
- [database.md](database.md) — schema, indexes, constraints
- [payments.md](payments.md) — Razorpay flow and idempotency
- [video-security.md](video-security.md) — playback threat model
- [deployment.md](deployment.md) — production setup
