from django import forms

from catalog.models import Product
from warehousing.models import Warehouse
from .models import (
    StockAdjustment, StockStatusTransition, StockStatus,
    ValuationConfig, InventoryReservation,
)


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['adjustment_type', 'quantity', 'reason', 'notes']
        widgets = {
            'adjustment_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Enter quantity',
            }),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)


class StockStatusTransitionForm(forms.ModelForm):
    class Meta:
        model = StockStatusTransition
        fields = ['product', 'warehouse', 'from_status', 'to_status', 'quantity', 'reason']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'from_status': forms.Select(attrs={'class': 'form-select'}),
            'to_status': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Quantity to transition',
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Reason for status change',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].empty_label = '— Select Product —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def clean(self):
        cleaned_data = super().clean()
        from_status = cleaned_data.get('from_status')
        to_status = cleaned_data.get('to_status')
        if from_status and to_status and from_status == to_status:
            raise forms.ValidationError('Source and target status must be different.')
        return cleaned_data


class ValuationConfigForm(forms.ModelForm):
    class Meta:
        model = ValuationConfig
        fields = ['method', 'auto_recalculate']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'auto_recalculate': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }


class InventoryReservationForm(forms.ModelForm):
    class Meta:
        model = InventoryReservation
        fields = ['product', 'warehouse', 'quantity', 'reference_type', 'reference_number', 'expires_at', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Quantity to reserve',
            }),
            'reference_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Sales Order, Job, Transfer',
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. SO-00001',
            }),
            'expires_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].empty_label = '— Select Product —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
