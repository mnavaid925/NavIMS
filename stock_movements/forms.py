from django import forms
from django.core.exceptions import ValidationError

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from .models import (
    StockTransfer, StockTransferItem,
    TransferApprovalRule, TransferApproval,
    TransferRoute,
)


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = [
            'transfer_type', 'source_warehouse', 'destination_warehouse',
            'source_bin', 'destination_bin', 'priority', 'notes',
        ]
        widgets = {
            'transfer_type': forms.Select(attrs={'class': 'form-select'}),
            'source_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'destination_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'source_bin': forms.Select(attrs={'class': 'form-select'}),
            'destination_bin': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
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
            self.fields['source_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['source_warehouse'].empty_label = '— Select Source Warehouse —'
            self.fields['destination_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['destination_warehouse'].empty_label = '— Select Destination Warehouse —'
            self.fields['source_bin'].queryset = Bin.objects.filter(zone__warehouse__tenant=tenant)
            self.fields['source_bin'].empty_label = '— Select Source Bin (optional) —'
            self.fields['destination_bin'].queryset = Bin.objects.filter(zone__warehouse__tenant=tenant)
            self.fields['destination_bin'].empty_label = '— Select Destination Bin (optional) —'

    def clean(self):
        cleaned_data = super().clean()
        transfer_type = cleaned_data.get('transfer_type')
        source_warehouse = cleaned_data.get('source_warehouse')
        destination_warehouse = cleaned_data.get('destination_warehouse')

        if transfer_type == 'inter_warehouse':
            if not destination_warehouse:
                self.add_error('destination_warehouse', 'Destination warehouse is required for inter-warehouse transfers.')
            if source_warehouse and destination_warehouse and source_warehouse == destination_warehouse:
                self.add_error('destination_warehouse', 'Source and destination warehouses must be different for inter-warehouse transfers.')
        elif transfer_type == 'intra_warehouse':
            cleaned_data['destination_warehouse'] = source_warehouse

        return cleaned_data


class StockTransferItemForm(forms.ModelForm):
    class Meta:
        model = StockTransferItem
        fields = ['product', 'quantity', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Enter quantity',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Item notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            # D-12: align with the rest of the codebase — orderable products are
            # the ones with status='active' (catalog/forms.py, receiving/forms.py).
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, status='active')
            self.fields['product'].empty_label = '— Select Product —'


class TransferApprovalRuleForm(forms.ModelForm):
    class Meta:
        model = TransferApprovalRule
        fields = ['name', 'min_items', 'max_items', 'requires_approval', 'approver_role', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Rule name',
            }),
            'min_items': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Minimum items',
            }),
            'max_items': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Maximum items (leave empty for unlimited)',
            }),
            'requires_approval': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
            'approver_role': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Manager, Warehouse Admin',
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
        # D-10: a rule with min_items > max_items would never match anything.
        cleaned = super().clean()
        min_items = cleaned.get('min_items')
        max_items = cleaned.get('max_items')
        if min_items is not None and max_items is not None and min_items > max_items:
            raise ValidationError({
                'max_items': 'Maximum items must be greater than or equal to minimum items.'
            })
        return cleaned


class TransferApprovalForm(forms.ModelForm):
    class Meta:
        model = TransferApproval
        fields = ['decision', 'comments']
        widgets = {
            'decision': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Comments (optional)',
            }),
        }


class TransferRouteForm(forms.ModelForm):
    class Meta:
        model = TransferRoute
        fields = [
            'name', 'source_warehouse', 'destination_warehouse',
            'transit_method', 'estimated_duration_hours', 'distance_km',
            'instructions', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Route name',
            }),
            'source_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'destination_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'transit_method': forms.Select(attrs={'class': 'form-select'}),
            'estimated_duration_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Hours',
            }),
            'distance_km': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': 'Distance in km',
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Route instructions and notes',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['source_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['source_warehouse'].empty_label = '— Select Source Warehouse —'
            self.fields['destination_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['destination_warehouse'].empty_label = '— Select Destination Warehouse —'

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source_warehouse')
        destination = cleaned_data.get('destination_warehouse')
        if source and destination and source == destination:
            self.add_error('destination_warehouse', 'Source and destination warehouses must be different.')
        return cleaned_data
