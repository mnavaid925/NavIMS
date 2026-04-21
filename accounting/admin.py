"""Admin registrations for Module 19.

`TenantScopedAdmin` mirrors the pattern from `returns/admin.py` — admin
queryset is filtered by `request.user.tenant` for tenant admins, bypassed
for superusers (who have `tenant=None`).
"""
from django.contrib import admin

from .models import (
    ChartOfAccount, FiscalPeriod, Customer,
    TaxJurisdiction, TaxRule,
    APBill, APBillLine, ARInvoice, ARInvoiceLine,
    JournalEntry, JournalLine,
)


class TenantScopedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        if user.is_superuser:
            return qs
        tenant = getattr(user, 'tenant', None)
        if tenant is None:
            return qs.none()
        return qs.filter(tenant=tenant)


@admin.register(ChartOfAccount)
class ChartOfAccountAdmin(TenantScopedAdmin):
    list_display = ('code', 'name', 'account_type', 'parent', 'is_active', 'tenant')
    list_filter = ('account_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')
    ordering = ('code',)


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(TenantScopedAdmin):
    list_display = ('period_number', 'name', 'start_date', 'end_date', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('period_number', 'name')


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdmin):
    list_display = ('customer_number', 'company_name', 'contact_email',
                    'payment_terms', 'is_active', 'tenant')
    list_filter = ('is_active', 'payment_terms', 'tenant')
    search_fields = ('customer_number', 'company_name', 'contact_email', 'tax_id')


@admin.register(TaxJurisdiction)
class TaxJurisdictionAdmin(TenantScopedAdmin):
    list_display = ('code', 'name', 'country', 'state', 'is_active', 'tenant')
    list_filter = ('is_active', 'country', 'tenant')
    search_fields = ('code', 'name')


@admin.register(TaxRule)
class TaxRuleAdmin(TenantScopedAdmin):
    list_display = ('rule_number', 'jurisdiction', 'tax_category', 'tax_rate',
                    'effective_date', 'end_date', 'is_active', 'tenant')
    list_filter = ('tax_category', 'is_active', 'jurisdiction', 'tenant')
    search_fields = ('rule_number',)


class APBillLineInline(admin.TabularInline):
    model = APBillLine
    extra = 0


@admin.register(APBill)
class APBillAdmin(TenantScopedAdmin):
    list_display = ('bill_number', 'vendor', 'bill_date', 'due_date',
                    'total_amount', 'status', 'sync_status', 'tenant')
    list_filter = ('status', 'sync_status', 'tenant')
    search_fields = ('bill_number', 'vendor__company_name')
    inlines = [APBillLineInline]
    readonly_fields = ('subtotal', 'tax_amount', 'total_amount',
                       'posted_at', 'paid_at', 'created_at', 'updated_at')


class ARInvoiceLineInline(admin.TabularInline):
    model = ARInvoiceLine
    extra = 0


@admin.register(ARInvoice)
class ARInvoiceAdmin(TenantScopedAdmin):
    list_display = ('invoice_number', 'customer', 'invoice_date', 'due_date',
                    'total_amount', 'status', 'sync_status', 'tenant')
    list_filter = ('status', 'sync_status', 'tenant')
    search_fields = ('invoice_number', 'customer__company_name')
    inlines = [ARInvoiceLineInline]
    readonly_fields = ('subtotal', 'tax_amount', 'total_amount',
                       'sent_at', 'paid_at', 'created_at', 'updated_at')


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(TenantScopedAdmin):
    list_display = ('entry_number', 'entry_date', 'fiscal_period',
                    'source_type', 'source_reference',
                    'total_debit', 'total_credit', 'status', 'sync_status', 'tenant')
    list_filter = ('status', 'sync_status', 'source_type', 'tenant')
    search_fields = ('entry_number', 'source_reference', 'description')
    inlines = [JournalLineInline]
    readonly_fields = ('total_debit', 'total_credit', 'posted_at',
                       'created_at', 'updated_at')
