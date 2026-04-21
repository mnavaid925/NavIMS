from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


ZERO = Decimal('0')


class Category(models.Model):
    LEVEL_CHOICES = [
        ('department', 'Department'),
        ('category', 'Category'),
        ('subcategory', 'Sub-category'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='department')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'slug')
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Regenerate slug whenever the name changes
        self.slug = slugify(self.name)
        # Auto-compute level based on parent depth
        if self.parent is None:
            self.level = 'department'
        elif self.parent.level == 'department':
            self.level = 'category'
        else:
            self.level = 'subcategory'
        super().save(*args, **kwargs)

    @property
    def full_path(self):
        parts = [self.name]
        current = self.parent
        while current:
            parts.insert(0, current.name)
            current = current.parent
        return ' > '.join(parts)


class Product(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('discontinued', 'Discontinued'),
    ]

    TAX_CATEGORY_CHOICES = [
        ('standard', 'Standard'),
        ('reduced', 'Reduced'),
        ('zero', 'Zero-rated'),
        ('exempt', 'Exempt'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='products',
    )
    sku = models.CharField(max_length=100, verbose_name='SKU')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Pricing & Costing
    purchase_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO)],
    )
    wholesale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO)],
    )
    retail_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO)],
    )
    markup_percentage = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO)],
    )

    # Physical attributes
    weight = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Weight in kg',
        validators=[MinValueValidator(ZERO)],
    )
    length = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Length in cm',
        validators=[MinValueValidator(ZERO)],
    )
    width = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Width in cm',
        validators=[MinValueValidator(ZERO)],
    )
    height = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Height in cm',
        validators=[MinValueValidator(ZERO)],
    )

    # Metadata
    barcode = models.CharField(max_length=100, blank=True, default='')
    brand = models.CharField(max_length=255, blank=True, default='')
    manufacturer = models.CharField(max_length=255, blank=True, default='')

    # Tax classification (Module 19)
    tax_category = models.CharField(
        max_length=20, choices=TAX_CATEGORY_CHOICES, default='standard',
        help_text='Tax category used by the accounting module to resolve jurisdictional tax rate.',
    )
    hsn_code = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='HSN/SAC Code',
        help_text='Harmonized System Nomenclature code (India GST, EU combined nomenclature).',
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'sku')

    def __str__(self):
        return f"{self.sku} - {self.name}"

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()


class ProductAttribute(models.Model):
    ATTR_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('boolean', 'Yes/No'),
        ('select', 'Selection'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='product_attributes',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='attributes',
    )
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=500)
    attr_type = models.CharField(max_length=20, choices=ATTR_TYPE_CHOICES, default='text')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.name}: {self.value}"


class ProductImage(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='product_images',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='products/images/')
    caption = models.CharField(max_length=255, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'sort_order']

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            # Clear is_primary on sibling images
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('safety_sheet', 'Safety Sheet'),
        ('datasheet', 'Datasheet'),
        ('warranty', 'Warranty'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='product_documents',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='products/documents/')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='other')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title
