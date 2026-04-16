from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
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


# File upload constraints for VendorInvoice.document (D-02, repeat of lesson #8)
INVOICE_DOCUMENT_ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'webp',
}
INVOICE_DOCUMENT_BLOCKED_CONTENT_TYPES = {
    'image/svg+xml', 'application/x-msdownload', 'application/x-sh',
    'application/x-executable', 'application/x-dosexec',
    'text/html', 'application/javascript', 'application/x-javascript',
    'application/x-php', 'application/x-httpd-php',
}
INVOICE_DOCUMENT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


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

    def __init__(self, *args, tenant=None, **kwargs):
        # D-04: tenant MUST be injected on both GET and POST so formset querysets
        # stay scoped during validation and we can't bind a foreign-tenant po_item.
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['po_item'].queryset = PurchaseOrderItem.objects.filter(tenant=tenant)
            self.fields['po_item'].empty_label = '— Select PO Item —'
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant, status='active',
            )
            self.fields['product'].empty_label = '— Select Product —'

    def clean(self):
        cleaned = super().clean()
        # D-06: Reject over-receipt. Allow qty_received ≤ qty_outstanding for this PO item.
        po_item = cleaned.get('po_item')
        qty_received = cleaned.get('quantity_received') or 0
        if po_item and qty_received:
            previously = (
                GoodsReceiptNoteItem.objects
                .filter(po_item=po_item, grn__status='completed')
                .exclude(pk=self.instance.pk if self.instance and self.instance.pk else 0)
                .aggregate(total=Sum('quantity_received'))['total'] or 0
            )
            outstanding = max(po_item.quantity - previously, 0)
            if qty_received > outstanding:
                raise ValidationError({
                    'quantity_received': (
                        f'Cannot receive {qty_received} — only {outstanding} outstanding '
                        f'on PO item "{po_item.product.name}" (ordered {po_item.quantity}, '
                        f'already received {previously}).'
                    )
                })
        return cleaned


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

    def clean_invoice_number(self):
        # D-01: unique_together(tenant, invoice_number) can't be enforced by
        # Django's default validate_unique because tenant is not a form field.
        number = (self.cleaned_data.get('invoice_number') or '').strip()
        if not number or self.tenant is None:
            return number
        qs = VendorInvoice.objects.filter(tenant=self.tenant, invoice_number__iexact=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                f'An invoice with number "{number}" already exists in this tenant.'
            )
        return number

    def clean_document(self):
        # D-02: whitelist extensions, cap size, block dangerous content types.
        doc = self.cleaned_data.get('document')
        if not doc:
            return doc
        name = getattr(doc, 'name', '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext not in INVOICE_DOCUMENT_ALLOWED_EXTENSIONS:
            raise ValidationError(
                f'File type ".{ext}" is not allowed. Allowed types: '
                f'{", ".join(sorted(INVOICE_DOCUMENT_ALLOWED_EXTENSIONS))}.'
            )
        content_type = (getattr(doc, 'content_type', '') or '').lower()
        if content_type in INVOICE_DOCUMENT_BLOCKED_CONTENT_TYPES:
            raise ValidationError(f'Content type "{content_type}" is not allowed.')
        size = getattr(doc, 'size', 0) or 0
        if size > INVOICE_DOCUMENT_MAX_SIZE:
            raise ValidationError(
                f'File is too large ({size // 1024 // 1024} MB). '
                f'Maximum allowed size is {INVOICE_DOCUMENT_MAX_SIZE // 1024 // 1024} MB.'
            )
        return doc

    def clean(self):
        # D-07: reconcile subtotal + tax == total within 0.01 tolerance.
        cleaned = super().clean()
        subtotal = cleaned.get('subtotal')
        tax = cleaned.get('tax_amount')
        total = cleaned.get('total_amount')
        if subtotal is not None and tax is not None and total is not None:
            expected = (subtotal or 0) + (tax or 0)
            if abs(Decimal(expected) - Decimal(total)) > Decimal('0.01'):
                raise ValidationError({
                    'total_amount': (
                        f'Total amount ({total}) does not equal subtotal + tax '
                        f'({expected}).'
                    )
                })
        return cleaned

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

    def __init__(self, *args, tenant=None, **kwargs):
        # D-04: tenant-scope grn_item + product on both GET and POST.
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['grn_item'].queryset = GoodsReceiptNoteItem.objects.filter(tenant=tenant)
            self.fields['grn_item'].empty_label = '— Select GRN Item —'
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant, status='active',
            )
            self.fields['product'].empty_label = '— Select Product —'

    def clean(self):
        # D-11: accepted + rejected + quarantined must equal inspected.
        cleaned = super().clean()
        inspected = cleaned.get('quantity_inspected') or 0
        accepted = cleaned.get('quantity_accepted') or 0
        rejected = cleaned.get('quantity_rejected') or 0
        quarantined = cleaned.get('quantity_quarantined') or 0
        # Skip the check on empty/deleted formset rows (inspected == 0 and no decision).
        if inspected or accepted or rejected or quarantined:
            if accepted + rejected + quarantined != inspected:
                raise ValidationError(
                    f'Accepted ({accepted}) + Rejected ({rejected}) + Quarantined '
                    f'({quarantined}) must equal Inspected ({inspected}).'
                )
        return cleaned


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

    def clean_code(self):
        # D-01: unique_together(tenant, code) trap.
        code = (self.cleaned_data.get('code') or '').strip()
        if not code or self.tenant is None:
            return code
        qs = WarehouseLocation.objects.filter(tenant=self.tenant, code__iexact=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                f'A location with code "{code}" already exists in this tenant.'
            )
        return code

    def clean_parent(self):
        # Prevent self-parent cycle (covers the simple direct case).
        parent = self.cleaned_data.get('parent')
        if parent and self.instance and self.instance.pk and parent.pk == self.instance.pk:
            raise ValidationError('A location cannot be its own parent.')
        return parent

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
