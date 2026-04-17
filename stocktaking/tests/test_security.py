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
