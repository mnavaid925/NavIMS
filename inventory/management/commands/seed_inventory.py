import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from catalog.models import Product
from warehousing.models import Warehouse
from inventory.models import (
    StockLevel, StockAdjustment, StockStatus, StockStatusTransition,
    ValuationConfig, InventoryValuation, ValuationEntry, InventoryReservation,
)


class Command(BaseCommand):
    help = 'Seed inventory data (stock levels, statuses, valuations, reservations) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing inventory data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing inventory data...')
            InventoryReservation.objects.all().delete()
            InventoryValuation.objects.all().delete()
            ValuationEntry.objects.all().delete()
            ValuationConfig.objects.all().delete()
            StockStatusTransition.objects.all().delete()
            StockStatus.objects.all().delete()
            StockAdjustment.objects.all().delete()
            StockLevel.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Inventory data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Inventory seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see inventory data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if StockLevel.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Inventory data already exists. Use --flush to re-seed.')
            return

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:8])
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])

        if not products:
            self.stdout.write(f'  [{tenant.name}] No products found. Run seed_catalog first.')
            return
        if not warehouses:
            self.stdout.write(f'  [{tenant.name}] No warehouses found. Run seed_warehousing first.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding inventory data...')

        now = timezone.now()
        stock_levels = []
        stock_statuses_created = 0
        adjustments_created = 0
        transitions_created = 0
        entries_created = 0
        valuations_created = 0
        reservations_created = 0

        # 1. Create StockLevel records for each product + warehouse
        for product in products:
            for warehouse in warehouses:
                on_hand = random.randint(50, 500)
                allocated = random.randint(0, min(50, on_hand // 4))
                on_order = random.randint(0, 100)

                sl = StockLevel.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=warehouse,
                    on_hand=on_hand,
                    allocated=allocated,
                    on_order=on_order,
                    reorder_point=random.randint(10, 50),
                    reorder_quantity=random.randint(50, 200),
                )
                stock_levels.append(sl)

                # 2. Create StockStatus records — every product gets an 'active' status
                active_qty = on_hand - random.randint(0, min(10, on_hand // 10))
                StockStatus.objects.create(
                    tenant=tenant,
                    product=product,
                    warehouse=warehouse,
                    status='active',
                    quantity=max(active_qty, 0),
                )
                stock_statuses_created += 1

                # Some products also get damaged/on_hold
                remaining = on_hand - active_qty
                if remaining > 0 and random.random() < 0.4:
                    dmg_status = random.choice(['damaged', 'on_hold'])
                    StockStatus.objects.create(
                        tenant=tenant,
                        product=product,
                        warehouse=warehouse,
                        status=dmg_status,
                        quantity=remaining,
                    )
                    stock_statuses_created += 1

                # 3. Create ValuationEntry cost layers (2-3 per product+warehouse)
                num_layers = random.randint(2, 3)
                for i in range(num_layers):
                    entry_date = (now - timedelta(days=random.randint(5, 90))).date()
                    qty = random.randint(20, 100)
                    unit_cost = Decimal(str(round(random.uniform(5.0, 50.0), 2)))
                    ValuationEntry.objects.create(
                        tenant=tenant,
                        product=product,
                        warehouse=warehouse,
                        entry_date=entry_date,
                        quantity=qty,
                        remaining_quantity=random.randint(5, qty),
                        unit_cost=unit_cost,
                        reference_type=random.choice(['GRN', 'PO', 'Adjustment']),
                        reference_number=f'REF-{random.randint(1000, 9999)}',
                    )
                    entries_created += 1

        # 4. Create StockAdjustment records (4 per tenant)
        adj_types = ['increase', 'decrease', 'correction']
        adj_reasons = ['count', 'damage', 'theft', 'return', 'correction', 'other']
        for i in range(4):
            sl = random.choice(stock_levels)
            adj = StockAdjustment(
                tenant=tenant,
                stock_level=sl,
                adjustment_type=random.choice(adj_types),
                quantity=random.randint(1, 20),
                reason=random.choice(adj_reasons),
                notes=f'Seed adjustment #{i + 1}',
            )
            adj.save()
            adjustments_created += 1

        # 5. Create StockStatusTransition records (3 per tenant)
        for i in range(3):
            sl = random.choice(stock_levels)
            statuses = ['active', 'damaged', 'expired', 'on_hold']
            from_s = random.choice(statuses)
            to_s = random.choice([s for s in statuses if s != from_s])
            t = StockStatusTransition(
                tenant=tenant,
                product=sl.product,
                warehouse=sl.warehouse,
                from_status=from_s,
                to_status=to_s,
                quantity=random.randint(1, 10),
                reason=f'Seed transition #{i + 1}',
            )
            t.save()
            transitions_created += 1

        # 6. Create ValuationConfig
        ValuationConfig.objects.create(
            tenant=tenant,
            method='weighted_avg',
            auto_recalculate=True,
            last_calculated_at=now,
        )

        # 7. Create InventoryValuation snapshots
        today = now.date()
        for sl in stock_levels:
            entries = ValuationEntry.objects.filter(
                tenant=tenant, product=sl.product, warehouse=sl.warehouse,
                remaining_quantity__gt=0,
            )
            total_qty = sum(e.remaining_quantity for e in entries)
            if total_qty > 0:
                total_cost = sum(e.remaining_quantity * e.unit_cost for e in entries)
                unit_cost = total_cost / total_qty
                InventoryValuation.objects.create(
                    tenant=tenant,
                    product=sl.product,
                    warehouse=sl.warehouse,
                    valuation_date=today,
                    method='weighted_avg',
                    total_quantity=total_qty,
                    unit_cost=round(unit_cost, 2),
                    total_value=round(total_qty * unit_cost, 2),
                )
                valuations_created += 1

        # 8. Create InventoryReservation records (4 per tenant)
        res_statuses = ['pending', 'confirmed', 'released', 'pending']
        ref_types = ['Sales Order', 'Job', 'Transfer', 'Sales Order']
        for i in range(4):
            sl = random.choice(stock_levels)
            qty = random.randint(5, 30)
            expires = now + timedelta(days=random.randint(7, 30)) if random.random() < 0.5 else None
            res = InventoryReservation(
                tenant=tenant,
                product=sl.product,
                warehouse=sl.warehouse,
                quantity=qty,
                reference_type=ref_types[i],
                reference_number=f'{ref_types[i][:2].upper()}-{random.randint(1000, 9999):05d}',
                status=res_statuses[i],
                expires_at=expires,
                notes=f'Seed reservation #{i + 1}',
            )
            res.save()
            reservations_created += 1

        self.stdout.write(f'    Stock Levels: {len(stock_levels)}')
        self.stdout.write(f'    Stock Statuses: {stock_statuses_created}')
        self.stdout.write(f'    Stock Adjustments: {adjustments_created}')
        self.stdout.write(f'    Status Transitions: {transitions_created}')
        self.stdout.write(f'    Valuation Entries: {entries_created}')
        self.stdout.write(f'    Valuations: {valuations_created}')
        self.stdout.write(f'    Reservations: {reservations_created}')
        self.stdout.write(f'    Valuation Config: 1')
