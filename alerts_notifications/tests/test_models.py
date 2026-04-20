"""Model-level tests — auto-numbering, state machine, dedup uniqueness, __str__."""
import pytest
from django.db import IntegrityError

from alerts_notifications.models import Alert, NotificationRule, NotificationDelivery


@pytest.mark.django_db
def test_alert_auto_number_first(tenant):
    a = Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    assert a.alert_number == 'ALN-00001'


@pytest.mark.django_db
def test_alert_auto_number_increments(tenant):
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    b = Alert.objects.create(tenant=tenant, alert_type='low_stock', title='y', dedup_key='t:2')
    assert b.alert_number == 'ALN-00002'


@pytest.mark.django_db
def test_alert_number_is_tenant_scoped(tenant, other_tenant):
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    b = Alert.objects.create(tenant=other_tenant, alert_type='low_stock', title='y', dedup_key='t:2')
    assert b.alert_number == 'ALN-00001'


@pytest.mark.django_db
def test_alert_user_supplied_number_preserved(tenant):
    a = Alert.objects.create(
        tenant=tenant, alert_number='CUSTOM-01',
        alert_type='low_stock', title='x', dedup_key='t:1',
    )
    assert a.alert_number == 'CUSTOM-01'


@pytest.mark.django_db
def test_alert_state_machine_from_new(tenant):
    a = Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1')
    assert a.can_transition_to('acknowledged')
    assert a.can_transition_to('dismissed')
    assert not a.can_transition_to('resolved')
    assert not a.can_transition_to('new')


@pytest.mark.django_db
def test_alert_state_machine_from_acknowledged(tenant):
    a = Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='t:1', status='acknowledged')
    assert a.can_transition_to('resolved')
    assert a.can_transition_to('dismissed')
    assert not a.can_transition_to('new')


@pytest.mark.django_db
def test_alert_state_machine_terminal_states(tenant):
    for terminal in ('resolved', 'dismissed'):
        a = Alert.objects.create(
            tenant=tenant, alert_type='low_stock',
            title=f'x-{terminal}', dedup_key=f't:{terminal}', status=terminal,
        )
        for other in ('new', 'acknowledged', 'resolved', 'dismissed'):
            assert not a.can_transition_to(other), f'{terminal} should not transition to {other}'


@pytest.mark.django_db
def test_alert_dedup_unique_per_tenant(tenant):
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='same-key')
    with pytest.raises(IntegrityError):
        Alert.objects.create(tenant=tenant, alert_type='low_stock', title='y', dedup_key='same-key')


@pytest.mark.django_db
def test_alert_dedup_allows_same_key_across_tenants(tenant, other_tenant):
    Alert.objects.create(tenant=tenant, alert_type='low_stock', title='x', dedup_key='shared-key')
    other = Alert.objects.create(tenant=other_tenant, alert_type='low_stock', title='y', dedup_key='shared-key')
    assert other.pk is not None


@pytest.mark.django_db
def test_alert_str(tenant):
    a = Alert.objects.create(tenant=tenant, alert_type='low_stock', title='Hello', dedup_key='t:1')
    assert a.alert_number in str(a)
    assert 'Hello' in str(a)


@pytest.mark.django_db
def test_rule_auto_code(tenant):
    r = NotificationRule.objects.create(tenant=tenant, name='R1', alert_type='low_stock')
    assert r.code == 'NR-00001'


@pytest.mark.django_db
def test_rule_code_increments(tenant):
    NotificationRule.objects.create(tenant=tenant, name='R1', alert_type='low_stock')
    r2 = NotificationRule.objects.create(tenant=tenant, name='R2', alert_type='overstock')
    assert r2.code == 'NR-00002'


@pytest.mark.django_db
def test_delivery_unique_per_alert_recipient_channel(tenant, tenant_admin, new_alert):
    NotificationDelivery.objects.create(
        tenant=tenant, alert=new_alert, recipient=tenant_admin,
        channel='email', status='sent',
    )
    with pytest.raises(IntegrityError):
        NotificationDelivery.objects.create(
            tenant=tenant, alert=new_alert, recipient=tenant_admin,
            channel='email', status='sent',
        )
