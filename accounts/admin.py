from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'role',
        'failed_attempts', 'account_locked', 'lock_until', 'is_active'
    )
    list_filter = ('role', 'account_locked', 'email_verified', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    actions = ['unlock_selected_accounts']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Account Lockout & Security Audit', {
            'fields': (
                'role', 'phone', 'failed_attempts', 'account_locked', 'lock_until',
                'failed_login_attempts', 'account_locked_until', 'last_failed_login',
                'last_successful_login', 'last_login_ip', 'last_login_user_agent'
            )
        }),
    )

    @admin.action(description="Unlock selected locked accounts")
    def unlock_selected_accounts(self, request, queryset):
        count = 0
        for user in queryset:
            user.unlock_account()
            count += 1
        self.message_user(request, f"Successfully unlocked {count} account(s).")
