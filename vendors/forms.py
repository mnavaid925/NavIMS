from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from .models import Vendor, VendorPerformance, VendorContract, VendorCommunication


# File upload constraints for VendorContract.document (D-06)
CONTRACT_DOCUMENT_ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg',
}
CONTRACT_DOCUMENT_BLOCKED_CONTENT_TYPES = {
    'image/svg+xml', 'application/x-msdownload', 'application/x-sh',
    'application/x-executable', 'application/x-dosexec',
    'text/html', 'application/javascript', 'application/x-javascript',
}
CONTRACT_DOCUMENT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'company_name', 'contact_person', 'email', 'phone', 'website',
            'address_line_1', 'address_line_2', 'city', 'state', 'country', 'postal_code',
            'tax_id', 'vendor_type', 'status', 'payment_terms',
            'lead_time_days', 'minimum_order_quantity', 'notes', 'is_active',
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter company name',
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Primary contact person',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'vendor@example.com',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1 (555) 123-4567',
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.example.com',
            }),
            'address_line_1': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street address',
            }),
            'address_line_2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Suite, unit, floor (optional)',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City',
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State / Province',
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country',
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Postal / ZIP code',
            }),
            'tax_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tax ID / VAT number',
            }),
            'vendor_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'payment_terms': forms.Select(attrs={
                'class': 'form-select',
            }),
            'lead_time_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Days',
            }),
            'minimum_order_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'MOQ',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes (optional)',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_company_name(self):
        # D-01: unique_together(tenant, company_name) cannot be enforced by
        # Django's default validate_unique because 'tenant' is not a form field.
        name = (self.cleaned_data.get('company_name') or '').strip()
        if not name or self.tenant is None:
            return name
        qs = Vendor.objects.filter(tenant=self.tenant, company_name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A vendor with this company name already exists for this tenant.')
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class VendorPerformanceForm(forms.ModelForm):
    class Meta:
        model = VendorPerformance
        fields = [
            'vendor', 'review_date', 'delivery_rating', 'quality_rating', 'compliance_rating',
            'defect_rate', 'on_time_delivery_rate', 'notes',
        ]
        widgets = {
            'vendor': forms.Select(attrs={
                'class': 'form-select',
            }),
            'review_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'delivery_rating': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '5',
                'placeholder': '1-5',
            }),
            'quality_rating': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '5',
                'placeholder': '1-5',
            }),
            'compliance_rating': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '5',
                'placeholder': '1-5',
            }),
            'defect_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '%',
            }),
            'on_time_delivery_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '%',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Review notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['vendor'].queryset = Vendor.objects.filter(tenant=tenant, is_active=True)
            self.fields['vendor'].empty_label = '— Select Vendor —'

    def clean_review_date(self):
        # D-05: review_date cannot be in the future (a review is for work already done).
        value = self.cleaned_data.get('review_date')
        if value and value > date.today():
            raise ValidationError('Review date cannot be in the future.')
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class VendorContractForm(forms.ModelForm):
    class Meta:
        model = VendorContract
        fields = [
            'vendor', 'contract_number', 'title', 'start_date', 'end_date',
            'payment_terms', 'lead_time_days', 'moq', 'contract_value',
            'status', 'document', 'notes',
        ]
        widgets = {
            'vendor': forms.Select(attrs={
                'class': 'form-select',
            }),
            'contract_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CON-001',
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contract title',
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_terms': forms.Select(attrs={
                'class': 'form-select',
            }),
            'lead_time_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Days',
            }),
            'moq': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'MOQ',
            }),
            'contract_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'document': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Contract notes (optional)',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['vendor'].queryset = Vendor.objects.filter(tenant=tenant, is_active=True)
            self.fields['vendor'].empty_label = '— Select Vendor —'

    def clean_contract_number(self):
        # D-02: unique_together(tenant, contract_number) trap — same pattern as D-01.
        number = (self.cleaned_data.get('contract_number') or '').strip()
        if not number or self.tenant is None:
            return number
        qs = VendorContract.objects.filter(tenant=self.tenant, contract_number__iexact=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A contract with this number already exists for this tenant.')
        return number

    def clean_document(self):
        # D-06: whitelist extensions, cap size, block dangerous content types.
        doc = self.cleaned_data.get('document')
        if not doc:
            return doc
        name = getattr(doc, 'name', '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext not in CONTRACT_DOCUMENT_ALLOWED_EXTENSIONS:
            raise ValidationError(
                f'File type ".{ext}" is not allowed. Allowed types: '
                f'{", ".join(sorted(CONTRACT_DOCUMENT_ALLOWED_EXTENSIONS))}.'
            )
        content_type = getattr(doc, 'content_type', '') or ''
        if content_type.lower() in CONTRACT_DOCUMENT_BLOCKED_CONTENT_TYPES:
            raise ValidationError(f'Content type "{content_type}" is not allowed.')
        size = getattr(doc, 'size', 0) or 0
        if size > CONTRACT_DOCUMENT_MAX_SIZE:
            raise ValidationError(
                f'File is too large ({size // 1024 // 1024} MB). '
                f'Maximum allowed size is {CONTRACT_DOCUMENT_MAX_SIZE // 1024 // 1024} MB.'
            )
        return doc

    def clean(self):
        # D-03: end_date must be after start_date when both provided.
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end <= start:
            raise ValidationError({'end_date': 'End date must be after the start date.'})
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class VendorCommunicationForm(forms.ModelForm):
    class Meta:
        model = VendorCommunication
        fields = [
            'vendor', 'communication_type', 'subject', 'message',
            'contact_person', 'communication_date',
        ]
        widgets = {
            'vendor': forms.Select(attrs={
                'class': 'form-select',
            }),
            'communication_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Message or notes...',
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Contact person (optional)',
            }),
            'communication_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['vendor'].queryset = Vendor.objects.filter(tenant=tenant, is_active=True)
            self.fields['vendor'].empty_label = '— Select Vendor —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
