from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum, F


# ──────────────────────────────────────────────
# Warehouse Location
# ──────────────────────────────────────────────

class WarehouseLocation(models.Model):
    LOCATION_TYPE_CHOICES = [
        ('zone', 'Zone'),
        ('aisle', 'Aisle'),
        ('rack', 'Rack'),
        ('shelf', 'Shelf'),
        ('bin', 'Bin'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='warehouse_locations',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    location_type = models.CharField(
        max_length=20, choices=LOCATION_TYPE_CHOICES, default='bin',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    capacity = models.PositiveIntegerField(default=0, help_text='Maximum quantity capacity')
    current_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def available_capacity(self):
        return max(self.capacity - self.current_quantity, 0)

    @property
    def is_full(self):
        return self.capacity > 0 and self.current_quantity >= self.capacity

    @property
    def full_path(self):
        parts = [self.name]
        parent = self.parent
        while parent:
            parts.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(parts)


# ──────────────────────────────────────────────
# Goods Receipt Note (GRN)
# ──────────────────────────────────────────────

class GoodsReceiptNote(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('inspecting', 'Inspecting'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['inspecting', 'completed', 'cancelled'],
        'inspecting': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='grns',
    )
    grn_number = models.CharField(max_length=20, verbose_name='GRN Number')
    purchase_order = models.ForeignKey(
        'purchase_orders.PurchaseOrder',
        on_delete=models.PROTECT,
        related_name='grns',
    )
    received_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    delivery_note_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_grns',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_grns',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'grn_number')

    def __str__(self):
        return f"{self.grn_number} - PO: {self.purchase_order.po_number}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def total_received_qty(self):
        return self.items.aggregate(total=Sum('quantity_received'))['total'] or 0

    def save(self, *args, **kwargs):
        if not self.grn_number:
            self.grn_number = self._generate_grn_number()
        super().save(*args, **kwargs)

    def _generate_grn_number(self):
        last = (
            GoodsReceiptNote.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('grn_number', flat=True)
            .first()
        )
        if last and last.startswith('GRN-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'GRN-{num:05d}'

    def update_po_status(self):
        """Update the linked PO status based on total received quantities across all completed GRNs."""
        po = self.purchase_order
        po_items = po.items.all()
        all_received = True

        for po_item in po_items:
            total_received = (
                GoodsReceiptNoteItem.objects.filter(
                    grn__purchase_order=po,
                    grn__status='completed',
                    po_item=po_item,
                ).aggregate(total=Sum('quantity_received'))['total'] or 0
            )
            if total_received < po_item.quantity:
                all_received = False
                break

        if all_received:
            if po.can_transition_to('received'):
                po.status = 'received'
                po.save()
        else:
            if po.can_transition_to('partially_received'):
                po.status = 'partially_received'
                po.save()


class GoodsReceiptNoteItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='grn_items',
    )
    grn = models.ForeignKey(
        GoodsReceiptNote,
        on_delete=models.CASCADE,
        related_name='items',
    )
    po_item = models.ForeignKey(
        'purchase_orders.PurchaseOrderItem',
        on_delete=models.PROTECT,
        related_name='grn_items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='grn_items',
    )
    quantity_received = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.product.name} x {self.quantity_received}"

    @property
    def quantity_ordered(self):
        return self.po_item.quantity

    @property
    def quantity_previously_received(self):
        """Total received across other completed GRNs for the same PO item."""
        return (
            GoodsReceiptNoteItem.objects.filter(
                po_item=self.po_item,
                grn__status='completed',
            )
            .exclude(pk=self.pk)
            .aggregate(total=Sum('quantity_received'))['total'] or 0
        )

    @property
    def quantity_outstanding(self):
        return max(self.quantity_ordered - self.quantity_previously_received, 0)


# ──────────────────────────────────────────────
# Vendor Invoice
# ──────────────────────────────────────────────

class VendorInvoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_match', 'Pending Match'),
        ('matched', 'Matched'),
        ('disputed', 'Disputed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['pending_match', 'cancelled'],
        'pending_match': ['matched', 'disputed', 'cancelled'],
        'matched': ['paid', 'disputed'],
        'disputed': ['pending_match', 'cancelled'],
        'paid': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='vendor_invoices',
    )
    invoice_number = models.CharField(max_length=100)
    vendor = models.ForeignKey(
        'vendors.Vendor',
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    purchase_order = models.ForeignKey(
        'purchase_orders.PurchaseOrder',
        on_delete=models.PROTECT,
        related_name='vendor_invoices',
    )
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    document = models.FileField(upload_to='receiving/invoices/', blank=True, null=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_vendor_invoices',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'invoice_number')

    def __str__(self):
        return f"INV-{self.invoice_number} - {self.vendor.company_name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])


# ──────────────────────────────────────────────
# Three-Way Match
# ──────────────────────────────────────────────

class ThreeWayMatch(models.Model):
    MATCH_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('discrepancy', 'Discrepancy Found'),
        ('resolved', 'Resolved'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='three_way_matches',
    )
    match_number = models.CharField(max_length=20, verbose_name='Match Number')
    purchase_order = models.ForeignKey(
        'purchase_orders.PurchaseOrder',
        on_delete=models.PROTECT,
        related_name='three_way_matches',
    )
    grn = models.ForeignKey(
        GoodsReceiptNote,
        on_delete=models.PROTECT,
        related_name='three_way_matches',
    )
    vendor_invoice = models.ForeignKey(
        VendorInvoice,
        on_delete=models.PROTECT,
        related_name='three_way_matches',
    )
    status = models.CharField(max_length=20, choices=MATCH_STATUS_CHOICES, default='pending')
    po_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grn_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    invoice_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity_match = models.BooleanField(default=False)
    price_match = models.BooleanField(default=False)
    total_match = models.BooleanField(default=False)
    discrepancy_notes = models.TextField(blank=True, default='')
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_matches',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_matches',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'match_number')

    def __str__(self):
        return f"{self.match_number} - PO: {self.purchase_order.po_number}"

    @property
    def is_fully_matched(self):
        return self.quantity_match and self.price_match and self.total_match

    def perform_match(self):
        """Compare PO, GRN, and Invoice to determine match status."""
        po = self.purchase_order
        grn = self.grn
        invoice = self.vendor_invoice

        # Set totals
        self.po_total = po.grand_total
        self.invoice_total = invoice.total_amount

        # Calculate GRN total based on received qty * PO unit prices
        grn_total = Decimal('0')
        for grn_item in grn.items.all().select_related('po_item'):
            grn_total += grn_item.quantity_received * grn_item.po_item.unit_price
        self.grn_total = grn_total

        # Quantity match: check if received quantities match ordered quantities
        qty_matched = True
        for po_item in po.items.all():
            received = (
                grn.items.filter(po_item=po_item)
                .aggregate(total=Sum('quantity_received'))['total'] or 0
            )
            if received != po_item.quantity:
                qty_matched = False
                break
        self.quantity_match = qty_matched

        # Price match: PO total vs Invoice total (within tolerance)
        tolerance = Decimal('0.01')
        self.price_match = abs(self.po_total - self.invoice_total) <= tolerance

        # Total match
        self.total_match = self.quantity_match and self.price_match

        # Set status
        if self.total_match:
            self.status = 'matched'
        else:
            self.status = 'discrepancy'

        self.save()

    def save(self, *args, **kwargs):
        if not self.match_number:
            self.match_number = self._generate_match_number()
        super().save(*args, **kwargs)

    def _generate_match_number(self):
        last = (
            ThreeWayMatch.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('match_number', flat=True)
            .first()
        )
        if last and last.startswith('TWM-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'TWM-{num:05d}'


# ──────────────────────────────────────────────
# Quality Inspection
# ──────────────────────────────────────────────

class QualityInspection(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='quality_inspections',
    )
    inspection_number = models.CharField(max_length=20, verbose_name='Inspection Number')
    grn = models.ForeignKey(
        GoodsReceiptNote,
        on_delete=models.CASCADE,
        related_name='inspections',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_inspections',
    )
    inspection_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_inspections',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'inspection_number')

    def __str__(self):
        return f"{self.inspection_number} - GRN: {self.grn.grn_number}"

    @property
    def total_inspected(self):
        return self.items.aggregate(total=Sum('quantity_inspected'))['total'] or 0

    @property
    def total_accepted(self):
        return self.items.aggregate(total=Sum('quantity_accepted'))['total'] or 0

    @property
    def total_rejected(self):
        return self.items.aggregate(total=Sum('quantity_rejected'))['total'] or 0

    @property
    def total_quarantined(self):
        return self.items.aggregate(total=Sum('quantity_quarantined'))['total'] or 0

    def save(self, *args, **kwargs):
        if not self.inspection_number:
            self.inspection_number = self._generate_inspection_number()
        super().save(*args, **kwargs)

    def _generate_inspection_number(self):
        last = (
            QualityInspection.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('inspection_number', flat=True)
            .first()
        )
        if last and last.startswith('QI-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'QI-{num:05d}'


class QualityInspectionItem(models.Model):
    DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('quarantined', 'Quarantined'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='quality_inspection_items',
    )
    inspection = models.ForeignKey(
        QualityInspection,
        on_delete=models.CASCADE,
        related_name='items',
    )
    grn_item = models.ForeignKey(
        GoodsReceiptNoteItem,
        on_delete=models.CASCADE,
        related_name='inspection_items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='inspection_items',
    )
    quantity_inspected = models.PositiveIntegerField(default=0)
    quantity_accepted = models.PositiveIntegerField(default=0)
    quantity_rejected = models.PositiveIntegerField(default=0)
    quantity_quarantined = models.PositiveIntegerField(default=0)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default='pending')
    reject_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} - {self.get_decision_display()}"


# ──────────────────────────────────────────────
# Putaway Task
# ──────────────────────────────────────────────

class PutawayTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['assigned', 'cancelled'],
        'assigned': ['in_progress', 'cancelled'],
        'in_progress': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='putaway_tasks',
    )
    task_number = models.CharField(max_length=20, verbose_name='Task Number')
    grn = models.ForeignKey(
        GoodsReceiptNote,
        on_delete=models.CASCADE,
        related_name='putaway_tasks',
    )
    grn_item = models.ForeignKey(
        GoodsReceiptNoteItem,
        on_delete=models.CASCADE,
        related_name='putaway_tasks',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='putaway_tasks',
    )
    quantity = models.PositiveIntegerField(default=0)
    suggested_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suggested_putaways',
    )
    assigned_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_putaways',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='putaway_tasks',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_putaway_tasks',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'task_number')

    def __str__(self):
        return f"{self.task_number} - {self.product.name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.task_number:
            self.task_number = self._generate_task_number()
        super().save(*args, **kwargs)

    def _generate_task_number(self):
        last = (
            PutawayTask.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('task_number', flat=True)
            .first()
        )
        if last and last.startswith('PUT-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'PUT-{num:05d}'

    @staticmethod
    def suggest_location(tenant, quantity):
        """Find the best-fit active bin with enough available capacity."""
        locations = (
            WarehouseLocation.objects.filter(
                tenant=tenant,
                is_active=True,
                location_type='bin',
            )
            .annotate(available=F('capacity') - F('current_quantity'))
            .filter(available__gte=quantity)
            .order_by('available')
        )
        return locations.first()
