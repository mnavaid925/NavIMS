"""Security tests — OWASP A01 cross-tenant IDOR, A03 injection, A08 CSRF."""
from datetime import date

import pytest
from django.urls import reverse


# ── A01 — Cross-tenant IDOR: detail / edit / delete all return 404 ────────

@pytest.mark.django_db
def test_idor_coa_detail(client_admin, other_tenant, other_gl_account):
    resp = client_admin.get(reverse('accounting:coa_detail', args=[other_gl_account.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_coa_delete(client_admin, other_tenant, other_gl_account):
    resp = client_admin.post(reverse('accounting:coa_delete', args=[other_gl_account.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_fiscal_period_detail(client_admin, other_fiscal_period):
    resp = client_admin.get(reverse('accounting:period_detail', args=[other_fiscal_period.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_customer_detail(client_admin, other_customer):
    resp = client_admin.get(reverse('accounting:customer_detail', args=[other_customer.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_jurisdiction_detail(client_admin, other_jurisdiction):
    resp = client_admin.get(
        reverse('accounting:jurisdiction_detail', args=[other_jurisdiction.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_ap_bill_detail(client_admin, other_tenant, other_vendor):
    from accounting.models import APBill
    other_bill = APBill.objects.create(
        tenant=other_tenant, vendor=other_vendor, bill_date=date.today(),
    )
    resp = client_admin.get(reverse('accounting:ap_bill_detail', args=[other_bill.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_ar_invoice_detail(client_admin, other_tenant, other_customer):
    from accounting.models import ARInvoice
    other_inv = ARInvoice.objects.create(
        tenant=other_tenant, customer=other_customer, invoice_date=date.today(),
    )
    resp = client_admin.get(reverse('accounting:ar_invoice_detail', args=[other_inv.pk]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_idor_journal_entry_detail(client_admin, other_tenant, other_fiscal_period):
    from accounting.models import JournalEntry
    other_entry = JournalEntry.objects.create(
        tenant=other_tenant, entry_date=date.today(),
        fiscal_period=other_fiscal_period,
    )
    resp = client_admin.get(
        reverse('accounting:journal_entry_detail', args=[other_entry.pk]))
    assert resp.status_code == 404


# ── A01 — Cross-tenant state transitions blocked ──────────────────────────

@pytest.mark.django_db
def test_idor_ap_bill_post_cross_tenant(client_admin, other_tenant, other_vendor):
    from accounting.models import APBill
    other_bill = APBill.objects.create(
        tenant=other_tenant, vendor=other_vendor, bill_date=date.today(),
        status='approved',
    )
    resp = client_admin.post(reverse('accounting:ap_bill_post', args=[other_bill.pk]))
    assert resp.status_code == 404


# ── A01 — Non-tenant-admin locked out of mutations ────────────────────────

@pytest.mark.django_db
def test_rbac_non_admin_cannot_edit_coa(client_user, gl_accounts):
    resp = client_user.post(reverse('accounting:coa_edit', args=[gl_accounts['1000'].pk]), {
        'code': '1000', 'name': 'Hacked', 'account_type': 'asset',
    })
    assert resp.status_code == 403


@pytest.mark.django_db
def test_rbac_non_admin_cannot_post_journal(client_user, journal_entry):
    resp = client_user.post(reverse('accounting:journal_entry_post', args=[journal_entry.pk]))
    assert resp.status_code == 403


# ── A08 — CSRF: @require_POST enforcement (GET rejected) ──────────────────

@pytest.mark.django_db
@pytest.mark.parametrize('url_name,args_fn', [
    ('accounting:coa_delete', lambda g: [g['1000'].pk]),
    ('accounting:period_close', lambda p: [p.pk]),
    ('accounting:customer_delete', lambda c: [c.pk]),
    ('accounting:ap_bill_submit', lambda b: [b.pk]),
    ('accounting:ar_invoice_send', lambda i: [i.pk]),
    ('accounting:journal_entry_void', lambda e: [e.pk]),
])
def test_get_on_mutating_endpoints_returns_405(client_admin, gl_accounts, fiscal_period,
                                                customer, ap_bill, ar_invoice, journal_entry,
                                                url_name, args_fn):
    ctx_map = {
        'accounting:coa_delete': gl_accounts,
        'accounting:period_close': fiscal_period,
        'accounting:customer_delete': customer,
        'accounting:ap_bill_submit': ap_bill,
        'accounting:ar_invoice_send': ar_invoice,
        'accounting:journal_entry_void': journal_entry,
    }
    args = args_fn(ctx_map[url_name])
    resp = client_admin.get(reverse(url_name, args=args))
    assert resp.status_code == 405


# ── Anonymous user redirected to login ────────────────────────────────────

@pytest.mark.django_db
def test_anonymous_redirected(client):
    resp = client.get(reverse('accounting:overview'))
    assert resp.status_code == 302
    assert '/accounts/login' in resp['Location']
