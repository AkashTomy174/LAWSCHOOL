"""Domain constants shared across apps.

Keeping the canonical status/role strings in one module stops subtle typos
("ACTIVE" vs "active") from silently breaking entitlement checks.
"""

from django.db import models


class UserRole(models.TextChoices):
    STUDENT = "student", "Student"
    INSTRUCTOR = "instructor", "Instructor"
    ADMIN = "admin", "Admin"


class CourseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class LessonStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class VideoStatus(models.TextChoices):
    PENDING = "pending", "Pending upload"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class SubscriptionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class PaymentStatus(models.TextChoices):
    CREATED = "created", "Created"
    AUTHORIZED = "authorized", "Authorized"
    CAPTURED = "captured", "Captured"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class PaymentProvider(models.TextChoices):
    RAZORPAY = "razorpay", "Razorpay"


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    IN_APP = "in_app", "In-app"


class NotificationKind(models.TextChoices):
    PAYMENT_SUCCESS = "payment_success", "Payment successful"
    PAYMENT_FAILED = "payment_failed", "Payment failed"
    SUBSCRIPTION_ACTIVATED = "subscription_activated", "Subscription activated"
    SUBSCRIPTION_EXPIRING = "subscription_expiring", "Subscription expiring soon"
    SUBSCRIPTION_EXPIRED = "subscription_expired", "Subscription expired"
    PASSWORD_RESET = "password_reset", "Password reset"
    ACCOUNT_VERIFICATION = "account_verification", "Account verification"
    COURSE_ENROLLED = "course_enrolled", "Course enrollment"
    QUIZ_RESULT = "quiz_result", "Quiz result"


class UnlockRule(models.TextChoices):
    """How a course becomes accessible to a student."""

    # Any ACTIVE subscription plan that includes the course unlocks it.
    SUBSCRIPTION = "subscription", "Subscription"
    # Free / open course: any authenticated student may watch it.
    FREE = "free", "Free"


def model_status_field(*choices) -> models.CharField:  # pragma: no cover - helper
    """Small helper for building indexed status columns consistently."""
    return models.CharField(max_length=20, choices=choices, db_index=True)
