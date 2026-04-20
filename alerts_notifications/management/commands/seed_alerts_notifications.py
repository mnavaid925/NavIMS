"""Idempotent seed command for Module 17 — Alerts & Notifications.

Creates 3 default NotificationRule rows (stock, expiry, workflow) and 6 sample
Alert rows per active tenant. Safe to run multiple times without --flush.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant, User
from catalog.models import Product
from warehousing.models import Warehouse
from lot_tracking.models import LotBatch
from purchase_orders.models import PurchaseOrder
from orders.models import Shipment

from alerts_notifications.models import Alert, NotificationDelivery, NotificationRule


DEFAULT_RULES = [
    {
        'name': 'Stock alerts → Tenant admins',
        'description': 'Email tenant admins on all low-stock and out-of-stock alerts.',
        'alert_type': 'out_of_stock',
        'min_severity': 'warning',
    },
    {
        'name': 'Critical expiry → Tenant admins',
        'description': 'Email tenant admins when lots are expired or expiring within 30 days.',
        'alert_type': 'expired',
        'min_severity': 'warning',
    },
    {
        'name': 'Workflow delays → Tenant admins',
        'description': 'Email tenant admins when POs sit in pending approval or shipments run past ETA.',
        'alert_type': 'po_approval_pending',
        'min_severity': 'warning',
    },
    {
        'name': 'Low stock → Tenant admins',
        'description': 'Email tenant admins when stock falls to the reorder point.',
        'alert_type': 'low_stock',
        'min_severity': 'warning',
    },
    {
        'name': 'Shipment delays → Tenant admins',
        'description': 'Email tenant admins when shipments pass estimated delivery date.',
        'alert_type': 'shipment_delayed',
        'min_severity': 'warning',
    },
    {
        'name': 'Overstock → Tenant admins',
        'description': 'Email tenant admins when inventory exceeds max-stock thresholds.',
        'alert_type': 'overstock',
        'min_severity': 'info',
    },
]


class Command(BaseCommand):
    help = 'Seed Alerts & Notifications demo data for all active tenants.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing alerts/rules/deliveries before seeding.',
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if not tenants.exists():
            self.stdout.write(self.style.WARNING(
                'No active tenants. Run "python manage.py seed" first.'
            ))
            return

        if options['flush']:
            self.stdout.write('Flushing existing alerts & notifications data…')
            NotificationDelivery.objects.all().delete()
            Alert.objects.all().delete()
            NotificationRule.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Alerts & notifications data flushed.'))

        for tenant in tenants:
            self._seed_tenant(tenant)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Alerts & Notifications seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login as a tenant admin to see the module data:')
        self.stdout.write('  admin_acme / demo123')
        self.stdout.write('  admin_global / demo123')
        self.stdout.write('  admin_techware / demo123')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            "Superuser 'admin' has no tenant — data won't appear when logged in as admin."
        ))
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('  python manage.py generate_stock_alerts')
        self.stdout.write('  python manage.py generate_overstock_alerts')
        self.stdout.write('  python manage.py generate_expiry_alerts')
        self.stdout.write('  python manage.py generate_workflow_alerts')
        self.stdout.write('  python manage.py dispatch_notifications')

    def _seed_tenant(self, tenant):
        if Alert.objects.filter(tenant=tenant).exists() or NotificationRule.objects.filter(tenant=tenant).exists():
            self.stdout.write(self.style.WARNING(
                f'[{tenant.name}] Alerts/rules already exist — skipping. Use --flush to re-seed.'
            ))
            return

        self.stdout.write(f'[{tenant.name}] Seeding…')
        admin = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        if admin is None:
            self.stdout.write(self.style.WARNING(
                f'  No tenant admin for {tenant.name} — skipping.'
            ))
            return

        admins = list(User.objects.filter(tenant=tenant, is_tenant_admin=True, is_active=True))

        # NotificationRules
        created_rules = []
        for spec in DEFAULT_RULES:
            rule = NotificationRule(
                tenant=tenant,
                name=spec['name'],
                description=spec['description'],
                alert_type=spec['alert_type'],
                min_severity=spec['min_severity'],
                notify_email=True,
                notify_inbox=True,
                is_active=True,
                created_by=admin,
            )
            rule.save()
            if admins:
                rule.recipient_users.set(admins)
            created_rules.append(rule)
        self.stdout.write(f'  {len(created_rules)} notification rules created.')

        # Sample alerts — pull real FK targets when available
        product = Product.objects.filter(tenant=tenant, is_active=True).first()
        warehouse = Warehouse.objects.filter(tenant=tenant, is_active=True).first()
        lot = LotBatch.objects.filter(tenant=tenant).first()
        po = PurchaseOrder.objects.filter(tenant=tenant).first()
        shipment = Shipment.objects.filter(tenant=tenant).first()

        now = timezone.now()
        samples = [
            {
                'alert_type': 'out_of_stock', 'severity': 'critical', 'status': 'new',
                'title': f'Out of stock: {product.sku if product else "DEMO"} @ {warehouse.code if warehouse else "WH"}',
                'message': 'Demo alert generated by seed_alerts_notifications.',
                'product': product, 'warehouse': warehouse,
                'threshold_value': 10, 'current_value': 0,
            },
            {
                'alert_type': 'low_stock', 'severity': 'warning', 'status': 'new',
                'title': f'Low stock: {product.sku if product else "DEMO"}',
                'message': 'Stock available is at or below the reorder point (demo).',
                'product': product, 'warehouse': warehouse,
                'threshold_value': 50, 'current_value': 42,
            },
            {
                'alert_type': 'overstock', 'severity': 'warning', 'status': 'acknowledged',
                'title': f'Overstock: {product.sku if product else "DEMO"}',
                'message': 'On-hand exceeds max-stock threshold (demo).',
                'product': product, 'warehouse': warehouse,
                'threshold_value': 500, 'current_value': 620,
                'acknowledged_by': admin, 'acknowledged_at': now - timedelta(hours=3),
            },
            {
                'alert_type': 'expiry_approaching', 'severity': 'warning', 'status': 'new',
                'title': f'Expiring soon: {lot.lot_number if lot else "LOT-DEMO"}',
                'message': 'Lot is within the 30-day expiry horizon (demo).',
                'product': product, 'warehouse': warehouse, 'lot_batch': lot,
            },
            {
                'alert_type': 'po_approval_pending', 'severity': 'warning', 'status': 'new',
                'title': f'PO pending approval: {po.po_number if po else "PO-DEMO"}',
                'message': 'PO has been pending approval for more than 48 hours (demo).',
                'purchase_order': po,
            },
            {
                'alert_type': 'shipment_delayed', 'severity': 'warning', 'status': 'resolved',
                'title': f'Shipment delayed: {shipment.shipment_number if shipment else "SHIP-DEMO"}',
                'message': 'Shipment passed estimated delivery date (demo). Resolved after carrier follow-up.',
                'shipment': shipment,
                'acknowledged_by': admin, 'acknowledged_at': now - timedelta(days=1),
                'resolved_at': now - timedelta(hours=2),
            },
        ]

        created_alerts = 0
        for idx, s in enumerate(samples):
            dedup_key = f'seed:{s["alert_type"]}:{idx}:{now.date().isoformat()}'
            if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                continue
            alert = Alert(
                tenant=tenant,
                dedup_key=dedup_key,
                alert_type=s['alert_type'],
                severity=s['severity'],
                status=s['status'],
                title=s['title'],
                message=s.get('message', ''),
                product=s.get('product'),
                warehouse=s.get('warehouse'),
                lot_batch=s.get('lot_batch'),
                purchase_order=s.get('purchase_order'),
                shipment=s.get('shipment'),
                threshold_value=s.get('threshold_value'),
                current_value=s.get('current_value'),
                acknowledged_by=s.get('acknowledged_by'),
                acknowledged_at=s.get('acknowledged_at'),
                resolved_at=s.get('resolved_at'),
            )
            alert.save()
            created_alerts += 1
        self.stdout.write(f'  {created_alerts} sample alerts created.')
