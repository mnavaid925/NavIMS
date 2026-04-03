from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Vendor(models.Model):
    VENDOR_TYPE_CHOICES = [
        ('manufacturer', 'Manufacturer'),
        ('distributor', 'Distributor'),
        ('wholesaler', 'Wholesaler'),
        ('service_provider', 'Service Provider'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('blocked', 'Blocked'),
        ('pending', 'Pending'),
    ]

    PAYMENT_TERMS_CHOICES = [
        ('net_30', 'Net 30'),
        ('net_60', 'Net 60'),
        ('net_90', 'Net 90'),
        ('cod', 'Cash on Delivery'),
        ('prepaid', 'Prepaid'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='vendors',
    )
    company_name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    website = models.URLField(blank=True, default='')

    # Address
    address_line_1 = models.CharField(max_length=255, blank=True, default='')
    address_line_2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    tax_id = models.CharField(max_length=100, blank=True, default='', verbose_name='Tax ID')

    # Classification & Terms
    vendor_type = models.CharField(max_length=20, choices=VENDOR_TYPE_CHOICES, default='distributor')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='net_30')
    lead_time_days = models.PositiveIntegerField(default=0, help_text='Average lead time in days')
    minimum_order_quantity = models.PositiveIntegerField(default=1, verbose_name='MOQ')
    notes = models.TextField(blank=True, default='')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name']
        unique_together = ('tenant', 'company_name')

    def __str__(self):
        return self.company_name

    @property
    def average_performance_score(self):
        performances = self.performances.all()
        if not performances:
            return None
        total = sum(p.overall_score for p in performances)
        return round(total / len(performances), 1)


class VendorPerformance(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='vendor_performances',
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='performances',
    )
    review_date = models.DateField()
    delivery_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1-5 rating',
    )
    quality_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1-5 rating',
    )
    compliance_rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1-5 rating',
    )
    defect_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Defect rate percentage',
    )
    on_time_delivery_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='On-time delivery percentage',
    )
    notes = models.TextField(blank=True, default='')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendor_reviews',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-review_date']

    def __str__(self):
        return f"{self.vendor.company_name} - {self.review_date}"

    @property
    def overall_score(self):
        return round((self.delivery_rating + self.quality_rating + self.compliance_rating) / 3, 1)


class VendorContract(models.Model):
    CONTRACT_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
    ]

    PAYMENT_TERMS_CHOICES = Vendor.PAYMENT_TERMS_CHOICES

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='vendor_contracts',
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='contracts',
    )
    contract_number = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='net_30')
    lead_time_days = models.PositiveIntegerField(default=0)
    moq = models.PositiveIntegerField(default=1, verbose_name='Minimum Order Quantity')
    contract_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=CONTRACT_STATUS_CHOICES, default='draft')
    document = models.FileField(upload_to='vendors/contracts/', blank=True, null=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ('tenant', 'contract_number')

    def __str__(self):
        return f"{self.contract_number} - {self.title}"


class VendorCommunication(models.Model):
    COMM_TYPE_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone Call'),
        ('meeting', 'Meeting'),
        ('note', 'Note'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='vendor_communications',
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='communications',
    )
    communication_type = models.CharField(max_length=20, choices=COMM_TYPE_CHOICES, default='note')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    contact_person = models.CharField(max_length=255, blank=True, default='')
    communicated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendor_communications',
    )
    communication_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-communication_date']

    def __str__(self):
        return f"{self.subject} ({self.get_communication_type_display()})"
