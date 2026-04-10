from django import forms

from catalog.models import Product
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if not instance.available_quantity:
            instance.available_quantity = instance.quantity
        if commit:
            instance.save()
        return instance


class SerialNumberForm(forms.ModelForm):
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
            self.fields['lot'].queryset = LotBatch.objects.filter(tenant=tenant, status='active')
            self.fields['lot'].empty_label = '— Select Lot (optional) —'
            self.fields['lot'].required = False
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

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
            raise forms.ValidationError('At least one of Lot or Serial Number is required.')
        return cleaned_data
