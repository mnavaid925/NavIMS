from django.contrib import admin

from .models import (
    Carrier, ShippingRate, SalesOrder, SalesOrderItem,
    WavePlan, WaveOrderAssignment, PickList, PickListItem,
    PackingList, Shipment, ShipmentTracking,
)


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_name', 'status', 'priority', 'warehouse', 'order_date', 'tenant')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('order_number', 'customer_name', 'customer_email')
    inlines = [SalesOrderItemInline]


@admin.register(SalesOrderItem)
class SalesOrderItemAdmin(admin.ModelAdmin):
    list_display = ('sales_order', 'product', 'quantity', 'unit_price', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('sales_order__order_number', 'product__name')


class PickListItemInline(admin.TabularInline):
    model = PickListItem
    extra = 0


@admin.register(PickList)
class PickListAdmin(admin.ModelAdmin):
    list_display = ('pick_number', 'sales_order', 'warehouse', 'status', 'assigned_to', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('pick_number', 'sales_order__order_number')
    inlines = [PickListItemInline]


@admin.register(PickListItem)
class PickListItemAdmin(admin.ModelAdmin):
    list_display = ('pick_list', 'product', 'ordered_quantity', 'picked_quantity', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('pick_list__pick_number', 'product__name')


@admin.register(PackingList)
class PackingListAdmin(admin.ModelAdmin):
    list_display = ('packing_number', 'sales_order', 'pick_list', 'status', 'packaging_type', 'tenant')
    list_filter = ('status', 'packaging_type', 'tenant')
    search_fields = ('packing_number', 'sales_order__order_number')


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('shipment_number', 'sales_order', 'carrier', 'status', 'tracking_number', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('shipment_number', 'sales_order__order_number', 'tracking_number')


@admin.register(ShipmentTracking)
class ShipmentTrackingAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'status', 'location', 'event_date', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('shipment__shipment_number', 'status', 'location')


class WaveOrderAssignmentInline(admin.TabularInline):
    model = WaveOrderAssignment
    extra = 0


@admin.register(WavePlan)
class WavePlanAdmin(admin.ModelAdmin):
    list_display = ('wave_number', 'warehouse', 'status', 'priority', 'tenant')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('wave_number',)
    inlines = [WaveOrderAssignmentInline]


@admin.register(WaveOrderAssignment)
class WaveOrderAssignmentAdmin(admin.ModelAdmin):
    list_display = ('wave_plan', 'sales_order', 'added_at', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('wave_plan__wave_number', 'sales_order__order_number')


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'contact_email', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'code')


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ('carrier', 'service_level', 'base_cost', 'cost_per_kg', 'estimated_transit_days', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('carrier__name', 'service_level')
