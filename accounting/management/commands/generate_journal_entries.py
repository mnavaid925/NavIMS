"""Scan unposted `inventory.StockAdjustment` and `quality_control.ScrapWriteOff`
rows and create draft `JournalEntry` records for each.

Idempotent: existing entries with matching (source_type, source_id) are skipped.
Entries are created in `draft` status for manual review/post.
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import Tenant
from accounting.models import (
    ChartOfAccount, FiscalPeriod, JournalEntry, JournalLine,
)


def _open_period(tenant, target_date):
    qs = FiscalPeriod.objects.filter(tenant=tenant, status='open')
    exact = qs.filter(start_date__lte=target_date, end_date__gte=target_date).first()
    return exact or qs.order_by('-start_date').first()


class Command(BaseCommand):
    help = 'Scan inventory adjustments and scrap write-offs; create draft journal entries. Idempotent.'

    def handle(self, *args, **options):
        total_created = 0
        total_skipped = 0
        for tenant in Tenant.objects.filter(is_active=True):
            period = _open_period(tenant, date.today())
            if period is None:
                self.stdout.write(self.style.WARNING(
                    f'[{tenant.slug}] no open fiscal period; run seed_accounting first.'))
                continue

            coa = {c.code: c for c in ChartOfAccount.objects.filter(tenant=tenant)}
            if '1200' not in coa or '5200' not in coa or '5100' not in coa:
                self.stdout.write(self.style.WARNING(
                    f'[{tenant.slug}] missing required GL accounts; run seed_accounting first.'))
                continue

            created = 0
            skipped = 0

            # Stock adjustments
            try:
                from inventory.models import StockAdjustment
                adjustments = StockAdjustment.objects.select_related(
                    'stock_level__product'
                ).filter(stock_level__product__tenant=tenant)
                for adj in adjustments:
                    if JournalEntry.objects.filter(
                        tenant=tenant, source_type='stock_adjustment',
                        source_id=str(adj.pk),
                        deleted_at__isnull=True,
                    ).exists():
                        skipped += 1
                        continue
                    entry = JournalEntry.objects.create(
                        tenant=tenant,
                        entry_date=adj.created_at.date() if adj.created_at else date.today(),
                        fiscal_period=period,
                        source_type='stock_adjustment',
                        source_reference=adj.adjustment_number,
                        source_id=str(adj.pk),
                        description=f'Auto-generated from {adj.adjustment_number} ({adj.get_reason_display()})',
                    )
                    amount = Decimal('10.00')  # Placeholder; refine in dedicated valuation pass
                    if adj.adjustment_type == 'increase':
                        JournalLine.objects.create(entry=entry, gl_account=coa['1200'],
                                                   debit_amount=amount, description='Inventory in', line_order=1)
                        JournalLine.objects.create(entry=entry, gl_account=coa['5200'],
                                                   credit_amount=amount, description='Adjustment offset', line_order=2)
                    else:
                        JournalLine.objects.create(entry=entry, gl_account=coa['5200'],
                                                   debit_amount=amount, description='Adjustment offset', line_order=1)
                        JournalLine.objects.create(entry=entry, gl_account=coa['1200'],
                                                   credit_amount=amount, description='Inventory out', line_order=2)
                    entry.recompute_totals()
                    entry.save(update_fields=['total_debit', 'total_credit'])
                    created += 1
            except ImportError:  # pragma: no cover
                pass

            # Scrap write-offs
            try:
                from quality_control.models import ScrapWriteOff
                scraps = ScrapWriteOff.objects.filter(tenant=tenant, approval_status='posted')
                for scrap in scraps:
                    if JournalEntry.objects.filter(
                        tenant=tenant, source_type='scrap_writeoff',
                        source_id=str(scrap.pk),
                        deleted_at__isnull=True,
                    ).exists():
                        skipped += 1
                        continue
                    entry = JournalEntry.objects.create(
                        tenant=tenant,
                        entry_date=scrap.posted_at.date() if scrap.posted_at else date.today(),
                        fiscal_period=period,
                        source_type='scrap_writeoff',
                        source_reference=scrap.scrap_number,
                        source_id=str(scrap.pk),
                        description=f'Auto-generated from scrap {scrap.scrap_number}',
                    )
                    amount = scrap.total_value or Decimal('0.00')
                    JournalLine.objects.create(entry=entry, gl_account=coa['5100'],
                                               debit_amount=amount, description='Scrap expense', line_order=1)
                    JournalLine.objects.create(entry=entry, gl_account=coa['1200'],
                                               credit_amount=amount, description='Inventory out', line_order=2)
                    entry.recompute_totals()
                    entry.save(update_fields=['total_debit', 'total_credit'])
                    created += 1
            except ImportError:  # pragma: no cover
                pass

            total_created += created
            total_skipped += skipped
            self.stdout.write(f'[{tenant.slug}] created={created}, skipped={skipped}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {total_created} draft entr(y/ies), skipped {total_skipped}.'))
