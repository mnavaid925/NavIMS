from django.db import models


class PricingPlan(models.Model):
    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default='')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    billing_cycle = models.CharField(
        max_length=10,
        choices=BILLING_CYCLE_CHOICES,
        default='monthly',
    )
    max_users = models.PositiveIntegerField(default=5)
    max_warehouses = models.PositiveIntegerField(default=1)
    max_products = models.PositiveIntegerField(default=100)
    features = models.TextField(
        blank=True,
        default='',
        help_text='JSON-like feature list',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} ({self.get_billing_cycle_display()})"


class TenantCustomization(models.Model):
    tenant = models.OneToOneField(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='customization',
    )
    logo = models.ImageField(upload_to='tenants/customization/logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='tenants/customization/favicons/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#3b82f6')
    secondary_color = models.CharField(max_length=7, default='#1e40af')
    company_address = models.TextField(blank=True, default='')
    company_phone = models.CharField(max_length=20, blank=True, default='')
    company_email = models.EmailField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tenant__name']

    def __str__(self):
        return f"Customization for {self.tenant.name}"


class BillingHistory(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='billing_history',
    )
    subscription = models.ForeignKey(
        'core.Subscription',
        on_delete=models.CASCADE,
        related_name='billing_history',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, default='')
    payment_method = models.CharField(max_length=50, blank=True, default='')
    payment_status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
    )
    transaction_id = models.CharField(max_length=255, blank=True, default='')
    billing_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-billing_date']
        verbose_name_plural = 'Billing histories'

    def __str__(self):
        return f"{self.tenant.name} - {self.amount} ({self.get_payment_status_display()})"
