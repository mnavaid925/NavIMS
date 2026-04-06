from django import forms
from django.forms import inlineformset_factory

from catalog.models import Product
from vendors.models import Vendor
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from core.models import User
from .models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice,
    ThreeWayMatch, QualityInspection, QualityInspectionItem,
    WarehouseLocation, PutawayTask,
)


# ──────────────────────────────────────────────
# GRN Forms
# ──────────────────────────────────────────────

class GoodsReceiptNoteForm(forms.ModelForm):
    class Meta:
        model = GoodsReceiptNote
        fields = ['purchase_order', 'received_date', 'delivery_note_number', 'notes']
        widgets = {
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'received_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'delivery_note_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Delivery note number (optional)',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(
                tenant=tenant,
                status__in=['sent', 'partially_received'],
            )
            self.fields['purchase_order'].empty_label = '— Select Purchase Order —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class GoodsReceiptNoteItemForm(forms.ModelForm):
    class Meta:
        model = GoodsReceiptNoteItem
        fields = ['po_item', 'product', 'quantity_received', 'notes']
        widgets = {
            'po_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantity_received': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '0',
                'placeholder': 'Qty',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Notes (optional)',
            }),
        }


GoodsReceiptNoteItemFormSet = inlineformset_factory(
    GoodsReceiptNote,
    GoodsReceiptNoteItem,
    form=GoodsReceiptNoteItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Vendor Invoice Form
# ──────────────────────────────────────────────

class VendorInvoiceForm(forms.ModelForm):
    class Meta:
        model = VendorInvoice
        fields = [
            'invoice_number', 'vendor', 'purchase_order',
            'invoice_date', 'due_date',
            'subtotal', 'tax_amount', 'total_amount',
            'document', 'notes',
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Vendor invoice number',
            }),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'subtotal': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00',
            }),
            'tax_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00',
            }),
            'total_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00',
            }),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['vendor'].queryset = Vendor.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['vendor'].empty_label = '— Select Vendor —'
            self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(
                tenant=tenant,
            ).exclude(status__in=['draft', 'cancelled'])
            self.fields['purchase_order'].empty_label = '— Select Purchase Order —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Three-Way Match Form
# ──────────────────────────────────────────────

class ThreeWayMatchForm(forms.ModelForm):
    class Meta:
        model = ThreeWayMatch
        fields = ['purchase_order', 'grn', 'vendor_invoice', 'discrepancy_notes']
        widgets = {
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'vendor_invoice': forms.Select(attrs={'class': 'form-select'}),
            'discrepancy_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(
                tenant=tenant,
            ).exclude(status__in=['draft', 'cancelled'])
            self.fields['purchase_order'].empty_label = '— Select Purchase Order —'
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['grn'].empty_label = '— Select GRN —'
            self.fields['vendor_invoice'].queryset = VendorInvoice.objects.filter(
                tenant=tenant,
            ).exclude(status='cancelled')
            self.fields['vendor_invoice'].empty_label = '— Select Vendor Invoice —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Quality Inspection Forms
# ──────────────────────────────────────────────

class QualityInspectionForm(forms.ModelForm):
    class Meta:
        model = QualityInspection
        fields = ['grn', 'inspector', 'inspection_date', 'notes']
        widgets = {
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'inspector': forms.Select(attrs={'class': 'form-select'}),
            'inspection_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(
                tenant=tenant, status__in=['draft', 'inspecting'],
            )
            self.fields['grn'].empty_label = '— Select GRN —'
            self.fields['inspector'].queryset = User.objects.filter(tenant=tenant, is_active=True)
            self.fields['inspector'].empty_label = '— Select Inspector —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class QualityInspectionItemForm(forms.ModelForm):
    class Meta:
        model = QualityInspectionItem
        fields = [
            'grn_item', 'product', 'quantity_inspected',
            'quantity_accepted', 'quantity_rejected', 'quantity_quarantined',
            'decision', 'reject_reason', 'notes',
        ]
        widgets = {
            'grn_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantity_inspected': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '0',
            }),
            'quantity_accepted': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '0',
            }),
            'quantity_rejected': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '0',
            }),
            'quantity_quarantined': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': '0',
            }),
            'decision': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'reject_reason': forms.TextInput(attrs={
                'class': 'form-control form-control-sm', 'placeholder': 'Reason',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control form-control-sm', 'placeholder': 'Notes',
            }),
        }


QualityInspectionItemFormSet = inlineformset_factory(
    QualityInspection,
    QualityInspectionItem,
    form=QualityInspectionItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Warehouse Location Form
# ──────────────────────────────────────────────

class WarehouseLocationForm(forms.ModelForm):
    class Meta:
        model = WarehouseLocation
        fields = ['name', 'code', 'location_type', 'parent', 'capacity', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., Bin A-01',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., A-01',
            }),
            'location_type': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'placeholder': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input', 'role': 'switch',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['parent'].queryset = WarehouseLocation.objects.filter(tenant=tenant)
            self.fields['parent'].empty_label = '— No Parent (Top Level) —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Putaway Task Form
# ──────────────────────────────────────────────

class PutawayTaskForm(forms.ModelForm):
    class Meta:
        model = PutawayTask
        fields = [
            'grn', 'grn_item', 'product', 'quantity',
            'suggested_location', 'assigned_location', 'assigned_to', 'notes',
        ]
        widgets = {
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'grn_item': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'placeholder': 'Qty',
            }),
            'suggested_location': forms.Select(attrs={'class': 'form-select'}),
            'assigned_location': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['grn'].empty_label = '— Select GRN —'
            self.fields['grn_item'].queryset = GoodsReceiptNoteItem.objects.filter(tenant=tenant)
            self.fields['grn_item'].empty_label = '— Select GRN Item —'
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, status='active')
            self.fields['product'].empty_label = '— Select Product —'
            locations = WarehouseLocation.objects.filter(tenant=tenant, is_active=True, location_type='bin')
            self.fields['suggested_location'].queryset = locations
            self.fields['suggested_location'].empty_label = '— None —'
            self.fields['assigned_location'].queryset = locations
            self.fields['assigned_location'].empty_label = '— None —'
            self.fields['assigned_to'].queryset = User.objects.filter(tenant=tenant, is_active=True)
            self.fields['assigned_to'].empty_label = '— Unassigned —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
