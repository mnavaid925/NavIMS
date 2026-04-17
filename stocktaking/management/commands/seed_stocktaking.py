import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from warehousing.models import Warehouse
from inventory.models import StockLevel
from stocktaking.models import (
    StocktakeFreeze, CycleCountSchedule,
    StockCount, StockCountItem, StockVarianceAdjustment,
)


class Command(BaseCommand):
    help = 'Seed Stocktaking & Cycle Counting data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing data before seeding')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants. Run "python manage.py seed" first.'))
            return

        if options['flush']:
            self.stdout.write('Flushing existing stocktaking data...')
            StockVarianceAdjustment.objects.all().delete()
            StockCountItem.objects.all().delete()
            StockCount.objects.all().delete()
            CycleCountSchedule.objects.all().delete()
            StocktakeFreeze.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Stocktaking data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Stocktaking seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see stocktaking data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if StockCount.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Stocktaking data already exists. Use --flush to re-seed.')
            return

        # D-18 — deterministic per-tenant variance pattern so bug reports
        # are reproducible against a freshly seeded environment.
        random.seed(f'stocktaking-{tenant.pk}')

        self.stdout.write(f'  [{tenant.name}] Seeding stocktaking data...')

        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        users = list(User.objects.filter(tenant=tenant)[:3])
        stock_levels = list(StockLevel.objects.filter(tenant=tenant).select_related('product'))

        if not warehouses or not users or not stock_levels:
            self.stdout.write(f'  [{tenant.name}] Missing warehouses, users, or stock levels. Skipping.')
            return

        today = timezone.now().date()
        now = timezone.now()

        # 2 cycle count schedules
        sched_a = CycleCountSchedule.objects.create(
            tenant=tenant,
            name='Weekly Class A High-Value Count',
            frequency='weekly',
            abc_class='a',
            warehouse=warehouses[0],
            next_run_date=today + timedelta(days=7),
            last_run_date=today - timedelta(days=7),
            is_active=True,
            notes='Automatic weekly count of high-value Class A items.',
            created_by=users[0],
        )
        sched_b = CycleCountSchedule.objects.create(
            tenant=tenant,
            name='Monthly Class B/C Count',
            frequency='monthly',
            abc_class='b',
            warehouse=warehouses[0],
            next_run_date=today + timedelta(days=30),
            is_active=True,
            notes='Monthly count for medium-value items.',
            created_by=users[0],
        )

        # 1 active freeze
        freeze = StocktakeFreeze.objects.create(
            tenant=tenant,
            warehouse=warehouses[0],
            status='active',
            reason='Year-end physical inventory',
            frozen_at=now - timedelta(hours=2),
            frozen_by=users[0],
            notes='Seeded active freeze for year-end count.',
        )

        # 3 stock counts across statuses
        count_configs = [
            ('draft', 'cycle', False, sched_a, None),
            ('in_progress', 'cycle', True, sched_a, None),
            ('adjusted', 'full', False, None, freeze),
        ]

        created_counts = []
        for status, ctype, blind, sched, frz in count_configs:
            count = StockCount.objects.create(
                tenant=tenant,
                type=ctype,
                warehouse=warehouses[0],
                schedule=sched,
                freeze=frz,
                status=status,
                blind_count=blind,
                scheduled_date=today - timedelta(days=2),
                started_at=now - timedelta(days=2) if status != 'draft' else None,
                completed_at=now - timedelta(days=1) if status == 'adjusted' else None,
                reviewed_at=now - timedelta(hours=12) if status == 'adjusted' else None,
                adjusted_at=now - timedelta(hours=6) if status == 'adjusted' else None,
                assigned_to=users[min(1, len(users) - 1)],
                counted_by=users[0] if status == 'adjusted' else None,
                reviewed_by=users[0] if status == 'adjusted' else None,
                created_by=users[0],
                notes=f'Seeded {status} {ctype} count',
            )

            sampled = [sl for sl in stock_levels if sl.warehouse == warehouses[0]][:6]
            if not sampled:
                sampled = stock_levels[:6]

            for sl in sampled:
                counted_qty = None
                counted_at = None
                counted_by = None
                reason_code = ''
                if status == 'adjusted':
                    # Create some variances
                    delta = random.choice([-2, -1, 0, 0, 1])
                    counted_qty = max(0, sl.on_hand + delta)
                    counted_at = now - timedelta(days=1)
                    counted_by = users[0]
                    if delta != 0:
                        reason_code = random.choice(['miscount', 'damage', 'misplaced'])
                elif status == 'in_progress':
                    # Half counted
                    if random.random() < 0.5:
                        counted_qty = sl.on_hand
                        counted_at = now - timedelta(hours=1)
                        counted_by = users[0]

                StockCountItem.objects.create(
                    tenant=tenant,
                    count=count,
                    product=sl.product,
                    system_qty=sl.on_hand,
                    counted_qty=counted_qty,
                    unit_cost=sl.product.purchase_cost or Decimal('0.00'),
                    reason_code=reason_code,
                    counted_at=counted_at,
                    counted_by=counted_by,
                )
            created_counts.append(count)

        # 1 posted variance adjustment for the adjusted count
        adjusted_count = created_counts[2]
        total_qty = 0
        total_value = Decimal('0.00')
        for item in adjusted_count.items.exclude(counted_qty__isnull=True):
            if item.has_variance:
                total_qty += item.variance
                total_value += item.variance_value

        StockVarianceAdjustment.objects.create(
            tenant=tenant,
            count=adjusted_count,
            status='posted',
            reason_code='miscount',
            total_variance_qty=total_qty,
            total_variance_value=total_value,
            approved_by=users[0],
            approved_at=now - timedelta(hours=8),
            posted_by=users[0],
            posted_at=now - timedelta(hours=6),
            notes='Seeded posted variance adjustment.',
            created_by=users[0],
        )

        self.stdout.write(self.style.SUCCESS(
            f'  [{tenant.name}] Created 2 schedules, 1 freeze, 3 counts, 1 posted variance adjustment.'
        ))
