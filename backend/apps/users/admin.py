"""User admin, customised for search/filtering and safe role editing."""

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.users.models import LastAdminError, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Email-first admin because there is no ``username`` column."""

    ordering = ("-date_joined",)
    list_display = (
        "email",
        "name",
        "role",
        "is_active",
        "is_email_verified",
        "date_joined",
    )
    list_filter = ("role", "is_active", "is_email_verified", "is_staff", "date_joined")
    search_fields = ("email", "name", "phone")
    readonly_fields = ("id", "date_joined", "last_login", "updated_at", "password")
    date_hierarchy = "date_joined"
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Identity"), {"fields": ("name", "phone", "role", "avatar")}),
        (_("Profile"), {"fields": ("bio", "city", "state", "qualification")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_email_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "role",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        # Avoids an extra query per row when groups are rendered.
        return (
            super().get_queryset(request).prefetch_related("groups", "user_permissions")
        )

    # The model refuses to drop the last administrator; surface that as a message
    # instead of a 500 page.
    def save_model(self, request, obj, form, change):
        try:
            super().save_model(request, obj, form, change)
        except LastAdminError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except LastAdminError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)

    def delete_queryset(self, request, queryset):
        # QuerySet.delete() skips Model.delete(), so check each row explicitly.
        for user in queryset:
            try:
                user.delete()
            except LastAdminError as exc:
                self.message_user(
                    request, f"{user.email}: {exc}", level=messages.ERROR
                )
