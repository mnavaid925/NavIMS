"""Management-command tests — idempotency + seeds + scan generators."""
from io import StringIO

import pytest
from django.core.management import call_command

from accounting.models import (
    ChartOfAccount, FiscalPeriod, TaxJurisdiction, TaxRule,
    APBill, ARInvoice, JournalEntry,
)


@pytest.mark.django_db
def test_seed_accounting_idempotent(tenant):
    out1 = StringIO()
    call_command('seed_accounting', stdout=out1)
    coa_count_1 = ChartOfAccount.objects.filter(tenant=tenant).count()
    period_count_1 = FiscalPeriod.objects.filter(tenant=tenant).count()
    jurisdiction_count_1 = TaxJurisdiction.objects.filter(tenant=tenant).count()
    rule_count_1 = TaxRule.objects.filter(tenant=tenant).count()
    assert coa_count_1 == 10
    assert period_count_1 == 1
    assert jurisdiction_count_1 == 3
    assert rule_count_1 == 9

    # Re-run — counts stable
    call_command('seed_accounting', stdout=StringIO())
    assert ChartOfAccount.objects.filter(tenant=tenant).count() == 10
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 1
    assert TaxRule.objects.filter(tenant=tenant).count() == 9


@pytest.mark.django_db
def test_seed_accounting_flush_clears(tenant):
    call_command('seed_accounting', stdout=StringIO())
    assert ChartOfAccount.objects.filter(tenant=tenant).count() == 10

    call_command('seed_accounting', '--flush', stdout=StringIO())
    # --flush clears then re-seeds; counts land at the same place
    assert ChartOfAccount.objects.filter(tenant=tenant).count() == 10


@pytest.mark.django_db
def test_generate_ap_bills_idempotent(tenant):
    call_command('seed_accounting', stdout=StringIO())
    call_command('generate_ap_bills', stdout=StringIO())
    bills_after_first = APBill.objects.filter(tenant=tenant).count()
    call_command('generate_ap_bills', stdout=StringIO())
    # Second run creates nothing new
    assert APBill.objects.filter(tenant=tenant).count() == bills_after_first


@pytest.mark.django_db
def test_generate_ar_invoices_idempotent(tenant):
    call_command('seed_accounting', stdout=StringIO())
    call_command('generate_ar_invoices', stdout=StringIO())
    before = ARInvoice.objects.filter(tenant=tenant).count()
    call_command('generate_ar_invoices', stdout=StringIO())
    assert ARInvoice.objects.filter(tenant=tenant).count() == before


@pytest.mark.django_db
def test_generate_journal_entries_idempotent(tenant):
    call_command('seed_accounting', stdout=StringIO())
    call_command('generate_journal_entries', stdout=StringIO())
    before = JournalEntry.objects.filter(tenant=tenant).count()
    call_command('generate_journal_entries', stdout=StringIO())
    assert JournalEntry.objects.filter(tenant=tenant).count() == before


@pytest.mark.django_db
def test_seed_accounting_respects_tenant_isolation(tenant, other_tenant):
    call_command('seed_accounting', stdout=StringIO())
    # Each tenant gets its own COA
    assert ChartOfAccount.objects.filter(tenant=tenant).count() == 10
    assert ChartOfAccount.objects.filter(tenant=other_tenant).count() == 10
    # Period numbers reset per tenant
    t_period = FiscalPeriod.objects.filter(tenant=tenant).first()
    o_period = FiscalPeriod.objects.filter(tenant=other_tenant).first()
    assert t_period.period_number == 'FP-00001'
    assert o_period.period_number == 'FP-00001'
