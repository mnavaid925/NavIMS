from django.contrib import admin
from .models import (
    StockLevel, StockAdjustment, StockStatus, StockStatusTransition,
    ValuationConfig, InventoryValuation, ValuationEntry, InventoryReservation,
)


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'on_hand', 'allocated', 'on_order', 'tenant')
    list_filter = ('warehouse', 'tenant')
    search_fields = ('product__sku', 'product__name')


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'stock_level', 'adjustment_type', 'quantity', 'reason', 'tenant')
    list_filter = ('adjustment_type', 'reason', 'tenant')
    search_fields = ('adjustment_number',)


@admin.register(StockStatus)
class StockStatusAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'status', 'quantity', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('product__sku', 'product__name')


@admin.register(StockStatusTransition)
class StockStatusTransitionAdmin(admin.ModelAdmin):
    list_display = ('transition_number', 'product', 'from_status', 'to_status', 'quantity', 'tenant')
    list_filter = ('from_status', 'to_status', 'tenant')
    search_fields = ('transition_number',)


@admin.register(ValuationConfig)
class ValuationConfigAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'method', 'auto_recalculate', 'last_calculated_at')
    list_filter = ('method',)


@admin.register(InventoryValuation)
class InventoryValuationAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'valuation_date', 'method', 'total_quantity', 'unit_cost', 'total_value', 'tenant')
    list_filter = ('method', 'tenant')
    search_fields = ('product__sku',)


@admin.register(ValuationEntry)
class ValuationEntryAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'entry_date', 'quantity', 'remaining_quantity', 'unit_cost', 'reference_type', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('product__sku', 'reference_number')


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = ('reservation_number', 'product', 'warehouse', 'quantity', 'status', 'reference_type', 'expires_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('reservation_number', 'reference_number')
