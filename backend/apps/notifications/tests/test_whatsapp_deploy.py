"""Deployment-time guarantees: misconfiguration is loud, defaults are safe."""

from io import StringIO

from django.core.management import call_command

from apps.core.checks import check_whatsapp_configuration
from apps.notifications.models import NotificationTemplate
from apps.notifications.whatsapp.templates import SPECS


def test_disabled_by_default_needs_no_credentials(settings):
    settings.WHATSAPP_ENABLED = False
    settings.WHATSAPP_ACCESS_TOKEN = ""
    assert check_whatsapp_configuration(None) == []


def test_enabled_without_credentials_is_a_deploy_error(settings):
    settings.WHATSAPP_ENABLED = True
    settings.WHATSAPP_ACCESS_TOKEN = ""
    settings.WHATSAPP_VERIFY_TOKEN = ""
    (error,) = check_whatsapp_configuration(None)
    assert error.id == "lawschool.E004"
    assert "WHATSAPP_ACCESS_TOKEN" in error.msg and "WHATSAPP_VERIFY_TOKEN" in error.msg
    assert "test-access-token-SECRET" not in error.msg


def test_enabled_with_credentials_passes(settings):
    settings.WHATSAPP_ENABLED = True
    assert check_whatsapp_configuration(None) == []


def test_seed_command_creates_unapproved_templates_idempotently(db):
    out = StringIO()
    call_command("seed_whatsapp_templates", "--show-bodies", stdout=out)
    call_command("seed_whatsapp_templates", stdout=StringIO())
    assert NotificationTemplate.objects.count() == len(SPECS)
    assert set(NotificationTemplate.objects.values_list("approval_status", flat=True)) == {"unknown"}
    assert "live_class_reminder" in out.getvalue()


def test_every_template_body_uses_exactly_its_declared_variables():
    import re

    for spec in SPECS.values():
        used = {int(n) for n in re.findall(r"\{\{(\d+)\}\}", spec.body)}
        assert used == set(range(1, len(spec.variables) + 1)), spec.name


def test_templates_without_an_lms_trigger_are_flagged():
    from apps.notifications.whatsapp.templates import SPECS

    idle = {n for n, s in SPECS.items() if not s.has_trigger}
    assert idle == {"live_class_recording_available", "assignment_reminder", "certificate_available"}
