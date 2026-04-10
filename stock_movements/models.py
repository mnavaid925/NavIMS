from django.conf import settings
from django.db import models
from django.utils import timezone


# ──────────────────────────────────────────────
# Sub-module 1 & 2: Inter/Intra-Warehouse Transfers
# ──────────────────────────────────────────────

class StockTransfer(models.Model):
    TRANSFER_TYPE_CHOICES = [
        ('inter_warehouse', 'Inter-Warehouse'),
        ('intra_warehouse', 'Intra-Warehouse'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['pending_approval', 'approved', 'cancelled'],
        'pending_approval': ['approved', 'cancelled'],
        'approved': ['in_transit', 'cancelled'],
        'in_transit': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_transfers',
    )
    transfer_number = models.CharField(max_length=20, verbose_name='Transfer Number')
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPE_CHOICES)
    source_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='outgoing_transfers',
    )
    destination_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='incoming_transfers',
        null=True,
        blank=True,
    )
    source_bin = models.ForeignKey(
        'warehousing.Bin',
        on_delete=models.PROTECT,
        related_name='outgoing_transfers',
        null=True,
        blank=True,
    )
    destination_bin = models.ForeignKey(
        'warehousing.Bin',
        on_delete=models.PROTECT,
        related_name='incoming_transfers',
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_transfers',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_transfers',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'transfer_number')

    def __str__(self):
        return f"{self.transfer_number} — {self.get_transfer_type_display()} ({self.get_status_display()})"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def total_items(self):
        return self.items.count()

    @property
    def total_quantity(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def total_received(self):
        return self.items.aggregate(total=models.Sum('received_quantity'))['total'] or 0

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            self.transfer_number = self._generate_transfer_number()
        super().save(*args, **kwargs)

    def _generate_transfer_number(self):
        last = (
            StockTransfer.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('transfer_number', flat=True)
            .first()
        )
        if last and last.startswith('TRF-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'TRF-{num:05d}'


class StockTransferItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='stock_transfer_items',
    )
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='transfer_items',
    )
    quantity = models.PositiveIntegerField()
    received_quantity = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def is_fully_received(self):
        return self.received_quantity >= self.quantity


# ──────────────────────────────────────────────
# Sub-module 3: Transfer Approval Workflow
# ──────────────────────────────────────────────

class TransferApprovalRule(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='transfer_approval_rules',
    )
    name = models.CharField(max_length=100)
    min_items = models.PositiveIntegerField(default=0)
    max_items = models.PositiveIntegerField(null=True, blank=True)
    requires_approval = models.BooleanField(default=True)
    approver_role = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['min_items']

    def __str__(self):
        return f"{self.name} ({self.min_items}–{self.max_items or '∞'} items)"


class TransferApproval(models.Model):
    DECISION_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='transfer_approvals',
    )
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name='approvals',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_approvals',
    )
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    comments = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transfer.transfer_number} — {self.get_decision_display()} by {self.approved_by}"


# ──────────────────────────────────────────────
# Sub-module 4: Transfer Routing
# ──────────────────────────────────────────────

class TransferRoute(models.Model):
    TRANSIT_METHOD_CHOICES = [
        ('truck', 'Truck'),
        ('van', 'Van'),
        ('courier', 'Courier'),
        ('internal', 'Internal'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='transfer_routes',
    )
    name = models.CharField(max_length=200)
    source_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='outgoing_routes',
    )
    destination_warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='incoming_routes',
    )
    transit_method = models.CharField(max_length=20, choices=TRANSIT_METHOD_CHOICES, default='truck')
    estimated_duration_hours = models.PositiveIntegerField(default=0)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    instructions = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — {self.source_warehouse.code} → {self.destination_warehouse.code}"
