"""Security — OWASP A01 (auth, IDOR), A03 (XSS), A05 (CSRF via GET)."""
import pytest
from django.urls import reverse

from stocktaking.models import StocktakeFreeze


@pytest.mark.django_db
class TestAuthn:
    @pytest.mark.parametrize('name,args', [
        ('stocktaking:count_list', []),
        ('stocktaking:count_create', []),
        ('stocktaking:freeze_list', []),
        ('stocktaking:freeze_create', []),
        ('stocktaking:schedule_list', []),
        ('stocktaking:schedule_create', []),
        ('stocktaking:adjustment_list', []),
        ('stocktaking:adjustment_create', []),
    ])
    def test_login_required(self, client, name, args):
        r = client.get(reverse(name, args=args))
        assert r.status_code == 302
        assert '/login' in r.url or 'accounts' in r.url


@pytest.mark.django_db
class TestCSRFviaGET:
    """D-01 — all 8 state-changing endpoints must reject GET."""
    @pytest.mark.parametrize('name', [
        'stocktaking:freeze_release',
        'stocktaking:schedule_run',
        'stocktaking:count_start',
        'stocktaking:count_review',
        'stocktaking:count_cancel',
        'stocktaking:adjustment_approve',
        'stocktaking:adjustment_reject',
        'stocktaking:adjustment_post',
    ])
    def test_state_mutation_rejects_get(self, client_admin, name):
        r = client_admin.get(reverse(name, args=[99999]))
        # Must be 405 (Method Not Allowed) — NOT 302 (redirect = happy path).
        # If it was 302 the view would have mutated state.
        assert r.status_code == 405, (
            f'D-01 regression: {name} accepts GET. '
            'State-changing views must be POST-only.'
        )


@pytest.mark.django_db
class TestXSS:
    def test_reason_escaped_in_freeze_list(
        self, client_admin, tenant, warehouse,
    ):
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse,
            reason='<script>alert(1)</script>',
        )
        r = client_admin.get(reverse('stocktaking:freeze_list'))
        assert b'<script>alert(1)</script>' not in r.content
        assert b'&lt;script&gt;' in r.content


@pytest.mark.django_db
class TestTenantIsolationList:
    def test_other_tenant_data_not_visible(
        self, client_other, freeze,
    ):
        r = client_other.get(reverse('stocktaking:freeze_list'))
        assert r.status_code == 200
        assert freeze.freeze_number.encode() not in r.content


@pytest.mark.django_db
class TestD19RBAC:
    """D-19 regression — non-admin tenant user must be blocked from
    destructive operations on all 4 entities. List/detail views remain
    accessible."""

    def test_non_admin_blocked_from_freeze_create(self, client_user):
        r = client_user.get(reverse('stocktaking:freeze_create'))
        assert r.status_code == 403

    def test_non_admin_blocked_from_freeze_release(self, client_user, freeze):
        r = client_user.post(reverse('stocktaking:freeze_release', args=[freeze.pk]))
        assert r.status_code == 403
        freeze.refresh_from_db()
        assert freeze.status == 'active'

    def test_non_admin_blocked_from_schedule_create(self, client_user):
        r = client_user.get(reverse('stocktaking:schedule_create'))
        assert r.status_code == 403

    def test_non_admin_blocked_from_schedule_run(
        self, client_user, schedule, stock_levels,
    ):
        from stocktaking.models import StockCount
        r = client_user.post(reverse('stocktaking:schedule_run', args=[schedule.pk]))
        assert r.status_code == 403
        assert not StockCount.objects.filter(schedule=schedule).exists()

    def test_non_admin_blocked_from_count_create(self, client_user):
        r = client_user.get(reverse('stocktaking:count_create'))
        assert r.status_code == 403

    def test_non_admin_blocked_from_count_delete(self, client_user, draft_count):
        from stocktaking.models import StockCount
        r = client_user.post(reverse('stocktaking:count_delete', args=[draft_count.pk]))
        assert r.status_code == 403
        assert StockCount.objects.filter(pk=draft_count.pk).exists()

    def test_non_admin_blocked_from_adjustment_approve(self, client_user, pending_adj):
        r = client_user.post(reverse('stocktaking:adjustment_approve', args=[pending_adj.pk]))
        assert r.status_code == 403
        pending_adj.refresh_from_db()
        assert pending_adj.status == 'pending'

    def test_non_admin_blocked_from_adjustment_post(self, client_user, approved_adj):
        r = client_user.post(reverse('stocktaking:adjustment_post', args=[approved_adj.pk]))
        assert r.status_code == 403
        approved_adj.refresh_from_db()
        assert approved_adj.status == 'approved'

    def test_non_admin_can_read_list(self, client_user):
        r = client_user.get(reverse('stocktaking:count_list'))
        assert r.status_code == 200

    def test_non_admin_can_read_detail(self, client_user, draft_count):
        r = client_user.get(reverse('stocktaking:count_detail', args=[draft_count.pk]))
        assert r.status_code == 200
