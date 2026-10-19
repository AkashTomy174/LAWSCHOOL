# WhatsApp notifications and assistant

WhatsApp is an optional delivery channel on top of the existing notification
system. It is **off by default** (`WHATSAPP_ENABLED=false`); with it off, no code
path sends, queues or stores anything WhatsApp-related and the LMS behaves exactly
as before.

## Architecture

```
LMS event (class saved, payment captured, quiz graded, beat job)
  -> whatsapp.service.enqueue()      consent + category + template + variable checks,
                                     one Notification row, UNIQUE idempotency_key
  -> transaction.on_commit -> Celery send_whatsapp_notification
  -> service.deliver()               atomic claim (pending->processing), re-check consent
                                     and staleness, rate limit, then ONE HTTP call
  -> whatsapp.client.send_template() the only module that talks to Meta
  -> Notification(accepted, provider_message_id)
  -> Meta status webhook -> service.apply_status_event()   sent / delivered / read / failed

Student WhatsApp message
  -> POST /api/v1/notifications/whatsapp/webhook/   X-Hub-Signature-256 over the raw body
  -> IncomingWhatsAppMessage (unique provider id = dedupe) -> Celery -> commands.py
  -> reply via client.send_text()
```

Reused, not duplicated: the existing `Notification` table (new `whatsapp` channel +
delivery columns), `notify_user()` (optional `whatsapp_key`), `can_user_access_course`
/ `accessible_course_ids` for entitlement, `LiveClass`, `QuizAttempt`,
`VideoProgress`, Celery + Beat + Redis, DRF throttling, `IsAdminRole`.

| Module (`backend/apps/notifications/`) | Role |
| --- | --- |
| `whatsapp/client.py` | Meta Cloud API client, error classification, redaction, phone normalisation |
| `whatsapp/templates.py` | closed registry of 18 templates, variable validation, seeding |
| `whatsapp/service.py` | enqueue, deliver, retry, status events, stuck-row release |
| `whatsapp/consent.py` | number linking, OTP, opt-in/out, preferences |
| `whatsapp/events.py` | producers: live-class fan-out, reminders, weekly summary, inactivity, announcements |
| `whatsapp/recipients.py` | bulk recipient SQL (entitlement + consent), chunked iteration |
| `whatsapp/signals.py` | LiveClass save/delete -> fan-out tasks |
| `whatsapp/webhook.py` | handshake, signature check, payload ingestion |
| `whatsapp/commands.py` | inbound assistant |
| `views_whatsapp.py`, `urls.py` | student, webhook and admin endpoints |
| `tasks.py` | Celery tasks |

## What is implemented

**Notifications** (all gated by consent + category switch + template approval):
class scheduled, reminders (default 24 h and 30 min; admin-configurable offsets,
`0` = at start), rescheduled, cancelled (unpublish or delete), link updated,
quiz result, payment success, payment failure, subscription expiry reminder and
expired, weekly progress summary (skipped when there is nothing to report),
inactivity reminder (threshold, cooldown and max count configurable), admin
announcements (preview + confirmed count + cap).

**Assistant commands** (exact match only, no free-text lookup, no AI):
`HELP`, `NEXT CLASS`, `MY COURSES`, `MY PROGRESS`, `MY QUIZZES`, `MY ASSIGNMENTS`
(replies that assignments do not exist yet), `PAYMENT STATUS`, `CONTACT SUPPORT`,
`STOP`. Only `STOP` changes state, and it runs synchronously in the webhook.

**Endpoints** (under `/api/v1/notifications/`):

| Method + path | Who |
| --- | --- |
| `GET/PATCH whatsapp/preferences/` | the signed-in user, own settings only |
| `POST whatsapp/link/` `{phone, consent}` | user; throttled 5/hour; sends an OTP template |
| `POST whatsapp/verify/` `{code}` | user; throttled 20/hour; 5 attempts per code, 10 min expiry |
| `POST whatsapp/opt-out/` | user |
| `GET whatsapp/history/` | user, own rows, no message content |
| `GET/POST whatsapp/webhook/` | Meta (verify token / HMAC signature, not JWT) |
| `GET admin/overview/`, `admin/history/`, `admin/failed/` | admin |
| `POST admin/<uuid>/retry/` | admin; only `failed` rows, same row/key |
| `GET admin/templates/`, `PATCH admin/templates/<id>/` | admin; records approval state |
| `GET/PATCH admin/settings/` | admin; validated |
| `GET admin/announcements/preview/`, `POST admin/announcements/` | admin only |

**Celery tasks / Beat** (`CELERY_BEAT_SCHEDULE`): `dispatch_class_reminders` (5 min),
`sweep_pending_whatsapp` (5 min; the outbox sweeper), `send_weekly_summaries` (Mon
09:00 IST), `send_inactivity_reminders` (daily 11:00 IST), `cleanup_whatsapp_records`
(daily 03:30 IST). All no-op while the flag is off.

**Frontend:** `/settings/whatsapp` (any signed-in user; linked from Profile) and
`/admin/notifications` (admin only).

## Reliability model

* **Idempotency:** `Notification.idempotency_key` is UNIQUE. Keys come from the
  business event (payment id, quiz attempt id, class id + start time + user, ISO
  week...), so duplicate webhooks, retried tasks and concurrent workers cannot
  create a second row.
* **Single sender:** a conditional `UPDATE ... WHERE status IN (pending, scheduled)`
  claims the row; the loser gets `skipped`. No transaction or lock is held across
  the HTTP call.
* **Lost enqueue:** the row is written in the business transaction; the task is
  queued `on_commit`. If the broker is down the 5-minute sweeper re-dispatches
  open rows. (This is a small outbox; no separate outbox table was needed.)
* **Retries:** only errors where Meta definitely did not accept the message are
  retried (429/rate limit, 5xx, connect failures) with exponential backoff + jitter,
  up to `WHATSAPP_MAX_ATTEMPTS`. Permanent errors (invalid recipient, template
  problem, auth) fail immediately with the provider code stored.
* **Residual duplicate risk (documented, not solved):** Meta's send API has no
  idempotency key. After a *read timeout* or a 2xx without a message id we cannot
  know whether Meta accepted the message. By default such rows are marked
  `failed` (`timeout` / `malformed_response`) and **not** resent
  (`WHATSAPP_RETRY_AMBIGUOUS=false`); an admin may retry them knowingly. A worker
  that dies mid-send leaves a `processing` row that the sweeper fails after 10 min
  (`stuck_processing`) rather than resending. Enabling `WHATSAPP_RETRY_AMBIGUOUS`
  trades possible duplicates for fewer lost messages.
* **Status webhooks:** `accepted < sent < delivered < read`, applied with a
  conditional update so late or duplicate events never move a row backwards; a
  `failed` event cannot undo `delivered`. If Meta's status arrives before the
  worker saved `provider_message_id` (very rare) the event is dropped and the row
  stays `accepted`.
* **Stale reminders:** reminder keys include the class start time, the sweeper
  reads current data, reschedule/cancel bulk-cancels open reminders, and
  `deliver()` re-checks the class (published, same start time, not started) just
  before sending.
* **Payments:** the WhatsApp leg runs inside `notify_user()` wrapped in
  try/except and queues work `on_commit`; a WhatsApp failure cannot affect a
  payment, entitlement or quiz grade.

## Privacy and security

* A typed phone number is never consent. Linking = explicit consent checkbox + OTP
  sent *to that WhatsApp number* (HMAC-hashed at rest, 10 min, 5 attempts,
  60 s resend cooldown, hourly throttle). `consent_status`, number, and verification
  are read-only through the API; the Django admin shows preferences read-only.
* A verified number is UNIQUE to one account (partial unique constraint). Linking a
  number owned by someone else returns the same response but sends nothing, so
  accounts cannot be enumerated and numbers cannot be hijacked.
* Inbound: sender -> account only via a verified number of an active account.
  Unknown senders get one link instruction per hour and no data. Message text is
  not stored (only the recognised command), and handlers query only the resolved
  user's rows. Instructors/admins get no student-data commands.
* Webhook: HMAC-SHA256 over the exact raw body, constant-time compare, 512 KB cap,
  throttled, malformed payloads rejected with 400, nothing logged beyond ids.
* Logs and DB errors pass through `client.redact()` (access token, bearer strings,
  phone numbers). The admin API returns masked numbers only. The OTP exists only in
  the outbound request and the user's WhatsApp.
* Opt-out (`STOP` or the app) withdraws consent, cancels queued messages and blocks
  all further sends including payment updates (conservative; see below).
* Retention: WhatsApp notification rows 90 days, inbound dedupe rows 30 days, OTP
  rows 1 day, audit rows 1 year (`WHATSAPP_RETENTION_DAYS`,
  `WHATSAPP_INBOUND_RETENTION_DAYS`).
* Audit trail (`NotificationAuditLog`): link requested/verified, opt-outs,
  preference changes, template/settings changes, retries, announcements.

## Environment variables

See `backend/.env.example`. Required when `WHATSAPP_ENABLED=true` (enforced by the
`lawschool.E004` system check, which fails `manage.py check`/`migrate`):
`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`,
`WHATSAPP_VERIFY_TOKEN`. Also set `WHATSAPP_BUSINESS_ACCOUNT_ID`,
`WHATSAPP_API_VERSION`, `WHATSAPP_DEFAULT_LANGUAGE`.

**Confirm `WHATSAPP_API_VERSION`** against Meta's current Graph API changelog before
go-live; the default (`v21.0`) was chosen without live verification and old versions
are retired on a schedule.

## Meta setup (manual steps, not done by this repo)

1. Create a Meta developer app (type: Business) and a WhatsApp Business Account;
   complete business verification as Meta requires.
2. Add and register a phone number; note its **Phone number ID** and the **WABA ID**.
3. Create a **system user** access token with `whatsapp_business_messaging` and
   `whatsapp_business_management`; store it only in the environment/secret manager.
4. Copy the app's **App Secret** into `WHATSAPP_APP_SECRET`; choose a long random
   `WHATSAPP_VERIFY_TOKEN`.
5. Deploy with the variables set (flag still `false` is fine for this step), then in
   the app dashboard set the callback URL
   `https://<api-host>/api/v1/notifications/whatsapp/webhook/` and the verify token,
   and subscribe to the `messages` field. The GET handshake works while the flag is
   off. HTTPS with a valid certificate is mandatory.
6. Seed templates and print the bodies: `python manage.py seed_whatsapp_templates --show-bodies`.
7. Submit each template in WhatsApp Manager with that exact body and the listed
   variable order, in the language set by `WHATSAPP_DEFAULT_LANGUAGE`.
8. When Meta approves a template, set it to **Approved** in `/admin/notifications` >
   Templates (or Django admin). Only approved templates are ever sent.
9. Only then set `WHATSAPP_ENABLED=true` on the web, worker **and beat** services.

## Templates to submit

Meta category is the intended one; Meta may reclassify any of them. Marketing-style
wording would change pricing, so keep bodies factual.

| Internal name | Category | Variables (in order) |
| --- | --- | --- |
| `live_class_scheduled` | utility | student_name, class_title, course_title, start_time |
| `live_class_reminder` | utility | student_name, class_title, start_time, time_left |
| `live_class_rescheduled` | utility | student_name, class_title, new_start_time |
| `live_class_cancelled` | utility | student_name, class_title, original_start_time |
| `live_class_link_updated` | utility | student_name, class_title, start_time |
| `live_class_recording_available` | utility | student_name, class_title *(no producer yet)* |
| `quiz_result_available` | utility | student_name, quiz_title, score_text |
| `assignment_reminder` | utility | student_name, assignment_title, due_time *(no producer yet)* |
| `weekly_progress_summary` | utility | student_name, lessons_completed, quizzes_attempted |
| `study_inactivity_reminder` | utility | student_name, days |
| `payment_success` | utility | student_name, amount, plan_name |
| `payment_failure` | utility | student_name, plan_name |
| `subscription_expiry_reminder` | utility | student_name, plan_name, end_date |
| `subscription_renewed` | utility | student_name, plan_name, end_date *(mapped; not currently emitted)* |
| `subscription_expired` | utility | student_name, plan_name, end_date |
| `certificate_available` | utility | student_name, course_title *(no producer yet)* |
| `platform_announcement` | utility | student_name, announcement_title, announcement_text |
| `whatsapp_verification_code` | authentication | code (body + URL-button parameter; build it as a Meta *authentication* template) |

Exact body text: `python manage.py seed_whatsapp_templates --show-bodies`.
`study_inactivity_reminder` and `weekly_progress_summary` are the likeliest to be
challenged as non-utility; check Meta's response and adjust.

## Deploy and verify

```bash
# migrate (adds columns/tables to notifications; no data rewrite)
python manage.py migrate
python manage.py check --deploy
python manage.py seed_whatsapp_templates

# processes (already defined in docker-compose*.yml; all need the WHATSAPP_* env):
#   web:    gunicorn ...
#   worker: celery -A config worker -l info
#   beat:   celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler   # exactly ONE
```

Smoke test with an authorised test recipient (add them as a test number in Meta
while the app is in development mode):

1. `GET .../webhook/?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=1` -> `1`.
2. Link the test number at `/settings/whatsapp`; receive and enter the OTP.
3. Mark the needed templates approved; schedule a live class for a course that
   test student can access; confirm `accepted` then `delivered` in the admin log.
4. From the phone send `HELP`, `NEXT CLASS`, then `STOP`; confirm opt-out in
   `/settings/whatsapp`.

Rollback: set `WHATSAPP_ENABLED=false` and redeploy web/worker/beat. Producers and
tasks become no-ops, queued rows stay `pending` (cancel with
`Notification.objects.filter(channel="whatsapp", status="pending").update(status="cancelled")`
if desired). Migrations are additive; there is no need to reverse them.

## Tests

```bash
cd backend && python -m pytest -q                       # sqlite in-memory
cd backend && python -m pytest apps/notifications -q
cd frontend && npx vitest run && npm run build
```

No test makes a network call: an autouse fixture makes any un-mocked Meta request
fail the test.

## Compliance points that need a human decision

* **DPDP Act 2023 / consent record:** confirm the consent wording on
  `/settings/whatsapp`, the privacy-policy text, and that storing number + consent
  timestamp + source meets your notice requirements. Right-to-erasure: deleting a
  user cascades their preference, verification and WhatsApp notification rows.
* **Meta policies:** opt-in must be collected before business-initiated messages
  (done via the explicit checkbox), and the messaging-limit/quality tiers apply.
  Confirm your business category and that the inactivity/weekly templates are
  acceptable as utility.
* **Opt-out scope:** `STOP` stops *all* WhatsApp messages, including payment
  receipts, which still go by email/in-app. Revisit if you want payment messages to
  survive an opt-out.
* **Free-form replies** are only sent in response to a user message (inside the
  24-hour window); business-initiated messages are always templates.

## Not done / deferred

* Live-class **recording published**, **assignments**, **exam schedules**,
  **certificates**, **course-completion and milestone** notifications, **refund**
  notifications: the LMS has no model or event for these, so no producer exists
  (templates are defined where named in the brief). Do not enable the templates in
  Meta until a producer is added.
* **AI learning assistant:** no AI/RAG infrastructure exists in the repo; deferred.
  When added it must be a separate, opt-in, rate-limited feature grounded in
  entitled course material.
* **Template approval sync** from Meta's Management API: approval is entered by an
  admin by hand.
* **Cost:** only a configurable planning figure (`WHATSAPP_ESTIMATED_COST_PER_MESSAGE`,
  INR per accepted message). No Meta prices are hard-coded; the estimate is shown as
  an estimate, never as billing.
* Per-minute send limiting uses the Django cache; if the cache is down it fails
  open and relies on Meta's own limits. Rate-limited sends retry individually with
  jitter, which is fine for hundreds of messages per minute but is not a work queue
  for very large bursts.
* Bulk inactivity query joins progress and quiz tables per student; fine for
  thousands, revisit with a materialised "last active" column beyond that.
