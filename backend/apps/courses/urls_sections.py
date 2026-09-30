"""Section routes, mounted at ``/api/v1/sections/``."""

from django.urls import path

from apps.courses import views

app_name = "sections"

urlpatterns = [
    path("", views.SectionListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", views.SectionDetailView.as_view(), name="detail"),
]
