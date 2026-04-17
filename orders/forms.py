from datetime import timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from core.forms import TenantUniqueCodeMixin
from core.models import User
from .models import (
    SalesOrder, SalesOrderItem, PickList, PickListItem,
    PackingList, Shipment, ShipmentTracking, WavePlan,
    Carrier, ShippingRate,
)


# ──────────────────────────────────────────────
# Sales Order Forms
# ──────────────────────────────────────────────

class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = [
            'customer_name', 'customer_email', 'customer_phone',
            'shipping_address', 'billing_address',
            'order_date', 'required_date', 'warehouse', 'priority', 'notes',
        ]
        widgets = {
            'customer_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Customer full name',
            }),
            'customer_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'customer@example.com',
            }),
            'customer_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1 (555) 000-0000',
            }),
            'shipping_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Shipping address',
            }),
            'billing_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Billing address (optional)',
            }),
            'order_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'required_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'warehouse': forms.Select(attrs={
                'class': 'form-select',
            }),
            'priority': forms.Select(attrs={
                'class': 'form-select',
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
            self.fields['warehouse'].queryset = Warehouse.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def clean(self):
        cleaned = super().clean()
        order_date = cleaned.get('order_date')
        required_date = cleaned.get('required_date')
        if order_date and required_date and required_date < order_date:
            self.add_error(
                'required_date',
                'Required delivery date cannot be earlier than order date.',
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
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

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant, status='active',
            )
            self.fields['product'].empty_label = '— Select Product —'

    def clean_quantity(self):
        value = self.cleaned_data.get('quantity')
        if value is not None and value < 1:
            raise ValidationError('Quantity must be at least 1.')
        return value

    def clean_unit_price(self):
        value = self.cleaned_data.get('unit_price')
        if value is not None and value < Decimal('0'):
            raise ValidationError('Unit price cannot be negative.')
        return value

    def clean_tax_rate(self):
        value = self.cleaned_data.get('tax_rate')
        if value is None:
            return value
        if value < Decimal('0') or value > Decimal('100'):
            raise ValidationError('Tax rate must be between 0 and 100.')
        return value

    def clean_discount(self):
        value = self.cleaned_data.get('discount')
        if value is not None and value < Decimal('0'):
            raise ValidationError('Discount cannot be negative.')
        return value


SalesOrderItemFormSet = inlineformset_factory(
    SalesOrder,
    SalesOrderItem,
    form=SalesOrderItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Pick List Forms
# ──────────────────────────────────────────────

class PickListForm(forms.ModelForm):
    class Meta:
        model = PickList
        fields = ['sales_order', 'warehouse', 'assigned_to', 'notes']
        widgets = {
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Pick list notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant, status__in=['confirmed', 'in_fulfillment'],
            )
            self.fields['sales_order'].empty_label = '— Select Sales Order —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['assigned_to'].queryset = User.objects.filter(tenant=tenant)
            self.fields['assigned_to'].empty_label = '— Assign Picker (optional) —'
            self.fields['assigned_to'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class PickListItemForm(forms.ModelForm):
    class Meta:
        model = PickListItem
        fields = ['product', 'bin_location', 'ordered_quantity', 'picked_quantity', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'bin_location': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'ordered_quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '0',
                'placeholder': 'Ordered',
            }),
            'picked_quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': '0',
                'placeholder': 'Picked',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Notes',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant, status='active',
            )
            self.fields['product'].empty_label = '— Select Product —'
            self.fields['bin_location'].queryset = Bin.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['bin_location'].empty_label = '— Select Bin (optional) —'
            self.fields['bin_location'].required = False

    def clean(self):
        cleaned = super().clean()
        ordered = cleaned.get('ordered_quantity') or 0
        picked = cleaned.get('picked_quantity') or 0
        if picked > ordered:
            self.add_error(
                'picked_quantity',
                'Picked quantity cannot exceed ordered quantity.',
            )
        return cleaned


PickListItemFormSet = inlineformset_factory(
    PickList,
    PickListItem,
    form=PickListItemForm,
    extra=3,
    can_delete=True,
)


class PickListAssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='— Select Picker —',
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['assigned_to'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )


# ──────────────────────────────────────────────
# Packing List Forms
# ──────────────────────────────────────────────

class PackingListForm(forms.ModelForm):
    class Meta:
        model = PackingList
        fields = [
            'pick_list', 'sales_order', 'packaging_type',
            'total_weight', 'length', 'width', 'height', 'notes',
        ]
        widgets = {
            'pick_list': forms.Select(attrs={'class': 'form-select'}),
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'packaging_type': forms.Select(attrs={'class': 'form-select'}),
            'total_weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Weight (kg)',
            }),
            'length': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Length (cm)',
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Width (cm)',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Height (cm)',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Packing notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['pick_list'].queryset = PickList.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['pick_list'].empty_label = '— Select Completed Pick List —'
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant, status__in=['in_fulfillment', 'picked'],
            )
            self.fields['sales_order'].empty_label = '— Select Sales Order —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Shipment Forms
# ──────────────────────────────────────────────

class ShipmentForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = [
            'sales_order', 'packing_list', 'carrier', 'service_level',
            'tracking_number', 'estimated_delivery_date', 'shipping_cost', 'notes',
        ]
        widgets = {
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'packing_list': forms.Select(attrs={'class': 'form-select'}),
            'carrier': forms.Select(attrs={'class': 'form-select'}),
            'service_level': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Ground, Express, Overnight',
            }),
            'tracking_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Carrier tracking number',
            }),
            'estimated_delivery_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'shipping_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Shipment notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant, status__in=['packed', 'shipped'],
            )
            self.fields['sales_order'].empty_label = '— Select Sales Order —'
            self.fields['packing_list'].queryset = PackingList.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['packing_list'].empty_label = '— Select Packing List (optional) —'
            self.fields['packing_list'].required = False
            self.fields['carrier'].queryset = Carrier.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['carrier'].empty_label = '— Select Carrier (optional) —'
            self.fields['carrier'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ShipmentTrackingForm(forms.ModelForm):
    class Meta:
        model = ShipmentTracking
        fields = ['status', 'location', 'description', 'event_date']
        widgets = {
            'status': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., In Transit, Out for Delivery',
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., New York, NY',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Tracking event description',
            }),
            'event_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
        }

    def clean_event_date(self):
        value = self.cleaned_data.get('event_date')
        if value and value > timezone.now() + timedelta(days=1):
            raise ValidationError('Event date cannot be in the future.')
        return value


# ──────────────────────────────────────────────
# Wave Planning Forms
# ──────────────────────────────────────────────

class WavePlanForm(forms.ModelForm):
    class Meta:
        model = WavePlan
        fields = [
            'warehouse', 'priority',
            'order_date_from', 'order_date_to', 'notes',
        ]
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'order_date_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'order_date_to': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Wave notes (optional)',
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class WaveOrderSelectionForm(forms.Form):
    orders = forms.ModelMultipleChoiceField(
        queryset=SalesOrder.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
    )

    def __init__(self, *args, tenant=None, warehouse=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = SalesOrder.objects.filter(tenant=tenant, status='confirmed')
        if warehouse:
            qs = qs.filter(warehouse=warehouse)
        self.fields['orders'].queryset = qs


# ──────────────────────────────────────────────
# Carrier & Shipping Rate Forms
# ──────────────────────────────────────────────

class CarrierForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = Carrier
        fields = [
            'name', 'code', 'contact_email', 'contact_phone',
            'api_endpoint', 'api_key', 'is_active', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FedEx, UPS, DHL',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FEDEX, UPS',
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'carrier@example.com',
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1 (555) 000-0000',
            }),
            'api_endpoint': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://api.carrier.com/v1/ (optional)',
            }),
            'api_key': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'API key (optional)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ShippingRateForm(forms.ModelForm):
    class Meta:
        model = ShippingRate
        fields = [
            'carrier', 'service_level', 'origin_region', 'destination_region',
            'base_cost', 'cost_per_kg', 'estimated_transit_days', 'is_active',
        ]
        widgets = {
            'carrier': forms.Select(attrs={'class': 'form-select'}),
            'service_level': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Ground, 2-Day, Overnight',
            }),
            'origin_region': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., US-East, Europe',
            }),
            'destination_region': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., US-West, Asia',
            }),
            'base_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'cost_per_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'estimated_transit_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Days',
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
            self.fields['carrier'].queryset = Carrier.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['carrier'].empty_label = '— Select Carrier —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
