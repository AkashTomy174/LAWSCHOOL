"""Subscriptions app."""

from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    verbose_name = "Subscriptions"

    def ready(self):
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from apps.subscriptions.models import Plan
        from apps.subscriptions.services import bump_plans_generation

        # Plan coverage is cached inside entitlement decisions; any change to it
        # must invalidate them.  ``Plan.courses.through`` also fires for edits made
        # from the course side (``course.plans.add(...)``).
        uid = "subscriptions.plan-coverage-changed"
        post_save.connect(bump_plans_generation, sender=Plan, dispatch_uid=uid + ".save")
        post_delete.connect(bump_plans_generation, sender=Plan, dispatch_uid=uid + ".delete")
        m2m_changed.connect(
            _on_plan_courses_changed, sender=Plan.courses.through, dispatch_uid=uid + ".m2m"
        )


def _on_plan_courses_changed(action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        from apps.subscriptions.services import bump_plans_generation

        bump_plans_generation()
