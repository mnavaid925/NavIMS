from django.contrib import admin
from .models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule,
    PurchaseOrderApproval, PurchaseOrderDispatch,
)


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


class PurchaseOrderApprovalInline(admin.TabularInline):
    model = PurchaseOrderApproval
    extra = 0


class PurchaseOrderDispatchInline(admin.TabularInline):
    model = PurchaseOrderDispatch
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'tenant', 'vendor', 'status', 'order_date', 'payment_terms', 'created_by', 'created_at')
    list_filter = ('status', 'payment_terms', 'tenant')
    search_fields = ('po_number', 'vendor__company_name')
    inlines = [PurchaseOrderItemInline, PurchaseOrderApprovalInline, PurchaseOrderDispatchInline]


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'product', 'tenant', 'quantity', 'unit_price', 'tax_rate', 'discount')
    list_filter = ('tenant',)
    search_fields = ('purchase_order__po_number', 'product__name')


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'min_amount', 'max_amount', 'required_approvals', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name',)


@admin.register(PurchaseOrderApproval)
class PurchaseOrderApprovalAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'tenant', 'approver', 'decision', 'decided_at')
    list_filter = ('decision', 'tenant')
    search_fields = ('purchase_order__po_number', 'approver__username')


@admin.register(PurchaseOrderDispatch)
class PurchaseOrderDispatchAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'tenant', 'dispatch_method', 'sent_to_email', 'sent_by', 'dispatched_at')
    list_filter = ('dispatch_method', 'tenant')
    search_fields = ('purchase_order__po_number', 'sent_to_email')
