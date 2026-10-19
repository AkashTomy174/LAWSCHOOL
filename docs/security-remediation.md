# Security remediation notes

Companion to the audit remediation. Records decisions, assumptions and what is
**not** fixed.

## Decisions

| Area | Decision |
| --- | --- |
| Payment states | `REFUNDED` is terminal. `CREATED`, `AUTHORIZED`, `FAILED` may settle (a customer can retry inside one Razorpay order). Checked under the row lock in `_settle_payment`, before the signature check in `verify_payment`. |
| Failed verification | Never creates `Subscription` rows. The audit trail is the `Payment` row (`status`, `failure_reason`). "Renew" vs "Buy" now counts only ACTIVE/EXPIRED/CANCELLED subscriptions. |
| Webhook identity | Razorpay signs the body only; `X-Razorpay-Event-Id` is unsigned. Event id = `sha256:<hash of signed body>`, so a replay with a fresh header is a duplicate (DB unique constraint). Signed `created_at` older than `PAYMENT_WEBHOOK_MAX_AGE_SECONDS` (3 days; Razorpay retries ~24h) is acknowledged and ignored; malformed or future (> `PAYMENT_WEBHOOK_TOLERANCE_SECONDS`) timestamps are rejected with 400. A 5-minute window was deliberately **not** used: it would drop legitimate retries. |
| WhatsApp webhook | Already idempotent: statuses are applied by provider id, inbound messages dedupe on `provider_message_id` (unique). A replayed signed body creates nothing new. |
| Lessons | `is_preview` (free access) is administrator-only. Instructors keep publish/unpublish of their own lessons (existing UI workflow); the course itself is still published only by an administrator. |
| Quiz submit | Start-time gates (published, window, rules, attempt limit) are not re-applied at submit. Entitlement and the time limit still are. Questions and marks are frozen on `AttemptQuestion`. |
| Registration | Always `202` with one neutral body and no tokens. Existing address gets a password-reset email. The SPA signs in with the entered credentials afterwards. |
| Reset links | 1 hour (`PASSWORD_RESET_LINK_SECONDS`), single use. Verification links keep Django's 3-day default. |
| Last admin | Enforced in `User.save()/delete()` under a row lock, so API, Django admin and shell share it. `QuerySet.update()` bypasses model code by Django design. |
| Admin login | `AdminLoginThrottleMiddleware`: 5 failures/IP and 10/username per 15 min, temporary, fail-closed if the cache is down. |

## Operational changes to apply on deploy

* `SECRET_KEY` (and `JWT_SECRET` if set) must be >= 32 characters and not look like a
  placeholder, or production **refuses to start**. A blank `JWT_SECRET` line must be
  removed or filled.
* Run `python manage.py migrate` (adds `quizzes.0006`).
* New optional settings: `PASSWORD_RESET_LINK_SECONDS`, `PAYMENT_WEBHOOK_MAX_AGE_SECONDS`,
  `WHATSAPP_OTP_DAILY_CAP`, `ADMIN_LOGIN_*`, `VIDEO_MAX_DURATION_SECONDS`.
* Requires `Django==6.0.9`, `PyJWT>=2.15`; reinstall requirements.
* Vercel: `vercel.json` now sets the CSP. `connect-src` allows `https://*.up.railway.app`
  for the API; **add your API origin if it is a custom domain**.
* Existing bank questions have `created_by = NULL`, so only administrators can edit them.
* Existing JWTs keep their old `email`/`name` claims until the user signs in again
  (refresh rotation copies claims forward).

## Not fixed / residual risk

* **Tokens are still in `localStorage`.** CSP reduces the chance and impact of XSS but any
  script on the origin can read them. Real fix: HttpOnly `Secure` `SameSite` cookies +
  CSRF handling, a separate migration.
* **Registration is not fully non-enumerating.** The follow-up sign-in differs for a new
  vs existing address. Closing it needs "no login until email verified".
* **Concurrency was tested on SQLite / thread-level only.** `select_for_update` is a no-op
  on SQLite; the lock behaviour (payments, last-admin) must be exercised on PostgreSQL.
* A refund event that arrives *before* the payment is captured locally cannot be matched
  (no `provider_payment_id` yet) and is dropped; reconciliation does not cover refunds.
* Celery task arguments are trusted (`send_announcement`, `fan_out_live_class_event`):
  keep the broker private and authenticated.
* CSP and security headers were verified from configuration only, not on a deployed Vercel
  URL. Real-browser HLS playback was not tested.
* The password-reset URL is stored in `Notification.context`; it now expires in 1 hour.
* Legacy static site: not referenced by any deploy config, no network calls, `innerHTML`
  fed from in-repo data files. Left unchanged.
* Dev-only `source-map-js` advisory in the frontend toolchain (`npm audit`); not shipped.
