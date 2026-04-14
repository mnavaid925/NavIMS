from django import forms
from django.forms import inlineformset_factory

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from orders.models import SalesOrder
from .models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


# ──────────────────────────────────────────────
# Return Authorization Forms
# ──────────────────────────────────────────────

class ReturnAuthorizationForm(forms.ModelForm):
    class Meta:
        model = ReturnAuthorization
        fields = [
            'sales_order', 'customer_name', 'customer_email', 'customer_phone',
            'return_address', 'reason', 'requested_date', 'expected_return_date',
            'warehouse', 'notes',
        ]
        widgets = {
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer full name'}),
            'customer_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'customer@example.com'}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 (555) 000-0000'}),
            'return_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Return pickup address'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'requested_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_return_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes (optional)'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant, status__in=['delivered', 'closed', 'shipped'],
            )
            self.fields['sales_order'].empty_label = '— Select Sales Order —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ReturnAuthorizationItemForm(forms.ModelForm):
    class Meta:
        model = ReturnAuthorizationItem
        fields = ['product', 'description', 'qty_requested', 'unit_price', 'reason_note']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Description (optional)'}),
            'qty_requested': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1', 'placeholder': 'Qty'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'reason_note': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }


ReturnAuthorizationItemFormSet = inlineformset_factory(
    ReturnAuthorization,
    ReturnAuthorizationItem,
    form=ReturnAuthorizationItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Return Inspection Forms
# ──────────────────────────────────────────────

class ReturnInspectionForm(forms.ModelForm):
    class Meta:
        model = ReturnInspection
        fields = ['rma', 'inspector', 'inspected_date', 'overall_result', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'inspector': forms.Select(attrs={'class': 'form-select'}),
            'inspected_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'overall_result': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Inspection notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            from core.models import User
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['approved', 'received'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'
            self.fields['inspector'].queryset = User.objects.filter(tenant=tenant)
            self.fields['inspector'].empty_label = '— Assign Inspector —'
            self.fields['inspector'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ReturnInspectionItemForm(forms.ModelForm):
    class Meta:
        model = ReturnInspectionItem
        fields = ['rma_item', 'qty_inspected', 'qty_passed', 'qty_failed', 'condition', 'restockable', 'notes']
        widgets = {
            'rma_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'qty_inspected': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'qty_passed': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'qty_failed': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'condition': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'restockable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }


ReturnInspectionItemFormSet = inlineformset_factory(
    ReturnInspection,
    ReturnInspectionItem,
    form=ReturnInspectionItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Disposition Forms
# ──────────────────────────────────────────────

class DispositionForm(forms.ModelForm):
    class Meta:
        model = Disposition
        fields = ['rma', 'inspection', 'decision', 'warehouse', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'inspection': forms.Select(attrs={'class': 'form-select'}),
            'decision': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Disposition notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['received', 'closed'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'
            self.fields['inspection'].queryset = ReturnInspection.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['inspection'].empty_label = '— Select Inspection (optional) —'
            self.fields['inspection'].required = False
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class DispositionItemForm(forms.ModelForm):
    class Meta:
        model = DispositionItem
        fields = ['inspection_item', 'product', 'qty', 'destination_bin', 'notes']
        widgets = {
            'inspection_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'destination_bin': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }


DispositionItemFormSet = inlineformset_factory(
    Disposition,
    DispositionItem,
    form=DispositionItemForm,
    extra=2,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Refund / Credit Forms
# ──────────────────────────────────────────────

class RefundCreditForm(forms.ModelForm):
    class Meta:
        model = RefundCredit
        fields = ['rma', 'type', 'method', 'amount', 'currency', 'reference_number', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Transaction or credit note reference'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['received', 'closed'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
