from django.contrib import admin

from .models import ReportSnapshot


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


@admin.register(ReportSnapshot)
class ReportSnapshotAdmin(TenantScopedAdmin):
    list_display = ('report_number', 'title', 'report_type', 'tenant', 'generated_by', 'generated_at')
    list_filter = ('report_type', 'tenant', 'generated_at')
    search_fields = ('report_number', 'title', 'notes')
    readonly_fields = ('report_number', 'generated_at', 'created_at', 'updated_at')
