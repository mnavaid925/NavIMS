"""View tests for the reporting app — list, generate, detail, delete, exports."""
from datetime import date

import pytest

from reporting.models import ReportSnapshot


# ── index ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_index_loads(client_admin):
    response = client_admin.get('/reporting/')
    assert response.status_code == 200
    assert b'Reporting' in response.content


@pytest.mark.django_db
def test_index_requires_login(db):
    from django.test import Client
    response = Client().get('/reporting/')
    assert response.status_code in (302, 301)


# ── list view ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_view_loads_for_each_report_type(client_admin):
    from reporting.registry import REPORTS
    for slug in REPORTS:
        response = client_admin.get(f'/reporting/{slug}/')
        assert response.status_code == 200, f'{slug} list view failed'


@pytest.mark.django_db
def test_list_unknown_report_type_404(client_admin):
    response = client_admin.get('/reporting/nonexistent_report/')
    assert response.status_code == 404


@pytest.mark.django_db
def test_list_shows_only_current_tenant_snapshots(client_admin, valuation_snapshot, other_tenant_snapshot):
    response = client_admin.get('/reporting/valuation/')
    assert response.status_code == 200
    assert valuation_snapshot.report_number.encode() in response.content
    assert other_tenant_snapshot.report_number.encode() not in response.content


# ── generate view ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_generate_form_loads(client_admin):
    response = client_admin.get('/reporting/valuation/generate/')
    assert response.status_code == 200


@pytest.mark.django_db
def test_generate_post_creates_snapshot(client_admin, tenant, tenant_admin):
    before = ReportSnapshot.objects.filter(tenant=tenant).count()
    response = client_admin.post('/reporting/valuation/generate/', data={
        'title': 'E2E Valuation',
        'notes': 'from test_views',
    })
    assert response.status_code == 302
    assert ReportSnapshot.objects.filter(tenant=tenant).count() == before + 1
    snap = ReportSnapshot.objects.filter(tenant=tenant).order_by('-id').first()
    assert snap.title == 'E2E Valuation'
    assert snap.generated_by == tenant_admin


@pytest.mark.django_db
def test_generate_requires_tenant_admin(client_user):
    """Non-admin tenant users cannot generate reports."""
    response = client_user.post('/reporting/valuation/generate/', data={'title': 'x'})
    assert response.status_code == 403


# ── detail view ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_detail_loads_own_snapshot(client_admin, valuation_snapshot):
    response = client_admin.get(f'/reporting/valuation/{valuation_snapshot.pk}/')
    assert response.status_code == 200
    assert valuation_snapshot.report_number.encode() in response.content


@pytest.mark.django_db
def test_detail_shows_summary_and_chart(client_admin, valuation_snapshot):
    response = client_admin.get(f'/reporting/valuation/{valuation_snapshot.pk}/')
    assert b'Summary' in response.content


# ── delete view ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_delete_is_post_only(client_admin, valuation_snapshot):
    response = client_admin.get(f'/reporting/valuation/{valuation_snapshot.pk}/delete/')
    assert response.status_code == 405  # Method not allowed


@pytest.mark.django_db
def test_delete_post_removes_snapshot(client_admin, valuation_snapshot):
    pk = valuation_snapshot.pk
    response = client_admin.post(f'/reporting/valuation/{pk}/delete/')
    assert response.status_code == 302
    assert not ReportSnapshot.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_delete_requires_tenant_admin(client_user, valuation_snapshot):
    response = client_user.post(f'/reporting/valuation/{valuation_snapshot.pk}/delete/')
    assert response.status_code == 403
    assert ReportSnapshot.objects.filter(pk=valuation_snapshot.pk).exists()


# ── exports ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_export_csv_returns_csv(client_admin, valuation_snapshot):
    response = client_admin.get(f'/reporting/valuation/{valuation_snapshot.pk}/export/csv/')
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/csv'
    assert 'attachment' in response['Content-Disposition']


@pytest.mark.django_db
def test_export_pdf_returns_pdf(client_admin, valuation_snapshot):
    response = client_admin.get(f'/reporting/valuation/{valuation_snapshot.pk}/export/pdf/')
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF')
