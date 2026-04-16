from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from catalog.models import Product
from vendors.models import Vendor
from .models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule,
    PurchaseOrderApproval, PurchaseOrderDispatch,
)


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            'vendor', 'order_date', 'expected_delivery_date',
            'payment_terms', 'shipping_address', 'notes',
        ]
        widgets = {
            'vendor': forms.Select(attrs={
                'class': 'form-select',
            }),
            'order_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'expected_delivery_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_terms': forms.Select(attrs={
                'class': 'form-select',
            }),
            'shipping_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter shipping address (optional)',
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
            self.fields['vendor'].queryset = Vendor.objects.filter(
                tenant=tenant, is_active=True, status='active',
            )
            self.fields['vendor'].empty_label = '— Select Vendor —'

    def clean(self):
        cleaned = super().clean()
        order_date = cleaned.get('order_date')
        delivery = cleaned.get('expected_delivery_date')
        if order_date and delivery and delivery < order_date:
            raise ValidationError({
                'expected_delivery_date':
                    'Expected delivery date cannot be earlier than order date.',
            })
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['product', 'description', 'quantity', 'unit_price', 'tax_rate', 'discount']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-select form-select-sm',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Description (optional)',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '1',
                'placeholder': 'Qty',
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '%',
            }),
            'discount': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
        }


PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=3,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class ApprovalRuleForm(forms.ModelForm):
    class Meta:
        model = ApprovalRule
        fields = ['name', 'min_amount', 'max_amount', 'required_approvals', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Low Value Orders',
            }),
            'min_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'max_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'required_approvals': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        min_amount = cleaned.get('min_amount')
        max_amount = cleaned.get('max_amount')
        if min_amount is not None and max_amount is not None and max_amount < min_amount:
            raise ValidationError({
                'max_amount':
                    'Maximum amount must be greater than or equal to minimum amount.',
            })
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class PurchaseOrderDispatchForm(forms.ModelForm):
    """Recipient address is server-pinned to `po.vendor.email`; not a form field (D-04)."""

    class Meta:
        model = PurchaseOrderDispatch
        fields = ['dispatch_method', 'notes']
        widgets = {
            'dispatch_method': forms.Select(attrs={
                'class': 'form-select',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Dispatch notes (optional)',
            }),
        }


class PurchaseOrderApprovalForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderApproval
        fields = ['decision', 'notes']
        widgets = {
            'decision': forms.Select(attrs={
                'class': 'form-select',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Approval notes (optional)',
            }),
        }
