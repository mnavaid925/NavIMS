"""Scan matched `receiving.VendorInvoice` rows and create `APBill` for each.

Idempotent: existing APBills are matched via `source_invoice` FK and skipped.
"""
from django.core.management.base import BaseCommand

from core.models import Tenant
from accounting.models import APBill, APBillLine, ChartOfAccount


class Command(BaseCommand):
    help = 'Scan matched vendor invoices and create APBill records. Idempotent.'

    def handle(self, *args, **options):
        try:
            from receiving.models import VendorInvoice
        except ImportError:
            self.stdout.write(self.style.ERROR('receiving app not installed.'))
            return

        total_created = 0
        total_skipped = 0
        for tenant in Tenant.objects.filter(is_active=True):
            expense_account = (
                ChartOfAccount.objects
                .filter(tenant=tenant, account_type='expense', is_active=True)
                .order_by('code').first()
            )
            if expense_account is None:
                self.stdout.write(self.style.WARNING(
                    f'[{tenant.slug}] no expense account; run seed_accounting first.'))
                continue

            invoices = VendorInvoice.objects.filter(tenant=tenant, status='matched')
            created = 0
            skipped = 0
            for inv in invoices:
                if APBill.objects.filter(tenant=tenant, source_invoice=inv,
                                         deleted_at__isnull=True).exists():
                    skipped += 1
                    continue
                bill = APBill.objects.create(
                    tenant=tenant, vendor=inv.vendor,
                    source_invoice=inv, source_po=inv.purchase_order,
                    bill_date=inv.invoice_date, due_date=inv.due_date,
                    subtotal=inv.subtotal, tax_amount=inv.tax_amount,
                    total_amount=inv.total_amount,
                    description=f'Auto-generated from {inv.invoice_number}',
                )
                APBillLine.objects.create(
                    bill=bill, gl_account=expense_account,
                    description=f'Vendor invoice {inv.invoice_number}',
                    quantity=1, unit_price=inv.subtotal, tax_rate=0, line_order=1,
                )
                created += 1
            total_created += created
            total_skipped += skipped
            self.stdout.write(f'[{tenant.slug}] created={created}, skipped={skipped}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {total_created}, skipped {total_skipped} (already linked).'))
