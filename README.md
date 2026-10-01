# LawSchool — Learning Management System

A production-oriented LMS for legal education: subscription-gated courses, protected
video streaming, quizzes with server-side scoring, progress tracking and leaderboards.

> **Status:** Phases 1–8 implemented and green — **299 backend tests** and
> **55 frontend tests** passing, frontend production build verified.

---

## Table of contents

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Database setup & migrations](#database-setup--migrations)
- [Running the backend](#running-the-backend)
- [Running the frontend](#running-the-frontend)
- [Running Celery](#running-celery)
- [Docker setup](#docker-setup)
- [Razorpay configuration](#razorpay-configuration)
- [Cloudflare Stream configuration](#cloudflare-stream-configuration)
- [API overview](#api-overview)
- [Test commands](#test-commands)
- [Production deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Further documentation](#further-documentation)

---

## Architecture

```
                        Internet
                           │
                           ▼
                    Cloudflare / CDN
                     │            │
      HTML/JS/CSS    │            │  video segments (signed, Cloudflare Stream)
                     ▼            ▼
              Nginx / Load Balancer          Cloudflare Stream
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   React SPA (Vite)         Django REST API (DRF + JWT)
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
            PostgreSQL         Redis          Celery worker
          (system of record) (cache/broker)  + Celery beat
                                                  │
                                                  ▼
                                           Background jobs:
                                           expiry, reconciliation,
                                           email, video sync,
                                           leaderboard rebuild
```

### Principles

**Authorization is a backend concern, always.** Route guards in React are UX
conveniences; every protected resource is independently authorized on the server.
The single chokepoint is `can_user_access_course(user, course)` in
`apps/subscriptions/services.py` — course, lesson and video endpoints all funnel
through it.

**Payments are proven, never asserted.** A client saying "payment succeeded" is
treated as a claim awaiting verification. Subscription state only changes inside a
database transaction after a server-side HMAC signature check (checkout) or a
webhook signature check.

**Video bytes never touch Django.** Cloudflare Stream owns encoding and delivery;
Django stores only metadata and mints short-lived signed playback tokens. No
permanent, unrestricted video URL is ever returned to a student.

**Money is `Decimal`, never `float`.** All amounts are `DecimalField`.

**The cache is an optimisation, not a source of truth.** Entitlement answers are
cached per user but always re-verified against the database, so a stale or flushed
cache can never grant access it shouldn't.

**Layering.** Views orchestrate only. Business rules live in `services/`, complex
reads in `selectors/`, validation in `serializers/`, access control in
`permissions/` + the entitlement service, and slow work in `tasks/`.

### Technology stack

| Layer          | Choice                                                               |
| -------------- | -------------------------------------------------------------------- |
| Frontend       | React 19, Vite 8, React Router 7, Axios, Tailwind CSS 4, Context API |
| Backend        | Python 3.12, Django 5, Django REST Framework, SimpleJWT              |
| Database       | PostgreSQL (SQLite fallback for zero-config local dev)               |
| Cache / broker | Redis (locmem fallback for local dev)                                |
| Async          | Celery + Celery Beat                                                 |
| Payments       | Razorpay                                                             |
| Video          | Cloudflare Stream                                                    |
| Docs           | drf-spectacular (OpenAPI 3 + Swagger UI + ReDoc)                     |

---

## Repository layout

```text
LAWSCHOOL/
├── frontend/
│   ├── src/
│   │   ├── components/      reusable UI (VideoPlayer, RouteGuards, Layout, …)
│   │   ├── pages/           Home, Courses, CourseDetails, VideoPlayer, Quiz,
│   │   │                    Leaderboard, Profile, Subscription, Auth, Admin
│   │   ├── services/        one module per API area (thin, axios-based)
│   │   ├── hooks/           useCheckout, useVideoProgress, useAsync
│   │   ├── context/         AuthContext, UIContext
│   │   ├── routes/          AppRoutes (lazy-loaded route tree)
│   │   └── utils/           format.js, validation.js
│   ├── package.json
│   └── .env.example
│
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/        base.py, development.py, production.py, test.py
│   │   ├── urls.py          versioned routing under /api/v1/
│   │   ├── celery.py        Celery app + beat schedule
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── core/            constants, permissions, exceptions, pagination,
│   │   │                    validators, logging, maintenance tasks
│   │   ├── users/           custom user, JWT auth, roles
│   │   ├── courses/         Course → Section → Lesson, selectors
│   │   ├── subscriptions/   Plans, Subscription, entitlement service
│   │   ├── videos/          Cloudflare Stream metadata, progress tracking
│   │   ├── quizzes/         Quiz → Question → Option, attempts, scoring
│   │   ├── payments/        Razorpay orders, verification, webhooks
│   │   ├── leaderboard/     aggregation-based ranking
│   │   └── notifications/   email + in-app notifications
│   ├── conftest.py          shared pytest fixtures and factories
│   ├── pytest.ini
│   ├── requirements/        base.txt, development.txt, production.txt
│   └── .env.example
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── database.md
│   ├── payments.md
│   ├── video-security.md
│   └── deployment.md
│
├── legacy-static-site/      original HTML/CSS/JS prototype (preserved)
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## Prerequisites

| Tool             | Version | Notes                                              |
| ---------------- | ------- | -------------------------------------------------- |
| Python           | 3.12+   |                                                    |
| Node.js          | 20+     | 22 LTS recommended                                 |
| PostgreSQL       | 15+     | Optional locally; SQLite is the fallback           |
| Redis            | 7+      | Optional locally; `CACHE_BACKEND=locmem` avoids it |
| Docker + Compose | 24+     | Only for the containerised path                    |

---

## Quick start

### Option A — local processes (fastest for development)

```powershell
# 1. Backend
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements\development.txt
Copy-Item .env.example .env          # then edit as needed
python manage.py migrate
python manage.py seed_demo           # optional but recommended
python manage.py runserver 8000
```

```powershell
# 2. Frontend (second terminal)
cd frontend
npm install
Copy-Item .env.example .env
npm run dev                          # http://localhost:5173
```

`seed_demo` creates an instructor, a student, plans, courses, lessons, quizzes and
leaderboard rows so every screen has real data. It prints the credentials it made.

> Running with no PostgreSQL and no Redis works out of the box: set
> `DATABASE_URL=sqlite:///db.sqlite3` and `CACHE_BACKEND=locmem` in `backend/.env`.
> This is intentionally supported so a new contributor needs one command, not an
> infrastructure project.

### Option B — Docker

```powershell
docker compose up --build        # postgres, redis, backend, celery-beat, frontend
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
```

See [Docker setup](#docker-setup).

---

## Environment variables

Secrets are read **only** from the environment. Nothing is hard-coded, and
`.env` is git-ignored.

### `backend/.env`

```env
SECRET_KEY=                 # generate: python -c "import secrets;print(secrets.token_urlsafe(64))"
DEBUG=True
DJANGO_SETTINGS_MODULE=config.settings.development
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgres://lawschool:lawschool@localhost:5432/lawschool
REDIS_URL=redis://127.0.0.1:6379/0
CACHE_BACKEND=redis         # set to `locmem` to run without Redis

JWT_SECRET=                 # falls back to SECRET_KEY if blank
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7

CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173
FRONTEND_URL=http://localhost:5173

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_STREAM_SIGNING_KEY=      # "<key_id>:<secret>"
CLOUDFLARE_STREAM_CUSTOMER_CODE=
CLOUDFLARE_PLAYBACK_TOKEN_TTL=300
```

Full annotated list: [`backend/.env.example`](backend/.env.example).
Production additionally **refuses to boot** if any required secret is missing
(see `config/settings/production.py`).

### `frontend/.env`

Only `VITE_`-prefixed values reach the browser. Never put a secret here.

```env
VITE_API_BASE_URL=/api/v1
VITE_PROXY_TARGET=http://localhost:8000
VITE_RAZORPAY_KEY_ID=               # public key id only
VITE_CLOUDFLARE_CUSTOMER_CODE=
```

---

## Database setup & migrations

```powershell
cd backend

# PostgreSQL via Docker (skip if using SQLite)
docker run --name lawschool-pg -e POSTGRES_USER=lawschool ^
  -e POSTGRES_PASSWORD=lawschool -e POSTGRES_DB=lawschool ^
  -p 5432:5432 -d postgres:16

python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
```

Useful commands:

```powershell
python manage.py showmigrations
python manage.py sqlmigrate users 0001     # inspect generated SQL
python manage.py dbshell
```

Index strategy and constraints are documented in
[`docs/database.md`](docs/database.md).

---

## Running the backend

```powershell
cd backend
..\.venv\Scripts\Activate.ps1
python manage.py runserver 8000
```

| URL                                 | Purpose              |
| ----------------------------------- | -------------------- |
| `http://localhost:8000/health/`     | liveness probe       |
| `http://localhost:8000/admin/`      | Django admin         |
| `http://localhost:8000/api/v1/`     | versioned API root   |
| `http://localhost:8000/api/docs/`   | Swagger UI           |
| `http://localhost:8000/api/redoc/`  | ReDoc                |
| `http://localhost:8000/api/schema/` | raw OpenAPI 3 schema |

---

## Running the frontend

```powershell
cd frontend
npm install
npm run dev            # http://localhost:5173
npm run build          # production bundle -> dist/
npm run preview        # serve the built bundle on :4173
npm test               # vitest
```

In development Vite proxies `/api` to `VITE_PROXY_TARGET`, so requests stay
same-origin and CORS/CSRF behave exactly as they do in production behind Nginx.

---

## Running Celery

Required only for background work (email, expiry, reconciliation, video sync,
leaderboard rebuild). The API stays correct without a worker.

```powershell
cd backend
..\.venv\Scripts\Activate.ps1

# worker
celery -A config worker -l info -P solo      # -P solo is required on Windows

# beat scheduler (separate terminal)
celery -A config beat -l info
```

Scheduled jobs (see `CELERY_BEAT_SCHEDULE`):

| Task                               | Cadence | Purpose                                       |
| ---------------------------------- | ------- | --------------------------------------------- |
| `expire_subscriptions`             | hourly  | flip lapsed subscriptions to EXPIRED, notify  |
| `send_expiry_reminders`            | daily   | warn students 7 days before expiry            |
| `reconcile_payments`               | 15 min  | resolve payments stuck after a missed webhook |
| `sync_pending_videos`              | 10 min  | poll Cloudflare for assets stuck processing   |
| `retry_failed_notification_emails` | hourly  | retry failed delivery                         |
| `recalculate_leaderboard_task`     | daily   | rebuild ranks                                 |

For tests and local demos, `CELERY_TASK_ALWAYS_EAGER=True` runs tasks inline.

---

## Docker setup

`docker-compose.yml` defines: `postgres`, `redis`, `backend`, `celery`,
`celery-beat`, `frontend`.

```powershell
docker compose up --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
docker compose logs -f backend
docker compose down            # add -v to also destroy volumes
```

Service ports: frontend `5173` (dev) / `80` (prod profile), backend `8000`,
postgres `5432`, redis `6379`.

---

## Razorpay configuration

1. Create an account and switch to **Test Mode** for development.
2. **Settings → API Keys → Generate** → copy the _Key ID_ and _Key Secret_ into
   `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`.
3. **Settings → Webhooks → Add New Webhook**
   - URL: `https://<your-domain>/api/v1/payments/webhook/`
   - Secret: generate a strong random string → `RAZORPAY_WEBHOOK_SECRET`
   - Events: `payment.captured`, `payment.failed`, `payment.authorized`,
     `refund.created`, `refund.processed`, `order.paid`
4. Test cards and the `rzp_test_*` keys work end-to-end in test mode.

Flow (full detail in [`docs/payments.md`](docs/payments.md)):

```
Student → select plan → POST /api/v1/payments/orders/   (server creates order)
        → Razorpay checkout opens in the browser
        → success callback → POST /api/v1/payments/verify/  (server checks HMAC)
        → subscription activated inside a transaction
```

Independently, Razorpay calls the webhook. Both paths are **idempotent** and
converge on the same state, so a missed callback or a duplicate webhook cannot
activate a subscription twice or leave it stuck.

---

## Cloudflare Stream configuration

1. Cloudflare dashboard → **Stream** → note the **Account ID** →
   `CLOUDFLARE_ACCOUNT_ID`.
2. **My Profile → API Tokens → Create Token** with the _Stream: Edit_ permission →
   `CLOUDFLARE_API_TOKEN`.
3. **Stream → Settings → Signing Keys → Create** →
   `CLOUDFLARE_STREAM_SIGNING_KEY` in the form `<key_id>:<secret>`.
4. Copy the customer subdomain code (the `customer-<code>` part of playback URLs) →
   `CLOUDFLARE_STREAM_CUSTOMER_CODE`.
5. Set `require_signed_urls` on each video; instructors typically upload straight
   from the admin via `POST /api/v1/videos/upload-url/` (a direct creator upload),
   so bytes never transit Django.

Playback flow: the browser asks Django for a token
(`GET /api/v1/videos/{id}/playback/`); Django authenticates the user, checks the
active subscription, checks course entitlement and lesson access, and only then
returns a **short-lived signed token** (`CLOUDFLARE_PLAYBACK_TOKEN_TTL`, default
300s). See [`docs/video-security.md`](docs/video-security.md).

---

## API overview

All endpoints are under `/api/v1/`. Protected endpoints require
`Authorization: Bearer <access_token>`. Errors share one envelope:

```json
{ "error": { "code": "not_authenticated", "message": "…", "details": {} } }
```

| Area          | Endpoints                                                                                                                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth          | `auth/register/`, `auth/login/`, `auth/refresh/`, `auth/logout/`, `auth/logout-all/`, `auth/me/`, `auth/password/change/`, `auth/password-reset/`, `auth/password-reset-confirm/`, `auth/verify-email/` |
| Users         | `users/`, `users/me/`, `users/<uuid>/`                                                                                                                                                                  |
| Courses       | `courses/`, `courses/<slug>/`, `courses/<slug>/lessons/`, `courses/<slug>/access/`                                                                                                                      |
| Sections      | `sections/`, `sections/<uuid>/`                                                                                                                                                                         |
| Lessons       | `lessons/`, `lessons/<uuid>/`, `lessons/<uuid>/watch/`                                                                                                                                                  |
| Videos        | `videos/`, `videos/register/`, `videos/upload-url/`, `videos/<uuid>/`, `videos/<uuid>/playback/`, `videos/<uuid>/progress/`, `videos/<uuid>/sync/`                                                      |
| Progress      | `progress/`, `progress/course/<slug>/`                                                                                                                                                                  |
| Subscriptions | `subscriptions/plans/`, `subscriptions/me/`, `subscriptions/me/cancel/`, `subscriptions/history/`                                                                                                       |
| Payments      | `payments/orders/`, `payments/verify/`, `payments/`, `payments/webhook/`                                                                                                                                |
| Quizzes       | `quizzes/`, `quizzes/<uuid>/`, `quizzes/<uuid>/attempts/`, `quizzes/<uuid>/progress/`, `quiz-attempts/`, `quiz-attempts/<uuid>/submit/`                                                                 |
| Leaderboard   | `leaderboard/`, `leaderboard/top/`, `leaderboard/me/`                                                                                                                                                   |
| Notifications | `notifications/`, `notifications/unread-count/`, `notifications/read/`                                                                                                                                  |

Full request/response shapes, permissions and status codes:
[`docs/api.md`](docs/api.md) and the live Swagger UI at `/api/docs/`.

---

## Test commands

```powershell
# Backend — 231 tests
cd backend
..\.venv\Scripts\python.exe -m pytest                 # whole suite
..\.venv\Scripts\python.exe -m pytest -q              # quiet
..\.venv\Scripts\python.exe -m pytest apps/payments   # one app
..\.venv\Scripts\python.exe -m pytest -k webhook      # by name
..\.venv\Scripts\python.exe -m pytest --lf            # last failed only
```

```powershell
# Frontend — 50 tests
cd frontend
npm test
npm test -- RouteGuards        # filter
```

Backend coverage by area: authentication, subscription entitlement (active /
expired / cancelled / unauthorized), payments (valid signature, invalid signature,
duplicate webhook, failed payment), video security (authorized, unauthorized,
expired subscription, another user's content), quizzes (valid/invalid attempt,
scoring, attempt limits), progress validation, leaderboard, and courses.

---

## Production deployment

Short version:

```powershell
# backend
set DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
celery -A config worker -l info
celery -A config beat -l info

# frontend
npm ci && npm run build      # serve dist/ from Nginx
```

Production settings enforce: `DEBUG=False`, `SECURE_SSL_REDIRECT`, HSTS with
preload, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, secure HttpOnly
samesite cookies, JSON structured logging, and a hard failure at boot if any
required secret is unset.

Full checklist, Nginx config, horizontal-scaling notes and rollback procedure:
[`docs/deployment.md`](docs/deployment.md).

---

## Troubleshooting

**`CLOUDFLARE_STREAM_SIGNING_KEY is not configured`**
Expected without real Cloudflare credentials. Set the variable, or exercise
playback through the test suite, which stubs the signing key. The API returns
**503** (not 500) for this misconfiguration.

**`python` / `node` not recognised**
Not on `PATH`. Use the venv interpreter directly
(`C:\dev\venvs\lawschool\Scripts\python.exe`) and
`C:\Program Files\nodejs\npm.cmd`, or add both to `PATH`.

**`celery` exits immediately on Windows**
Run with `-P solo`. Celery's default prefork pool is not supported on Windows.

**CORS errors in the browser**
`CORS_ALLOWED_ORIGINS` must list the exact origin **including scheme and port**.
In dev, prefer the Vite proxy and leave `VITE_API_BASE_URL=/api/v1`.

**401 on every request right after login**
The access token expired. The axios client refreshes transparently and retries
once; if refresh also fails the user is logged out. Check that
`JWT_ACCESS_MINUTES` is sane and that the client and server clocks agree.

**Login fails with a correct password**
Password policy requires 10+ characters and rejects common/numeric-only
passwords. `createsuperuser` and `create_user` bypass validators by design;
`RegisterSerializer` does not.

**Subscription is ACTIVE but content is locked**
Entitlement requires **both** `status=ACTIVE` **and** a valid
`start_date <= now <= end_date`. A row with status `ACTIVE` but a past `end_date`
is treated as expired. The hourly `expire_subscriptions` job corrects the stored
status.

**Webhook returns 400**
Signature mismatch: `RAZORPAY_WEBHOOK_SECRET` must match the dashboard value
exactly. Razorpay retries automatically; processing is idempotent.

**Frontend build can't find `node`**
`npm.cmd` shells out to `node`; ensure Node's directory is on `PATH`, or invoke
Vite directly: `node .\node_modules\vite\bin\vite.js build`.

---

## Further documentation

| Document                                           | Contents                                                     |
| -------------------------------------------------- | ------------------------------------------------------------ |
| [`docs/architecture.md`](docs/architecture.md)     | layering, request lifecycle, scaling, decisions & trade-offs |
| [`docs/api.md`](docs/api.md)                       | every endpoint, payloads, permissions, status codes          |
| [`docs/database.md`](docs/database.md)             | schema, relationships, indexes, constraints                  |
| [`docs/payments.md`](docs/payments.md)             | Razorpay flow, idempotency, failure handling                 |
| [`docs/video-security.md`](docs/video-security.md) | signed playback, threat model, anti-cheat                    |
| [`docs/deployment.md`](docs/deployment.md)         | production build, Nginx, hardening, rollback                 |

---

## License

UNLICENSED — proprietary. All rights reserved.
