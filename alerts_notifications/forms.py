from django import forms

from core.forms import TenantUniqueCodeMixin
from core.models import User

from .models import Alert, NotificationRule


class AlertForm(forms.ModelForm):
    """Manual alert create/edit form (most alerts are scanner-generated, but
    tenant admins may log ad-hoc alerts too)."""

    class Meta:
        model = Alert
        fields = [
            'alert_type', 'severity', 'title', 'message',
            'product', 'warehouse',
            'threshold_value', 'current_value', 'notes',
        ]
        widgets = {
            'alert_type': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Low stock on SKU-123'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'threshold_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'current_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            from catalog.models import Product
            from warehousing.models import Warehouse
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, is_active=True)
            self.fields['product'].required = False
            self.fields['product'].empty_label = '— No specific product —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].required = False
            self.fields['warehouse'].empty_label = '— No specific warehouse —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class NotificationRuleForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = NotificationRule
        fields = [
            'code', 'name', 'description',
            'alert_type', 'min_severity',
            'notify_email', 'notify_inbox',
            'recipient_users', 'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto: NR-00001'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Critical stock alerts → warehouse managers'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'alert_type': forms.Select(attrs={'class': 'form-select'}),
            'min_severity': forms.Select(attrs={'class': 'form-select'}),
            'notify_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_inbox': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recipient_users': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False
        if tenant:
            self.fields['recipient_users'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            ).order_by('username')
            self.fields['recipient_users'].required = False

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AlertResolveForm(forms.Form):
    """Optional notes when resolving/dismissing an alert.

    D-04: max_length caps per-submission size; view-layer also truncates the
    combined alert.notes to prevent unbounded growth across many resolve cycles.
    """
    notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Resolution notes (optional, max 2000 chars)'}),
    )
