from django.contrib import admin

from .models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'location_type', 'parent', 'warehouse', 'is_active', 'tenant')
    list_filter = ('location_type', 'is_active', 'tenant')
    search_fields = ('code', 'name', 'city', 'country')
    raw_id_fields = ('parent', 'warehouse')


@admin.register(LocationPricingRule)
class LocationPricingRuleAdmin(admin.ModelAdmin):
    list_display = ('location', 'rule_type', 'value', 'product', 'category', 'priority', 'is_active', 'tenant')
    list_filter = ('rule_type', 'is_active', 'tenant')
    search_fields = ('location__name', 'product__name', 'category__name')
    raw_id_fields = ('location', 'product', 'category')


@admin.register(LocationTransferRule)
class LocationTransferRuleAdmin(admin.ModelAdmin):
    list_display = ('source_location', 'destination_location', 'allowed', 'lead_time_days', 'priority', 'is_active', 'tenant')
    list_filter = ('allowed', 'requires_approval', 'is_active', 'tenant')
    search_fields = ('source_location__name', 'destination_location__name')
    raw_id_fields = ('source_location', 'destination_location')


@admin.register(LocationSafetyStockRule)
class LocationSafetyStockRuleAdmin(admin.ModelAdmin):
    list_display = ('location', 'product', 'safety_stock_qty', 'reorder_point', 'max_stock_qty', 'tenant')
    list_filter = ('location', 'tenant')
    search_fields = ('location__name', 'product__name', 'product__sku')
    raw_id_fields = ('location', 'product')
