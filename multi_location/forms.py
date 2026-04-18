from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

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

        # D-03 — Default FK querysets to .none() when tenant is missing so the
        # superuser path cannot cross-tenant-select parent / warehouse.
        if tenant is None:
            self.fields['parent'].queryset = Location.objects.none()
            self.fields['warehouse'].queryset = Warehouse.objects.none()
        else:
            parent_qs = Location.objects.filter(tenant=tenant)
            if self.instance.pk:
                exclude_ids = self.instance.get_descendant_ids(include_self=True)
                parent_qs = parent_qs.exclude(pk__in=exclude_ids)
            self.fields['parent'].queryset = parent_qs
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)

        self.fields['parent'].empty_label = '— No Parent (Top Level) —'
        self.fields['parent'].required = False
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

# Business bounds per rule_type for `value` — D-06 / D-07
_PRICING_VALUE_BOUNDS = {
    'markup_pct':       {'min': Decimal('0'),   'max': Decimal('1000'),   'err_min': 'Markup % cannot be negative.',       'err_max': 'Markup % cannot exceed 1000%.'},
    'markdown_pct':     {'min': Decimal('0'),   'max': Decimal('100'),    'err_min': 'Markdown % cannot be negative.',     'err_max': 'Markdown % cannot exceed 100%.'},
    'fixed_adjustment': {'min': None,           'max': None},
    'override_price':   {'min': Decimal('0.01'),'max': None,              'err_min': 'Override price must be positive.'},
}


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

        if tenant is None:
            # D-03 — superuser path cannot cross-tenant-select FKs.
            self.fields['location'].queryset = Location.objects.none()
            self.fields['product'].queryset = Product.objects.none()
            self.fields['category'].queryset = Category.objects.none()
        else:
            self.fields['location'].queryset = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant)

        self.fields['location'].empty_label = '— Select Location —'
        self.fields['product'].empty_label = '— Any Product —'
        self.fields['product'].required = False
        self.fields['category'].empty_label = '— Any Category —'
        self.fields['category'].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('product') and cleaned.get('category'):
            raise ValidationError(
                'Choose either a product or a category, not both. Leave both empty to apply to all.'
            )

        # D-06 / D-07 — value bounds per rule_type
        rule_type = cleaned.get('rule_type')
        value = cleaned.get('value')
        bounds = _PRICING_VALUE_BOUNDS.get(rule_type)
        if bounds is not None and value is not None:
            if bounds.get('min') is not None and value < bounds['min']:
                self.add_error('value', bounds.get('err_min', f'Value must be ≥ {bounds["min"]}.'))
            if bounds.get('max') is not None and value > bounds['max']:
                self.add_error('value', bounds.get('err_max', f'Value must be ≤ {bounds["max"]}.'))

        # D-05 — effective_from must precede effective_to
        efrom = cleaned.get('effective_from')
        eto = cleaned.get('effective_to')
        if efrom and eto and efrom > eto:
            self.add_error('effective_to', 'Effective-to date must be on or after effective-from.')

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

        if tenant is None:
            # D-03
            self.fields['source_location'].queryset = Location.objects.none()
            self.fields['destination_location'].queryset = Location.objects.none()
        else:
            qs = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['source_location'].queryset = qs
            self.fields['destination_location'].queryset = qs

        self.fields['source_location'].empty_label = '— Select Source —'
        self.fields['destination_location'].empty_label = '— Select Destination —'

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get('source_location')
        dst = cleaned.get('destination_location')
        if src and dst and src.pk == dst.pk:
            raise ValidationError('Source and destination must be different locations.')

        # D-11 — tenant-scoped uniqueness guard; Django's validate_unique
        # excludes tenant when it is not a form field.
        if src and dst and self.tenant is not None:
            qs = LocationTransferRule.objects.filter(
                tenant=self.tenant,
                source_location=src,
                destination_location=dst,
            )
            if self.instance.pk is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A transfer rule for this source → destination already exists.'
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

        if tenant is None:
            # D-03
            self.fields['location'].queryset = Location.objects.none()
            self.fields['product'].queryset = Product.objects.none()
        else:
            self.fields['location'].queryset = Location.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)

        self.fields['location'].empty_label = '— Select Location —'
        self.fields['product'].empty_label = '— Select Product —'

    def clean(self):
        cleaned = super().clean()
        ss = cleaned.get('safety_stock_qty')
        rop = cleaned.get('reorder_point')
        maxq = cleaned.get('max_stock_qty')

        # D-04 — enforce safety ≤ reorder ≤ max (max=0 means "no ceiling").
        if ss is not None and rop is not None and ss > rop:
            self.add_error(
                'reorder_point',
                'Reorder point must be ≥ safety stock quantity.',
            )
        if rop is not None and maxq is not None and maxq > 0 and rop > maxq:
            self.add_error(
                'max_stock_qty',
                'Max stock quantity must be ≥ reorder point (or 0 for no ceiling).',
            )

        # D-11 — unique_together(tenant, location, product) guard.
        location = cleaned.get('location')
        product = cleaned.get('product')
        if location and product and self.tenant is not None:
            qs = LocationSafetyStockRule.objects.filter(
                tenant=self.tenant, location=location, product=product,
            )
            if self.instance.pk is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A safety-stock rule for this location + product already exists.'
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
