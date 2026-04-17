"""Form-level negative coverage — regression guards for D-01..D-04, D-10, D-13."""
import pytest
from datetime import date, timedelta

from lot_tracking.forms import (
    LotBatchForm, SerialNumberForm, TraceabilityLogForm,
)
from lot_tracking.models import LotBatch


def _lot_data(product, warehouse, **overrides):
    data = {
        'product': product.pk, 'warehouse': warehouse.pk, 'grn': '',
        'quantity': 10,
        'manufacturing_date': '', 'expiry_date': '',
        'supplier_batch_number': '', 'notes': '',
    }
    data.update(overrides)
    return data


def _serial_data(product, warehouse, **overrides):
    data = {
        'serial_number': 'SN-NEW', 'product': product.pk,
        'lot': '', 'warehouse': warehouse.pk,
        'purchase_date': '', 'warranty_expiry': '', 'notes': '',
    }
    data.update(overrides)
    return data


# ── D-01 — duplicate serial rejected ──────────────────────────────────────

@pytest.mark.django_db
class TestSerialUniqueness:
    def test_duplicate_serial_rejected(self, tenant, product, warehouse, serial):
        form = SerialNumberForm(
            data=_serial_data(product, warehouse, serial_number=serial.serial_number),
            tenant=tenant,
        )
        assert not form.is_valid()
        assert 'serial_number' in form.errors

    def test_duplicate_case_insensitive(self, tenant, product, warehouse, serial):
        form = SerialNumberForm(
            data=_serial_data(product, warehouse, serial_number=serial.serial_number.lower()),
            tenant=tenant,
        )
        assert not form.is_valid()

    def test_same_serial_other_tenant_allowed(
        self, tenant, other_tenant, product, warehouse, serial,
    ):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="X")
        p2 = P.objects.create(tenant=other_tenant, sku="S2", name="S2", category=cat,
                              purchase_cost=1, retail_price=2, status="active")
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        form = SerialNumberForm(
            data=_serial_data(p2, w2, serial_number=serial.serial_number),
            tenant=other_tenant,
        )
        assert form.is_valid(), form.errors

    def test_edit_serial_with_own_number_allowed(
        self, tenant, product, warehouse, serial,
    ):
        form = SerialNumberForm(
            data=_serial_data(product, warehouse, serial_number=serial.serial_number),
            instance=serial, tenant=tenant,
        )
        assert form.is_valid(), form.errors


# ── D-02 — lot FK preserved on edit even for non-active lots ──────────────

@pytest.mark.django_db
class TestSerialEditPreservesLot:
    @pytest.mark.parametrize("lot_status", ["quarantine", "expired", "consumed", "recalled"])
    def test_current_lot_included_in_queryset(
        self, tenant, product, warehouse, serial, lot_status,
    ):
        serial.lot.status = lot_status
        serial.lot.save()
        form = SerialNumberForm(instance=serial, tenant=tenant)
        assert serial.lot in list(form.fields['lot'].queryset)


# ── D-03 — manufacturing/expiry ───────────────────────────────────────────

@pytest.mark.django_db
class TestLotDateValidation:
    def test_mfg_after_expiry_rejected(self, tenant, product, warehouse):
        form = LotBatchForm(data=_lot_data(
            product, warehouse,
            manufacturing_date=(date.today() + timedelta(days=30)).isoformat(),
            expiry_date=date.today().isoformat(),
        ), tenant=tenant)
        assert not form.is_valid()

    def test_mfg_same_as_expiry_allowed(self, tenant, product, warehouse):
        form = LotBatchForm(data=_lot_data(
            product, warehouse,
            manufacturing_date=date.today().isoformat(),
            expiry_date=date.today().isoformat(),
        ), tenant=tenant)
        assert form.is_valid(), form.errors


# ── D-04 — quantity ≥ 1 ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLotQuantityValidation:
    def test_quantity_zero_rejected(self, tenant, product, warehouse):
        form = LotBatchForm(data=_lot_data(product, warehouse, quantity=0), tenant=tenant)
        assert not form.is_valid()
        assert 'quantity' in form.errors


# ── D-13 — quantity invariant on edit ─────────────────────────────────────

@pytest.mark.django_db
class TestLotAvailableQuantityInvariant:
    def test_edit_quantity_below_available_rejected(self, tenant, lot):
        lot.available_quantity = 80
        lot.save()
        form = LotBatchForm(
            data=_lot_data(lot.product, lot.warehouse, quantity=50),
            instance=lot, tenant=tenant,
        )
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_edit_quantity_equal_to_available_allowed(self, tenant, lot):
        lot.available_quantity = 80
        lot.save()
        form = LotBatchForm(
            data=_lot_data(lot.product, lot.warehouse, quantity=80),
            instance=lot, tenant=tenant,
        )
        assert form.is_valid(), form.errors


# ── D-10 — TraceabilityLog event-type guards ──────────────────────────────

@pytest.mark.django_db
class TestTraceabilityEventValidation:
    def test_transfer_requires_both_warehouses(self, tenant, lot, warehouse):
        form = TraceabilityLogForm(data={
            'lot': lot.pk, 'serial_number': '',
            'event_type': 'transferred',
            'from_warehouse': warehouse.pk, 'to_warehouse': '',
            'quantity': 5,
            'reference_type': '', 'reference_number': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()

    def test_transfer_same_warehouse_rejected(self, tenant, lot, warehouse):
        form = TraceabilityLogForm(data={
            'lot': lot.pk, 'serial_number': '',
            'event_type': 'transferred',
            'from_warehouse': warehouse.pk, 'to_warehouse': warehouse.pk,
            'quantity': 5,
            'reference_type': '', 'reference_number': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()

    def test_sold_quantity_zero_rejected(self, tenant, lot):
        form = TraceabilityLogForm(data={
            'lot': lot.pk, 'serial_number': '',
            'event_type': 'sold',
            'from_warehouse': '', 'to_warehouse': '', 'quantity': 0,
            'reference_type': '', 'reference_number': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()
        assert 'quantity' in form.errors

    def test_neither_lot_nor_serial_rejected(self, tenant):
        form = TraceabilityLogForm(data={
            'lot': '', 'serial_number': '',
            'event_type': 'adjusted', 'quantity': 1,
            'reference_type': '', 'reference_number': '',
            'from_warehouse': '', 'to_warehouse': '', 'notes': '',
        }, tenant=tenant)
        assert not form.is_valid()
