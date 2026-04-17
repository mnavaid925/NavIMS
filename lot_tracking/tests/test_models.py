"""Unit tests — model invariants, auto-codes, computed properties, transitions."""
import pytest
from datetime import timedelta
from django.utils import timezone

from lot_tracking.models import LotBatch, SerialNumber, TraceabilityLog


def today():
    """Use Django's timezone-aware date to match model properties."""
    return timezone.now().date()


@pytest.mark.django_db
class TestLotAutoCode:
    def test_first(self, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        assert lot.lot_number == "LOT-00001"

    def test_increments(self, tenant, product, warehouse):
        LotBatch.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=1)
        l2 = LotBatch.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=1)
        assert l2.lot_number == "LOT-00002"

    def test_per_tenant(self, tenant, other_tenant):
        from catalog.models import Category, Product as P
        from warehousing.models import Warehouse as W
        cat = Category.objects.create(tenant=other_tenant, name="Cat2")
        p2 = P.objects.create(
            tenant=other_tenant, sku="PX", name="X", category=cat,
            purchase_cost=1, retail_price=2, status="active",
        )
        w2 = W.objects.create(tenant=other_tenant, name="W2")
        from catalog.models import Category as C2, Product as P2
        from warehousing.models import Warehouse as W2
        cat1 = C2.objects.create(tenant=tenant, name="Cat1")
        p1 = P2.objects.create(
            tenant=tenant, sku="PY", name="Y", category=cat1,
            purchase_cost=1, retail_price=2, status="active",
        )
        w1 = W2.objects.create(tenant=tenant, name="W1")
        LotBatch.objects.create(tenant=tenant, product=p1, warehouse=w1, quantity=1)
        l = LotBatch.objects.create(tenant=other_tenant, product=p2, warehouse=w2, quantity=1)
        assert l.lot_number == "LOT-00001"

    def test_explicit_lot_number_preserved(self, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            lot_number="CUSTOM-01", quantity=1,
        )
        assert lot.lot_number == "CUSTOM-01"


@pytest.mark.django_db
class TestTraceabilityAutoCode:
    def test_first(self, tenant, lot):
        log = TraceabilityLog.objects.create(
            tenant=tenant, lot=lot, event_type="adjusted", quantity=1,
        )
        assert log.log_number == "TRC-00001"

    def test_increments(self, tenant, lot):
        TraceabilityLog.objects.create(tenant=tenant, lot=lot, event_type="adjusted", quantity=1)
        l2 = TraceabilityLog.objects.create(tenant=tenant, lot=lot, event_type="adjusted", quantity=1)
        assert l2.log_number == "TRC-00002"


@pytest.mark.django_db
class TestLotProperties:
    def test_is_expired_true(self, lot):
        lot.expiry_date = today() - timedelta(days=1)
        lot.save()
        assert lot.is_expired is True

    def test_is_expired_false_when_status_already_expired(self, lot):
        lot.expiry_date = today() - timedelta(days=1)
        lot.status = "expired"
        lot.save()
        assert lot.is_expired is False

    def test_days_until_expiry_none_without_date(self, tenant, product, warehouse):
        lot = LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, quantity=1,
        )
        assert lot.days_until_expiry is None

    def test_days_until_expiry_negative(self, lot):
        lot.expiry_date = today() - timedelta(days=5)
        lot.save()
        assert lot.days_until_expiry == -5


@pytest.mark.django_db
class TestSerialProperties:
    def test_warranty_expired_true(self, serial):
        serial.warranty_expiry = today() - timedelta(days=1)
        serial.save()
        assert serial.is_warranty_expired is True

    def test_warranty_expired_false_when_future(self, serial):
        serial.warranty_expiry = today() + timedelta(days=30)
        serial.save()
        assert serial.is_warranty_expired is False

    def test_warranty_expired_none_when_no_date(self, serial):
        serial.warranty_expiry = None
        serial.save()
        assert serial.is_warranty_expired in (False, None)


LOT_OK = [
    ("active", "quarantine"), ("active", "expired"),
    ("active", "consumed"), ("active", "recalled"),
    ("quarantine", "active"), ("quarantine", "expired"),
    ("quarantine", "recalled"), ("expired", "recalled"),
]
LOT_BAD = [
    ("consumed", "active"), ("recalled", "active"),
    ("consumed", "recalled"), ("active", "active"),
    ("expired", "active"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", LOT_OK)
def test_lot_transition_allowed(lot, src, dst):
    lot.status = src
    assert lot.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", LOT_BAD)
def test_lot_transition_denied(lot, src, dst):
    lot.status = src
    assert not lot.can_transition_to(dst)


SERIAL_OK = [
    ("available", "allocated"), ("available", "sold"),
    ("available", "damaged"), ("available", "scrapped"),
    ("allocated", "available"), ("allocated", "sold"),
    ("allocated", "damaged"),
    ("sold", "returned"),
    ("returned", "available"), ("returned", "damaged"), ("returned", "scrapped"),
    ("damaged", "scrapped"),
]
SERIAL_BAD = [
    ("scrapped", "available"), ("sold", "available"),
    ("damaged", "available"), ("available", "returned"),
    ("scrapped", "damaged"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", SERIAL_OK)
def test_serial_transition_allowed(serial, src, dst):
    serial.status = src
    assert serial.can_transition_to(dst)


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", SERIAL_BAD)
def test_serial_transition_denied(serial, src, dst):
    serial.status = src
    assert not serial.can_transition_to(dst)
