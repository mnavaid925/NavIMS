from django import forms
from core.models import Tenant, Subscription, Role, Permission
from .models import TenantCustomization, PricingPlan


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'domain', 'is_active', 'plan']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'domain': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
        }


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = [
            'plan', 'status', 'max_users', 'max_warehouses',
            'current_period_start', 'current_period_end',
        ]
        widgets = {
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'max_users': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_warehouses': forms.NumberInput(attrs={'class': 'form-control'}),
            'current_period_start': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'current_period_end': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
        }


class TenantCustomizationForm(forms.ModelForm):
    class Meta:
        model = TenantCustomization
        fields = [
            'primary_color', 'secondary_color', 'company_address',
            'company_phone', 'company_email', 'logo', 'favicon',
        ]
        widgets = {
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'company_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'company_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'company_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'favicon': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class PricingPlanForm(forms.ModelForm):
    class Meta:
        model = PricingPlan
        exclude = ['created_at', 'updated_at']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'billing_cycle': forms.Select(attrs={'class': 'form-select'}),
            'max_users': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_warehouses': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_products': forms.NumberInput(attrs={'class': 'form-control'}),
            'features': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ['name', 'codename', 'description', 'module']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'codename': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'module': forms.Select(attrs={'class': 'form-select'}),
        }
