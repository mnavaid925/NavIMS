from decimal import Decimal

from django.conf import settings
from django.db import models


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_TERMS_CHOICES = [
        ('net_30', 'Net 30'),
        ('net_60', 'Net 60'),
        ('net_90', 'Net 90'),
        ('cod', 'Cash on Delivery'),
        ('prepaid', 'Prepaid'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['pending_approval', 'cancelled'],
        'pending_approval': ['approved', 'draft', 'cancelled'],
        'approved': ['sent', 'cancelled'],
        'sent': ['partially_received', 'received', 'cancelled'],
        'partially_received': ['received', 'cancelled'],
        'received': ['closed'],
        'closed': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='purchase_orders',
    )
    po_number = models.CharField(max_length=20, verbose_name='PO Number')
    vendor = models.ForeignKey(
        'vendors.Vendor',
        on_delete=models.PROTECT,
        related_name='purchase_orders',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    shipping_address = models.TextField(blank=True, default='')
    payment_terms = models.CharField(
        max_length=20, choices=PAYMENT_TERMS_CHOICES, default='net_30',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_purchase_orders',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'po_number')

    def __str__(self):
        return f"{self.po_number} - {self.vendor.company_name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def tax_total(self):
        return sum(item.tax_amount for item in self.items.all())

    @property
    def discount_total(self):
        return sum(item.discount_amount for item in self.items.all())

    @property
    def grand_total(self):
        return self.subtotal + self.tax_total - self.discount_total

    @property
    def approval_status(self):
        approvals = self.approvals.all()
        if approvals.filter(decision='rejected').exists():
            return 'rejected'
        rule = ApprovalRule.objects.filter(
            tenant=self.tenant,
            is_active=True,
            min_amount__lte=self.grand_total,
            max_amount__gte=self.grand_total,
        ).first()
        required = rule.required_approvals if rule else 1
        approved_count = approvals.filter(decision='approved').count()
        if approved_count >= required:
            return 'approved'
        return 'pending'

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self._generate_po_number()
        super().save(*args, **kwargs)

    def _generate_po_number(self):
        last = (
            PurchaseOrder.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('po_number', flat=True)
            .first()
        )
        if last and last.startswith('PO-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'PO-{num:05d}'


class PurchaseOrderItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='purchase_order_items',
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='purchase_order_items',
    )
    description = models.CharField(max_length=500, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Tax rate as percentage (e.g. 10.00 for 10%)',
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Discount amount per unit',
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def discount_amount(self):
        return self.quantity * self.discount

    @property
    def tax_amount(self):
        taxable = self.line_total - self.discount_amount
        return (taxable * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))


class ApprovalRule(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='approval_rules',
    )
    name = models.CharField(max_length=255)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    required_approvals = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['min_amount']

    def __str__(self):
        return f"{self.name} (${self.min_amount} - ${self.max_amount})"


class PurchaseOrderApproval(models.Model):
    DECISION_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='po_approvals',
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='approvals',
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='po_approvals',
    )
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    notes = models.TextField(blank=True, default='')
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-decided_at']
        unique_together = ('purchase_order', 'approver')

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.get_decision_display()} by {self.approver}"


class PurchaseOrderDispatch(models.Model):
    DISPATCH_METHOD_CHOICES = [
        ('email', 'Email'),
        ('edi', 'EDI (Electronic Data Interchange)'),
        ('manual', 'Manual / Hand Delivery'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='po_dispatches',
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='dispatches',
    )
    dispatch_method = models.CharField(max_length=20, choices=DISPATCH_METHOD_CHOICES, default='email')
    sent_to_email = models.EmailField(blank=True, default='')
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='po_dispatches',
    )
    notes = models.TextField(blank=True, default='')
    dispatched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dispatched_at']

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.get_dispatch_method_display()} on {self.dispatched_at}"
