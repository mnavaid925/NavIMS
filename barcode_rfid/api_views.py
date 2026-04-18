"""Device-facing scan API.

Authentication model: every ScannerDevice has an opaque `api_token` (32-byte
URL-safe secret) rotated via `POST /barcode-rfid/devices/<pk>/rotate-token/`.
Devices send `Authorization: Device <token>` with every request; tenant
context is derived from the matched device — never trusted from the payload.

All endpoints are CSRF-exempt (devices have no CSRF tokens), POST-only, and
return JSON. Tenant isolation is enforced: the device can only resolve / log
scans against its own tenant's data.

Endpoints:
    POST /api/barcode-rfid/scan/          — single-scan lookup + audit log
    POST /api/barcode-rfid/batch-scan/    — append items to an active BatchScanSession
    POST /api/barcode-rfid/rfid-read/     — log an RFID read event
    POST /api/barcode-rfid/heartbeat/     — device ping (last_seen_at, battery)
"""
import json

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from catalog.models import Product
from lot_tracking.models import LotBatch, SerialNumber
from warehousing.models import Bin, Warehouse

from .models import (
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)


def _authenticate_device(request):
    """Return ScannerDevice or None. Never trusts tenant from payload."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Device '):
        return None
    token = header.removeprefix('Device ').strip()
    if not token or len(token) < 16:
        return None
    device = ScannerDevice.objects.filter(api_token=token, is_active=True).first()
    if device is None:
        return None
    if device.status not in ('active',):
        return None
    return device


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _parse_json(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return None


def _resolve_barcode(tenant, value):
    """Attempt to resolve a barcode value against tenant-scoped catalog rows.

    Returns (resolved_type, resolved_id, display) — ('none', None, '') if no match.
    Resolution order: serial → lot → RFID EPC → product.sku → product.barcode → bin.code.
    """
    if not value:
        return 'none', None, ''
    v = value.strip()

    serial = SerialNumber.objects.filter(tenant=tenant, serial_number=v).first()
    if serial is not None:
        return 'serial', serial.pk, f'Serial {serial.serial_number}'

    lot = LotBatch.objects.filter(tenant=tenant, lot_number=v).first()
    if lot is not None:
        return 'lot', lot.pk, f'Lot {lot.lot_number}'

    rfid = RFIDTag.objects.filter(tenant=tenant, epc_code=v).first()
    if rfid is not None:
        return 'rfid', rfid.pk, f'RFID {rfid.epc_code}'

    product = Product.objects.filter(tenant=tenant, sku=v).first()
    if product is not None:
        return 'product', product.pk, f'{product.sku} — {product.name}'
    product = Product.objects.filter(tenant=tenant, barcode=v).first()
    if product is not None:
        return 'product', product.pk, f'{product.sku} — {product.name}'

    bin_obj = Bin.objects.filter(tenant=tenant, code=v).first()
    if bin_obj is not None:
        return 'bin', bin_obj.pk, f'Bin {bin_obj.code}'

    return 'none', None, ''


@csrf_exempt
@require_POST
def scan_view(request):
    device = _authenticate_device(request)
    if device is None:
        return JsonResponse({'error': 'invalid_or_missing_device_token'}, status=401)

    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'invalid_json_body'}, status=400)

    barcode_value = (payload.get('barcode') or '').strip()
    if not barcode_value:
        return JsonResponse({'error': 'barcode_required'}, status=400)

    scan_type = payload.get('scan_type', 'lookup')
    if scan_type not in dict(ScanEvent.SCAN_TYPE_CHOICES):
        scan_type = 'lookup'
    symbology = (payload.get('symbology') or '')[:20]

    tenant = device.tenant
    rtype, rid, display = _resolve_barcode(tenant, barcode_value)
    event_status = 'success' if rtype != 'none' else 'unmatched'

    warehouse = device.assigned_warehouse
    warehouse_id = payload.get('warehouse_id')
    if warehouse_id:
        wh = Warehouse.objects.filter(tenant=tenant, pk=warehouse_id).first()
        if wh is not None:
            warehouse = wh

    with transaction.atomic():
        event = ScanEvent.objects.create(
            tenant=tenant,
            device=device,
            user=device.assigned_to,
            scan_type=scan_type,
            barcode_value=barcode_value,
            symbology=symbology,
            resolved_object_type=rtype,
            resolved_object_id=rid,
            resolved_display=display,
            warehouse=warehouse,
            status=event_status,
            ip_address=_client_ip(request),
        )
        ScannerDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())

    return JsonResponse({
        'event_id': event.pk,
        'resolved_type': rtype,
        'resolved_id': rid,
        'resolved_display': display,
        'status': event_status,
    })


@csrf_exempt
@require_POST
def batch_scan_view(request):
    device = _authenticate_device(request)
    if device is None:
        return JsonResponse({'error': 'invalid_or_missing_device_token'}, status=401)

    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'invalid_json_body'}, status=400)

    session_id = payload.get('session_id')
    items = payload.get('items') or []
    if not session_id or not isinstance(items, list) or not items:
        return JsonResponse({'error': 'session_id_and_items_required'}, status=400)

    tenant = device.tenant
    session = BatchScanSession.objects.filter(tenant=tenant, pk=session_id, status='active').first()
    if session is None:
        return JsonResponse({'error': 'session_not_found_or_closed'}, status=404)

    created = []
    with transaction.atomic():
        for raw in items:
            value = (raw.get('value') or '').strip()
            if not value:
                continue
            qty = raw.get('quantity', 1)
            try:
                from decimal import Decimal, InvalidOperation
                qty_dec = Decimal(str(qty))
                if qty_dec <= 0:
                    qty_dec = Decimal('1')
            except (InvalidOperation, TypeError):
                from decimal import Decimal
                qty_dec = Decimal('1')
            rtype, rid, display = _resolve_barcode(tenant, value)
            item = BatchScanItem.objects.create(
                tenant=tenant,
                session=session,
                scanned_value=value,
                symbology=(raw.get('symbology') or '')[:20],
                resolution_type=rtype if rtype != 'none' else 'unmatched',
                resolved_object_id=rid,
                resolved_display=display,
                quantity=qty_dec,
                is_resolved=(rtype != 'none'),
            )
            created.append({'id': item.pk, 'resolved_type': item.resolution_type, 'resolved_id': rid})

        session.total_items_scanned = session.items.count()
        session.save(update_fields=['total_items_scanned', 'updated_at'])
        ScannerDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())

    return JsonResponse({'session_id': session.pk, 'added': len(created), 'items': created})


@csrf_exempt
@require_POST
def rfid_read_view(request):
    device = _authenticate_device(request)
    if device is None:
        return JsonResponse({'error': 'invalid_or_missing_device_token'}, status=401)

    payload = _parse_json(request)
    if payload is None:
        return JsonResponse({'error': 'invalid_json_body'}, status=400)

    epc = (payload.get('epc') or '').strip()
    reader_code = (payload.get('reader_code') or '').strip()
    if not epc or not reader_code:
        return JsonResponse({'error': 'epc_and_reader_code_required'}, status=400)

    tenant = device.tenant
    tag = RFIDTag.objects.filter(tenant=tenant, epc_code=epc).first()
    reader = RFIDReader.objects.filter(tenant=tenant, reader_code=reader_code).first()
    if tag is None or reader is None:
        return JsonResponse({'error': 'tag_or_reader_not_found'}, status=404)

    direction = payload.get('direction', 'unknown')
    if direction not in dict(RFIDReadEvent.DIRECTION_CHOICES):
        direction = 'unknown'

    with transaction.atomic():
        event = RFIDReadEvent.objects.create(
            tenant=tenant,
            tag=tag,
            reader=reader,
            signal_strength_dbm=payload.get('signal_strength_dbm'),
            read_count_at_event=payload.get('read_count_at_event', 1) or 1,
            direction=direction,
            antenna_number=payload.get('antenna_number', 1) or 1,
        )
        now = timezone.now()
        RFIDTag.objects.filter(pk=tag.pk).update(
            last_read_at=now,
            first_read_at=tag.first_read_at or now,
            read_count=tag.read_count + 1,
        )
        RFIDReader.objects.filter(pk=reader.pk).update(last_seen_at=now)
        ScannerDevice.objects.filter(pk=device.pk).update(last_seen_at=now)

    return JsonResponse({'event_id': event.pk})


@csrf_exempt
@require_POST
def heartbeat_view(request):
    device = _authenticate_device(request)
    if device is None:
        return JsonResponse({'error': 'invalid_or_missing_device_token'}, status=401)

    payload = _parse_json(request) or {}
    battery = payload.get('battery_level_percent')
    updates = {'last_seen_at': timezone.now()}
    if isinstance(battery, int) and 0 <= battery <= 100:
        updates['battery_level_percent'] = battery
    ScannerDevice.objects.filter(pk=device.pk).update(**updates)
    return JsonResponse({'ok': True, 'device_id': device.pk, 'tenant_id': device.tenant_id})
