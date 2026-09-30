"""Payment routes, mounted at ``/api/v1/payments/``."""

from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    # Student-facing
    path("orders/", views.CreateOrderView.as_view(), name="create-order"),
    path("verify/", views.VerifyPaymentView.as_view(), name="verify"),
    path("", views.MyPaymentsView.as_view(), name="my-payments"),
    # Provider -> server (no JWT; HMAC-verified)
    path("webhook/", views.PaymentWebhookView.as_view(), name="webhook"),
    # Admin
    path("all/", views.AdminPaymentListView.as_view(), name="admin-list"),
    path(
        "webhook-events/",
        views.AdminWebhookEventListView.as_view(),
        name="webhook-events",
    ),
]
