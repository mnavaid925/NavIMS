from django.contrib import admin
from .models import Vendor, VendorPerformance, VendorContract, VendorCommunication


class VendorPerformanceInline(admin.TabularInline):
    model = VendorPerformance
    extra = 0


class VendorContractInline(admin.TabularInline):
    model = VendorContract
    extra = 0


class VendorCommunicationInline(admin.TabularInline):
    model = VendorCommunication
    extra = 0


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'tenant', 'vendor_type', 'status', 'email', 'payment_terms', 'created_at')
    list_filter = ('vendor_type', 'status', 'payment_terms', 'is_active', 'tenant')
    search_fields = ('company_name', 'email', 'tax_id', 'contact_person')
    inlines = [VendorPerformanceInline, VendorContractInline, VendorCommunicationInline]


@admin.register(VendorPerformance)
class VendorPerformanceAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'tenant', 'review_date', 'delivery_rating', 'quality_rating', 'compliance_rating', 'reviewed_by')
    list_filter = ('review_date', 'tenant')
    search_fields = ('vendor__company_name',)


@admin.register(VendorContract)
class VendorContractAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'vendor', 'tenant', 'title', 'status', 'start_date', 'end_date', 'contract_value')
    list_filter = ('status', 'tenant')
    search_fields = ('contract_number', 'title', 'vendor__company_name')


@admin.register(VendorCommunication)
class VendorCommunicationAdmin(admin.ModelAdmin):
    list_display = ('subject', 'vendor', 'tenant', 'communication_type', 'communication_date', 'communicated_by')
    list_filter = ('communication_type', 'tenant')
    search_fields = ('subject', 'vendor__company_name')
