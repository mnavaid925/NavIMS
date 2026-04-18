from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from core.forms import TenantUniqueCodeMixin
from warehousing.models import Warehouse, Zone
from .models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)


# ──────────────────────────────────────────────
# Submodule 1: Label Generation
# ──────────────────────────────────────────────

class LabelTemplateForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = LabelTemplate
        fields = [
            'name', 'code', 'label_type', 'symbology', 'paper_size',
            'width_mm', 'height_mm',
            'includes_name', 'includes_price', 'includes_sku', 'includes_date',
            'copies_per_label', 'is_active', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Standard Product Label'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. LBL-PROD'}),
            'label_type': forms.Select(attrs={'class': 'form-select'}),
            'symbology': forms.Select(attrs={'class': 'form-select'}),
            'paper_size': forms.Select(attrs={'class': 'form-select'}),
            'width_mm': forms.NumberInput(attrs={'class': 'form-control', 'min': '10', 'max': '300'}),
            'height_mm': forms.NumberInput(attrs={'class': 'form-control', 'min': '10', 'max': '300'}),
            'copies_per_label': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '100'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'includes_name': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'includes_price': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'includes_sku': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'includes_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class LabelPrintJobForm(forms.ModelForm):
    class Meta:
        model = LabelPrintJob
        fields = ['template', 'target_type', 'target_id', 'target_display', 'quantity', 'notes']
        widgets = {
            'template': forms.Select(attrs={'class': 'form-select'}),
            'target_type': forms.Select(attrs={'class': 'form-select'}),
            'target_id': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'target_display': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Widget A — SKU-001'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10000'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['template'].queryset = LabelTemplate.objects.filter(tenant=tenant, is_active=True)
            self.fields['template'].empty_label = '— Select Template —'

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Submodule 2: Scanner Devices
# ──────────────────────────────────────────────

class ScannerDeviceForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'device_code'

    class Meta:
        model = ScannerDevice
        fields = [
            'device_code', 'name', 'device_type', 'manufacturer', 'model_number',
            'os_version', 'firmware_version', 'assigned_to', 'assigned_warehouse',
            'status', 'battery_level_percent', 'is_active', 'notes',
        ]
        widgets = {
            'device_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SCAN-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'device_type': forms.Select(attrs={'class': 'form-select'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control'}),
            'model_number': forms.TextInput(attrs={'class': 'form-control'}),
            'os_version': forms.TextInput(attrs={'class': 'form-control'}),
            'firmware_version': forms.TextInput(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'assigned_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'battery_level_percent': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            from core.models import User
            self.fields['assigned_to'].queryset = User.objects.filter(tenant=tenant, is_active=True)
            self.fields['assigned_to'].empty_label = '— Unassigned —'
            self.fields['assigned_to'].required = False
            self.fields['assigned_warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['assigned_warehouse'].empty_label = '— No warehouse —'
            self.fields['assigned_warehouse'].required = False

    def clean_device_code(self):
        return self._clean_tenant_unique_field('device_code')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Submodule 3: RFID Tag / Reader
# ──────────────────────────────────────────────

class RFIDTagForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'epc_code'

    class Meta:
        model = RFIDTag
        fields = [
            'epc_code', 'tag_type', 'frequency_band',
            'linked_object_type', 'linked_object_id', 'linked_display',
            'status', 'battery_voltage', 'notes',
        ]
        widgets = {
            'epc_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. E20034120123456789ABCDEF'}),
            'tag_type': forms.Select(attrs={'class': 'form-select'}),
            'frequency_band': forms.Select(attrs={'class': 'form-select'}),
            'linked_object_type': forms.Select(attrs={'class': 'form-select'}),
            'linked_object_id': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'linked_display': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'battery_voltage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '9.99'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_epc_code(self):
        return self._clean_tenant_unique_field('epc_code')

    def clean(self):
        cleaned = super().clean()
        tag_type = cleaned.get('tag_type')
        battery = cleaned.get('battery_voltage')
        if tag_type == 'passive' and battery:
            self.add_error('battery_voltage', 'Passive tags do not have a battery.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class RFIDReaderForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'reader_code'

    class Meta:
        model = RFIDReader
        fields = [
            'reader_code', 'name', 'reader_type', 'warehouse', 'zone',
            'ip_address', 'antenna_count', 'frequency_band',
            'status', 'firmware_version', 'is_active', 'notes',
        ]
        widgets = {
            'reader_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. RDR-GATE-01'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'reader_type': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control'}),
            'antenna_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '16'}),
            'frequency_band': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'firmware_version': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['zone'].empty_label = '— Any zone —'
            self.fields['zone'].required = False

    def clean_reader_code(self):
        return self._clean_tenant_unique_field('reader_code')

    def clean(self):
        cleaned = super().clean()
        warehouse = cleaned.get('warehouse')
        zone = cleaned.get('zone')
        if warehouse and zone and zone.warehouse_id != warehouse.pk:
            self.add_error('zone', f'Zone "{zone.name}" does not belong to warehouse "{warehouse.name}".')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ──────────────────────────────────────────────
# Submodule 4: Batch Scanning
# ──────────────────────────────────────────────

class BatchScanSessionForm(forms.ModelForm):
    class Meta:
        model = BatchScanSession
        fields = ['purpose', 'device', 'warehouse', 'zone', 'notes']
        widgets = {
            'purpose': forms.Select(attrs={'class': 'form-select'}),
            'device': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['device'].queryset = ScannerDevice.objects.filter(tenant=tenant, is_active=True)
            self.fields['device'].empty_label = '— Any device —'
            self.fields['device'].required = False
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'
            self.fields['zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['zone'].empty_label = '— Any zone —'
            self.fields['zone'].required = False

    def clean(self):
        cleaned = super().clean()
        warehouse = cleaned.get('warehouse')
        zone = cleaned.get('zone')
        if warehouse and zone and zone.warehouse_id != warehouse.pk:
            self.add_error('zone', f'Zone "{zone.name}" does not belong to warehouse "{warehouse.name}".')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class BatchScanItemForm(forms.ModelForm):
    class Meta:
        model = BatchScanItem
        fields = ['scanned_value', 'symbology', 'resolution_type', 'resolved_object_id', 'resolved_display', 'quantity']
        widgets = {
            'scanned_value': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Barcode/EPC'}),
            'symbology': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'resolution_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'resolved_object_id': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1'}),
            'resolved_display': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)


BatchScanItemFormSet = inlineformset_factory(
    BatchScanSession,
    BatchScanItem,
    form=BatchScanItemForm,
    extra=3,
    can_delete=True,
)
