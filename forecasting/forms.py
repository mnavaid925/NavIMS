from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from catalog.models import Product, Category
from warehousing.models import Warehouse
from .models import (
    DemandForecast, DemandForecastLine,
    ReorderPoint, ReorderAlert,
    SafetyStock,
    SeasonalityProfile, SeasonalityPeriod,
)


# ──────────────────────────────────────────────
# Demand Forecast Forms
# ──────────────────────────────────────────────

class DemandForecastForm(forms.ModelForm):
    class Meta:
        model = DemandForecast
        fields = [
            'name', 'product', 'warehouse', 'method', 'period_type',
            'history_periods', 'forecast_periods', 'seasonality_profile',
            'confidence_pct', 'status', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Monthly Q2 forecast — Widget A'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'history_periods': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '36'}),
            'forecast_periods': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '24'}),
            'seasonality_profile': forms.Select(attrs={'class': 'form-select'}),
            'confidence_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].empty_label = '— Select Product —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['seasonality_profile'].queryset = SeasonalityProfile.objects.filter(tenant=tenant, is_active=True)
            self.fields['seasonality_profile'].empty_label = '— None —'
            self.fields['seasonality_profile'].required = False

    def clean(self):
        cleaned = super().clean()
        hp = cleaned.get('history_periods')
        fp = cleaned.get('forecast_periods')
        if hp is not None and hp < 1:
            self.add_error('history_periods', 'Must be at least 1.')
        if fp is not None and fp < 1:
            self.add_error('forecast_periods', 'Must be at least 1.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Reorder Point Forms
# ──────────────────────────────────────────────

class ReorderPointForm(forms.ModelForm):
    class Meta:
        model = ReorderPoint
        fields = [
            'product', 'warehouse', 'avg_daily_usage', 'lead_time_days',
            'safety_stock_qty', 'rop_qty', 'min_qty', 'max_qty',
            'reorder_qty', 'is_active', 'notes',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'avg_daily_usage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'safety_stock_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'rop_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'readonly': 'readonly'}),
            'min_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'max_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'reorder_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'rop_qty': 'Auto-calculated on save: (avg_daily_usage × lead_time_days) + safety_stock_qty',
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
        # D-01 regression guard — tenant is not a form field so Django's
        # validate_unique() excludes it; enforce unique_together manually.
        cleaned = super().clean()
        product = cleaned.get('product')
        warehouse = cleaned.get('warehouse')
        if self.tenant and product and warehouse:
            qs = ReorderPoint.objects.filter(
                tenant=self.tenant, product=product, warehouse=warehouse,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A reorder point already exists for this product/warehouse.'
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        instance.recalc_rop()
        if commit:
            instance.save()
        return instance


class ReorderAlertAcknowledgeForm(forms.ModelForm):
    class Meta:
        model = ReorderAlert
        fields = ['suggested_order_qty', 'notes']
        widgets = {
            'suggested_order_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.pk and not self.instance.can_transition_to('acknowledged'):
            raise ValidationError(
                f'Alert cannot be acknowledged from status "{self.instance.get_status_display()}".'
            )
        return cleaned


# ──────────────────────────────────────────────
# Safety Stock Forms
# ──────────────────────────────────────────────

class SafetyStockForm(forms.ModelForm):
    class Meta:
        model = SafetyStock
        fields = [
            'product', 'warehouse', 'method', 'service_level',
            'avg_demand', 'demand_std_dev', 'avg_lead_time_days', 'lead_time_std_dev',
            'fixed_qty', 'percentage', 'safety_stock_qty', 'notes',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'service_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.005', 'min': '0.5', 'max': '0.999'}),
            'avg_demand': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'demand_std_dev': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'avg_lead_time_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'lead_time_std_dev': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'fixed_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'safety_stock_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'readonly': 'readonly'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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
        # D-02 regression guard — same tenant-trap as ReorderPointForm.
        cleaned = super().clean()
        product = cleaned.get('product')
        warehouse = cleaned.get('warehouse')
        if self.tenant and product and warehouse:
            qs = SafetyStock.objects.filter(
                tenant=self.tenant, product=product, warehouse=warehouse,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A safety stock record already exists for this product/warehouse.'
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        instance.recalc()
        from django.utils import timezone
        instance.calculated_at = timezone.now()
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Seasonality Forms
# ──────────────────────────────────────────────

class SeasonalityProfileForm(forms.ModelForm):
    class Meta:
        model = SeasonalityProfile
        fields = ['name', 'description', 'category', 'product', 'period_type', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Summer spike profile'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant)
            self.fields['category'].empty_label = '— Any Category —'
            self.fields['category'].required = False
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].empty_label = '— Any Product —'
            self.fields['product'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class SeasonalityPeriodForm(forms.ModelForm):
    class Meta:
        model = SeasonalityPeriod
        fields = ['period_number', 'period_label', 'demand_multiplier', 'notes']
        widgets = {
            'period_number': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1', 'max': '12'}),
            'period_label': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'demand_multiplier': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def clean(self):
        cleaned = super().clean()
        n = cleaned.get('period_number')
        mult = cleaned.get('demand_multiplier')
        profile = getattr(self.instance, 'profile', None)
        if n is not None:
            if profile is not None and profile.period_type == 'quarter':
                if n < 1 or n > 4:
                    self.add_error('period_number', 'Quarterly profile accepts 1–4.')
            else:
                if n < 1 or n > 12:
                    self.add_error('period_number', 'Monthly profile accepts 1–12.')
        if mult is not None and mult < 0:
            self.add_error('demand_multiplier', 'Multiplier cannot be negative.')
        return cleaned


SeasonalityPeriodFormSet = inlineformset_factory(
    SeasonalityProfile,
    SeasonalityPeriod,
    form=SeasonalityPeriodForm,
    extra=0,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Generate Forecast helper form
# ──────────────────────────────────────────────

class GenerateForecastForm(forms.Form):
    """No-op form shown on generate page — trigger recalculation."""
    regenerate = forms.BooleanField(
        required=False, initial=True,
        label='Regenerate forecast lines (replace existing)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
    )
