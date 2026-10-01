# Payments

Payment integration with Razorpay. The governing rule is:

> **Never trust payment status from the frontend.**

A client claiming "payment succeeded" is treated as an unverified claim. Subscription
state changes only after a server-side cryptographic verification, inside a
database transaction.

## 1. Configuration

```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxx
PAYMENT_WEBHOOK_TOLERANCE_SECONDS=300
```

| Value                     | Where it comes from | Exposure                                                 |
| ------------------------- | ------------------- | -------------------------------------------------------- |
| `RAZORPAY_KEY_ID`         | Settings → API Keys | **public** — sent to the browser in the checkout payload |
| `RAZORPAY_KEY_SECRET`     | Settings → API Keys | server only                                              |
| `RAZORPAY_WEBHOOK_SECRET` | Settings → Webhooks | server only                                              |

`checkout_payload()` deliberately returns only `key_id`. The secret, webhook secret
and Cloudflare credentials never leave the server. `config/settings/production.py`
refuses to boot if any of the three is unset.

## 2. Happy path

```
Student
  │  selects a plan
  ▼
POST /api/v1/payments/orders/         ← server creates the Razorpay order
  │  { plan_slug, idempotency_key }
  │  → 201 { payment, checkout: { order_id, key_id, amount, currency, prefill } }
  ▼
Razorpay Checkout opens in the browser
  │  student pays
  ▼
POST /api/v1/payments/verify/         ← client sends ONLY the three identifiers
  │  { razorpay_order_id, razorpay_payment_id, razorpay_signature }
  ▼
Server recomputes HMAC_SHA256(order_id + "|" + payment_id, key_secret)
  │  compare against razorpay_signature
  │  ✓ match
  ▼
transaction.atomic():
  ├─ Payment.status = CAPTURED, captured_at = now
  ├─ activate_subscription(user, plan, payment_reference)
  └─ queue payment + activation notifications
  ▼
Subscription ACTIVE, entitlement cache invalidated
```

Independently and asynchronously, Razorpay also calls the webhook. Both paths
converge on `_settle_payment()`, so whichever arrives first wins and the second is
a no-op.

## 3. What the client is allowed to send

`VerifyPaymentView` accepts exactly three fields — all identifiers:

```json
{
  "razorpay_order_id": "order_MxAbC",
  "razorpay_payment_id": "pay_MxAbC",
  "razorpay_signature": "9ef4dffbfd84..."
}
```

It does **not** accept `amount`, `status`, `plan`, or `user`. The serializer
rejects unknown fields, and the amount is always re-read from the server's own
`Payment` row. This closes the obvious attacks:

| Attack                                  | Why it fails                                                         |
| --------------------------------------- | -------------------------------------------------------------------- |
| "Set `status: captured` in the request" | There is no such field                                               |
| "Pay ₹1 for a ₹4,999 plan"              | The amount comes from our order row, and the webhook cross-checks it |
| "Use someone else's order id"           | `payment.user_id != user.pk` → `forbidden`                           |
| "Forge a signature"                     | HMAC requires `RAZORPAY_KEY_SECRET`, which never leaves the server   |
| "Replay a successful verify"            | `status == CAPTURED` returns the existing payment idempotently       |
| "Replay a webhook"                      | `UniqueConstraint(provider, event_id)` rejects the second delivery   |

## 4. Idempotency

Three layers, each defending a different race.

### 4.1 Order creation — `idempotency_key`

```python
if idempotency_key:
    existing = Payment.objects.filter(
        user=user, plan=plan, idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        return existing          # same order, no second charge
```

The SPA generates the key once per checkout intent. A retried request after a
network timeout returns the _same_ order rather than creating a second one the
student could also be charged for. `provider_order_id` is additionally `unique`,
so even a race that slips past the check hits an `IntegrityError` and recovers by
fetching the existing row.

### 4.2 Verification — locking read + status guard

```python
with transaction.atomic():
    payment = Payment.objects.select_for_update().get(provider_order_id=order_id)

if payment.status == PaymentStatus.CAPTURED:
    return payment               # idempotent success
```

`select_for_update` serialises concurrent verifications of the same order, and the
status check makes a repeat a no-op. Two simultaneous verifications cannot both
activate.

### 4.3 Webhooks — the database is the lock

```python
constraints = [
    models.UniqueConstraint(fields=["provider", "event_id"],
                            name="unique_webhook_event")
]
```

`record_webhook_event()` returns `(event, created)`. `created=False` means the
delivery has been seen before. It is only a no-op when the stored event is already
`processed`; if an earlier attempt crashed (we answered 500), the redelivery re-runs
the idempotent handler. Signatures are verified *before* anything is stored, so an
unsigned request can neither write rows nor claim a genuine event id.

The insert runs inside its own savepoint, so when the constraint fires only that
savepoint rolls back and the surrounding transaction stays usable for the
follow-up lookup. This makes duplicate handling race-safe under Razorpay's
concurrent retry behaviour, which application-level "have I seen this?" checks are
not.

## 5. Webhook processing

```
POST /api/v1/payments/webhook/
   │
   ├─ 1. Read request.body  ← the RAW bytes
   ├─ 2. Verify HMAC over those exact bytes
   ├─ 3. Record the event (dedupe by event_id)
   ├─ 4. Dispatch to a handler
   └─ 5. Mark processed
```

**Why the raw body matters.** The signature is computed over the exact bytes
Razorpay sent. Any JSON round-trip — parse and re-serialize — changes whitespace or
key order and breaks verification. The view therefore reads `request.body` rather
than a re-serialized copy of `request.data`. This is unusual enough to be called
out in the view's docstring so nobody "cleans it up" later.

### Handled events

| Event                                 | Handler behaviour                                                   |
| ------------------------------------- | ------------------------------------------------------------------- |
| `payment.captured`                    | settle: mark captured, activate subscription                        |
| `payment.failed`                      | record the decline; if the payment is already captured, ignore      |
| `refund.processed`                    | full refund: mark `REFUNDED`, cancel subscription, end access; partial refund: record the refund id only |
| `subscription.charged`                | routed to the same activation path, so a renewal _extends_ the term |

### Amount cross-check

```python
if int(provider_amount) != payment.amount_paise:
    payment.status = PaymentStatus.FAILED
    payment.failure_reason = f"Amount mismatch: gateway reported {provider_amount}, expected {payment.amount_paise}."
```

A captured INR 1 payment against an INR 10,000 order is recorded as failed and
logged at ERROR rather than activating anything.

### Response semantics

| Situation          | Response                      | Why                                                                                       |
| ------------------ | ----------------------------- | ----------------------------------------------------------------------------------------- |
| Processed          | `200 {"status": "processed"}` | done                                                                                      |
| Duplicate delivery | `200 {"status": "duplicate"}` | already processed; **not** an error — an error would make Razorpay keep retrying           |
| Unknown event type | `200 {"status": "ignored"}`   | acknowledged so retries stop                                                              |
| Bad signature      | `400 invalid_signature`       | logged at ERROR; nothing is persisted                                                     |
| Handler crashed    | `500 webhook_failed`          | deliberately non-2xx so Razorpay retries; the redelivery re-runs the idempotent handler    |

## 6. Failure handling

### Signature mismatch

The payment is **committed** as FAILED (with `provider_payment_id` and the
attempted signature recorded) before the exception is raised, and the subscription
is marked failed. This is intentional: a declined or forged attempt must appear in
the payment history so support can answer "I was charged but nothing happened".

Wrapping the whole function in `transaction.atomic()` would silently roll that
record back. Only the locking read uses a transaction. This is documented in the
function docstring because it looks like a missing transaction at first glance.

### Failed payment

`payment.failed` records the decline reason, sets `failure_reason`, stores the raw
entity under `provider_payload["failure"]`, marks the subscription failed and
queues a notification. If the payment is already `CAPTURED`, the late event is
ignored — a capture that won the race must not be undone by a stale failure event.

### Refund

Access ends **immediately**: the subscription moves to `CANCELLED` with
`end_date = now`, and the entitlement cache is invalidated so the change is visible
on the next request rather than after the 60s TTL.

### Missed webhook

If Razorpay cannot reach the endpoint, or the student closes the browser before the
callback fires, the payment stays in `CREATED`. The `reconcile_payments` Celery task
(built into beat, every 15 minutes) finds payments older than 30 minutes in
`CREATED`/`AUTHORIZED`, queries the gateway for the authoritative status, and
applies it through **the same handler the webhook would use**. There is one
settlement code path, so reconciliation cannot drift from webhook handling.

## 7. Status model

`Payment.status`: `created` → `authorized` → `captured`, or `failed`, or `refunded`.

`Subscription.status`: `pending` → `active` → `expired` / `cancelled` / `failed`.

A payment being `captured` is what activates a subscription. A subscription being
`active` is **not** by itself sufficient for access — the date window is always
checked too (see [architecture.md](architecture.md#4-entitlement-the-single-authorization-chokepoint)).

## 8. Testing

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest apps/payments -v
..\.venv\Scripts\python.exe -m pytest apps/payments -k webhook
```

`config/settings/test.py` provides deterministic fake credentials so signature
tests are reproducible:

```python
RAZORPAY_KEY_ID = "rzp_test_key"
RAZORPAY_KEY_SECRET = "test_secret_key"
RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"
```

Covered cases: valid signature activates · invalid signature is rejected and
recorded · duplicate webhook is a no-op · failed payment marks the subscription
failed · cross-user verification is forbidden · amount mismatch does not activate ·
refund cancels access immediately · reconciliation resolves a stuck payment.

## 9. Going live checklist

- [ ] Switch from **Test Mode** to **Live Mode** and generate live keys.
- [ ] Create a _new_ webhook secret for production; do not reuse the test value.
- [ ] Point the webhook URL at the real domain over HTTPS:
      `https://<domain>/api/v1/payments/webhook/`
- [ ] Confirm the events list includes `payment.captured`, `payment.failed`,
      `payment.authorized`, `refund.created`, `refund.processed`, `order.paid`.
- [ ] Verify the endpoint is reachable from the public internet (not behind auth).
- [ ] Test one real low-value payment end to end, then refund it and confirm access
      is revoked.
- [ ] Monitor `Payment` rows stuck in `CREATED` and the `reconcile_payments` task
      output.
- [ ] Set `PAYMENT_WEBHOOK_TOLERANCE_SECONDS` appropriately for your clock accuracy.
- [ ] Alert on `webhook signature verification failed` — a spike means a rotated
      secret or someone probing the endpoint.
