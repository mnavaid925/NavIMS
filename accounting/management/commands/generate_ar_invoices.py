"""Scan delivered `orders.Shipment` rows and create `ARInvoice` for each.

Idempotent: existing ARInvoices with matching `source_shipment` are skipped.
Also resolves customer_name → Customer via `get_or_create`.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand

from core.models import Tenant
from accounting.models import ARInvoice, ARInvoiceLine, ChartOfAccount, Customer


class Command(BaseCommand):
    help = 'Scan delivered shipments and create ARInvoice records. Idempotent.'

    def handle(self, *args, **options):
        try:
            from orders.models import Shipment
        except ImportError:
            self.stdout.write(self.style.ERROR('orders app not installed.'))
            return

        total_created = 0
        total_skipped = 0
        for tenant in Tenant.objects.filter(is_active=True):
            revenue_account = (
                ChartOfAccount.objects
                .filter(tenant=tenant, account_type='revenue', is_active=True)
                .order_by('code').first()
            )
            if revenue_account is None:
                self.stdout.write(self.style.WARNING(
                    f'[{tenant.slug}] no revenue account; run seed_accounting first.'))
                continue

            shipments = Shipment.objects.select_related('sales_order').filter(
                tenant=tenant, status='delivered',
            )
            created = 0
            skipped = 0
            for shipment in shipments:
                if ARInvoice.objects.filter(tenant=tenant, source_shipment=shipment,
                                            deleted_at__isnull=True).exists():
                    skipped += 1
                    continue
                so = shipment.sales_order
                customer_name = (so.customer_name or '').strip() or 'Walk-in Customer'
                customer, _ = Customer.objects.get_or_create(
                    tenant=tenant, company_name=customer_name,
                    defaults={'contact_email': so.customer_email or '',
                              'contact_phone': so.customer_phone or '',
                              'billing_address': so.billing_address or ''},
                )
                invoice = ARInvoice.objects.create(
                    tenant=tenant, customer=customer,
                    source_so=so, source_shipment=shipment,
                    invoice_date=shipment.shipped_date.date() if shipment.shipped_date else so.order_date,
                    due_date=(so.order_date + timedelta(days=30)) if so.order_date else None,
                    subtotal=so.subtotal, tax_amount=so.tax_total,
                    total_amount=so.grand_total,
                )
                ARInvoiceLine.objects.create(
                    invoice=invoice, gl_account=revenue_account,
                    description=f'Shipment {shipment.shipment_number} / SO {so.order_number}',
                    quantity=1, unit_price=so.subtotal, tax_rate=0, line_order=1,
                )
                created += 1
            total_created += created
            total_skipped += skipped
            self.stdout.write(f'[{tenant.slug}] created={created}, skipped={skipped}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {total_created}, skipped {total_skipped} (already linked).'))
