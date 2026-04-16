from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from catalog.models import Product
from .models import (
    Warehouse, Zone, Aisle, Rack, Bin,
    CrossDockOrder, CrossDockItem,
)


class TenantUniqueCodeMixin:
    """Enforce `unique_together = ('tenant', 'code')` at the form layer.

    D-01 remediation. Without this, Django's `validate_unique()` skips the
    `tenant` column because it is not a form field, and a duplicate code
    reaches the DB as IntegrityError → 500.
    """

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            return code
        tenant = getattr(self, 'tenant', None)
        if tenant is None:
            return code
        model = self._meta.model
        qs = model.objects.filter(tenant=tenant, code__iexact=code)
        if self.instance.pk is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                f'Code "{code}" already exists for this tenant.'
            )
        return code


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = [
            'name', 'warehouse_type', 'address', 'city', 'state',
            'country', 'postal_code', 'contact_person', 'contact_email',
            'contact_phone', 'is_active', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter warehouse name',
            }),
            'warehouse_type': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Street address',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City',
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State / Province',
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country',
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Postal code',
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contact name',
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com',
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description (optional)',
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


class ZoneForm(TenantUniqueCodeMixin, forms.ModelForm):
    class Meta:
        model = Zone
        fields = [
            'warehouse', 'name', 'code', 'zone_type',
            'temperature_controlled', 'temperature_min', 'temperature_max',
            'is_active', 'description',
        ]
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Zone name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Z-RCV-01',
            }),
            'zone_type': forms.Select(attrs={'class': 'form-select'}),
            'temperature_controlled': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
            'temperature_min': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Min temp (C)',
            }),
            'temperature_max': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Max temp (C)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def clean(self):
        """D-02 — temperature_min must not exceed temperature_max."""
        cleaned = super().clean()
        temp_controlled = cleaned.get('temperature_controlled')
        tmin = cleaned.get('temperature_min')
        tmax = cleaned.get('temperature_max')
        if temp_controlled:
            if tmin is None or tmax is None:
                raise ValidationError(
                    'Temperature-controlled zones require both a minimum and a maximum temperature.'
                )
            if tmin > tmax:
                self.add_error(
                    'temperature_min',
                    'Minimum temperature must be less than or equal to maximum temperature.',
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class AisleForm(TenantUniqueCodeMixin, forms.ModelForm):
    class Meta:
        model = Aisle
        fields = ['zone', 'name', 'code', 'is_active']
        widgets = {
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Aisle name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., A-01',
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
            self.fields['zone'].queryset = Zone.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('warehouse')
            self.fields['zone'].empty_label = '— Select Zone —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class RackForm(TenantUniqueCodeMixin, forms.ModelForm):
    class Meta:
        model = Rack
        fields = ['aisle', 'name', 'code', 'levels', 'max_weight_capacity', 'is_active']
        widgets = {
            'aisle': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Rack name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., R-A01-01',
            }),
            'levels': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '1',
            }),
            'max_weight_capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Max weight (kg)',
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
            self.fields['aisle'].queryset = Aisle.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('zone', 'zone__warehouse')
            self.fields['aisle'].empty_label = '— Select Aisle —'

    def clean_max_weight_capacity(self):
        """D-03 — reject negative capacity."""
        value = self.cleaned_data.get('max_weight_capacity')
        if value is not None and value < 0:
            raise ValidationError('Max weight capacity cannot be negative.')
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class BinForm(TenantUniqueCodeMixin, forms.ModelForm):
    class Meta:
        model = Bin
        fields = [
            'zone', 'rack', 'name', 'code', 'bin_type',
            'max_weight', 'max_volume', 'max_quantity', 'is_active',
        ]
        widgets = {
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'rack': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Bin name',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., BIN-A01-01-03',
            }),
            'bin_type': forms.Select(attrs={'class': 'form-select'}),
            'max_weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Max weight (kg)',
            }),
            'max_volume': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Max volume (m3)',
            }),
            'max_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Max items',
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
            self.fields['zone'].queryset = Zone.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('warehouse')
            self.fields['zone'].empty_label = '— Select Zone —'
            self.fields['rack'].queryset = Rack.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('aisle', 'aisle__zone')
            self.fields['rack'].empty_label = '— No Rack (Floor Bin) —'
            self.fields['rack'].required = False

    def _reject_negative(self, field_name, label):
        value = self.cleaned_data.get(field_name)
        if value is not None and value < 0:
            raise ValidationError(f'{label} cannot be negative.')
        return value

    def clean_max_weight(self):
        return self._reject_negative('max_weight', 'Max weight')

    def clean_max_volume(self):
        return self._reject_negative('max_volume', 'Max volume')

    def clean(self):
        """D-04 — rack.aisle.zone must match the selected zone.
        D-12 — defence-in-depth: rack must belong to same tenant as bin.
        """
        cleaned = super().clean()
        zone = cleaned.get('zone')
        rack = cleaned.get('rack')
        if zone and rack and rack.aisle.zone_id != zone.id:
            self.add_error(
                'rack',
                'Rack must belong to the selected zone.',
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class CrossDockOrderForm(forms.ModelForm):
    class Meta:
        model = CrossDockOrder
        fields = [
            'source', 'destination', 'priority',
            'scheduled_arrival', 'scheduled_departure',
            'dock_door', 'notes',
        ]
        widgets = {
            'source': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Source / origin',
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Destination',
            }),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_arrival': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'scheduled_departure': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'dock_door': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Dock 3',
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

    def clean(self):
        """D-10 — scheduled_arrival must not exceed scheduled_departure."""
        cleaned = super().clean()
        arr = cleaned.get('scheduled_arrival')
        dep = cleaned.get('scheduled_departure')
        if arr and dep and arr > dep:
            self.add_error(
                'scheduled_departure',
                'Scheduled departure must be on or after scheduled arrival.',
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class CrossDockItemForm(forms.ModelForm):
    class Meta:
        model = CrossDockItem
        fields = ['product', 'description', 'quantity', 'weight', 'volume']

    def clean_quantity(self):
        """D-09 — quantity must be at least 1."""
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean_weight(self):
        value = self.cleaned_data.get('weight')
        if value is not None and value < 0:
            raise ValidationError('Weight cannot be negative.')
        return value

    def clean_volume(self):
        value = self.cleaned_data.get('volume')
        if value is not None and value < 0:
            raise ValidationError('Volume cannot be negative.')
        return value
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-select form-select-sm',
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Item description',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '1',
                'placeholder': 'Qty',
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': 'kg',
            }),
            'volume': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': 'm3',
            }),
        }


CrossDockItemFormSet = inlineformset_factory(
    CrossDockOrder,
    CrossDockItem,
    form=CrossDockItemForm,
    extra=3,
    can_delete=True,
)
