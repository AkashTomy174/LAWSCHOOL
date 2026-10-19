"""Meta webhook (handshake, signature, dedupe) and the inbound assistant."""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.notifications.models import (
    ConsentStatus,
    IncomingWhatsAppMessage,
    Notification,
    NotificationPreference,
)
from apps.notifications.tests.wa_support import (
    message_payload,
    ok_response,
    sign,
    status_payload,
)
from apps.notifications.whatsapp import commands, service

URL = "/api/v1/notifications/whatsapp/webhook/"
WA_ID = "919876543210"


# ------------------------------- handshake -------------------------------- #
def test_handshake_echoes_challenge_for_correct_token(api_client):
    r = api_client.get(URL, {"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "12345"})
    assert r.status_code == 200 and r.content == b"12345"


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
        {"hub.mode": "unsubscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "1"},
        {},
    ],
)
def test_handshake_rejects_bad_token_or_mode(api_client, params):
    assert api_client.get(URL, params).status_code == 403


def test_handshake_refuses_when_no_token_configured(api_client, settings):
    settings.WHATSAPP_VERIFY_TOKEN = ""
    assert api_client.get(URL, {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}).status_code == 403


# ------------------------------- signature -------------------------------- #
def test_invalid_or_missing_signature_is_rejected_and_changes_nothing(wa_on, db, post_webhook):
    payload = message_payload(WA_ID, "help")
    assert post_webhook(payload, signature="sha256=" + "0" * 64).status_code == 403
    assert post_webhook(payload, signature="").status_code == 403
    assert post_webhook(payload, signature=sign(b"other body")).status_code == 403
    assert not IncomingWhatsAppMessage.objects.exists()


def test_signature_covers_exact_raw_bytes_not_reserialised_json(wa_on, db, post_webhook):
    body = b'{"object": "whatsapp_business_account",   "entry": []}'  # odd spacing
    assert post_webhook(None, raw=body).status_code == 200
    assert post_webhook(None, raw=body, signature=sign(json.dumps(json.loads(body)).encode())).status_code == 403


def test_oversized_body_rejected(wa_on, db, settings, post_webhook):
    settings.WHATSAPP_WEBHOOK_MAX_BYTES = 100
    assert post_webhook(None, raw=b"x" * 500).status_code == 413


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"object": "page"}', b'{"object":"whatsapp_business_account","entry":"x"}'])
def test_malformed_payloads_get_400(wa_on, db, post_webhook, raw):
    assert post_webhook(None, raw=raw).status_code == 400


def test_signed_webhook_when_disabled_is_acknowledged_but_ignored(db, post_webhook):
    r = post_webhook(message_payload(WA_ID, "help"))
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    assert not IncomingWhatsAppMessage.objects.exists()


def test_tolerates_missing_fields(wa_on, db, post_webhook):
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [{"id": "x"}, {}], "statuses": [{}]}}, {}, {"value": 5}]}, {}]}
    r = post_webhook(payload)
    assert r.status_code == 200 and r.json()["ignored"] == 3


# ---------------------------- status events -------------------------------- #
def test_status_webhook_updates_the_matching_notification(wa_on, approved_templates, student, consent_user, mock_post, post_webhook):
    consent_user(student)
    n = service.enqueue(user=student, template="payment_success", variables={"student_name": "A", "amount": "1", "plan_name": "P"}, key="s1")
    service.deliver(n.pk)
    assert post_webhook(status_payload("wamid.TEST1", "delivered")).status_code == 200
    n.refresh_from_db()
    assert n.status == "delivered"
    # Out of order + duplicate: no regression.
    post_webhook(status_payload("wamid.TEST1", "sent"))
    post_webhook(status_payload("wamid.TEST1", "delivered"))
    n.refresh_from_db()
    assert n.status == "delivered"
    post_webhook(status_payload("wamid.TEST1", "failed", [{"code": 131026}]))
    n.refresh_from_db()
    assert n.status == "delivered"


# ------------------------------- inbound ---------------------------------- #
def test_duplicate_incoming_message_is_processed_once(wa_on, db, post_webhook, django_capture_on_commit_callbacks):
    payload = message_payload(WA_ID, "help", message_id="wamid.DUP")
    with mock.patch("apps.notifications.tasks.process_incoming_whatsapp.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            first = post_webhook(payload).json()
        with django_capture_on_commit_callbacks(execute=True):
            second = post_webhook(payload).json()
    assert first["messages"] == 1 and second["messages"] == 0 and second["duplicates"] == 1
    assert IncomingWhatsAppMessage.objects.count() == 1
    assert delay.call_count == 1


def test_message_text_is_not_stored_only_the_command(wa_on, db, post_webhook):
    post_webhook(message_payload(WA_ID, "my passport number is X1234567 NEXT CLASS?"))
    row = IncomingWhatsAppMessage.objects.get()
    assert row.command == commands.UNKNOWN
    assert "X1234567" not in str(row.__dict__)


def test_unsupported_message_types_are_recorded_but_not_processed(wa_on, db, post_webhook):
    with mock.patch("apps.notifications.tasks.process_incoming_whatsapp.delay") as delay:
        post_webhook({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [{"from": WA_ID, "id": "wamid.IMG", "type": "image", "timestamp": "1"}]}}]}]})
    row = IncomingWhatsAppMessage.objects.get()
    assert row.processing_status == "ignored" and row.message_type == "image"
    delay.assert_not_called()


def test_unknown_sender_gets_link_instruction_once_and_no_data(wa_on, db, mock_post):
    msg = IncomingWhatsAppMessage.objects.create(provider_message_id="m1", sender_identifier="911111111111", message_type="text", command=commands.MY_PROGRESS)
    assert commands.process_incoming(msg.pk) == "processed"
    body = mock_post.call_args.kwargs["json"]["text"]["body"]
    assert "verify this number" in body
    # Second message from the same stranger: no reply (reflector protection).
    msg2 = IncomingWhatsAppMessage.objects.create(provider_message_id="m2", sender_identifier="911111111111", message_type="text", command=commands.HELP)
    assert commands.process_incoming(msg2.pk) == "ignored"
    assert mock_post.call_count == 1


def test_processing_same_message_twice_replies_once(wa_on, db, student, consent_user, mock_post):
    consent_user(student)
    msg = IncomingWhatsAppMessage.objects.create(provider_message_id="m1", sender_identifier=WA_ID, message_type="text", command=commands.HELP)
    commands.process_incoming(msg.pk)
    assert commands.process_incoming(msg.pk) == "skipped"
    assert mock_post.call_count == 1


def _ask(command, mock_post, wa_id=WA_ID, n=[0]):
    n[0] += 1
    msg = IncomingWhatsAppMessage.objects.create(provider_message_id=f"q{n[0]}", sender_identifier=wa_id, message_type="text", command=command)
    commands.process_incoming(msg.pk)
    return mock_post.call_args.kwargs["json"]["text"]["body"]


def test_help_and_unknown(wa_on, db, student, consent_user, mock_post):
    consent_user(student)
    assert "NEXT CLASS" in _ask(commands.HELP, mock_post)
    assert "did not understand" in _ask(commands.UNKNOWN, mock_post)
    assert "no assignments" in _ask(commands.MY_ASSIGNMENTS, mock_post).lower() or "not available" in _ask(commands.MY_ASSIGNMENTS, mock_post)


def test_stop_via_webhook_opts_out_immediately(wa_on, db, student, consent_user, post_webhook, mock_post):
    consent_user(student)
    queued = Notification.objects.create(user=student, kind="payment_success", channel="whatsapp", title="x", status="pending")
    post_webhook(message_payload(WA_ID, " Stop! "))
    prefs = NotificationPreference.objects.get(user=student)
    assert prefs.consent_status == ConsentStatus.OPTED_OUT and not prefs.whatsapp_enabled
    queued.refresh_from_db()
    assert queued.status == "cancelled"


def test_inactive_account_is_treated_as_unlinked(wa_on, db, student, consent_user, mock_post):
    consent_user(student)
    student.is_active = False
    student.save()
    assert "verify this number" in _ask(commands.MY_COURSES, mock_post)


def test_command_parser_is_exact_and_ignores_embedded_text():
    assert commands.parse_command("next class") == commands.NEXT_CLASS
    assert commands.parse_command("  Next   Class!! ") == commands.NEXT_CLASS
    assert commands.parse_command("STOP") == commands.STOP
    assert commands.parse_command("please stop everything") == commands.UNKNOWN
    assert commands.parse_command("my progress; DROP TABLE") == commands.UNKNOWN
    assert commands.parse_command("") == commands.UNKNOWN


# ------------------- data isolation (the important part) ------------------- #
def test_progress_and_quizzes_only_show_the_senders_own_data(
    wa_on, db, student, other_student, consent_user, mock_post, lesson, quiz, course, active_subscription
):
    from apps.quizzes.models import QuizAttempt
    from apps.videos.models import VideoProgress

    consent_user(student, "+919876543210")
    consent_user(other_student, "+919000000002")
    VideoProgress.objects.create(user=other_student, video=lesson.video, lesson=lesson, completed=True, completed_at=timezone.now())
    QuizAttempt.objects.create(quiz=quiz, user=other_student, submitted_at=timezone.now(), score=2, max_score=2, percentage=100, passed=True)

    assert "No completed lessons" in _ask(commands.MY_PROGRESS, mock_post)
    assert "No quiz attempts" in _ask(commands.MY_QUIZZES, mock_post)
    # The other student, from their own verified number, sees theirs.
    assert "1/1 lessons" in _ask(commands.MY_PROGRESS, mock_post, wa_id="919000000002")
    assert "Module 1 Quiz" in _ask(commands.MY_QUIZZES, mock_post, wa_id="919000000002")


def test_a_different_number_cannot_reach_a_students_account(wa_on, db, student, consent_user, mock_post):
    consent_user(student, "+919876543210")
    body = _ask(commands.MY_COURSES, mock_post, wa_id="919876543211")  # one digit off
    assert "verify this number" in body


def test_next_class_is_entitlement_gated(wa_on, db, student, consent_user, mock_post, course, active_subscription):
    from apps.live.models import LiveClass

    consent_user(student)
    live = LiveClass.objects.create(course=course, title="Art 21 Deep Dive", scheduled_start=timezone.now() + timedelta(days=1), meeting_url="https://zoom.example/j/secret")
    body = _ask(commands.NEXT_CLASS, mock_post)
    # Details and the signed-in page -- never the meeting link (a day ahead, the
    # join endpoint would refuse it too).
    assert "Art 21 Deep Dive" in body and "zoom.example" not in body
    assert body.rstrip().endswith("/live")

    active_subscription.status = "expired"
    active_subscription.save()
    from apps.subscriptions.services import invalidate_entitlement_cache

    invalidate_entitlement_cache(student)
    body = _ask(commands.NEXT_CLASS, mock_post)
    assert "zoom.example" not in body and "no upcoming" in body.lower()


def test_unpublished_class_is_never_revealed(wa_on, db, student, consent_user, mock_post, course, active_subscription):
    from apps.live.models import LiveClass

    consent_user(student)
    LiveClass.objects.create(course=course, title="Secret Draft", scheduled_start=timezone.now() + timedelta(days=1), meeting_url="https://zoom.example/x", is_published=False)
    assert "Secret Draft" not in _ask(commands.NEXT_CLASS, mock_post)


def test_instructor_only_sees_classes_they_host_and_no_student_data(wa_on, db, instructor, consent_user, mock_post, course):
    from apps.live.models import LiveClass

    consent_user(instructor, "+919000000003")
    LiveClass.objects.create(course=course, title="My Class", scheduled_start=timezone.now() + timedelta(hours=5), meeting_url="https://zoom.example/h")
    assert "My Class" in _ask(commands.NEXT_CLASS, mock_post, wa_id="919000000003")
    assert "student accounts" in _ask(commands.MY_PROGRESS, mock_post, wa_id="919000000003")


def test_admin_cannot_use_assistant_for_admin_actions(wa_on, db, admin_user, consent_user, mock_post):
    consent_user(admin_user, "+919000000004")
    assert "website" in _ask(commands.NEXT_CLASS, mock_post, wa_id="919000000004")
    assert "student accounts" in _ask(commands.PAYMENT_STATUS, mock_post, wa_id="919000000004")


def test_payment_status_shows_only_own_plan(wa_on, db, student, other_student, consent_user, mock_post, active_subscription):
    consent_user(other_student, "+919000000005")
    assert "no active subscription" in _ask(commands.PAYMENT_STATUS, mock_post, wa_id="919000000005").lower()
    consent_user(student)
    assert "Foundations" in _ask(commands.PAYMENT_STATUS, mock_post)


def test_next_class_never_sends_the_link_even_inside_the_join_window(
    wa_on, db, student, consent_user, mock_post, course, active_subscription, jwt_client
):
    """WhatsApp only points to LawSchool; the authorized student still joins there."""
    from apps.live.models import LiveClass

    consent_user(student)
    live = LiveClass.objects.create(
        course=course, title="Bail Clinic", scheduled_start=timezone.now() + timedelta(minutes=5),
        meeting_url="https://zoom.example/j/inside-window",
    )
    body = _ask(commands.NEXT_CLASS, mock_post)
    assert "Bail Clinic" in body and "inside-window" not in body
    joined = jwt_client(student).get(f"/api/v1/live-classes/{live.pk}/join/")
    assert joined.status_code == 200
    assert joined.data["meeting_url"] == "https://zoom.example/j/inside-window"


def test_instructor_is_pointed_to_the_teaching_page(wa_on, db, instructor, consent_user, mock_post, course):
    from apps.live.models import LiveClass

    consent_user(instructor, "+919000000003")
    LiveClass.objects.create(course=course, title="My Class", scheduled_start=timezone.now() + timedelta(hours=5), meeting_url="https://zoom.example/h")
    body = _ask(commands.NEXT_CLASS, mock_post, wa_id="919000000003")
    assert body.rstrip().endswith("/instructor/live") and "zoom.example" not in body
