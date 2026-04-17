from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from catalog.models import Product
from core.forms import TenantUniqueCodeMixin
from warehousing.models import Warehouse
from receiving.models import GoodsReceiptNote
from .models import LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog


class LotBatchForm(forms.ModelForm):
    class Meta:
        model = LotBatch
        fields = [
            'product', 'warehouse', 'grn', 'quantity',
            'manufacturing_date', 'expiry_date',
            'supplier_batch_number', 'notes',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'placeholder': 'Initial quantity',
            }),
            'manufacturing_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'supplier_batch_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': "Supplier's batch reference",
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
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
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(tenant=tenant)
            self.fields['grn'].empty_label = '— Select GRN (optional) —'
            self.fields['grn'].required = False

    def clean_quantity(self):
        """D-04 — quantity must be ≥ 1.
        D-13 — on edit, quantity cannot drop below available_quantity (invariant).
        """
        value = self.cleaned_data.get('quantity')
        if value is None or value < 1:
            raise ValidationError('Quantity must be at least 1.')
        if self.instance.pk and value < self.instance.available_quantity:
            raise ValidationError(
                f'Quantity ({value}) cannot be less than the available quantity '
                f'({self.instance.available_quantity}).'
            )
        return value

    def clean(self):
        """D-03 — manufacturing_date must not be after expiry_date."""
        cleaned = super().clean()
        mfg = cleaned.get('manufacturing_date')
        exp = cleaned.get('expiry_date')
        if mfg and exp and mfg > exp:
            self.add_error(
                'expiry_date',
                'Expiry date must be on or after manufacturing date.',
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if not instance.available_quantity:
            instance.available_quantity = instance.quantity
        if commit:
            instance.save()
        return instance


class SerialNumberForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'serial_number'

    class Meta:
        model = SerialNumber
        fields = [
            'serial_number', 'product', 'lot', 'warehouse',
            'purchase_date', 'warranty_expiry', 'notes',
        ]
        widgets = {
            'serial_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Enter serial number',
            }),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'lot': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'purchase_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'warranty_expiry': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].empty_label = '— Select Product —'
            # D-02 — preserve the current lot in the queryset even if its status
            # is no longer 'active', so editing a serial tied to a
            # quarantine/expired/recalled lot does not silently clear the FK.
            lot_qs = LotBatch.objects.filter(tenant=tenant, status='active')
            if self.instance.pk and self.instance.lot_id:
                lot_qs = LotBatch.objects.filter(
                    Q(tenant=tenant, status='active') | Q(pk=self.instance.lot_id)
                )
            self.fields['lot'].queryset = lot_qs.distinct()
            self.fields['lot'].empty_label = '— Select Lot (optional) —'
            self.fields['lot'].required = False
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def clean_serial_number(self):
        """D-01 — reject duplicate (tenant, serial_number) at form layer."""
        return self._clean_tenant_unique_field('serial_number')

    # Override the mixin's default `clean_code` — this model has no `code` field.
    def clean_code(self):
        return None

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ExpiryAlertAcknowledgeForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3, 'placeholder': 'Acknowledgement notes (optional)',
        }),
    )


class TraceabilityLogForm(forms.ModelForm):
    # D-10 — event types that demand a positive quantity.
    QUANTITY_REQUIRED_EVENTS = {'received', 'sold', 'scrapped', 'expired', 'adjusted'}

    class Meta:
        model = TraceabilityLog
        fields = [
            'lot', 'serial_number', 'event_type',
            'from_warehouse', 'to_warehouse', 'quantity',
            'reference_type', 'reference_number', 'notes',
        ]
        widgets = {
            'lot': forms.Select(attrs={'class': 'form-select'}),
            'serial_number': forms.Select(attrs={'class': 'form-select'}),
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'from_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Quantity (for lot movements)',
            }),
            'reference_type': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. GRN, Transfer, Sales Order',
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. GRN-00001',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['lot'].queryset = LotBatch.objects.filter(tenant=tenant)
            self.fields['lot'].empty_label = '— Select Lot (optional) —'
            self.fields['lot'].required = False
            self.fields['serial_number'].queryset = SerialNumber.objects.filter(tenant=tenant)
            self.fields['serial_number'].empty_label = '— Select Serial (optional) —'
            self.fields['serial_number'].required = False
            self.fields['from_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['from_warehouse'].empty_label = '— From Warehouse (optional) —'
            self.fields['from_warehouse'].required = False
            self.fields['to_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['to_warehouse'].empty_label = '— To Warehouse (optional) —'
            self.fields['to_warehouse'].required = False
            self.fields['quantity'].required = False

    def clean(self):
        cleaned_data = super().clean()
        lot = cleaned_data.get('lot')
        serial = cleaned_data.get('serial_number')
        if not lot and not serial:
            raise ValidationError('At least one of Lot or Serial Number is required.')

        # D-10 — event-type-specific guards.
        event_type = cleaned_data.get('event_type')
        quantity = cleaned_data.get('quantity')
        frm = cleaned_data.get('from_warehouse')
        to = cleaned_data.get('to_warehouse')

        if event_type == 'transferred':
            if not frm or not to:
                self.add_error(
                    'to_warehouse',
                    'Transfers require both From Warehouse and To Warehouse.',
                )
            elif frm == to:
                self.add_error(
                    'to_warehouse',
                    'To Warehouse must differ from From Warehouse.',
                )

        if event_type in self.QUANTITY_REQUIRED_EVENTS:
            if quantity is None or quantity <= 0:
                self.add_error(
                    'quantity',
                    f'Quantity must be a positive number for "{event_type}" events.',
                )

        return cleaned_data
