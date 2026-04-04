from django import forms
from django.forms import inlineformset_factory

from catalog.models import Product
from vendors.models import Vendor
from .models import PurchaseOrder, PurchaseOrderItem, ApprovalRule, PurchaseOrderApproval


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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


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
