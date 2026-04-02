from django.contrib import admin
from .models import PricingPlan, TenantCustomization, BillingHistory


@admin.register(PricingPlan)
class PricingPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'billing_cycle', 'max_users', 'max_warehouses', 'max_products', 'is_active')
    list_filter = ('billing_cycle', 'is_active')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TenantCustomization)
class TenantCustomizationAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'primary_color', 'secondary_color', 'company_email')
    search_fields = ('tenant__name', 'company_email')


@admin.register(BillingHistory)
class BillingHistoryAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'amount', 'payment_status', 'payment_method', 'billing_date')
    list_filter = ('payment_status', 'payment_method')
    search_fields = ('tenant__name', 'transaction_id', 'description')
    date_hierarchy = 'billing_date'
