"""Management command — D-09 generate_expiry_alerts idempotency + dedup."""
import pytest
from datetime import timedelta
from io import StringIO
from django.core.management import call_command
from django.utils import timezone


def today():
    return timezone.now().date()

from lot_tracking.models import ExpiryAlert, LotBatch


@pytest.mark.django_db
class TestGenerateExpiryAlerts:
    def test_creates_expired_alert(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() - timedelta(days=1),
            lot_number="LOT-EXP-1",
        )
        call_command("generate_expiry_alerts", stdout=StringIO())
        assert ExpiryAlert.objects.filter(
            tenant=tenant, alert_type="expired",
        ).count() == 1

    def test_creates_approaching_alert(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() + timedelta(days=10),
            lot_number="LOT-APP-1",
        )
        call_command("generate_expiry_alerts", stdout=StringIO())
        assert ExpiryAlert.objects.filter(
            tenant=tenant, alert_type="approaching",
        ).count() == 1

    def test_idempotent_same_day(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() + timedelta(days=10),
            lot_number="LOT-IDEM",
        )
        call_command("generate_expiry_alerts", stdout=StringIO())
        call_command("generate_expiry_alerts", stdout=StringIO())
        assert ExpiryAlert.objects.filter(tenant=tenant).count() == 1

    def test_non_active_lots_ignored(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() - timedelta(days=1),
            status="recalled", lot_number="LOT-REC",
        )
        call_command("generate_expiry_alerts", stdout=StringIO())
        assert ExpiryAlert.objects.filter(tenant=tenant).count() == 0

    def test_beyond_horizon_ignored(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() + timedelta(days=90),
            lot_number="LOT-FAR",
        )
        call_command("generate_expiry_alerts", stdout=StringIO())
        assert ExpiryAlert.objects.filter(tenant=tenant).count() == 0

    def test_days_arg_widens_horizon(self, tenant, product, warehouse):
        LotBatch.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            quantity=1, expiry_date=today() + timedelta(days=90),
            lot_number="LOT-60",
        )
        call_command("generate_expiry_alerts", "--days=120", stdout=StringIO())
        assert ExpiryAlert.objects.filter(
            tenant=tenant, alert_type="approaching",
        ).count() == 1
