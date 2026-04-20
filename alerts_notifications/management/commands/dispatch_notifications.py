"""Email-dispatch undelivered alerts per active NotificationRule.

For every Alert (status in new/acknowledged) without a NotificationDelivery row
yet, resolve all active NotificationRule rows that match by alert_type + severity
threshold, expand recipient_users, and create a NotificationDelivery per
(alert, recipient, channel) pair. Idempotent via the unique_together.

Email channel uses django.core.mail.send_mail. Console backend prints payloads
in development; SMTP is honoured in production via EMAIL_BACKEND env var.
"""
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone

from core.models import Tenant

from alerts_notifications.models import (
    SEVERITY_CHOICES,
    Alert,
    NotificationDelivery,
    NotificationRule,
)


SEVERITY_RANK = {sev: rank for rank, (sev, _label) in enumerate(SEVERITY_CHOICES)}


def _meets_min_severity(alert_severity, rule_min):
    return SEVERITY_RANK.get(alert_severity, 0) >= SEVERITY_RANK.get(rule_min, 0)


class Command(BaseCommand):
    help = 'Dispatch pending notifications for open alerts via email / inbox.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Tenant slug (default: all active tenants)')
        parser.add_argument('--dry-run', action='store_true', help='Print dispatch plan without sending.')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])

        total_dispatched = total_failed = total_skipped = 0

        for tenant in tenants:
            self.stdout.write(f'[{tenant.name}] Dispatching notifications…')
            alerts = Alert.objects.filter(
                tenant=tenant,
                status__in=['new', 'acknowledged'],
                deleted_at__isnull=True,
            ).select_related('product', 'warehouse')

            active_rules = list(
                NotificationRule.objects.filter(
                    tenant=tenant, is_active=True, deleted_at__isnull=True,
                ).prefetch_related('recipient_users')
            )
            if not active_rules:
                self.stdout.write('  No active notification rules — nothing to dispatch.')
                continue

            for alert in alerts:
                matching = [
                    r for r in active_rules
                    if r.alert_type == alert.alert_type
                    and _meets_min_severity(alert.severity, r.min_severity)
                ]
                for rule in matching:
                    for user in rule.recipient_users.all():
                        channels = []
                        if rule.notify_email:
                            channels.append('email')
                        if rule.notify_inbox:
                            channels.append('inbox')
                        for channel in channels:
                            if NotificationDelivery.objects.filter(
                                alert=alert, recipient=user, channel=channel,
                            ).exists():
                                total_skipped += 1
                                continue
                            if options['dry_run']:
                                self.stdout.write(
                                    f'  [dry-run] would dispatch alert {alert.alert_number} '
                                    f'→ {user.username} via {channel} (rule {rule.code})'
                                )
                                continue
                            try:
                                delivery = NotificationDelivery.objects.create(
                                    tenant=tenant,
                                    alert=alert,
                                    rule=rule,
                                    recipient=user,
                                    channel=channel,
                                    recipient_email=user.email or '',
                                    status='pending',
                                )
                            except IntegrityError:
                                total_skipped += 1
                                continue

                            if channel == 'email':
                                if not user.email:
                                    delivery.status = 'failed'
                                    delivery.error_message = 'Recipient has no email address.'
                                    delivery.save(update_fields=['status', 'error_message'])
                                    total_failed += 1
                                    continue
                                try:
                                    subject = f'[{tenant.name}] {alert.get_severity_display()}: {alert.title}'
                                    body = (
                                        f'Alert: {alert.alert_number}\n'
                                        f'Type: {alert.get_alert_type_display()}\n'
                                        f'Severity: {alert.get_severity_display()}\n'
                                        f'Triggered: {alert.triggered_at.isoformat()}\n\n'
                                        f'{alert.message}\n\n'
                                        f'Rule: {rule.code} — {rule.name}\n'
                                    )
                                    send_mail(
                                        subject, body,
                                        settings.DEFAULT_FROM_EMAIL,
                                        [user.email],
                                        fail_silently=False,
                                    )
                                    delivery.status = 'sent'
                                    delivery.sent_at = timezone.now()
                                    delivery.save(update_fields=['status', 'sent_at'])
                                    total_dispatched += 1
                                except (smtplib.SMTPException, OSError, ConnectionError) as exc:
                                    # D-07: narrowed from bare Exception — programming
                                    # bugs now surface instead of being logged as 'failed'.
                                    delivery.status = 'failed'
                                    delivery.error_message = str(exc)[:2000]
                                    delivery.save(update_fields=['status', 'error_message'])
                                    total_failed += 1
                            else:  # inbox
                                delivery.status = 'sent'
                                delivery.sent_at = timezone.now()
                                delivery.save(update_fields=['status', 'sent_at'])
                                total_dispatched += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Dispatch complete. Sent: {total_dispatched}, '
            f'failed: {total_failed}, skipped (already-sent): {total_skipped}.'
        ))
