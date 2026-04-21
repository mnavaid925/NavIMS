"""View-layer tests — CRUD happy paths + RBAC gating + CSRF @require_POST."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounting.models import (
    ChartOfAccount, FiscalPeriod, Customer, TaxJurisdiction, TaxRule,
    APBill, ARInvoice, JournalEntry,
)


# ── Overview + dashboards render for any tenant user ──────────────────────

@pytest.mark.django_db
def test_overview_renders(client_admin, tenant):
    resp = client_admin.get(reverse('accounting:overview'))
    assert resp.status_code == 200
    assert b'Accounting' in resp.content


@pytest.mark.django_db
def test_ap_dashboard_renders(client_admin):
    resp = client_admin.get(reverse('accounting:ap_dashboard'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_ar_dashboard_renders(client_admin):
    resp = client_admin.get(reverse('accounting:ar_dashboard'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_journal_dashboard_renders(client_admin):
    resp = client_admin.get(reverse('accounting:journal_dashboard'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_tax_dashboard_renders(client_admin):
    resp = client_admin.get(reverse('accounting:tax_dashboard'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_trial_balance_renders(client_admin, gl_accounts, journal_entry):
    journal_entry.status = 'posted'
    journal_entry.save()
    resp = client_admin.get(reverse('accounting:trial_balance'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_tax_calculator_get_and_post(client_admin, tenant, product, jurisdiction, tax_rule):
    resp = client_admin.get(reverse('accounting:tax_calculator'))
    assert resp.status_code == 200
    resp = client_admin.post(reverse('accounting:tax_calculator'), {
        'product': product.pk, 'jurisdiction': jurisdiction.pk, 'amount': '100',
    })
    assert resp.status_code == 200
    # Verify the computed tax appears in the rendered output
    assert b'10.00' in resp.content


# ── CRUD smoke tests (one per model) ──────────────────────────────────────

@pytest.mark.django_db
def test_coa_full_crud(client_admin, tenant):
    # Create
    resp = client_admin.post(reverse('accounting:coa_create'), {
        'code': '9000', 'name': 'Test Account', 'account_type': 'asset',
        'is_active': 'on',
    })
    assert resp.status_code == 302
    acc = ChartOfAccount.objects.get(tenant=tenant, code='9000')
    # Read list + detail
    assert client_admin.get(reverse('accounting:coa_list')).status_code == 200
    assert client_admin.get(reverse('accounting:coa_detail', args=[acc.pk])).status_code == 200
    # Edit
    resp = client_admin.post(reverse('accounting:coa_edit', args=[acc.pk]), {
        'code': '9000', 'name': 'Renamed', 'account_type': 'asset', 'is_active': 'on',
    })
    assert resp.status_code == 302
    acc.refresh_from_db()
    assert acc.name == 'Renamed'
    # Delete
    resp = client_admin.post(reverse('accounting:coa_delete', args=[acc.pk]))
    assert resp.status_code == 302
    assert not ChartOfAccount.objects.filter(pk=acc.pk).exists()


@pytest.mark.django_db
def test_fiscal_period_crud(client_admin, tenant):
    resp = client_admin.post(reverse('accounting:period_create'), {
        'name': 'FY26-Q2', 'start_date': '2026-04-01', 'end_date': '2026-06-30',
    })
    assert resp.status_code == 302
    period = FiscalPeriod.objects.get(tenant=tenant, name='FY26-Q2')
    assert client_admin.get(reverse('accounting:period_detail', args=[period.pk])).status_code == 200
    # Close
    resp = client_admin.post(reverse('accounting:period_close', args=[period.pk]))
    period.refresh_from_db()
    assert period.status == 'closed'


@pytest.mark.django_db
def test_customer_crud(client_admin, tenant):
    resp = client_admin.post(reverse('accounting:customer_create'), {
        'company_name': 'Test Co', 'contact_name': '', 'contact_email': '',
        'contact_phone': '', 'billing_address': '', 'country': '',
        'state': '', 'city': '', 'postal_code': '', 'tax_id': '',
        'payment_terms': 'net_30', 'default_currency': 'USD', 'is_active': 'on',
        'notes': '',
    })
    assert resp.status_code == 302
    cust = Customer.objects.get(tenant=tenant, company_name='Test Co')
    assert cust.customer_number.startswith('CUST-')


@pytest.mark.django_db
def test_jurisdiction_create_and_rule_create(client_admin, tenant):
    resp = client_admin.post(reverse('accounting:jurisdiction_create'), {
        'code': 'CA', 'name': 'Canada', 'country': 'CA', 'state': '',
        'description': '', 'is_active': 'on',
    })
    assert resp.status_code == 302
    jur = TaxJurisdiction.objects.get(tenant=tenant, code='CA')

    resp = client_admin.post(reverse('accounting:tax_rule_create'), {
        'jurisdiction': jur.pk, 'tax_category': 'standard', 'tax_rate': '5',
        'effective_date': '2026-01-01', 'end_date': '',
        'description': '', 'is_active': 'on',
    })
    assert resp.status_code == 302
    assert TaxRule.objects.filter(tenant=tenant, jurisdiction=jur).count() == 1


# ── RBAC: non-admin user cannot create/edit/delete ────────────────────────

@pytest.mark.django_db
def test_non_admin_cannot_create_coa(client_user):
    resp = client_user.post(reverse('accounting:coa_create'), {
        'code': '8000', 'name': 'X', 'account_type': 'asset',
    })
    assert resp.status_code == 403


@pytest.mark.django_db
def test_non_admin_can_read_lists(client_user):
    assert client_user.get(reverse('accounting:coa_list')).status_code == 200
    assert client_user.get(reverse('accounting:ap_bill_list')).status_code == 200
    assert client_user.get(reverse('accounting:ar_invoice_list')).status_code == 200
    assert client_user.get(reverse('accounting:journal_entry_list')).status_code == 200


# ── @require_POST enforcement on state transitions ────────────────────────

@pytest.mark.django_db
def test_delete_requires_post(client_admin, ap_bill):
    resp = client_admin.get(reverse('accounting:ap_bill_delete', args=[ap_bill.pk]))
    assert resp.status_code == 405


@pytest.mark.django_db
def test_ap_bill_void_requires_post(client_admin, ap_bill):
    resp = client_admin.get(reverse('accounting:ap_bill_void', args=[ap_bill.pk]))
    assert resp.status_code == 405


@pytest.mark.django_db
def test_journal_entry_post_requires_post(client_admin, journal_entry):
    resp = client_admin.get(reverse('accounting:journal_entry_post', args=[journal_entry.pk]))
    assert resp.status_code == 405


# ── Sync queue action ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_ap_bill_queue_sync(client_admin, ap_bill):
    resp = client_admin.post(reverse('accounting:ap_bill_queue_sync', args=[ap_bill.pk]))
    assert resp.status_code == 302
    ap_bill.refresh_from_db()
    assert ap_bill.sync_status == 'queued'


# ── State transitions happy path ──────────────────────────────────────────

@pytest.mark.django_db
def test_ap_bill_submit_approve(client_admin, ap_bill):
    resp = client_admin.post(reverse('accounting:ap_bill_submit', args=[ap_bill.pk]))
    assert resp.status_code == 302
    ap_bill.refresh_from_db()
    assert ap_bill.status == 'pending_approval'
    resp = client_admin.post(reverse('accounting:ap_bill_approve', args=[ap_bill.pk]))
    assert resp.status_code == 302
    ap_bill.refresh_from_db()
    assert ap_bill.status == 'approved'


@pytest.mark.django_db
def test_journal_entry_post_balanced(client_admin, journal_entry, tenant_admin):
    # Balanced entry by fixture; post should succeed
    other_user = tenant_admin  # same tenant
    # Re-assign created_by to a different user to avoid SoD self-check
    from django.contrib.auth import get_user_model
    U = get_user_model()
    creator = U.objects.create_user(username='creator', password='x',
                                    tenant=journal_entry.tenant, is_tenant_admin=True)
    journal_entry.created_by = creator
    journal_entry.save()
    resp = client_admin.post(reverse('accounting:journal_entry_post', args=[journal_entry.pk]))
    assert resp.status_code == 302
    journal_entry.refresh_from_db()
    assert journal_entry.status == 'posted'


@pytest.mark.django_db
def test_journal_entry_post_rejects_creator(client_admin, tenant, fiscal_period, gl_accounts,
                                              tenant_admin):
    """Segregation of duties: creator cannot post their own entry."""
    from accounting.models import JournalLine
    entry = JournalEntry.objects.create(
        tenant=tenant, entry_date=date.today(), fiscal_period=fiscal_period,
        created_by=tenant_admin,
    )
    JournalLine.objects.create(entry=entry, gl_account=gl_accounts['1000'],
                               debit_amount=Decimal('10'), line_order=1)
    JournalLine.objects.create(entry=entry, gl_account=gl_accounts['4000'],
                               credit_amount=Decimal('10'), line_order=2)
    entry.recompute_totals()
    entry.save()
    resp = client_admin.post(reverse('accounting:journal_entry_post', args=[entry.pk]))
    assert resp.status_code == 302
    entry.refresh_from_db()
    assert entry.status == 'draft'  # blocked by SoD
