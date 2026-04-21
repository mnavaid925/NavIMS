"""Model-layer tests for accounting — auto-number, state machines, invariants."""
from datetime import date
from decimal import Decimal

import pytest

from accounting.models import (
    ChartOfAccount, FiscalPeriod, Customer, TaxJurisdiction, TaxRule,
    APBill, ARInvoice, JournalEntry, JournalLine,
)


# ── Auto-number: per-tenant sequences ─────────────────────────────────────

@pytest.mark.django_db
def test_fiscal_period_autonumber_per_tenant(tenant, other_tenant):
    p1 = FiscalPeriod.objects.create(tenant=tenant, name='A',
                                     start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
    p2 = FiscalPeriod.objects.create(tenant=tenant, name='B',
                                     start_date=date(2026, 4, 1), end_date=date(2026, 6, 30))
    assert p1.period_number == 'FP-00001'
    assert p2.period_number == 'FP-00002'
    # Separate sequence per tenant
    p3 = FiscalPeriod.objects.create(tenant=other_tenant, name='Other A',
                                     start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
    assert p3.period_number == 'FP-00001'


@pytest.mark.django_db
def test_customer_autonumber(tenant):
    c = Customer.objects.create(tenant=tenant, company_name='Acme')
    assert c.customer_number == 'CUST-00001'


@pytest.mark.django_db
def test_ap_bill_autonumber(tenant, vendor):
    b = APBill.objects.create(tenant=tenant, vendor=vendor, bill_date=date.today())
    assert b.bill_number == 'BIL-00001'


@pytest.mark.django_db
def test_ar_invoice_autonumber(tenant, customer):
    i = ARInvoice.objects.create(tenant=tenant, customer=customer, invoice_date=date.today())
    assert i.invoice_number == 'ARI-00001'


@pytest.mark.django_db
def test_journal_entry_autonumber(tenant, fiscal_period):
    j = JournalEntry.objects.create(
        tenant=tenant, entry_date=date.today(), fiscal_period=fiscal_period,
    )
    assert j.entry_number == 'JE-00001'


@pytest.mark.django_db
def test_tax_rule_autonumber(tenant, jurisdiction):
    r = TaxRule.objects.create(
        tenant=tenant, jurisdiction=jurisdiction,
        tax_category='standard', tax_rate=Decimal('10.00'),
        effective_date=date(2026, 1, 1),
    )
    assert r.rule_number == 'TRL-00001'


# ── unique_together enforcement ───────────────────────────────────────────

@pytest.mark.django_db
def test_coa_code_unique_per_tenant(tenant, other_tenant):
    ChartOfAccount.objects.create(tenant=tenant, code='1000', name='Cash', account_type='asset')
    # Same code in other tenant is fine
    ChartOfAccount.objects.create(tenant=other_tenant, code='1000', name='Cash', account_type='asset')
    # Same code in same tenant blows up
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        ChartOfAccount.objects.create(tenant=tenant, code='1000', name='Dup', account_type='asset')


@pytest.mark.django_db
def test_tax_jurisdiction_code_unique_per_tenant(tenant, other_tenant):
    TaxJurisdiction.objects.create(tenant=tenant, code='US', name='US')
    TaxJurisdiction.objects.create(tenant=other_tenant, code='US', name='US')
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        TaxJurisdiction.objects.create(tenant=tenant, code='US', name='Dup')


# ── State machines ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_ap_bill_state_machine(ap_bill):
    assert ap_bill.can_transition_to('pending_approval')
    assert ap_bill.can_transition_to('voided')
    assert not ap_bill.can_transition_to('paid')  # must go draft → pending → approved → posted → paid
    ap_bill.status = 'approved'
    assert ap_bill.can_transition_to('posted')
    assert not ap_bill.can_transition_to('paid')


@pytest.mark.django_db
def test_ar_invoice_state_machine(ar_invoice):
    assert ar_invoice.can_transition_to('sent')
    ar_invoice.status = 'sent'
    assert ar_invoice.can_transition_to('paid')
    assert ar_invoice.can_transition_to('overdue')
    ar_invoice.status = 'paid'
    assert not ar_invoice.can_transition_to('voided')  # terminal


@pytest.mark.django_db
def test_journal_entry_state_machine(journal_entry):
    assert journal_entry.can_transition_to('posted')
    assert journal_entry.can_transition_to('voided')
    journal_entry.status = 'posted'
    assert journal_entry.can_transition_to('voided')
    assert not journal_entry.can_transition_to('draft')  # no unposting


@pytest.mark.django_db
def test_fiscal_period_open_close(fiscal_period):
    assert fiscal_period.status == 'open'
    assert fiscal_period.can_transition_to('closed')
    fiscal_period.status = 'closed'
    assert fiscal_period.can_transition_to('open')  # reopening allowed


# ── Journal entry balance invariant ───────────────────────────────────────

@pytest.mark.django_db
def test_journal_entry_is_balanced(journal_entry):
    assert journal_entry.total_debit == Decimal('50.00')
    assert journal_entry.total_credit == Decimal('50.00')
    assert journal_entry.is_balanced


@pytest.mark.django_db
def test_journal_entry_unbalanced_flag(tenant, fiscal_period, gl_accounts):
    entry = JournalEntry.objects.create(
        tenant=tenant, entry_date=date.today(), fiscal_period=fiscal_period,
    )
    JournalLine.objects.create(entry=entry, gl_account=gl_accounts['1000'],
                               debit_amount=Decimal('100.00'), line_order=1)
    JournalLine.objects.create(entry=entry, gl_account=gl_accounts['4000'],
                               credit_amount=Decimal('50.00'), line_order=2)
    entry.recompute_totals()
    assert not entry.is_balanced


# ── APBill totals helper ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_ap_bill_recompute_totals(tenant, vendor, gl_accounts):
    from accounting.models import APBillLine
    bill = APBill.objects.create(tenant=tenant, vendor=vendor, bill_date=date.today())
    APBillLine.objects.create(
        bill=bill, gl_account=gl_accounts['5000'],
        quantity=Decimal('2'), unit_price=Decimal('50.00'), tax_rate=Decimal('10'),
    )
    bill.recompute_totals()
    assert bill.subtotal == Decimal('100.00')
    assert bill.tax_amount == Decimal('10.00')
    assert bill.total_amount == Decimal('110.00')


# ── Soft-delete field presence ────────────────────────────────────────────

@pytest.mark.django_db
def test_soft_delete_fields_exist(ap_bill, ar_invoice, journal_entry, customer):
    for obj in [ap_bill, ar_invoice, journal_entry, customer]:
        assert hasattr(obj, 'deleted_at')
        assert obj.deleted_at is None
