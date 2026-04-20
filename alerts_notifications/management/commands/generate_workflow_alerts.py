"""Scan workflow state for overdue conditions.

Detects:
- PurchaseOrder stuck in `pending_approval` for > --po-stale-hours (default 48)
- Shipment with estimated_delivery_date + grace_days < today, not yet delivered,
  status in pending/dispatched/in_transit
- Import failed: placeholder — no import-log model yet; reserved for a later sprint.

Idempotent per (alert_type, source_pk, YYYY-MM-DD) via dedup_key.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from orders.models import Shipment
from purchase_orders.models import PurchaseOrder

from alerts_notifications.models import Alert


class Command(BaseCommand):
    help = 'Scan PO approvals and shipment deliveries for workflow delays; create alerts.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Tenant slug (default: all active tenants)')
        parser.add_argument('--po-stale-hours', type=int, default=48,
                            help='PO hours-in-pending_approval that counts as stale (default 48).')
        parser.add_argument('--grace-days', type=int, default=0,
                            help='Grace days added to estimated_delivery_date before flagging as delayed.')
        parser.add_argument('--dry-run', action='store_true', help='Print candidates without writing.')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])

        now = timezone.now()
        today = now.date()
        today_str = today.isoformat()
        po_cutoff = now - timedelta(hours=options['po_stale_hours'])
        grace = options['grace_days']
        total_created = total_skipped = 0

        for tenant in tenants:
            self.stdout.write(
                f'[{tenant.name}] Scanning workflow state '
                f'(PO stale > {options["po_stale_hours"]}h, shipment grace {grace}d)…'
            )

            # ── PO approval pending ──
            pos = PurchaseOrder.objects.filter(
                tenant=tenant, status='pending_approval', updated_at__lt=po_cutoff,
            ).select_related('vendor')
            for po in pos:
                dedup_key = f'po_approval_pending:purchase_order:{po.pk}:{today_str}'
                if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                    total_skipped += 1
                    continue
                hours_stale = int((now - po.updated_at).total_seconds() // 3600)
                if options['dry_run']:
                    self.stdout.write(f'  [dry-run] would create po_approval_pending for PO {po.pk}')
                    continue
                Alert.objects.create(
                    tenant=tenant,
                    dedup_key=dedup_key,
                    alert_type='po_approval_pending',
                    severity='warning',
                    title=f'PO pending approval > {options["po_stale_hours"]}h: {po.po_number}',
                    message=(
                        f'Purchase Order {po.po_number} has been in pending-approval status '
                        f'for {hours_stale}h. Vendor: {po.vendor.company_name if po.vendor_id else "—"}.'
                    ),
                    purchase_order=po,
                )
                total_created += 1

            # ── Shipment delayed ──
            shipments = Shipment.objects.filter(
                tenant=tenant,
                status__in=['pending', 'dispatched', 'in_transit'],
                estimated_delivery_date__isnull=False,
                actual_delivery_date__isnull=True,
            ).select_related('carrier')
            for sh in shipments:
                cutoff = sh.estimated_delivery_date + timedelta(days=grace)
                if cutoff >= today:
                    continue
                dedup_key = f'shipment_delayed:shipment:{sh.pk}:{today_str}'
                if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                    total_skipped += 1
                    continue
                days_over = (today - sh.estimated_delivery_date).days
                if options['dry_run']:
                    self.stdout.write(f'  [dry-run] would create shipment_delayed for shipment {sh.pk}')
                    continue
                Alert.objects.create(
                    tenant=tenant,
                    dedup_key=dedup_key,
                    alert_type='shipment_delayed',
                    severity='warning',
                    title=f'Shipment delayed: {sh.shipment_number} ({days_over}d past ETA)',
                    message=(
                        f'Shipment {sh.shipment_number} was expected on '
                        f'{sh.estimated_delivery_date.isoformat()} but has not been delivered '
                        f'({days_over} days past ETA). Status: {sh.get_status_display()}.'
                    ),
                    shipment=sh,
                )
                total_created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Workflow scan complete. Created: {total_created}, skipped (dedup): {total_skipped}.'
        ))
