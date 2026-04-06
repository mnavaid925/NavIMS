from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import (
    Warehouse, Zone, Aisle, Rack, Bin,
    CrossDockOrder, CrossDockItem,
)


class Command(BaseCommand):
    help = 'Seed warehousing data (warehouses, zones, aisles, racks, bins, cross-dock orders) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing warehousing data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)

        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing warehousing data...')
            CrossDockItem.objects.all().delete()
            CrossDockOrder.objects.all().delete()
            Bin.objects.all().delete()
            Rack.objects.all().delete()
            Aisle.objects.all().delete()
            Zone.objects.all().delete()
            Warehouse.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Warehousing data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Warehousing seeding complete!'))
        self.stdout.write(self.style.WARNING(
            'Note: Superuser "admin" has no tenant — data won\'t appear when logged in as admin.'
        ))
        self.stdout.write('Login as a tenant admin (e.g., admin_acme / demo123) to see warehousing data.')

    def _seed_tenant(self, tenant):
        if Warehouse.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Warehousing data already exists. Use --flush to re-seed.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding warehousing data...')

        # Get a user for created_by
        admin_user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()

        # ── Warehouse 1: Main Distribution Center ──
        wh1 = Warehouse.objects.create(
            tenant=tenant,
            name='Main Distribution Center',
            warehouse_type='distribution_center',
            address='100 Industrial Blvd',
            city='Chicago',
            state='Illinois',
            country='United States',
            postal_code='60601',
            contact_person='John Smith',
            contact_email='warehouse@example.com',
            contact_phone='+1-312-555-0100',
            description='Primary distribution center for all outbound operations.',
        )

        # Zones for WH1
        z1_recv = Zone.objects.create(
            tenant=tenant, warehouse=wh1,
            name='Receiving Dock', code='Z-RCV-01',
            zone_type='receiving',
            description='Inbound goods receiving area.',
        )
        z1_stor = Zone.objects.create(
            tenant=tenant, warehouse=wh1,
            name='Main Storage', code='Z-STR-01',
            zone_type='storage',
            description='General purpose storage area.',
        )
        z1_ship = Zone.objects.create(
            tenant=tenant, warehouse=wh1,
            name='Shipping Dock', code='Z-SHP-01',
            zone_type='shipping',
            description='Outbound shipping area.',
        )
        z1_stag = Zone.objects.create(
            tenant=tenant, warehouse=wh1,
            name='Staging Area', code='Z-STG-01',
            zone_type='staging',
            description='Order staging and consolidation.',
        )
        z1_xdock = Zone.objects.create(
            tenant=tenant, warehouse=wh1,
            name='Cross-Dock Bay', code='Z-XDK-01',
            zone_type='cross_dock',
            description='Direct transfer bay - receiving to shipping.',
        )

        # Aisles and Racks for Main Storage
        for aisle_num in range(1, 4):
            aisle = Aisle.objects.create(
                tenant=tenant, zone=z1_stor,
                name=f'Aisle {aisle_num}', code=f'A-{aisle_num:02d}',
            )
            for rack_num in range(1, 4):
                rack = Rack.objects.create(
                    tenant=tenant, aisle=aisle,
                    name=f'Rack {aisle_num}-{rack_num}',
                    code=f'R-{aisle_num:02d}-{rack_num:02d}',
                    levels=4,
                    max_weight_capacity=Decimal('500.00'),
                )
                for bin_num in range(1, 5):
                    util = Decimal(str(bin_num * 15))
                    Bin.objects.create(
                        tenant=tenant, zone=z1_stor, rack=rack,
                        name=f'Bin {aisle_num}-{rack_num}-{bin_num}',
                        code=f'BIN-{aisle_num:02d}-{rack_num:02d}-{bin_num:02d}',
                        bin_type='standard',
                        max_weight=Decimal('100.00'),
                        max_volume=Decimal('2.50'),
                        max_quantity=50,
                        current_weight=util,
                        current_volume=util / 40,
                        current_quantity=int(util / 2),
                        is_occupied=bin_num <= 2,
                    )

        # Floor bins in receiving
        for i in range(1, 4):
            Bin.objects.create(
                tenant=tenant, zone=z1_recv,
                name=f'Receiving Floor {i}', code=f'BIN-RCV-F{i:02d}',
                bin_type='pallet',
                max_weight=Decimal('500.00'),
                max_volume=Decimal('10.00'),
                max_quantity=20,
                current_weight=Decimal('120.00') if i == 1 else Decimal('0'),
                current_volume=Decimal('2.50') if i == 1 else Decimal('0'),
                current_quantity=5 if i == 1 else 0,
                is_occupied=i == 1,
            )

        # Aisles for staging
        stag_aisle = Aisle.objects.create(
            tenant=tenant, zone=z1_stag,
            name='Staging Lane 1', code='A-STG-01',
        )
        stag_rack = Rack.objects.create(
            tenant=tenant, aisle=stag_aisle,
            name='Staging Rack 1', code='R-STG-01',
            levels=2, max_weight_capacity=Decimal('300.00'),
        )
        for i in range(1, 3):
            Bin.objects.create(
                tenant=tenant, zone=z1_stag, rack=stag_rack,
                name=f'Staging Bin {i}', code=f'BIN-STG-{i:02d}',
                bin_type='standard',
                max_weight=Decimal('150.00'),
                max_volume=Decimal('5.00'),
                max_quantity=30,
            )

        # ── Warehouse 2: Cold Storage Facility ──
        wh2 = Warehouse.objects.create(
            tenant=tenant,
            name='Cold Storage Facility',
            warehouse_type='cold_storage',
            address='200 Refrigeration Way',
            city='Chicago',
            state='Illinois',
            country='United States',
            postal_code='60602',
            contact_person='Jane Doe',
            contact_email='cold@example.com',
            contact_phone='+1-312-555-0200',
            description='Temperature-controlled storage for perishable goods.',
        )

        z2_cold = Zone.objects.create(
            tenant=tenant, warehouse=wh2,
            name='Frozen Storage', code='Z-FRZ-01',
            zone_type='storage',
            temperature_controlled=True,
            temperature_min=Decimal('-25.00'),
            temperature_max=Decimal('-18.00'),
            description='Deep freeze storage (-25C to -18C).',
        )
        z2_chill = Zone.objects.create(
            tenant=tenant, warehouse=wh2,
            name='Chilled Storage', code='Z-CHL-01',
            zone_type='storage',
            temperature_controlled=True,
            temperature_min=Decimal('2.00'),
            temperature_max=Decimal('8.00'),
            description='Chilled storage (2C to 8C).',
        )
        z2_quar = Zone.objects.create(
            tenant=tenant, warehouse=wh2,
            name='Quarantine Zone', code='Z-QRN-01',
            zone_type='quarantine',
            temperature_controlled=True,
            temperature_min=Decimal('2.00'),
            temperature_max=Decimal('8.00'),
            description='Quarantine area for inspection.',
        )

        # Cold storage aisles/racks/bins
        for zone_obj, prefix in [(z2_cold, 'FRZ'), (z2_chill, 'CHL')]:
            aisle = Aisle.objects.create(
                tenant=tenant, zone=zone_obj,
                name=f'{prefix} Aisle 1', code=f'A-{prefix}-01',
            )
            for rack_num in range(1, 3):
                rack = Rack.objects.create(
                    tenant=tenant, aisle=aisle,
                    name=f'{prefix} Rack {rack_num}',
                    code=f'R-{prefix}-{rack_num:02d}',
                    levels=3,
                    max_weight_capacity=Decimal('400.00'),
                )
                for bin_num in range(1, 4):
                    Bin.objects.create(
                        tenant=tenant, zone=zone_obj, rack=rack,
                        name=f'{prefix} Bin {rack_num}-{bin_num}',
                        code=f'BIN-{prefix}-{rack_num:02d}-{bin_num:02d}',
                        bin_type='cold',
                        max_weight=Decimal('80.00'),
                        max_volume=Decimal('2.00'),
                        max_quantity=40,
                        current_weight=Decimal('30.00') if bin_num == 1 else Decimal('0'),
                        current_volume=Decimal('0.80') if bin_num == 1 else Decimal('0'),
                        current_quantity=15 if bin_num == 1 else 0,
                        is_occupied=bin_num == 1,
                    )

        # Quarantine floor bins
        for i in range(1, 3):
            Bin.objects.create(
                tenant=tenant, zone=z2_quar,
                name=f'Quarantine Bay {i}', code=f'BIN-QRN-{i:02d}',
                bin_type='standard',
                max_weight=Decimal('200.00'),
                max_volume=Decimal('5.00'),
                max_quantity=25,
            )

        # ── Cross-Dock Orders ──
        products = list(Product.objects.filter(tenant=tenant)[:3])
        now = timezone.now()

        # Order 1: Completed
        cd1 = CrossDockOrder.objects.create(
            tenant=tenant,
            source='Vendor: ABC Supplies',
            destination='Retail Store #12',
            status='completed',
            priority='high',
            scheduled_arrival=now - timedelta(days=3),
            actual_arrival=now - timedelta(days=3, hours=-1),
            scheduled_departure=now - timedelta(days=2),
            actual_departure=now - timedelta(days=2, hours=2),
            dock_door='Dock 1',
            notes='Urgent retail replenishment.',
            created_by=admin_user,
        )
        if products:
            CrossDockItem.objects.create(
                tenant=tenant, cross_dock_order=cd1,
                product=products[0] if products else None,
                description='Electronics batch A',
                quantity=50, weight=Decimal('120.00'), volume=Decimal('3.50'),
            )
            if len(products) > 1:
                CrossDockItem.objects.create(
                    tenant=tenant, cross_dock_order=cd1,
                    product=products[1],
                    description='Accessories pack',
                    quantity=200, weight=Decimal('45.00'), volume=Decimal('1.20'),
                )

        # Order 2: Processing
        cd2 = CrossDockOrder.objects.create(
            tenant=tenant,
            source='Vendor: Global Parts',
            destination='Warehouse #2 - Cold Storage',
            status='processing',
            priority='normal',
            scheduled_arrival=now - timedelta(hours=6),
            actual_arrival=now - timedelta(hours=5),
            scheduled_departure=now + timedelta(hours=4),
            dock_door='Dock 3',
            notes='Temperature-sensitive items, handle with care.',
            created_by=admin_user,
        )
        CrossDockItem.objects.create(
            tenant=tenant, cross_dock_order=cd2,
            description='Refrigerated goods pallet A',
            quantity=30, weight=Decimal('250.00'), volume=Decimal('8.00'),
        )
        CrossDockItem.objects.create(
            tenant=tenant, cross_dock_order=cd2,
            description='Refrigerated goods pallet B',
            quantity=25, weight=Decimal('200.00'), volume=Decimal('6.50'),
        )

        # Order 3: Pending
        cd3 = CrossDockOrder.objects.create(
            tenant=tenant,
            source='Vendor: FastShip Inc.',
            destination='Distribution Hub East',
            status='pending',
            priority='low',
            scheduled_arrival=now + timedelta(days=2),
            scheduled_departure=now + timedelta(days=2, hours=6),
            notes='Standard transfer, no special handling required.',
            created_by=admin_user,
        )
        if len(products) > 2:
            CrossDockItem.objects.create(
                tenant=tenant, cross_dock_order=cd3,
                product=products[2],
                description='General merchandise',
                quantity=100, weight=Decimal('500.00'), volume=Decimal('15.00'),
            )

        # Counts
        wh_count = Warehouse.objects.filter(tenant=tenant).count()
        zone_count = Zone.objects.filter(tenant=tenant).count()
        aisle_count = Aisle.objects.filter(tenant=tenant).count()
        rack_count = Rack.objects.filter(tenant=tenant).count()
        bin_count = Bin.objects.filter(tenant=tenant).count()
        cd_count = CrossDockOrder.objects.filter(tenant=tenant).count()
        cdi_count = CrossDockItem.objects.filter(tenant=tenant).count()

        self.stdout.write(self.style.SUCCESS(
            f'  [{tenant.name}] Created: {wh_count} warehouses, {zone_count} zones, '
            f'{aisle_count} aisles, {rack_count} racks, {bin_count} bins, '
            f'{cd_count} cross-dock orders, {cdi_count} cross-dock items.'
        ))
