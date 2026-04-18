import random
from decimal import Decimal

# D-18 — deterministic seed so tests and demos see the same values each run.
_rng = random.Random(42)

from django.core.management.base import BaseCommand

from core.models import Tenant
from warehousing.models import Warehouse
from catalog.models import Product, Category
from multi_location.models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)


class Command(BaseCommand):
    help = 'Seed Multi-Location Management data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing data before seeding')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants. Run "python manage.py seed" first.'))
            return

        if options['flush']:
            self.stdout.write('Flushing existing multi-location data...')
            LocationSafetyStockRule.objects.all().delete()
            LocationTransferRule.objects.all().delete()
            LocationPricingRule.objects.all().delete()
            Location.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Multi-location data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Multi-Location seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see multi-location data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if Location.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Multi-location data already exists. Use --flush to re-seed.')
            return

        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True))
        products = list(Product.objects.filter(tenant=tenant)[:8])
        categories = list(Category.objects.filter(tenant=tenant)[:3])

        if not warehouses:
            self.stdout.write(
                f'  [{tenant.name}] No warehouses found. Run "seed_warehousing" first. Skipping.'
            )
            return

        self.stdout.write(f'  [{tenant.name}] Seeding multi-location data...')

        # ── 1. Location hierarchy ──
        company = Location.objects.create(
            tenant=tenant,
            name=f'{tenant.name} HQ',
            location_type='company',
            address='Corporate Headquarters',
            manager_name='Chief Operations Officer',
            contact_email=f'ops@{tenant.slug}.example.com',
            is_active=True,
        )

        north_region = Location.objects.create(
            tenant=tenant,
            name='North Region',
            location_type='regional_dc',
            parent=company,
            city='Seattle', state='WA', country='USA',
            manager_name='Regional Manager North',
            is_active=True,
        )

        south_region = Location.objects.create(
            tenant=tenant,
            name='South Region',
            location_type='regional_dc',
            parent=company,
            city='Austin', state='TX', country='USA',
            manager_name='Regional Manager South',
            is_active=True,
        )

        dc_north = Location.objects.create(
            tenant=tenant,
            name='Seattle DC',
            location_type='distribution_center',
            parent=north_region,
            warehouse=warehouses[0] if len(warehouses) > 0 else None,
            city='Seattle', state='WA', country='USA',
            manager_name='DC Supervisor',
            is_active=True,
        )

        dc_south = Location.objects.create(
            tenant=tenant,
            name='Austin DC',
            location_type='distribution_center',
            parent=south_region,
            warehouse=warehouses[1] if len(warehouses) > 1 else None,
            city='Austin', state='TX', country='USA',
            manager_name='DC Supervisor',
            is_active=True,
        )

        store_north = Location.objects.create(
            tenant=tenant,
            name='Seattle Downtown Store',
            location_type='retail_store',
            parent=north_region,
            city='Seattle', state='WA', country='USA',
            manager_name='Store Manager',
            contact_phone='+1-206-555-0101',
            is_active=True,
        )

        store_south = Location.objects.create(
            tenant=tenant,
            name='Austin Retail Store',
            location_type='retail_store',
            parent=south_region,
            city='Austin', state='TX', country='USA',
            manager_name='Store Manager',
            contact_phone='+1-512-555-0202',
            is_active=True,
        )

        dcs = [dc_north, dc_south]
        stores = [store_north, store_south]

        # ── 2. Pricing rules ──
        if categories:
            LocationPricingRule.objects.create(
                tenant=tenant, location=store_north, category=categories[0],
                rule_type='markup_pct', value=Decimal('15.00'), priority=1,
                notes='North premium market markup',
            )
            LocationPricingRule.objects.create(
                tenant=tenant, location=store_south, category=categories[0],
                rule_type='markdown_pct', value=Decimal('5.00'), priority=1,
                notes='South competitive markdown',
            )
        if products:
            LocationPricingRule.objects.create(
                tenant=tenant, location=dc_north, product=products[0],
                rule_type='fixed_adjustment', value=Decimal('-2.50'), priority=2,
                notes='Wholesale DC discount',
            )
            LocationPricingRule.objects.create(
                tenant=tenant, location=store_north, product=products[1] if len(products) > 1 else products[0],
                rule_type='override_price', value=Decimal('99.99'), priority=1,
                notes='Promotional override',
            )

        # ── 3. Transfer rules ──
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc_north, destination_location=store_north,
            allowed=True, max_transfer_qty=500, lead_time_days=1,
            requires_approval=False, priority=1, notes='DC-to-store primary route',
        )
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc_south, destination_location=store_south,
            allowed=True, max_transfer_qty=500, lead_time_days=1,
            requires_approval=False, priority=1,
        )
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=dc_north, destination_location=dc_south,
            allowed=True, max_transfer_qty=200, lead_time_days=3,
            requires_approval=True, priority=2, notes='Inter-DC rebalancing',
        )
        LocationTransferRule.objects.create(
            tenant=tenant, source_location=store_north, destination_location=store_south,
            allowed=False, max_transfer_qty=0, lead_time_days=0,
            priority=3, notes='Store-to-store transfers blocked by policy',
        )

        # ── 4. Safety stock rules ──
        if products:
            for idx, product in enumerate(products[:6]):
                location = dcs[idx % len(dcs)]
                LocationSafetyStockRule.objects.create(
                    tenant=tenant, location=location, product=product,
                    safety_stock_qty=_rng.choice([10, 20, 30, 50]),
                    reorder_point=_rng.choice([20, 40, 60, 100]),
                    max_stock_qty=_rng.choice([200, 500, 1000]),
                    notes='Seeded demo rule',
                )
            for idx, product in enumerate(products[:4]):
                store = stores[idx % len(stores)]
                LocationSafetyStockRule.objects.create(
                    tenant=tenant, location=store, product=product,
                    safety_stock_qty=_rng.choice([5, 10, 15]),
                    reorder_point=_rng.choice([10, 20, 30]),
                    max_stock_qty=_rng.choice([50, 100, 200]),
                )

        self.stdout.write(f'  [{tenant.name}] Seeded 7 locations, 4 pricing rules, 4 transfer rules, 10 safety stock rules')
