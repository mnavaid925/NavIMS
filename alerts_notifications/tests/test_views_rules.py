"""NotificationRule view tests — CRUD + toggle-active + D-02 regression."""
import pytest
from django.urls import reverse

from alerts_notifications.models import NotificationRule


@pytest.mark.django_db
def test_D02_superuser_create_rule_does_not_crash(client_super):
    """Regression: rule-create must not 500 when tenant=None."""
    r = client_super.post(reverse('alerts_notifications:rule_create'), {
        'code': '', 'name': 'probe',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'is_active': 'on',
    })
    assert r.status_code in (302, 400)
    assert NotificationRule.objects.filter(tenant__isnull=True).count() == 0


@pytest.mark.django_db
def test_rule_list_renders(client_admin, rule):
    r = client_admin.get(reverse('alerts_notifications:rule_list'))
    assert r.status_code == 200
    assert rule.code in r.content.decode()


@pytest.mark.django_db
def test_rule_list_excludes_other_tenants(client_admin, foreign_rule):
    r = client_admin.get(reverse('alerts_notifications:rule_list'))
    assert foreign_rule.code not in r.content.decode()


@pytest.mark.django_db
def test_rule_create_happy_path(client_admin, tenant, tenant_admin):
    r = client_admin.post(reverse('alerts_notifications:rule_create'), {
        'code': '', 'name': 'NewRule',
        'alert_type': 'overstock', 'min_severity': 'info',
        'notify_email': 'on', 'notify_inbox': 'on',
        'recipient_users': [tenant_admin.pk],
        'is_active': 'on',
    })
    assert r.status_code == 302
    obj = NotificationRule.objects.get(tenant=tenant, name='NewRule')
    assert obj.code.startswith('NR-')
    assert tenant_admin in obj.recipient_users.all()


@pytest.mark.django_db
def test_rule_edit_preserves_m2m(client_admin, rule, tenant_admin, tenant_user):
    r = client_admin.post(reverse('alerts_notifications:rule_edit', args=[rule.pk]), {
        'code': rule.code, 'name': 'Updated',
        'alert_type': rule.alert_type, 'min_severity': rule.min_severity,
        'notify_email': 'on', 'notify_inbox': 'on',
        'recipient_users': [tenant_admin.pk, tenant_user.pk],
        'is_active': 'on',
    })
    assert r.status_code == 302
    rule.refresh_from_db()
    assert rule.name == 'Updated'
    assert set(rule.recipient_users.values_list('pk', flat=True)) == {tenant_admin.pk, tenant_user.pk}


@pytest.mark.django_db
def test_rule_delete_soft_deletes(client_admin, rule):
    r = client_admin.post(reverse('alerts_notifications:rule_delete', args=[rule.pk]))
    assert r.status_code == 302
    rule.refresh_from_db()
    assert rule.deleted_at is not None


@pytest.mark.django_db
def test_rule_toggle_active(client_admin, rule):
    assert rule.is_active is True
    r = client_admin.post(reverse('alerts_notifications:rule_toggle_active', args=[rule.pk]))
    assert r.status_code == 302
    rule.refresh_from_db()
    assert rule.is_active is False

    client_admin.post(reverse('alerts_notifications:rule_toggle_active', args=[rule.pk]))
    rule.refresh_from_db()
    assert rule.is_active is True


@pytest.mark.django_db
def test_rule_toggle_active_get_returns_405(client_admin, rule):
    r = client_admin.get(reverse('alerts_notifications:rule_toggle_active', args=[rule.pk]))
    assert r.status_code == 405


@pytest.mark.django_db
def test_rule_detail_cross_tenant_404(client_admin, foreign_rule):
    r = client_admin.get(reverse('alerts_notifications:rule_detail', args=[foreign_rule.pk]))
    assert r.status_code == 404
