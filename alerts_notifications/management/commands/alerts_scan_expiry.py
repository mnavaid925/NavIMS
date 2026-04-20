"""Scan LotBatch for approaching or past expiry dates.

Distinct from `lot_tracking.generate_expiry_alerts` (which writes into
`lot_tracking.ExpiryAlert`). This one writes into the canonical
`alerts_notifications.Alert` table so all module-17 inbox / dispatcher code
treats expiry the same way as stock and workflow alerts.

Idempotent per (alert_type, lot_batch, YYYY-MM-DD) via dedup_key.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from lot_tracking.models import LotBatch

from alerts_notifications.models import Alert


class Command(BaseCommand):
    help = 'Scan active LotBatch rows for expired or near-expiry dates; create alerts.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Tenant slug (default: all active tenants)')
        parser.add_argument('--days-ahead', type=int, default=30,
                            help='Days-ahead horizon for approaching-expiry (default 30).')
        parser.add_argument('--dry-run', action='store_true', help='Print candidates without writing.')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])

        today = timezone.now().date()
        horizon = today + timedelta(days=options['days_ahead'])
        today_str = today.isoformat()
        total_created = total_skipped = 0

        for tenant in tenants:
            self.stdout.write(
                f'[{tenant.name}] Scanning lots (horizon {options["days_ahead"]} days)…'
            )
            lots = LotBatch.objects.filter(
                tenant=tenant, status='active', expiry_date__isnull=False,
            ).select_related('product', 'warehouse')

            for lot in lots:
                if lot.expiry_date < today:
                    alert_type = 'expired'
                    severity = 'critical'
                    days = (today - lot.expiry_date).days
                    title = f'Expired lot: {lot.lot_number} ({days}d past)'
                    message = (
                        f'Lot {lot.lot_number} for product {lot.product.sku} — '
                        f'"{lot.product.name}" at warehouse {lot.warehouse.code} expired '
                        f'on {lot.expiry_date.isoformat()} ({days} days ago). '
                        f'Available qty: {lot.available_quantity}.'
                    )
                elif lot.expiry_date <= horizon:
                    alert_type = 'expiry_approaching'
                    severity = 'warning'
                    days = (lot.expiry_date - today).days
                    title = f'Expiring soon: {lot.lot_number} ({days}d left)'
                    message = (
                        f'Lot {lot.lot_number} for product {lot.product.sku} — '
                        f'"{lot.product.name}" at warehouse {lot.warehouse.code} will expire '
                        f'on {lot.expiry_date.isoformat()} ({days} days from today). '
                        f'Available qty: {lot.available_quantity}.'
                    )
                else:
                    continue

                dedup_key = f'{alert_type}:lot_batch:{lot.pk}:{today_str}'
                if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                    total_skipped += 1
                    continue

                if options['dry_run']:
                    self.stdout.write(f'  [dry-run] would create {alert_type} for lot {lot.pk}')
                    continue

                Alert.objects.create(
                    tenant=tenant,
                    dedup_key=dedup_key,
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    product=lot.product,
                    warehouse=lot.warehouse,
                    lot_batch=lot,
                )
                total_created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Expiry scan complete. Created: {total_created}, skipped (dedup): {total_skipped}.'
        ))
