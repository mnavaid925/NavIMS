from django.contrib import admin

from .models import (
    DemandForecast, DemandForecastLine,
    ReorderPoint, ReorderAlert,
    SafetyStock,
    SeasonalityProfile, SeasonalityPeriod,
)


class DemandForecastLineInline(admin.TabularInline):
    model = DemandForecastLine
    extra = 0


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ('forecast_number', 'tenant', 'name', 'product', 'warehouse', 'method', 'period_type', 'status')
    list_filter = ('status', 'method', 'period_type', 'tenant')
    search_fields = ('forecast_number', 'name', 'product__name')
    list_per_page = 50
    raw_id_fields = ('tenant', 'product', 'warehouse', 'seasonality_profile', 'created_by')
    inlines = [DemandForecastLineInline]


@admin.register(ReorderPoint)
class ReorderPointAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'tenant', 'rop_qty', 'safety_stock_qty', 'reorder_qty', 'is_active')
    list_filter = ('is_active', 'tenant', 'warehouse')
    search_fields = ('product__name', 'product__sku')
    list_per_page = 50
    raw_id_fields = ('tenant', 'product', 'warehouse')


@admin.register(ReorderAlert)
class ReorderAlertAdmin(admin.ModelAdmin):
    list_display = ('alert_number', 'tenant', 'product', 'warehouse', 'current_qty', 'rop_qty', 'status', 'triggered_at')
    list_filter = ('status', 'tenant', 'warehouse')
    search_fields = ('alert_number', 'product__name')
    list_per_page = 50
    raw_id_fields = ('tenant', 'rop', 'product', 'warehouse', 'acknowledged_by')


@admin.register(SafetyStock)
class SafetyStockAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'tenant', 'method', 'service_level', 'safety_stock_qty', 'calculated_at')
    list_filter = ('method', 'tenant', 'warehouse')
    search_fields = ('product__name', 'product__sku')
    list_per_page = 50
    raw_id_fields = ('tenant', 'product', 'warehouse')


class SeasonalityPeriodInline(admin.TabularInline):
    model = SeasonalityPeriod
    extra = 0


@admin.register(SeasonalityProfile)
class SeasonalityProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'period_type', 'category', 'product', 'is_active')
    list_filter = ('period_type', 'is_active', 'tenant')
    search_fields = ('name',)
    list_per_page = 50
    raw_id_fields = ('tenant', 'category', 'product', 'created_by')
    inlines = [SeasonalityPeriodInline]
