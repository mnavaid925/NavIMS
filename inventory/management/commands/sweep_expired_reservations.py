from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.models import InventoryReservation, StockLevel


class Command(BaseCommand):
    help = (
        'Sweep reservations whose `expires_at` has passed: flip status to '
        '`expired` and release any allocated stock. Intended to run on a cron.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options['dry_run']

        stale = InventoryReservation.objects.filter(
            expires_at__lt=now,
            status__in=['pending', 'confirmed'],
        ).select_related('product', 'warehouse')

        total = stale.count()
        released_allocated = 0

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — would expire {total} reservation(s).'
            ))
            for r in stale:
                self.stdout.write(
                    f'  [{r.tenant.slug}] {r.reservation_number} — '
                    f'{r.get_status_display()} x {r.quantity} '
                    f'({r.product.sku} @ {r.warehouse.code})'
                )
            return

        for r in stale:
            with transaction.atomic():
                was_confirmed = r.status == 'confirmed'
                r.status = 'expired'
                r.save()

                if was_confirmed:
                    try:
                        sl = StockLevel.objects.select_for_update().get(
                            tenant=r.tenant, product=r.product, warehouse=r.warehouse,
                        )
                    except StockLevel.DoesNotExist:
                        continue
                    sl.allocated = max(sl.allocated - r.quantity, 0)
                    sl.save()
                    released_allocated += r.quantity

        self.stdout.write(self.style.SUCCESS(
            f'Expired {total} reservation(s); released {released_allocated} '
            f'unit(s) of allocated stock.'
        ))
