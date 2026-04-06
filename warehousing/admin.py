from django.contrib import admin
from .models import (
    Warehouse, Zone, Aisle, Rack, Bin,
    CrossDockOrder, CrossDockItem,
)


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0


class AisleInline(admin.TabularInline):
    model = Aisle
    extra = 0


class RackInline(admin.TabularInline):
    model = Rack
    extra = 0


class BinInline(admin.TabularInline):
    model = Bin
    extra = 0
    fk_name = 'rack'


class CrossDockItemInline(admin.TabularInline):
    model = CrossDockItem
    extra = 0


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'warehouse_type', 'city', 'is_active', 'created_at')
    list_filter = ('warehouse_type', 'is_active', 'tenant')
    search_fields = ('code', 'name', 'city')
    inlines = [ZoneInline]


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'warehouse', 'zone_type', 'temperature_controlled', 'is_active')
    list_filter = ('zone_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')
    inlines = [AisleInline]


@admin.register(Aisle)
class AisleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'zone', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')
    inlines = [RackInline]


@admin.register(Rack)
class RackAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'aisle', 'levels', 'max_weight_capacity', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')
    inlines = [BinInline]


@admin.register(Bin)
class BinAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'zone', 'rack', 'bin_type', 'is_active', 'is_occupied')
    list_filter = ('bin_type', 'is_active', 'is_occupied', 'tenant')
    search_fields = ('code', 'name')


@admin.register(CrossDockOrder)
class CrossDockOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'tenant', 'source', 'destination', 'status', 'priority', 'created_by', 'created_at')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('order_number', 'source', 'destination')
    inlines = [CrossDockItemInline]


@admin.register(CrossDockItem)
class CrossDockItemAdmin(admin.ModelAdmin):
    list_display = ('cross_dock_order', 'tenant', 'description', 'product', 'quantity', 'weight', 'volume')
    list_filter = ('tenant',)
    search_fields = ('cross_dock_order__order_number', 'description')
