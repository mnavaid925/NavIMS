from django.conf import settings
from django.db import models
from django.utils import timezone


# ──────────────────────────────────────────────
# Sub-module 1: Real-Time Stock Levels
# ──────────────────────────────────────────────

class StockLevel(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_levels',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='stock_levels',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='stock_levels',
    )
    on_hand = models.PositiveIntegerField(default=0)
    allocated = models.PositiveIntegerField(default=0)
    on_order = models.PositiveIntegerField(default=0)
    reorder_point = models.PositiveIntegerField(default=0)
    reorder_quantity = models.PositiveIntegerField(default=0)
    last_counted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name']
        unique_together = ('tenant', 'product', 'warehouse')

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code} — OH:{self.on_hand} AL:{self.allocated} AV:{self.available}"

    @property
    def available(self):
        return max(self.on_hand - self.allocated, 0)

    @property
    def needs_reorder(self):
        return self.reorder_point > 0 and self.available <= self.reorder_point


class StockAdjustment(models.Model):
    ADJUSTMENT_TYPE_CHOICES = [
        ('increase', 'Increase'),
        ('decrease', 'Decrease'),
        ('correction', 'Correction'),
    ]

    REASON_CHOICES = [
        ('count', 'Physical Count'),
        ('damage', 'Damage'),
        ('theft', 'Theft / Loss'),
        ('return', 'Customer Return'),
        ('correction', 'Data Correction'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_adjustments',
    )
    adjustment_number = models.CharField(max_length=20, verbose_name='Adjustment Number')
    stock_level = models.ForeignKey(
        StockLevel,
        on_delete=models.CASCADE,
        related_name='adjustments',
    )
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    notes = models.TextField(blank=True, default='')
    adjusted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_adjustments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'adjustment_number')

    def __str__(self):
        return f"{self.adjustment_number} — {self.get_adjustment_type_display()} {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.adjustment_number:
            self.adjustment_number = self._generate_adjustment_number()
        super().save(*args, **kwargs)

    def _generate_adjustment_number(self):
        last = (
            StockAdjustment.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('adjustment_number', flat=True)
            .first()
        )
        if last and last.startswith('ADJ-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'ADJ-{num:05d}'

    def apply_adjustment(self):
        sl = self.stock_level
        if self.adjustment_type == 'increase':
            sl.on_hand += self.quantity
        elif self.adjustment_type == 'decrease':
            if self.quantity > sl.on_hand:
                # D-01: form guards against this, but the model is the last
                # line of defence. Surface as ValueError rather than silent clamp.
                raise ValueError(
                    f'Cannot decrease {self.quantity}: only {sl.on_hand} on hand.'
                )
            sl.on_hand -= self.quantity
        elif self.adjustment_type == 'correction':
            sl.on_hand = self.quantity
        sl.save()


# ──────────────────────────────────────────────
# Sub-module 2: Stock Status Management
# ──────────────────────────────────────────────

class StockStatus(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('damaged', 'Damaged'),
        ('expired', 'Expired'),
        ('on_hold', 'On Hold'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_statuses',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='stock_statuses',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='stock_statuses',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    quantity = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name', 'status']
        unique_together = ('tenant', 'product', 'warehouse', 'status')
        verbose_name_plural = 'Stock statuses'

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code} — {self.get_status_display()}: {self.quantity}"


class StockStatusTransition(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_status_transitions',
    )
    transition_number = models.CharField(max_length=20, verbose_name='Transition Number')
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='stock_status_transitions',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='stock_status_transitions',
    )
    from_status = models.CharField(max_length=20, choices=StockStatus.STATUS_CHOICES)
    to_status = models.CharField(max_length=20, choices=StockStatus.STATUS_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.TextField(blank=True, default='')
    transitioned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_status_transitions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'transition_number')

    def __str__(self):
        return f"{self.transition_number} — {self.get_from_status_display()} → {self.get_to_status_display()} ({self.quantity})"

    def save(self, *args, **kwargs):
        if not self.transition_number:
            self.transition_number = self._generate_transition_number()
        super().save(*args, **kwargs)

    def _generate_transition_number(self):
        last = (
            StockStatusTransition.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('transition_number', flat=True)
            .first()
        )
        if last and last.startswith('SST-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'SST-{num:05d}'

    def apply_transition(self):
        # D-02: require an existing source bucket with enough quantity — no
        # more phantom-creating source StockStatus rows at 0 qty. The form
        # is the first line of defence; this is the model-level backstop.
        try:
            source = StockStatus.objects.get(
                tenant=self.tenant,
                product=self.product,
                warehouse=self.warehouse,
                status=self.from_status,
            )
        except StockStatus.DoesNotExist:
            raise ValueError(
                f'No {self.from_status} inventory exists for '
                f'{self.product.sku} at {self.warehouse.code}.'
            )
        if self.quantity > source.quantity:
            raise ValueError(
                f'Cannot transition {self.quantity}: only {source.quantity} '
                f'in {self.from_status} at {self.warehouse.code}.'
            )
        source.quantity -= self.quantity
        source.save()

        target, _ = StockStatus.objects.get_or_create(
            tenant=self.tenant,
            product=self.product,
            warehouse=self.warehouse,
            status=self.to_status,
            defaults={'quantity': 0},
        )
        target.quantity += self.quantity
        target.save()


# ──────────────────────────────────────────────
# Sub-module 3: Inventory Valuation
# ──────────────────────────────────────────────

class ValuationConfig(models.Model):
    METHOD_CHOICES = [
        ('fifo', 'FIFO (First In, First Out)'),
        ('lifo', 'LIFO (Last In, First Out)'),
        ('weighted_avg', 'Weighted Average'),
    ]

    tenant = models.OneToOneField(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='valuation_config',
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='weighted_avg')
    auto_recalculate = models.BooleanField(default=True)
    last_calculated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Valuation Configuration'

    def __str__(self):
        return f"{self.tenant.name} — {self.get_method_display()}"


class InventoryValuation(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='inventory_valuations',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='inventory_valuations',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_valuations',
    )
    valuation_date = models.DateField()
    method = models.CharField(max_length=20, choices=ValuationConfig.METHOD_CHOICES)
    total_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-valuation_date', 'product__name']

    def __str__(self):
        return f"{self.product.sku} — {self.valuation_date} — ${self.total_value}"


class ValuationEntry(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='valuation_entries',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='valuation_entries',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='valuation_entries',
    )
    entry_date = models.DateField()
    quantity = models.PositiveIntegerField(default=0)
    remaining_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_number = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['entry_date', 'id']
        verbose_name_plural = 'Valuation entries'

    def __str__(self):
        return f"{self.product.sku} — {self.entry_date} — {self.remaining_quantity} @ ${self.unit_cost}"

    @property
    def total_value(self):
        return self.remaining_quantity * self.unit_cost


# ──────────────────────────────────────────────
# Sub-module 4: Inventory Reservations
# ──────────────────────────────────────────────

class InventoryReservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('released', 'Released'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['confirmed', 'released', 'cancelled'],
        'confirmed': ['released', 'expired', 'cancelled'],
        'released': [],
        'expired': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='inventory_reservations',
    )
    reservation_number = models.CharField(max_length=20, verbose_name='Reservation Number')
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='inventory_reservations',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='inventory_reservations',
    )
    quantity = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_number = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_reservations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'reservation_number')

    def __str__(self):
        return f"{self.reservation_number} — {self.product.sku} x {self.quantity} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def is_expired(self):
        return (
            self.expires_at
            and timezone.now() > self.expires_at
            and self.status not in ('released', 'cancelled', 'expired')
        )

    def save(self, *args, **kwargs):
        if not self.reservation_number:
            self.reservation_number = self._generate_reservation_number()
        super().save(*args, **kwargs)

    def _generate_reservation_number(self):
        last = (
            InventoryReservation.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('reservation_number', flat=True)
            .first()
        )
        if last and last.startswith('RES-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'RES-{num:05d}'
