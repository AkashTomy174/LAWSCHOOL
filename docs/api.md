# API Reference

Base URL: `/api/v1/`. Interactive docs: `/api/docs/` (Swagger UI) and
`/api/redoc/`. Raw OpenAPI 3 schema: `/api/schema/`.

## Conventions

### Authentication

Protected endpoints require a JWT access token:

```
Authorization: Bearer <access_token>
```

Obtain a pair from `POST /api/v1/auth/login/`. Access tokens are short-lived
(default 15 minutes); refresh tokens are long-lived (default 7 days) and are
**rotated on every use** — the token you just used is blacklisted, so replaying it
fails. The SPA's axios client performs this rotation transparently.

### Error envelope

Every error — validation, auth, permission, not-found, server — uses one shape:

```json
{
  "error": {
    "code": "subscription_required",
    "message": "An active subscription is required for this course.",
    "details": null
  }
}
```

`details` is populated only for validation failures, keyed by field:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid input.",
    "details": { "email": ["Enter a valid email address."] }
  }
}
```

### Status codes

| Code            | Meaning                                                           |
| --------------- | ----------------------------------------------------------------- |
| 200 / 201 / 204 | success / created / deleted                                       |
| 400             | validation error, bad domain request                              |
| 401             | missing, invalid or expired token                                 |
| 403             | authenticated but not permitted (`EntitlementError`, role denial) |
| 404             | not found                                                         |
| 409             | conflict (video still processing)                                 |
| 429             | throttled                                                         |
| 503             | server-side dependency unavailable (playback token minting)       |

### Pagination

List endpoints are paginated (`PAGE_SIZE = 20`):

```json
{ "count": 42, "next": "…?page=2", "previous": null, "results": [ … ] }
```

### Throttling

Scoped limits (per user/IP):

| Scope      | Default |
| ---------- | ------- |
| `auth`     | 10/min  |
| `payment`  | 30/min  |
| `playback` | 120/min |
| `progress` | 120/min |
| `webhook`  | 300/min |

---

## Authentication — `/api/v1/auth/`

### `POST register/` — public

```json
{
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "password": "CorrectHorse42!",
  "password_confirm": "CorrectHorse42!"
}
```

→ `201` with the created user and a token pair. Password policy: minimum 10
characters, not entirely numeric, not a common password, not too similar to the
email. An account-verification notification is queued.

### `POST login/` — public

```json
{ "email": "ada@example.com", "password": "CorrectHorse42!" }
```

→ `200 { "access": "…", "refresh": "…", "user": { … } }`

Email matching is case-insensitive. Wrong password and unknown account return the
**same** error, so the endpoint cannot be used to enumerate accounts.

### `POST refresh/` — public

```json
{ "refresh": "<refresh token>" }
```

→ `200 { "access": "…", "refresh": "…" }` — the supplied refresh token is
blacklisted. Reusing it returns `401`.

### `POST logout/` — authenticated

Body: `{ "refresh": "<token>" }`. Blacklists that refresh token.
`POST logout-all/` blacklists every refresh token for the user.

### `GET me/` — authenticated

Returns the caller's profile, role and `is_email_verified`.

### `POST password/change/` — authenticated

```json
{ "current_password": "…", "new_password": "CorrectHorse99!" }
```

### `POST password-reset/` — public

`{ "email": "…" }` → always `200`, whether or not the address exists.

### `POST password-reset-confirm/` — public

`{ "token": "…", "new_password": "…" }`

### `POST verify-email/` — public

`{ "token": "…" }`

---

## Users — `/api/v1/users/`

| Method | Path      | Access        | Notes                               |
| ------ | --------- | ------------- | ----------------------------------- |
| GET    | ``        | admin         | paginated user list, filter by role |
| GET    | `me/`     | authenticated | own profile                         |
| PATCH  | `me/`     | authenticated | update name, phone, avatar, bio     |
| GET    | `<uuid>/` | admin         | single user                         |
| PATCH  | `<uuid>/` | admin         | change role, activate/deactivate    |

Role changes are admin-only. A student cannot promote themselves.

---

## Courses — `/api/v1/courses/`

| Method | Path              | Access            | Notes                                            |
| ------ | ----------------- | ----------------- | ------------------------------------------------ |
| GET    | ``                | public            | published catalogue, paginated                   |
| POST   | ``                | instructor, admin | create a course                                  |
| GET    | `<slug>/`         | public            | detail: sections + lessons, **no playback data** |
| PATCH  | `<slug>/`         | owner or admin    | update                                           |
| GET    | `<slug>/lessons/` | authenticated     | flat lesson list with lock/completion flags      |
| GET    | `<slug>/access/`  | public            | entitlement decision for the caller              |

Query parameters on the list: `search`, `level`, `language`, `ordering`
(`published_at`, `price`, `title`), plus `scope=all&status=draft` for staff.

`GET /courses/<slug>/access/`:

```json
{
  "course": {
    "id": "…",
    "slug": "constitutional-law",
    "title": "Constitutional Law"
  },
  "allowed": false,
  "reason": "subscription_required",
  "detail": "An active subscription is required for this course."
}
```

Possible `reason` values: `admin`, `instructor`, `free_course`, `preview_lesson`,
`active_subscription`, `authentication_required`, `not_published`,
`subscription_required`, `subscription_expired`, `not_in_plan`,
`lesson_unavailable`.

> **Important:** the course detail response deliberately contains no video
> identifiers, no playback URLs and no tokens. Playback is a separate, authorized
> call. A locked lesson reports `is_locked: true` and `has_video: true` — a
> presence flag, never an address.

---

## Sections — `/api/v1/sections/`

| Method           | Path             | Access         |
| ---------------- | ---------------- | -------------- |
| GET              | `?course=<slug>` | owner or admin |
| POST             | ``               | owner or admin |
| GET/PATCH/DELETE | `<uuid>/`        | owner or admin |

`ordering` is unique within a course; a duplicate returns `400`.

## Lessons — `/api/v1/lessons/`

| Method           | Path              | Access                   |
| ---------------- | ----------------- | ------------------------ |
| GET              | `?section=<uuid>` | owner or admin           |
| POST             | ``                | owner or admin           |
| GET/PATCH/DELETE | `<uuid>/`         | owner or admin           |
| GET              | `<uuid>/watch/`   | authenticated + entitled |

`GET /lessons/<uuid>/watch/` is the single entry point the video player uses.

→ `200` when allowed:

```json
{
  "lesson": {
    "id": "…",
    "title": "The Preamble",
    "duration_seconds": 600,
    "is_preview": false,
    "ordering": 1
  },
  "course": {
    "id": "…",
    "slug": "constitutional-law",
    "title": "Constitutional Law"
  },
  "access": { "allowed": true, "reason": "active_subscription", "detail": "…" },
  "playback": {
    "video_uid": "…",
    "hls_url": "…",
    "dash_url": "…",
    "thumbnail_url": "…",
    "duration_seconds": 600,
    "token_expires_at": "…",
    "expires_in": 300
  }
}
```

→ `403` when locked, with `"playback": null` and no video data whatsoever.

`duration_seconds` is not client-writable — it is synced from the Cloudflare asset.

---

## Videos — `/api/v1/videos/`

| Method | Path               | Access                   | Notes                                         |
| ------ | ------------------ | ------------------------ | --------------------------------------------- |
| GET    | ``                 | instructor, admin        | metadata list                                 |
| POST   | `register/`        | instructor, admin        | register an existing Stream asset             |
| POST   | `upload-url/`      | instructor, admin        | direct creator upload URL                     |
| GET    | `<uuid>/`          | authenticated            | metadata (Cloudflare id hidden from students) |
| GET    | `<uuid>/playback/` | authenticated + entitled | mint a signed playback token                  |
| POST   | `<uuid>/progress/` | authenticated + entitled | progress heartbeat                            |
| POST   | `<uuid>/sync/`     | instructor, admin        | re-pull metadata from Cloudflare              |

### `GET <uuid>/playback/`

The authorization sequence, in order: authenticate → active subscription → course
entitlement → lesson access → **then** mint a short-lived signed token.

```json
{
  "video_uid": "…",
  "hls_url": "https://customer-<code>.cloudflarestream.com/<token>/manifest/video.m3u8",
  "dash_url": "https://customer-<code>.cloudflarestream.com/<token>/manifest/video.mpd",
  "thumbnail_url": "…",
  "duration_seconds": 600,
  "token": "<signed JWT>",
  "token_expires_at": "…",
  "expires_in": 300
}
```

Failures: `401` unauthenticated · `403` no/expired subscription or wrong course ·
`409` video not ready · `429` too many token requests · `503` signing key missing
or malformed (server-side problem, logged with a traceback, nothing leaked).

### `POST <uuid>/progress/`

```json
{ "position_seconds": 420, "watched_seconds": 400, "completed": false }
```

Validated server-side:

- `position_seconds` may not exceed the real duration (+5s rounding slack).
- A single update may not jump more than `VIDEO_PROGRESS_MAX_DRIFT_SECONDS`
  (default 30s) past the stored position — a script cannot jump straight to 100%.
  The _first_ update is exempt, because resuming and seeking are legitimate.
- Progress is monotonic: it never decreases.
- `completed` alone is not trusted: completion requires ≥95% with an explicit
  end-of-video signal, or ≥98% from actual playback.

The frontend sends this every 10–30 seconds, plus once on video end and on page
unload — never once per second.

## Progress — `/api/v1/progress/`

| Method | Path             | Access                                   |
| ------ | ---------------- | ---------------------------------------- |
| GET    | ``               | authenticated — own progress rows        |
| GET    | `course/<slug>/` | authenticated — aggregate for one course |

---

## Subscriptions — `/api/v1/subscriptions/`

| Method | Path            | Access        | Notes                                    |
| ------ | --------------- | ------------- | ---------------------------------------- |
| GET    | `plans/`        | public        | active plans with covered course slugs   |
| GET    | `plans/<slug>/` | public        | plan detail                              |
| GET    | `me/`           | authenticated | current subscription                     |
| POST   | `me/cancel/`    | authenticated | cancel at period end                     |
| GET    | `history/`      | authenticated | own subscription history                 |
| GET    | ``              | admin         | all subscriptions, filter by status/user |
| GET    | `<uuid>/`       | admin         | single subscription                      |

Statuses: `pending`, `active`, `expired`, `cancelled`, `failed`.

A subscription is usable only when `status == "active"` **and**
`start_date <= now <= end_date`. Status alone is never sufficient.

## Payments — `/api/v1/payments/`

| Method | Path              | Access                           | Notes                         |
| ------ | ----------------- | -------------------------------- | ----------------------------- |
| POST   | `orders/`         | authenticated                    | create a Razorpay order       |
| POST   | `verify/`         | authenticated                    | verify the checkout signature |
| GET    | ``                | authenticated                    | own payment history           |
| POST   | `webhook/`        | public (signature-authenticated) | Razorpay notifications        |
| GET    | `all/`            | admin                            | all payments, filterable      |
| GET    | `webhook-events/` | admin                            | webhook audit trail           |

### `POST orders/`

```json
{ "plan_slug": "foundations", "idempotency_key": "uuid-from-client" }
```

→ `201 { "payment": { … }, "checkout": { "order_id": "…", "key_id": "rzp_…",
"amount": 199900, "currency": "INR", "prefill": { … } } }`

`key_id` is the **public** key. The secret never leaves the server. Reusing an
`idempotency_key` returns the existing order rather than creating a second one.

### `POST verify/`

```json
{
  "razorpay_order_id": "order_x",
  "razorpay_payment_id": "pay_x",
  "razorpay_signature": "hmac"
}
```

The body carries **only** identifiers — never an amount or a status. The server
recomputes the HMAC, re-reads the amount from its own order row, and activates
inside a transaction. Retrying a settled order returns the same success.

Errors: `invalid_signature` (403/400 — also recorded as a failed payment),
`unknown_order`, `forbidden` (the order belongs to another user).

### `POST webhook/`

Razorpay → server. Verified via the `X-Razorpay-Signature` HMAC over the **raw**
body; `X-Razorpay-Event-Id` provides the idempotency key. Handled events:
`payment.captured`, `payment.authorized`, `payment.failed`, `refund.created`,
`refund.processed`, `subscription.charged`.

Responses: `{"status": "processed"}` · `{"status": "duplicate"}` (a no-op, not an
error) · `{"status": "ignored"}` (unhandled event type, acknowledged so Razorpay
stops retrying) · `400` bad signature · `500` handler failure (deliberately
non-2xx so Razorpay retries).

---

## Quizzes — `/api/v1/quizzes/`

| Method           | Path                | Access                   | Notes               |
| ---------------- | ------------------- | ------------------------ | ------------------- |
| GET              | ``                  | authenticated            | available quizzes   |
| POST             | ``                  | instructor, admin        | create              |
| GET/PATCH/DELETE | `<uuid>/`           | instructor, admin        | manage              |
| POST/GET         | `questions/`        | instructor, admin        | author questions    |
| GET/PATCH/DELETE | `questions/<uuid>/` | instructor, admin        |                     |
| POST/GET         | `options/`          | instructor, admin        | author options      |
| GET/PATCH/DELETE | `options/<uuid>/`   | instructor, admin        |                     |
| POST             | `<uuid>/attempts/`  | authenticated + entitled | start an attempt    |
| GET              | `<uuid>/progress/`  | authenticated            | own attempt summary |

> **`is_correct` is never exposed to students.** It appears only on the
> authoring serializer, which instructors and admins use. The student-facing
> question payload contains options with `id` and `text` only — otherwise the
> answer key is one network-tab away.

### Attempts — `/api/v1/quiz-attempts/`

| Method | Path             | Access                       |
| ------ | ---------------- | ---------------------------- |
| GET    | ``               | authenticated — own attempts |
| GET    | `all/`           | admin                        |
| GET    | `<uuid>/`        | owner or admin               |
| POST   | `<uuid>/submit/` | owner                        |

`POST <uuid>/submit/`:

```json
{
  "answers": [
    { "question": "<uuid>", "option": "<uuid>" },
    { "question": "<uuid>", "option": null }
  ]
}
```

→ `200`

```json
{
  "attempt_id": "…",
  "score": 18,
  "max_score": 20,
  "percentage": 90.0,
  "passed": true,
  "attempts_used": 1,
  "attempts_remaining": 2,
  "results": [
    {
      "question": "<uuid>",
      "selected_option": "<uuid>",
      "correct_option": "<uuid>",
      "is_correct": true,
      "marks_awarded": 2
    }
  ]
}
```

The score is computed **only** on the server — the frontend never submits a score.
Attempt limits (`max_attempts`) are enforced server-side; exceeding them returns
`400` with code `attempt_limit_reached`. The correct-answer key is revealed only
after submission.

---

## Leaderboard — `/api/v1/leaderboard/`

| Method | Path           | Access        | Notes                     |
| ------ | -------------- | ------------- | ------------------------- |
| GET    | ``             | authenticated | paginated ranking         |
| GET    | `top/`         | authenticated | top-N shortcut            |
| GET    | `me/`          | authenticated | own rank and score        |
| GET    | `snapshots/`   | authenticated | historical top-N captures |
| POST   | `recalculate/` | admin         | force a rebuild           |

Ranking is computed with database aggregation over an indexed derived table —
never by loading every student into Python. Ordering: `total_score` desc, then
`lessons_completed`, then `courses_completed`, then account age as a stable
tie-breaker.

Score weighting (documented so the ranking is explainable):
`total_score = quiz_score + (lessons_completed × 10)`.

---

## Notifications — `/api/v1/notifications/`

| Method | Path            | Access                                  |
| ------ | --------------- | --------------------------------------- |
| GET    | ``              | authenticated — own notifications       |
| GET    | `unread-count/` | authenticated                           |
| POST   | `read/`         | authenticated — mark one or all as read |

Email delivery is asynchronous; in-app rows are written immediately.

---

## Admin surface

Django admin at `/admin/` covers users, courses, sections, lessons, videos,
subscriptions, payments, webhook events, quizzes, questions, options, quiz
attempts, leaderboard entries and notifications, with list filters and search.
The REST admin endpoints listed above back the `/admin` SPA section and are
restricted by `IsAdminRole` / `IsInstructorOrAdmin`.

> Frontend route guards for `/admin` are a convenience. Every admin endpoint
> re-checks the role server-side.
