"""Quiz API views: authoring, attempt lifecycle, results and review."""

from __future__ import annotations

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.exceptions import ConflictError
from apps.core.network import client_ip
from apps.core.permissions import (
    IsCourseOwnerOrAdmin,
    IsInstructorOrAdmin,
    is_admin,
    is_schema_generation,
)
from apps.quizzes import services
from apps.quizzes.models import (
    Option,
    Question,
    Quiz,
    QuizAttempt,
    QuizFixedQuestion,
    QuizSectionRule,
    Subject,
)
from apps.quizzes.serializers import (
    AttemptQuestionSerializer,
    OptionWriteSerializer,
    QuestionBankSerializer,
    QuizAttemptSerializer,
    QuizAttemptSummarySerializer,
    QuizDetailSerializer,
    QuizFixedQuestionSerializer,
    QuizListSerializer,
    QuizSectionRuleSerializer,
    QuizWriteSerializer,
    SubjectSerializer,
    SubmitAttemptSerializer,
)


class CanManageQuestionBank(BasePermission):
    """Admins, instructors, or users granted ``manage_question_bank``.

    The question bank is shared infrastructure reused across many courses'
    quizzes.  Anyone allowed in can read and add; changing or deleting an
    existing question is limited to admins and its creator
    (see ``_can_change_question``).
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            is_admin(request)
            or getattr(user, "role", None) == "instructor"
            or user.has_perm("quizzes.manage_question_bank")
        )


class ProtectedDeleteMixin:
    """Turn a PROTECT foreign key into a 409 instead of an unhandled 500."""

    protected_message = "This item is in use and cannot be deleted."

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ConflictError(
                {"detail": self.protected_message}, code="protected_resource"
            )


def _can_change_question(request, question: Question) -> bool:
    return is_admin(request) or question.created_by_id == request.user.pk


# --------------------------------------------------------------------------- #
# Authoring (instructor / admin)
# --------------------------------------------------------------------------- #
class QuizListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/quizzes/?course=<slug> · POST (course owner/admin).

    ``IsCourseOwnerOrAdmin`` closes the hole where any instructor could author a
    quiz into another instructor's course -- the role check alone is not enough.
    """

    permission_classes = [IsCourseOwnerOrAdmin]
    pagination_class = None

    def get_serializer_class(self):
        return (
            QuizWriteSerializer if self.request.method == "POST" else QuizListSerializer
        )

    def get_queryset(self):
        queryset = Quiz.objects.select_related("course", "lesson").order_by(
            "-created_at"
        )
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(course__slug=course_slug)
        if not is_admin(self.request):
            queryset = queryset.filter(course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        self.check_object_permissions(self.request, serializer.validated_data["course"])
        serializer.save()


class QuizDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET (student-safe) · PATCH/DELETE (instructor/admin) a quiz.

    The read serializer is chosen by role: students get questions with no answer
    key, staff get the admin shape.
    """

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in {"PATCH", "PUT", "DELETE"}:
            return [IsCourseOwnerOrAdmin()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return QuizWriteSerializer
        return QuizDetailSerializer

    def get_queryset(self):
        queryset = Quiz.objects.select_related("course", "lesson").prefetch_related(
            "section_rules__subject"
        )
        if self.request.method in {"PATCH", "PUT", "DELETE"}:
            if not is_admin(self.request):
                queryset = queryset.filter(course__instructor=self.request.user)
        else:
            # Students only ever see published quizzes on published courses.
            queryset = queryset.filter(is_published=True, course__status="published")
        return queryset

    def perform_update(self, serializer):
        # Moving a quiz needs ownership of the destination course too.
        if "course" in serializer.validated_data:
            self.check_object_permissions(
                self.request, serializer.validated_data["course"]
            )
        serializer.save()


class SubjectListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/quizzes/subjects/ -- the independent exam taxonomy."""

    serializer_class = SubjectSerializer
    permission_classes = [CanManageQuestionBank]
    pagination_class = None
    queryset = Subject.objects.all()


class SubjectDetailView(ProtectedDeleteMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/quizzes/subjects/<uuid>/."""

    protected_message = "This subject is used by a quiz rule and cannot be deleted."

    serializer_class = SubjectSerializer
    permission_classes = [CanManageQuestionBank]
    queryset = Subject.objects.all()


class QuestionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/quizzes/questions/?subject=<uuid> -- the shared question bank.

    Not course/quiz-scoped: a question can be tagged under multiple subjects
    and sampled into any quiz whose rules reference those subjects.
    """

    serializer_class = QuestionBankSerializer
    permission_classes = [CanManageQuestionBank]

    def get_queryset(self):
        queryset = Question.objects.prefetch_related(
            "options", "subjects"
        ).order_by("-created_at")
        params = self.request.query_params
        if params.get("subject"):
            queryset = queryset.filter(subjects=params["subject"])
        if params.get("search"):
            queryset = queryset.filter(text__icontains=params["search"])
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class QuestionDetailView(ProtectedDeleteMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/quizzes/questions/<uuid>/."""

    protected_message = (
        "This question is pinned in a quiz or used in an attempt and cannot be "
        "deleted. Deactivate it instead."
    )

    serializer_class = QuestionBankSerializer
    permission_classes = [CanManageQuestionBank]
    queryset = Question.objects.prefetch_related("options", "subjects")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in SAFE_METHODS and not _can_change_question(request, obj):
            self.permission_denied(request, message="You can only change your own questions.")


class QuizSectionRuleListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/quizzes/rules/?quiz=<uuid> -- per-subject exam composition."""

    serializer_class = QuizSectionRuleSerializer
    permission_classes = [IsCourseOwnerOrAdmin]
    pagination_class = None

    def get_queryset(self):
        queryset = QuizSectionRule.objects.select_related("quiz", "subject").order_by(
            "quiz", "ordering"
        )
        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        if not is_admin(self.request):
            queryset = queryset.filter(quiz__course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        self.check_object_permissions(
            self.request, serializer.validated_data["quiz"].course
        )
        serializer.save()


class QuizSectionRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/quizzes/rules/<uuid>/."""

    serializer_class = QuizSectionRuleSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = QuizSectionRule.objects.select_related("quiz", "subject")
        if not is_admin(self.request):
            queryset = queryset.filter(quiz__course__instructor=self.request.user)
        return queryset

    def perform_update(self, serializer):
        # Moving a rule needs ownership of the destination quiz's course too.
        if "quiz" in serializer.validated_data:
            self.check_object_permissions(
                self.request, serializer.validated_data["quiz"].course
            )
        serializer.save()


class QuizFixedQuestionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/quizzes/fixed-questions/?quiz=<uuid> -- hand-picked questions."""

    serializer_class = QuizFixedQuestionSerializer
    permission_classes = [IsCourseOwnerOrAdmin]
    pagination_class = None

    def get_queryset(self):
        queryset = QuizFixedQuestion.objects.select_related("quiz", "question")
        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        if not is_admin(self.request):
            queryset = queryset.filter(quiz__course__instructor=self.request.user)
        return queryset

    def perform_create(self, serializer):
        self.check_object_permissions(
            self.request, serializer.validated_data["quiz"].course
        )
        serializer.save()


class QuizFixedQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/quizzes/fixed-questions/<uuid>/."""

    serializer_class = QuizFixedQuestionSerializer
    permission_classes = [IsCourseOwnerOrAdmin]

    def get_queryset(self):
        queryset = QuizFixedQuestion.objects.select_related("quiz", "question")
        if not is_admin(self.request):
            queryset = queryset.filter(quiz__course__instructor=self.request.user)
        return queryset


class QuizPoolPreviewView(APIView):
    """GET /api/v1/quizzes/<uuid>/preview-pool/ -- requested vs available per rule."""

    permission_classes = [IsCourseOwnerOrAdmin]

    def get(self, request, pk):
        quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=pk)
        self.check_object_permissions(request, quiz.course)
        rules = [
            {
                "subject": rule.subject.name,
                "requested": rule.question_count,
                "available": Question.objects.filter(
                    subjects=rule.subject, is_active=True
                ).count(),
            }
            for rule in quiz.section_rules.select_related("subject")
        ]
        return Response(
            {
                "rules": rules,
                "fixed": quiz.fixed_questions.count(),
                "total_questions": quiz.question_count,
                "total_marks": quiz.total_marks,
            }
        )


class OptionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/quizzes/options/?question=<uuid>.

    Options belong to a bank question, not a course, so this follows the same
    bank-wide permission as ``QuestionListCreateView``.
    """

    serializer_class = OptionWriteSerializer
    permission_classes = [CanManageQuestionBank]
    pagination_class = None

    def get_queryset(self):
        queryset = Option.objects.select_related("question").order_by("ordering")
        question_id = self.request.query_params.get("question")
        if question_id:
            queryset = queryset.filter(question_id=question_id)
        return queryset

    def perform_create(self, serializer):
        question = serializer.validated_data["question"]
        if not _can_change_question(self.request, question):
            self.permission_denied(
                self.request, message="You can only change your own questions."
            )
        serializer.save()


class OptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/quizzes/options/<uuid>/."""

    serializer_class = OptionWriteSerializer
    permission_classes = [CanManageQuestionBank]
    queryset = Option.objects.select_related("question")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in SAFE_METHODS and not _can_change_question(
            request, obj.question
        ):
            self.permission_denied(
                request, message="You can only change your own questions."
            )


# --------------------------------------------------------------------------- #
# Student attempt flow
# --------------------------------------------------------------------------- #
class StartAttemptView(APIView):
    """POST /api/v1/quizzes/<uuid>/attempts/ -- open (or resume) an attempt."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: QuizAttemptSerializer})
    def post(self, request, pk):
        quiz = get_object_or_404(
            Quiz.objects.select_related("course").filter(is_published=True), pk=pk
        )
        attempt = services.start_attempt(
            user=request.user, quiz=quiz, ip_address=client_ip(request)
        )
        quiz_payload = QuizDetailSerializer(quiz).data
        attempt_questions = attempt.attempt_questions.select_related(
            "question"
        ).prefetch_related("question__options").order_by("ordering")
        quiz_payload["questions"] = AttemptQuestionSerializer(
            attempt_questions, many=True
        ).data
        return Response(
            {
                "attempt": QuizAttemptSerializer(attempt).data,
                "quiz": quiz_payload,
                "attempts_remaining": services.attempts_remaining(request.user, quiz),
            },
            status=status.HTTP_201_CREATED,
        )


class SubmitAttemptView(APIView):
    """POST /api/v1/quiz-attempts/<uuid>/submit/ -- grade and store the attempt."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SubmitAttemptSerializer, responses={200: QuizAttemptSerializer}
    )
    def post(self, request, pk):
        attempt = get_object_or_404(
            QuizAttempt.objects.select_related("quiz", "user"), pk=pk
        )

        # A student may only submit their own attempt.
        if attempt.user_id != request.user.pk:
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "This attempt does not belong to you.",
                        "details": None,
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SubmitAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attempt = services.submit_attempt(
            attempt=attempt,
            answers=serializer.validated_data["answers"],
            duration_seconds=serializer.validated_data.get("duration_seconds", 0),
        )

        # Derived leaderboard refresh (never blocks correctness of the score).
        try:
            from apps.leaderboard.models import refresh_user_leaderboard

            refresh_user_leaderboard(request.user)
        except Exception:  # pragma: no cover
            pass

        return Response(
            {
                "attempt": QuizAttemptSerializer(attempt).data,
                "review": services.attempt_review(attempt),
            }
        )


class MyAttemptListView(generics.ListAPIView):
    """GET /api/v1/quiz-attempts/ -- the caller's attempt history (paginated)."""

    serializer_class = QuizAttemptSummarySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # See apps.core.permissions.is_schema_generation: an AnonymousUser cannot be
        # used as a UUID filter while the OpenAPI document is being built.
        if is_schema_generation(self):
            return QuizAttempt.objects.none()
        queryset = (
            QuizAttempt.objects.filter(
                user=self.request.user, submitted_at__isnull=False
            )
            .select_related("quiz", "quiz__course")
            .order_by("-submitted_at")
        )
        quiz_id = self.request.query_params.get("quiz")
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        course_slug = self.request.query_params.get("course")
        if course_slug:
            queryset = queryset.filter(quiz__course__slug=course_slug)
        return queryset


class AttemptDetailView(APIView):
    """GET /api/v1/quiz-attempts/<uuid>/ -- one attempt plus its review."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attempt = get_object_or_404(
            QuizAttempt.objects.select_related("quiz", "quiz__course").prefetch_related(
                "answers__question", "answers__selected_option"
            ),
            pk=pk,
        )
        is_owner = attempt.user_id == request.user.pk
        # Instructors may only see attempts on quizzes in courses they own.
        is_staff = is_admin(request) or (
            getattr(request.user, "role", None) == "instructor"
            and attempt.quiz.course.instructor_id == request.user.pk
        )
        if not (is_owner or is_staff):
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "You do not have access to this attempt.",
                        "details": None,
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = {"attempt": QuizAttemptSerializer(attempt).data}
        # The review reveals correct answers, so it is only returned once the
        # attempt is graded and only to its owner/staff.
        if attempt.submitted_at:
            payload["review"] = services.attempt_review(attempt)
        return Response(payload)


class QuizAttemptListView(generics.ListAPIView):
    """GET /api/v1/quiz-attempts/all/ -- admin listing with filters."""

    serializer_class = QuizAttemptSummarySerializer
    permission_classes = [IsInstructorOrAdmin]

    def get_queryset(self):
        queryset = QuizAttempt.objects.select_related("quiz", "user").order_by(
            "-started_at"
        )
        params = self.request.query_params
        if params.get("quiz"):
            queryset = queryset.filter(quiz_id=params["quiz"])
        if params.get("user"):
            queryset = queryset.filter(user_id=params["user"])
        if not is_admin(self.request):
            queryset = queryset.filter(quiz__course__instructor=self.request.user)
        return queryset


class QuizProgressView(APIView):
    """GET /api/v1/quizzes/<uuid>/progress/ -- the caller's standing on one quiz.

    Lets the UI show "2 of 3 attempts used, best score 8/10" without fetching all
    attempts.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        quiz = get_object_or_404(
            Quiz, pk=pk, is_published=True, course__status="published"
        )
        attempts = QuizAttempt.objects.filter(
            user=request.user, quiz=quiz, submitted_at__isnull=False
        )
        best = attempts.order_by("-score", "-percentage").first()
        # An unsubmitted attempt still inside its time limit: starting again
        # resumes it, so the UI can say "Resume" instead of "Start".
        in_progress = (
            QuizAttempt.objects.filter(
                user=request.user, quiz=quiz, submitted_at__isnull=True
            )
            .select_related("quiz")
            .order_by("-attempt_number")
            .first()
        )
        if in_progress is not None and services.is_past_time_limit(in_progress):
            in_progress = None
        return Response(
            {
                "quiz": {"id": str(quiz.id), "title": quiz.title},
                "in_progress_attempt": (
                    {"id": str(in_progress.id), "started_at": in_progress.started_at}
                    if in_progress
                    else None
                ),
                "attempts_used": attempts.count(),
                "attempts_allowed": quiz.max_attempts,
                "attempts_remaining": services.attempts_remaining(request.user, quiz),
                "best_attempt": (
                    QuizAttemptSummarySerializer(best).data if best else None
                ),
            }
        )
