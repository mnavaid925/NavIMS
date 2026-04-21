"""Security tests — cross-tenant IDOR, RBAC, CSRF / @require_POST."""
import pytest

from reporting.models import ReportSnapshot


# ── cross-tenant IDOR ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cross_tenant_detail_returns_404(client_admin, other_tenant_snapshot):
    """Tenant A cannot view Tenant B's snapshot even with the correct report_type."""
    response = client_admin.get(
        f'/reporting/valuation/{other_tenant_snapshot.pk}/'
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_cross_tenant_delete_returns_404(client_admin, other_tenant_snapshot):
    """Tenant A cannot delete Tenant B's snapshot."""
    response = client_admin.post(
        f'/reporting/valuation/{other_tenant_snapshot.pk}/delete/'
    )
    assert response.status_code == 404
    # Row still exists
    assert ReportSnapshot.objects.filter(pk=other_tenant_snapshot.pk).exists()


@pytest.mark.django_db
def test_cross_tenant_csv_returns_404(client_admin, other_tenant_snapshot):
    response = client_admin.get(
        f'/reporting/valuation/{other_tenant_snapshot.pk}/export/csv/'
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_cross_tenant_pdf_returns_404(client_admin, other_tenant_snapshot):
    response = client_admin.get(
        f'/reporting/valuation/{other_tenant_snapshot.pk}/export/pdf/'
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_wrong_report_type_for_existing_snapshot_returns_404(client_admin, valuation_snapshot):
    """A valid snapshot pk under the wrong report_type slug must 404."""
    response = client_admin.get(
        f'/reporting/abc/{valuation_snapshot.pk}/'
    )
    assert response.status_code == 404


# ── RBAC: non-admin users cannot mutate ───────────────────────────────────

@pytest.mark.django_db
def test_non_admin_cannot_generate(client_user):
    response = client_user.post('/reporting/valuation/generate/', data={'title': 'x'})
    assert response.status_code == 403


@pytest.mark.django_db
def test_non_admin_cannot_delete(client_user, valuation_snapshot):
    response = client_user.post(
        f'/reporting/valuation/{valuation_snapshot.pk}/delete/'
    )
    assert response.status_code == 403
    assert ReportSnapshot.objects.filter(pk=valuation_snapshot.pk).exists()


@pytest.mark.django_db
def test_non_admin_can_read_list_and_detail(client_user, valuation_snapshot):
    """Reads are open to tenant users — only destructive ops are gated."""
    assert client_user.get('/reporting/valuation/').status_code == 200
    assert client_user.get(
        f'/reporting/valuation/{valuation_snapshot.pk}/'
    ).status_code == 200


# ── anonymous user blocked ────────────────────────────────────────────────

@pytest.mark.django_db
def test_anonymous_redirected_to_login(db, valuation_snapshot):
    from django.test import Client
    r1 = Client().get('/reporting/')
    r2 = Client().get(f'/reporting/valuation/{valuation_snapshot.pk}/')
    assert r1.status_code in (301, 302)
    assert r2.status_code in (301, 302)


# ── @require_POST: GET must not delete ────────────────────────────────────

@pytest.mark.django_db
def test_get_on_delete_endpoint_returns_405(client_admin, valuation_snapshot):
    response = client_admin.get(
        f'/reporting/valuation/{valuation_snapshot.pk}/delete/'
    )
    assert response.status_code == 405
    # Row still exists
    assert ReportSnapshot.objects.filter(pk=valuation_snapshot.pk).exists()
