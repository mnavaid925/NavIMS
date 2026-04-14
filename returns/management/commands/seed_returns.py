import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import Warehouse
from orders.models import SalesOrder
from returns.models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)


class Command(BaseCommand):
    help = 'Seed Returns Management (RMA) data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing returns data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing returns data...')
            RefundCredit.objects.all().delete()
            DispositionItem.objects.all().delete()
            Disposition.objects.all().delete()
            ReturnInspectionItem.objects.all().delete()
            ReturnInspection.objects.all().delete()
            ReturnAuthorizationItem.objects.all().delete()
            ReturnAuthorization.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Returns data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Returns Management seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see returns data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if ReturnAuthorization.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Returns data already exists. Use --flush to re-seed.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding returns data...')

        sales_orders = list(SalesOrder.objects.filter(
            tenant=tenant, status__in=['delivered', 'closed', 'shipped'],
        )[:5])
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        users = list(User.objects.filter(tenant=tenant)[:3])
        products = list(Product.objects.filter(tenant=tenant, status='active')[:6])

        if not sales_orders or not warehouses or not users or not products:
            self.stdout.write(f'  [{tenant.name}] Missing sales orders, warehouses, users, or products. Skipping.')
            return

        today = timezone.now().date()
        now = timezone.now()

        reason_cycle = ['defective', 'wrong_item', 'not_as_described', 'customer_change', 'warranty']
        status_cycle = ['draft', 'pending', 'approved', 'received', 'closed']

        rmas = []
        for i in range(5):
            so = sales_orders[i % len(sales_orders)]
            warehouse = warehouses[i % len(warehouses)]
            reason = reason_cycle[i]
            status = status_cycle[i]

            rma = ReturnAuthorization.objects.create(
                tenant=tenant,
                sales_order=so,
                customer_name=so.customer_name,
                customer_email=so.customer_email,
                customer_phone=so.customer_phone,
                return_address=so.shipping_address,
                reason=reason,
                status=status,
                requested_date=today - timedelta(days=10 - i),
                expected_return_date=today + timedelta(days=5 - i),
                warehouse=warehouse,
                notes=f'Seeded RMA #{i + 1} — {reason}',
                created_by=users[0],
                approved_by=users[0] if status in ['approved', 'received', 'closed'] else None,
                approved_at=now - timedelta(days=5 - i) if status in ['approved', 'received', 'closed'] else None,
                received_at=now - timedelta(days=3 - i) if status in ['received', 'closed'] else None,
                closed_at=now - timedelta(days=1) if status == 'closed' else None,
            )

            so_items = list(so.items.all()[:2])
            if not so_items:
                for p in products[:2]:
                    ReturnAuthorizationItem.objects.create(
                        tenant=tenant,
                        rma=rma,
                        product=p,
                        description=f'Return of {p.name}',
                        qty_requested=random.randint(1, 3),
                        qty_received=random.randint(1, 3) if status in ['received', 'closed'] else 0,
                        unit_price=p.retail_price or Decimal('10.00'),
                        reason_note='',
                    )
            else:
                for soi in so_items:
                    qty_req = random.randint(1, max(1, soi.quantity))
                    ReturnAuthorizationItem.objects.create(
                        tenant=tenant,
                        rma=rma,
                        sales_order_item=soi,
                        product=soi.product,
                        description=soi.description,
                        qty_requested=qty_req,
                        qty_received=qty_req if status in ['received', 'closed'] else 0,
                        unit_price=soi.unit_price,
                        reason_note='',
                    )
            rmas.append(rma)

        # Inspections for received/closed RMAs
        inspections = []
        for rma in rmas:
            if rma.status not in ['received', 'closed']:
                continue
            insp = ReturnInspection.objects.create(
                tenant=tenant,
                rma=rma,
                status='completed',
                overall_result=random.choice(['pass', 'fail', 'partial']),
                inspector=users[min(1, len(users) - 1)],
                inspected_date=today - timedelta(days=2),
                started_at=now - timedelta(days=2, hours=4),
                completed_at=now - timedelta(days=2),
                notes='Seeded inspection',
            )
            for rma_item in rma.items.all():
                condition = random.choice(['good', 'minor_damage', 'defective'])
                restockable = condition == 'good'
                qty = rma_item.qty_received or rma_item.qty_requested
                ReturnInspectionItem.objects.create(
                    tenant=tenant,
                    inspection=insp,
                    rma_item=rma_item,
                    qty_inspected=qty,
                    qty_passed=qty if restockable else 0,
                    qty_failed=0 if restockable else qty,
                    condition=condition,
                    restockable=restockable,
                    notes='',
                )
            inspections.append(insp)

        # Dispositions
        for insp in inspections:
            decision = random.choice(['restock', 'repair', 'scrap', 'liquidate'])
            disp = Disposition.objects.create(
                tenant=tenant,
                rma=insp.rma,
                inspection=insp,
                decision=decision,
                warehouse=insp.rma.warehouse,
                status='processed' if insp.rma.status == 'closed' else 'pending',
                processed_by=users[0] if insp.rma.status == 'closed' else None,
                processed_at=now - timedelta(days=1) if insp.rma.status == 'closed' else None,
                notes=f'Seeded disposition — {decision}',
            )
            for ins_item in insp.items.all():
                DispositionItem.objects.create(
                    tenant=tenant,
                    disposition=disp,
                    inspection_item=ins_item,
                    product=ins_item.rma_item.product,
                    qty=ins_item.qty_inspected,
                    notes='',
                )

        # Refunds for received/closed RMAs
        for rma in rmas:
            if rma.status not in ['received', 'closed']:
                continue
            RefundCredit.objects.create(
                tenant=tenant,
                rma=rma,
                type=random.choice(['refund', 'credit_note', 'store_credit']),
                method=random.choice(['card', 'bank_transfer', 'store_credit']),
                amount=rma.total_value,
                currency='USD',
                reference_number=f'TXN-{random.randint(100000, 999999)}',
                status='processed' if rma.status == 'closed' else 'pending',
                processed_by=users[0] if rma.status == 'closed' else None,
                processed_at=now - timedelta(hours=12) if rma.status == 'closed' else None,
                notes='Seeded refund',
            )

        self.stdout.write(self.style.SUCCESS(
            f'  [{tenant.name}] Created {len(rmas)} RMAs, {len(inspections)} inspections, dispositions, and refunds.'
        ))
