"""D-04: state-transition endpoints must refuse GET.

Django's ``@require_POST`` returns 405 for any non-POST method.  Critically, no
state change must occur on GET regardless of status code.
"""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


TRANSITION_URLS_RMA = [
    'rma_submit', 'rma_approve', 'rma_reject',
    'rma_receive', 'rma_close', 'rma_cancel', 'rma_delete',
]


@pytest.mark.parametrize('url_name', TRANSITION_URLS_RMA)
def test_get_on_rma_transition_returns_405_and_no_state_change(
    client_admin, draft_rma, url_name,
):
    before_status = draft_rma.status
    url = reverse(f'returns:{url_name}', args=[draft_rma.pk])
    resp = client_admin.get(url)
    assert resp.status_code == 405
    draft_rma.refresh_from_db()
    assert draft_rma.status == before_status


INSPECTION_URLS = ['inspection_start', 'inspection_complete', 'inspection_delete']


@pytest.mark.parametrize('url_name', INSPECTION_URLS)
def test_get_on_inspection_transition_returns_405(
    client_admin, inspection_in_progress, url_name,
):
    before_status = inspection_in_progress.status
    url = reverse(f'returns:{url_name}', args=[inspection_in_progress.pk])
    resp = client_admin.get(url)
    assert resp.status_code == 405
    inspection_in_progress.refresh_from_db()
    assert inspection_in_progress.status == before_status


DISPOSITION_URLS = ['disposition_process', 'disposition_cancel', 'disposition_delete']


@pytest.mark.parametrize('url_name', DISPOSITION_URLS)
def test_get_on_disposition_transition_returns_405(
    client_admin, disposition_pending_restock, url_name,
):
    before_status = disposition_pending_restock.status
    url = reverse(f'returns:{url_name}', args=[disposition_pending_restock.pk])
    resp = client_admin.get(url)
    assert resp.status_code == 405
    disposition_pending_restock.refresh_from_db()
    assert disposition_pending_restock.status == before_status


REFUND_URLS = ['refund_process', 'refund_fail', 'refund_cancel', 'refund_delete']


@pytest.mark.parametrize('url_name', REFUND_URLS)
def test_get_on_refund_transition_returns_405(client_admin, pending_refund, url_name):
    before_status = pending_refund.status
    url = reverse(f'returns:{url_name}', args=[pending_refund.pk])
    resp = client_admin.get(url)
    assert resp.status_code == 405
    pending_refund.refresh_from_db()
    assert pending_refund.status == before_status
