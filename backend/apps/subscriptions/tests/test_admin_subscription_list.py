"""Admin subscription list: response contract the admin UI depends on, and access.

Regression: the admin page read ``data.results`` while the client unwrapped the
envelope to a bare array, so the table was always empty.  These pin the server
side of that contract.
"""

from __future__ import annotations

import pytest

from conftest import make_subscription

URL = "/api/v1/subscriptions/"


def test_admin_gets_a_paginated_envelope(auth_client, admin_user, student, plan):
    make_subscription(student, plan, payment_reference="pay_1")
    body = auth_client(admin_user).get(URL).json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["user_email"] == student.email
    assert row["plan"]["name"] == plan.name
    assert row["status"] == "active"
    assert row["payment_reference"] == "pay_1"


def test_status_filter_counts_active_only(auth_client, admin_user, student, other_student, plan):
    make_subscription(student, plan, payment_reference="a")
    make_subscription(other_student, plan, status="expired", payment_reference="b")
    body = auth_client(admin_user).get(URL, {"status": "active", "page_size": 1}).json()
    assert body["count"] == 1


@pytest.mark.parametrize("who", ["student", "instructor"])
def test_non_admins_are_refused(request, auth_client, who, plan):
    response = auth_client(request.getfixturevalue(who)).get(URL)
    assert response.status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401
