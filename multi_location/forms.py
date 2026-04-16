from django import forms

from warehousing.models import Warehouse
from catalog.models import Product, Category
from .models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)


# ──────────────────────────────────────────────
# Location Form
# ──────────────────────────────────────────────

class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = [
            'name', 'location_type', 'parent', 'warehouse',
            'address', 'city', 'state', 'country', 'postal_code',
            'manager_name', 'contact_email', 'contact_phone',
            'is_active', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., North Region DC'}),
            'location_type': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'manager_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            parent_qs = Location.objects.filter(tenant=tenant)
            if self.instance.pk:
                exclude_ids = self.instance.get_descendant_ids(include_self=True)
                parent_qs = parent_qs.exclude(pk__in=exclude_ids)
            self.fields['parent'].queryset = parent_qs
            self.fields['parent'].empty_label = '— No Parent (Top Level) —'
            self.fields['parent'].required = False

            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— None —'
            self.fields['warehouse'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Pricing Rule Form
# ──────────────────────────────────────────────

class LocationPricingRuleForm(forms.ModelForm):
    class Meta:
        model = LocationPricingRule
        fields = [
            'location', 'product', 'category', 'rule_type', 'value',
            'priority', 'is_active', 'effective_from', 'effective_to', 'notes',
        ]
        widgets = {
            'location': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rule_type': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'effective_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['location'].queryset = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['location'].empty_label = '— Select Location —'
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].empty_label = '— Any Product —'
            self.fields['product'].required = False
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant)
            self.fields['category'].empty_label = '— Any Category —'
            self.fields['category'].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('product') and cleaned.get('category'):
            raise forms.ValidationError(
                'Choose either a product or a category, not both. Leave both empty to apply to all.'
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Transfer Rule Form
# ──────────────────────────────────────────────

class LocationTransferRuleForm(forms.ModelForm):
    class Meta:
        model = LocationTransferRule
        fields = [
            'source_location', 'destination_location', 'allowed',
            'max_transfer_qty', 'lead_time_days', 'requires_approval',
            'priority', 'is_active', 'notes',
        ]
        widgets = {
            'source_location': forms.Select(attrs={'class': 'form-select'}),
            'destination_location': forms.Select(attrs={'class': 'form-select'}),
            'allowed': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'max_transfer_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'requires_approval': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            qs = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['source_location'].queryset = qs
            self.fields['source_location'].empty_label = '— Select Source —'
            self.fields['destination_location'].queryset = qs
            self.fields['destination_location'].empty_label = '— Select Destination —'

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get('source_location')
        dst = cleaned.get('destination_location')
        if src and dst and src.pk == dst.pk:
            raise forms.ValidationError('Source and destination must be different locations.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Safety Stock Rule Form
# ──────────────────────────────────────────────

class LocationSafetyStockRuleForm(forms.ModelForm):
    class Meta:
        model = LocationSafetyStockRule
        fields = ['location', 'product', 'safety_stock_qty', 'reorder_point', 'max_stock_qty', 'notes']
        widgets = {
            'location': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'safety_stock_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'reorder_point': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'max_stock_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['location'].queryset = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['location'].empty_label = '— Select Location —'
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].empty_label = '— Select Product —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
