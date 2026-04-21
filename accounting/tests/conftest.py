"""Shared fixtures for the accounting test suite."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from catalog.models import Category, Product
from vendors.models import Vendor
from accounting.models import (
    ChartOfAccount, FiscalPeriod, Customer,
    TaxJurisdiction, TaxRule,
    APBill, APBillLine, ARInvoice, ARInvoiceLine,
    JournalEntry, JournalLine,
)


# ── tenants & users ───────────────────────────────────────────────────────

@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-Acct', slug='t-acct')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-Acct-Other', slug='t-acct-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_acct', password='x',
        email='admin_acct@example.com',
        tenant=tenant, is_tenant_admin=True, is_active=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_acct', password='x',
        tenant=tenant, is_tenant_admin=False, is_active=True,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_acct_other', password='x',
        email='admin_other@example.com',
        tenant=other_tenant, is_tenant_admin=True, is_active=True,
    )


@pytest.fixture
def client_admin(db, tenant_admin):
    c = Client()
    c.force_login(tenant_admin)
    return c


@pytest.fixture
def client_user(db, tenant_user):
    c = Client()
    c.force_login(tenant_user)
    return c


@pytest.fixture
def client_other(db, other_tenant_admin):
    c = Client()
    c.force_login(other_tenant_admin)
    return c


# ── catalog + vendors ─────────────────────────────────────────────────────

@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name='Widgets')


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, category=category,
        sku='SKU-ACCT-1', name='Widget',
        purchase_cost=Decimal('10.00'), status='active',
        tax_category='standard',
    )


@pytest.fixture
def other_product(db, other_tenant):
    cat = Category.objects.create(tenant=other_tenant, name='OtherCat')
    return Product.objects.create(
        tenant=other_tenant, category=cat,
        sku='SKU-OTH-1', name='Other Widget',
        purchase_cost=Decimal('5.00'), status='active',
        tax_category='standard',
    )


@pytest.fixture
def vendor(db, tenant):
    return Vendor.objects.create(tenant=tenant, company_name='Acme Vendor')


@pytest.fixture
def other_vendor(db, other_tenant):
    return Vendor.objects.create(tenant=other_tenant, company_name='Other Vendor')


# ── accounting master data ────────────────────────────────────────────────

@pytest.fixture
def gl_accounts(db, tenant):
    """Minimal chart of accounts set for tests."""
    coa = {}
    for code, name, acc_type in [
        ('1000', 'Cash', 'asset'),
        ('1100', 'Accounts Receivable', 'asset'),
        ('1200', 'Inventory Asset', 'asset'),
        ('2000', 'Accounts Payable', 'liability'),
        ('2100', 'Tax Payable', 'liability'),
        ('4000', 'Sales Revenue', 'revenue'),
        ('5000', 'COGS', 'expense'),
    ]:
        coa[code] = ChartOfAccount.objects.create(
            tenant=tenant, code=code, name=name,
            account_type=acc_type, is_active=True,
        )
    return coa


@pytest.fixture
def other_gl_account(db, other_tenant):
    return ChartOfAccount.objects.create(
        tenant=other_tenant, code='2000', name='Other AP',
        account_type='liability', is_active=True,
    )


@pytest.fixture
def fiscal_period(db, tenant):
    return FiscalPeriod.objects.create(
        tenant=tenant, name='Test Period',
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        status='open',
    )


@pytest.fixture
def other_fiscal_period(db, other_tenant):
    return FiscalPeriod.objects.create(
        tenant=other_tenant, name='Other Period',
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        status='open',
    )


@pytest.fixture
def customer(db, tenant):
    return Customer.objects.create(
        tenant=tenant, company_name='Alpha Customer', contact_email='a@ex.com',
    )


@pytest.fixture
def other_customer(db, other_tenant):
    return Customer.objects.create(
        tenant=other_tenant, company_name='Other Cust', contact_email='o@ex.com',
    )


@pytest.fixture
def jurisdiction(db, tenant):
    return TaxJurisdiction.objects.create(
        tenant=tenant, code='US', name='United States', country='US',
    )


@pytest.fixture
def other_jurisdiction(db, other_tenant):
    return TaxJurisdiction.objects.create(
        tenant=other_tenant, code='US', name='Other US', country='US',
    )


@pytest.fixture
def tax_rule(db, tenant, jurisdiction):
    return TaxRule.objects.create(
        tenant=tenant, jurisdiction=jurisdiction,
        tax_category='standard', tax_rate=Decimal('10.00'),
        effective_date=date(2026, 1, 1),
    )


@pytest.fixture
def ap_bill(db, tenant, vendor, fiscal_period):
    return APBill.objects.create(
        tenant=tenant, vendor=vendor,
        bill_date=date(2026, 4, 15),
        subtotal=Decimal('100.00'), tax_amount=Decimal('10.00'),
        total_amount=Decimal('110.00'),
    )


@pytest.fixture
def ar_invoice(db, tenant, customer, fiscal_period):
    return ARInvoice.objects.create(
        tenant=tenant, customer=customer,
        invoice_date=date(2026, 4, 15),
        subtotal=Decimal('200.00'), tax_amount=Decimal('20.00'),
        total_amount=Decimal('220.00'),
    )


@pytest.fixture
def journal_entry(db, tenant, fiscal_period, gl_accounts):
    entry = JournalEntry.objects.create(
        tenant=tenant, entry_date=date(2026, 4, 15),
        fiscal_period=fiscal_period,
        source_type='manual', description='Test entry',
    )
    JournalLine.objects.create(
        entry=entry, gl_account=gl_accounts['1000'],
        debit_amount=Decimal('50.00'), line_order=1,
    )
    JournalLine.objects.create(
        entry=entry, gl_account=gl_accounts['4000'],
        credit_amount=Decimal('50.00'), line_order=2,
    )
    entry.recompute_totals()
    entry.save(update_fields=['total_debit', 'total_credit'])
    return entry
