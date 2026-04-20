"""Named regression guards for defects D-NN surfaced in SQA review 2026-04-20."""
import pytest
from django.urls import reverse

from alerts_notifications.models import Alert


@pytest.mark.django_db
def test_D04_50K_notes_rejected(client_admin, acknowledged_alert):
    """D-04: 50 KB notes on resolve must be rejected by AlertResolveForm (max_length=2000)."""
    before_len = len(acknowledged_alert.notes)
    before_status = acknowledged_alert.status
    r = client_admin.post(
        reverse('alerts_notifications:alert_resolve', args=[acknowledged_alert.pk]),
        {'notes': 'A' * 50000},
    )
    assert r.status_code == 302  # redirect with error flash
    acknowledged_alert.refresh_from_db()
    assert acknowledged_alert.status == before_status, 'Form rejected → state unchanged'
    assert len(acknowledged_alert.notes) == before_len


@pytest.mark.django_db
def test_D04_2K_notes_accepted_and_combined_capped(client_admin, acknowledged_alert):
    """D-04: 2000-char notes accepted; combined alert.notes capped to 16 KB."""
    r = client_admin.post(
        reverse('alerts_notifications:alert_resolve', args=[acknowledged_alert.pk]),
        {'notes': 'B' * 2000},
    )
    assert r.status_code == 302
    acknowledged_alert.refresh_from_db()
    assert acknowledged_alert.status == 'resolved'
    assert len(acknowledged_alert.notes) <= 16384


@pytest.mark.django_db
def test_D06_manual_alert_uses_uuid_dedup_key(client_admin, tenant, product, warehouse):
    """D-06: manual alerts use uuid4 (32 hex chars), not floating-point timestamp."""
    client_admin.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'uuid-probe', 'message': '',
        'product': product.pk, 'warehouse': warehouse.pk,
    })
    a = Alert.objects.get(tenant=tenant, title='uuid-probe')
    assert a.dedup_key.startswith('manual:')
    tail = a.dedup_key[len('manual:'):]
    assert len(tail) == 32
    # Hex only
    int(tail, 16)  # raises if not hex
