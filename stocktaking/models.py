from decimal import Decimal

from django.conf import settings
from django.db import models


# ──────────────────────────────────────────────
# Sub-module 1: Full Physical Inventory — Warehouse Freeze
# ──────────────────────────────────────────────

class StocktakeFreeze(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('released', 'Released'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stocktake_freezes',
    )
    freeze_number = models.CharField(max_length=20, verbose_name='Freeze Number')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='stocktake_freezes',
    )
    zones = models.ManyToManyField(
        'warehousing.Zone',
        related_name='stocktake_freezes',
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    reason = models.CharField(max_length=255, blank=True, default='')
    frozen_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stocktake_freezes',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'freeze_number')

    def __str__(self):
        return f"{self.freeze_number} — {self.warehouse.name}"

    def save(self, *args, **kwargs):
        if not self.freeze_number:
            self.freeze_number = self._generate_freeze_number()
        super().save(*args, **kwargs)

    def _generate_freeze_number(self):
        last = (
            StocktakeFreeze.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('freeze_number', flat=True)
            .first()
        )
        if last and last.startswith('FRZ-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'FRZ-{num:05d}'


# ──────────────────────────────────────────────
# Sub-module 2: Cycle Count Scheduling
# ──────────────────────────────────────────────

class CycleCountSchedule(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    ABC_CLASS_CHOICES = [
        ('a', 'Class A (High Value)'),
        ('b', 'Class B (Medium Value)'),
        ('c', 'Class C (Low Value)'),
        ('all', 'All Classes'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='cycle_count_schedules',
    )
    name = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='weekly')
    abc_class = models.CharField(max_length=10, choices=ABC_CLASS_CHOICES, default='all')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='cycle_count_schedules',
    )
    zones = models.ManyToManyField(
        'warehousing.Zone',
        related_name='cycle_count_schedules',
        blank=True,
    )
    next_run_date = models.DateField(null=True, blank=True)
    last_run_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_cycle_count_schedules',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"


# ──────────────────────────────────────────────
# Sub-module 1+2+3: Stock Count (Full or Cycle or Spot)
# ──────────────────────────────────────────────

class StockCount(models.Model):
    TYPE_CHOICES = [
        ('full', 'Full Physical Inventory'),
        ('cycle', 'Cycle Count'),
        ('spot', 'Spot Check'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('counted', 'Counted'),
        ('reviewed', 'Reviewed'),
        ('adjusted', 'Adjusted'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['in_progress', 'cancelled'],
        'in_progress': ['counted', 'cancelled'],
        'counted': ['reviewed', 'in_progress', 'cancelled'],
        'reviewed': ['adjusted', 'counted', 'cancelled'],
        'adjusted': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_counts',
    )
    count_number = models.CharField(max_length=20, verbose_name='Count Number')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='cycle')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='stock_counts',
    )
    zone = models.ForeignKey(
        'warehousing.Zone',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_counts',
    )
    schedule = models.ForeignKey(
        CycleCountSchedule,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_counts',
    )
    freeze = models.ForeignKey(
        StocktakeFreeze,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_counts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    blind_count = models.BooleanField(
        default=False,
        help_text='Hide expected system quantity from counters to prevent bias.',
    )
    scheduled_date = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    adjusted_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_stock_counts',
    )
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='counted_stock_counts',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_stock_counts',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_stock_counts',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'count_number')

    def __str__(self):
        return f"{self.count_number} — {self.warehouse.name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def total_items(self):
        return self.items.count()

    @property
    def counted_items(self):
        return self.items.filter(counted_qty__isnull=False).count()

    @property
    def variance_items(self):
        return self.items.exclude(counted_qty__isnull=True).exclude(counted_qty=models.F('system_qty')).count()

    @property
    def total_variance_value(self):
        total = Decimal('0.00')
        for item in self.items.exclude(counted_qty__isnull=True):
            total += item.variance_value
        return total

    def save(self, *args, **kwargs):
        if not self.count_number:
            self.count_number = self._generate_count_number()
        super().save(*args, **kwargs)

    def _generate_count_number(self):
        last = (
            StockCount.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('count_number', flat=True)
            .first()
        )
        if last and last.startswith('CNT-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'CNT-{num:05d}'


class StockCountItem(models.Model):
    REASON_CODE_CHOICES = [
        ('', '— Select —'),
        ('miscount', 'Miscount'),
        ('damage', 'Damage'),
        ('theft', 'Theft / Shrinkage'),
        ('misplaced', 'Misplaced / Wrong Bin'),
        ('data_error', 'Data Entry Error'),
        ('receiving_error', 'Receiving Error'),
        ('shipping_error', 'Shipping Error'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_count_items',
    )
    count = models.ForeignKey(
        StockCount,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='stock_count_items',
    )
    bin_location = models.ForeignKey(
        'warehousing.Bin',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_count_items',
    )
    lot = models.ForeignKey(
        'lot_tracking.LotBatch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_count_items',
    )
    system_qty = models.IntegerField(default=0, help_text='Expected quantity from system at snapshot time.')
    counted_qty = models.IntegerField(null=True, blank=True, help_text='Actual counted quantity.')
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason_code = models.CharField(max_length=30, choices=REASON_CODE_CHOICES, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    counted_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='counted_stock_count_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} — sys:{self.system_qty} cnt:{self.counted_qty if self.counted_qty is not None else '—'}"

    @property
    def variance(self):
        if self.counted_qty is None:
            return None
        return self.counted_qty - self.system_qty

    @property
    def variance_value(self):
        if self.counted_qty is None:
            return Decimal('0.00')
        return Decimal(self.variance) * self.unit_cost

    @property
    def has_variance(self):
        return self.counted_qty is not None and self.counted_qty != self.system_qty


# ──────────────────────────────────────────────
# Sub-module 4: Variance Analysis & Adjustments
# ──────────────────────────────────────────────

class StockVarianceAdjustment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('posted', 'Posted'),
        ('rejected', 'Rejected'),
    ]

    REASON_CODE_CHOICES = [
        ('miscount', 'Miscount'),
        ('damage', 'Damage / Loss'),
        ('theft', 'Theft / Shrinkage'),
        ('data_error', 'Data Entry Error'),
        ('receiving_error', 'Receiving Error'),
        ('shipping_error', 'Shipping Error'),
        ('other', 'Other'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['approved', 'rejected'],
        'approved': ['posted', 'rejected'],
        'posted': [],
        'rejected': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='variance_adjustments',
    )
    adjustment_number = models.CharField(max_length=20, verbose_name='Adjustment Number')
    count = models.ForeignKey(
        StockCount,
        on_delete=models.CASCADE,
        related_name='variance_adjustments',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reason_code = models.CharField(max_length=30, choices=REASON_CODE_CHOICES, default='miscount')
    total_variance_qty = models.IntegerField(default=0)
    total_variance_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_variance_adjustments',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='posted_variance_adjustments',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_variance_adjustments',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'adjustment_number')

    def __str__(self):
        return f"{self.adjustment_number} — {self.count.count_number}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.adjustment_number:
            self.adjustment_number = self._generate_adjustment_number()
        super().save(*args, **kwargs)

    def _generate_adjustment_number(self):
        last = (
            StockVarianceAdjustment.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('adjustment_number', flat=True)
            .first()
        )
        if last and last.startswith('VADJ-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'VADJ-{num:05d}'
