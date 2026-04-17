from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone


# ──────────────────────────────────────────────
# Sub-module 1: Lot/Batch Generation
# ──────────────────────────────────────────────

class LotBatch(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('quarantine', 'Quarantine'),
        ('expired', 'Expired'),
        ('consumed', 'Consumed'),
        ('recalled', 'Recalled'),
    ]

    VALID_TRANSITIONS = {
        'active': ['quarantine', 'expired', 'consumed', 'recalled'],
        'quarantine': ['active', 'expired', 'recalled'],
        'expired': ['recalled'],
        'consumed': [],
        'recalled': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='lot_batches',
    )
    lot_number = models.CharField(max_length=20, verbose_name='Lot Number')
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='lot_batches',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='lot_batches',
    )
    grn = models.ForeignKey(
        'receiving.GoodsReceiptNote',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lot_batches',
        verbose_name='Goods Receipt Note',
    )
    quantity = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(1)],
        verbose_name='Initial Quantity',
    )
    available_quantity = models.PositiveIntegerField(default=0, verbose_name='Available Quantity')
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supplier_batch_number = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_lots',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'lot_number')
        verbose_name = 'Lot / Batch'
        verbose_name_plural = 'Lots / Batches'

    def __str__(self):
        return f"{self.lot_number} — {self.product.name} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def is_expired(self):
        return self.expiry_date and timezone.now().date() > self.expiry_date and self.status != 'expired'

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None
        delta = (self.expiry_date - timezone.now().date()).days
        return delta

    def save(self, *args, **kwargs):
        """D-07 — retry-on-collision for concurrent LOT-NNNNN generation."""
        if self.lot_number:
            super().save(*args, **kwargs)
            return
        for _ in range(5):
            self.lot_number = self._generate_lot_number()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.lot_number = ''
        super().save(*args, **kwargs)

    def _generate_lot_number(self):
        last = (
            LotBatch.objects.filter(tenant=self.tenant, lot_number__startswith='LOT-')
            .order_by('-id')
            .values_list('lot_number', flat=True)
            .first()
        )
        if last:
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'LOT-{num:05d}'


# ──────────────────────────────────────────────
# Sub-module 2: Serial Number Tracking
# ──────────────────────────────────────────────

class SerialNumber(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('allocated', 'Allocated'),
        ('sold', 'Sold'),
        ('returned', 'Returned'),
        ('damaged', 'Damaged'),
        ('scrapped', 'Scrapped'),
    ]

    VALID_TRANSITIONS = {
        'available': ['allocated', 'sold', 'damaged', 'scrapped'],
        'allocated': ['available', 'sold', 'damaged'],
        'sold': ['returned'],
        'returned': ['available', 'damaged', 'scrapped'],
        'damaged': ['scrapped'],
        'scrapped': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='serial_numbers',
    )
    serial_number = models.CharField(max_length=100, verbose_name='Serial Number')
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='serial_numbers',
    )
    lot = models.ForeignKey(
        LotBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='serial_numbers',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='serial_numbers',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_serials',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'serial_number')

    def __str__(self):
        return f"{self.serial_number} — {self.product.name} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def is_warranty_expired(self):
        return self.warranty_expiry and timezone.now().date() > self.warranty_expiry


# ──────────────────────────────────────────────
# Sub-module 3: Shelf-Life & Expiry Management
# ──────────────────────────────────────────────

class ExpiryAlert(models.Model):
    ALERT_TYPE_CHOICES = [
        ('approaching', 'Approaching Expiry'),
        ('expired', 'Expired'),
        ('recalled', 'Recalled'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='expiry_alerts',
    )
    lot = models.ForeignKey(
        LotBatch,
        on_delete=models.CASCADE,
        related_name='expiry_alerts',
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    alert_date = models.DateField()
    days_before_expiry = models.IntegerField(default=0)
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_expiry_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.lot.lot_number} — {self.get_alert_type_display()} ({self.alert_date})"


# ──────────────────────────────────────────────
# Sub-module 4: Traceability & Genealogy
# ──────────────────────────────────────────────

class TraceabilityLog(models.Model):
    EVENT_TYPE_CHOICES = [
        ('received', 'Received'),
        ('transferred', 'Transferred'),
        ('adjusted', 'Adjusted'),
        ('sold', 'Sold'),
        ('returned', 'Returned'),
        ('recalled', 'Recalled'),
        ('scrapped', 'Scrapped'),
        ('expired', 'Expired'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='traceability_logs',
    )
    log_number = models.CharField(max_length=20, verbose_name='Log Number')
    lot = models.ForeignKey(
        LotBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='traceability_logs',
    )
    serial_number = models.ForeignKey(
        SerialNumber,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='traceability_logs',
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    from_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trace_from',
    )
    to_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trace_to',
    )
    quantity = models.IntegerField(null=True, blank=True)
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_number = models.CharField(max_length=100, blank=True, default='')
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='traceability_actions',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'log_number')

    def __str__(self):
        subject = self.lot.lot_number if self.lot else (self.serial_number.serial_number if self.serial_number else '—')
        return f"{self.log_number} — {self.get_event_type_display()} — {subject}"

    def save(self, *args, **kwargs):
        """D-07 — retry-on-collision for concurrent TRC-NNNNN generation."""
        if self.log_number:
            super().save(*args, **kwargs)
            return
        for _ in range(5):
            self.log_number = self._generate_log_number()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.log_number = ''
        super().save(*args, **kwargs)

    def _generate_log_number(self):
        last = (
            TraceabilityLog.objects.filter(tenant=self.tenant, log_number__startswith='TRC-')
            .order_by('-id')
            .values_list('log_number', flat=True)
            .first()
        )
        if last:
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'TRC-{num:05d}'
