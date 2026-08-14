from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from cms.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email", "username")
    list_display = ("username", "email", "is_staff", "is_active", "id")
    search_fields = ("username", "email", "first_name", "last_name")
    readonly_fields = ("id", "last_login", "date_joined")
