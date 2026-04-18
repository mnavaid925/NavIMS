from django.contrib import admin

from .models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
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


@admin.register(LabelTemplate)
class LabelTemplateAdmin(TenantScopedAdmin):
    list_display = ('code', 'name', 'tenant', 'label_type', 'symbology', 'paper_size', 'is_active')
    list_filter = ('label_type', 'symbology', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(LabelPrintJob)
class LabelPrintJobAdmin(TenantScopedAdmin):
    list_display = ('job_number', 'tenant', 'template', 'target_type', 'quantity', 'status', 'printed_at')
    list_filter = ('status', 'target_type', 'tenant')
    search_fields = ('job_number', 'target_display')


@admin.register(ScannerDevice)
class ScannerDeviceAdmin(TenantScopedAdmin):
    list_display = ('device_code', 'name', 'tenant', 'device_type', 'status', 'assigned_to', 'assigned_warehouse', 'last_seen_at')
    list_filter = ('device_type', 'status', 'tenant')
    search_fields = ('device_code', 'name', 'manufacturer', 'model_number')
    readonly_fields = ('api_token', 'last_seen_at')


@admin.register(ScanEvent)
class ScanEventAdmin(TenantScopedAdmin):
    list_display = ('scanned_at', 'tenant', 'device', 'user', 'scan_type', 'barcode_value', 'status')
    list_filter = ('scan_type', 'status', 'resolved_object_type', 'tenant')
    search_fields = ('barcode_value', 'resolved_display')
    date_hierarchy = 'scanned_at'


@admin.register(RFIDTag)
class RFIDTagAdmin(TenantScopedAdmin):
    list_display = ('epc_code', 'tenant', 'tag_type', 'frequency_band', 'linked_object_type', 'status', 'read_count', 'last_read_at')
    list_filter = ('tag_type', 'frequency_band', 'status', 'linked_object_type', 'tenant')
    search_fields = ('epc_code', 'linked_display')


@admin.register(RFIDReader)
class RFIDReaderAdmin(TenantScopedAdmin):
    list_display = ('reader_code', 'name', 'tenant', 'reader_type', 'warehouse', 'zone', 'status', 'last_seen_at')
    list_filter = ('reader_type', 'status', 'frequency_band', 'tenant')
    search_fields = ('reader_code', 'name', 'ip_address')


@admin.register(RFIDReadEvent)
class RFIDReadEventAdmin(TenantScopedAdmin):
    list_display = ('read_at', 'tenant', 'tag', 'reader', 'direction', 'signal_strength_dbm')
    list_filter = ('direction', 'tenant')
    search_fields = ('tag__epc_code', 'reader__reader_code')
    date_hierarchy = 'read_at'


class BatchScanItemInline(admin.TabularInline):
    model = BatchScanItem
    extra = 0


@admin.register(BatchScanSession)
class BatchScanSessionAdmin(TenantScopedAdmin):
    list_display = ('session_number', 'tenant', 'purpose', 'user', 'warehouse', 'status', 'total_items_scanned', 'started_at')
    list_filter = ('purpose', 'status', 'tenant')
    search_fields = ('session_number', 'notes')
    inlines = [BatchScanItemInline]


@admin.register(BatchScanItem)
class BatchScanItemAdmin(TenantScopedAdmin):
    list_display = ('scanned_at', 'tenant', 'session', 'scanned_value', 'resolution_type', 'quantity', 'is_resolved')
    list_filter = ('resolution_type', 'is_resolved', 'tenant')
    search_fields = ('scanned_value', 'resolved_display')
