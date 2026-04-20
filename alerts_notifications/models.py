from django.conf import settings
from django.db import IntegrityError, models, transaction

from core.state_machine import StateMachineMixin


_NUMBER_RETRY_ATTEMPTS = 5


def _save_with_number_retry(instance, number_field, save_super):
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


ALERT_TYPE_CHOICES = [
    ('low_stock', 'Low Stock'),
    ('out_of_stock', 'Out of Stock'),
    ('overstock', 'Overstock'),
    ('expiry_approaching', 'Expiry Approaching'),
    ('expired', 'Expired'),
    ('po_approval_pending', 'PO Approval Pending'),
    ('shipment_delayed', 'Shipment Delayed'),
    ('import_failed', 'Import Failed'),
]

SEVERITY_CHOICES = [
    ('info', 'Info'),
    ('warning', 'Warning'),
    ('critical', 'Critical'),
]


# ═══════════════════════════════════════════════════════════════════════════
# Alert — the canonical alert record (all 4 submodules write here)
# ═══════════════════════════════════════════════════════════════════════════

class Alert(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    VALID_TRANSITIONS = {
        'new': ['acknowledged', 'dismissed'],
        'acknowledged': ['resolved', 'dismissed'],
        'resolved': [],
        'dismissed': [],
    }

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='alerts',
    )
    alert_number = models.CharField(max_length=20)
    dedup_key = models.CharField(max_length=255, db_index=True)

    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='warning')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')

    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default='')

    # Nullable polymorphic source — up to one of these is populated per alert.
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )
    warehouse = models.ForeignKey(
        'warehousing.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )
    stock_level = models.ForeignKey(
        'inventory.StockLevel', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )
    lot_batch = models.ForeignKey(
        'lot_tracking.LotBatch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )
    purchase_order = models.ForeignKey(
        'purchase_orders.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )
    shipment = models.ForeignKey(
        'orders.Shipment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts',
    )

    threshold_value = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    current_value = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='acknowledged_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']
        unique_together = (
            ('tenant', 'alert_number'),
            ('tenant', 'dedup_key'),
        )

    def __str__(self):
        return f'{self.alert_number} — {self.title}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.alert_number:
                self.alert_number = self._generate_number()
            super(Alert, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'alert_number', _do)

    def _generate_number(self):
        last = (
            Alert.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('alert_number', flat=True).first()
        )
        if last and last.startswith('ALN-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'ALN-{num:05d}'


# ═══════════════════════════════════════════════════════════════════════════
# NotificationRule — config for who gets alerted, over which channel, when
# ═══════════════════════════════════════════════════════════════════════════

class NotificationRule(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='notification_rules',
    )
    code = models.CharField(max_length=20, verbose_name='Rule Code')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')

    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    min_severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='warning')

    notify_email = models.BooleanField(default=True)
    notify_inbox = models.BooleanField(default=True)

    recipient_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='notification_rules',
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_notification_rules',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['alert_type', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        def _do():
            if not self.code:
                self.code = self._generate_code()
            super(NotificationRule, self).save(*args, **kwargs)

        if self.pk is not None:
            _do()
        else:
            _save_with_number_retry(self, 'code', _do)

    def _generate_code(self):
        last = (
            NotificationRule.objects.filter(tenant=self.tenant)
            .order_by('-id').values_list('code', flat=True).first()
        )
        if last and last.startswith('NR-'):
            try:
                num = int(last.split('-')[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1
        return f'NR-{num:05d}'


# ═══════════════════════════════════════════════════════════════════════════
# NotificationDelivery — audit log of outbound notifications
# ═══════════════════════════════════════════════════════════════════════════

class NotificationDelivery(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('inbox', 'In-App Inbox'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE, related_name='notification_deliveries',
    )
    alert = models.ForeignKey(
        Alert, on_delete=models.CASCADE, related_name='deliveries',
    )
    rule = models.ForeignKey(
        NotificationRule, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deliveries',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='notification_deliveries',
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    recipient_email = models.CharField(max_length=254, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('alert', 'recipient', 'channel')

    def __str__(self):
        return f'Delivery of {self.alert.alert_number} to {self.recipient_email or self.recipient_id} via {self.channel}'
