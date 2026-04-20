"""Scan StockLevel rows and create low-stock / out-of-stock Alert rows.

Idempotent per (tenant, alert_type, stock_level, YYYY-MM-DD) via dedup_key.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from inventory.models import StockLevel

from alerts_notifications.models import Alert


class Command(BaseCommand):
    help = 'Scan StockLevel for low-stock and out-of-stock conditions; create alerts.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Tenant slug (default: all active tenants)')
        parser.add_argument('--dry-run', action='store_true', help='Print candidates without writing.')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])

        today = timezone.now().date().isoformat()
        total_created = total_skipped = 0

        for tenant in tenants:
            self.stdout.write(f'[{tenant.name}] Scanning stock levels…')
            qs = StockLevel.objects.filter(tenant=tenant).select_related('product', 'warehouse')
            for sl in qs:
                available = sl.available
                if available <= 0:
                    alert_type = 'out_of_stock'
                    severity = 'critical'
                    title = f'Out of stock: {sl.product.sku} @ {sl.warehouse.code}'
                    message = (
                        f'Product {sl.product.sku} — "{sl.product.name}" has zero available '
                        f'stock at warehouse {sl.warehouse.code} ({sl.warehouse.name}). '
                        f'On-hand: {sl.on_hand}, allocated: {sl.allocated}.'
                    )
                elif sl.needs_reorder:
                    alert_type = 'low_stock'
                    severity = 'warning'
                    title = f'Low stock: {sl.product.sku} @ {sl.warehouse.code}'
                    message = (
                        f'Product {sl.product.sku} — "{sl.product.name}" is at or below the '
                        f'reorder point at warehouse {sl.warehouse.code}. '
                        f'Available: {available}, reorder point: {sl.reorder_point}, reorder qty: {sl.reorder_quantity}.'
                    )
                else:
                    continue

                dedup_key = f'{alert_type}:stock_level:{sl.pk}:{today}'
                if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                    total_skipped += 1
                    continue

                if options['dry_run']:
                    self.stdout.write(f'  [dry-run] would create {alert_type} for SL {sl.pk}')
                    continue

                Alert.objects.create(
                    tenant=tenant,
                    dedup_key=dedup_key,
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    product=sl.product,
                    warehouse=sl.warehouse,
                    stock_level=sl,
                    threshold_value=sl.reorder_point or 0,
                    current_value=available,
                )
                total_created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Stock scan complete. Created: {total_created}, skipped (dedup): {total_skipped}.'
        ))
