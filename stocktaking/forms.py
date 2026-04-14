from django import forms
from django.forms import inlineformset_factory

from warehousing.models import Warehouse, Zone
from .models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)


# ──────────────────────────────────────────────
# Freeze Forms
# ──────────────────────────────────────────────

class StocktakeFreezeForm(forms.ModelForm):
    class Meta:
        model = StocktakeFreeze
        fields = ['warehouse', 'zones', 'reason', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zones': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 5}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reason for freezing (e.g., Year-end physical count)'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['zones'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['zones'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
            self.save_m2m()
        return instance


# ──────────────────────────────────────────────
# Cycle Count Schedule Forms
# ──────────────────────────────────────────────

class CycleCountScheduleForm(forms.ModelForm):
    class Meta:
        model = CycleCountSchedule
        fields = ['name', 'frequency', 'abc_class', 'warehouse', 'zones', 'next_run_date', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Weekly Class A count'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'abc_class': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zones': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 5}),
            'next_run_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['zones'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['zones'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
            self.save_m2m()
        return instance


# ──────────────────────────────────────────────
# Stock Count Forms
# ──────────────────────────────────────────────

class StockCountForm(forms.ModelForm):
    class Meta:
        model = StockCount
        fields = [
            'type', 'warehouse', 'zone', 'schedule', 'freeze',
            'blind_count', 'scheduled_date', 'assigned_to', 'notes',
        ]
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'schedule': forms.Select(attrs={'class': 'form-select'}),
            'freeze': forms.Select(attrs={'class': 'form-select'}),
            'blind_count': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'scheduled_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            from core.models import User
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['zone'].empty_label = '— All Zones —'
            self.fields['zone'].required = False
            self.fields['schedule'].queryset = CycleCountSchedule.objects.filter(tenant=tenant, is_active=True)
            self.fields['schedule'].empty_label = '— None —'
            self.fields['schedule'].required = False
            self.fields['freeze'].queryset = StocktakeFreeze.objects.filter(tenant=tenant, status='active')
            self.fields['freeze'].empty_label = '— None —'
            self.fields['freeze'].required = False
            self.fields['assigned_to'].queryset = User.objects.filter(tenant=tenant)
            self.fields['assigned_to'].empty_label = '— Assign Counter —'
            self.fields['assigned_to'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class StockCountItemCountForm(forms.ModelForm):
    """Form used during counting — only counted_qty, reason_code, notes."""
    class Meta:
        model = StockCountItem
        fields = ['counted_qty', 'reason_code', 'notes']
        widgets = {
            'counted_qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0', 'placeholder': 'Count'}),
            'reason_code': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }


StockCountItemFormSet = inlineformset_factory(
    StockCount,
    StockCountItem,
    form=StockCountItemCountForm,
    extra=0,
    can_delete=False,
)


# ──────────────────────────────────────────────
# Variance Adjustment Forms
# ──────────────────────────────────────────────

class StockVarianceAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockVarianceAdjustment
        fields = ['count', 'reason_code', 'notes']
        widgets = {
            'count': forms.Select(attrs={'class': 'form-select'}),
            'reason_code': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['count'].queryset = StockCount.objects.filter(
                tenant=tenant, status__in=['counted', 'reviewed'],
            )
            self.fields['count'].empty_label = '— Select Count —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
