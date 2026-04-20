"""NotificationDelivery audit-log view tests (read-only)."""
import pytest
from django.urls import reverse

from alerts_notifications.models import NotificationDelivery


@pytest.mark.django_db
def test_delivery_list_renders(client_admin, tenant, tenant_admin, new_alert, rule):
    NotificationDelivery.objects.create(
        tenant=tenant, alert=new_alert, rule=rule, recipient=tenant_admin,
        channel='email', status='sent', recipient_email='a@example.com',
    )
    r = client_admin.get(reverse('alerts_notifications:delivery_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_delivery_list_excludes_other_tenants(client_admin, other_tenant, foreign_alert, foreign_rule, other_tenant_admin):
    NotificationDelivery.objects.create(
        tenant=other_tenant, alert=foreign_alert, rule=foreign_rule,
        recipient=other_tenant_admin, channel='email', status='sent',
    )
    r = client_admin.get(reverse('alerts_notifications:delivery_list'))
    assert foreign_alert.alert_number not in r.content.decode()


@pytest.mark.django_db
def test_delivery_detail_cross_tenant_404(client_admin, other_tenant, foreign_alert, other_tenant_admin):
    d = NotificationDelivery.objects.create(
        tenant=other_tenant, alert=foreign_alert,
        recipient=other_tenant_admin, channel='inbox', status='sent',
    )
    r = client_admin.get(reverse('alerts_notifications:delivery_detail', args=[d.pk]))
    assert r.status_code == 404
