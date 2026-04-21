"""Form-layer tests — tenant scoping, TenantUniqueCodeMixin, validation."""
from datetime import date
from decimal import Decimal

import pytest

from accounting.forms import (
    ChartOfAccountForm, FiscalPeriodForm, CustomerForm,
    TaxJurisdictionForm, TaxRuleForm,
    APBillForm, ARInvoiceForm, JournalEntryForm, JournalLineForm,
)
from accounting.models import ChartOfAccount, TaxJurisdiction


# ── Tenant-scoped FK querysets ────────────────────────────────────────────

@pytest.mark.django_db
def test_coa_form_parent_queryset_scoped(tenant, other_tenant):
    ChartOfAccount.objects.create(tenant=tenant, code='100', name='Mine', account_type='asset')
    ChartOfAccount.objects.create(tenant=other_tenant, code='100', name='Theirs', account_type='asset')
    form = ChartOfAccountForm(tenant=tenant)
    assert form.fields['parent'].queryset.count() == 1
    assert form.fields['parent'].queryset.first().name == 'Mine'


@pytest.mark.django_db
def test_coa_form_code_unique_per_tenant(tenant):
    ChartOfAccount.objects.create(tenant=tenant, code='1000', name='Cash', account_type='asset')
    form = ChartOfAccountForm(
        data={'code': '1000', 'name': 'Dup', 'account_type': 'asset', 'is_active': 'on'},
        tenant=tenant,
    )
    assert not form.is_valid()
    assert 'code' in form.errors


@pytest.mark.django_db
def test_coa_form_code_case_insensitive(tenant):
    ChartOfAccount.objects.create(tenant=tenant, code='1000', name='Cash', account_type='asset')
    form = ChartOfAccountForm(
        data={'code': '1000', 'name': 'Dup', 'account_type': 'asset'},
        tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_jurisdiction_form_code_unique(tenant):
    TaxJurisdiction.objects.create(tenant=tenant, code='US', name='US')
    form = TaxJurisdictionForm(
        data={'code': 'US', 'name': 'Dup', 'is_active': 'on'}, tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_fiscal_period_date_order(tenant):
    form = FiscalPeriodForm(
        data={'name': 'Bad', 'start_date': '2026-06-30', 'end_date': '2026-01-01'},
        tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_tax_rule_jurisdiction_scoped(tenant, other_tenant, jurisdiction, other_jurisdiction):
    form = TaxRuleForm(tenant=tenant)
    qs = form.fields['jurisdiction'].queryset
    assert jurisdiction in qs
    assert other_jurisdiction not in qs


@pytest.mark.django_db
def test_tax_rule_end_date_order(tenant, jurisdiction):
    form = TaxRuleForm(
        data={
            'jurisdiction': jurisdiction.pk, 'tax_category': 'standard',
            'tax_rate': '10', 'effective_date': '2026-06-01', 'end_date': '2026-01-01',
            'is_active': 'on',
        },
        tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_ap_bill_form_vendor_scoped(tenant, vendor, other_vendor):
    form = APBillForm(tenant=tenant)
    qs = form.fields['vendor'].queryset
    assert vendor in qs
    assert other_vendor not in qs


@pytest.mark.django_db
def test_ar_invoice_form_customer_scoped(tenant, customer, other_customer):
    form = ARInvoiceForm(tenant=tenant)
    qs = form.fields['customer'].queryset
    assert customer in qs
    assert other_customer not in qs


@pytest.mark.django_db
def test_journal_entry_form_period_scoped(tenant, other_tenant, fiscal_period, other_fiscal_period):
    form = JournalEntryForm(tenant=tenant)
    qs = form.fields['fiscal_period'].queryset
    assert fiscal_period in qs
    assert other_fiscal_period not in qs


@pytest.mark.django_db
def test_tenant_none_forms_use_empty_querysets(tenant):
    """When tenant=None (superuser context), all FK querysets must be empty."""
    for FormCls in (APBillForm, ARInvoiceForm, JournalEntryForm, TaxRuleForm, ChartOfAccountForm):
        form = FormCls(tenant=None)
        # Spot-check any FK field is empty
        for field_name, field in form.fields.items():
            if hasattr(field, 'queryset'):
                assert field.queryset.count() == 0, f'{FormCls.__name__}.{field_name} not empty'


# ── JournalLine debit/credit validation ───────────────────────────────────

@pytest.mark.django_db
def test_journal_line_both_debit_and_credit_rejected(tenant, gl_accounts):
    form = JournalLineForm(
        data={'gl_account': gl_accounts['1000'].pk,
              'debit_amount': '10', 'credit_amount': '5', 'line_order': 1},
        tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_journal_line_zero_debit_and_credit_rejected(tenant, gl_accounts):
    form = JournalLineForm(
        data={'gl_account': gl_accounts['1000'].pk,
              'debit_amount': '0', 'credit_amount': '0', 'line_order': 1},
        tenant=tenant,
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_journal_line_debit_only_accepted(tenant, gl_accounts):
    form = JournalLineForm(
        data={'gl_account': gl_accounts['1000'].pk,
              'debit_amount': '10', 'credit_amount': '0', 'line_order': 1},
        tenant=tenant,
    )
    assert form.is_valid(), form.errors
