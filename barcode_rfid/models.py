import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction

from core.state_machine import StateMachineMixin


# Auto-numbering is read-then-increment and therefore TOCTOU-racy.
# Lesson #22: DB `unique_together (tenant, <number>)` is the ultimate guard;
# this helper retries the save on IntegrityError so a race surfaces as a retry.
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


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 1: Label Generation
# ═══════════════════════════════════════════════════════════════════════════

class LabelTemplate(models.Model):
    LABEL_TYPE_CHOICES = [
        ('barcode', 'Barcode Only'),
        ('qr', 'QR Code Only'),
        ('mixed', 'Barcode + QR'),
    ]

    SYMBOLOGY_CHOICES = [
        ('code128', 'CODE128'),
        ('code39', 'CODE39'),
        ('ean13', 'EAN-13'),
        ('ean8', 'EAN-8'),
        ('upca', 'UPC-A'),
        ('qr', 'QR Code'),
        ('datamatrix', 'Data Matrix'),
        ('pdf417', 'PDF417'),
    ]

    PAPER_SIZE_CHOICES = [
        ('a4', 'A4'),
        ('letter', 'Letter'),
        ('label_small', 'Label 40x20mm'),
        ('label_medium', 'Label 60x40mm'),
        ('label_large', 'Label 100x60mm'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='label_templates',
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, verbose_name='Template Code')
    label_type = models.CharField(max_length=20, choices=LABEL_TYPE_CHOICES, default='barcode')
    symbology = models.CharField(max_length=20, choices=SYMBOLOGY_CHOICES, default='code128')
    paper_size = models.CharField(max_length=20, choices=PAPER_SIZE_CHOICES, default='label_medium')
    width_mm = models.PositiveIntegerField(default=60)
    height_mm = models.PositiveIntegerField(default=40)
    includes_name = models.BooleanField(default=True)
    includes_price = models.BooleanField(default=False)
    includes_sku = models.BooleanField(default=True)
    includes_date = models.BooleanField(default=False)
    copies_per_label = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_label_templates',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} — {self.name}"


class LabelPrintJob(StateMachineMixin, models.Model):
    TARGET_TYPE_CHOICES = [
        ('product', 'Product'),
        ('bin', 'Bin'),
        ('pallet', 'Pallet'),
        ('lot', 'Lot / Batch'),
        ('serial', 'Serial Number'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('printing', 'Printing'),
        ('printed', 'Printed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['queued', 'cancelled'],
        'queued': ['printing', 'cancelled'],
        'printing': ['printed', 'failed'],
        'printed': [],
        'failed': ['queued', 'cancelled'],
        'cancelled': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='label_print_jobs',
    )
    job_number = models.CharField(max_length=20)
    template = models.ForeignKey(
        LabelTemplate, on_delete=models.PROTECT, related_name='print_jobs',
    )
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_display = models.CharField(max_length=255, default='')
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='printed_label_jobs',
    )
    printed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_label_jobs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'job_number')

    def __str__(self):
        return f"{self.job_number} — {self.template.name}"

    def save(self, *args, **kwargs):
        def _do():
            if not self.job_number:
                self.job_number = self._generate_job_number()
            super(LabelPrintJob, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'job_number', _do)

    def _generate_job_number(self):
        last = (
            LabelPrintJob.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('job_number', flat=True).first()
        )
        if last and last.startswith('LPJ-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'LPJ-{num:05d}'


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 2: Mobile/Handheld Scanner Integration
# ═══════════════════════════════════════════════════════════════════════════

class ScannerDevice(models.Model):
    DEVICE_TYPE_CHOICES = [
        ('handheld', 'Handheld Scanner'),
        ('fixed', 'Fixed Scanner'),
        ('mobile_phone', 'Mobile Phone'),
        ('tablet', 'Tablet'),
        ('wearable', 'Wearable'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Under Maintenance'),
        ('lost', 'Lost / Stolen'),
        ('retired', 'Retired'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='scanner_devices',
    )
    device_code = models.CharField(max_length=40, verbose_name='Device Code')
    name = models.CharField(max_length=120)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default='handheld')
    manufacturer = models.CharField(max_length=80, blank=True, default='')
    model_number = models.CharField(max_length=80, blank=True, default='')
    os_version = models.CharField(max_length=40, blank=True, default='')
    firmware_version = models.CharField(max_length=40, blank=True, default='')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_scanner_devices',
    )
    assigned_warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scanner_devices',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_seen_at = models.DateTimeField(null=True, blank=True)
    battery_level_percent = models.PositiveIntegerField(null=True, blank=True)
    api_token = models.CharField(max_length=64, blank=True, default='', db_index=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'device_code')

    def __str__(self):
        return f"{self.device_code} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.api_token:
            self.api_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def rotate_token(self):
        self.api_token = secrets.token_urlsafe(32)
        self.save(update_fields=['api_token', 'updated_at'])


class ScanEvent(models.Model):
    SCAN_TYPE_CHOICES = [
        ('receive', 'Receive'),
        ('putaway', 'Putaway'),
        ('pick', 'Pick'),
        ('pack', 'Pack'),
        ('ship', 'Ship'),
        ('count', 'Cycle Count'),
        ('transfer', 'Transfer'),
        ('lookup', 'Lookup'),
        ('other', 'Other'),
    ]

    RESOLVED_TYPE_CHOICES = [
        ('product', 'Product'),
        ('lot', 'Lot / Batch'),
        ('serial', 'Serial Number'),
        ('bin', 'Bin'),
        ('rfid', 'RFID Tag'),
        ('none', 'Unmatched'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('unmatched', 'Unmatched'),
        ('error', 'Error'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='scan_events',
    )
    device = models.ForeignKey(
        ScannerDevice, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scan_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scan_events',
    )
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, default='lookup')
    barcode_value = models.CharField(max_length=255)
    symbology = models.CharField(max_length=20, blank=True, default='')
    resolved_object_type = models.CharField(
        max_length=20, choices=RESOLVED_TYPE_CHOICES, default='none',
    )
    resolved_object_id = models.PositiveIntegerField(null=True, blank=True)
    resolved_display = models.CharField(max_length=255, blank=True, default='')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scan_events',
    )
    scanned_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    error_message = models.CharField(max_length=255, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-scanned_at']
        indexes = [
            models.Index(fields=['tenant', 'barcode_value']),
            models.Index(fields=['tenant', 'scan_type']),
        ]

    def __str__(self):
        return f"{self.barcode_value} @ {self.scanned_at:%Y-%m-%d %H:%M}"


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 3: RFID Tag Management
# ═══════════════════════════════════════════════════════════════════════════

class RFIDTag(StateMachineMixin, models.Model):
    TAG_TYPE_CHOICES = [
        ('passive', 'Passive'),
        ('active', 'Active'),
        ('semi_active', 'Semi-Active'),
    ]

    FREQUENCY_BAND_CHOICES = [
        ('lf', 'Low Frequency (125 kHz)'),
        ('hf', 'High Frequency (13.56 MHz)'),
        ('uhf', 'Ultra-High Frequency (860-960 MHz)'),
        ('microwave', 'Microwave (2.45 GHz)'),
    ]

    LINKED_TYPE_CHOICES = [
        ('product', 'Product'),
        ('lot', 'Lot / Batch'),
        ('serial', 'Serial Number'),
        ('bin', 'Bin'),
        ('pallet', 'Pallet'),
        ('none', 'Unlinked'),
    ]

    STATUS_CHOICES = [
        ('unassigned', 'Unassigned'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('lost', 'Lost'),
        ('damaged', 'Damaged'),
        ('retired', 'Retired'),
    ]

    VALID_TRANSITIONS = {
        'unassigned': ['active', 'retired'],
        'active': ['inactive', 'lost', 'damaged', 'retired'],
        'inactive': ['active', 'retired'],
        'lost': ['active', 'retired'],
        'damaged': ['retired'],
        'retired': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='rfid_tags',
    )
    epc_code = models.CharField(max_length=64, verbose_name='EPC Code')
    tag_type = models.CharField(max_length=20, choices=TAG_TYPE_CHOICES, default='passive')
    frequency_band = models.CharField(max_length=20, choices=FREQUENCY_BAND_CHOICES, default='uhf')
    linked_object_type = models.CharField(
        max_length=20, choices=LINKED_TYPE_CHOICES, default='none',
    )
    linked_object_id = models.PositiveIntegerField(null=True, blank=True)
    linked_display = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unassigned')
    first_read_at = models.DateTimeField(null=True, blank=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    read_count = models.PositiveBigIntegerField(default=0)
    battery_voltage = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text='Active tags only',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'epc_code')

    def __str__(self):
        return self.epc_code


class RFIDReader(models.Model):
    READER_TYPE_CHOICES = [
        ('fixed_gate', 'Fixed Gate'),
        ('handheld', 'Handheld'),
        ('integrated', 'Integrated'),
        ('vehicle_mount', 'Vehicle-Mounted'),
    ]

    FREQUENCY_BAND_CHOICES = RFIDTag.FREQUENCY_BAND_CHOICES

    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='rfid_readers',
    )
    reader_code = models.CharField(max_length=40, verbose_name='Reader Code')
    name = models.CharField(max_length=120)
    reader_type = models.CharField(max_length=20, choices=READER_TYPE_CHOICES, default='fixed_gate')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT, related_name='rfid_readers',
    )
    zone = models.ForeignKey(
        'warehousing.Zone', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rfid_readers',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    antenna_count = models.PositiveIntegerField(default=1)
    frequency_band = models.CharField(max_length=20, choices=FREQUENCY_BAND_CHOICES, default='uhf')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='online')
    last_seen_at = models.DateTimeField(null=True, blank=True)
    firmware_version = models.CharField(max_length=40, blank=True, default='')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'reader_code')

    def __str__(self):
        return f"{self.reader_code} — {self.name}"


class RFIDReadEvent(models.Model):
    DIRECTION_CHOICES = [
        ('in', 'Inbound'),
        ('out', 'Outbound'),
        ('unknown', 'Unknown'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='rfid_read_events',
    )
    tag = models.ForeignKey(
        RFIDTag, on_delete=models.CASCADE, related_name='read_events',
    )
    reader = models.ForeignKey(
        RFIDReader, on_delete=models.CASCADE, related_name='read_events',
    )
    read_at = models.DateTimeField(auto_now_add=True)
    signal_strength_dbm = models.IntegerField(null=True, blank=True)
    read_count_at_event = models.PositiveIntegerField(default=1)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='unknown')
    antenna_number = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-read_at']
        indexes = [
            models.Index(fields=['tenant', 'tag', '-read_at']),
            models.Index(fields=['tenant', 'reader', '-read_at']),
        ]

    def __str__(self):
        return f"{self.tag.epc_code} @ {self.reader.name} ({self.read_at:%Y-%m-%d %H:%M})"


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 4: Batch Scanning
# ═══════════════════════════════════════════════════════════════════════════

class BatchScanSession(StateMachineMixin, models.Model):
    PURPOSE_CHOICES = [
        ('receiving', 'Receiving'),
        ('counting', 'Cycle Counting'),
        ('picking', 'Picking'),
        ('putaway', 'Putaway'),
        ('transfer', 'Transfer'),
        ('audit', 'Audit'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'active': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='batch_scan_sessions',
    )
    session_number = models.CharField(max_length=20)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='receiving')
    device = models.ForeignKey(
        ScannerDevice, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='batch_sessions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='batch_sessions',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT, related_name='batch_sessions',
    )
    zone = models.ForeignKey(
        'warehousing.Zone', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='batch_sessions',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    total_items_scanned = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_batch_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'session_number')

    def __str__(self):
        return f"{self.session_number} — {self.get_purpose_display()}"

    def save(self, *args, **kwargs):
        def _do():
            if not self.session_number:
                self.session_number = self._generate_session_number()
            super(BatchScanSession, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'session_number', _do)

    def _generate_session_number(self):
        last = (
            BatchScanSession.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('session_number', flat=True).first()
        )
        if last and last.startswith('BSS-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'BSS-{num:05d}'

    def recalc_total(self):
        self.total_items_scanned = self.items.count()
        self.save(update_fields=['total_items_scanned', 'updated_at'])


class BatchScanItem(models.Model):
    RESOLUTION_TYPE_CHOICES = [
        ('product', 'Product'),
        ('lot', 'Lot / Batch'),
        ('serial', 'Serial Number'),
        ('bin', 'Bin'),
        ('rfid', 'RFID Tag'),
        ('unmatched', 'Unmatched'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='batch_scan_items',
    )
    session = models.ForeignKey(
        BatchScanSession, on_delete=models.CASCADE, related_name='items',
    )
    scanned_value = models.CharField(max_length=255)
    symbology = models.CharField(max_length=20, blank=True, default='')
    resolution_type = models.CharField(
        max_length=20, choices=RESOLUTION_TYPE_CHOICES, default='unmatched',
    )
    resolved_object_id = models.PositiveIntegerField(null=True, blank=True)
    resolved_display = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    scanned_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    error_message = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['scanned_at']
        indexes = [
            models.Index(fields=['tenant', 'session']),
        ]

    def __str__(self):
        return f"{self.scanned_value} ({self.quantity})"
