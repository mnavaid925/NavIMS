from django.contrib import admin
from .models import (
    StockTransfer, StockTransferItem,
    TransferApprovalRule, TransferApproval,
    TransferRoute,
)


class StockTransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 1


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_number', 'transfer_type', 'source_warehouse', 'destination_warehouse', 'status', 'priority', 'tenant')
    list_filter = ('status', 'transfer_type', 'priority', 'tenant')
    search_fields = ('transfer_number',)
    inlines = [StockTransferItemInline]


@admin.register(StockTransferItem)
class StockTransferItemAdmin(admin.ModelAdmin):
    list_display = ('transfer', 'product', 'quantity', 'received_quantity', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('transfer__transfer_number', 'product__name')


@admin.register(TransferApprovalRule)
class TransferApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_items', 'max_items', 'requires_approval', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name',)


@admin.register(TransferApproval)
class TransferApprovalAdmin(admin.ModelAdmin):
    list_display = ('transfer', 'approved_by', 'decision', 'created_at', 'tenant')
    list_filter = ('decision', 'tenant')
    search_fields = ('transfer__transfer_number',)


@admin.register(TransferRoute)
class TransferRouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_warehouse', 'destination_warehouse', 'transit_method', 'estimated_duration_hours', 'is_active', 'tenant')
    list_filter = ('transit_method', 'is_active', 'tenant')
    search_fields = ('name',)
