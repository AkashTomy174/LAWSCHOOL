"""Quiz routes, mounted at ``/api/v1/quizzes/``."""

from django.urls import path

from apps.quizzes import views

app_name = "quizzes"

urlpatterns = [
    path("", views.QuizListCreateView.as_view(), name="list"),
    # Authoring sub-resources are registered before the <uuid> detail pattern so
    # "questions"/"options"/"subjects"/"rules" are never mistaken for a quiz id.
    path("subjects/", views.SubjectListCreateView.as_view(), name="subject-list"),
    path(
        "subjects/<uuid:pk>/", views.SubjectDetailView.as_view(), name="subject-detail"
    ),
    path("questions/", views.QuestionListCreateView.as_view(), name="question-list"),
    path(
        "questions/<uuid:pk>/",
        views.QuestionDetailView.as_view(),
        name="question-detail",
    ),
    path("options/", views.OptionListCreateView.as_view(), name="option-list"),
    path("options/<uuid:pk>/", views.OptionDetailView.as_view(), name="option-detail"),
    path("rules/", views.QuizSectionRuleListCreateView.as_view(), name="rule-list"),
    path(
        "rules/<uuid:pk>/",
        views.QuizSectionRuleDetailView.as_view(),
        name="rule-detail",
    ),
    path("<uuid:pk>/", views.QuizDetailView.as_view(), name="detail"),
    path("<uuid:pk>/attempts/", views.StartAttemptView.as_view(), name="start-attempt"),
    path("<uuid:pk>/progress/", views.QuizProgressView.as_view(), name="progress"),
]
