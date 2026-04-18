"""Shared fixtures for the barcode_rfid test suite.

Follows the same convention as lot_tracking/, stocktaking/, returns/ tests —
a primary tenant + user + warehouse, and a parallel `other_*` set for
cross-tenant IDOR tests.
"""
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Tenant, User
from warehousing.models import Warehouse, Zone

from barcode_rfid.models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice,
    RFIDTag, RFIDReader,
    BatchScanSession,
)


# ── Tenants & Users ──────────────────────────────────────────────

@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name='T-BRF', slug='t-brf')


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name='T-BRF-Other', slug='t-brf-other')


@pytest.fixture
def tenant_admin(db, tenant):
    return User.objects.create_user(
        username='admin_brf', password='x',
        tenant=tenant, is_tenant_admin=True,
    )


@pytest.fixture
def tenant_user(db, tenant):
    return User.objects.create_user(
        username='user_brf', password='x',
        tenant=tenant, is_tenant_admin=False,
    )


@pytest.fixture
def other_tenant_admin(db, other_tenant):
    return User.objects.create_user(
        username='admin_brf_other', password='x',
        tenant=other_tenant, is_tenant_admin=True,
    )


# ── Warehouse / Zone ─────────────────────────────────────────────

@pytest.fixture
def warehouse(db, tenant):
    return Warehouse.objects.create(
        tenant=tenant, code='WH1', name='Main WH', is_active=True,
    )


@pytest.fixture
def other_warehouse(db, other_tenant):
    return Warehouse.objects.create(
        tenant=other_tenant, code='WH1', name='Other WH', is_active=True,
    )


@pytest.fixture
def zone(db, tenant, warehouse):
    return Zone.objects.create(
        tenant=tenant, warehouse=warehouse, code='Z1', name='Zone 1',
    )


@pytest.fixture
def other_zone(db, other_tenant, other_warehouse):
    return Zone.objects.create(
        tenant=other_tenant, warehouse=other_warehouse, code='Z1', name='Other Zone',
    )


# ── Domain fixtures ──────────────────────────────────────────────

@pytest.fixture
def label_template(db, tenant):
    return LabelTemplate.objects.create(
        tenant=tenant, code='LBL-STD', name='Standard', is_active=True,
    )


@pytest.fixture
def other_label_template(db, other_tenant):
    return LabelTemplate.objects.create(
        tenant=other_tenant, code='LBL-OTHER', name='Other', is_active=True,
    )


@pytest.fixture
def print_job(db, tenant, label_template):
    return LabelPrintJob.objects.create(
        tenant=tenant, template=label_template,
        target_type='product', target_display='SKU-001', quantity=5,
    )


@pytest.fixture
def scanner_device(db, tenant, warehouse):
    return ScannerDevice.objects.create(
        tenant=tenant, device_code='SCAN-001', name='Dev 1',
        device_type='handheld', assigned_warehouse=warehouse,
        status='active', is_active=True,
    )


@pytest.fixture
def other_scanner_device(db, other_tenant, other_warehouse):
    return ScannerDevice.objects.create(
        tenant=other_tenant, device_code='SCAN-OTHER', name='Other Dev',
        device_type='handheld', assigned_warehouse=other_warehouse,
        status='active', is_active=True,
    )


@pytest.fixture
def rfid_tag(db, tenant):
    return RFIDTag.objects.create(
        tenant=tenant, epc_code='E200001', tag_type='passive',
        frequency_band='uhf', status='unassigned',
    )


@pytest.fixture
def other_rfid_tag(db, other_tenant):
    return RFIDTag.objects.create(
        tenant=other_tenant, epc_code='E200OTHER', tag_type='passive',
        frequency_band='uhf', status='unassigned',
    )


@pytest.fixture
def rfid_reader(db, tenant, warehouse, zone):
    return RFIDReader.objects.create(
        tenant=tenant, reader_code='RDR-01', name='Gate 1',
        reader_type='fixed_gate', warehouse=warehouse, zone=zone,
        status='online', is_active=True,
    )


@pytest.fixture
def batch_session(db, tenant, warehouse, tenant_admin):
    return BatchScanSession.objects.create(
        tenant=tenant, warehouse=warehouse, purpose='receiving',
        status='active', user=tenant_admin, created_by=tenant_admin,
    )


# ── Clients ──────────────────────────────────────────────────────

@pytest.fixture
def client_admin(db, tenant_admin):
    c = Client()
    c.force_login(tenant_admin)
    return c


@pytest.fixture
def client_user(db, tenant_user):
    c = Client()
    c.force_login(tenant_user)
    return c


@pytest.fixture
def client_other(db, other_tenant_admin):
    c = Client()
    c.force_login(other_tenant_admin)
    return c


@pytest.fixture
def client_anonymous(db):
    return Client()
