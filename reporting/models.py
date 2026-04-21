from django.conf import settings
from django.db import IntegrityError, models, transaction


REPORT_TYPE_CHOICES = [
    # Section 1: Inventory & Stock
    ('valuation', 'Inventory Valuation'),
    ('aging', 'Aging Analysis'),
    ('abc', 'ABC Analysis'),
    ('turnover', 'Stock Turnover Ratio'),
    ('reservations', 'Reservations Report'),
    ('multi_location', 'Multi-Location Stock Roll-up'),
    # Section 2: Procurement
    ('po_summary', 'Purchase Order Summary'),
    ('vendor_performance', 'Vendor Performance'),
    ('three_way_match', 'Three-Way Match Variance'),
    ('receiving_grn', 'Receiving / GRN'),
    # Section 3: Warehouse Ops
    ('stock_transfers', 'Stock Transfers'),
    ('stocktake_variance', 'Stocktaking Variance'),
    ('quality_control', 'Quality Control'),
    ('scrap_writeoff', 'Scrap Write-Off'),
    # Section 4: Sales & Fulfillment
    ('so_summary', 'Sales Order Summary'),
    ('fulfillment', 'Fulfillment (Pick/Pack/Ship)'),
    ('shipment_carrier', 'Shipment / Carrier'),
    ('returns_rma', 'Returns (RMA)'),
    # Section 5: Tracking & Ops
    ('lot_expiry', 'Lot / Serial / Expiry'),
    ('forecast_vs_actual', 'Forecast vs Actual'),
    ('alerts_log', 'Alerts & Notifications Log'),
]


_NUMBER_RETRY_ATTEMPTS = 5


def _save_with_number_retry(instance, number_field, save_super):
    user_supplied_number = bool(getattr(instance, number_field))
    last_error = None
    for _ in range(_NUMBER_RETRY_ATTEMPTS):
        try:
            with transaction.atomic():
                save_super()
            return
        except IntegrityError as exc:
            last_error = exc
            if user_supplied_number or instance.pk is not None:
                raise
            setattr(instance, number_field, '')
    raise last_error  # type: ignore[misc]


class ReportSnapshot(models.Model):
    """A saved, immutable snapshot of a computed report.

    Single table with a `report_type` discriminator — the 21 report variants
    share the same shape (metadata + parameters + computed summary + data),
    so concrete per-type models would be duplicate boilerplate.

    `parameters`, `summary`, and `data` are JSONField; services
    (`reporting/services.py`) produce these blobs and views render them.
    """

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='report_snapshots',
    )
    report_number = models.CharField(max_length=20, verbose_name='Report #')
    report_type = models.CharField(max_length=32, choices=REPORT_TYPE_CHOICES)
    title = models.CharField(max_length=200)

    # Optional time-scoping params (one snapshot uses either as_of_date OR period_*)
    as_of_date = models.DateField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Optional entity-scoping filters
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    category = models.ForeignKey(
        'catalog.Category', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    # Full parameter set sent to the compute service (for re-generation traceability)
    parameters = models.JSONField(default=dict, blank=True)
    # KPI cards rendered above the data table
    summary = models.JSONField(default=dict, blank=True)
    # Row data rendered as table / CSV / PDF; may include `chart` sub-key for Chart.js config
    data = models.JSONField(default=dict, blank=True)

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reports_generated',
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-generated_at', '-id']
        unique_together = ('tenant', 'report_number')
        indexes = [
            models.Index(fields=['tenant', 'report_type']),
            models.Index(fields=['tenant', 'generated_at']),
        ]

    def __str__(self):
        return f'{self.report_number} — {self.title}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.report_number:
                self.report_number = self._generate_number()
            super(ReportSnapshot, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'report_number', _do)

    def _generate_number(self):
        last = (
            ReportSnapshot.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('report_number', flat=True).first()
        )
        if last and last.startswith('RPT-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'RPT-{num:05d}'
