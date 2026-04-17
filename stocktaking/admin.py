from django.contrib import admin

from .models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)

# D-21 — Django admin here is deliberately cross-tenant for superuser
# troubleshooting. Non-superuser access is governed by `is_staff`; tenant
# admins use the app's own views, which filter by `request.tenant`.


@admin.register(StocktakeFreeze)
class StocktakeFreezeAdmin(admin.ModelAdmin):
    list_display = ('freeze_number', 'tenant', 'warehouse', 'status', 'frozen_at', 'released_at')
    list_filter = ('status', 'tenant')
    search_fields = ('freeze_number', 'reason')


@admin.register(CycleCountSchedule)
class CycleCountScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'frequency', 'abc_class', 'warehouse', 'next_run_date', 'is_active')
    list_filter = ('frequency', 'abc_class', 'is_active', 'tenant')
    search_fields = ('name',)


class StockCountItemInline(admin.TabularInline):
    model = StockCountItem
    extra = 0


@admin.register(StockCount)
class StockCountAdmin(admin.ModelAdmin):
    list_display = ('count_number', 'tenant', 'type', 'warehouse', 'status', 'blind_count', 'scheduled_date')
    list_filter = ('type', 'status', 'blind_count', 'tenant')
    search_fields = ('count_number',)
    inlines = [StockCountItemInline]


@admin.register(StockVarianceAdjustment)
class StockVarianceAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'tenant', 'count', 'status', 'reason_code', 'total_variance_value', 'posted_at')
    list_filter = ('status', 'reason_code', 'tenant')
    search_fields = ('adjustment_number', 'count__count_number')
