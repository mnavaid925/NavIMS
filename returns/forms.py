import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.forms import inlineformset_factory

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from orders.models import SalesOrder
from .models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


CURRENCY_RE = re.compile(r'^[A-Z]{3}$')


# ──────────────────────────────────────────────
# Return Authorization Forms
# ──────────────────────────────────────────────

class ReturnAuthorizationForm(forms.ModelForm):
    class Meta:
        model = ReturnAuthorization
        fields = [
            'sales_order', 'customer_name', 'customer_email', 'customer_phone',
            'return_address', 'reason', 'requested_date', 'expected_return_date',
            'warehouse', 'notes',
        ]
        widgets = {
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer full name'}),
            'customer_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'customer@example.com'}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 (555) 000-0000'}),
            'return_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Return pickup address'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'requested_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_return_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes (optional)'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                tenant=tenant, status__in=['delivered', 'closed', 'shipped'],
            )
            self.fields['sales_order'].empty_label = '— Select Sales Order —'
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def clean(self):
        cleaned = super().clean()
        req = cleaned.get('requested_date')
        exp = cleaned.get('expected_return_date')
        if req and exp and exp < req:
            self.add_error('expected_return_date', 'Expected return date cannot precede requested date.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ReturnAuthorizationItemForm(forms.ModelForm):
    class Meta:
        model = ReturnAuthorizationItem
        fields = ['product', 'description', 'qty_requested', 'unit_price', 'reason_note']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Description (optional)'}),
            'qty_requested': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '1', 'placeholder': 'Qty'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'reason_note': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, status='active')
            self.fields['product'].empty_label = '— Select Product —'

    def clean_qty_requested(self):
        qty = self.cleaned_data.get('qty_requested') or 0
        if qty < 1:
            raise ValidationError('Quantity must be at least 1.')
        return qty

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price') or Decimal('0')
        if price < 0:
            raise ValidationError('Unit price cannot be negative.')
        return price


ReturnAuthorizationItemFormSet = inlineformset_factory(
    ReturnAuthorization,
    ReturnAuthorizationItem,
    form=ReturnAuthorizationItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Return Inspection Forms
# ──────────────────────────────────────────────

class ReturnInspectionForm(forms.ModelForm):
    class Meta:
        model = ReturnInspection
        fields = ['rma', 'inspector', 'inspected_date', 'overall_result', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'inspector': forms.Select(attrs={'class': 'form-select'}),
            'inspected_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'overall_result': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Inspection notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            from core.models import User
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['approved', 'received'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'
            self.fields['inspector'].queryset = User.objects.filter(tenant=tenant)
            self.fields['inspector'].empty_label = '— Assign Inspector —'
            self.fields['inspector'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


class ReturnInspectionItemForm(forms.ModelForm):
    class Meta:
        model = ReturnInspectionItem
        fields = ['rma_item', 'qty_inspected', 'qty_passed', 'qty_failed', 'condition', 'restockable', 'notes']
        widgets = {
            'rma_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'qty_inspected': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'qty_passed': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'qty_failed': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'condition': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'restockable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['rma_item'].queryset = ReturnAuthorizationItem.objects.filter(tenant=tenant)
            self.fields['rma_item'].empty_label = '— Select Return Item —'

    def clean(self):
        cleaned = super().clean()
        if self.cleaned_data.get('DELETE'):
            return cleaned
        q_ins = cleaned.get('qty_inspected') or 0
        q_pass = cleaned.get('qty_passed') or 0
        q_fail = cleaned.get('qty_failed') or 0
        rma_item = cleaned.get('rma_item')
        if q_pass + q_fail != q_ins:
            raise ValidationError(
                f'qty_passed ({q_pass}) + qty_failed ({q_fail}) must equal qty_inspected ({q_ins}).'
            )
        if rma_item is not None and q_ins > rma_item.qty_received:
            raise ValidationError(
                f'qty_inspected ({q_ins}) cannot exceed qty_received on RMA item ({rma_item.qty_received}).'
            )
        return cleaned


ReturnInspectionItemFormSet = inlineformset_factory(
    ReturnInspection,
    ReturnInspectionItem,
    form=ReturnInspectionItemForm,
    extra=3,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Disposition Forms
# ──────────────────────────────────────────────

class DispositionForm(forms.ModelForm):
    class Meta:
        model = Disposition
        fields = ['rma', 'inspection', 'decision', 'warehouse', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'inspection': forms.Select(attrs={'class': 'form-select'}),
            'decision': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Disposition notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['received', 'closed'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'
            self.fields['inspection'].queryset = ReturnInspection.objects.filter(
                tenant=tenant, status='completed',
            )
            self.fields['inspection'].empty_label = '— Select Inspection (optional) —'
            self.fields['inspection'].required = False
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant, is_active=True)
            self.fields['warehouse'].empty_label = '— Select Warehouse —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance


# Condition values that cannot be restocked regardless of the flag —
# keeps D-02 enforcement in one place.
NON_RESTOCKABLE_CONDITIONS = frozenset({'defective', 'unusable', 'major_damage', 'missing_parts'})


class DispositionItemForm(forms.ModelForm):
    class Meta:
        model = DispositionItem
        fields = ['inspection_item', 'product', 'qty', 'destination_bin', 'notes']
        widgets = {
            'inspection_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'product': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': '0'}),
            'destination_bin': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant, status='active')
            self.fields['product'].empty_label = '— Select Product —'
            self.fields['destination_bin'].queryset = Bin.objects.filter(tenant=tenant, is_active=True)
            self.fields['destination_bin'].empty_label = '— Select Bin (optional) —'
            self.fields['destination_bin'].required = False
            self.fields['inspection_item'].queryset = ReturnInspectionItem.objects.filter(tenant=tenant)
            self.fields['inspection_item'].empty_label = '— Select Inspection Item —'

    def clean(self):
        cleaned = super().clean()
        if self.cleaned_data.get('DELETE'):
            return cleaned
        qty = cleaned.get('qty') or 0
        ins_item = cleaned.get('inspection_item')
        # Inline formsets pre-populate the parent FK on every child form's
        # instance before clean() runs, so `self.instance.disposition_id` is
        # reliable whether the row is new or existing.
        decision = None
        if getattr(self.instance, 'disposition_id', None):
            parent = Disposition.objects.filter(pk=self.instance.disposition_id).first()
            if parent is not None:
                decision = parent.decision
        if decision is None:
            # Fallback: the parent form is being submitted alongside the formset;
            # read the decision from the raw POST data.
            decision = (self.data or {}).get('decision')
        if qty < 0:
            raise ValidationError('Quantity cannot be negative.')
        if ins_item is not None and qty > ins_item.qty_inspected:
            raise ValidationError(
                f'Disposition qty ({qty}) cannot exceed inspected qty ({ins_item.qty_inspected}).'
            )
        if ins_item is not None and decision == 'restock':
            if not ins_item.restockable or ins_item.condition in NON_RESTOCKABLE_CONDITIONS:
                raise ValidationError(
                    'Cannot restock an inspection item flagged non-restockable or with '
                    f'condition "{ins_item.get_condition_display()}".'
                )
            if qty > ins_item.qty_passed:
                raise ValidationError(
                    f'Restock qty ({qty}) cannot exceed qty_passed ({ins_item.qty_passed}).'
                )
        return cleaned


DispositionItemFormSet = inlineformset_factory(
    Disposition,
    DispositionItem,
    form=DispositionItemForm,
    extra=2,
    can_delete=True,
)


# ──────────────────────────────────────────────
# Refund / Credit Forms
# ──────────────────────────────────────────────

class RefundCreditForm(forms.ModelForm):
    class Meta:
        model = RefundCredit
        fields = ['rma', 'type', 'method', 'amount', 'currency', 'reference_number', 'notes']
        widgets = {
            'rma': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Transaction or credit note reference'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Notes (optional)'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['rma'].queryset = ReturnAuthorization.objects.filter(
                tenant=tenant, status__in=['received', 'closed'],
            )
            self.fields['rma'].empty_label = '— Select RMA —'

    def clean_currency(self):
        currency = (self.cleaned_data.get('currency') or '').strip().upper()
        if not CURRENCY_RE.match(currency):
            raise ValidationError('Currency must be a 3-letter ISO 4217 code (e.g. USD, EUR, GBP).')
        return currency

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        rma = cleaned.get('rma')
        if amount is not None and amount <= 0:
            self.add_error('amount', 'Amount must be greater than zero.')
        if rma is not None and amount is not None and amount > 0:
            # Sum non-cancelled, non-failed refunds already issued against this RMA,
            # excluding the current instance on edit.
            qs = RefundCredit.objects.filter(rma=rma).exclude(status__in=['cancelled', 'failed'])
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            already = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            cap = rma.total_value - already
            if amount > cap:
                self.add_error(
                    'amount',
                    f'Amount {amount} exceeds remaining refundable balance {cap} '
                    f'(RMA total {rma.total_value} minus {already} already refunded).',
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tenant:
            instance.tenant = self.tenant
        if commit:
            instance.save()
        return instance
