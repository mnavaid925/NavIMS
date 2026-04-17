"""D-23: admin list views must not leak cross-tenant rows.

Tenant admins browsing `/admin/returns/...` must only see rows from their own
tenant. Superusers continue to see every tenant's data.
"""
import pytest
from django.test import RequestFactory

from returns.admin import (
    ReturnAuthorizationAdmin, ReturnInspectionAdmin,
    DispositionAdmin, RefundCreditAdmin,
)
from returns.models import (
    ReturnAuthorization, ReturnInspection, Disposition, RefundCredit,
)


pytestmark = pytest.mark.django_db


def _req(user):
    rf = RequestFactory()
    req = rf.get('/admin/returns/')
    req.user = user
    return req


class TestRMAAdminTenantScope:
    def test_tenant_admin_only_sees_own_tenant_rmas(
        self, tenant_admin, draft_rma, other_draft_rma,
    ):
        admin = ReturnAuthorizationAdmin(ReturnAuthorization, None)
        qs = admin.get_queryset(_req(tenant_admin))
        assert draft_rma in qs
        assert other_draft_rma not in qs

    def test_non_tenant_user_sees_nothing(
        self, db, draft_rma, django_user_model,
    ):
        """A user without a tenant (and non-superuser) sees an empty queryset."""
        from core.models import User
        orphan = User.objects.create_user(username='orphan', password='x')
        admin = ReturnAuthorizationAdmin(ReturnAuthorization, None)
        qs = admin.get_queryset(_req(orphan))
        assert qs.count() == 0

    def test_superuser_sees_all(self, db, draft_rma, other_draft_rma):
        from core.models import User
        su = User.objects.create_superuser(username='su', password='x', email='su@x.com')
        admin = ReturnAuthorizationAdmin(ReturnAuthorization, None)
        qs = admin.get_queryset(_req(su))
        assert draft_rma in qs
        assert other_draft_rma in qs


class TestOtherAdminsTenantScope:
    def test_inspection_admin_scoped(
        self, tenant_admin, inspection_in_progress, other_tenant, other_draft_rma,
    ):
        other_insp = ReturnInspection.objects.create(
            tenant=other_tenant, rma=other_draft_rma, status='pending',
        )
        admin = ReturnInspectionAdmin(ReturnInspection, None)
        qs = admin.get_queryset(_req(tenant_admin))
        assert inspection_in_progress in qs
        assert other_insp not in qs

    def test_disposition_admin_scoped(
        self, tenant_admin, disposition_pending_restock,
        other_tenant, other_warehouse, other_draft_rma,
    ):
        # Move other_draft_rma to 'received' so we can legally create a disposition for it.
        other_draft_rma.status = 'received'
        other_draft_rma.save()
        other_disp = Disposition.objects.create(
            tenant=other_tenant, rma=other_draft_rma,
            decision='restock', warehouse=other_warehouse, status='pending',
        )
        admin = DispositionAdmin(Disposition, None)
        qs = admin.get_queryset(_req(tenant_admin))
        assert disposition_pending_restock in qs
        assert other_disp not in qs

    def test_refund_admin_scoped(
        self, tenant_admin, pending_refund, other_tenant, other_draft_rma,
    ):
        other_draft_rma.status = 'received'
        other_draft_rma.save()
        from decimal import Decimal
        other_refund = RefundCredit.objects.create(
            tenant=other_tenant, rma=other_draft_rma,
            amount=Decimal('1'), currency='USD',
        )
        admin = RefundCreditAdmin(RefundCredit, None)
        qs = admin.get_queryset(_req(tenant_admin))
        assert pending_refund in qs
        assert other_refund not in qs
