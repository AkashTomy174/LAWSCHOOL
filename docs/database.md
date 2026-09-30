z# Database Design

PostgreSQL is the system of record. SQLite is supported for zero-config local
development, but production targets PostgreSQL 15+.

## 1. Entity relationships

```
User (custom, email login)
 │
 ├─1:N─ Subscription ─N:1─ Plan ─M:N─ Course
 │                                └─ is_all_access (unlocks everything)
 │
 ├─1:1─ LeaderboardEntry
 ├─1:N─ Payment ─N:1─ Plan
 ├─1:N─ Notification
 ├─1:N─ QuizAttempt ─1:N─ QuizAnswer
 ├─1:N─ VideoProgress ─N:1─ Video ─1:1─ Lesson
 └─1:N─ PlaybackSession ─N:1─ Video

Course
 ├─1:N─ Section ─1:N─ Lesson ─1:1─ Video
 │                            └─1:1─ Quiz ─1:N─ Question ─1:N─ Option
 └─1:N─ Quiz
```

The required hierarchy:

```
Course
  |
  ├── Section
  │     ├── Lesson/Video
  │     ├── Lesson/Video
  │     └── Quiz
  |
  └── Section
        ├── Lesson/Video
        └── Quiz
```

is expressed as `Course → Section → Lesson`, with `Lesson` holding a nullable
`OneToOneField` to `Video` and to `Quiz`. A DB-level `CheckConstraint` requires at
least one of the two to be present, so a lesson that contains nothing is
impossible rather than merely discouraged.

## 2. `users.User`

| Column                                    | Type         | Notes                                       |
| ----------------------------------------- | ------------ | ------------------------------------------- |
| `id`                                      | UUID         | PK, not enumerable                          |
| `email`                                   | varchar(254) | **unique, indexed**, `USERNAME_FIELD`       |
| `name`                                    | varchar(150) | required (`REQUIRED_FIELDS`)                |
| `phone`                                   | varchar(20)  | optional, E.164 preferred                   |
| `role`                                    | varchar(20)  | indexed, `student` / `instructor` / `admin` |
| `avatar`                                  | image        | optional, validated                         |
| `bio`, `city`, `state`, `qualification`   | text         | profile                                     |
| `is_active`                               | bool         | soft deactivation — history is preserved    |
| `is_staff`, `is_superuser`                | bool         | Django admin / permissions                  |
| `is_email_verified`                       | bool         |                                             |
| `date_joined`, `last_login`, `updated_at` | timestamptz  |                                             |

Indexes: `user_email_idx (email)`, `user_role_active_idx (role, is_active)`,
`user_joined_idx (date_joined)`.

Constraint: `user_role_valid` — `role` must be one of the three enum values,
enforced in Postgres so a bad row cannot be inserted by a script or a migration.

**Decisions**

- `AbstractBaseUser` + custom manager rather than `AbstractUser`: no unused
  `username` column, and Django's own docs recommend this when email is the
  identifier.
- A single indexed `role` column rather than Django Groups: roles are a closed set
  read on nearly every request, so a plain column beats a three-table join. The
  Groups/permissions machinery remains available for finer delegation later.
- Soft deactivation: payments, refunds and quiz attempts must survive an account
  being disabled, for audit and dispute handling.

## 3. `courses`

### `Course`

| Column                               | Notes                                                       |
| ------------------------------------ | ----------------------------------------------------------- |
| `id`                                 | UUID PK                                                     |
| `title`                              | indexed                                                     |
| `slug`                               | **unique, indexed** — the public identifier                 |
| `subtitle`, `description`, `summary` | summary capped at 500 chars                                 |
| `thumbnail`                          | image, validated (type + size)                              |
| `instructor`                         | FK → User, `on_delete=PROTECT`, limited to instructor/admin |
| `price`                              | `Decimal(10,2)`, `>= 0`                                     |
| `status`                             | `draft` / `published` / `archived`, indexed                 |
| `unlock_rule`                        | `subscription` / `free`                                     |
| `published_at`                       | indexed, stamped only on first publish                      |
| `duration_minutes`, `lesson_count`   | denormalised aggregates                                     |
| `language`, `level`                  | filterable metadata                                         |

Indexes: `course_slug_idx`, `course_status_pub_idx (status, published_at)`,
`course_instructor_idx (instructor, status)`, `course_unlock_idx (unlock_rule, status)`.

Constraints: `course_price_non_negative`, `course_status_valid`,
`course_unlock_rule_valid`.

`instructor` uses `PROTECT`, not `CASCADE`: deleting a user must never silently
orphan a published course.

### `Section`

FK `course` (`CASCADE`), `title`, `description`, `ordering` (indexed),
`is_published`.

Index: `section_course_order_idx (course, ordering)`.
Constraint: **`unique_section_ordering_per_course (course, ordering)`**.

### `Lesson`

FK `section` (`CASCADE`), `title`, `description`, `ordering` (indexed),
`duration_seconds`, `is_preview`, `status` (indexed), plus the nullable
`OneToOne` `video` (`SET_NULL`) and `quiz` (`SET_NULL`).

Indexes: `lesson_section_order_idx (section, ordering)`,
`lesson_status_preview_idx (status, is_preview)`.

Constraints:

- `unique_lesson_ordering_per_section (section, ordering)`
- **`lesson_requires_video_or_quiz`** — `video IS NOT NULL OR quiz IS NOT NULL`

A `Lesson.save()` also refreshes the parent course's denormalised
`lesson_count` / `duration_minutes`, so course lists need no join at all. The cost
is one aggregate per lesson write, which is negligible against a join on every
course-list read.

## 4. `subscriptions`

### `Plan`

`id` UUID, `name` (unique), `slug` (unique, indexed), `description`,
`price` `Decimal(10,2)`, `currency` (default `INR`), `duration_days`,
`courses` (M2M → Course, `related_name="plans"`), `is_all_access`, `is_active`
(indexed), `is_featured`, `ordering`, timestamps.

Index: `plan_active_order_idx (is_active, ordering)`.
Constraints: `plan_price_non_negative`, `plan_duration_positive`.

`price_paise` is a property (`int(price * 100)`) because Razorpay takes the smallest
currency unit. Deriving it in one place prevents a rounding mismatch elsewhere.

`is_all_access` exists so the flagship "everything" tier does not require attaching
every future course by hand, while the explicit M2M still allows a plan to be
scoped to a track.

### `Subscription`

FK `user` (`CASCADE`), FK `plan` (**`PROTECT`**), `status` (indexed),
`start_date`, `end_date` (indexed), `payment_reference` (indexed),
`cancelled_at`, timestamps.

Indexes:

- **`sub_user_status_end_idx (user, status, end_date)`** — the single hottest query
  in the system: "does this user have a currently active subscription?"
- `sub_status_end_idx (status, end_date)` — the hourly expiry sweep
- `sub_payment_ref_idx (payment_reference)`

Constraints:

- `subscription_status_valid` — status must be one of `pending`, `active`,
  `expired`, `cancelled`, `failed`
- `subscription_end_after_start` — `end_date >= start_date` (NULLs tolerated)

`plan` uses `PROTECT`: deleting a plan that people paid for must not erase the
evidence of what they bought.

`is_currently_active` checks **both** the status and the date window. Relying on
`status` alone would keep access alive for rows that a crashed expiry job never
flipped.

## 5. `videos`

### `Video`

Metadata only — **no video bytes are ever stored here**.

| Column                               | Notes                                              |
| ------------------------------------ | -------------------------------------------------- |
| `id`                                 | UUID PK                                            |
| `playback_uid`                       | UUID, **unique**, indexed — internal opaque handle |
| `cloudflare_video_id`                | **unique**, indexed — the provider's identifier    |
| `title`, `description`               |                                                    |
| `status`                             | `pending` / `processing` / `ready` / `failed`      |
| `duration_seconds`                   | synced from Cloudflare                             |
| `thumbnail_url`                      |                                                    |
| `require_signed_urls`                | must be true for protected content                 |
| `processing_error`, `last_synced_at` | operational                                        |

Indexes: `video_status_created_idx (status, created_at)`,
`video_cf_id_idx (cloudflare_video_id)`.
Constraint: `status` must be a valid `VideoStatus`.

The API exposes `playback_uid` to clients, never `cloudflare_video_id`. Keeping the
provider id server-side means a leaked URL reveals nothing usable, and the
identifier can be rotated without touching lesson ordering.

### `VideoProgress`

One row per `(user, video)` — the unique constraint guarantees it, so a retried
progress update cannot create duplicates.

`watched_seconds`, `completion_percentage`, `completed`, `last_position`,
`update_count`, `updated_at`.

Indexes: `progress_user_lesson_idx (user, lesson)`,
`progress_user_recent_idx (user, updated_at)`,
`progress_user_completed_idx (user, completed)`,
`progress_video_completed_idx (video, completed)`.
Constraint: `unique_progress_per_user_video (user, video)` plus a
percentage-bounds check.

`(user, lesson)` is indexed explicitly because "what have I completed?" and the
dashboard's "recently watched" are both hot paths.

### `PlaybackSession`

Audit trail for every issued token: `user`, `video`, `ip_address`, `user_agent`,
`token_fingerprint`, `expires_at`, `created_at`.

**The token itself is never stored** — only a SHA-256 fingerprint. A database dump
therefore cannot be used to replay playback.

Indexes: `playback_user_created_idx (user, created_at)`,
`playback_video_created_idx (video, created_at)`.

## 6. `payments`

### `Payment`

`id` UUID, FK `user`, FK `plan`, FK `subscription` (nullable), `status`,
`amount` `Decimal(10,2)`, `currency`, `amount_paise` (property),
**`provider_order_id` (unique, indexed)**, `provider_payment_id` (indexed),
`provider_refund_id`, `provider_signature`, `provider_payload` (JSON),
`idempotency_key`, `failure_reason`, `captured_at`, `notes`, timestamps.

Indexes: `payment_user_status_idx (user, status)`,
`payment_status_created_idx (status, created_at)`,
`payment_provider_pay_idx (provider_payment_id)`.
Constraints: `payment_status_valid`, `payment_amount_non_negative`.

`provider_order_id` being **unique** is a load-bearing security property: a replayed
order id cannot create a second payment row.

### `WebhookEvent`

`provider`, `event_id`, `event_type`, `payload` (JSON), `payload_hash`,
`signature_valid`, `processed`, `processed_at`, `processing_error`, `received_at`.

**Constraint: `UniqueConstraint(provider, event_id)`** — this _is_ the idempotency
guarantee. Duplicate deliveries are rejected by the database rather than by
application logic, which makes it correct under concurrent delivery from
Razorpay's retry mechanism. A duplicate is treated as a no-op returning
`{"status": "duplicate"}`, not an error.

Indexes: `webhook_processed_idx (processed, received_at)`,
`webhook_type_idx (event_type, received_at)`.

## 7. `quizzes`

`Quiz` — FK `course`, `title`, `description`, `pass_percentage`, `max_attempts`,
`time_limit_minutes`, `is_published`, timestamps.

`Question` — FK `quiz`, `text`, `marks`, `ordering`.
Constraint: unique `(quiz, ordering)`.

`Option` — FK `question`, `text`, `is_correct`, `ordering`.
Constraint: unique `(question, ordering)`.

`QuizAttempt` — FK `user`, FK `quiz`, `started_at`, `submitted_at`, `score`,
`max_score`, `percentage`, `passed`, `time_taken_seconds`.

`QuizAnswer` — FK `attempt`, FK `question`, FK `selected_option` (nullable),
`is_correct`, `marks_awarded`.

Indexes support "my attempts", "attempts for this quiz" and
"has this user passed?" without table scans.

**`is_correct` is never serialized to students.** It appears only on the authoring
serializer used by instructors and admins. Exposing it on the student-facing
question payload would put the answer key one network-tab away.

## 8. `leaderboard`

`LeaderboardEntry` — `OneToOneField(user)`, with `total_score`, `quiz_score`,
`quizzes_passed`, `lessons_completed`, `courses_completed`, `courses_enrolled`,
`rank`, `last_activity_at`, `updated_at`.

Indexes: `lb_ordering_idx (-total_score, -lessons_completed, user)`,
`lb_courses_idx (-courses_completed)`, `lb_activity_idx (last_activity_at)`.
Constraint: `lb_total_non_negative`.

`lb_ordering_idx` mirrors the exact `ORDER BY` of the leaderboard query, so
PostgreSQL walks the index instead of sorting the result set.

Weighting, documented so the ranking is explainable:
`total_score = quiz_score + (lessons_completed × 10)`.

`LeaderboardSnapshot` — `scope`, `captured_at`, `entries` (JSON, top-N). Retained
to a bounded history (52 entries per scope); snapshots are analytics, not records.

### Why a derived table

The alternative — a `GROUP BY` over `QuizAttempt` and `VideoProgress` on every
leaderboard page load — scans the two largest tables in the system. A small indexed
table makes the leaderboard `O(page_size)`, with the expensive full recomputation
deferred to a nightly Celery job and refreshed incrementally on each grading event
(`refresh_user_leaderboard`).

Trade-off: a row can be stale until the next grading event or the nightly rebuild.
That is acceptable for a leaderboard and unacceptable for a payment — which is
precisely why payments are never denormalised.

## 9. `notifications`

`Notification` — FK `user`, `kind`, `channel` (`email` / `in_app`), `title`,
`body`, `payload` (JSON), `read_at`, `email_sent_at`, `email_error`, `created_at`.

Index supports "my unread notifications" efficiently.

## 10. Query performance

### Confirmed patterns

- **Entitlement** is a single indexed lookup on
  `(user, status, end_date)` per request, then cached for 60s.
- **Course detail** costs a fixed number of queries (course + sections + lessons +
  quizzes) regardless of course size, via `Prefetch(..., to_attr=...)` in
  `courses/selectors.py`. The `to_attr` form matters: it lets the serializer reuse
  the prefetched objects instead of triggering a fresh query per section.
- **Course list** paginates _first_, then computes progress for that page only.
  Progress is two aggregate queries for the whole page, not one per course.
- **Leaderboard** is one indexed query with `select_related("user")`.
- **User rank** is `COUNT(*) WHERE total_score > mine` — an index-only scan —
  rather than enumerating the table in Python.

### Rules

1. No database access inside a loop. Aggregates and `prefetch_related` instead.
2. `select_related` for forward FKs read on every row; `prefetch_related` for
   reverse/M2M.
3. Complex reads live in `selectors.py` so the query shape is reviewable in one
   place.
4. Pagination on courses, students, payments, leaderboard, quiz attempts and
   notifications.
5. Cached answers are always re-verified against the database — the cache can never
   grant access the database would deny.

### N+1 regression tests

`apps/courses/tests/test_courses.py::TestQueryEfficiency` uses
`CaptureQueriesContext` to assert that query counts stay bounded as row counts
grow. Adding 12 courses or 10 lessons must not add queries. This catches the
regression at test time rather than in production.

## 11. Migrations

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py sqlmigrate courses 0001     # inspect the SQL first
python manage.py showmigrations
```

Conventions:

- `AUTH_USER_MODEL` is set in `base.py` before the first migration so the custom
  user is used from the very first commit — swapping it later is painful.
- Read a generated migration before applying it, especially anything touching
  constraints or a nullable-to-non-null change.
- Add indexes in their own migration when backfilling large tables, so an index
  build does not block a schema change.
- Never edit an applied migration; add a new one.
