"""OWASP A01 (IDOR + authn), A05 (CSRF/require_POST), A08 (formset tenant injection).

Guards against:
    - Cross-tenant edit/delete (IDOR via predictable pk).
    - State-transition endpoints that accept GET (would let any link mutate state).
    - Non-admin users mutating data (RBAC regression).
    - Unauthenticated users bypassing @login_required.
    - Formset-level tenant forgery (parallel to lesson #9 / D-11 / D-14).
    - Cross-tenant FK forgery on form POST (template from another tenant).
"""
import pytest
from django.urls import reverse

from barcode_rfid.models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice,
    RFIDTag, RFIDReader,
    BatchScanSession, BatchScanItem,
)


# ── Cross-tenant IDOR — edit ─────────────────────────────────────

@pytest.mark.django_db
class TestCrossTenantEditBlocked:
    def test_label_template_edit_blocked(self, client_other, label_template):
        r = client_other.post(reverse('barcode_rfid:label_template_edit', args=[label_template.pk]), {
            'name': 'Hacked', 'code': 'LBL-STD',
            'label_type': 'barcode', 'symbology': 'code128', 'paper_size': 'label_medium',
            'width_mm': 60, 'height_mm': 40, 'copies_per_label': 1,
        })
        assert r.status_code == 404
        label_template.refresh_from_db()
        assert label_template.name != 'Hacked'

    def test_label_job_edit_blocked(self, client_other, print_job):
        r = client_other.post(reverse('barcode_rfid:label_job_edit', args=[print_job.pk]), {
            'template': print_job.template_id,
            'target_type': 'product', 'target_display': 'hacked', 'quantity': 1, 'notes': '',
        })
        assert r.status_code == 404

    def test_scanner_device_edit_blocked(self, client_other, scanner_device):
        r = client_other.post(reverse('barcode_rfid:device_edit', args=[scanner_device.pk]), {
            'device_code': 'SCAN-001', 'name': 'Hacked',
            'device_type': 'handheld',
            'manufacturer': '', 'model_number': '', 'os_version': '', 'firmware_version': '',
            'status': 'active', 'is_active': True,
        })
        assert r.status_code == 404

    def test_rfid_tag_edit_blocked(self, client_other, rfid_tag):
        r = client_other.post(reverse('barcode_rfid:rfid_tag_edit', args=[rfid_tag.pk]), {
            'epc_code': 'E200001', 'tag_type': 'passive', 'frequency_band': 'uhf',
            'linked_object_type': 'none', 'status': 'unassigned', 'notes': 'hacked',
        })
        assert r.status_code == 404

    def test_rfid_reader_edit_blocked(self, client_other, rfid_reader):
        r = client_other.post(reverse('barcode_rfid:rfid_reader_edit', args=[rfid_reader.pk]), {
            'reader_code': 'RDR-01', 'name': 'Hacked',
            'reader_type': 'fixed_gate', 'warehouse': rfid_reader.warehouse_id,
            'antenna_count': 1, 'frequency_band': 'uhf',
            'status': 'online', 'firmware_version': '', 'is_active': True,
        })
        assert r.status_code == 404

    def test_batch_session_edit_blocked(self, client_other, batch_session):
        r = client_other.post(reverse('barcode_rfid:batch_session_edit', args=[batch_session.pk]), {
            'purpose': 'receiving', 'warehouse': batch_session.warehouse_id, 'notes': 'hacked',
        })
        assert r.status_code == 404


# ── Cross-tenant IDOR — delete ───────────────────────────────────

@pytest.mark.django_db
class TestCrossTenantDeleteBlocked:
    def test_label_template_delete_blocked(self, client_other, label_template):
        r = client_other.post(reverse('barcode_rfid:label_template_delete', args=[label_template.pk]))
        assert r.status_code == 404
        assert LabelTemplate.objects.filter(pk=label_template.pk).exists()

    def test_rfid_tag_delete_blocked(self, client_other, rfid_tag):
        r = client_other.post(reverse('barcode_rfid:rfid_tag_delete', args=[rfid_tag.pk]))
        assert r.status_code == 404
        assert RFIDTag.objects.filter(pk=rfid_tag.pk).exists()

    def test_batch_session_delete_blocked(self, client_other, batch_session):
        r = client_other.post(reverse('barcode_rfid:batch_session_delete', args=[batch_session.pk]))
        assert r.status_code == 404
        assert BatchScanSession.objects.filter(pk=batch_session.pk).exists()


# ── State-transition endpoints require POST ──────────────────────

@pytest.mark.django_db
class TestTransitionsRequirePOST:
    @pytest.mark.parametrize('name', [
        'barcode_rfid:label_job_queue',
        'barcode_rfid:label_job_start_printing',
        'barcode_rfid:label_job_mark_printed',
        'barcode_rfid:label_job_cancel',
        'barcode_rfid:rfid_tag_activate',
        'barcode_rfid:rfid_tag_deactivate',
        'barcode_rfid:rfid_tag_retire',
        'barcode_rfid:batch_session_complete',
        'barcode_rfid:batch_session_cancel',
        'barcode_rfid:device_rotate_token',
    ])
    def test_get_rejected_405(self, client_admin, name):
        # Use an arbitrary pk — the `require_POST` decorator fires before get_object_or_404.
        r = client_admin.get(reverse(name, args=[999999]))
        assert r.status_code == 405


# ── RBAC — non-admin tenant user blocked ─────────────────────────

@pytest.mark.django_db
class TestRBAC:
    def test_non_admin_blocked_from_template_create(self, client_user):
        r = client_user.get(reverse('barcode_rfid:label_template_create'))
        assert r.status_code == 403

    def test_non_admin_blocked_from_template_delete(self, client_user, label_template):
        r = client_user.post(reverse('barcode_rfid:label_template_delete', args=[label_template.pk]))
        assert r.status_code == 403
        assert LabelTemplate.objects.filter(pk=label_template.pk).exists()

    def test_non_admin_blocked_from_tag_create(self, client_user):
        r = client_user.post(reverse('barcode_rfid:rfid_tag_create'), {
            'epc_code': 'E200X', 'tag_type': 'passive', 'frequency_band': 'uhf',
            'linked_object_type': 'none', 'status': 'unassigned',
        })
        assert r.status_code == 403

    def test_non_admin_blocked_from_tag_activate(self, client_user, rfid_tag):
        r = client_user.post(reverse('barcode_rfid:rfid_tag_activate', args=[rfid_tag.pk]))
        assert r.status_code == 403
        rfid_tag.refresh_from_db()
        assert rfid_tag.status == 'unassigned'

    def test_non_admin_blocked_from_session_complete(self, client_user, batch_session):
        r = client_user.post(reverse('barcode_rfid:batch_session_complete', args=[batch_session.pk]))
        assert r.status_code == 403
        batch_session.refresh_from_db()
        assert batch_session.status == 'active'

    def test_non_admin_blocked_from_rotate_token(self, client_user, scanner_device):
        old = scanner_device.api_token
        r = client_user.post(reverse('barcode_rfid:device_rotate_token', args=[scanner_device.pk]))
        assert r.status_code == 403
        scanner_device.refresh_from_db()
        assert scanner_device.api_token == old

    def test_non_admin_can_read_list(self, client_user):
        r = client_user.get(reverse('barcode_rfid:label_template_list'))
        assert r.status_code == 200


# ── Anonymous user blocked ───────────────────────────────────────

@pytest.mark.django_db
class TestAnonymousBlocked:
    @pytest.mark.parametrize('name', [
        'barcode_rfid:label_template_list',
        'barcode_rfid:label_job_list',
        'barcode_rfid:device_list',
        'barcode_rfid:rfid_tag_list',
        'barcode_rfid:batch_session_list',
    ])
    def test_anon_redirected_to_login(self, client_anonymous, name):
        r = client_anonymous.get(reverse(name))
        assert r.status_code == 302
        assert '/accounts/login/' in r.url or '/login' in r.url


# ── Formset & cross-tenant FK injection ──────────────────────────

@pytest.mark.django_db
class TestFormsetTenantInjection:
    def test_batch_item_tenant_injection_forced_to_session_tenant(
        self, client_admin, tenant, other_tenant, batch_session,
    ):
        """View loops over formset.save(commit=False) and sets item.tenant = tenant.
        Even if the attacker tries to spoof tenant in the POST, the view must
        overwrite it with the session's tenant."""
        payload = {
            'purpose': 'receiving', 'warehouse': batch_session.warehouse_id,
            'notes': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-scanned_value': 'FORGE',
            'items-0-symbology': '',
            'items-0-resolution_type': 'unmatched',
            'items-0-resolved_object_id': '',
            'items-0-resolved_display': '',
            'items-0-quantity': '1.00',
            # The form has no 'tenant' field — but even if a crafted payload included
            # tenant=other_tenant.pk, it's not bound to the form. The view forcibly
            # overrides with `item.tenant = tenant` anyway. Verify the invariant.
            'items-0-tenant': str(other_tenant.pk),
        }
        r = client_admin.post(
            reverse('barcode_rfid:batch_session_edit', args=[batch_session.pk]),
            payload,
        )
        assert r.status_code == 302
        item = BatchScanItem.objects.get(session=batch_session, scanned_value='FORGE')
        assert item.tenant_id == tenant.pk
        assert item.tenant_id != other_tenant.pk

    def test_template_fk_from_other_tenant_rejected(
        self, client_admin, tenant, other_label_template,
    ):
        """Posting a template FK that belongs to another tenant must fail
        form validation because the queryset is tenant-scoped."""
        r = client_admin.post(reverse('barcode_rfid:label_job_create'), {
            'template': other_label_template.pk,
            'target_type': 'product', 'target_display': 'x', 'quantity': 1, 'notes': '',
        })
        # Form invalid → 200 with form errors, job NOT created.
        assert r.status_code == 200
        assert not LabelPrintJob.objects.filter(
            tenant=tenant, template=other_label_template,
        ).exists()


# ── Zone cross-warehouse guard regression ────────────────────────

@pytest.mark.django_db
class TestZoneFromDifferentWarehouseRejected:
    def test_rfid_reader_create_rejects_mismatched_zone(self, client_admin, tenant, warehouse):
        from warehousing.models import Warehouse, Zone
        wh2 = Warehouse.objects.create(tenant=tenant, code='WH2', name='W2', is_active=True)
        z2 = Zone.objects.create(tenant=tenant, warehouse=wh2, code='Z2', name='Zone 2')
        r = client_admin.post(reverse('barcode_rfid:rfid_reader_create'), {
            'reader_code': 'RDR-X', 'name': 'X',
            'reader_type': 'fixed_gate', 'warehouse': warehouse.pk, 'zone': z2.pk,
            'antenna_count': 1, 'frequency_band': 'uhf',
            'status': 'online', 'firmware_version': '', 'is_active': True,
        })
        assert r.status_code == 200  # re-rendered with errors
        assert not RFIDReader.objects.filter(tenant=tenant, reader_code='RDR-X').exists()
