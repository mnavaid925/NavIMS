"""Forms for the 21 report types.

Each form collects the params needed by the corresponding compute service.
All forms inherit from BaseReportForm which supplies tenant-scoped warehouse /
category FKs + title + notes. Subclasses add report-specific params
(as_of_date, period_start/end, thresholds, etc.).
"""
from datetime import date, timedelta
from decimal import Decimal

from django import forms


class BaseReportForm(forms.Form):
    """Common fields every report shares."""

    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Report title'}),
    )
    warehouse = forms.ModelChoiceField(
        queryset=None, required=False, empty_label='All warehouses',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    category = forms.ModelChoiceField(
        queryset=None, required=False, empty_label='All categories',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    notes = forms.CharField(
        required=False, max_length=2000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        # Lazy imports to avoid Django app-loading ordering issues
        from warehousing.models import Warehouse
        from catalog.models import Category
        if tenant is not None:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)
            self.fields['category'].queryset = Category.objects.filter(tenant=tenant)
        else:
            self.fields['warehouse'].queryset = Warehouse.objects.none()
            self.fields['category'].queryset = Category.objects.none()


# ─────────────────────────────────────────────────────────────────────────────
# Mixins for common param clusters
# ─────────────────────────────────────────────────────────────────────────────

class AsOfDateMixin(forms.Form):
    as_of_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text='Defaults to today.',
    )


class PeriodMixin(forms.Form):
    period_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    period_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get('period_start')
        e = cleaned.get('period_end')
        if s and e and e < s:
            raise forms.ValidationError('Period end must be on or after period start.')
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Inventory & Stock
# ─────────────────────────────────────────────────────────────────────────────

class ValuationForm(AsOfDateMixin, BaseReportForm):
    pass


class AgingForm(AsOfDateMixin, BaseReportForm):
    dead_stock_days = forms.IntegerField(
        required=False, initial=180, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='Days since last movement to classify as dead stock (default: 180).',
    )


class ABCForm(PeriodMixin, BaseReportForm):
    a_threshold = forms.IntegerField(
        initial=80, min_value=1, max_value=99,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='Class A cumulative % threshold (default: 80).',
    )
    b_threshold = forms.IntegerField(
        initial=15, min_value=1, max_value=99,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='Class B cumulative % threshold (default: 15).',
    )

    def clean(self):
        cleaned = super().clean()
        a = cleaned.get('a_threshold') or 0
        b = cleaned.get('b_threshold') or 0
        if a + b >= 100:
            raise forms.ValidationError('a_threshold + b_threshold must be less than 100.')
        return cleaned


class TurnoverForm(PeriodMixin, BaseReportForm):
    pass


class ReservationsForm(BaseReportForm):
    STATUS_CHOICES = [
        ('', 'All statuses'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('released', 'Released'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]
    status = forms.ChoiceField(
        choices=STATUS_CHOICES, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class MultiLocationForm(BaseReportForm):
    # No extra params — warehouse/category already in base + the report
    # walks the Location hierarchy internally.
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Procurement
# ─────────────────────────────────────────────────────────────────────────────

class POSummaryForm(PeriodMixin, BaseReportForm):
    vendor = forms.ModelChoiceField(
        queryset=None, required=False, empty_label='All vendors',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    status = forms.CharField(
        required=False, max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'draft, approved, sent, received, closed'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, tenant=tenant, **kwargs)
        try:
            from vendors.models import Vendor
            self.fields['vendor'].queryset = Vendor.objects.filter(tenant=tenant) if tenant else Vendor.objects.none()
        except ImportError:
            self.fields['vendor'].queryset = self.fields['vendor'].queryset or []


class VendorPerformanceForm(PeriodMixin, BaseReportForm):
    pass


class ThreeWayMatchForm(PeriodMixin, BaseReportForm):
    status = forms.CharField(
        required=False, max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'match / variance / mismatch'}),
    )


class ReceivingGRNForm(PeriodMixin, BaseReportForm):
    vendor = forms.ModelChoiceField(
        queryset=None, required=False, empty_label='All vendors',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, tenant=tenant, **kwargs)
        try:
            from vendors.models import Vendor
            self.fields['vendor'].queryset = Vendor.objects.filter(tenant=tenant) if tenant else Vendor.objects.none()
        except ImportError:
            self.fields['vendor'].queryset = self.fields['vendor'].queryset or []


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Warehouse Ops
# ─────────────────────────────────────────────────────────────────────────────

class StockTransfersForm(PeriodMixin, BaseReportForm):
    status = forms.CharField(
        required=False, max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'draft / pending / approved / in_transit / completed'}),
    )


class StocktakeVarianceForm(PeriodMixin, BaseReportForm):
    pass


class QualityControlForm(PeriodMixin, BaseReportForm):
    pass


class ScrapWriteoffForm(PeriodMixin, BaseReportForm):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Sales & Fulfillment
# ─────────────────────────────────────────────────────────────────────────────

class SOSummaryForm(PeriodMixin, BaseReportForm):
    status = forms.CharField(
        required=False, max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'draft / confirmed / shipped / delivered / closed'}),
    )


class FulfillmentForm(PeriodMixin, BaseReportForm):
    pass


class ShipmentCarrierForm(PeriodMixin, BaseReportForm):
    carrier = forms.ModelChoiceField(
        queryset=None, required=False, empty_label='All carriers',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, tenant=tenant, **kwargs)
        try:
            from orders.models import Carrier
            self.fields['carrier'].queryset = Carrier.objects.filter(tenant=tenant) if tenant else Carrier.objects.none()
        except ImportError:
            self.fields['carrier'].queryset = self.fields['carrier'].queryset or []


class ReturnsRMAForm(PeriodMixin, BaseReportForm):
    status = forms.CharField(
        required=False, max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'draft / pending / approved / received / closed'}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: Tracking & Ops
# ─────────────────────────────────────────────────────────────────────────────

class LotExpiryForm(AsOfDateMixin, BaseReportForm):
    days_ahead = forms.IntegerField(
        required=False, initial=30, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='How many days ahead to flag as approaching (default: 30).',
    )


class ForecastVsActualForm(PeriodMixin, BaseReportForm):
    pass


class AlertsLogForm(PeriodMixin, BaseReportForm):
    alert_type = forms.CharField(
        required=False, max_length=64,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'low_stock / out_of_stock / expired / ...'}),
    )
