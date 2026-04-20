from django.contrib import admin

from .models import (
    QCChecklist, QCChecklistItem,
    InspectionRoute, InspectionRouteRule,
    QuarantineRecord,
    DefectReport, DefectPhoto,
    ScrapWriteOff,
)


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


class QCChecklistItemInline(admin.TabularInline):
    model = QCChecklistItem
    extra = 0


@admin.register(QCChecklist)
class QCChecklistAdmin(TenantScopedAdmin):
    list_display = ('code', 'name', 'tenant', 'applies_to', 'is_mandatory', 'is_active', 'created_at')
    list_filter = ('applies_to', 'is_mandatory', 'is_active', 'tenant')
    search_fields = ('code', 'name', 'description')
    inlines = [QCChecklistItemInline]


@admin.register(QCChecklistItem)
class QCChecklistItemAdmin(TenantScopedAdmin):
    list_display = ('checklist', 'sequence', 'check_name', 'check_type', 'is_critical')
    list_filter = ('check_type', 'is_critical', 'tenant')
    search_fields = ('check_name',)


class InspectionRouteRuleInline(admin.TabularInline):
    model = InspectionRouteRule
    extra = 0


@admin.register(InspectionRoute)
class InspectionRouteAdmin(TenantScopedAdmin):
    list_display = ('code', 'name', 'tenant', 'source_warehouse', 'qc_zone', 'priority', 'is_active')
    list_filter = ('is_active', 'source_warehouse', 'tenant')
    search_fields = ('code', 'name')
    inlines = [InspectionRouteRuleInline]


@admin.register(InspectionRouteRule)
class InspectionRouteRuleAdmin(TenantScopedAdmin):
    list_display = ('route', 'applies_to', 'product', 'vendor', 'category', 'checklist')
    list_filter = ('applies_to', 'tenant')


@admin.register(QuarantineRecord)
class QuarantineRecordAdmin(TenantScopedAdmin):
    list_display = ('quarantine_number', 'tenant', 'product', 'warehouse', 'zone', 'quantity', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'warehouse', 'tenant')
    search_fields = ('quarantine_number', 'product__sku', 'product__name', 'reason_notes')
    date_hierarchy = 'created_at'


class DefectPhotoInline(admin.TabularInline):
    model = DefectPhoto
    extra = 0
    readonly_fields = ('uploaded_at',)


@admin.register(DefectReport)
class DefectReportAdmin(TenantScopedAdmin):
    list_display = ('defect_number', 'tenant', 'product', 'warehouse', 'defect_type', 'severity', 'source', 'status', 'created_at')
    list_filter = ('status', 'severity', 'defect_type', 'source', 'warehouse', 'tenant')
    search_fields = ('defect_number', 'product__sku', 'product__name', 'description')
    date_hierarchy = 'created_at'
    inlines = [DefectPhotoInline]


@admin.register(DefectPhoto)
class DefectPhotoAdmin(TenantScopedAdmin):
    list_display = ('defect_report', 'caption', 'uploaded_at', 'tenant')
    list_filter = ('tenant',)


@admin.register(ScrapWriteOff)
class ScrapWriteOffAdmin(TenantScopedAdmin):
    list_display = ('scrap_number', 'tenant', 'product', 'warehouse', 'quantity', 'total_value', 'approval_status', 'posted_at')
    list_filter = ('approval_status', 'warehouse', 'tenant')
    search_fields = ('scrap_number', 'product__sku', 'product__name', 'reason')
    date_hierarchy = 'created_at'
    readonly_fields = ('total_value', 'posted_at', 'stock_adjustment')
