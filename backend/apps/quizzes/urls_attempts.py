"""Quiz attempt routes, mounted at ``/api/v1/quiz-attempts/``."""

from django.urls import path

from apps.quizzes import views

app_name = "quiz-attempts"

urlpatterns = [
    path("", views.MyAttemptListView.as_view(), name="list"),
    path("all/", views.QuizAttemptListView.as_view(), name="admin-list"),
    path("<uuid:pk>/", views.AttemptDetailView.as_view(), name="detail"),
    path("<uuid:pk>/submit/", views.SubmitAttemptView.as_view(), name="submit"),
]
