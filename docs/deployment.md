# Deployment

Production deployment guide for LawSchool.

## 1. Target topology

```
                    Internet
                       │
                       ▼
                Cloudflare / CDN
                 │            │
        HTML/JS/CSS            video segments (signed)
                 ▼            ▼
          Nginx / Load Balancer          Cloudflare Stream
                 │
        ┌────────┴────────┐
        ▼                 ▼
   React SPA         Django API (Gunicorn)
   (static)               │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        PostgreSQL     Redis      Celery worker + beat
                                             │
                                             ▼
                                      Background jobs
```

The Django application is **stateless**: no session affinity, no in-process state,
no local file writes (media goes to object storage in production). This is what
makes horizontal scaling a matter of starting more replicas.

## 2. Build

### Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/production.txt

export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy          # must report zero issues

gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --threads 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
```

Worker count: start at `(2 × CPU cores) + 1` and tune against real traffic.
`config.settings.production` will **refuse to start** if any required secret is
missing — a failed boot is far better than silently running with a development
default.

### Worker sizing

Playback token minting is HMAC and sub-millisecond, so the API is not
CPU-bound; it is bound by database round trips. More workers help until the
connection pool saturates, at which point add a PgBouncer or scale the database.

### Frontend

```bash
npm ci
npm run build        # → dist/
```

Serve `dist/` as static files from Nginx or an object store behind Cloudflare. The
SPA needs a history-mode fallback (`try_files $uri /index.html`) so client-side
routes resolve on a hard refresh.

### Celery

```bash
celery -A config worker -l info --concurrency 4
celery -A config beat   -l info
```

Only **one** beat instance may run — it is a scheduler, and duplicates cause
duplicate periodic jobs. Workers scale horizontally without limit.

## 3. Environment

`config/settings/production.py` requires:

```env
SECRET_KEY=<64+ random chars>
DEBUG=False
DATABASE_URL=postgres://user:pass@host:5432/lawschool
REDIS_URL=redis://host:6379/0
CORS_ALLOWED_ORIGINS=https://app.example.com
ALLOWED_HOSTS=api.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com

RAZORPAY_KEY_ID=rzp_live_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx

CLOUDFLARE_ACCOUNT_ID=xxx
CLOUDFLARE_API_TOKEN=xxx
CLOUDFLARE_STREAM_SIGNING_KEY=key_id:secret
CLOUDFLARE_STREAM_CUSTOMER_CODE=xxx
```

Generate the secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

`JWT_SECRET` is separate from `SECRET_KEY` by default, so rotating the Django secret
does not silently invalidate every active session.

**Never commit `.env`.** `.gitignore` blocks it, but also confirm with
`git ls-files | grep -i env` — it should show only `.env.example`.

### Secret management

Store production secrets in a managed secret store (AWS Secrets Manager, GCP Secret
Manager, Vault, or the platform's encrypted environment configuration) and inject
them at runtime. Do not bake them into an image: image layers are readable by
anyone with registry access, and rotation would require a rebuild.

Rotate on schedule and immediately on suspicion:

| Secret                          | Impact of rotation                                           |
| ------------------------------- | ------------------------------------------------------------ |
| `SECRET_KEY`                    | invalidates sessions/signed values                           |
| `JWT_SECRET`                    | logs every user out                                          |
| `RAZORPAY_KEY_SECRET`           | requires a matching dashboard key update                     |
| `RAZORPAY_WEBHOOK_SECRET`       | webhooks fail until the dashboard matches — do both together |
| `CLOUDFLARE_STREAM_SIGNING_KEY` | new tokens use the new key; old ones expire within 300s      |

## 4. Nginx

```nginx
upstream lawschool_api {
    server 127.0.0.1:8000;
    keepalive 32;
}

limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=webhook:10m rate=5r/s;

server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/ssl/certs/example.pem;
    ssl_certificate_key /etc/ssl/private/example.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options    "nosniff" always;
    add_header X-Frame-Options           "DENY" always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;

    client_max_body_size 10m;      # thumbnails only; videos go to Cloudflare

    # Hashed assets are immutable.
    location /assets/ {
        root /var/www/lawschool;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API
    location /api/ {
        limit_req zone=api burst=40 nodelay;
        proxy_pass http://lawschool_api;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Webhooks get their own bucket: Razorpay must not be rate-limited with users.
    location = /api/v1/payments/webhook/ {
        limit_req zone=webhook burst=10 nodelay;
        proxy_pass http://lawschool_api;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        proxy_pass http://lawschool_api;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA history fallback
    location / {
        root /var/www/lawschool;
        try_files $uri $uri/ /index.html;
    }
}
```

`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` is already set in
production settings, so Django correctly detects HTTPS behind the proxy. The
`X-Forwarded-Proto` header above is therefore required, not optional.

## 5. Docker

`docker-compose.yml` defines `postgres`, `redis`, `backend`, `celery`,
`celery-beat` and `frontend`.

```bash
docker compose up --build -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py createsuperuser
docker compose logs -f backend celery
```

For production, set `DEBUG=False`, point `DATABASE_URL`/`REDIS_URL` at managed
services, and never publish the database or Redis port publicly.

## 6. Security hardening checklist

### Application

- [ ] `DEBUG=False` (production settings force this)
- [ ] All secrets from environment/secret store, none in code
- [ ] `.env` not tracked; only `.env.example` in git
- [ ] `python manage.py check --deploy` reports zero issues
- [ ] `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` list exact production origins
- [ ] JSON structured logging enabled (`LOG_JSON=True`)

### Transport

- [ ] TLS 1.2+ only, valid certificate, auto-renewal configured
- [ ] HSTS with a long max-age, includeSubDomains, preload
- [ ] `SECURE_SSL_REDIRECT=True` (default)
- [ ] Secure, HttpOnly, SameSite cookies
- [ ] `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`

### Access

- [ ] Entitlement enforced server-side on every content endpoint (tested)
- [ ] Admin surface restricted; Django admin not exposed on a guessable path without protection
- [ ] Rate limiting active at both DRF and Nginx layers
- [ ] Webhook endpoint signature-verified (tested)
- [ ] JWT refresh rotation and blacklist enabled
- [ ] No permanent unrestricted video URLs (see [video-security.md](video-security.md))

### Data

- [ ] Database not publicly reachable
- [ ] Automated daily backups, **and a restore actually rehearsed**
- [ ] Redis not publicly reachable; require a password if shared
- [ ] PII minimised; payment details handled entirely by Razorpay (no card data stored)

## 7. Zero-downtime deploy

```
1. Build a new image tagged with the git SHA.
2. Run migrations            ← must be backward compatible
3. Start new containers alongside the old ones.
4. Health-check /health/     → {"status": "ok"}
5. Shift traffic gradually.
6. Stop the old containers.
7. Watch error rates, 5xx, and payment/webhook failures.
```

**Migrations must be backward compatible** so old and new code can run
simultaneously. Expand, then contract:

1. Deploy a migration that _adds_ a nullable column (or a new table).
2. Deploy code that writes both old and new shapes.
3. Backfill.
4. Deploy code that reads only the new shape.
5. Deploy a migration that drops the old column.

Skipping straight to a destructive migration guarantees downtime during the
overlap window.

## 8. Rollback

```bash
# application
docker compose up -d --no-deps --build backend@<previous-sha>

# migration (only if the new migration was reversible and non-destructive)
python manage.py migrate <app> <previous_migration_number>

# frontend
# redeploy the previous dist/ or re-tag the previous image
```

Always know the previous image SHA before deploying, and confirm that the
migration you are about to run has a working reverse operation. For a destructive
migration, rollback means restoring from backup — which is why destructive
migrations should be a separate, deliberate deploy.

## 9. Monitoring

### Health

- `GET /health/` → `{"status": "ok", "service": "lawschool-api"}`
- Probe the **liveness** endpoint above; add a readiness probe that also checks the
  database and Redis.

### Metrics to alert on

| Signal                                        | Why it matters                          |
| --------------------------------------------- | --------------------------------------- |
| 5xx rate                                      | any sustained rise is an incident       |
| `503 playback_unavailable`                    | Cloudflare signing key missing/rotated  |
| `429 rate_limited`                            | abuse, or a client bug hammering tokens |
| `webhook signature verification failed`       | rotated secret, or probing              |
| Payments stuck in `CREATED` > 30 min          | missed webhook / reconciliation failing |
| `reconcile_payments` output `resolved`        | should be near zero in steady state     |
| Celery queue depth and task failures          | background work backing up              |
| DB connections, slow queries, replication lag | capacity                                |
| `Suspicious progress jump rejected`           | cheating attempts                       |
| `Playback denied` volume                      | unusual entitlement probing             |

### Logging

Logs are JSON when `LOG_JSON=True`, with a dedicated `lawschool` logger. Events are
logged with structured `extra` fields (`user_id`, `video_id`, `payment_id`,
`event_id`) rather than interpolated strings, so they are queryable.

**Tokens, passwords and secrets are never logged.** Only `token_fingerprint` is
persisted or emitted.

## 10. Post-deploy verification

```bash
curl -fsS https://api.example.com/health/
curl -fsS -o /dev/null -w '%{http_code}\n' https://api.example.com/api/docs/
```

Then verify by hand:

- [ ] Register and log in (JWT issued)
- [ ] Refresh the token (rotation works, old token rejected)
- [ ] Purchase a plan with a real low-value payment
- [ ] Confirm the subscription activates and the payment appears in history
- [ ] Confirm the webhook was received and processed (admin → webhook events)
- [ ] Play a protected video (signed token issued)
- [ ] Confirm an unsubscribed account cannot play it
- [ ] Submit a quiz and confirm the score is computed server-side
- [ ] Check the leaderboard rank updates
- [ ] Receive a notification email
- [ ] Refresh the page on a deep link (SPA fallback works)
- [ ] Refund the test payment and confirm access is revoked

## 11. Troubleshooting

| Symptom                       | Likely cause                                | Fix                                                                                       |
| ----------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Container exits at startup    | missing required env var                    | production settings fail closed by design — read the error naming the variable            |
| `DisallowedHost`              | host not in `ALLOWED_HOSTS`                 | add the exact hostname                                                                    |
| CORS error in browser         | origin not listed exactly (scheme + port)   | fix `CORS_ALLOWED_ORIGINS`                                                                |
| CSRF failure on admin         | `CSRF_TRUSTED_ORIGINS` missing              | add the full origin                                                                       |
| `503 playback_unavailable`    | signing key unset/rotated                   | set `CLOUDFLARE_STREAM_SIGNING_KEY` and restart                                           |
| Video stuck `processing`      | missed `video.processed` webhook            | `sync_pending_videos` self-heals within 10 minutes                                        |
| Webhook `400`                 | secret mismatch                             | make dashboard and env match                                                              |
| Payments stuck `CREATED`      | webhook unreachable / client closed browser | `reconcile_payments` resolves within 15 minutes; check the endpoint is publicly reachable |
| Leaderboard stale             | nightly rebuild hasn't run                  | `POST /api/v1/leaderboard/recalculate/` or wait for beat                                  |
| 502 from Nginx                | backend not listening / crashed             | check `docker compose logs backend`                                                       |
| Migrations conflict on deploy | concurrent migrators                        | run migrations as a single release step, never from every replica                         |
| Static files 404              | `collectstatic` not run                     | run it in the release step                                                                |
