from django.contrib import admin

from .models import Alert, NotificationDelivery, NotificationRule


class TenantScopedAdmin(admin.ModelAdmin):
    """Filter admin list by the admin user's tenant (superusers see all)."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            return qs.none()
        return qs.filter(tenant=tenant)


@admin.register(Alert)
class AlertAdmin(TenantScopedAdmin):
    list_display = (
        'alert_number', 'tenant', 'alert_type', 'severity',
        'status', 'title', 'triggered_at',
    )
    list_filter = ('alert_type', 'severity', 'status', 'tenant')
    search_fields = ('alert_number', 'title', 'message', 'dedup_key')
    date_hierarchy = 'triggered_at'
    readonly_fields = ('alert_number', 'dedup_key', 'triggered_at', 'updated_at')


@admin.register(NotificationRule)
class NotificationRuleAdmin(TenantScopedAdmin):
    list_display = ('code', 'tenant', 'name', 'alert_type', 'min_severity', 'is_active', 'updated_at')
    list_filter = ('alert_type', 'min_severity', 'is_active', 'tenant')
    search_fields = ('code', 'name', 'description')
    filter_horizontal = ('recipient_users',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(TenantScopedAdmin):
    list_display = ('id', 'tenant', 'alert', 'recipient', 'channel', 'status', 'sent_at')
    list_filter = ('channel', 'status', 'tenant')
    search_fields = ('alert__alert_number', 'recipient_email', 'error_message')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'sent_at')
