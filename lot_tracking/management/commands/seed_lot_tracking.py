import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import Warehouse
from receiving.models import GoodsReceiptNote
from lot_tracking.models import LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog


class Command(BaseCommand):
    help = 'Seed lot & serial tracking data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing lot tracking data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing lot tracking data...')
            TraceabilityLog.objects.all().delete()
            ExpiryAlert.objects.all().delete()
            SerialNumber.objects.all().delete()
            LotBatch.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Lot tracking data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Lot tracking seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see lot tracking data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if LotBatch.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Lot tracking data already exists. Use --flush to re-seed.')
            return

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:8])
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        users = list(User.objects.filter(tenant=tenant)[:3])
        grns = list(GoodsReceiptNote.objects.filter(tenant=tenant)[:4])

        if not products:
            self.stdout.write(f'  [{tenant.name}] No products found. Run seed_catalog first.')
            return
        if not warehouses:
            self.stdout.write(f'  [{tenant.name}] No warehouses found. Run seed_warehousing first.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding lot tracking data...')

        now = timezone.now()
        user = users[0] if users else None
        lots_created = 0
        serials_created = 0
        alerts_created = 0
        logs_created = 0

        # 1. Create Lot/Batch records (8 per tenant)
        lot_configs = [
            {'status': 'active', 'days_offset': 90, 'qty': 100},
            {'status': 'active', 'days_offset': 60, 'qty': 250},
            {'status': 'active', 'days_offset': 15, 'qty': 50},
            {'status': 'active', 'days_offset': -5, 'qty': 75},
            {'status': 'quarantine', 'days_offset': 30, 'qty': 40},
            {'status': 'expired', 'days_offset': -30, 'qty': 120},
            {'status': 'consumed', 'days_offset': None, 'qty': 200},
            {'status': 'recalled', 'days_offset': 45, 'qty': 60},
        ]

        lots = []
        for i, cfg in enumerate(lot_configs):
            product = products[i % len(products)]
            warehouse = warehouses[i % len(warehouses)]
            grn = grns[i % len(grns)] if grns else None

            expiry = None
            if cfg['days_offset'] is not None:
                expiry = (now + timedelta(days=cfg['days_offset'])).date()

            mfg_date = (now - timedelta(days=random.randint(30, 180))).date()
            available = cfg['qty'] if cfg['status'] == 'active' else (0 if cfg['status'] in ('consumed', 'recalled') else random.randint(0, cfg['qty']))

            lot = LotBatch(
                tenant=tenant,
                product=product,
                warehouse=warehouse,
                grn=grn,
                quantity=cfg['qty'],
                available_quantity=available,
                manufacturing_date=mfg_date,
                expiry_date=expiry,
                supplier_batch_number=f'SUP-{random.randint(1000, 9999)}',
                status=cfg['status'],
                created_by=user,
                notes=f'Seed lot #{i + 1} — {cfg["status"]}',
            )
            lot.save()
            lots.append(lot)
            lots_created += 1

        # 2. Create Serial Numbers (12 per tenant)
        serial_statuses = ['available', 'available', 'available', 'allocated', 'allocated',
                           'sold', 'sold', 'returned', 'damaged', 'available', 'available', 'scrapped']
        for i in range(12):
            product = products[i % len(products)]
            lot = lots[i % len(lots)] if lots[i % len(lots)].status == 'active' else None
            warehouse = warehouses[i % len(warehouses)]

            serial = SerialNumber(
                tenant=tenant,
                serial_number=f'SN-{product.sku}-{i + 1:04d}',
                product=product,
                lot=lot,
                warehouse=warehouse if serial_statuses[i] not in ('sold',) else None,
                status=serial_statuses[i],
                purchase_date=(now - timedelta(days=random.randint(10, 120))).date(),
                warranty_expiry=(now + timedelta(days=random.randint(-30, 365))).date(),
                created_by=user,
                notes=f'Seed serial #{i + 1}',
            )
            serial.save()
            serials_created += 1

        # 3. Create Expiry Alerts (5 per tenant)
        alert_configs = [
            {'lot_idx': 2, 'type': 'approaching', 'days': 15},
            {'lot_idx': 3, 'type': 'expired', 'days': -5},
            {'lot_idx': 5, 'type': 'expired', 'days': -30},
            {'lot_idx': 0, 'type': 'approaching', 'days': 90},
            {'lot_idx': 7, 'type': 'recalled', 'days': 45},
        ]
        for ac in alert_configs:
            lot = lots[ac['lot_idx']]
            ExpiryAlert.objects.create(
                tenant=tenant,
                lot=lot,
                alert_type=ac['type'],
                alert_date=now.date(),
                days_before_expiry=ac['days'],
                is_acknowledged=random.random() < 0.3,
                acknowledged_by=user if random.random() < 0.3 else None,
                acknowledged_at=now if random.random() < 0.3 else None,
            )
            alerts_created += 1

        # 4. Create Traceability Logs (10 per tenant)
        event_types = ['received', 'received', 'transferred', 'adjusted', 'sold',
                       'returned', 'received', 'transferred', 'expired', 'recalled']
        for i in range(10):
            lot = lots[i % len(lots)]
            serial = None
            if i < 5:
                serial_qs = SerialNumber.objects.filter(tenant=tenant)
                if serial_qs.exists():
                    serial = serial_qs[i % serial_qs.count()]

            from_wh = warehouses[0] if event_types[i] in ('transferred', 'sold') else None
            to_wh = warehouses[1] if event_types[i] in ('transferred', 'received') else None

            log = TraceabilityLog(
                tenant=tenant,
                lot=lot,
                serial_number=serial,
                event_type=event_types[i],
                from_warehouse=from_wh,
                to_warehouse=to_wh,
                quantity=random.randint(5, 50),
                reference_type=random.choice(['GRN', 'Transfer', 'Adjustment', 'Sales Order']),
                reference_number=f'REF-{random.randint(1000, 9999)}',
                performed_by=user,
                notes=f'Seed trace log #{i + 1}',
            )
            log.save()
            logs_created += 1

        self.stdout.write(f'    Lots: {lots_created}')
        self.stdout.write(f'    Serial Numbers: {serials_created}')
        self.stdout.write(f'    Expiry Alerts: {alerts_created}')
        self.stdout.write(f'    Traceability Logs: {logs_created}')
