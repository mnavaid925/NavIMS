from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction

from core.state_machine import StateMachineMixin


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
# Submodule 1: QC Checklists
# ═══════════════════════════════════════════════════════════════════════════

class QCChecklist(models.Model):
    APPLIES_TO_CHOICES = [
        ('all', 'All Products'),
        ('product', 'Specific Product'),
        ('vendor', 'Specific Vendor'),
        ('category', 'Specific Category'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='qc_checklists',
    )
    code = models.CharField(max_length=20, verbose_name='Checklist Code')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    applies_to = models.CharField(max_length=20, choices=APPLIES_TO_CHOICES, default='all')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='qc_checklists',
    )
    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='qc_checklists',
    )
    category = models.ForeignKey(
        'catalog.Category', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='qc_checklists',
    )
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_qc_checklists',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.code:
                self.code = self._generate_code()
            super(QCChecklist, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'code', _do)

    def _generate_code(self):
        last = (
            QCChecklist.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('code', flat=True).first()
        )
        if last and last.startswith('QCC-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'QCC-{num:05d}'


class QCChecklistItem(models.Model):
    CHECK_TYPE_CHOICES = [
        ('visual', 'Visual Inspection'),
        ('measurement', 'Measurement'),
        ('boolean', 'Yes / No'),
        ('text', 'Free Text'),
        ('photo', 'Photo Required'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='qc_checklist_items',
    )
    checklist = models.ForeignKey(
        QCChecklist, on_delete=models.CASCADE, related_name='items',
    )
    sequence = models.PositiveIntegerField(default=1)
    check_name = models.CharField(max_length=200)
    check_type = models.CharField(max_length=20, choices=CHECK_TYPE_CHOICES, default='visual')
    expected_value = models.CharField(max_length=200, blank=True, default='')
    is_critical = models.BooleanField(
        default=False, help_text='Failing a critical item auto-quarantines the item.',
    )

    class Meta:
        ordering = ['checklist', 'sequence']

    def __str__(self):
        return f'{self.sequence}. {self.check_name}'


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 2: Inspection Routing
# ═══════════════════════════════════════════════════════════════════════════

class InspectionRoute(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='inspection_routes',
    )
    code = models.CharField(max_length=20, verbose_name='Route Code')
    name = models.CharField(max_length=200)
    source_warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT,
        related_name='inspection_routes',
    )
    qc_zone = models.ForeignKey(
        'warehousing.Zone', on_delete=models.PROTECT,
        related_name='qc_inspection_routes',
        help_text='Zone where items are held pending QC.',
    )
    putaway_zone = models.ForeignKey(
        'warehousing.Zone', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='qc_putaway_routes',
        help_text='Destination zone after QC pass.',
    )
    priority = models.PositiveIntegerField(
        default=100, help_text='Lower = higher priority.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.code:
                self.code = self._generate_code()
            super(InspectionRoute, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'code', _do)

    def _generate_code(self):
        last = (
            InspectionRoute.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('code', flat=True).first()
        )
        if last and last.startswith('IR-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'IR-{num:05d}'


class InspectionRouteRule(models.Model):
    APPLIES_TO_CHOICES = [
        ('all', 'All Items'),
        ('product', 'Specific Product'),
        ('vendor', 'Specific Vendor'),
        ('category', 'Specific Category'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='inspection_route_rules',
    )
    route = models.ForeignKey(
        InspectionRoute, on_delete=models.CASCADE, related_name='rules',
    )
    applies_to = models.CharField(max_length=20, choices=APPLIES_TO_CHOICES, default='all')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inspection_route_rules',
    )
    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inspection_route_rules',
    )
    category = models.ForeignKey(
        'catalog.Category', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inspection_route_rules',
    )
    checklist = models.ForeignKey(
        QCChecklist, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='route_rules',
    )
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['route', 'id']

    def __str__(self):
        return f'{self.route.code} — {self.get_applies_to_display()}'


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 3: Quarantine Management
# ═══════════════════════════════════════════════════════════════════════════

class QuarantineRecord(StateMachineMixin, models.Model):
    REASON_CHOICES = [
        ('defect', 'Defect'),
        ('expiry', 'Approaching Expiry / Expired'),
        ('contamination', 'Contamination'),
        ('damage', 'Damage'),
        ('vendor_issue', 'Vendor Issue'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active Hold'),
        ('under_review', 'Under Review'),
        ('released', 'Released'),
        ('scrapped', 'Scrapped'),
    ]

    DISPOSITION_CHOICES = [
        ('return_to_stock', 'Return to Stock'),
        ('rework', 'Rework'),
        ('scrap', 'Scrap'),
        ('return_to_vendor', 'Return to Vendor'),
    ]

    VALID_TRANSITIONS = {
        'active': ['under_review', 'released', 'scrapped'],
        'under_review': ['active', 'released', 'scrapped'],
        'released': [],
        'scrapped': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='quarantine_records',
    )
    quarantine_number = models.CharField(max_length=20)
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='quarantine_records',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT,
        related_name='quarantine_records',
    )
    zone = models.ForeignKey(
        'warehousing.Zone', on_delete=models.PROTECT,
        related_name='quarantine_records',
        help_text='Quarantine zone holding this item.',
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default='defect')
    reason_notes = models.TextField(blank=True, default='')
    grn = models.ForeignKey(
        'receiving.GoodsReceiptNote', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quarantine_records',
    )
    lot = models.ForeignKey(
        'lot_tracking.LotBatch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quarantine_records',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quarantine_holds_created',
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quarantine_holds_released',
    )
    released_at = models.DateTimeField(null=True, blank=True)
    release_disposition = models.CharField(
        max_length=20, choices=DISPOSITION_CHOICES, blank=True, default='',
    )
    release_notes = models.TextField(blank=True, default='')
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'quarantine_number')

    def __str__(self):
        return f'{self.quarantine_number} — {self.product.sku} x{self.quantity}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.quarantine_number:
                self.quarantine_number = self._generate_number()
            super(QuarantineRecord, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'quarantine_number', _do)

    def _generate_number(self):
        last = (
            QuarantineRecord.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('quarantine_number', flat=True).first()
        )
        if last and last.startswith('QR-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'QR-{num:05d}'


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 4: Defect & Scrap Reporting
# ═══════════════════════════════════════════════════════════════════════════

class DefectReport(StateMachineMixin, models.Model):
    DEFECT_TYPE_CHOICES = [
        ('visual', 'Visual / Cosmetic'),
        ('functional', 'Functional'),
        ('packaging', 'Packaging'),
        ('labeling', 'Labeling'),
        ('expiry', 'Expiry'),
        ('contamination', 'Contamination'),
        ('other', 'Other'),
    ]

    SEVERITY_CHOICES = [
        ('minor', 'Minor'),
        ('major', 'Major'),
        ('critical', 'Critical'),
    ]

    SOURCE_CHOICES = [
        ('receiving', 'Receiving / Inspection'),
        ('stocktaking', 'Stocktaking / Cycle Count'),
        ('customer_return', 'Customer Return'),
        ('production', 'Production'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('scrapped', 'Scrapped'),
    ]

    VALID_TRANSITIONS = {
        'open': ['investigating', 'resolved', 'scrapped'],
        'investigating': ['resolved', 'scrapped', 'open'],
        'resolved': [],
        'scrapped': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='defect_reports',
    )
    defect_number = models.CharField(max_length=20)
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='defect_reports',
    )
    lot = models.ForeignKey(
        'lot_tracking.LotBatch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='defect_reports',
    )
    serial = models.ForeignKey(
        'lot_tracking.SerialNumber', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='defect_reports',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT, related_name='defect_reports',
    )
    quantity_affected = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    defect_type = models.CharField(max_length=20, choices=DEFECT_TYPE_CHOICES, default='visual')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='minor')
    description = models.TextField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='receiving')
    grn = models.ForeignKey(
        'receiving.GoodsReceiptNote', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='defect_reports',
    )
    quarantine_record = models.ForeignKey(
        QuarantineRecord, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='defect_reports',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reported_defects',
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='resolved_defects',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default='')
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'defect_number')

    def __str__(self):
        return f'{self.defect_number} — {self.product.sku} ({self.get_severity_display()})'

    def save(self, *args, **kwargs):
        def _do():
            if not self.defect_number:
                self.defect_number = self._generate_number()
            super(DefectReport, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'defect_number', _do)

    def _generate_number(self):
        last = (
            DefectReport.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('defect_number', flat=True).first()
        )
        if last and last.startswith('DEF-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'DEF-{num:05d}'


class DefectPhoto(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='defect_photos',
    )
    defect_report = models.ForeignKey(
        DefectReport, on_delete=models.CASCADE, related_name='photos',
    )
    image = models.ImageField(upload_to='quality_control/defect_photos/')
    caption = models.CharField(max_length=200, blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f'Photo for {self.defect_report.defect_number}'


class ScrapWriteOff(StateMachineMixin, models.Model):
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('posted', 'Posted'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['approved', 'rejected'],
        'approved': ['posted', 'rejected'],
        'rejected': [],
        'posted': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='scrap_writeoffs',
    )
    scrap_number = models.CharField(max_length=20)
    defect_report = models.ForeignKey(
        DefectReport, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scrap_writeoffs',
    )
    quarantine_record = models.ForeignKey(
        QuarantineRecord, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='scrap_writeoffs',
    )
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='scrap_writeoffs',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.PROTECT, related_name='scrap_writeoffs',
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reason = models.CharField(max_length=200)
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES, default='pending',
    )
    status = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES, default='pending',
        help_text='Mirror of approval_status for StateMachineMixin.',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requested_scrap_writeoffs',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_scrap_writeoffs',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_scrap_writeoffs',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    stock_adjustment = models.ForeignKey(
        'inventory.StockAdjustment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_scrap_writeoffs',
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'scrap_number')

    def __str__(self):
        return f'{self.scrap_number} — {self.product.sku} x{self.quantity}'

    def save(self, *args, **kwargs):
        # Keep status in lockstep with approval_status so StateMachineMixin
        # (which reads self.status) stays accurate.
        self.status = self.approval_status
        # Compute total_value from quantity × unit_cost.
        try:
            self.total_value = (self.unit_cost or 0) * (self.quantity or 0)
        except (TypeError, ValueError):
            self.total_value = 0

        def _do():
            if not self.scrap_number:
                self.scrap_number = self._generate_number()
            super(ScrapWriteOff, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'scrap_number', _do)

    def _generate_number(self):
        last = (
            ScrapWriteOff.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('scrap_number', flat=True).first()
        )
        if last and last.startswith('SCR-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'SCR-{num:05d}'
