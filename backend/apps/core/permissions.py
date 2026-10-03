"""Reusable DRF permission classes.

The guiding rule for this project: *frontend route guards are UX, not security*.
Every object-level check therefore has a server-side twin here, and views never
inline role comparisons.
"""

from __future__ import annotations

from rest_framework import permissions

from apps.core.constants import UserRole


def is_admin(request) -> bool:
    """True when the request's user has administrator rights.

    Centralises what would otherwise be an ``is_staff or role == ADMIN or
    is_superuser`` comparison copy-pasted into every view.  Being a single
    definition means an authorization rule cannot drift between endpoints.

    Note the ``is_authenticated`` guard: ``AnonymousUser`` has no ``role``
    attribute, so calling this during schema generation (drf-spectacular resolves
    ``get_queryset()`` with an anonymous user) would otherwise raise
    ``AttributeError`` and strip the endpoint's serializer from the OpenAPI
    document.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    return bool(
        getattr(user, "role", None) == UserRole.ADMIN
        or user.is_staff
        or user.is_superuser
    )


def client_ip(request) -> str | None:
    """The caller's IP, trusting only ``NUM_PROXIES`` hops of X-Forwarded-For.

    Reuses DRF's throttle identity so audit logs and rate limits agree; reading
    the first X-Forwarded-For entry directly would let a client forge it.
    """
    from rest_framework.throttling import BaseThrottle

    return BaseThrottle().get_ident(request) or None


def is_schema_generation(view) -> bool:
    """True while drf-spectacular is building the OpenAPI document.

    Schema generation resolves ``get_queryset()`` with an ``AnonymousUser``.  Any
    queryset that filters on the caller's identity therefore raises
    ("AnonymousUser is not a valid UUID"), and spectacular falls back to an
    undocumented endpoint.

    Views that scope a queryset by the current user should short-circuit:

    .. code-block:: python

        def get_queryset(self):
            if is_schema_generation(self):
                return MyModel.objects.none()
            return MyModel.objects.filter(user=self.request.user)

    Returning ``none()`` still lets spectacular infer the model and serializer, so
    the endpoint is documented correctly -- it is simply not executed.  This is the
    conditional drf-spectacular documents for exactly this situation.
    """
    return bool(getattr(view, "swagger_fake_view", False))


class IsAdminRole(permissions.BasePermission):
    """Platform administrators (``role == ADMIN`` or Django ``is_staff``)."""

    message = "This action is available to administrators only."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.role == UserRole.ADMIN or user.is_staff or user.is_superuser


class IsInstructorOrAdmin(permissions.BasePermission):
    """Content authoring surface shared by instructors and admins."""

    message = "This action requires instructor or administrator rights."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.role in {UserRole.INSTRUCTOR, UserRole.ADMIN}
            or user.is_staff
            or user.is_superuser
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """Object-level: the row's ``user``/``owner``/``author`` must be the caller.

    The attribute name is resolved dynamically so the same class guards
    subscriptions, quiz attempts, progress rows and instructor-owned courses.
    """

    message = "You do not have access to this object."
    owner_fields = ("user", "owner", "author", "instructor", "student")

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == UserRole.ADMIN or user.is_staff:
            return True
        for field in self.owner_fields:
            owner = getattr(obj, field, None)
            if owner is not None and getattr(owner, "pk", None) == user.pk:
                return True
        return False


class IsCourseOwnerOrAdmin(permissions.BasePermission):
    """Instructor must own the course; admins bypass the ownership check.

    ``IsInstructorOrAdmin`` only proves *what the caller is*, not *what they may
    touch*.  Without an ownership check any instructor could author content into
    another instructor's course -- a privilege-escalation hole that the object
    permissions here close.

    Accepts any object from which a course can be reached: a ``Course``, a
    ``Section``, a ``Lesson``, a ``Quiz``, a ``Question``, an ``Option``, or a
    plain course-like object exposing ``instructor_id``.
    """

    message = "You can only manage content in courses you own."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.role in {UserRole.INSTRUCTOR, UserRole.ADMIN}
            or user.is_staff
            or user.is_superuser
        )

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if user.role == UserRole.ADMIN or user.is_staff or user.is_superuser:
            return True
        course = _course_for(obj)
        if course is None:
            return False
        return course.instructor_id == user.pk


def _course_for(obj):
    """Resolve the owning course from any content object, or None."""
    if obj is None:
        return None
    # A Course (or anything course-shaped) exposes instructor_id directly.
    if hasattr(obj, "instructor_id"):
        return obj
    for attribute in ("course", "section", "quiz", "question", "lesson"):
        related = getattr(obj, attribute, None)
        if related is None:
            continue
        resolved = _course_for(related)
        if resolved is not None:
            return resolved
    return None
