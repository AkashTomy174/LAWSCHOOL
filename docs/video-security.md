# Video Security

Protected video delivery via Cloudflare Stream. The design goal:

> A student can watch only the lessons their subscription currently entitles them
> to, and no permanent unrestricted URL to any protected asset exists anywhere in
> the system.

## 1. Division of responsibility

| Concern                               | Owner                          |
| ------------------------------------- | ------------------------------ |
| Encoding, storage, worldwide delivery | Cloudflare Stream              |
| Who may watch what, right now         | **Django**                     |
| Minting short-lived playback tokens   | Django (holds the signing key) |
| Deciding whether a token is valid     | Cloudflare                     |

Django is the authorization layer. Cloudflare is a delivery layer that refuses to
serve an asset without a valid, unexpired, correctly-signed token. Neither alone is
sufficient; together, revoking access in Django takes effect within the token TTL.

## 2. Configuration

```env
CLOUDFLARE_ACCOUNT_ID=xxxxxxxx
CLOUDFLARE_API_TOKEN=xxxxxxxx        # "Stream: Edit" permission
CLOUDFLARE_STREAM_SIGNING_KEY=<key_id>:<secret>
CLOUDFLARE_STREAM_CUSTOMER_CODE=xxxx # "customer-<code>" subdomain
CLOUDFLARE_PLAYBACK_TOKEN_TTL=300    # seconds
```

Setup:

1. Cloudflare dashboard → **Stream** → copy the **Account ID**.
2. **My Profile → API Tokens → Create Token** with _Stream: Edit_ → the API token.
3. **Stream → Settings → Signing Keys → Create** → copy as `<key_id>:<secret>`.
4. Copy the customer subdomain code from any playback URL.
5. Mark each asset `require_signed_urls = true`. The registration endpoint does
   this automatically; a reconciliation task retries if the call fails.

`config/settings/production.py` refuses to boot without all of these. The signing
key and API token are never sent to the browser.

## 3. Why bytes never touch Django

Video is uploaded **directly from the instructor's browser to Cloudflare** using a
direct creator upload:

```
Instructor ──POST /api/v1/videos/upload-url/──▶ Django
                                                  │  requests an upload URL
                                                  ▼
                                            Cloudflare Stream
Instructor ──PUT video bytes────────────────────▶ Cloudflare Stream
                                                  │
                                                  ▼
                                            Cloudflare encodes
                                                  │
Django ◀──video.processed webhook ────────────────┘
   └─ Video.status = READY
```

Django stores only the resulting `cloudflare_video_id`. Consequences:

- No large files in PostgreSQL or in Django's `MEDIA_ROOT`.
- No upload bandwidth or transcoding CPU on the application servers.
- Application instances stay stateless and disposable, which is what makes
  horizontal scaling a matter of starting more workers.

## 4. Playback flow

```
Student
  │
  ▼
GET /api/v1/videos/{playback_uid}/playback/
  │
  ├─ 1. JWT authentication        → 401 if anonymous
  ├─ 2. can_user_access_video()   → 403 if not entitled  ← the decision
  ├─ 3. video.status == READY?    → 409 if still encoding
  ├─ 4. rate limit (30 / 10 min)  → 429 if scripted harvesting
  ├─ 5. mint signed token (HS256, TTL 300s, downloadable=false)
  ├─ 6. record PlaybackSession (token fingerprint only)
  ▼
200 { hls_url, dash_url, token, token_expires_at, expires_in, thumbnail_url }
  │
  ▼
Cloudflare Stream player verifies the signature and serves the stream
```

The player also uses `GET /api/v1/lessons/{id}/watch/`, which performs the identical
check and returns lesson metadata plus playback info in one round trip. Both entry
points funnel through `issue_playback_token()`, which is the _only_ way playback
credentials leave the system.

### The signed token

```python
header  = {"alg": "HS256", "typ": "JWT", "kid": key_id}
payload = {
    "sub": video_uid,
    "kid": key_id,
    "exp": expires_at,
    "nbf": now - 30s,      # small clock-skew allowance
    "iat": now,
    "downloadable": False,  # least privilege
}
```

Implemented with the standard library (`hmac` + `hashlib`) rather than a JWT
package: the algorithm is fixed by Cloudflare, so there is no benefit to a
dependency to keep patched in the signing path, and fewer moving parts on the one
code path that guards the product's core asset.

## 5. Threat model

| Threat                                            | Defence                                                                                                                                                                                                          |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unauthenticated playback**                      | JWT required; anonymous requests get `401` and no token. Tested.                                                                                                                                                 |
| **Expired subscription keeps playing**            | Entitlement is re-evaluated on every token request; the date window is checked in SQL, so a stale `status` column cannot extend access. Tokens are short-lived, so an already-issued token dies quickly. Tested. |
| **Watching another student's course**             | Entitlement is per user _and_ per plan coverage — "some student is paying" is not enough. Tested.                                                                                                                |
| **Direct access to an unrestricted URL**          | No such URL exists. The HLS/DASH URLs embed the signed token and are inert without it; `require_signed_urls` is set on every protected asset.                                                                    |
| **Sharing a playback URL**                        | The token is bound to the asset (`sub`) and expires in 300s. This is _not_ DRM — a determined user can re-share within the window. See the note below.                                                           |
| **Harvesting tokens by script**                   | Fixed-window rate limit per user: 30 token requests / 10 min. Exceeding it logs a warning and returns `429`.                                                                                                     |
| **Downloading the asset**                         | `downloadable: false` in the token payload.                                                                                                                                                                      |
| **Learning the Cloudflare asset id**              | The API exposes `playback_uid` (an internal UUID); `cloudflare_video_id` never appears in a student-facing response. Tested against the raw response body.                                                       |
| **Replaying a token from a DB dump**              | Only a SHA-256 fingerprint of the token is stored, never the token.                                                                                                                                              |
| **Learning the signing key**                      | The key is server-side only; the playback response is asserted not to contain it, and `production.py` fails to boot without it. Tested.                                                                          |
| **Server misconfiguration leaking a stack trace** | A missing or malformed signing key returns a clean `503 playback_unavailable`, with full detail logged server-side only. Three regression tests.                                                                 |

### What this is not

This is **not a DRM system**, and it should not be described as one. It prevents
unauthenticated access, expired-subscription access and cross-course access, and it
makes bulk downloading inconvenient. It does not prevent a subscriber from
screen-recording, nor from sharing a token that is valid for another 300 seconds.
Real DRM (hardware-backed key exchange, output protection) is a different product
with different costs, and Cloudflare Stream does not offer it. The honest
description of what is implemented here is **short-lived signed playback with
server-side authorization**.

## 6. Rate limiting

Two fixed-window limiters, both per user, and both logged when exceeded:

| Scope      | Budget | Window | Purpose                                                                               |
| ---------- | ------ | ------ | ------------------------------------------------------------------------------------- |
| `playback` | 30     | 10 min | a real player refreshes every few minutes; 30 is generous, scripted harvesting is not |
| `progress` | 120    | 10 min | absorbs a 10–30s heartbeat with headroom                                              |

A fixed window was chosen over a sliding window deliberately: token requests are
cheap, and the objective is to stop scripted harvesting, not to shape traffic
precisely. DRF's `ScopedRateThrottle` provides an additional coarse layer
(`playback` 120/min) in front of the view.

## 7. Progress tracking

The player sends progress every 10–30 seconds — never every second — plus once on
video end and once on page unload.

```json
POST /api/v1/videos/{uid}/progress/
{ "position_seconds": 420, "watched_seconds": 400, "completed": false }
```

### Server-side validation (anti-cheat)

```
duration = video.duration_seconds
ceiling  = duration + 5                     # player rounding slack

position = clamp(position_seconds, 0, ceiling)
```

1. **Cannot exceed the asset.** A value beyond the real duration (+5s) is clamped.
2. **Cannot jump.** A single update may not advance more than
   `VIDEO_PROGRESS_MAX_DRIFT_SECONDS` (default 30s) past the stored position. A
   script posting `{"position_seconds": 99999}` lands at the stored position and is
   logged as a suspicious jump.
   The **first** update is exempt (`update_count == 0 and last_position == 0`),
   because resuming mid-video and seeking in the player are both legitimate.
3. **Monotonic.** `last_position = max(last_position, position)`; progress never
   goes backwards.
4. **`completed` is not trusted on its own.** Completion requires either an explicit
   end-of-video signal _and_ ≥95%, or ≥98% from actual playback. A flag that
   contradicts the percentage is ignored.
5. **Upsert, never duplicate.** The `unique_progress_per_user_video` constraint plus
   a `select_for_update` read means repeated updates cannot create duplicate rows.
6. **Entitlement required.** Progress cannot be submitted for a video the user may
   not watch.

## 8. Video lifecycle

```
pending ──▶ processing ──▶ ready
                     └──▶ failed (processing_error recorded)
```

State arrives two ways:

1. **`video.processed` webhook** — the primary signal, immediate.
2. **`sync_pending_videos` Celery task** — every 10 minutes, polls Cloudflare for
   anything stuck in `pending`/`processing`.

The safety net exists because a dropped webhook would otherwise leave a lesson
permanently unplayable. `POST /api/v1/videos/{uid}/sync/` lets an instructor force
a refresh while editing.

Playback while `status != ready` returns `409 video_not_ready` — a clear "try again
shortly" rather than an empty player.

## 9. Testing

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest apps/videos -v
```

`config/settings/test.py` sets a well-formed fake signing key
(`"test-key-id:test-signing-secret"`) so the real HMAC path is exercised rather
than short-circuited. Cloudflare's HTTP API is never called.

Covered: anonymous playback denied · subscribed student receives a valid token ·
no subscription denied · **expired subscription denied** · cancelled subscription
denied · another student's course denied · a plan that excludes the course denied ·
preview lessons open to authenticated users · not-ready returns 409 · Cloudflare id
never leaked · signing key never leaked · missing/malformed signing key returns 503 ·
tokens are valid HS256 JWTs · token expiry is correct · sessions are recorded ·
rate limiting triggers · progress validation rejects impossible values · completion
requires real playback.

## 10. Operational notes

- **Rotating the signing key**: update `CLOUDFLARE_STREAM_SIGNING_KEY` and restart.
  In-flight tokens stay valid until their own expiry (≤300s). During the changeover
  requests return `503` rather than `500`, so clients retry cleanly and users see
  nothing alarming.
- **Monitoring**: watch for `503 playback_unavailable` (configuration), `429
rate_limited` (abuse or a misbehaving client), and `Suspicious progress jump
rejected` (cheating attempts).
- **`PlaybackSession` growth**: one row per issued token. Partition or prune by
  `created_at` once volume justifies it; the table is append-only and indexed by
  `(user, created_at)` and `(video, created_at)` for that purpose.
- **Never log the token itself.** Only `token_fingerprint` is persisted or logged.
