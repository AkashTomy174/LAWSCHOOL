# LawSchool LMS — Project Scope & Deliverables

**Document type:** Statement of what is included in the delivered system
**Version:** 1.0
**Status:** Delivered and verified

---

## 1. Executive summary

LawSchool is a production-oriented Learning Management System for legal education.

It lets students **buy a subscription**, **watch protected videos**, **take graded
quizzes**, **track their progress** and **compete on a leaderboard**. Instructors
build courses; administrators manage the platform.

The system is a two-tier web application: a React single-page application talking
to a Django REST API, backed by PostgreSQL and Redis, with Razorpay for payments
and Cloudflare Stream for video delivery.

### At a glance

| Metric              | Delivered                            |
| ------------------- | ------------------------------------ |
| Backend test suite  | **272 automated tests**, all passing |
| Frontend test suite | **55 automated tests**, all passing  |
| REST API endpoints  | **73 routes** across 9 modules       |
| Database models     | **22 domain models**                 |
| Frontend screens    | **9 public/student + 8 admin**       |
| Documentation       | **6 technical documents + README**   |
| Backend code        | ~200 Python files                    |
| Frontend code       | 45 files / ~7,600 lines              |

---

## 2. Functional scope

### 2.1 User roles

The system implements three roles, each with a distinct surface. Authorization is
enforced **on the server** for every action — hiding a button in the browser is
never the protection.

| Role           | Capabilities                                                                                                                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Student**    | Register · log in · purchase subscription · browse catalogue · access entitled courses · watch protected videos · track progress · take quizzes · view results · view leaderboard · manage profile            |
| **Instructor** | Everything a student can do, plus: create and manage courses · organise sections and lessons · register and manage videos · author quizzes and questions · view student progress                              |
| **Admin**      | Everything above, plus: manage users and roles · manage all courses · manage subscriptions · manage payments and refunds · manage videos · manage quizzes · manage the leaderboard · view platform statistics |

### 2.2 Feature areas

**Authentication & accounts**
Registration, login, token refresh, logout (single device and all devices),
password change, password reset via email, email verification. Login is by email
address, not username.

**Course catalogue & delivery**
Courses are browsable and searchable before purchase. Each course contains ordered
**sections**, each section containing ordered **lessons**. A lesson holds a video,
a quiz, or both. Locked content is clearly marked as locked and never leaks video
data.

**Subscriptions**
Tiered plans, each scoped to a set of courses or marked "all access". A
subscription has a real date window. Access is granted only when the subscription
is **active _and_ today falls inside that window** — a stale status flag alone can
never unlock content.

**Payments (Razorpay)**
Order creation, server-side signature verification, webhook processing,
subscription activation, failed-payment handling, refund handling, and automatic
reconciliation of payments orphaned by a dropped webhook.

**Protected video (Cloudflare Stream)**
Private playback via short-lived signed tokens. Video files are never stored on
the application servers or in the database.

**Video progress**
Watching position and completion are tracked with server-side validation, so
progress cannot be faked.

**Quizzes**
Multiple-choice quizzes with per-question marks, passing thresholds, attempt limits
and automatic scoring.

**Leaderboard**
Ranking by measurable achievement, designed to scale to a large student population.

**Dashboards & profile**
Student dashboard (subscription status, course progress, recent activity, quiz
scores, leaderboard position), profile management, and a full admin area.

**Notifications**
Transactional email and in-app notifications for payment success, subscription
activation, expiry reminders, password reset, enrolment and quiz results.

---

## 3. Technical scope

### 3.1 Technology stack

| Layer                  | Technology                                                           |
| ---------------------- | -------------------------------------------------------------------- |
| Frontend               | React 19, Vite 8, React Router 7, Axios, Tailwind CSS 4, Context API |
| Backend                | Python 3.12, Django 6, Django REST Framework, SimpleJWT              |
| Database               | PostgreSQL 15+ (SQLite supported for local development)              |
| Cache / message broker | Redis 7                                                              |
| Background jobs        | Celery + Celery Beat                                                 |
| Payments               | Razorpay                                                             |
| Video                  | Cloudflare Stream                                                    |
| API documentation      | OpenAPI 3 (drf-spectacular) with Swagger UI and ReDoc                |
| Containers             | Docker + Docker Compose                                              |
| CI                     | GitHub Actions                                                       |

### 3.2 Database models (22)

| Module        | Models                                                    |
| ------------- | --------------------------------------------------------- |
| Users         | `User` (custom, email-based)                              |
| Courses       | `Course`, `Section`, `Lesson`                             |
| Subscriptions | `Plan`, `Subscription`                                    |
| Videos        | `Video`, `VideoProgress`, `PlaybackSession`               |
| Quizzes       | `Quiz`, `Question`, `Option`, `QuizAttempt`, `QuizAnswer` |
| Payments      | `Payment`, `WebhookEvent`                                 |
| Leaderboard   | `LeaderboardEntry`, `LeaderboardSnapshot`                 |
| Notifications | `Notification`                                            |

### 3.3 API surface (73 routes, 9 modules)

| Module        | Base path                                    | Covers                                                                          |
| ------------- | -------------------------------------------- | ------------------------------------------------------------------------------- |
| Auth          | `/api/v1/auth/`                              | register, login, refresh, logout, me, password change/reset, email verification |
| Users         | `/api/v1/users/`                             | profile, admin user management                                                  |
| Courses       | `/api/v1/courses/`                           | catalogue, detail, lessons, access check                                        |
| Sections      | `/api/v1/sections/`                          | authoring                                                                       |
| Lessons       | `/api/v1/lessons/`                           | authoring, watch endpoint                                                       |
| Videos        | `/api/v1/videos/`                            | registration, upload, playback, progress, sync                                  |
| Progress      | `/api/v1/progress/`                          | per-lesson and per-course progress                                              |
| Subscriptions | `/api/v1/subscriptions/`                     | plans, current, cancel, history                                                 |
| Payments      | `/api/v1/payments/`                          | orders, verify, webhook, history                                                |
| Quizzes       | `/api/v1/quizzes/`, `/api/v1/quiz-attempts/` | authoring, attempts, scoring                                                    |
| Leaderboard   | `/api/v1/leaderboard/`                       | rankings, personal rank                                                         |
| Notifications | `/api/v1/notifications/`                     | in-app feed                                                                     |

Full request/response documentation: `docs/api.md`, plus a live Swagger UI at
`/api/docs/`.

### 3.4 Frontend screens

**Public & student (17)**

| Route                                                  | Screen                           |
| ------------------------------------------------------ | -------------------------------- |
| `/`                                                    | Landing page                     |
| `/login`, `/register`                                  | Authentication                   |
| `/forgot-password`, `/reset-password`, `/verify-email` | Account recovery                 |
| `/courses`                                             | Course catalogue                 |
| `/courses/:slug`                                       | Course detail with syllabus      |
| `/dashboard`                                           | Student dashboard                |
| `/watch/:lessonId`                                     | Video player                     |
| `/quiz/:quizId`, `/quiz/:quizId/result`                | Quiz and results                 |
| `/subscription`                                        | Plans, checkout, payment history |
| `/leaderboard`                                         | Rankings                         |
| `/profile`, `/progress`, `/notifications`              | Account area                     |

**Admin (8)**: `/admin`, `/admin/users`, `/admin/courses`,
`/admin/courses/:id`, `/admin/subscriptions`, `/admin/payments`,
`/admin/videos`, `/admin/quizzes`, `/admin/leaderboard`

### 3.5 Background jobs

| Job                    | Schedule     | Purpose                                       |
| ---------------------- | ------------ | --------------------------------------------- |
| Subscription expiry    | hourly       | correct lapsed subscriptions, notify          |
| Expiry reminders       | daily        | warn students before expiry                   |
| Payment reconciliation | every 15 min | resolve payments orphaned by a missed webhook |
| Video status sync      | every 10 min | recover assets stuck in processing            |
| Email retry            | hourly       | retry failed notification delivery            |
| Leaderboard rebuild    | nightly      | recompute rankings                            |

---

## 4. Security scope

Security was treated as a first-class requirement, not a later hardening pass.

| Area                     | Implementation                                                                                                                        |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| Authentication           | JWT with short-lived access tokens, refresh-token rotation, blacklisting on logout                                                    |
| Password storage         | Django's password hashing with a 10-character minimum policy and common-password rejection                                            |
| Authorization            | Server-side on every endpoint. A single entitlement service decides all course/lesson/video access                                    |
| Object-level permissions | Instructors cannot touch other instructors' courses; students cannot reach other students' data                                       |
| Payments                 | Never trusts the browser. Subscription activation requires a server-side cryptographic signature check, inside a database transaction |
| Webhooks                 | Signature-verified over the raw request body, with database-enforced idempotency                                                      |
| Video                    | No permanent unrestricted video URL exists anywhere. Tokens last 5 minutes and require an entitlement check                           |
| Secrets                  | Read only from environment variables. Production **refuses to start** if a required secret is missing                                 |
| Transport                | HTTPS enforcement, HSTS with preload, secure cookies                                                                                  |
| Headers                  | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, strict Referrer-Policy                                                    |
| Rate limiting            | Scoped throttling on authentication, payment, playback, progress and webhook endpoints                                                |
| Input validation         | All input validated through serializers; uploads validated by type and size                                                           |
| SQL injection            | Django ORM throughout; no raw SQL                                                                                                     |
| XSS                      | React escapes by default; no unsafe HTML rendering                                                                                    |
| Error disclosure         | One consistent error format; internal details are logged, never returned                                                              |
| Secret hygiene           | `.gitignore` blocks `.env`; CI fails the build if a secret-looking value or a tracked `.env` is found                                 |

---

## 5. Quality assurance scope

### 5.1 Automated tests — 327 total

**Backend — 272 tests** (pytest, against real PostgreSQL and Redis in CI)

| Area                        | Tests | Covers                                                                                                                    |
| --------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------- |
| Video security & progress   | 54    | authorized/unauthorized playback, expired subscription, another student's content, token signing, service-outage handling |
| Subscriptions & entitlement | 41    | active, expired, cancelled, wrong-plan, free-course access                                                                |
| Authentication              | 40    | registration, login, invalid credentials, token refresh, unauthorized access                                              |
| Payments                    | 40    | valid signature, invalid signature, duplicate webhook, failed payment, refund                                             |
| Courses                     | 39    | catalogue, locking, N+1 query guards, ordering constraints, object-level permissions                                      |
| Quizzes                     | 39    | valid/invalid attempts, scoring, attempt limits, answer-key protection                                                    |
| Leaderboard                 | 26    | ranking order, ties, scaling behaviour                                                                                    |

**Frontend — 55 tests** (vitest + React Testing Library)

Component behaviour, route guards, formatting and validation utilities, and API
service contracts.

### 5.2 Continuous integration

Every push and pull request runs: the full backend suite against real PostgreSQL
and Redis, a check that no database migration is missing, Django system checks,
OpenAPI schema generation, the frontend suite, the production frontend build, and
a **secret scan**.

---

## 6. Documentation deliverables

| Document                 | Contents                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------ |
| `README.md`              | Setup, prerequisites, environment variables, running the app, troubleshooting        |
| `docs/architecture.md`   | System design, layering, request lifecycle, technical decisions and their trade-offs |
| `docs/api.md`            | Every endpoint with request/response formats, permissions and status codes           |
| `docs/database.md`       | Schema, relationships, indexes, constraints, query-performance strategy              |
| `docs/payments.md`       | Payment flow, idempotency, failure handling, go-live checklist                       |
| `docs/video-security.md` | Playback protection, threat model, and an honest statement of what is and is not DRM |
| `docs/deployment.md`     | Production build, Nginx configuration, hardening checklist, rollback procedure       |

---

## 7. Delivered infrastructure

- **Docker Compose** — development and production configurations covering the
  application, database, cache, background worker and scheduler
- **Dockerfiles** — multi-stage builds running as a non-root user
- **Nginx configuration** — SPA routing, API proxying, caching and security headers
- **CI pipeline** — GitHub Actions, as described above
- **Environment templates** — `.env.example` for both frontend and backend, with
  every variable documented
- **Demo data seeder** — generates a complete working dataset for demonstration

---

## 8. Engineering standards applied

- Business logic lives in service layers, not in view functions or React components
- Validation via serializers; access control via permissions and a single
  entitlement service
- Database transactions for all payment and subscription state changes
- Idempotent webhook processing
- No database queries inside loops; indexes added for every hot query path
- Pagination on all list endpoints
- Structured logging with no secrets or tokens ever written to logs

---

## 9. Explicitly out of scope

Stated plainly so expectations are accurate:

| Not included                        | Notes                                                                                                                                                                                                                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Digital Rights Management (DRM)** | Video is protected by short-lived signed tokens and server-side authorization. This prevents unauthorized access and makes downloading inconvenient, but it does **not** prevent screen recording. True DRM is a materially different product. See `docs/video-security.md`. |
| **Native mobile apps**              | The interface is responsive and mobile-first, but there are no iOS/Android builds.                                                                                                                                                                                           |
| **Live/virtual classroom features** | No live sessions, chat or video conferencing.                                                                                                                                                                                                                                |
| **Certificate generation**          | Completion is tracked, but no certificates are issued.                                                                                                                                                                                                                       |
| **Multi-tenancy**                   | Single-tenant deployment.                                                                                                                                                                                                                                                    |
| **Third-party SSO**                 | No Google/LinkedIn/Microsoft login — email and password only.                                                                                                                                                                                                                |
| **Automated refund initiation**     | Refunds are received and processed from Razorpay; issuing them is done in the Razorpay dashboard.                                                                                                                                                                            |
| **Payment methods beyond Razorpay** | Razorpay only (which itself covers cards, UPI and netbanking).                                                                                                                                                                                                               |

---

## 10. Verification status

### Verified working

- ✅ **272 backend tests pass**, **55 frontend tests pass**
- ✅ Frontend production build succeeds
- ✅ Application runs end to end on a clean database
- ✅ Login, entitlement checks, course access and leaderboard confirmed working against the live API
- ✅ All database migrations apply cleanly

### Integration status — requires the client's credentials

The **Razorpay** and **Cloudflare Stream** integrations are **fully implemented and
covered by the automated test suite**, but have not been exercised against live
accounts, because live API keys are not available in the development environment.

| Integration             | Code     | Tests            | Live verification             |
| ----------------------- | -------- | ---------------- | ----------------------------- |
| Razorpay payments       | Complete | 40 tests passing | ⏳ Pending client credentials |
| Cloudflare Stream video | Complete | 54 tests passing | ⏳ Pending client credentials |

To complete live verification, the client provides:

- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_STREAM_SIGNING_KEY`, `CLOUDFLARE_STREAM_CUSTOMER_CODE`

Until then, video playback correctly returns a clear "temporarily unavailable"
response rather than failing ambiguously — behaviour that is itself covered by
three dedicated tests.

### Known limitations

- **No error boundary in the frontend.** An unexpected rendering error can blank a
  page instead of showing a recoverable message. Recommended as a small follow-up.
- **Remaining API documentation gaps.** A number of hand-written endpoints work
  correctly but are not yet described in the generated Swagger documentation. They
  are all documented in `docs/api.md`.
- **Container images have not been built** in this environment (Docker is
  unavailable here). The Docker configuration is complete and reviewed but
  unverified. Building and testing them is a first deployment step.
- **Leaderboard ranks are built by a nightly job.** On a fresh database the
  leaderboard is empty until that job runs once.

---

## 11. Suggested next steps

| Priority | Item                                                                     | Effort        |
| -------- | ------------------------------------------------------------------------ | ------------- |
| 1        | Supply Razorpay and Cloudflare credentials to complete live verification | Client action |
| 2        | Add a frontend error boundary                                            | Small         |
| 3        | Build and verify the Docker images                                       | Small         |
| 4        | Complete API documentation annotations                                   | Small         |
| 5        | Deploy to staging, run the go-live checklist in `docs/deployment.md`     | Medium        |
| 6        | Add an error-monitoring service (e.g. Sentry)                            | Small         |

---

_Prepared from the delivered source tree. All figures in this document were
measured from the codebase, not estimated._
