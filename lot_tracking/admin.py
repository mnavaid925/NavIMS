from django.contrib import admin
from .models import LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog


@admin.register(LotBatch)
class LotBatchAdmin(admin.ModelAdmin):
    list_display = ('lot_number', 'product', 'warehouse', 'quantity', 'available_quantity', 'status', 'expiry_date', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('lot_number', 'product__name', 'supplier_batch_number')


@admin.register(SerialNumber)
class SerialNumberAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'product', 'lot', 'warehouse', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('serial_number', 'product__name')


@admin.register(ExpiryAlert)
class ExpiryAlertAdmin(admin.ModelAdmin):
    list_display = ('lot', 'alert_type', 'alert_date', 'days_before_expiry', 'is_acknowledged', 'tenant')
    list_filter = ('alert_type', 'is_acknowledged', 'tenant')
    search_fields = ('lot__lot_number',)


@admin.register(TraceabilityLog)
class TraceabilityLogAdmin(admin.ModelAdmin):
    list_display = ('log_number', 'lot', 'serial_number', 'event_type', 'quantity', 'reference_type', 'tenant')
    list_filter = ('event_type', 'tenant')
    search_fields = ('log_number', 'lot__lot_number', 'serial_number__serial_number', 'reference_number')
