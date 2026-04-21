"""Idempotent per-tenant seed for Module 19 — Accounting & Financial Integration.

Creates for every active tenant:
    - 10 Chart of Accounts (standard set: Cash, AR, Inventory, AP, Tax Payable, …)
    - 1 open FiscalPeriod (current quarter)
    - Up to N Customers derived from distinct SalesOrder.customer_name
    - 3 TaxJurisdictions (US, EU, IN) with 3 TaxRules each (standard/reduced/zero)
    - 3 APBills drawn from existing VendorInvoices
    - 3 ARInvoices drawn from delivered Shipments
    - 4 JournalEntries (one draft + three posted — AP / AR / StockAdjustment)

Safe to run multiple times — per-tenant existence guard skips already-seeded rows.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Tenant
from accounting.models import (
    ChartOfAccount, FiscalPeriod, Customer,
    TaxJurisdiction, TaxRule,
    APBill, APBillLine, ARInvoice, ARInvoiceLine,
    JournalEntry, JournalLine,
)


STANDARD_COA = [
    # (code, name, type)
    ('1000', 'Cash', 'asset'),
    ('1100', 'Accounts Receivable', 'asset'),
    ('1200', 'Inventory Asset', 'asset'),
    ('2000', 'Accounts Payable', 'liability'),
    ('2100', 'Tax Payable', 'liability'),
    ('3000', 'Retained Earnings', 'equity'),
    ('4000', 'Sales Revenue', 'revenue'),
    ('5000', 'Cost of Goods Sold', 'expense'),
    ('5100', 'Scrap / Damage Expense', 'expense'),
    ('5200', 'Inventory Adjustments', 'expense'),
]

TAX_JURISDICTIONS = [
    # (code, name, country, state)
    ('US', 'United States — Federal', 'United States', ''),
    ('EU', 'European Union', 'European Union', ''),
    ('IN', 'India GST', 'India', ''),
]

TAX_RULES = [
    # (jurisdiction_code, category, rate)
    ('US', 'standard', Decimal('8.00')),
    ('US', 'reduced', Decimal('4.00')),
    ('US', 'zero', Decimal('0.00')),
    ('EU', 'standard', Decimal('20.00')),
    ('EU', 'reduced', Decimal('10.00')),
    ('EU', 'zero', Decimal('0.00')),
    ('IN', 'standard', Decimal('18.00')),
    ('IN', 'reduced', Decimal('5.00')),
    ('IN', 'zero', Decimal('0.00')),
]


class Command(BaseCommand):
    help = 'Seed Accounting demo data — idempotent per tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true',
                            help='Delete all accounting rows before seeding (does not touch upstream apps).')

    def handle(self, *args, **options):
        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING(
                'No active tenants. Run `python manage.py seed` first.'))
            return

        if options['flush']:
            JournalLine.objects.all().delete()
            JournalEntry.objects.all().delete()
            ARInvoiceLine.objects.all().delete()
            ARInvoice.objects.all().delete()
            APBillLine.objects.all().delete()
            APBill.objects.all().delete()
            TaxRule.objects.all().delete()
            TaxJurisdiction.objects.all().delete()
            Customer.objects.all().delete()
            FiscalPeriod.objects.all().delete()
            ChartOfAccount.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Flushed accounting data.'))

        for tenant in tenants:
            self.stdout.write(f'[{tenant.slug}] seeding…')
            with transaction.atomic():
                self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done seeding accounting data.'))
        self.stdout.write(self.style.WARNING(
            "Reminder: Superuser 'admin' has no tenant — log in as a tenant admin "
            "(e.g. admin_acme / demo123) to see the data."))

    # ──────────────────────────────────────────────────────────────
    # Per-tenant seed
    # ──────────────────────────────────────────────────────────────

    def _seed_tenant(self, tenant):
        coa = self._seed_coa(tenant)
        period = self._seed_fiscal_period(tenant)
        customers = self._seed_customers(tenant)
        jurisdictions = self._seed_tax_jurisdictions(tenant)
        self._seed_tax_rules(tenant, jurisdictions)
        bills = self._seed_ap_bills(tenant, coa, period)
        invoices = self._seed_ar_invoices(tenant, customers, coa, period)
        self._seed_journal_entries(tenant, period, coa, bills, invoices)

    def _seed_coa(self, tenant):
        coa = {}
        already = ChartOfAccount.objects.filter(tenant=tenant).exists()
        for code, name, acc_type in STANDARD_COA:
            acc, _ = ChartOfAccount.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={'name': name, 'account_type': acc_type, 'is_active': True},
            )
            coa[code] = acc
        if not already:
            self.stdout.write(f'  [OK]{len(coa)} chart of accounts')
        return coa

    def _seed_fiscal_period(self, tenant):
        today = date.today()
        quarter = (today.month - 1) // 3 + 1
        start = date(today.year, 3 * (quarter - 1) + 1, 1)
        end_month = start.month + 2
        end_year = start.year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        # Approx last day of that month
        if end_month == 12:
            end = date(end_year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(end_year, end_month + 1, 1) - timedelta(days=1)
        name = f'FY{today.year}-Q{quarter}'
        period = FiscalPeriod.objects.filter(tenant=tenant, name=name).first()
        if period is None:
            period = FiscalPeriod.objects.create(
                tenant=tenant, name=name,
                start_date=start, end_date=end, status='open',
            )
            self.stdout.write(f'  [OK]fiscal period {period.period_number} — {name}')
        return period

    def _seed_customers(self, tenant):
        """Resolve distinct customer_name on existing SalesOrders into a Customer master."""
        try:
            from orders.models import SalesOrder
        except ImportError:  # pragma: no cover
            return []
        so_names = list(
            SalesOrder.objects.filter(tenant=tenant)
            .exclude(customer_name='')
            .values_list('customer_name', 'customer_email', 'customer_phone',
                         'billing_address')
            .distinct()[:20]
        )
        customers = []
        created = 0
        for name, email, phone, addr in so_names:
            norm = (name or '').strip()
            if not norm:
                continue
            cust, was_created = Customer.objects.get_or_create(
                tenant=tenant, company_name=norm,
                defaults={'contact_email': email or '', 'contact_phone': phone or '',
                          'billing_address': addr or '', 'is_active': True},
            )
            if was_created:
                created += 1
            customers.append(cust)
        if created:
            self.stdout.write(f'  [OK]{created} customer(s) from SalesOrder data')
        return customers

    def _seed_tax_jurisdictions(self, tenant):
        jurisdictions = {}
        created = 0
        for code, name, country, state in TAX_JURISDICTIONS:
            j, was = TaxJurisdiction.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={'name': name, 'country': country, 'state': state},
            )
            jurisdictions[code] = j
            if was:
                created += 1
        if created:
            self.stdout.write(f'  [OK]{created} tax jurisdiction(s)')
        return jurisdictions

    def _seed_tax_rules(self, tenant, jurisdictions):
        created = 0
        effective = date.today().replace(month=1, day=1)
        for jur_code, category, rate in TAX_RULES:
            j = jurisdictions.get(jur_code)
            if j is None:
                continue
            existing = TaxRule.objects.filter(
                tenant=tenant, jurisdiction=j, tax_category=category,
                effective_date=effective,
            ).first()
            if existing:
                continue
            TaxRule.objects.create(
                tenant=tenant, jurisdiction=j, tax_category=category,
                tax_rate=rate, effective_date=effective, is_active=True,
            )
            created += 1
        if created:
            self.stdout.write(f'  [OK]{created} tax rule(s)')

    def _seed_ap_bills(self, tenant, coa, period):
        """Create APBills from the first few VendorInvoices (if any)."""
        try:
            from receiving.models import VendorInvoice
        except ImportError:  # pragma: no cover
            return []
        expense = coa.get('5000') or coa.get('1200')
        ap_liability = coa.get('2000')
        if expense is None or ap_liability is None:
            return []
        bills = []
        invoices = VendorInvoice.objects.filter(tenant=tenant)[:3]
        for inv in invoices:
            if APBill.objects.filter(tenant=tenant, source_invoice=inv).exists():
                continue
            bill = APBill.objects.create(
                tenant=tenant, vendor=inv.vendor, source_invoice=inv,
                source_po=inv.purchase_order,
                bill_date=inv.invoice_date, due_date=inv.due_date,
                subtotal=inv.subtotal, tax_amount=inv.tax_amount,
                total_amount=inv.total_amount,
                description=f'Seed — from vendor invoice {inv.invoice_number}',
            )
            APBillLine.objects.create(
                bill=bill, gl_account=expense,
                description=f'Invoice {inv.invoice_number}', quantity=1,
                unit_price=inv.subtotal, tax_rate=0, line_order=1,
            )
            bills.append(bill)
        if bills:
            self.stdout.write(f'  [OK]{len(bills)} AP bill(s) from vendor invoices')
        return bills

    def _seed_ar_invoices(self, tenant, customers, coa, period):
        try:
            from orders.models import Shipment
        except ImportError:  # pragma: no cover
            return []
        revenue = coa.get('4000')
        if revenue is None or not customers:
            return []
        invoices = []
        shipments = Shipment.objects.filter(tenant=tenant, status='delivered')[:3]
        for shipment in shipments:
            if ARInvoice.objects.filter(tenant=tenant, source_shipment=shipment).exists():
                continue
            so = shipment.sales_order
            # Find matching customer or fallback to first
            cust = next((c for c in customers if c.company_name.lower() == (so.customer_name or '').lower()), customers[0])
            invoice = ARInvoice.objects.create(
                tenant=tenant, customer=cust,
                source_so=so, source_shipment=shipment,
                invoice_date=shipment.shipped_date.date() if shipment.shipped_date else so.order_date,
                due_date=so.order_date + timedelta(days=30) if so.order_date else None,
                subtotal=so.subtotal, tax_amount=so.tax_total,
                total_amount=so.grand_total,
            )
            ARInvoiceLine.objects.create(
                invoice=invoice, gl_account=revenue,
                description=f'Shipment {shipment.shipment_number}',
                quantity=1, unit_price=so.subtotal, tax_rate=0, line_order=1,
            )
            invoices.append(invoice)
        if invoices:
            self.stdout.write(f'  [OK]{len(invoices)} AR invoice(s) from shipments')
        return invoices

    def _seed_journal_entries(self, tenant, period, coa, bills, invoices):
        existing = JournalEntry.objects.filter(tenant=tenant).exists()
        if existing:
            return
        created = 0
        # AP posted entry
        if bills:
            bill = bills[0]
            self._create_ap_journal(tenant, period, coa, bill, posted=True)
            created += 1
        # AR posted entry
        if invoices:
            invoice = invoices[0]
            self._create_ar_journal(tenant, period, coa, invoice, posted=True)
            created += 1
        # Stock adjustment entry (if any exists)
        try:
            from inventory.models import StockAdjustment
            adj = StockAdjustment.objects.filter(
                stock_level__product__tenant=tenant,
            ).first()
            if adj and coa.get('1200') and coa.get('5200'):
                self._create_stock_adj_journal(tenant, period, coa, adj, posted=True)
                created += 1
        except ImportError:  # pragma: no cover
            pass
        # A draft manual entry
        if coa.get('1000') and coa.get('3000'):
            entry = JournalEntry.objects.create(
                tenant=tenant, entry_date=date.today(), fiscal_period=period,
                source_type='manual',
                description='Seed — opening retained earnings placeholder',
                source_reference='SEED-0001',
            )
            JournalLine.objects.create(entry=entry, gl_account=coa['1000'],
                                        debit_amount=Decimal('0'),
                                        credit_amount=Decimal('0'),
                                        description='Placeholder', line_order=1)
            created += 1
        if created:
            self.stdout.write(f'  [OK]{created} journal entr(y/ies)')

    def _create_ap_journal(self, tenant, period, coa, bill, posted=False):
        entry = JournalEntry.objects.create(
            tenant=tenant, entry_date=bill.bill_date, fiscal_period=period,
            source_type='ap_bill', source_reference=bill.bill_number,
            source_id=str(bill.pk),
            description=f'Seed — AP Bill {bill.bill_number}',
        )
        JournalLine.objects.create(entry=entry, gl_account=coa['5000'],
                                   debit_amount=bill.subtotal,
                                   description='Purchase expense', line_order=1)
        if bill.tax_amount:
            JournalLine.objects.create(entry=entry, gl_account=coa['2100'],
                                       debit_amount=bill.tax_amount,
                                       description='Input tax', line_order=2)
        JournalLine.objects.create(entry=entry, gl_account=coa['2000'],
                                   credit_amount=bill.total_amount,
                                   description='AP liability', line_order=3)
        entry.recompute_totals()
        if posted:
            entry.status = 'posted'
            entry.posted_at = timezone.now()
        entry.save(update_fields=['total_debit', 'total_credit', 'status', 'posted_at'])
        bill.journal_entry = entry
        bill.save(update_fields=['journal_entry'])

    def _create_ar_journal(self, tenant, period, coa, invoice, posted=False):
        entry = JournalEntry.objects.create(
            tenant=tenant, entry_date=invoice.invoice_date, fiscal_period=period,
            source_type='ar_invoice', source_reference=invoice.invoice_number,
            source_id=str(invoice.pk),
            description=f'Seed — AR Invoice {invoice.invoice_number}',
        )
        JournalLine.objects.create(entry=entry, gl_account=coa['1100'],
                                   debit_amount=invoice.total_amount,
                                   description='AR asset', line_order=1)
        JournalLine.objects.create(entry=entry, gl_account=coa['4000'],
                                   credit_amount=invoice.subtotal,
                                   description='Revenue', line_order=2)
        if invoice.tax_amount:
            JournalLine.objects.create(entry=entry, gl_account=coa['2100'],
                                       credit_amount=invoice.tax_amount,
                                       description='Output tax', line_order=3)
        entry.recompute_totals()
        if posted:
            entry.status = 'posted'
            entry.posted_at = timezone.now()
        entry.save(update_fields=['total_debit', 'total_credit', 'status', 'posted_at'])
        invoice.journal_entry = entry
        invoice.save(update_fields=['journal_entry'])

    def _create_stock_adj_journal(self, tenant, period, coa, adj, posted=False):
        entry = JournalEntry.objects.create(
            tenant=tenant, entry_date=date.today(), fiscal_period=period,
            source_type='stock_adjustment', source_reference=adj.adjustment_number,
            source_id=str(adj.pk),
            description=f'Seed — StockAdjustment {adj.adjustment_number} ({adj.get_reason_display()})',
        )
        # Assume a small, symbolic amount to avoid churn on real balances
        amount = Decimal('10.00')
        if adj.adjustment_type == 'increase':
            JournalLine.objects.create(entry=entry, gl_account=coa['1200'],
                                       debit_amount=amount, description='Inventory in', line_order=1)
            JournalLine.objects.create(entry=entry, gl_account=coa['5200'],
                                       credit_amount=amount, description='Adjustment offset', line_order=2)
        else:
            JournalLine.objects.create(entry=entry, gl_account=coa['5200'],
                                       debit_amount=amount, description='Adjustment offset', line_order=1)
            JournalLine.objects.create(entry=entry, gl_account=coa['1200'],
                                       credit_amount=amount, description='Inventory out', line_order=2)
        entry.recompute_totals()
        if posted:
            entry.status = 'posted'
            entry.posted_at = timezone.now()
        entry.save(update_fields=['total_debit', 'total_credit', 'status', 'posted_at'])
