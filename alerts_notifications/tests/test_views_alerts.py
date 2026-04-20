"""View integration tests for Alert CRUD + state transitions + inbox JSON.

Includes D-01 regression guard: superuser (tenant=None) create must not 500.
"""
import pytest
from django.urls import reverse

from alerts_notifications.models import Alert


# ── D-01 regression ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_D01_superuser_create_alert_does_not_crash(client_super):
    """Regression: create-view must not 500 when tenant=None."""
    response = client_super.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'probe', 'message': '',
    })
    assert response.status_code in (302, 400), 'must not be 500'
    assert Alert.objects.filter(tenant__isnull=True).count() == 0


# ── Alert list ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_alert_list_renders(client_admin):
    r = client_admin.get(reverse('alerts_notifications:alert_list'))
    assert r.status_code == 200


@pytest.mark.django_db
def test_alert_list_excludes_other_tenants(client_admin, foreign_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_list'))
    assert 'Foreign alert' not in r.content.decode()


@pytest.mark.django_db
def test_alert_list_search_by_number(client_admin, new_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_list') + f'?q={new_alert.alert_number}')
    assert new_alert.title in r.content.decode()


@pytest.mark.django_db
def test_alert_list_filter_by_status(client_admin, new_alert, acknowledged_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_list') + '?status=new')
    body = r.content.decode()
    assert new_alert.alert_number in body
    assert acknowledged_alert.alert_number not in body


@pytest.mark.django_db
def test_alert_list_filter_by_warehouse_retains_stringformat(client_admin, warehouse, new_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_list') + f'?warehouse={warehouse.pk}')
    body = r.content.decode()
    # Dropdown retains selected option via |stringformat:"d" — verify the selected attribute is on that <option>.
    assert f'value="{warehouse.pk}" selected' in body


# ── Alert detail ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_alert_detail_renders(client_admin, new_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_detail', args=[new_alert.pk]))
    assert r.status_code == 200
    assert new_alert.title in r.content.decode()


@pytest.mark.django_db
def test_alert_detail_cross_tenant_404(client_admin, foreign_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_detail', args=[foreign_alert.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_alert_detail_soft_deleted_404(client_admin, new_alert):
    from django.utils import timezone
    new_alert.deleted_at = timezone.now()
    new_alert.save()
    r = client_admin.get(reverse('alerts_notifications:alert_detail', args=[new_alert.pk]))
    assert r.status_code == 404


# ── Create ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_alert_create_happy_path(client_admin, tenant, product, warehouse):
    r = client_admin.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'Manual probe', 'message': 'created via UI',
        'product': product.pk, 'warehouse': warehouse.pk,
    })
    assert r.status_code == 302
    a = Alert.objects.get(tenant=tenant, title='Manual probe')
    assert a.dedup_key.startswith('manual:')


@pytest.mark.django_db
def test_alert_create_non_admin_forbidden(client_user):
    r = client_user.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning', 'title': 'x',
    })
    assert r.status_code == 403


# ── State transitions ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_acknowledge_transitions_new_to_acknowledged(client_admin, tenant_admin, new_alert):
    r = client_admin.post(reverse('alerts_notifications:alert_acknowledge', args=[new_alert.pk]))
    assert r.status_code == 302
    new_alert.refresh_from_db()
    assert new_alert.status == 'acknowledged'
    assert new_alert.acknowledged_by_id == tenant_admin.pk
    assert new_alert.acknowledged_at is not None


@pytest.mark.django_db
def test_resolve_blocked_from_new(client_admin, new_alert):
    r = client_admin.post(reverse('alerts_notifications:alert_resolve', args=[new_alert.pk]))
    new_alert.refresh_from_db()
    assert new_alert.status == 'new'


@pytest.mark.django_db
def test_resolve_allowed_from_acknowledged(client_admin, acknowledged_alert):
    r = client_admin.post(
        reverse('alerts_notifications:alert_resolve', args=[acknowledged_alert.pk]),
        {'notes': 'Fixed the stock'},
    )
    assert r.status_code == 302
    acknowledged_alert.refresh_from_db()
    assert acknowledged_alert.status == 'resolved'
    assert acknowledged_alert.resolved_at is not None
    assert 'Fixed the stock' in acknowledged_alert.notes


@pytest.mark.django_db
def test_dismiss_from_new(client_admin, new_alert):
    r = client_admin.post(reverse('alerts_notifications:alert_dismiss', args=[new_alert.pk]))
    assert r.status_code == 302
    new_alert.refresh_from_db()
    assert new_alert.status == 'dismissed'


@pytest.mark.django_db
def test_acknowledge_get_returns_405(client_admin, new_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_acknowledge', args=[new_alert.pk]))
    assert r.status_code == 405


@pytest.mark.django_db
def test_delete_soft_deletes(client_admin, new_alert):
    r = client_admin.post(reverse('alerts_notifications:alert_delete', args=[new_alert.pk]))
    assert r.status_code == 302
    new_alert.refresh_from_db()
    assert new_alert.deleted_at is not None


# ── Alert edit (D-03) ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_D03_manual_alert_editable(client_admin, tenant, product, warehouse):
    client_admin.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'Manual-edit-probe', 'message': '',
        'product': product.pk, 'warehouse': warehouse.pk,
    })
    a = Alert.objects.get(tenant=tenant, title='Manual-edit-probe')
    r = client_admin.get(reverse('alerts_notifications:alert_edit', args=[a.pk]))
    assert r.status_code == 200


@pytest.mark.django_db
def test_D03_scanner_alert_not_editable(client_admin, new_alert):
    """Scanner-generated alert → edit redirects to detail with error message."""
    r = client_admin.get(reverse('alerts_notifications:alert_edit', args=[new_alert.pk]))
    assert r.status_code == 302  # redirects with error flash


# ── Inbox JSON ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_inbox_json_tenant_scoped(client_admin, new_alert, foreign_alert):
    r = client_admin.get(reverse('alerts_notifications:alert_inbox_json'))
    assert r.status_code == 200
    data = r.json()
    assert data['unread_count'] == 1
    assert data['items'][0]['alert_number'] == new_alert.alert_number


@pytest.mark.django_db
def test_inbox_json_superuser_empty(client_super):
    r = client_super.get(reverse('alerts_notifications:alert_inbox_json'))
    assert r.status_code == 200
    assert r.json() == {'unread_count': 0, 'items': []}
