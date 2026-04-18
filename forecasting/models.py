from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction


# ──────────────────────────────────────────────
# Sub-module 1: Demand Forecasting
# ──────────────────────────────────────────────

class DemandForecast(models.Model):
    METHOD_CHOICES = [
        ('moving_avg', 'Moving Average'),
        ('exp_smoothing', 'Exponential Smoothing'),
        ('linear_regression', 'Linear Regression'),
        ('seasonal', 'Seasonal (Moving Avg × Seasonality)'),
    ]

    PERIOD_TYPE_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='demand_forecasts',
    )
    forecast_number = models.CharField(max_length=20, verbose_name='Forecast Number')
    name = models.CharField(max_length=255)
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='demand_forecasts',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='demand_forecasts',
    )
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, default='moving_avg')
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES, default='monthly')
    history_periods = models.PositiveIntegerField(
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(36)],
        help_text='Number of past periods to use for calculation.',
    )
    forecast_periods = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        help_text='Number of future periods to project.',
    )
    seasonality_profile = models.ForeignKey(
        'forecasting.SeasonalityProfile',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='demand_forecasts',
    )
    confidence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('80.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text='Estimated confidence in forecast (0–100).',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, default='')
    generated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_demand_forecasts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'forecast_number')

    def __str__(self):
        return f"{self.forecast_number} — {self.product.name}"

    @property
    def total_forecast_qty(self):
        return sum(
            (line.adjusted_qty or line.forecast_qty or 0)
            for line in self.lines.all()
        )

    @property
    def total_historical_qty(self):
        return sum((line.historical_qty or 0) for line in self.lines.all())

    def save(self, *args, **kwargs):
        if not self.forecast_number:
            # Atomic read-max-then-write to prevent concurrent duplicate numbers (D-03).
            with transaction.atomic():
                self.forecast_number = self._generate_forecast_number()
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def _generate_forecast_number(self):
        last = (
            DemandForecast.objects.select_for_update()
            .filter(tenant=self.tenant, forecast_number__startswith='FC-')
            .order_by('-id')
            .values_list('forecast_number', flat=True)
            .first()
        )
        if last:
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'FC-{num:05d}'


class DemandForecastLine(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='demand_forecast_lines',
    )
    forecast = models.ForeignKey(
        DemandForecast,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    period_index = models.IntegerField(
        help_text='Negative = history, zero/positive = future.',
    )
    period_label = models.CharField(max_length=30, help_text='e.g. "Jan 2026", "Q1 2026", "W12-2026".')
    period_start_date = models.DateField()
    period_end_date = models.DateField()
    historical_qty = models.IntegerField(null=True, blank=True)
    forecast_qty = models.IntegerField(null=True, blank=True)
    adjusted_qty = models.IntegerField(
        null=True, blank=True,
        help_text='Forecast qty after seasonality multiplier.',
    )
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['forecast', 'period_index']

    def __str__(self):
        return f"{self.forecast.forecast_number} — {self.period_label}"


# ──────────────────────────────────────────────
# Sub-module 2: Reorder Point (ROP) Calculation
# ──────────────────────────────────────────────

class ReorderPoint(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='reorder_points',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='reorder_points',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.CASCADE,
        related_name='reorder_points',
    )
    avg_daily_usage = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Average units consumed per day.',
    )
    lead_time_days = models.PositiveIntegerField(default=0, help_text='Vendor lead time in days.')
    safety_stock_qty = models.PositiveIntegerField(default=0)
    rop_qty = models.PositiveIntegerField(
        default=0,
        help_text='ROP = (avg_daily_usage × lead_time_days) + safety_stock_qty.',
    )
    min_qty = models.PositiveIntegerField(default=0)
    max_qty = models.PositiveIntegerField(default=0)
    reorder_qty = models.PositiveIntegerField(
        default=0,
        help_text='Standard replenishment quantity (EOQ or fixed).',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    last_calculated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name', 'warehouse__name']
        unique_together = ('tenant', 'product', 'warehouse')

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name} — ROP {self.rop_qty}"

    def recalc_rop(self):
        self.rop_qty = int(round(float(self.avg_daily_usage) * self.lead_time_days)) + self.safety_stock_qty
        return self.rop_qty


class ReorderAlert(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('ordered', 'Ordered'),
        ('closed', 'Closed'),
    ]

    VALID_TRANSITIONS = {
        'new': ['acknowledged', 'closed'],
        'acknowledged': ['ordered', 'closed'],
        'ordered': ['closed'],
        'closed': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='reorder_alerts',
    )
    alert_number = models.CharField(max_length=20, verbose_name='Alert Number')
    rop = models.ForeignKey(
        ReorderPoint,
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='reorder_alerts',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='reorder_alerts',
    )
    current_qty = models.IntegerField(default=0)
    rop_qty = models.PositiveIntegerField(default=0)
    suggested_order_qty = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='acknowledged_reorder_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-triggered_at']
        unique_together = ('tenant', 'alert_number')

    def __str__(self):
        return f"{self.alert_number} — {self.product.name} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.alert_number:
            with transaction.atomic():
                self.alert_number = self._generate_alert_number()
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def _generate_alert_number(self):
        last = (
            ReorderAlert.objects.select_for_update()
            .filter(tenant=self.tenant, alert_number__startswith='ROA-')
            .order_by('-id')
            .values_list('alert_number', flat=True)
            .first()
        )
        if last:
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'ROA-{num:05d}'


# ──────────────────────────────────────────────
# Sub-module 3: Safety Stock Calculation
# ──────────────────────────────────────────────

class SafetyStock(models.Model):
    METHOD_CHOICES = [
        ('fixed', 'Fixed Quantity'),
        ('statistical', 'Statistical (Service Level)'),
        ('percentage', 'Percentage of Demand'),
    ]

    # Z-scores for common service levels (approx NORMSINV).
    Z_SCORES = {
        Decimal('0.50'): Decimal('0.00'),
        Decimal('0.75'): Decimal('0.67'),
        Decimal('0.85'): Decimal('1.04'),
        Decimal('0.90'): Decimal('1.28'),
        Decimal('0.95'): Decimal('1.645'),
        Decimal('0.975'): Decimal('1.96'),
        Decimal('0.99'): Decimal('2.33'),
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='safety_stocks',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='safety_stocks',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.CASCADE,
        related_name='safety_stocks',
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='statistical')
    service_level = models.DecimalField(
        max_digits=5, decimal_places=3, default=Decimal('0.950'),
        validators=[MinValueValidator(Decimal('0.5')), MaxValueValidator(Decimal('0.999'))],
        help_text='Target service level (e.g. 0.95 = 95%).',
    )
    avg_demand = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Average daily demand.',
    )
    demand_std_dev = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Standard deviation of daily demand.',
    )
    avg_lead_time_days = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    lead_time_std_dev = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    fixed_qty = models.PositiveIntegerField(
        default=0,
        help_text='Used when method = Fixed.',
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text='Percent of avg lead-time demand (used when method = Percentage).',
    )
    safety_stock_qty = models.PositiveIntegerField(
        default=0,
        help_text='Calculated safety stock quantity.',
    )
    notes = models.TextField(blank=True, default='')
    calculated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name', 'warehouse__name']
        unique_together = ('tenant', 'product', 'warehouse')

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name} — SS {self.safety_stock_qty}"

    def recalc(self):
        """Recalculate safety_stock_qty based on current method."""
        if self.method == 'fixed':
            self.safety_stock_qty = int(self.fixed_qty)
        elif self.method == 'percentage':
            lt_demand = float(self.avg_demand) * float(self.avg_lead_time_days)
            self.safety_stock_qty = int(round(lt_demand * float(self.percentage) / 100.0))
        else:
            # Statistical: Z × sqrt((LT × σ_d²) + (μ_d² × σ_LT²))
            z = float(self._lookup_z(self.service_level))
            lt = float(self.avg_lead_time_days)
            sd = float(self.demand_std_dev)
            mu = float(self.avg_demand)
            sl = float(self.lead_time_std_dev)
            variance = (lt * sd * sd) + (mu * mu * sl * sl)
            self.safety_stock_qty = int(round(z * (variance ** 0.5)))
        return self.safety_stock_qty

    @classmethod
    def _lookup_z(cls, service_level):
        closest = min(cls.Z_SCORES.keys(), key=lambda sl: abs(sl - Decimal(service_level)))
        return cls.Z_SCORES[closest]


# ──────────────────────────────────────────────
# Sub-module 4: Seasonality Planning
# ──────────────────────────────────────────────

class SeasonalityProfile(models.Model):
    PERIOD_TYPE_CHOICES = [
        ('month', 'Monthly (12 Periods)'),
        ('quarter', 'Quarterly (4 Periods)'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='seasonality_profiles',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        'catalog.Category',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='seasonality_profiles',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='seasonality_profiles',
    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES, default='month')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_seasonality_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def multiplier_for_date(self, d):
        """Return demand multiplier for a date based on profile's period_type."""
        if self.period_type == 'quarter':
            q = (d.month - 1) // 3 + 1
            period = self.periods.filter(period_number=q).first()
        else:
            period = self.periods.filter(period_number=d.month).first()
        return period.demand_multiplier if period else Decimal('1.00')


class SeasonalityPeriod(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='seasonality_periods',
    )
    profile = models.ForeignKey(
        SeasonalityProfile,
        on_delete=models.CASCADE,
        related_name='periods',
    )
    period_number = models.PositiveSmallIntegerField(help_text='1–12 for month, 1–4 for quarter.')
    period_label = models.CharField(max_length=20)
    demand_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Multiplier applied to forecast qty (1.00 = baseline).',
    )
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['profile', 'period_number']
        unique_together = ('profile', 'period_number')

    def __str__(self):
        return f"{self.profile.name} — {self.period_label}: ×{self.demand_multiplier}"
