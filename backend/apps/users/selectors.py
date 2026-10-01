"""User-facing selectors (complex reads live here, not in views)."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.users.models import User


def user_list(
    *, role: str | None = None, is_active: bool | None = None, search: str | None = None
) -> QuerySet[User]:
    """Admin listing queryset.

    Only the columns the admin table renders are selected, and no per-row
    related lookups exist here, so pagination keeps this to one query.
    """
    queryset = User.objects.all()
    if role:
        queryset = queryset.filter(role=role)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    if search:
        # Q-combine on the *same* queryset; OR-ing two querysets would drop the
        # role/is_active filters applied above.
        queryset = queryset.filter(Q(email__icontains=search) | Q(name__icontains=search))
    return queryset.order_by("-date_joined")


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email=email.strip().lower()).first()
