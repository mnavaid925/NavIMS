"""Idempotent seed command for the Quality Control & Inspection module.

Per project rules (CLAUDE.md):
- Safe to run multiple times without --flush
- Skips per-tenant if data already exists
- Prints tenant admin login creds + warns about superuser having no tenant
"""
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Category, Product
from vendors.models import Vendor
from warehousing.models import Warehouse, Zone
from inventory.models import StockAdjustment, StockLevel

from quality_control.models import (
    QCChecklist, QCChecklistItem,
    InspectionRoute, InspectionRouteRule,
    QuarantineRecord,
    DefectReport,
    ScrapWriteOff,
)


class Command(BaseCommand):
    help = 'Seed Quality Control & Inspection demo data for all tenants'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete existing QC data before seeding')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No active tenants. Run "python manage.py seed" first.'))
            return

        if options['flush']:
            self.stdout.write('Flushing existing quality control data...')
            ScrapWriteOff.objects.all().delete()
            DefectReport.objects.all().delete()  # cascades to photos
            QuarantineRecord.objects.all().delete()
            InspectionRouteRule.objects.all().delete()
            InspectionRoute.objects.all().delete()
            QCChecklistItem.objects.all().delete()
            QCChecklist.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Quality control data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Quality control seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see the module data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))

    def _seed_tenant(self, tenant):
        if QCChecklist.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'[{tenant.name}] Quality Control data already exists — skipping. Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'[{tenant.name}] Seeding…')
        creator = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        warehouses = list(Warehouse.objects.filter(tenant=tenant, is_active=True)[:2])
        if not warehouses:
            self.stdout.write(self.style.WARNING(
                f'  No warehouses for {tenant.name} — skipping; run seed_warehousing first.'
            ))
            return
        wh = warehouses[0]

        zones = list(Zone.objects.filter(tenant=tenant, warehouse=wh))
        qc_zone = next((z for z in zones if z.zone_type == 'quarantine'), None) or (zones[0] if zones else None)
        putaway_zone = next((z for z in zones if z.zone_type == 'storage'), None)
        if qc_zone is None:
            self.stdout.write(self.style.WARNING(
                f'  No zones for {wh.name} — skipping; run seed_warehousing first.'
            ))
            return

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:5])
        if not products:
            self.stdout.write(self.style.WARNING(
                f'  No products for {tenant.name} — skipping; run seed_catalog first.'
            ))
            return

        vendor = Vendor.objects.filter(tenant=tenant).first()
        category = Category.objects.filter(tenant=tenant, is_active=True).first()

        # 1. QC Checklists (3) + items (3-5 each)
        checklist_specs = [
            {
                'name': 'General Receiving QC Checklist',
                'description': 'Default inbound checks for any product.',
                'applies_to': 'all',
                'items': [
                    ('Packaging intact', 'visual', '', False),
                    ('Label legible & correct SKU', 'visual', 'SKU match', True),
                    ('Quantity matches PO', 'measurement', 'PO qty', True),
                    ('No visible damage', 'visual', '', False),
                ],
            },
            {
                'name': f'Product-specific: {products[0].sku}',
                'description': 'Product-level checks for the first catalogued SKU.',
                'applies_to': 'product',
                'product': products[0],
                'items': [
                    ('Serial number scan', 'text', '', True),
                    ('Functional test pass', 'boolean', 'Yes', True),
                    ('Weight within tolerance', 'measurement', '±5%', False),
                ],
            },
            {
                'name': f'Vendor-specific: {vendor.company_name}' if vendor else 'Vendor-specific sample',
                'description': 'Extra checks for items from this vendor.',
                'applies_to': 'vendor' if vendor else 'all',
                'vendor': vendor,
                'items': [
                    ('Vendor seal intact', 'visual', '', True),
                    ('Certificate of analysis present', 'photo', '', False),
                    ('Batch / lot number captured', 'text', '', False),
                    ('Expiry > 6 months', 'measurement', '> 180 days', True),
                    ('Temperature indicator green', 'visual', 'Green', False),
                ],
            },
        ]

        checklists = []
        for spec in checklist_specs:
            obj = QCChecklist(
                tenant=tenant,
                name=spec['name'],
                description=spec['description'],
                applies_to=spec['applies_to'],
                product=spec.get('product'),
                vendor=spec.get('vendor'),
                category=spec.get('category', None),
                is_mandatory=True,
                is_active=True,
                created_by=creator,
            )
            obj.save()
            for i, (name, ctype, expected, critical) in enumerate(spec['items'], start=1):
                QCChecklistItem.objects.create(
                    tenant=tenant, checklist=obj,
                    sequence=i, check_name=name, check_type=ctype,
                    expected_value=expected, is_critical=critical,
                )
            checklists.append(obj)

        # 2. Inspection Routes (2) + rules (2 each)
        route_specs = [
            ('Standard Inbound QC', 100),
            ('Express Bypass (Low-risk)', 50),
        ]
        routes = []
        for name, priority in route_specs:
            route = InspectionRoute(
                tenant=tenant, name=name,
                source_warehouse=wh, qc_zone=qc_zone,
                putaway_zone=putaway_zone, priority=priority, is_active=True,
            )
            route.save()
            routes.append(route)

        # Rule 1 on standard: generic / default checklist
        InspectionRouteRule.objects.create(
            tenant=tenant, route=routes[0], applies_to='all',
            checklist=checklists[0], notes='Default route for all inbound.',
        )
        # Rule 2 on standard: product-specific
        InspectionRouteRule.objects.create(
            tenant=tenant, route=routes[0], applies_to='product',
            product=products[0], checklist=checklists[1],
            notes='Product-specific checklist.',
        )
        # Rules on express: vendor bypass
        if vendor:
            InspectionRouteRule.objects.create(
                tenant=tenant, route=routes[1], applies_to='vendor',
                vendor=vendor, checklist=checklists[2],
                notes='Trusted vendor bypass.',
            )
        if category:
            InspectionRouteRule.objects.create(
                tenant=tenant, route=routes[1], applies_to='category',
                category=category, checklist=checklists[0],
                notes='Category-level bypass.',
            )

        # 3. Quarantine Records (4) across statuses
        quarantine_specs = [
            {'status': 'active', 'reason': 'defect', 'qty': 5, 'product': products[0]},
            {'status': 'under_review', 'reason': 'vendor_issue', 'qty': 12, 'product': products[1] if len(products) > 1 else products[0]},
            {'status': 'released', 'reason': 'damage', 'qty': 3, 'product': products[2] if len(products) > 2 else products[0]},
            {'status': 'scrapped', 'reason': 'contamination', 'qty': 8, 'product': products[3] if len(products) > 3 else products[0]},
        ]
        quarantines = []
        for spec in quarantine_specs:
            qr = QuarantineRecord(
                tenant=tenant,
                product=spec['product'],
                warehouse=wh,
                zone=qc_zone,
                quantity=spec['qty'],
                reason=spec['reason'],
                reason_notes=f"Demo: {spec['reason']} hold for {spec['qty']} units.",
                status=spec['status'],
                held_by=creator,
            )
            if spec['status'] in ('released', 'scrapped'):
                qr.released_by = creator
                qr.released_at = timezone.now()
                qr.release_disposition = 'return_to_stock' if spec['status'] == 'released' else 'scrap'
                qr.release_notes = 'Demo release note.'
            qr.save()
            quarantines.append(qr)

        # 4. Defect Reports (5) across severities + sources
        defect_specs = [
            {'severity': 'minor', 'defect_type': 'visual', 'source': 'receiving', 'status': 'open', 'qty': 2, 'product': products[0]},
            {'severity': 'major', 'defect_type': 'functional', 'source': 'receiving', 'status': 'investigating', 'qty': 1, 'product': products[1] if len(products) > 1 else products[0]},
            {'severity': 'critical', 'defect_type': 'contamination', 'source': 'stocktaking', 'status': 'open', 'qty': 4, 'product': products[2] if len(products) > 2 else products[0], 'quarantine': quarantines[0]},
            {'severity': 'minor', 'defect_type': 'packaging', 'source': 'customer_return', 'status': 'resolved', 'qty': 1, 'product': products[0]},
            {'severity': 'major', 'defect_type': 'labeling', 'source': 'production', 'status': 'scrapped', 'qty': 6, 'product': products[3] if len(products) > 3 else products[0]},
        ]
        defects = []
        for spec in defect_specs:
            dr = DefectReport(
                tenant=tenant,
                product=spec['product'],
                warehouse=wh,
                quantity_affected=spec['qty'],
                defect_type=spec['defect_type'],
                severity=spec['severity'],
                description=(
                    f"Demo {spec['severity']} {spec['defect_type']} defect reported during "
                    f"{spec['source'].replace('_', ' ')}."
                ),
                source=spec['source'],
                quarantine_record=spec.get('quarantine'),
                status=spec['status'],
                reported_by=creator,
            )
            if spec['status'] in ('resolved', 'scrapped'):
                dr.resolved_by = creator
                dr.resolved_at = timezone.now()
                dr.resolution_notes = 'Demo resolution.'
            dr.save()
            defects.append(dr)

        # 5. Scrap Write-Offs (2): one pending, one posted (posted → real StockAdjustment)
        ScrapWriteOff.objects.create(
            tenant=tenant,
            defect_report=defects[4],
            product=defects[4].product,
            warehouse=wh,
            quantity=defects[4].quantity_affected,
            unit_cost=Decimal('12.5000'),
            reason='Labeling error — full batch scrap.',
            approval_status='pending',
            requested_by=creator,
        )

        # Post a second scrap against a stock level with on_hand > 0.
        sl = (
            StockLevel.objects
            .filter(tenant=tenant, warehouse=wh, on_hand__gt=0)
            .select_related('product')
            .first()
        )
        if sl is not None:
            scrap_qty = min(2, sl.on_hand)
            scrap = ScrapWriteOff(
                tenant=tenant,
                product=sl.product,
                warehouse=wh,
                quantity=scrap_qty,
                unit_cost=Decimal('9.9900'),
                reason='Demo posted scrap — damaged during handling.',
                approval_status='approved',
                requested_by=creator,
                approved_by=creator,
                approved_at=timezone.now(),
            )
            scrap.save()
            with transaction.atomic():
                adjustment = StockAdjustment(
                    tenant=tenant,
                    stock_level=sl,
                    adjustment_type='decrease',
                    quantity=scrap_qty,
                    reason='damage',
                    notes=f'Scrap {scrap.scrap_number}: {scrap.reason}',
                    adjusted_by=creator,
                )
                adjustment.save()
                adjustment.apply_adjustment()
                scrap.stock_adjustment = adjustment
                scrap.approval_status = 'posted'
                scrap.posted_by = creator
                scrap.posted_at = timezone.now()
                scrap.save()

        self.stdout.write(self.style.SUCCESS(
            f'  [{tenant.name}] 3 checklists, 2 routes, 4 quarantines, 5 defects, 2 scrap write-offs seeded.'
        ))
