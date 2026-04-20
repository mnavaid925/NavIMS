from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from core.forms import TenantUniqueCodeMixin
from catalog.models import Category, Product
from vendors.models import Vendor
from warehousing.models import Warehouse, Zone
from receiving.models import GoodsReceiptNote
from lot_tracking.models import LotBatch, SerialNumber

from .models import (
    QCChecklist, QCChecklistItem,
    InspectionRoute, InspectionRouteRule,
    QuarantineRecord,
    DefectReport, DefectPhoto,
    ScrapWriteOff,
)


def _include_current(base_qs, instance, fk_name):
    """D-04 helper: widen a tenant-scoped, active-filtered FK queryset so that
    the FK value currently assigned to ``instance`` is always selectable — even
    if it has since been deactivated (or soft-deleted). Without this, editing
    a historical record whose FK target was later `is_active=False` raises
    ``"Select a valid choice. That choice is not one of the available choices."``
    """
    if instance is None or instance.pk is None:
        return base_qs
    current_id = getattr(instance, f'{fk_name}_id', None)
    if not current_id:
        return base_qs
    extra = base_qs.model.objects.filter(pk=current_id)
    return (base_qs | extra).distinct()


# ──────────────────────────────────────────────
# Submodule 1: QC Checklists
# ──────────────────────────────────────────────

class QCChecklistForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = QCChecklist
        fields = [
            'code', 'name', 'description', 'applies_to',
            'product', 'vendor', 'category',
            'is_mandatory', 'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto: QCC-00001'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Electronics receiving checklist'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'applies_to': forms.Select(attrs={'class': 'form-select'}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False
        if tenant:
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['product'].required = False
            self.fields['product'].empty_label = '— No specific product —'
            self.fields['vendor'].queryset = _include_current(
                Vendor.objects.filter(tenant=tenant),
                self.instance, 'vendor',
            )
            self.fields['vendor'].required = False
            self.fields['vendor'].empty_label = '— No specific vendor —'
            self.fields['category'].queryset = _include_current(
                Category.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'category',
            )
            self.fields['category'].required = False
            self.fields['category'].empty_label = '— No specific category —'

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def clean(self):
        cleaned = super().clean()
        applies_to = cleaned.get('applies_to')
        if applies_to == 'product' and not cleaned.get('product'):
            self.add_error('product', 'Select a product when applies-to is "Specific Product".')
        if applies_to == 'vendor' and not cleaned.get('vendor'):
            self.add_error('vendor', 'Select a vendor when applies-to is "Specific Vendor".')
        if applies_to == 'category' and not cleaned.get('category'):
            self.add_error('category', 'Select a category when applies-to is "Specific Category".')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class QCChecklistItemForm(forms.ModelForm):
    class Meta:
        model = QCChecklistItem
        fields = ['sequence', 'check_name', 'check_type', 'expected_value', 'is_critical']
        widgets = {
            'sequence': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1'}),
            'check_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'check_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'expected_value': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'is_critical': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)


QCChecklistItemFormSet = inlineformset_factory(
    QCChecklist, QCChecklistItem,
    form=QCChecklistItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Submodule 2: Inspection Routing
# ──────────────────────────────────────────────

class InspectionRouteForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = InspectionRoute
        fields = [
            'code', 'name', 'source_warehouse', 'qc_zone', 'putaway_zone',
            'priority', 'is_active', 'notes',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto: IR-00001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'source_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'qc_zone': forms.Select(attrs={'class': 'form-select'}),
            'putaway_zone': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '1000'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False
        if tenant:
            self.fields['source_warehouse'].queryset = _include_current(
                Warehouse.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'source_warehouse',
            )
            self.fields['source_warehouse'].empty_label = '— Select Warehouse —'
            self.fields['qc_zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['qc_zone'].empty_label = '— Select QC Zone —'
            self.fields['putaway_zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['putaway_zone'].empty_label = '— No default putaway zone —'
            self.fields['putaway_zone'].required = False

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def clean(self):
        cleaned = super().clean()
        wh = cleaned.get('source_warehouse')
        qc_zone = cleaned.get('qc_zone')
        putaway_zone = cleaned.get('putaway_zone')
        if wh and qc_zone and qc_zone.warehouse_id != wh.pk:
            self.add_error('qc_zone', f'QC zone "{qc_zone.name}" does not belong to warehouse "{wh.name}".')
        if wh and putaway_zone and putaway_zone.warehouse_id != wh.pk:
            self.add_error('putaway_zone', f'Putaway zone "{putaway_zone.name}" does not belong to warehouse "{wh.name}".')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class InspectionRouteRuleForm(forms.ModelForm):
    class Meta:
        model = InspectionRouteRule
        fields = ['applies_to', 'product', 'vendor', 'category', 'checklist', 'notes']
        widgets = {
            'applies_to': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'vendor': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'category': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'checklist': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['product'].required = False
            self.fields['product'].empty_label = '—'
            self.fields['vendor'].queryset = _include_current(
                Vendor.objects.filter(tenant=tenant),
                self.instance, 'vendor',
            )
            self.fields['vendor'].required = False
            self.fields['vendor'].empty_label = '—'
            self.fields['category'].queryset = _include_current(
                Category.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'category',
            )
            self.fields['category'].required = False
            self.fields['category'].empty_label = '—'
            self.fields['checklist'].queryset = _include_current(
                QCChecklist.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'checklist',
            )
            self.fields['checklist'].required = False
            self.fields['checklist'].empty_label = '— No checklist —'

    def clean(self):
        # D-08: if the rule is scoped, the corresponding FK must be populated.
        cleaned = super().clean()
        # Skip completely-blank extra formset rows — nothing to validate.
        if not any(
            cleaned.get(f) for f in ('applies_to', 'product', 'vendor', 'category', 'checklist', 'notes')
        ):
            return cleaned
        applies_to = cleaned.get('applies_to')
        if applies_to == 'product' and not cleaned.get('product'):
            self.add_error('product', 'Select a product when scope is "Specific Product".')
        if applies_to == 'vendor' and not cleaned.get('vendor'):
            self.add_error('vendor', 'Select a vendor when scope is "Specific Vendor".')
        if applies_to == 'category' and not cleaned.get('category'):
            self.add_error('category', 'Select a category when scope is "Specific Category".')
        return cleaned


InspectionRouteRuleFormSet = inlineformset_factory(
    InspectionRoute, InspectionRouteRule,
    form=InspectionRouteRuleForm,
    extra=2,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Submodule 3: Quarantine Management
# ──────────────────────────────────────────────

class QuarantineRecordForm(forms.ModelForm):
    class Meta:
        model = QuarantineRecord
        fields = [
            'product', 'warehouse', 'zone', 'quantity',
            'reason', 'reason_notes', 'grn', 'lot',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'reason_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'lot': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['warehouse'].queryset = _include_current(
                Warehouse.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'warehouse',
            )
            self.fields['zone'].queryset = Zone.objects.filter(tenant=tenant)
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(tenant=tenant)
            self.fields['grn'].required = False
            self.fields['grn'].empty_label = '— No source GRN —'
            self.fields['lot'].queryset = LotBatch.objects.filter(tenant=tenant)
            self.fields['lot'].required = False
            self.fields['lot'].empty_label = '— No lot —'

    def clean(self):
        cleaned = super().clean()
        wh = cleaned.get('warehouse')
        zone = cleaned.get('zone')
        qty = cleaned.get('quantity')
        if wh and zone and zone.warehouse_id != wh.pk:
            self.add_error('zone', f'Zone "{zone.name}" does not belong to warehouse "{wh.name}".')
        if qty is not None and qty < 1:
            self.add_error('quantity', 'Quantity must be at least 1.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class QuarantineReleaseForm(forms.Form):
    disposition = forms.ChoiceField(
        choices=QuarantineRecord.DISPOSITION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


# ──────────────────────────────────────────────
# Submodule 4: Defect & Scrap Reporting
# ──────────────────────────────────────────────

class DefectReportForm(forms.ModelForm):
    class Meta:
        model = DefectReport
        fields = [
            'product', 'lot', 'serial', 'warehouse',
            'quantity_affected', 'defect_type', 'severity',
            'description', 'source', 'grn', 'quarantine_record',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'lot': forms.Select(attrs={'class': 'form-select'}),
            'serial': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity_affected': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'defect_type': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'grn': forms.Select(attrs={'class': 'form-select'}),
            'quarantine_record': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['warehouse'].queryset = _include_current(
                Warehouse.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'warehouse',
            )
            self.fields['lot'].queryset = LotBatch.objects.filter(tenant=tenant)
            self.fields['lot'].required = False
            self.fields['lot'].empty_label = '— No lot —'
            self.fields['serial'].queryset = SerialNumber.objects.filter(tenant=tenant)
            self.fields['serial'].required = False
            self.fields['serial'].empty_label = '— No serial —'
            self.fields['grn'].queryset = GoodsReceiptNote.objects.filter(tenant=tenant)
            self.fields['grn'].required = False
            self.fields['grn'].empty_label = '— No GRN —'
            self.fields['quarantine_record'].queryset = _include_current(
                QuarantineRecord.objects.filter(tenant=tenant, deleted_at__isnull=True),
                self.instance, 'quarantine_record',
            )
            self.fields['quarantine_record'].required = False
            self.fields['quarantine_record'].empty_label = '— Not linked —'

    def clean_quantity_affected(self):
        qty = self.cleaned_data.get('quantity_affected')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity affected must be at least 1.')
        return qty

    def clean(self):
        # D-07: lot/serial must reference the same product as the defect.
        cleaned = super().clean()
        product = cleaned.get('product')
        lot = cleaned.get('lot')
        serial = cleaned.get('serial')
        if product and lot and getattr(lot, 'product_id', None) and lot.product_id != product.pk:
            self.add_error(
                'lot',
                f'Lot "{lot}" belongs to a different product than the selected product.',
            )
        if product and serial and getattr(serial, 'product_id', None) and serial.product_id != product.pk:
            self.add_error(
                'serial',
                f'Serial "{serial}" belongs to a different product than the selected product.',
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class DefectPhotoForm(forms.ModelForm):
    class Meta:
        model = DefectPhoto
        fields = ['image', 'caption']
        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control form-control-sm',
                'accept': 'image/jpeg,image/png,image/gif,image/webp',
            }),
            'caption': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Caption'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_image(self):
        # D-03: route every upload through the model-level validators (size,
        # extension, magic-bytes). The ImageField validators run on save, but
        # we also want form-layer rejection so inline-formset errors surface
        # before the instance reaches save().
        image = self.cleaned_data.get('image')
        if image and getattr(image, 'file', None):
            from .models import (
                DEFECT_PHOTO_ALLOWED_EXT,
                validate_defect_photo_size,
                validate_defect_photo_magic,
            )
            from django.core.validators import FileExtensionValidator
            FileExtensionValidator(allowed_extensions=DEFECT_PHOTO_ALLOWED_EXT)(image)
            validate_defect_photo_size(image)
            validate_defect_photo_magic(image)
        return image


DefectPhotoFormSet = inlineformset_factory(
    DefectReport, DefectPhoto,
    form=DefectPhotoForm,
    extra=3,
    can_delete=True,
)


class ScrapWriteOffForm(forms.ModelForm):
    class Meta:
        model = ScrapWriteOff
        fields = [
            'product', 'warehouse', 'quantity', 'unit_cost',
            'reason', 'defect_report', 'quarantine_record',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'defect_report': forms.Select(attrs={'class': 'form-select'}),
            'quarantine_record': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['warehouse'].queryset = _include_current(
                Warehouse.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'warehouse',
            )
            self.fields['defect_report'].queryset = _include_current(
                DefectReport.objects.filter(tenant=tenant, deleted_at__isnull=True),
                self.instance, 'defect_report',
            )
            self.fields['defect_report'].required = False
            self.fields['defect_report'].empty_label = '— No defect report —'
            self.fields['quarantine_record'].queryset = _include_current(
                QuarantineRecord.objects.filter(tenant=tenant, deleted_at__isnull=True),
                self.instance, 'quarantine_record',
            )
            self.fields['quarantine_record'].required = False
            self.fields['quarantine_record'].empty_label = '— No quarantine record —'

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean_unit_cost(self):
        cost = self.cleaned_data.get('unit_cost')
        if cost is not None and cost < 0:
            raise ValidationError('Unit cost cannot be negative.')
        return cost

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
