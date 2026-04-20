"""dispatch_notifications tests — send, idempotent, failed-email, narrow except."""
import pytest
from django.core import mail
from django.core.management import call_command

from alerts_notifications.models import Alert, NotificationDelivery, NotificationRule


@pytest.mark.django_db
def test_dispatch_sends_email_and_inbox(tenant, tenant_admin, rule):
    Alert.objects.create(
        tenant=tenant, alert_type='low_stock', severity='warning',
        title='Probe', dedup_key='t:1',
    )
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    assert NotificationDelivery.objects.filter(status='sent').count() == 2  # email + inbox
    assert len(mail.outbox) == 1
    assert 'Probe' in mail.outbox[0].subject


@pytest.mark.django_db
def test_dispatch_idempotent(tenant, tenant_admin, rule):
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    before = NotificationDelivery.objects.count()
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    assert NotificationDelivery.objects.count() == before


@pytest.mark.django_db
def test_dispatch_failed_when_recipient_has_no_email(tenant):
    from core.models import User
    u = User.objects.create_user(
        username='noemail', password='x',
        tenant=tenant, is_tenant_admin=True, email='',
    )
    r = NotificationRule.objects.create(
        tenant=tenant, name='R', alert_type='low_stock', min_severity='warning',
        notify_email=True, notify_inbox=False, is_active=True,
    )
    r.recipient_users.add(u)
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    d = NotificationDelivery.objects.get()
    assert d.status == 'failed'
    assert 'no email' in d.error_message.lower()


@pytest.mark.django_db
def test_dispatch_skips_inactive_rule(tenant, tenant_admin):
    r = NotificationRule.objects.create(
        tenant=tenant, name='R', alert_type='low_stock', min_severity='warning',
        notify_email=True, is_active=False,
    )
    r.recipient_users.add(tenant_admin)
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    assert NotificationDelivery.objects.count() == 0


@pytest.mark.django_db
def test_dispatch_respects_min_severity(tenant, tenant_admin):
    r = NotificationRule.objects.create(
        tenant=tenant, name='R', alert_type='low_stock', min_severity='critical',
        notify_email=False, notify_inbox=True, is_active=True,  # single channel for easy counting
    )
    r.recipient_users.add(tenant_admin)
    # Only warning-level alert → should NOT match critical-min rule
    Alert.objects.create(
        tenant=tenant, alert_type='low_stock', severity='warning',
        title='x', dedup_key='t:1',
    )
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    assert NotificationDelivery.objects.count() == 0

    # Now a critical-level alert → should match (1 channel × 1 recipient = 1 delivery)
    Alert.objects.create(
        tenant=tenant, alert_type='low_stock', severity='critical',
        title='y', dedup_key='t:2',
    )
    call_command('dispatch_notifications', '--tenant', tenant.slug)
    assert NotificationDelivery.objects.count() == 1
