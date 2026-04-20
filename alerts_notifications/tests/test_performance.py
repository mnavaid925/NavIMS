"""Query-count budgets — guards against N+1 regressions."""
import pytest
from django.urls import reverse

from alerts_notifications.models import Alert, NotificationRule


@pytest.mark.django_db
def test_alert_list_query_budget(client_admin, tenant, product, warehouse, django_assert_max_num_queries):
    for i in range(25):
        Alert.objects.create(
            tenant=tenant, alert_type='low_stock', severity='warning',
            title=f'Alert {i}', dedup_key=f't:{i}',
            product=product, warehouse=warehouse,
        )
    with django_assert_max_num_queries(15):
        r = client_admin.get(reverse('alerts_notifications:alert_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_rule_list_query_budget(client_admin, tenant, tenant_admin, django_assert_max_num_queries):
    """D-11 regression: |length over prefetched recipient_users, not .count() per row."""
    for i in range(10):
        r = NotificationRule.objects.create(tenant=tenant, name=f'R{i}', alert_type='low_stock')
        r.recipient_users.add(tenant_admin)
    with django_assert_max_num_queries(12):
        r = client_admin.get(reverse('alerts_notifications:rule_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_delivery_list_query_budget(client_admin, tenant, tenant_admin, product, warehouse, rule, django_assert_max_num_queries):
    from alerts_notifications.models import NotificationDelivery
    # Each delivery needs a distinct (alert, recipient, channel) triple per unique_together.
    for i in range(15):
        a = Alert.objects.create(
            tenant=tenant, alert_type='low_stock', severity='warning',
            title=f'A{i}', dedup_key=f'perf:{i}',
            product=product, warehouse=warehouse,
        )
        NotificationDelivery.objects.create(
            tenant=tenant, alert=a, rule=rule, recipient=tenant_admin,
            channel='email', status='sent',
        )
    with django_assert_max_num_queries(12):
        r = client_admin.get(reverse('alerts_notifications:delivery_list'))
    assert r.status_code == 200
