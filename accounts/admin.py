from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model()

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Show email first; keep username read-only so it's obvious it mirrors email
    readonly_fields = ("username",)

    def save_model(self, request, obj, form, change):
        if obj.email:
            obj.username = obj.email.lower().strip()
        super().save_model(request, obj, form, change)
