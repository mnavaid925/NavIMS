"""Device-facing JSON API — auth, tenant isolation, event logging.

Guards against:
    - Device auth being bypassed (missing / invalid / inactive token).
    - Tenant forgery via payload (warehouse_id from another tenant).
    - Scan events silently dropping when barcode unmatched.
    - Batch-scan being appended to a closed session.
    - RFID read event not updating tag counters.
    - Heartbeat not updating last_seen_at + battery.
    - Inactive device being allowed to scan.
"""
import json

import pytest
from django.urls import reverse
from django.utils import timezone

from warehousing.models import Warehouse

from barcode_rfid.models import (
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)


def _post_json(client, url, payload, token=None):
    headers = {'content_type': 'application/json'}
    if token is not None:
        headers['HTTP_AUTHORIZATION'] = f'Device {token}'
    return client.post(url, data=json.dumps(payload), **headers)


# ── scan endpoint ────────────────────────────────────────────────

@pytest.mark.django_db
class TestScanEndpoint:
    def test_missing_auth_header_401(self, client_anonymous):
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': 'X'})
        assert r.status_code == 401

    def test_invalid_token_401(self, client_anonymous):
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': 'X'}, token='deadbeefdeadbeefdeadbeef')
        assert r.status_code == 401

    def test_inactive_device_cannot_scan(self, client_anonymous, scanner_device):
        scanner_device.status = 'inactive'
        scanner_device.save()
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': 'X'}, token=scanner_device.api_token)
        assert r.status_code == 401

    def test_valid_token_logs_event(self, client_anonymous, tenant, scanner_device):
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': 'ABC-UNKNOWN'}, token=scanner_device.api_token)
        assert r.status_code == 200
        data = r.json()
        assert 'event_id' in data
        ev = ScanEvent.objects.get(pk=data['event_id'])
        # Tenant must come from device, not payload.
        assert ev.tenant_id == scanner_device.tenant_id
        assert ev.device_id == scanner_device.pk

    def test_tenant_forgery_ignored(
        self, client_anonymous, tenant, scanner_device,
        other_tenant, other_warehouse,
    ):
        """Payload includes another tenant's warehouse_id — scan view must
        ignore cross-tenant warehouses. Resulting event is tenant=device.tenant."""
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:scan'),
            {'barcode': 'Y', 'warehouse_id': other_warehouse.pk},
            token=scanner_device.api_token,
        )
        assert r.status_code == 200
        ev = ScanEvent.objects.get(pk=r.json()['event_id'])
        assert ev.tenant_id == scanner_device.tenant_id
        # The view falls back to device.assigned_warehouse (same-tenant) when
        # payload warehouse_id doesn't resolve under the device's tenant.
        assert ev.warehouse_id == scanner_device.assigned_warehouse_id

    def test_unmatched_barcode_recorded(self, client_anonymous, scanner_device):
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': 'NO-SUCH-CODE'}, token=scanner_device.api_token)
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'unmatched'
        assert data['resolved_type'] == 'none'
        ev = ScanEvent.objects.get(pk=data['event_id'])
        assert ev.status == 'unmatched'

    def test_scan_resolves_rfid_tag(self, client_anonymous, scanner_device, rfid_tag):
        r = _post_json(client_anonymous, reverse('barcode_rfid_api:scan'),
                       {'barcode': rfid_tag.epc_code}, token=scanner_device.api_token)
        assert r.status_code == 200
        assert r.json()['resolved_type'] == 'rfid'


# ── batch-scan endpoint ──────────────────────────────────────────

@pytest.mark.django_db
class TestBatchScanEndpoint:
    def test_append_items_to_active_session(
        self, client_anonymous, tenant, scanner_device, batch_session,
    ):
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:batch_scan'),
            {'session_id': batch_session.pk,
             'items': [
                 {'value': 'ITEM-1', 'quantity': 2},
                 {'value': 'ITEM-2', 'quantity': 1},
             ]},
            token=scanner_device.api_token,
        )
        assert r.status_code == 200
        data = r.json()
        assert data['added'] == 2
        items = BatchScanItem.objects.filter(session=batch_session)
        assert items.count() == 2
        for it in items:
            assert it.tenant_id == scanner_device.tenant_id

    def test_closed_session_404(
        self, client_anonymous, scanner_device, batch_session,
    ):
        batch_session.status = 'completed'
        batch_session.save()
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:batch_scan'),
            {'session_id': batch_session.pk,
             'items': [{'value': 'X', 'quantity': 1}]},
            token=scanner_device.api_token,
        )
        assert r.status_code == 404


# ── rfid-read endpoint ───────────────────────────────────────────

@pytest.mark.django_db
class TestRFIDReadEndpoint:
    def test_creates_event_and_updates_tag_counts(
        self, client_anonymous, scanner_device, rfid_tag, rfid_reader,
    ):
        assert rfid_tag.read_count == 0
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:rfid_read'),
            {'epc': rfid_tag.epc_code, 'reader_code': rfid_reader.reader_code,
             'direction': 'in', 'signal_strength_dbm': -50},
            token=scanner_device.api_token,
        )
        assert r.status_code == 200
        event_id = r.json()['event_id']
        assert RFIDReadEvent.objects.filter(pk=event_id).exists()
        rfid_tag.refresh_from_db()
        assert rfid_tag.read_count == 1
        assert rfid_tag.last_read_at is not None


# ── heartbeat endpoint ───────────────────────────────────────────

@pytest.mark.django_db
class TestHeartbeatEndpoint:
    def test_updates_last_seen_and_battery(
        self, client_anonymous, scanner_device,
    ):
        assert scanner_device.last_seen_at is None
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:heartbeat'),
            {'battery_level_percent': 73},
            token=scanner_device.api_token,
        )
        assert r.status_code == 200
        data = r.json()
        assert data['ok'] is True
        scanner_device.refresh_from_db()
        assert scanner_device.last_seen_at is not None
        assert scanner_device.battery_level_percent == 73

    def test_battery_out_of_range_ignored(
        self, client_anonymous, scanner_device,
    ):
        r = _post_json(
            client_anonymous, reverse('barcode_rfid_api:heartbeat'),
            {'battery_level_percent': 200},
            token=scanner_device.api_token,
        )
        assert r.status_code == 200
        scanner_device.refresh_from_db()
        # Out-of-range payload must NOT overwrite the stored value.
        assert scanner_device.battery_level_percent != 200
