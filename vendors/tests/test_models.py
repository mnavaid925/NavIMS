"""Model-level unit tests for the vendors module."""
import pytest
from datetime import date
from decimal import Decimal
from django.db import IntegrityError, transaction

from vendors.models import Vendor, VendorPerformance, VendorContract


@pytest.mark.django_db
class TestVendorModel:
    def test_str_returns_company_name(self, vendor):
        assert str(vendor) == "Acme Corp"

    def test_unique_together_tenant_company_name_rejected_at_db(self, tenant, vendor):
        with pytest.raises(IntegrityError), transaction.atomic():
            Vendor.objects.create(
                tenant=tenant, company_name="Acme Corp", status="active",
            )

    def test_same_company_name_across_tenants_allowed(self, tenant, other_tenant, vendor):
        clone = Vendor.objects.create(
            tenant=other_tenant, company_name="Acme Corp", status="active",
        )
        assert clone.pk != vendor.pk

    def test_average_performance_score_none_when_no_reviews(self, vendor):
        assert vendor.average_performance_score is None

    def test_average_performance_score_rounds_to_1_decimal(self, vendor, tenant):
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=5, quality_rating=5, compliance_rating=5,
        )  # 5.0
        VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=3, quality_rating=3, compliance_rating=3,
        )  # 3.0
        assert vendor.average_performance_score == 4.0


@pytest.mark.django_db
class TestPerformanceModel:
    def test_overall_score_rounds(self, performance):
        # (5+4+5)/3 = 4.6666... → 4.7
        assert performance.overall_score == 4.7

    @pytest.mark.parametrize("d,q,c,expected", [
        (5, 5, 5, 5.0),
        (1, 1, 1, 1.0),
        (3, 4, 5, 4.0),
        (5, 4, 4, 4.3),
    ])
    def test_overall_score_parametrised(self, tenant, vendor, d, q, c, expected):
        p = VendorPerformance.objects.create(
            tenant=tenant, vendor=vendor, review_date=date.today(),
            delivery_rating=d, quality_rating=q, compliance_rating=c,
        )
        assert p.overall_score == pytest.approx(expected, abs=0.05)

    def test_reviewed_by_set_null_on_user_delete(self, user, performance):
        user.delete()
        performance.refresh_from_db()
        assert performance.reviewed_by is None

    def test_db_check_constraint_rejects_zero_rating(self, tenant, vendor):
        """D-07 regression — zero ratings must be rejected at the DB layer."""
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorPerformance.objects.create(
                tenant=tenant, vendor=vendor, review_date=date.today(),
                delivery_rating=0, quality_rating=5, compliance_rating=5,
            )

    def test_db_check_constraint_rejects_rating_six(self, tenant, vendor):
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorPerformance.objects.create(
                tenant=tenant, vendor=vendor, review_date=date.today(),
                delivery_rating=5, quality_rating=6, compliance_rating=5,
            )

    def test_db_check_constraint_rejects_defect_rate_above_100(self, tenant, vendor):
        """D-04 + D-07 regression."""
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorPerformance.objects.create(
                tenant=tenant, vendor=vendor, review_date=date.today(),
                delivery_rating=5, quality_rating=5, compliance_rating=5,
                defect_rate=Decimal("150.00"),
            )


@pytest.mark.django_db
class TestContractModel:
    def test_unique_together_tenant_contract_number_rejected_at_db(self, contract):
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorContract.objects.create(
                tenant=contract.tenant, vendor=contract.vendor,
                contract_number="CON-001", title="dup",
                start_date=date.today(),
            )

    def test_db_check_constraint_rejects_negative_value(self, tenant, vendor):
        """D-17 regression."""
        with pytest.raises(IntegrityError), transaction.atomic():
            VendorContract.objects.create(
                tenant=tenant, vendor=vendor,
                contract_number="CON-NEG", title="neg",
                start_date=date.today(),
                contract_value=Decimal("-1.00"),
            )
