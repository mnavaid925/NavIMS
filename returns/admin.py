from django.contrib import admin

from .models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


class TenantScopedAdmin(admin.ModelAdmin):
    """Filter admin list + form FK widgets by the admin user's tenant.

    Superusers still see every tenant's rows. Tenant admins only see their
    own tenant's data — closes D-23 (admin cross-tenant visibility).
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            return qs.none()
        return qs.filter(tenant=tenant)


class ReturnAuthorizationItemInline(admin.TabularInline):
    model = ReturnAuthorizationItem
    extra = 0


@admin.register(ReturnAuthorization)
class ReturnAuthorizationAdmin(TenantScopedAdmin):
    list_display = ('rma_number', 'tenant', 'customer_name', 'sales_order', 'status', 'reason', 'requested_date')
    list_filter = ('status', 'reason', 'tenant')
    search_fields = ('rma_number', 'customer_name', 'customer_email')
    inlines = [ReturnAuthorizationItemInline]


class ReturnInspectionItemInline(admin.TabularInline):
    model = ReturnInspectionItem
    extra = 0


@admin.register(ReturnInspection)
class ReturnInspectionAdmin(TenantScopedAdmin):
    list_display = ('inspection_number', 'tenant', 'rma', 'status', 'overall_result', 'inspector', 'inspected_date')
    list_filter = ('status', 'overall_result', 'tenant')
    search_fields = ('inspection_number', 'rma__rma_number')
    inlines = [ReturnInspectionItemInline]


class DispositionItemInline(admin.TabularInline):
    model = DispositionItem
    extra = 0


@admin.register(Disposition)
class DispositionAdmin(TenantScopedAdmin):
    list_display = ('disposition_number', 'tenant', 'rma', 'decision', 'warehouse', 'status', 'processed_at')
    list_filter = ('decision', 'status', 'tenant')
    search_fields = ('disposition_number', 'rma__rma_number')
    inlines = [DispositionItemInline]


@admin.register(RefundCredit)
class RefundCreditAdmin(TenantScopedAdmin):
    list_display = ('refund_number', 'tenant', 'rma', 'type', 'method', 'amount', 'status', 'processed_at')
    list_filter = ('type', 'method', 'status', 'tenant')
    search_fields = ('refund_number', 'rma__rma_number', 'reference_number')
