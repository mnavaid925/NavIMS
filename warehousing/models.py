from django.conf import settings
from django.db import models


class Warehouse(models.Model):
    WAREHOUSE_TYPE_CHOICES = [
        ('distribution_center', 'Distribution Center'),
        ('manufacturing', 'Manufacturing'),
        ('retail', 'Retail'),
        ('cold_storage', 'Cold Storage'),
        ('cross_dock', 'Cross-Dock'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='warehouses',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, verbose_name='Warehouse Code')
    warehouse_type = models.CharField(
        max_length=20, choices=WAREHOUSE_TYPE_CHOICES, default='distribution_center',
    )
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    contact_person = models.CharField(max_length=255, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def zone_count(self):
        return self.zones.count()

    @property
    def bin_count(self):
        return Bin.objects.filter(zone__warehouse=self).count()

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def _generate_code(self):
        last = (
            Warehouse.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('code', flat=True)
            .first()
        )
        if last and last.startswith('WH-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'WH-{num:05d}'


class Zone(models.Model):
    ZONE_TYPE_CHOICES = [
        ('receiving', 'Receiving'),
        ('storage', 'Storage'),
        ('shipping', 'Shipping'),
        ('staging', 'Staging'),
        ('cross_dock', 'Cross-Dock'),
        ('quarantine', 'Quarantine'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='zones',
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='zones',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPE_CHOICES, default='storage')
    temperature_controlled = models.BooleanField(default=False)
    temperature_min = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Minimum temperature in Celsius',
    )
    temperature_max = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Maximum temperature in Celsius',
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['warehouse', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def aisle_count(self):
        return self.aisles.count()

    @property
    def bin_count(self):
        return self.bins.count()


class Aisle(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='aisles',
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.CASCADE,
        related_name='aisles',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['zone', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def rack_count(self):
        return self.racks.count()


class Rack(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='racks',
    )
    aisle = models.ForeignKey(
        Aisle,
        on_delete=models.CASCADE,
        related_name='racks',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    levels = models.PositiveIntegerField(default=1, help_text='Number of shelf levels')
    max_weight_capacity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Maximum weight capacity in kg',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['aisle', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def bin_count(self):
        return self.bins.count()


class Bin(models.Model):
    BIN_TYPE_CHOICES = [
        ('standard', 'Standard'),
        ('bulk', 'Bulk'),
        ('pick', 'Pick'),
        ('pallet', 'Pallet'),
        ('cold', 'Cold'),
        ('hazmat', 'Hazmat'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='bins',
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.CASCADE,
        related_name='bins',
    )
    rack = models.ForeignKey(
        Rack,
        on_delete=models.CASCADE,
        related_name='bins',
        null=True,
        blank=True,
        help_text='Leave empty for floor bins',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    bin_type = models.CharField(max_length=20, choices=BIN_TYPE_CHOICES, default='standard')
    max_weight = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Maximum weight capacity in kg',
    )
    max_volume = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Maximum volume capacity in cubic meters',
    )
    max_quantity = models.PositiveIntegerField(
        default=0, help_text='Maximum number of items',
    )
    current_weight = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_volume = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_occupied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['zone', 'code']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'bins'

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def available_weight(self):
        if self.max_weight <= 0:
            return 0
        return max(self.max_weight - self.current_weight, 0)

    @property
    def available_volume(self):
        if self.max_volume <= 0:
            return 0
        return max(self.max_volume - self.current_volume, 0)

    @property
    def available_quantity(self):
        if self.max_quantity <= 0:
            return 0
        return max(self.max_quantity - self.current_quantity, 0)

    @property
    def utilization_percentage(self):
        percentages = []
        if self.max_weight > 0:
            percentages.append(float(self.current_weight) / float(self.max_weight) * 100)
        if self.max_volume > 0:
            percentages.append(float(self.current_volume) / float(self.max_volume) * 100)
        if self.max_quantity > 0:
            percentages.append(float(self.current_quantity) / float(self.max_quantity) * 100)
        if not percentages:
            return 0
        return round(sum(percentages) / len(percentages), 1)

    @property
    def location_path(self):
        parts = [self.zone.warehouse.code, self.zone.code]
        if self.rack:
            parts.extend([self.rack.aisle.code, self.rack.code])
        parts.append(self.code)
        return ' > '.join(parts)


class CrossDockOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('at_dock', 'At Dock'),
        ('processing', 'Processing'),
        ('dispatched', 'Dispatched'),
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
        'pending': ['in_transit', 'cancelled'],
        'in_transit': ['at_dock', 'cancelled'],
        'at_dock': ['processing', 'cancelled'],
        'processing': ['dispatched', 'cancelled'],
        'dispatched': ['completed'],
        'completed': [],
        'cancelled': ['pending'],
    }

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='cross_dock_orders',
    )
    order_number = models.CharField(max_length=20, verbose_name='CD Number')
    source = models.CharField(max_length=255, help_text='Source / origin of goods')
    destination = models.CharField(max_length=255, help_text='Destination for goods')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    scheduled_arrival = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    scheduled_departure = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    dock_door = models.CharField(max_length=50, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_cross_dock_orders',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'order_number')

    def __str__(self):
        return f"{self.order_number} - {self.source} to {self.destination}"

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def _generate_order_number(self):
        last = (
            CrossDockOrder.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('order_number', flat=True)
            .first()
        )
        if last and last.startswith('CD-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'CD-{num:05d}'


class CrossDockItem(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='cross_dock_items',
    )
    cross_dock_order = models.ForeignKey(
        CrossDockOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cross_dock_items',
    )
    description = models.CharField(max_length=500, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    weight = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    volume = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        name = self.description or (self.product.name if self.product else 'Item')
        return f"{name} x {self.quantity}"
