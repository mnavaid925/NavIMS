from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction


def _next_number(model, tenant, field_name, prefix):
    last = (
        model.objects.filter(tenant=tenant)
        .order_by('-id')
        .values_list(field_name, flat=True)
        .first()
    )
    if last and last.startswith(prefix):
        try:
            num = int(last.split('-')[1]) + 1
        except (IndexError, ValueError):
            num = 1
    else:
        num = 1
    return f'{prefix}{num:05d}'


# ──────────────────────────────────────────────
# Sub-module 4: Shipping Integration (no FK deps on other orders models)
# ──────────────────────────────────────────────

class Carrier(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='carriers',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, verbose_name='Carrier Code')
    api_endpoint = models.URLField(blank=True, default='', verbose_name='API Endpoint')
    api_key = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='API Key',
        help_text='Placeholder for future carrier API integration',
    )
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.name} ({self.code})"


class ShippingRate(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='shipping_rates',
    )
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.CASCADE,
        related_name='rates',
    )
    service_level = models.CharField(max_length=100, verbose_name='Service Level')
    origin_region = models.CharField(max_length=100, blank=True, default='')
    destination_region = models.CharField(max_length=100, blank=True, default='')
    base_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_per_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_transit_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['carrier__name', 'service_level']

    def __str__(self):
        return f"{self.carrier.name} — {self.service_level}"


# ──────────────────────────────────────────────
# Sub-module 1: Sales Order Processing
# ──────────────────────────────────────────────

class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_fulfillment', 'In Fulfillment'),
        ('picked', 'Picked'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
        ('on_hold', 'On Hold'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    VALID_TRANSITIONS = {
        'draft': ['confirmed', 'cancelled'],
        'confirmed': ['in_fulfillment', 'on_hold', 'cancelled'],
        'in_fulfillment': ['picked', 'on_hold', 'cancelled'],
        'picked': ['packed', 'on_hold', 'cancelled'],
        'packed': ['shipped', 'on_hold', 'cancelled'],
        'shipped': ['delivered', 'cancelled'],
        'delivered': ['closed'],
        'closed': [],
        'cancelled': ['draft'],
        'on_hold': ['confirmed', 'in_fulfillment', 'picked', 'packed', 'cancelled'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='sales_orders',
    )
    order_number = models.CharField(max_length=20, verbose_name='Order Number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, default='')
    customer_phone = models.CharField(max_length=30, blank=True, default='')
    shipping_address = models.TextField(blank=True, default='')
    billing_address = models.TextField(blank=True, default='')
    order_date = models.DateField()
    required_date = models.DateField(null=True, blank=True, verbose_name='Required Delivery Date')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='sales_orders',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sales_orders',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'order_number')
        indexes = [
            # D-18: forecasting's historical-demand query joins on
            # (tenant, warehouse, order_date). Without this index, the
            # forecasting/views.py::_historical_demand_for scan grows
            # O(n) with order volume per period.
            models.Index(fields=['tenant', 'warehouse', 'order_date']),
        ]

    def __str__(self):
        return f"{self.order_number} — {self.customer_name}"

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
    def total_items(self):
        return self.items.count()

    def save(self, *args, **kwargs):
        if self.pk or self.order_number:
            super().save(*args, **kwargs)
            return
        from django.db import IntegrityError
        for _ in range(5):
            with transaction.atomic():
                self.order_number = _next_number(
                    SalesOrder, self.tenant, 'order_number', 'SO-',
                )
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.order_number = ''
                    continue
        raise RuntimeError('Unable to generate unique order number after retries.')


class SalesOrderItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='sales_order_items',
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='sales_order_items',
    )
    description = models.CharField(max_length=500, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text='Tax rate as percentage (e.g. 10.00 for 10%)',
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Discount amount per unit',
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [
            # D-18: forecasting filters SalesOrderItem by (tenant, product)
            # before the JOIN to SalesOrder — this index lets that pre-filter
            # resolve without a scan of the full item table.
            models.Index(fields=['tenant', 'product']),
        ]

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


# ──────────────────────────────────────────────
# Sub-module 3: Wave Planning
# ─────────────────────────────────────────────��

class WavePlan(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('released', 'Released'),
        ('in_progress', 'In Progress'),
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
        'draft': ['released', 'cancelled'],
        'released': ['in_progress', 'cancelled'],
        'in_progress': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': ['draft'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='wave_plans',
    )
    wave_number = models.CharField(max_length=20, verbose_name='Wave Number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='wave_plans',
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    order_date_from = models.DateField(null=True, blank=True, verbose_name='Order Date From')
    order_date_to = models.DateField(null=True, blank=True, verbose_name='Order Date To')
    orders = models.ManyToManyField(
        SalesOrder,
        through='WaveOrderAssignment',
        related_name='wave_plans',
        blank=True,
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_wave_plans',
    )
    released_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'wave_number')

    def __str__(self):
        return f"{self.wave_number} — {self.warehouse.name}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if self.pk or self.wave_number:
            super().save(*args, **kwargs)
            return
        from django.db import IntegrityError
        for _ in range(5):
            with transaction.atomic():
                self.wave_number = _next_number(
                    WavePlan, self.tenant, 'wave_number', 'WV-',
                )
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.wave_number = ''
                    continue
        raise RuntimeError('Unable to generate unique wave number after retries.')


class WaveOrderAssignment(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='wave_order_assignments',
    )
    wave_plan = models.ForeignKey(
        WavePlan,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='wave_assignments',
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('wave_plan', 'sales_order')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.wave_plan.wave_number} ← {self.sales_order.order_number}"


# ──────────────────────────────────────────────
# Sub-module 2: Pick, Pack, Ship Workflow
# ──────────────────────────────────────────────

class PickList(models.Model):
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
        related_name='pick_lists',
    )
    pick_number = models.CharField(max_length=20, verbose_name='Pick Number')
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='pick_lists',
        null=True,
        blank=True,
    )
    wave_plan = models.ForeignKey(
        WavePlan,
        on_delete=models.SET_NULL,
        related_name='pick_lists',
        null=True,
        blank=True,
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.PROTECT,
        related_name='pick_lists',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_pick_lists',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_pick_lists',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'pick_number')

    def __str__(self):
        return self.pick_number

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if self.pk or self.pick_number:
            super().save(*args, **kwargs)
            return
        from django.db import IntegrityError
        for _ in range(5):
            with transaction.atomic():
                self.pick_number = _next_number(
                    PickList, self.tenant, 'pick_number', 'PK-',
                )
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.pick_number = ''
                    continue
        raise RuntimeError('Unable to generate unique pick number after retries.')


class PickListItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='pick_list_items',
    )
    pick_list = models.ForeignKey(
        PickList,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='pick_list_items',
    )
    bin_location = models.ForeignKey(
        'warehousing.Bin',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pick_list_items',
    )
    ordered_quantity = models.PositiveIntegerField(default=0)
    picked_quantity = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} — {self.picked_quantity}/{self.ordered_quantity}"


class PackingList(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PACKAGING_TYPE_CHOICES = [
        ('box', 'Box'),
        ('envelope', 'Envelope'),
        ('pallet', 'Pallet'),
        ('crate', 'Crate'),
        ('tube', 'Tube'),
        ('other', 'Other'),
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
        related_name='packing_lists',
    )
    packing_number = models.CharField(max_length=20, verbose_name='Packing Number')
    pick_list = models.ForeignKey(
        PickList,
        on_delete=models.CASCADE,
        related_name='packing_lists',
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='packing_lists',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    packaging_type = models.CharField(
        max_length=20, choices=PACKAGING_TYPE_CHOICES, default='box',
    )
    total_weight = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    length = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    width = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    packed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='packed_lists',
    )
    packed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'packing_number')

    def __str__(self):
        return self.packing_number

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if self.pk or self.packing_number:
            super().save(*args, **kwargs)
            return
        from django.db import IntegrityError
        for _ in range(5):
            with transaction.atomic():
                self.packing_number = _next_number(
                    PackingList, self.tenant, 'packing_number', 'PL-',
                )
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.packing_number = ''
                    continue
        raise RuntimeError('Unable to generate unique packing number after retries.')


class Shipment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('dispatched', 'Dispatched'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        'pending': ['dispatched', 'cancelled'],
        'dispatched': ['in_transit', 'delivered', 'cancelled'],
        'in_transit': ['delivered', 'cancelled'],
        'delivered': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='shipments',
    )
    shipment_number = models.CharField(max_length=20, verbose_name='Shipment Number')
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='shipments',
    )
    packing_list = models.ForeignKey(
        PackingList,
        on_delete=models.SET_NULL,
        related_name='shipments',
        null=True,
        blank=True,
    )
    carrier = models.ForeignKey(
        Carrier,
        on_delete=models.SET_NULL,
        related_name='shipments',
        null=True,
        blank=True,
    )
    service_level = models.CharField(max_length=100, blank=True, default='')
    tracking_number = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    shipped_date = models.DateTimeField(null=True, blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shipped_shipments',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'shipment_number')

    def __str__(self):
        return f"{self.shipment_number} — {self.sales_order.order_number}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if self.pk or self.shipment_number:
            super().save(*args, **kwargs)
            return
        from django.db import IntegrityError
        for _ in range(5):
            with transaction.atomic():
                self.shipment_number = _next_number(
                    Shipment, self.tenant, 'shipment_number', 'SH-',
                )
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.shipment_number = ''
                    continue
        raise RuntimeError('Unable to generate unique shipment number after retries.')


class ShipmentTracking(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='shipment_tracking_events',
    )
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='tracking_events',
    )
    status = models.CharField(max_length=100)
    location = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    event_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date']

    def __str__(self):
        return f"{self.shipment.shipment_number} — {self.status} @ {self.event_date}"
