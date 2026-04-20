"""Unit tests for quality_control models — auto-numbering, state machines,
`total_value` computation, `status ↔ approval_status` mirror.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError

from quality_control.models import (
    QCChecklist, InspectionRoute,
    QuarantineRecord, DefectReport, ScrapWriteOff,
)


# ── Auto-numbering ───────────────────────────────────────────────

@pytest.mark.django_db
def test_checklist_autonumbers(tenant, tenant_admin):
    c1 = QCChecklist.objects.create(tenant=tenant, name='A', applies_to='all', created_by=tenant_admin)
    c2 = QCChecklist.objects.create(tenant=tenant, name='B', applies_to='all', created_by=tenant_admin)
    assert c1.code == 'QCC-00001'
    assert c2.code == 'QCC-00002'


@pytest.mark.django_db
def test_route_autonumbers(tenant, warehouse, qc_zone):
    r1 = InspectionRoute.objects.create(
        tenant=tenant, name='R1', source_warehouse=warehouse, qc_zone=qc_zone,
    )
    r2 = InspectionRoute.objects.create(
        tenant=tenant, name='R2', source_warehouse=warehouse, qc_zone=qc_zone,
    )
    assert r1.code == 'IR-00001'
    assert r2.code == 'IR-00002'


@pytest.mark.django_db
def test_quarantine_autonumbers(tenant, product, warehouse, qc_zone):
    q1 = QuarantineRecord.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, zone=qc_zone,
        quantity=1, reason='defect',
    )
    q2 = QuarantineRecord.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, zone=qc_zone,
        quantity=1, reason='defect',
    )
    assert q1.quarantine_number == 'QR-00001'
    assert q2.quarantine_number == 'QR-00002'


@pytest.mark.django_db
def test_defect_autonumbers(tenant, product, warehouse):
    d1 = DefectReport.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity_affected=1, description='a',
    )
    d2 = DefectReport.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity_affected=1, description='b',
    )
    assert d1.defect_number == 'DEF-00001'
    assert d2.defect_number == 'DEF-00002'


@pytest.mark.django_db
def test_scrap_autonumbers(tenant, product, warehouse):
    s1 = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='a',
    )
    s2 = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='b',
    )
    assert s1.scrap_number == 'SCR-00001'
    assert s2.scrap_number == 'SCR-00002'


# ── Unique-per-tenant ────────────────────────────────────────────

@pytest.mark.django_db
def test_checklist_code_unique_per_tenant(tenant, other_tenant, tenant_admin):
    QCChecklist.objects.create(
        tenant=tenant, code='QCC-SHARED', name='A', applies_to='all',
        created_by=tenant_admin,
    )
    # other tenant can reuse
    QCChecklist.objects.create(
        tenant=other_tenant, code='QCC-SHARED', name='B', applies_to='all',
    )
    # same tenant cannot
    with pytest.raises(IntegrityError):
        QCChecklist.objects.create(
            tenant=tenant, code='QCC-SHARED', name='C', applies_to='all',
        )


# ── State machines ──────────────────────────────────────────────

@pytest.mark.django_db
def test_quarantine_state_machine(tenant, product, warehouse, qc_zone):
    q = QuarantineRecord.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, zone=qc_zone,
        quantity=5, reason='defect',
    )
    assert q.status == 'active'
    assert q.can_transition_to('under_review')
    assert q.can_transition_to('released')
    assert q.can_transition_to('scrapped')
    q.status = 'released'; q.save()
    assert not q.can_transition_to('active')
    assert not q.can_transition_to('under_review')


@pytest.mark.django_db
def test_defect_state_machine(tenant, product, warehouse):
    d = DefectReport.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity_affected=1, description='x',
    )
    assert d.status == 'open'
    assert d.can_transition_to('investigating')
    assert d.can_transition_to('resolved')
    assert d.can_transition_to('scrapped')
    d.status = 'resolved'; d.save()
    assert not d.can_transition_to('open')
    assert not d.can_transition_to('investigating')


@pytest.mark.django_db
def test_scrap_state_machine(tenant, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=Decimal('1.00'), reason='x',
    )
    # approval_status='pending' → status='pending' via save()
    assert s.status == 'pending'
    assert s.can_transition_to('approved')
    assert s.can_transition_to('rejected')
    assert not s.can_transition_to('posted')
    s.approval_status = 'approved'; s.save()
    assert s.status == 'approved'
    assert s.can_transition_to('posted')
    assert s.can_transition_to('rejected')
    s.approval_status = 'posted'; s.save()
    assert not s.can_transition_to('approved')


# ── Computed fields ─────────────────────────────────────────────

@pytest.mark.django_db
def test_scrap_total_value_computed_on_save(tenant, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=4, unit_cost=Decimal('12.5000'), reason='x',
    )
    assert s.total_value == Decimal('50.00')


@pytest.mark.django_db
def test_scrap_status_mirrors_approval_status(tenant, product, warehouse):
    s = ScrapWriteOff.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        quantity=1, unit_cost=1, reason='x', approval_status='approved',
    )
    assert s.status == 'approved'
    s.approval_status = 'posted'; s.save()
    assert s.status == 'posted'
