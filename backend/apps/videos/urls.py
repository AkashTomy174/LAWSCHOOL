"""Video routes, mounted at ``/api/v1/videos/``."""

from django.urls import path

from apps.videos import views

app_name = "videos"

urlpatterns = [
    path("", views.VideoListView.as_view(), name="list"),
    path("register/", views.VideoRegisterView.as_view(), name="register"),
    path("upload-url/", views.DirectUploadURLView.as_view(), name="upload-url"),
    path(
        "lessons/<uuid:lesson_id>/playback/",
        views.LessonPlaybackView.as_view(),
        name="lesson-playback",
    ),
    path("<uuid:uid>/", views.VideoDetailView.as_view(), name="detail"),
    path("<uuid:uid>/playback/", views.VideoPlaybackView.as_view(), name="playback"),
    path(
        "<uuid:uid>/progress/", views.VideoProgressUpdateView.as_view(), name="progress"
    ),
    path("<uuid:uid>/sync/", views.VideoSyncView.as_view(), name="sync"),
]
