"""WhatsApp template registry.

Code owns the *shape* of each template (name, ordered variables, preference
category, Meta category and the body text to submit for review).  The database
(``NotificationTemplate``) owns operational state: the provider template name,
language and the approval status an administrator recorded after checking Meta.

Callers pick a template by internal name from this closed registry -- user input
can never select a template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.notifications.models import Category

_WS = re.compile(r"\s+")
MAX_PARAM_LENGTH = 400


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    variables: tuple[str, ...]
    body: str  # what to submit to Meta; {{n}} follows `variables` order
    category: str  # preference Category, "" = account/security
    meta_category: str = "utility"
    otp: bool = False
    has_trigger: bool = True  # False: no LMS event sends this yet


def _spec(name, variables, body, category, **kw) -> TemplateSpec:
    return TemplateSpec(name, tuple(variables), body, category, **kw)


SPECS: dict[str, TemplateSpec] = {
    s.name: s
    for s in [
        _spec(
            "live_class_scheduled",
            ["student_name", "class_title", "course_title", "start_time"],
            'Hi {{1}}, a live class "{{2}}" for {{3}} is scheduled for {{4}}. '
            "Open LawSchool to join when it starts.",
            Category.LIVE_CLASS,
        ),
        _spec(
            "live_class_reminder",
            ["student_name", "class_title", "start_time", "time_left"],
            'Reminder: "{{2}}" starts {{4}} (at {{3}}). Hi {{1}}, open LawSchool to join.',
            Category.LIVE_CLASS,
        ),
        _spec(
            "live_class_rescheduled",
            ["student_name", "class_title", "new_start_time"],
            'Hi {{1}}, the live class "{{2}}" has been rescheduled to {{3}}.',
            Category.SCHEDULE_CHANGE,
        ),
        _spec(
            "live_class_cancelled",
            ["student_name", "class_title", "original_start_time"],
            'Hi {{1}}, the live class "{{2}}" planned for {{3}} has been cancelled.',
            Category.SCHEDULE_CHANGE,
        ),
        _spec(
            "live_class_link_updated",
            ["student_name", "class_title", "start_time"],
            'Hi {{1}}, the joining link for "{{2}}" ({{3}}) has changed. '
            "Open LawSchool for the latest link.",
            Category.SCHEDULE_CHANGE,
        ),
        _spec(
            "live_class_recording_available",
            ["student_name", "class_title"],
            'Hi {{1}}, the recording of "{{2}}" is now available on LawSchool.',
            Category.LIVE_CLASS,
            has_trigger=False,
        ),
        _spec(
            "quiz_result_available",
            ["student_name", "quiz_title", "score_text"],
            'Hi {{1}}, your result for "{{2}}" is ready: {{3}}.',
            Category.QUIZ_UPDATES,
        ),
        _spec(
            "assignment_reminder",
            ["student_name", "assignment_title", "due_time"],
            'Hi {{1}}, "{{2}}" is due on {{3}}.',
            Category.ASSIGNMENT_REMINDERS,
            has_trigger=False,
        ),
        _spec(
            "weekly_progress_summary",
            ["student_name", "lessons_completed", "quizzes_attempted"],
            "Hi {{1}}, your week on LawSchool: {{2}} lesson(s) completed and "
            "{{3}} quiz attempt(s).",
            Category.PROGRESS_UPDATES,
        ),
        _spec(
            "study_inactivity_reminder",
            ["student_name", "days"],
            "Hi {{1}}, you have not studied on LawSchool for {{2}} days. "
            "Pick up where you left off.",
            Category.STUDY_REMINDERS,
        ),
        _spec(
            "payment_success",
            ["student_name", "amount", "plan_name"],
            "Hi {{1}}, we received your payment of {{2}} for {{3}}. Thank you.",
            Category.PAYMENT_UPDATES,
        ),
        _spec(
            "payment_failure",
            ["student_name", "plan_name"],
            "Hi {{1}}, your payment for {{2}} could not be completed. "
            "You can retry from the subscription page.",
            Category.PAYMENT_UPDATES,
        ),
        _spec(
            "subscription_expiry_reminder",
            ["student_name", "plan_name", "end_date"],
            "Hi {{1}}, your {{2}} access ends on {{3}}. Renew to keep your courses unlocked.",
            Category.PAYMENT_UPDATES,
        ),
        _spec(
            "subscription_renewed",
            ["student_name", "plan_name", "end_date"],
            "Hi {{1}}, {{2}} is active. You have access until {{3}}.",
            Category.PAYMENT_UPDATES,
        ),
        _spec(
            "subscription_expired",
            ["student_name", "plan_name", "end_date"],
            "Hi {{1}}, your {{2}} access ended on {{3}}. Renew to continue learning.",
            Category.PAYMENT_UPDATES,
        ),
        _spec(
            "certificate_available",
            ["student_name", "course_title"],
            "Hi {{1}}, your certificate for {{2}} is ready on LawSchool.",
            Category.PROGRESS_UPDATES,
            has_trigger=False,
        ),
        _spec(
            "platform_announcement",
            ["student_name", "announcement_title", "announcement_text"],
            "Hi {{1}}, {{2}}: {{3}}",
            Category.ANNOUNCEMENTS,
        ),
        _spec(
            "whatsapp_verification_code",
            ["code"],
            "{{1}} is your LawSchool verification code.",
            "",
            meta_category="authentication",
            otp=True,
        ),
    ]
}


class TemplateVariableError(ValueError):
    pass


def clean_param(value) -> str:
    """Meta rejects newlines, tabs and long space runs in parameters."""
    text = _WS.sub(" ", str(value if value is not None else "")).strip()
    return text[:MAX_PARAM_LENGTH]


def build_params(spec: TemplateSpec, variables: dict) -> list[str]:
    """Return ordered, validated body parameters or raise ``TemplateVariableError``."""
    missing = [v for v in spec.variables if v not in variables]
    extra = [k for k in variables if k not in spec.variables]
    if missing or extra:
        raise TemplateVariableError(
            f"{spec.name}: missing={missing or '-'} unexpected={extra or '-'}"
        )
    params = [clean_param(variables[v]) for v in spec.variables]
    if any(not p for p in params):
        raise TemplateVariableError(f"{spec.name}: empty variable value")
    return params


def seed_templates() -> int:
    """Create a DB row per registry entry (approval stays 'unknown')."""
    from django.conf import settings

    from apps.notifications.models import NotificationTemplate

    created = 0
    for spec in SPECS.values():
        _obj, was_created = NotificationTemplate.objects.get_or_create(
            internal_name=spec.name,
            defaults={
                "provider_template_name": spec.name,
                "language_code": settings.WHATSAPP_DEFAULT_LANGUAGE,
                "meta_category": spec.meta_category,
                "notification_category": spec.category,
                "variable_schema": list(spec.variables),
                "body_preview": spec.body,
            },
        )
        created += was_created
    return created
