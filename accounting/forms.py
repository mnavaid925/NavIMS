"""Accounting & Financial Integration forms (Module 19).

Every ModelForm accepts `tenant=` in `__init__`; FK querysets are scoped to
that tenant at form build time (closes inline-formset tenant-injection IDOR).

Where `unique_together(tenant, <field>)` is the constraint, `TenantUniqueCodeMixin`
from `core.forms` handles the form-layer duplicate check so the DB never sees
an `IntegrityError` from a plain form submission.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from core.forms import TenantUniqueCodeMixin

from .models import (
    ChartOfAccount, FiscalPeriod, Customer,
    TaxJurisdiction, TaxRule,
    APBill, APBillLine, ARInvoice, ARInvoiceLine,
    JournalEntry, JournalLine,
)


# ──────────────────────────────────────────────────────────────────────────
# Small helper — keep the instance's current FK selection in a filtered
# queryset even if the FK target has since been deactivated (Lesson #37).
# ──────────────────────────────────────────────────────────────────────────

def _include_current(qs, instance, field):
    if instance is not None and instance.pk is not None:
        current = getattr(instance, field + '_id', None)
        if current:
            return (qs | qs.model.objects.filter(pk=current)).distinct()
    return qs


# ══════════════════════════════════════════════════════════════════════════
# Chart of Accounts
# ══════════════════════════════════════════════════════════════════════════

class ChartOfAccountForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = ChartOfAccount
        fields = ['code', 'name', 'account_type', 'parent', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 1000'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        qs = ChartOfAccount.objects.none() if tenant is None else ChartOfAccount.objects.filter(
            tenant=tenant, is_active=True,
        )
        if self.instance.pk is not None:
            qs = qs.exclude(pk=self.instance.pk)
            qs = _include_current(qs, self.instance, 'parent')
        self.fields['parent'].queryset = qs
        self.fields['parent'].required = False

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ══════════════════════════════════════════════════════════════════════════
# Fiscal Periods
# ══════════════════════════════════════════════════════════════════════════

class FiscalPeriodForm(forms.ModelForm):
    class Meta:
        model = FiscalPeriod
        fields = ['name', 'start_date', 'end_date', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control',
                                           'placeholder': 'e.g., FY2026-Q2'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        sd, ed = cleaned.get('start_date'), cleaned.get('end_date')
        if sd and ed and ed < sd:
            raise ValidationError('End date cannot be before start date.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ══════════════════════════════════════════════════════════════════════════
# Customers
# ══════════════════════════════════════════════════════════════════════════

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'company_name', 'contact_name', 'contact_email', 'contact_phone',
            'billing_address', 'country', 'state', 'city', 'postal_code',
            'tax_id', 'payment_terms', 'default_currency', 'is_active', 'notes',
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_terms': forms.Select(attrs={'class': 'form-select'}),
            'default_currency': forms.TextInput(attrs={'class': 'form-control',
                                                        'placeholder': 'USD'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ══════════════════════════════════════════════════════════════════════════
# Tax Jurisdictions
# ══════════════════════════════════════════════════════════════════════════

class TaxJurisdictionForm(TenantUniqueCodeMixin, forms.ModelForm):
    tenant_unique_field = 'code'

    class Meta:
        model = TaxJurisdiction
        fields = ['code', 'name', 'country', 'state', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., US-CA'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_code(self):
        return self._clean_tenant_unique_field('code')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ══════════════════════════════════════════════════════════════════════════
# Tax Rules
# ══════════════════════════════════════════════════════════════════════════

class TaxRuleForm(forms.ModelForm):
    class Meta:
        model = TaxRule
        fields = ['jurisdiction', 'tax_category', 'tax_rate',
                  'effective_date', 'end_date', 'description', 'is_active']
        widgets = {
            'jurisdiction': forms.Select(attrs={'class': 'form-select'}),
            'tax_category': forms.Select(attrs={'class': 'form-select'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        qs = TaxJurisdiction.objects.none() if tenant is None else TaxJurisdiction.objects.filter(
            tenant=tenant, is_active=True,
        )
        qs = _include_current(qs, self.instance, 'jurisdiction')
        self.fields['jurisdiction'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        ed = cleaned.get('effective_date')
        end = cleaned.get('end_date')
        if ed and end and end < ed:
            raise ValidationError('End date cannot be before effective date.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# ══════════════════════════════════════════════════════════════════════════
# AP Bills + inline line formset
# ══════════════════════════════════════════════════════════════════════════

class APBillForm(forms.ModelForm):
    class Meta:
        model = APBill
        fields = [
            'vendor', 'source_invoice', 'source_po', 'source_grn',
            'bill_date', 'due_date', 'currency', 'payment_terms',
            'description',
        ]
        widgets = {
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'source_invoice': forms.Select(attrs={'class': 'form-select'}),
            'source_po': forms.Select(attrs={'class': 'form-select'}),
            'source_grn': forms.Select(attrs={'class': 'form-select'}),
            'bill_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'net_30'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            for fname in ('vendor', 'source_invoice', 'source_po', 'source_grn'):
                self.fields[fname].queryset = self.fields[fname].queryset.none()
        else:
            from vendors.models import Vendor
            from receiving.models import VendorInvoice, GoodsReceiptNote
            from purchase_orders.models import PurchaseOrder
            self.fields['vendor'].queryset = _include_current(
                Vendor.objects.filter(tenant=tenant), self.instance, 'vendor',
            )
            self.fields['source_invoice'].queryset = _include_current(
                VendorInvoice.objects.filter(tenant=tenant), self.instance, 'source_invoice',
            )
            self.fields['source_po'].queryset = _include_current(
                PurchaseOrder.objects.filter(tenant=tenant), self.instance, 'source_po',
            )
            self.fields['source_grn'].queryset = _include_current(
                GoodsReceiptNote.objects.filter(tenant=tenant), self.instance, 'source_grn',
            )
        for fname in ('source_invoice', 'source_po', 'source_grn'):
            self.fields[fname].required = False
            self.fields[fname].empty_label = '— None —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class APBillLineForm(forms.ModelForm):
    class Meta:
        model = APBillLine
        fields = ['product', 'gl_account', 'description', 'quantity', 'unit_price',
                  'tax_rate', 'line_order']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'gl_account': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                 'step': '0.001', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                   'step': '0.01', 'min': '0'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                 'step': '0.01', 'min': '0'}),
            'line_order': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                   'min': '0', 'style': 'width: 70px;'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            self.fields['product'].queryset = self.fields['product'].queryset.none()
            self.fields['gl_account'].queryset = self.fields['gl_account'].queryset.none()
        else:
            from catalog.models import Product
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['gl_account'].queryset = _include_current(
                ChartOfAccount.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'gl_account',
            )
        self.fields['product'].required = False
        self.fields['product'].empty_label = '— None —'


APBillLineFormSet = inlineformset_factory(
    APBill, APBillLine, form=APBillLineForm,
    extra=3, can_delete=True,
)


# ══════════════════════════════════════════════════════════════════════════
# AR Invoices + inline line formset
# ══════════════════════════════════════════════════════════════════════════

class ARInvoiceForm(forms.ModelForm):
    class Meta:
        model = ARInvoice
        fields = [
            'customer', 'source_so', 'source_shipment',
            'invoice_date', 'due_date', 'currency', 'payment_terms', 'notes',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'source_so': forms.Select(attrs={'class': 'form-select'}),
            'source_shipment': forms.Select(attrs={'class': 'form-select'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'net_30'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            for f in ('customer', 'source_so', 'source_shipment'):
                self.fields[f].queryset = self.fields[f].queryset.none()
        else:
            from orders.models import SalesOrder, Shipment
            self.fields['customer'].queryset = _include_current(
                Customer.objects.filter(tenant=tenant, deleted_at__isnull=True),
                self.instance, 'customer',
            )
            self.fields['source_so'].queryset = _include_current(
                SalesOrder.objects.filter(tenant=tenant),
                self.instance, 'source_so',
            )
            self.fields['source_shipment'].queryset = _include_current(
                Shipment.objects.filter(tenant=tenant),
                self.instance, 'source_shipment',
            )
        for fname in ('source_so', 'source_shipment'):
            self.fields[fname].required = False
            self.fields[fname].empty_label = '— None —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ARInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = ARInvoiceLine
        fields = ['product', 'gl_account', 'description', 'quantity', 'unit_price',
                  'tax_rate', 'line_order']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'gl_account': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                 'step': '0.001', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                   'step': '0.01', 'min': '0'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                 'step': '0.01', 'min': '0'}),
            'line_order': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                   'min': '0', 'style': 'width: 70px;'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            self.fields['product'].queryset = self.fields['product'].queryset.none()
            self.fields['gl_account'].queryset = self.fields['gl_account'].queryset.none()
        else:
            from catalog.models import Product
            self.fields['product'].queryset = _include_current(
                Product.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'product',
            )
            self.fields['gl_account'].queryset = _include_current(
                ChartOfAccount.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'gl_account',
            )
        self.fields['product'].required = False
        self.fields['product'].empty_label = '— None —'


ARInvoiceLineFormSet = inlineformset_factory(
    ARInvoice, ARInvoiceLine, form=ARInvoiceLineForm,
    extra=3, can_delete=True,
)


# ══════════════════════════════════════════════════════════════════════════
# Journal Entries + inline line formset
# ══════════════════════════════════════════════════════════════════════════

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['entry_date', 'fiscal_period', 'source_type',
                  'source_reference', 'description']
        widgets = {
            'entry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-select'}),
            'source_type': forms.Select(attrs={'class': 'form-select'}),
            'source_reference': forms.TextInput(attrs={'class': 'form-control',
                                                        'placeholder': 'e.g., BIL-00001'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            self.fields['fiscal_period'].queryset = self.fields['fiscal_period'].queryset.none()
        else:
            self.fields['fiscal_period'].queryset = _include_current(
                FiscalPeriod.objects.filter(tenant=tenant),
                self.instance, 'fiscal_period',
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant is not None:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class JournalLineForm(forms.ModelForm):
    class Meta:
        model = JournalLine
        fields = ['gl_account', 'description', 'debit_amount', 'credit_amount', 'line_order']
        widgets = {
            'gl_account': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'debit_amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                     'step': '0.01', 'min': '0'}),
            'credit_amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                      'step': '0.01', 'min': '0'}),
            'line_order': forms.NumberInput(attrs={'class': 'form-control form-control-sm',
                                                   'min': '0', 'style': 'width: 70px;'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is None:
            self.fields['gl_account'].queryset = self.fields['gl_account'].queryset.none()
        else:
            self.fields['gl_account'].queryset = _include_current(
                ChartOfAccount.objects.filter(tenant=tenant, is_active=True),
                self.instance, 'gl_account',
            )

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get('debit_amount') or Decimal('0')
        credit = cleaned.get('credit_amount') or Decimal('0')
        if self.cleaned_data.get('DELETE'):
            return cleaned
        # Empty rows (no gl_account) are allowed — the formset drops them.
        if cleaned.get('gl_account') is None:
            return cleaned
        if debit > 0 and credit > 0:
            raise ValidationError('A line cannot have both a debit and a credit.')
        if debit == 0 and credit == 0:
            raise ValidationError('A line must have either a debit or a credit > 0.')
        return cleaned


JournalLineFormSet = inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm,
    extra=4, can_delete=True,
)
