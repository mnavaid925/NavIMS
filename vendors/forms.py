from django import forms
from .models import Vendor, VendorPerformance, VendorContract, VendorCommunication


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
            'review_date', 'delivery_rating', 'quality_rating', 'compliance_rating',
            'defect_rate', 'on_time_delivery_rate', 'notes',
        ]
        widgets = {
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
                'rows': 2,
                'placeholder': 'Review notes (optional)',
            }),
        }


class VendorContractForm(forms.ModelForm):
    class Meta:
        model = VendorContract
        fields = [
            'contract_number', 'title', 'start_date', 'end_date',
            'payment_terms', 'lead_time_days', 'moq', 'contract_value',
            'status', 'document', 'notes',
        ]
        widgets = {
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
                'rows': 2,
                'placeholder': 'Contract notes (optional)',
            }),
        }


class VendorCommunicationForm(forms.ModelForm):
    class Meta:
        model = VendorCommunication
        fields = [
            'communication_type', 'subject', 'message',
            'contact_person', 'communication_date',
        ]
        widgets = {
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
