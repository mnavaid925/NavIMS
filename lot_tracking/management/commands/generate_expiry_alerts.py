"""D-09 remediation — generate ExpiryAlert rows based on LotBatch expiry dates.

Idempotent: dedupes by `(tenant, lot, alert_type, alert_date)` so it is safe
to run daily (cron, Celery beat, Windows scheduled task). Creates two kinds
of alerts:

- `approaching` — one per lot whose expiry falls within `--days` (default 30)
  of `today` and whose status is `active`. `alert_date=today`.
- `expired` — one per lot whose expiry is in the past and whose status is
  still `active`. `alert_date=today`.

Idempotency: re-running on the same day is a no-op; running on a later day
creates a fresh `(alert_date=that_day)` row per affected lot.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from lot_tracking.models import ExpiryAlert, LotBatch


class Command(BaseCommand):
    help = 'Generate ExpiryAlert rows for lots approaching or past their expiry date.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='How many days ahead to look for approaching expiries (default: 30).',
        )
        parser.add_argument(
            '--tenant',
            type=str,
            default=None,
            help='Optional tenant slug — run for a single tenant instead of all.',
        )

    def handle(self, *args, **options):
        days = options['days']
        tenant_slug = options.get('tenant')
        today = timezone.now().date()
        horizon = today + timedelta(days=days)

        tenants = Tenant.objects.filter(is_active=True)
        if tenant_slug:
            tenants = tenants.filter(slug=tenant_slug)

        total_created = 0
        for tenant in tenants:
            created = self._process_tenant(tenant, today, horizon, days)
            total_created += created

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {total_created} new alert(s).'
        ))
        return None

    def _process_tenant(self, tenant, today, horizon, days):
        created_count = 0

        # Expired lots (expiry < today, still active).
        expired = LotBatch.objects.filter(
            tenant=tenant, expiry_date__lt=today, status='active',
        )
        for lot in expired:
            days_before = (lot.expiry_date - today).days  # negative
            _, was_created = ExpiryAlert.objects.get_or_create(
                tenant=tenant, lot=lot, alert_type='expired', alert_date=today,
                defaults={'days_before_expiry': days_before},
            )
            if was_created:
                created_count += 1

        # Approaching expiry (today <= expiry <= horizon, active).
        approaching = LotBatch.objects.filter(
            tenant=tenant,
            expiry_date__gte=today,
            expiry_date__lte=horizon,
            status='active',
        )
        for lot in approaching:
            days_before = (lot.expiry_date - today).days
            _, was_created = ExpiryAlert.objects.get_or_create(
                tenant=tenant, lot=lot, alert_type='approaching', alert_date=today,
                defaults={'days_before_expiry': days_before},
            )
            if was_created:
                created_count += 1

        self.stdout.write(
            f'  [{tenant.name}] Created {created_count} alert(s) '
            f'(expired={expired.count()}, approaching<={days}d={approaching.count()}).'
        )
        return created_count
