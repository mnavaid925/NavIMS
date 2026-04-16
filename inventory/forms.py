from django import forms
from django.core.exceptions import ValidationError

from catalog.models import Product
from warehousing.models import Warehouse
from .models import (
    StockAdjustment, StockStatusTransition, StockStatus, StockLevel,
    ValuationConfig, InventoryReservation,
)


class StockAdjustmentForm(forms.ModelForm):
    """Guards against over-decrement (D-01) and zero quantity (D-13).

    The view must pass `stock_level=` so `clean()` can compare against on-hand.
    """

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

    def __init__(self, *args, tenant=None, stock_level=None, **kwargs):
        self.tenant = tenant
        self.stock_level = stock_level
        super().__init__(*args, **kwargs)

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean(self):
        cleaned = super().clean()
        adj_type = cleaned.get('adjustment_type')
        qty = cleaned.get('quantity')
        if adj_type == 'decrease' and qty and self.stock_level is not None:
            if qty > self.stock_level.on_hand:
                raise ValidationError({
                    'quantity':
                        f'Decrease of {qty} exceeds on-hand '
                        f'{self.stock_level.on_hand} — no silent clamp.',
                })
        return cleaned


class StockStatusTransitionForm(forms.ModelForm):
    """Guards against phantom-source and under-stocked transitions (D-02)."""

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

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        warehouse = cleaned.get('warehouse')
        from_status = cleaned.get('from_status')
        to_status = cleaned.get('to_status')
        qty = cleaned.get('quantity')

        if from_status and to_status and from_status == to_status:
            raise ValidationError('Source and target status must be different.')

        if self.tenant and product and warehouse and from_status and qty:
            source = StockStatus.objects.filter(
                tenant=self.tenant, product=product,
                warehouse=warehouse, status=from_status,
            ).first()
            if source is None or source.quantity <= 0:
                raise ValidationError({
                    'from_status':
                        f'No {from_status} inventory exists for '
                        f'{product.sku} at {warehouse.code} — cannot transition from thin air.',
                })
            if qty > source.quantity:
                raise ValidationError({
                    'quantity':
                        f'Requested {qty} exceeds {from_status} on-hand '
                        f'of {source.quantity}.',
                })
        return cleaned


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
    """Guards against over-reserve and missing StockLevel (D-03)."""

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

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        warehouse = cleaned.get('warehouse')
        qty = cleaned.get('quantity')

        if self.tenant and product and warehouse and qty:
            sl = StockLevel.objects.filter(
                tenant=self.tenant, product=product, warehouse=warehouse,
            ).first()
            if sl is None:
                raise ValidationError({
                    'product':
                        f'No stock level configured for {product.sku} '
                        f'at {warehouse.code} — cannot reserve.',
                })

            # On edit, the current reservation's quantity is already counted
            # in `sl.allocated` if it was confirmed. For a realistic available
            # figure during validation we use `on_hand - allocated`, and if
            # this is an edit (instance has pk) we add back any quantity this
            # reservation already contributes when confirmed.
            available = max(sl.on_hand - sl.allocated, 0)
            if self.instance and self.instance.pk and self.instance.status == 'confirmed':
                available += self.instance.quantity

            if qty > available:
                raise ValidationError({
                    'quantity':
                        f'Requested {qty} exceeds available '
                        f'{available} at {warehouse.code}.',
                })
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
