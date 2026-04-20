"""Scan StockLevel × LocationSafetyStockRule for overstock conditions.

A StockLevel row is matched to a LocationSafetyStockRule by (tenant, product) via
the Location that is linked to the StockLevel's warehouse. If
`max_stock_qty > 0` and `StockLevel.on_hand > max_stock_qty`, an `overstock`
alert is emitted.

Idempotent per (alert_type, stock_level, YYYY-MM-DD) via dedup_key.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from inventory.models import StockLevel
from multi_location.models import LocationSafetyStockRule

from alerts_notifications.models import Alert


class Command(BaseCommand):
    help = 'Scan LocationSafetyStockRule max_stock_qty against StockLevel on_hand; create overstock alerts.'

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
            self.stdout.write(f'[{tenant.name}] Scanning overstock thresholds…')
            rules = LocationSafetyStockRule.objects.filter(
                tenant=tenant, max_stock_qty__gt=0,
            ).select_related('location', 'product')
            if not rules.exists():
                self.stdout.write('  No LocationSafetyStockRule rows with max_stock_qty > 0 — skipping.')
                continue

            for rule in rules:
                warehouse = rule.location.warehouse if rule.location_id else None
                if warehouse is None:
                    continue
                sl = StockLevel.objects.filter(
                    tenant=tenant, product=rule.product, warehouse=warehouse,
                ).select_related('product', 'warehouse').first()
                if sl is None or sl.on_hand <= rule.max_stock_qty:
                    continue

                dedup_key = f'overstock:stock_level:{sl.pk}:{today}'
                if Alert.objects.filter(tenant=tenant, dedup_key=dedup_key).exists():
                    total_skipped += 1
                    continue

                if options['dry_run']:
                    self.stdout.write(f'  [dry-run] would create overstock for SL {sl.pk}')
                    continue

                Alert.objects.create(
                    tenant=tenant,
                    dedup_key=dedup_key,
                    alert_type='overstock',
                    severity='warning',
                    title=f'Overstock: {sl.product.sku} @ {sl.warehouse.code}',
                    message=(
                        f'Product {sl.product.sku} — "{sl.product.name}" at warehouse '
                        f'{sl.warehouse.code} has on-hand {sl.on_hand}, exceeding the max-stock '
                        f'threshold of {rule.max_stock_qty} (location {rule.location.code}).'
                    ),
                    product=sl.product,
                    warehouse=sl.warehouse,
                    stock_level=sl,
                    threshold_value=rule.max_stock_qty,
                    current_value=sl.on_hand,
                )
                total_created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Overstock scan complete. Created: {total_created}, skipped (dedup): {total_skipped}.'
        ))
