"""Accounting & Financial Integration models (Module 19).

Integration staging layer + lightweight double-entry GL. Four concerns:

1. **Accounts Payable (AP)** — `APBill` staged from `receiving.VendorInvoice` /
   `purchase_orders.PurchaseOrder` / `receiving.GoodsReceiptNote`.
2. **Accounts Receivable (AR)** — `ARInvoice` staged from `orders.Shipment` /
   `orders.SalesOrder`.
3. **Journal Entry Automation** — `JournalEntry` + `JournalLine` posted from
   `inventory.StockAdjustment`, `quality_control.ScrapWriteOff`, AP/AR, or
   manual entries, against a per-tenant `ChartOfAccount`.
4. **Tax Management** — `TaxJurisdiction` × `TaxRule` lookup keyed on
   `catalog.Product.tax_category`.

`sync_status` on APBill/ARInvoice/JournalEntry is the hand-off field for
Module 20 (Third-Party Integrations) — when an external accounting adapter
pushes a record it flips `pending → queued → synced` (or `failed`).

Patterns reused from existing modules:
- `_save_with_number_retry()` (stocktaking, reporting, alerts_notifications)
- `StateMachineMixin` from `core.state_machine`
- Soft-delete via `deleted_at` (returns, quality_control)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import IntegrityError, models, transaction

from core.state_machine import StateMachineMixin


ZERO = Decimal('0')

_NUMBER_RETRY_ATTEMPTS = 5


def _save_with_number_retry(instance, number_field, save_super):
    """Race-safe auto-number retry. See stocktaking/models.py for rationale."""
    user_supplied_number = bool(getattr(instance, number_field))
    last_error = None
    for _ in range(_NUMBER_RETRY_ATTEMPTS):
        try:
            with transaction.atomic():
                save_super()
            return
        except IntegrityError as exc:
            last_error = exc
            if user_supplied_number or instance.pk is not None:
                raise
            setattr(instance, number_field, '')
    raise last_error  # type: ignore[misc]


def _next_sequence_number(model, tenant, field, prefix, width=5):
    """Compute the next N for `<prefix>-NNNNN` per-tenant sequence."""
    last = (
        model.objects.filter(tenant=tenant)
        .order_by('-id').values_list(field, flat=True).first()
    )
    if last and last.startswith(f'{prefix}-'):
        try:
            num = int(last.split('-', 1)[1]) + 1
        except (IndexError, ValueError):
            num = 1
    else:
        num = 1
    return f'{prefix}-{num:0{width}d}'


SYNC_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('queued', 'Queued'),
    ('synced', 'Synced'),
    ('failed', 'Failed'),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. ChartOfAccount — GL master
# ═══════════════════════════════════════════════════════════════════════════

class ChartOfAccount(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='chart_of_accounts',
    )
    code = models.CharField(max_length=20, verbose_name='Account Code')
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children',
    )
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')
        verbose_name = 'Chart of Account'
        verbose_name_plural = 'Chart of Accounts'

    def __str__(self):
        return f'{self.code} — {self.name}'


# ═══════════════════════════════════════════════════════════════════════════
# 2. FiscalPeriod — posting windows
# ═══════════════════════════════════════════════════════════════════════════

class FiscalPeriod(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    VALID_TRANSITIONS = {
        'open': ['closed'],
        'closed': ['open'],  # reopen is allowed (non-ERP policy)
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='fiscal_periods',
    )
    period_number = models.CharField(max_length=20, verbose_name='Period #')
    name = models.CharField(max_length=100, help_text='e.g., "FY2026-Q1", "Apr 2026"')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ('tenant', 'period_number')

    def __str__(self):
        return f'{self.period_number} — {self.name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.period_number:
                self.period_number = _next_sequence_number(
                    FiscalPeriod, self.tenant, 'period_number', 'FP',
                )
            super(FiscalPeriod, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'period_number', _do)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Customer — AR customer master
# ═══════════════════════════════════════════════════════════════════════════

class Customer(models.Model):
    PAYMENT_TERMS_CHOICES = [
        ('net_15', 'Net 15'),
        ('net_30', 'Net 30'),
        ('net_45', 'Net 45'),
        ('net_60', 'Net 60'),
        ('net_90', 'Net 90'),
        ('cod', 'Cash on Delivery'),
        ('prepaid', 'Prepaid'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='ar_customers',
    )
    customer_number = models.CharField(max_length=20, verbose_name='Customer #')
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')

    billing_address = models.TextField(blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')

    tax_id = models.CharField(max_length=100, blank=True, default='',
                              verbose_name='Tax ID (GST/VAT)')
    payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES,
                                     default='net_30')
    default_currency = models.CharField(max_length=10, default='USD')

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['company_name']
        unique_together = ('tenant', 'customer_number')

    def __str__(self):
        return f'{self.customer_number} — {self.company_name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.customer_number:
                self.customer_number = _next_sequence_number(
                    Customer, self.tenant, 'customer_number', 'CUST',
                )
            super(Customer, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'customer_number', _do)


# ═══════════════════════════════════════════════════════════════════════════
# 4. TaxJurisdiction — country/state
# ═══════════════════════════════════════════════════════════════════════════

class TaxJurisdiction(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='tax_jurisdictions',
    )
    code = models.CharField(max_length=20,
                            help_text='e.g., "US", "US-CA", "IN", "GB", "EU"')
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')
        verbose_name = 'Tax Jurisdiction'

    def __str__(self):
        return f'{self.code} — {self.name}'


# ═══════════════════════════════════════════════════════════════════════════
# 5. TaxRule — product-category × jurisdiction → rate
# ═══════════════════════════════════════════════════════════════════════════

class TaxRule(models.Model):
    TAX_CATEGORY_CHOICES = [
        ('standard', 'Standard'),
        ('reduced', 'Reduced'),
        ('zero', 'Zero-rated'),
        ('exempt', 'Exempt'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='tax_rules',
    )
    rule_number = models.CharField(max_length=20, verbose_name='Rule #')
    jurisdiction = models.ForeignKey(
        TaxJurisdiction, on_delete=models.CASCADE, related_name='rules',
    )
    tax_category = models.CharField(max_length=20, choices=TAX_CATEGORY_CHOICES,
                                    default='standard')
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal('100'))],
        help_text='Rate as percentage (e.g. 10.00 for 10%).',
    )
    effective_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date', 'jurisdiction__code', 'tax_category']
        unique_together = ('tenant', 'rule_number')

    def __str__(self):
        return (f'{self.rule_number} — {self.jurisdiction.code} / '
                f'{self.get_tax_category_display()} @ {self.tax_rate}%')

    def save(self, *args, **kwargs):
        def _do():
            if not self.rule_number:
                self.rule_number = _next_sequence_number(
                    TaxRule, self.tenant, 'rule_number', 'TRL',
                )
            super(TaxRule, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'rule_number', _do)


# ═══════════════════════════════════════════════════════════════════════════
# 6. APBill — Accounts Payable staged for external sync
# ═══════════════════════════════════════════════════════════════════════════

class APBill(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('posted', 'Posted'),
        ('paid', 'Paid'),
        ('voided', 'Voided'),
    ]
    VALID_TRANSITIONS = {
        'draft': ['pending_approval', 'voided'],
        'pending_approval': ['approved', 'draft', 'voided'],
        'approved': ['posted', 'voided'],
        'posted': ['paid', 'voided'],
        'paid': [],
        'voided': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='ap_bills',
    )
    bill_number = models.CharField(max_length=20, verbose_name='Bill #')

    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.PROTECT, related_name='ap_bills',
    )
    source_invoice = models.ForeignKey(
        'receiving.VendorInvoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ap_bills',
    )
    source_po = models.ForeignKey(
        'purchase_orders.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ap_bills',
    )
    source_grn = models.ForeignKey(
        'receiving.GoodsReceiptNote', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ap_bills',
    )

    bill_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   validators=[MinValueValidator(ZERO)])
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     validators=[MinValueValidator(ZERO)])
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                       validators=[MinValueValidator(ZERO)])
    currency = models.CharField(max_length=10, default='USD')
    payment_terms = models.CharField(max_length=20, blank=True, default='net_30')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sync_status = models.CharField(max_length=10, choices=SYNC_STATUS_CHOICES,
                                   default='pending')
    sync_error = models.TextField(blank=True, default='')

    journal_entry = models.ForeignKey(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ap_bills',
    )

    description = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ap_bills_created',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-bill_date', '-id']
        unique_together = ('tenant', 'bill_number')
        indexes = [models.Index(fields=['tenant', 'status'])]

    def __str__(self):
        return f'{self.bill_number} — {self.vendor.company_name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.bill_number:
                self.bill_number = _next_sequence_number(
                    APBill, self.tenant, 'bill_number', 'BIL',
                )
            super(APBill, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'bill_number', _do)

    def recompute_totals(self):
        lines = list(self.lines.all())
        self.subtotal = sum((ln.line_total for ln in lines), ZERO)
        self.tax_amount = sum((ln.tax_amount for ln in lines), ZERO)
        self.total_amount = self.subtotal + self.tax_amount


class APBillLine(models.Model):
    bill = models.ForeignKey(APBill, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    gl_account = models.ForeignKey(
        ChartOfAccount, on_delete=models.PROTECT, related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1,
                                   validators=[MinValueValidator(ZERO)])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     validators=[MinValueValidator(ZERO)])
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal('100'))],
    )
    line_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['line_order', 'id']

    def __str__(self):
        return f'Line for {self.bill.bill_number}'

    @property
    def line_total(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def tax_amount(self):
        return (self.line_total * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))


# ═══════════════════════════════════════════════════════════════════════════
# 7. ARInvoice — Accounts Receivable staged for external sync
# ═══════════════════════════════════════════════════════════════════════════

class ARInvoice(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('voided', 'Voided'),
    ]
    VALID_TRANSITIONS = {
        'draft': ['sent', 'voided'],
        'sent': ['paid', 'overdue', 'voided'],
        'overdue': ['paid', 'voided'],
        'paid': [],
        'voided': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='ar_invoices',
    )
    invoice_number = models.CharField(max_length=20, verbose_name='Invoice #')

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='invoices',
    )
    source_so = models.ForeignKey(
        'orders.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ar_invoices',
    )
    source_shipment = models.ForeignKey(
        'orders.Shipment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ar_invoices',
    )

    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   validators=[MinValueValidator(ZERO)])
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     validators=[MinValueValidator(ZERO)])
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                       validators=[MinValueValidator(ZERO)])
    currency = models.CharField(max_length=10, default='USD')
    payment_terms = models.CharField(max_length=20, blank=True, default='net_30')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sync_status = models.CharField(max_length=10, choices=SYNC_STATUS_CHOICES,
                                   default='pending')
    sync_error = models.TextField(blank=True, default='')

    journal_entry = models.ForeignKey(
        'accounting.JournalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ar_invoices',
    )

    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ar_invoices_created',
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-invoice_date', '-id']
        unique_together = ('tenant', 'invoice_number')
        indexes = [models.Index(fields=['tenant', 'status'])]

    def __str__(self):
        return f'{self.invoice_number} — {self.customer.company_name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.invoice_number:
                self.invoice_number = _next_sequence_number(
                    ARInvoice, self.tenant, 'invoice_number', 'ARI',
                )
            super(ARInvoice, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'invoice_number', _do)

    def recompute_totals(self):
        lines = list(self.lines.all())
        self.subtotal = sum((ln.line_total for ln in lines), ZERO)
        self.tax_amount = sum((ln.tax_amount for ln in lines), ZERO)
        self.total_amount = self.subtotal + self.tax_amount


class ARInvoiceLine(models.Model):
    invoice = models.ForeignKey(ARInvoice, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    gl_account = models.ForeignKey(
        ChartOfAccount, on_delete=models.PROTECT, related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1,
                                   validators=[MinValueValidator(ZERO)])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     validators=[MinValueValidator(ZERO)])
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal('100'))],
    )
    line_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['line_order', 'id']

    def __str__(self):
        return f'Line for {self.invoice.invoice_number}'

    @property
    def line_total(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def tax_amount(self):
        return (self.line_total * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))


# ═══════════════════════════════════════════════════════════════════════════
# 8. JournalEntry — lightweight double-entry GL posting
# ═══════════════════════════════════════════════════════════════════════════

class JournalEntry(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('voided', 'Voided'),
    ]
    VALID_TRANSITIONS = {
        'draft': ['posted', 'voided'],
        'posted': ['voided'],
        'voided': [],
    }

    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('ap_bill', 'AP Bill'),
        ('ar_invoice', 'AR Invoice'),
        ('stock_adjustment', 'Stock Adjustment'),
        ('scrap_writeoff', 'Scrap Write-Off'),
        ('valuation', 'Inventory Valuation'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='journal_entries',
    )
    entry_number = models.CharField(max_length=20, verbose_name='JE #')
    entry_date = models.DateField()
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, related_name='journal_entries',
    )

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES,
                                   default='manual')
    source_reference = models.CharField(max_length=40, blank=True, default='',
                                        help_text='Denormalized source number, e.g. "BIL-00001".')
    source_id = models.CharField(max_length=40, blank=True, default='',
                                 help_text='Source model pk as string.')

    description = models.TextField(blank=True, default='')
    total_debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sync_status = models.CharField(max_length=10, choices=SYNC_STATUS_CHOICES,
                                   default='pending')
    sync_error = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal_entries_created',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal_entries_posted',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-entry_date', '-id']
        unique_together = ('tenant', 'entry_number')
        verbose_name_plural = 'Journal Entries'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'source_type', 'source_id']),
        ]

    def __str__(self):
        return f'{self.entry_number} — {self.entry_date}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.entry_number:
                self.entry_number = _next_sequence_number(
                    JournalEntry, self.tenant, 'entry_number', 'JE',
                )
            super(JournalEntry, self).save(*args, **kwargs)
        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'entry_number', _do)

    def recompute_totals(self):
        lines = list(self.lines.all())
        self.total_debit = sum((ln.debit_amount for ln in lines), ZERO)
        self.total_credit = sum((ln.credit_amount for ln in lines), ZERO)

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit and self.total_debit > 0


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE,
                              related_name='lines')
    gl_account = models.ForeignKey(
        ChartOfAccount, on_delete=models.PROTECT, related_name='+',
    )
    description = models.CharField(max_length=255, blank=True, default='')
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                       validators=[MinValueValidator(ZERO)])
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        validators=[MinValueValidator(ZERO)])
    line_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['line_order', 'id']

    def __str__(self):
        return f'Line for {self.entry.entry_number}'
