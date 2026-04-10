import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import Warehouse, Bin
from stock_movements.models import (
    StockTransfer, StockTransferItem,
    TransferApprovalRule, TransferApproval,
    TransferRoute,
)


class Command(BaseCommand):
    help = 'Seed stock movements data (transfers, approval rules, routes) for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing stock movements data before seeding',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants found. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing stock movements data...')
            TransferApproval.objects.all().delete()
            StockTransferItem.objects.all().delete()
            StockTransfer.objects.all().delete()
            TransferApprovalRule.objects.all().delete()
            TransferRoute.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Stock movements data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Stock movements seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see stock movements data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if StockTransfer.objects.filter(tenant=tenant).exists():
            self.stdout.write(f'  [{tenant.name}] Stock movements data already exists. Use --flush to re-seed.')
            return

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:8])
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        users = list(User.objects.filter(tenant=tenant)[:3])

        if not products:
            self.stdout.write(f'  [{tenant.name}] No products found. Run seed_catalog first.')
            return
        if not warehouses:
            self.stdout.write(f'  [{tenant.name}] No warehouses found. Run seed_warehousing first.')
            return
        if len(warehouses) < 2:
            self.stdout.write(f'  [{tenant.name}] Need at least 2 warehouses for inter-warehouse transfers.')
            return

        self.stdout.write(f'  [{tenant.name}] Seeding stock movements data...')

        now = timezone.now()
        user = users[0] if users else None

        # 1. Create Transfer Approval Rules (3 per tenant)
        rules_data = [
            {'name': 'Small Transfer', 'min_items': 0, 'max_items': 3, 'requires_approval': False, 'approver_role': ''},
            {'name': 'Medium Transfer', 'min_items': 4, 'max_items': 10, 'requires_approval': True, 'approver_role': 'Manager'},
            {'name': 'Large Transfer', 'min_items': 11, 'max_items': None, 'requires_approval': True, 'approver_role': 'Admin'},
        ]
        rules_created = 0
        for rd in rules_data:
            TransferApprovalRule.objects.create(
                tenant=tenant,
                name=rd['name'],
                min_items=rd['min_items'],
                max_items=rd['max_items'],
                requires_approval=rd['requires_approval'],
                approver_role=rd['approver_role'],
                is_active=True,
            )
            rules_created += 1

        # 2. Create Transfer Routes (3 per tenant)
        methods = ['truck', 'van', 'courier']
        routes_created = 0
        wh1, wh2 = warehouses[0], warehouses[1]

        routes_data = [
            {
                'name': f'{wh1.code} to {wh2.code} — Primary',
                'source': wh1, 'dest': wh2,
                'method': 'truck', 'hours': 4, 'km': Decimal('85.50'),
                'instructions': f'Take main highway from {wh1.name} to {wh2.name}. Use loading dock B on arrival.',
            },
            {
                'name': f'{wh2.code} to {wh1.code} — Return',
                'source': wh2, 'dest': wh1,
                'method': 'truck', 'hours': 4, 'km': Decimal('85.50'),
                'instructions': f'Return route from {wh2.name} to {wh1.name}. Use loading dock A on arrival.',
            },
            {
                'name': f'{wh1.code} to {wh2.code} — Express',
                'source': wh1, 'dest': wh2,
                'method': 'courier', 'hours': 2, 'km': Decimal('85.50'),
                'instructions': 'Express courier for urgent transfers. Max 5 pallets.',
            },
        ]
        for rd in routes_data:
            TransferRoute.objects.create(
                tenant=tenant,
                name=rd['name'],
                source_warehouse=rd['source'],
                destination_warehouse=rd['dest'],
                transit_method=rd['method'],
                estimated_duration_hours=rd['hours'],
                distance_km=rd['km'],
                instructions=rd['instructions'],
                is_active=True,
            )
            routes_created += 1

        # 3. Create Stock Transfers (6 per tenant — mix of types and statuses)
        transfers_created = 0
        items_created = 0
        approvals_created = 0

        transfer_configs = [
            {'type': 'inter_warehouse', 'status': 'draft', 'priority': 'normal'},
            {'type': 'inter_warehouse', 'status': 'pending_approval', 'priority': 'high'},
            {'type': 'inter_warehouse', 'status': 'approved', 'priority': 'normal'},
            {'type': 'inter_warehouse', 'status': 'in_transit', 'priority': 'urgent'},
            {'type': 'inter_warehouse', 'status': 'completed', 'priority': 'normal'},
            {'type': 'intra_warehouse', 'status': 'completed', 'priority': 'low'},
        ]

        for i, cfg in enumerate(transfer_configs):
            if cfg['type'] == 'inter_warehouse':
                src = warehouses[i % 2]
                dest = warehouses[(i + 1) % 2]
            else:
                src = warehouses[0]
                dest = warehouses[0]

            transfer = StockTransfer(
                tenant=tenant,
                transfer_type=cfg['type'],
                source_warehouse=src,
                destination_warehouse=dest,
                status=cfg['status'],
                priority=cfg['priority'],
                requested_by=user,
                notes=f'Seed transfer #{i + 1} — {cfg["type"]} ({cfg["status"]})',
            )

            if cfg['status'] in ('approved', 'in_transit', 'completed'):
                transfer.approved_by = user
                transfer.approved_at = now - timedelta(days=random.randint(1, 10))
            if cfg['status'] in ('in_transit', 'completed'):
                transfer.shipped_at = now - timedelta(days=random.randint(0, 3))
            if cfg['status'] == 'completed':
                transfer.completed_at = now - timedelta(hours=random.randint(1, 48))

            transfer.save()
            transfers_created += 1

            # Add 2-4 items per transfer
            num_items = random.randint(2, 4)
            used_products = random.sample(products, min(num_items, len(products)))
            for product in used_products:
                qty = random.randint(5, 50)
                received = qty if cfg['status'] == 'completed' else 0
                StockTransferItem.objects.create(
                    tenant=tenant,
                    transfer=transfer,
                    product=product,
                    quantity=qty,
                    received_quantity=received,
                    notes='',
                )
                items_created += 1

            # Add approval record for approved/completed/in_transit transfers
            if cfg['status'] in ('approved', 'in_transit', 'completed'):
                TransferApproval.objects.create(
                    tenant=tenant,
                    transfer=transfer,
                    approved_by=user,
                    decision='approved',
                    comments=f'Approved — seed data for transfer #{i + 1}',
                )
                approvals_created += 1

        self.stdout.write(f'    Approval Rules: {rules_created}')
        self.stdout.write(f'    Transfer Routes: {routes_created}')
        self.stdout.write(f'    Transfers: {transfers_created}')
        self.stdout.write(f'    Transfer Items: {items_created}')
        self.stdout.write(f'    Approvals: {approvals_created}')
