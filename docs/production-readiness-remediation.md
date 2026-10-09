# Production readiness remediation

Remediation of the findings from the October 2026 production-readiness audit,
on branch `main` (13 commits on top of the 5 already-reviewed local commits,
none pushed). Date: 2026-10-09.

Nothing was pushed, deployed, migrated in production, or changed in Railway,
Vercel, Cloudflare, Razorpay or email settings. No real payments, refunds or
emails were triggered. No secret values appear in this document.

## A. Executive summary

| | |
|---|---|
| Initial status | **NOT READY**: backend down, deep links broken, paying users could lose access, quizzes unreachable, uploads lost on deploy, Redis outage = full outage |
| Final status | **READY FOR PUSH**: code-side fixes are complete and tested. Deployment still needs the manual configuration in section F. |
| Findings investigated | 20 (A–M, with M split into its eight parts) |
| Confirmed | 15 |
| Fixed in code | 13 |
| Partially fixed (code done, external step required) | 5 (D, E, F, I, J) |
| Blocked on external access | 1 (D: production startup needs `CLOUDFLARE_STREAM_KEY_ID`) |
| Not reproducible / already correct | 5 (M-B privilege escalation, M-E answer review, M-F draft visibility, M-G live-class host, M-H cache ordering) |
| Documented only, by design | 1 (M-A localStorage tokens, a separate project) |

Two defects that were not in the audit were found and fixed during the work:
Cloudflare sync crashed on the real API payload (`status` is an object), so no
upload could ever become READY; and Railway's healthcheck would have been
rejected by `ALLOWED_HOSTS` and redirected by `SECURE_SSL_REDIRECT`.

## B. Findings

| ID | Finding | Confirmed? | Severity | Root cause | Fix | Tests | Status |
|---|---|---|---|---|---|---|---|
| A | Second plan revokes access to a still-paid first plan | Yes, reproduced | Critical | Entitlement read only the latest-ending subscription | Access is the union of all ACTIVE in-window subscriptions; cache TTL bounded by the covering subscription | `test_overlapping_subscriptions.py` (24) | Fixed `4aadff8` |
| B | Students cannot discover or start quizzes | Yes, reproduced in browser | Critical | Course API sent only `quiz_count`; quiz page POSTed an attempt on load | Course detail lists published quizzes; quiz page opens on an intro and starts or resumes on click; progress reports the open attempt | `test_quiz_discovery.py` (9), `Quiz.test.jsx` (8), `CourseDetails.test.jsx` (3) | Fixed `401c8eb` |
| C | Vercel deep links 404 | Yes, live `X-Vercel-Error: NOT_FOUND` | Critical | No SPA rewrite | `frontend/vercel.json` rewrite to `/index.html` | Local production build: 8 deep links render; Vercel itself not verified | Fixed `cfe2a1e`, needs deploy |
| D | Backend down: missing Cloudflare key; no usable healthcheck | Yes (Railway logs) | Critical | `CLOUDFLARE_STREAM_KEY_ID` unset → fail-fast `RuntimeError`; healthcheck host/redirect | Readiness probe; healthcheck host allowed and redirect-exempt; actionable startup error | `test_health.py` (5) | Partially fixed `52d7b0a`, **blocked** on the key |
| E | Migrations never run on deploy | Yes | Critical | Dockerfile CMD only starts gunicorn; no pre-deploy step | Railway pre-deploy command (manual, F.3); migrations reviewed | `makemigrations --check`, full migrate on PG16 | Manual step |
| F | Email delivery unconfigured | Yes (names only) | High | No `EMAIL_HOST` or credentials on Railway; possible double send | System checks W001/W002; never resend a sent notification | `test_email_delivery.py` (12) | Partially fixed `529a182`, needs a provider |
| G | Failed signed-only enforcement treated as success | Yes, reproduced | Critical | `register_video` swallowed the error; no retry | `require_signed_urls` = confirmed state; sync re-enforces and retries; playback 503 until confirmed; tokens capped at access end | `test_signed_only_enforcement.py` (12) | Fixed `b59eb39` |
| G2 | Cloudflare sync crashed on real payload *(new)* | Yes, reproduced | High | `status` is an object; used as a dict key | Read `status.state` / `errorReasonText` | same file | Fixed `b59eb39` |
| H | `.vscode/settings.json` API key could be committed | Yes | Critical (latent) | `.gitignore` re-included the file | Stop re-including it | `git check-ignore` | Fixed `a95bda6`; key never in history, no rotation needed |
| I | No Celery worker or Beat | Yes (Railway) | High | Services never created | Schedule-to-registry tests; worker verified locally; service definitions in F.3 | `test_celery_config.py` (4) + local worker run | Manual step |
| J | Uploads on ephemeral disk | Yes, worse: never served either | High | Filesystem storage; `/media/` served only with DEBUG | Optional S3-compatible storage; image installs `production.txt`; W003 check | `test_media_storage.py` (2) + S3 mock upload | Partially fixed `03cf9b1`, needs a bucket |
| K | Redis outage = full outage | Yes, reproduced | High | Every cache call raised | Per-use policy (table in E); 1s socket timeouts | `test_cache_outage.py` (11) + unreachable-Redis timing | Fixed `77df486` |
| L | Admin subscription table empty | Yes, reproduced in browser | High | Client unwrapped the paginated envelope; pages read `.results` | Return the envelope; dashboard counts `?status=active`; empty state | `test_admin_subscription_list.py` (5), `AdminSubscriptions.test.jsx` (4), service test | Fixed `d83df5a` |
| M-A | JWT tokens in localStorage | Yes (by design) | Medium | Architecture | Not changed: separate project (G) | — | Documented |
| M-B | `is_staff` = full API admin; escalation? | Model confirmed, no escalation | Info | `is_admin()` treats `is_staff` as admin | Docstring; no serializer exposes `is_staff`/`is_superuser` | `test_admin_activation.py` (2 of 7) | Not reproducible |
| M-C | Admin cannot deactivate accounts via API | Yes | Medium | `is_active` missing from `AdminUserSerializer` | Field added; refresh tokens revoked; self-deactivation refused | `test_admin_activation.py` (5 of 7) | Fixed `87d040a` |
| M-D | Video sync dead authorization branch | Yes | Info | Ownership branch unreachable behind `IsAdminRole` | Removed | existing tests | Fixed `64e6f81` |
| M-E | Answers visible before submission | No | — | — | — | `test_quiz_discovery.py` start payload test | Not reproducible |
| M-F/G/H | Earlier fixes (drafts, live host, cache ordering) regressed? | No | — | — | Preserved | full suite incl. their tests | Not reproducible |

## C. Files changed

| File | Change |
|---|---|
| `.gitignore` | Stop re-including `.vscode/settings.json` |
| `backend/apps/subscriptions/services.py` | Aggregate all active subscriptions; `AccessDecision.expires_at`; outage-safe cache reads, writes and invalidation |
| `backend/apps/videos/services.py` | Signed-only confirmed state, re-enforcement, object-status sync, token TTL cap, outage-safe limiter |
| `backend/apps/core/tasks.py` | Periodic sync also retries unconfirmed videos |
| `backend/apps/courses/{selectors,serializers}.py` | Course detail returns published quizzes (metadata only) |
| `backend/apps/quizzes/views.py` | Progress reports the open attempt |
| `backend/apps/core/{cache,throttling,checks}.py` *(new)* | Degrading cache helpers; per-scope throttle policy; email and media system checks |
| `backend/apps/core/{exceptions,apps}.py` | `TemporarilyUnavailableError` (503); register checks |
| `backend/apps/{users,payments,videos}/views.py` | Use the resilient throttle; admin deactivation; drop dead sync branch |
| `backend/apps/users/serializers.py` | `is_active` for admins |
| `backend/apps/leaderboard/views.py` | Outage-safe leaderboard cache |
| `backend/apps/notifications/services.py` | Never resend a sent notification |
| `backend/config/urls.py` | `/health/ready/` readiness probe |
| `backend/config/settings/base.py` | Resilient default throttle; Redis 1s socket timeouts |
| `backend/config/settings/production.py` | Healthcheck host and redirect exemption; actionable integration error; email and media flags; optional S3 storage |
| `backend/requirements/production.txt`, `backend/Dockerfile` | `django-storages[s3]` + `boto3`; image installs production requirements |
| `frontend/vercel.json` *(new)* | SPA rewrite |
| `frontend/src/pages/CourseDetails/CourseDetails.jsx` | Quizzes section |
| `frontend/src/pages/Quiz/Quiz.jsx` | Intro screen; start or resume on click |
| `frontend/src/services/paymentService.js`, `frontend/src/pages/Admin/AdminPages.jsx` | Admin subscriptions envelope, active count, empty state |
| Tests *(new)* | `test_overlapping_subscriptions.py`, `test_signed_only_enforcement.py`, `test_quiz_discovery.py`, `test_admin_subscription_list.py`, `test_cache_outage.py`, `test_admin_activation.py`, `test_email_delivery.py`, `test_health.py`, `test_celery_config.py`, `test_media_storage.py`, `Quiz.test.jsx`, `CourseDetails.test.jsx`, `AdminSubscriptions.test.jsx` |
| `frontend/src/services/paymentService.test.js` | One test encoded the admin-table bug (it asserted `all()` returns an array while both consumers read `.results`/`.count`); replaced by an envelope-contract test |

## D. Test results

All at HEAD `03cf9b1` unless noted.

| Check | Command | Result |
|---|---|---|
| Backend, SQLite | `python -m pytest -q` | **473 passed, 2 skipped** (was 383/2) |
| Backend, PostgreSQL 16 | same, `DATABASE_URL=postgres://…` | **473 passed, 2 skipped** |
| Backend, real Redis 7 (cache-sensitive apps) | `pytest --ds=<temp redis settings> apps/subscriptions apps/core/tests apps/videos apps/payments apps/courses apps/quizzes` | 369 passed, 2 skipped, **4 failed**: all four use `freezegun` to jump past a cache TTL, which cannot move Redis's own clock. The behavior they cover was verified on real Redis with a real clock: TTL 9s, access denied after 11s, with an overlapping non-covering subscription present. |
| Migrations | `manage.py makemigrations --check --dry-run` | No changes |
| System checks | `manage.py check` (test settings) | No issues |
| Frontend | `npx vitest run` | **88 passed** (was 73) |
| Frontend build | `npx vite build` | Succeeds |
| Browser (local, seeded) | Playwright | Course page → quiz intro (no POST on load) → start → 2/2 Passed (one attempt) → intro shows "1 of 3 used"; admin Subscriptions table shows the row; dashboard "Active subscriptions 1" |
| Deep links | `vite preview` of the production build | `/`, `/forgot-password`, `/reset-password?…`, `/verify-email`, `/dashboard`, `/courses/<slug>`, `/quiz/<id>`, unknown route: all render the right screen; refresh and back work; assets served as JS |
| Redis outage | `django-redis` → black-holed host | Login 503 in 1.2s; access check answered from the database in 1.0s |
| Celery | real worker (`--pool=solo`) + Redis broker | `reconcile_payments` and `sync_pending_videos` received and succeeded |
| Object storage | real avatar upload via `PATCH /auth/me/` against S3Mock | Stored by `S3Storage`; signed URL fetches 200. S3Mock does not enforce auth, so bucket privacy is **not verified** |
| Docker image | `docker build backend/` | Builds (594 MB); `storages`, `boto3` and Django 6.0.1 import inside the image |
| Lint / static analysis | — | **Not run**: none configured; no linter installed |
| Vercel, Railway, Cloudflare, Razorpay, email | — | **Not verified in production** (no deploys allowed) |

## E. Security review

- **Secrets.** `.vscode/settings.json` (holds an editor API key) is ignored again. The key was never committed, so no rotation is needed. No secrets in any commit (pattern scan of history: only a documented placeholder). Railway variables were inspected by name only; the IaC import used `preserve()` placeholders and was deleted.
- **Authorization.** Draft visibility (`bad13a9`) is unchanged and still tested. Authoring ownership is unchanged. No serializer exposes `is_staff`/`is_superuser`; `is_staff` remains equivalent to platform admin (grantable only by a superuser in the Django admin). Admin deactivation revokes refresh tokens and refuses self-lockout.
- **Subscriptions.** Access = any ACTIVE subscription with `start_date ≤ now < end_date` whose plan covers the course. PENDING, FAILED, EXPIRED and CANCELLED never grant access. A user cancellation runs to `end_date`; an immediate cancellation or full refund ends only that subscription. One user's subscriptions never affect another (per-user keys, tested).
- **Quiz answers.** Course and quiz-detail payloads carry no questions or options. Start payloads omit `is_correct` and explanations. The review appears only after grading. Attempts are owner-only.
- **Cloudflare playback.** Tokens are issued only after the entitlement check, only for READY videos that Cloudflare has *confirmed* signed-only, and expire no later than the access behind them (the longest covering subscription when several overlap). Limitation: a token is a stateless RS256 JWT; Cloudflare cannot revoke it early, and whether in-progress playback re-checks `exp` on every segment is not verified. Videos registered before this release are marked signed-only without confirmation; sync each once after deploy (F.5).
- **Redis failure policy.**

  | Use | Kind | When Redis is down |
  |---|---|---|
  | Entitlement cache + generation counters | optimization | skipped; decided from the database; never grants on error; invalidation never raises (staleness ≤ 60s TTL) |
  | Leaderboard top-N cache | optimization | skipped |
  | Throttle `auth` (login, register, verify, password reset) | brute-force control | **fails closed**: 503 `service_unavailable` |
  | Throttles `token_refresh`, `payment`, `webhook`, `playback`, `progress` | flood control | fail open (tokens signed, blacklist in the database, signatures and entitlement still checked) |
  | Playback/progress per-user limiter | anti-harvesting | fails open; entitlement still enforced |
  | Refresh-token blacklist | revocation | database-backed: unaffected (tested) |
  | Celery broker | queueing | notification sends fall back to inline delivery (existing behavior) |

  Sockets time out after 1s. Failures are logged at most once a minute per process, error type only.
- **Remaining risks.** Section G.

## F. Deployment checklist

### 1. Implemented in code (this branch)
Everything in section B marked Fixed.

### 2. Local configuration
None needed. Development keeps local media and console email, with no warnings.

### 3. Railway (manual; requires approval)

`railway.json` (Config as Code) is deprecated by Railway and stops being honored on 2026-12-01, so the settings below are given for the dashboard. A `.railway/railway.ts` (IaC) file was drafted but **not committed**: `railway config plan` could not run (SDK/CLI version check), and an unvalidated IaC file could plan the removal of the existing Postgres and Redis.

Backend service `lawschool-backend` (Dockerfile build):

| Setting | Value |
|---|---|
| Pre-deploy command | `python manage.py migrate --noinput` (runs once per deploy, not per worker; also prints the W001–W003 warnings) |
| Healthcheck path | `/health/ready/` |
| Variables to add | `CLOUDFLARE_STREAM_KEY_ID` (**blocker**), email provider (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`), bucket (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) |
| Variables to check | `CELERY_TASK_ALWAYS_EAGER` = `False` once the worker exists; `CACHE_BACKEND` unset (defaults to `redis`); `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` include the Vercel domain; `FRONTEND_URL` is the Vercel URL |

New services (same repository and Dockerfile, same variables as the backend):

| Service | Start command | Replicas |
|---|---|---|
| `celery-worker` | `celery -A config worker -l info --concurrency 2` | 1+ |
| `celery-beat` | `celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` | **exactly 1** (a second Beat duplicates every periodic job) |

Object storage: a Railway Bucket (or R2/S3). Railway Buckets are S3-compatible and billed by usage, so **approval needed**.

Read-only check of the production schema before the first deploy:
`railway run --service lawschool-backend python manage.py showmigrations --plan`

Migration notes: all 20 migrations apply cleanly on a fresh PostgreSQL 16 (production runs 18). `quizzes.0005` drops the old question→quiz link after `0004` backfills subjects. They are correctly ordered, but `0004`'s reverse is a no-op, so rolling back past `0005` cannot restore that link. Take a database backup before the first migrate.

### 4. Vercel (manual)
Redeploy the frontend (`vercel --prod` from `frontend/`) so it picks up `vercel.json` and the frontend fixes. The live build dates from 2026-10-03 and predates `2f1e7b3`.

### 5. Cloudflare (manual)
1. Create a Stream signing key: `POST /accounts/<account_id>/stream/keys`. Set `CLOUDFLARE_STREAM_KEY_ID` to the returned `id` and `CLOUDFLARE_STREAM_SIGNING_KEY` to the returned base64 `pem` (if the current signing key belongs to a different key id, replace both together).
2. After deploy, run admin `POST /api/v1/videos/<uid>/sync/` once per existing video, so `requireSignedURLs` is confirmed against Cloudflare.

### 6. Email provider (manual)
Choose a provider and set the SMTP variables. Smoke test with an inbox you control: request a password reset for a test account and confirm one email with a working `/reset-password` link arrives. Register a test account and confirm the verification email. Check the deploy log shows no `lawschool.W001`/`W002`.

### 7. Operational verification after deploy
- `GET /health/` → 200; `GET /health/ready/` → 200 `{"database": "ok", "cache": "ok"}`.
- Frontend: open `/forgot-password` and `/courses/<slug>` directly (not via navigation) → app pages, not 404.
- Sign in; open a course; play a lesson (token issued); start, submit and review a quiz.
- Admin: Subscriptions table lists rows; dashboard count is non-zero.
- Upload an avatar; redeploy; confirm it still loads. Confirm the object URL without its signature is refused (bucket private).
- Worker and Beat logs show the periodic tasks running.

## G. Remaining issues

| Severity | Issue | Impact | Why unresolved | Next action | Needs |
|---|---|---|---|---|---|
| Critical | `CLOUDFLARE_STREAM_KEY_ID` missing on Railway | Backend cannot start | Production config change | F.5 step 1, then deploy | Approval + Cloudflare access |
| Critical | Migrations not wired into deploys | Schema may be behind the code | Railway setting | F.3 pre-deploy command | Approval |
| High | No email provider | Password reset and verification undeliverable | Provider choice and credentials | F.6 | Approval + credentials |
| High | No Celery worker/Beat | Videos never become READY automatically; payments not reconciled; no expiry notices | New Railway services | F.3 | Approval (cost) |
| High | No object storage | Uploads lost and not served | Provider choice and cost | F.3 bucket + variables | Approval (cost) |
| High | Frontend not redeployed | Live site lacks every frontend fix | No deploys allowed | F.4 | Approval |
| Medium | Tokens in localStorage | XSS could read tokens | Separate architecture project | Branch `security/move-auth-tokens-to-http-only-cookies` | Planning |
| Medium | No error monitoring | Failures invisible | Provider choice (`sentry-sdk` now installed in the image, not configured) | Configure a DSN or log alerts | Approval |
| Medium | Backups unverified | Data-loss risk on a destructive migration | No access to backup evidence | Take and restore-test a backup before the first migrate | Railway access |
| Low | Playback tokens not revocable before `exp` | ≤ token TTL of continued playback after revocation | Cloudflare token semantics | Lower `CLOUDFLARE_PLAYBACK_TOKEN_TTL` if needed | — |
| Low | "My subscription" and cancel act on the latest-ending row only | UI shows one of several active subscriptions | Presentation only; access is correct | Show all active subscriptions | — |
| Low | Instructors routed into admin-only pages (403s) | Confusing UI | Out of scope | Restrict those routes to admins | — |
| Low | 4 `freezegun` cache tests cannot run against real Redis | CI uses the in-memory cache, so it is unaffected | Test design | Optional: Redis-backed CI job with time-independent tests | — |
| Info | Production runs PostgreSQL 18; CI tests 16 | Version drift | CI configuration | Add PG 18 to CI | — |
| Info | No linter configured; Python CVE scan not run | Unknown | Tooling not installed | Add ruff and pip-audit to CI | — |

## H. Final readiness verdict

**READY FOR PUSH**

The code is tested on SQLite, PostgreSQL 16 and real Redis, the frontend builds, and the history holds no secrets. It is not ready for production until the manual steps in section F (the Cloudflare key, pre-deploy migrations, email, worker and Beat, object storage, frontend redeploy) are approved and completed and the post-deploy checks pass.
