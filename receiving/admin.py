from django.contrib import admin

from .models import (
    WarehouseLocation, GoodsReceiptNote, GoodsReceiptNoteItem,
    VendorInvoice, ThreeWayMatch, QualityInspection,
    QualityInspectionItem, PutawayTask,
)


class GoodsReceiptNoteItemInline(admin.TabularInline):
    model = GoodsReceiptNoteItem
    extra = 1


class QualityInspectionItemInline(admin.TabularInline):
    model = QualityInspectionItem
    extra = 1


@admin.register(WarehouseLocation)
class WarehouseLocationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'location_type', 'parent', 'capacity', 'current_quantity', 'is_active', 'tenant')
    list_filter = ('location_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(GoodsReceiptNote)
class GoodsReceiptNoteAdmin(admin.ModelAdmin):
    list_display = ('grn_number', 'purchase_order', 'status', 'received_date', 'received_by', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('grn_number',)
    inlines = [GoodsReceiptNoteItemInline]


@admin.register(VendorInvoice)
class VendorInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'vendor', 'purchase_order', 'invoice_date', 'total_amount', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('invoice_number',)


@admin.register(ThreeWayMatch)
class ThreeWayMatchAdmin(admin.ModelAdmin):
    list_display = ('match_number', 'purchase_order', 'grn', 'vendor_invoice', 'status', 'quantity_match', 'price_match', 'total_match', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('match_number',)


@admin.register(QualityInspection)
class QualityInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_number', 'grn', 'status', 'inspector', 'inspection_date', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('inspection_number',)
    inlines = [QualityInspectionItemInline]


@admin.register(PutawayTask)
class PutawayTaskAdmin(admin.ModelAdmin):
    list_display = ('task_number', 'grn', 'product', 'quantity', 'suggested_location', 'assigned_location', 'status', 'assigned_to', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('task_number',)
