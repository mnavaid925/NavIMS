from decimal import Decimal

from django.conf import settings
from django.db import models


# ──────────────────────────────────────────────
# Sub-module 1: Return Merchandise Authorization
# ──────────────────────────────────────────────

class ReturnAuthorization(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('received', 'Received'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    REASON_CHOICES = [
        ('defective', 'Defective / Damaged'),
        ('wrong_item', 'Wrong Item Shipped'),
        ('not_as_described', 'Not as Described'),
        ('customer_change', 'Customer Changed Mind'),
        ('warranty', 'Warranty Claim'),
        ('expired', 'Expired / Near Expiry'),
        ('other', 'Other'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['pending', 'cancelled'],
        'pending': ['approved', 'rejected', 'cancelled'],
        'approved': ['received', 'cancelled'],
        'rejected': ['draft'],
        'received': ['closed'],
        'closed': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='return_authorizations',
    )
    rma_number = models.CharField(max_length=20, verbose_name='RMA Number')
    sales_order = models.ForeignKey(
        'orders.SalesOrder',
        on_delete=models.PROTECT,
        related_name='return_authorizations',
    )
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, default='')
    customer_phone = models.CharField(max_length=30, blank=True, default='')
    return_address = models.TextField(blank=True, default='')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default='defective')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    requested_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True)
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='return_authorizations',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_rmas',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_rmas',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'rma_number')

    def __str__(self):
        return f"{self.rma_number} — {self.customer_name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def total_qty_requested(self):
        return sum(item.qty_requested for item in self.items.all())

    @property
    def total_qty_received(self):
        return sum(item.qty_received for item in self.items.all())

    @property
    def total_value(self):
        return sum(
            (item.qty_requested * item.unit_price) for item in self.items.all()
        )

    def save(self, *args, **kwargs):
        if not self.rma_number:
            self.rma_number = self._generate_rma_number()
        super().save(*args, **kwargs)

    def _generate_rma_number(self):
        last = (
            ReturnAuthorization.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('rma_number', flat=True)
            .first()
        )
        if last and last.startswith('RMA-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'RMA-{num:05d}'


class ReturnAuthorizationItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='return_authorization_items',
    )
    rma = models.ForeignKey(
        ReturnAuthorization,
        on_delete=models.CASCADE,
        related_name='items',
    )
    sales_order_item = models.ForeignKey(
        'orders.SalesOrderItem',
        on_delete=models.PROTECT,
        related_name='return_items',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='return_items',
    )
    description = models.CharField(max_length=500, blank=True, default='')
    qty_requested = models.PositiveIntegerField(default=1)
    qty_received = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason_note = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} x {self.qty_requested}"

    @property
    def line_total(self):
        return self.qty_requested * self.unit_price


# ──────────────────────────────────────────────
# Sub-module 2: Return Inspection
# ──────────────────────────────────────────────

class ReturnInspection(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    RESULT_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('partial', 'Partial'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['in_progress', 'cancelled'],
        'in_progress': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='return_inspections',
    )
    inspection_number = models.CharField(max_length=20, verbose_name='Inspection Number')
    rma = models.ForeignKey(
        ReturnAuthorization,
        on_delete=models.CASCADE,
        related_name='inspections',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    overall_result = models.CharField(
        max_length=20, choices=RESULT_CHOICES, blank=True, default='',
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='return_inspections',
    )
    inspected_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'inspection_number')

    def __str__(self):
        return f"{self.inspection_number} — {self.rma.rma_number}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.inspection_number:
            self.inspection_number = self._generate_inspection_number()
        super().save(*args, **kwargs)

    def _generate_inspection_number(self):
        last = (
            ReturnInspection.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('inspection_number', flat=True)
            .first()
        )
        if last and last.startswith('RINS-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'RINS-{num:05d}'


class ReturnInspectionItem(models.Model):
    CONDITION_CHOICES = [
        ('good', 'Good / Like New'),
        ('minor_damage', 'Minor Damage'),
        ('major_damage', 'Major Damage'),
        ('missing_parts', 'Missing Parts'),
        ('defective', 'Defective'),
        ('unusable', 'Unusable / Scrap'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='return_inspection_items',
    )
    inspection = models.ForeignKey(
        ReturnInspection,
        on_delete=models.CASCADE,
        related_name='items',
    )
    rma_item = models.ForeignKey(
        ReturnAuthorizationItem,
        on_delete=models.CASCADE,
        related_name='inspection_items',
    )
    qty_inspected = models.PositiveIntegerField(default=0)
    qty_passed = models.PositiveIntegerField(default=0)
    qty_failed = models.PositiveIntegerField(default=0)
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='good',
    )
    restockable = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.rma_item.product.name} — {self.get_condition_display()}"


# ──────────────────────────────────────────────
# Sub-module 3: Disposition Routing
# ──────────────────────────────────────────────

class Disposition(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('cancelled', 'Cancelled'),
    ]

    DECISION_CHOICES = [
        ('restock', 'Restock to Inventory'),
        ('repair', 'Send to Repair'),
        ('liquidate', 'Liquidate'),
        ('scrap', 'Scrap / Destroy'),
        ('return_to_vendor', 'Return to Vendor'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['processed', 'cancelled'],
        'processed': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='dispositions',
    )
    disposition_number = models.CharField(max_length=20, verbose_name='Disposition Number')
    rma = models.ForeignKey(
        ReturnAuthorization,
        on_delete=models.CASCADE,
        related_name='dispositions',
    )
    inspection = models.ForeignKey(
        ReturnInspection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispositions',
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default='restock')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='dispositions',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_dispositions',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'disposition_number')

    def __str__(self):
        return f"{self.disposition_number} — {self.get_decision_display()}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.disposition_number:
            self.disposition_number = self._generate_disposition_number()
        super().save(*args, **kwargs)

    def _generate_disposition_number(self):
        last = (
            Disposition.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('disposition_number', flat=True)
            .first()
        )
        if last and last.startswith('DISP-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'DISP-{num:05d}'


class DispositionItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='disposition_items',
    )
    disposition = models.ForeignKey(
        Disposition,
        on_delete=models.CASCADE,
        related_name='items',
    )
    inspection_item = models.ForeignKey(
        ReturnInspectionItem,
        on_delete=models.CASCADE,
        related_name='disposition_items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='disposition_items',
    )
    qty = models.PositiveIntegerField(default=0)
    destination_bin = models.ForeignKey(
        'warehousing.Bin',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disposition_items',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} x {self.qty}"


# ──────────────────────────────────────────────
# Sub-module 4: Credit / Refund Processing
# ──────────────────────────────────────────────

class RefundCredit(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    TYPE_CHOICES = [
        ('refund', 'Refund'),
        ('credit_note', 'Credit Note'),
        ('store_credit', 'Store Credit'),
        ('exchange', 'Exchange'),
    ]

    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Credit/Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('store_credit', 'Store Credit'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['processed', 'failed', 'cancelled'],
        'processed': [],
        'failed': ['pending', 'cancelled'],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='refund_credits',
    )
    refund_number = models.CharField(max_length=20, verbose_name='Refund Number')
    rma = models.ForeignKey(
        ReturnAuthorization,
        on_delete=models.CASCADE,
        related_name='refunds',
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='refund')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='card')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='USD')
    reference_number = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_refunds',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'refund_number')

    def __str__(self):
        return f"{self.refund_number} — {self.get_type_display()} {self.amount}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.refund_number:
            self.refund_number = self._generate_refund_number()
        super().save(*args, **kwargs)

    def _generate_refund_number(self):
        last = (
            RefundCredit.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('refund_number', flat=True)
            .first()
        )
        if last and last.startswith('REF-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'REF-{num:05d}'
