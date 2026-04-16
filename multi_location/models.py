from decimal import Decimal

from django.conf import settings
from django.db import models


# ──────────────────────────────────────────────
# Sub-module 1: Location Hierarchy
# ──────────────────────────────────────────────

class Location(models.Model):
    LOCATION_TYPE_CHOICES = [
        ('company', 'Parent Company'),
        ('regional_dc', 'Regional Distribution Center'),
        ('distribution_center', 'Distribution Center'),
        ('retail_store', 'Retail Store'),
        ('warehouse', 'Warehouse'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='locations',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='children',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, verbose_name='Location Code')
    location_type = models.CharField(
        max_length=30, choices=LOCATION_TYPE_CHOICES, default='retail_store',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='locations',
        help_text='Optional link to a physical warehouse for stock roll-up.',
    )
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    manager_name = models.CharField(max_length=255, blank=True, default='')
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
        return f"{self.code} - {self.name}"

    @property
    def children_count(self):
        return self.children.count()

    @property
    def full_path(self):
        parts = [self.name]
        node = self.parent
        guard = 0
        while node and guard < 10:
            parts.append(node.name)
            node = node.parent
            guard += 1
        return ' > '.join(reversed(parts))

    def get_descendant_ids(self, include_self=False):
        ids = [self.pk] if include_self else []
        stack = list(self.children.values_list('pk', flat=True))
        while stack:
            current_id = stack.pop()
            ids.append(current_id)
            stack.extend(
                Location.objects.filter(parent_id=current_id).values_list('pk', flat=True)
            )
        return ids

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def _generate_code(self):
        last = (
            Location.objects.filter(tenant=self.tenant)
            .order_by('-id')
            .values_list('code', flat=True)
            .first()
        )
        if last and last.startswith('LOC-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'LOC-{num:05d}'


# ──────────────────────────────────────────────
# Sub-module 3: Location-Specific Rules
# ──────────────────────────────────────────────

class LocationPricingRule(models.Model):
    RULE_TYPE_CHOICES = [
        ('markup_pct', 'Markup %'),
        ('markdown_pct', 'Markdown %'),
        ('fixed_adjustment', 'Fixed Price Adjustment'),
        ('override_price', 'Override Retail Price'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='location_pricing_rules',
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='pricing_rules',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='location_pricing_rules',
    )
    category = models.ForeignKey(
        'catalog.Category',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='location_pricing_rules',
    )
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES, default='markup_pct')
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    priority = models.PositiveIntegerField(default=1, help_text='Lower number = higher priority')
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['location', 'priority']

    def __str__(self):
        scope = self.product.name if self.product else (self.category.name if self.category else 'All')
        return f"{self.location.code} / {scope} / {self.get_rule_type_display()}"

    @property
    def scope_display(self):
        if self.product:
            return f"Product: {self.product.name}"
        if self.category:
            return f"Category: {self.category.name}"
        return 'All Products'


class LocationTransferRule(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='location_transfer_rules',
    )
    source_location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='outbound_transfer_rules',
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='inbound_transfer_rules',
    )
    allowed = models.BooleanField(default=True)
    max_transfer_qty = models.PositiveIntegerField(
        default=0, help_text='0 = unlimited',
    )
    lead_time_days = models.PositiveIntegerField(default=0)
    requires_approval = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=1, help_text='Lower number = higher priority')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_location', 'priority']
        unique_together = ('tenant', 'source_location', 'destination_location')

    def __str__(self):
        arrow = '→' if self.allowed else '⊘'
        return f"{self.source_location.code} {arrow} {self.destination_location.code}"


class LocationSafetyStockRule(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='location_safety_stock_rules',
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='safety_stock_rules',
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='location_safety_stock_rules',
    )
    safety_stock_qty = models.PositiveIntegerField(default=0)
    reorder_point = models.PositiveIntegerField(default=0)
    max_stock_qty = models.PositiveIntegerField(
        default=0, help_text='0 = no ceiling',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['location', 'product']
        unique_together = ('tenant', 'location', 'product')

    def __str__(self):
        return f"{self.location.code} / {self.product.sku} — SS:{self.safety_stock_qty}"
