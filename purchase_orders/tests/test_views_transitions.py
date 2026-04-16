import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSubmit:
    def test_submit_with_items(self, client_logged_in, draft_po):
        client_logged_in.post(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'pending_approval'

    def test_submit_without_items_blocked(self, client_logged_in, draft_po):
        draft_po.items.all().delete()
        client_logged_in.post(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'

    def test_submit_must_be_POST(self, client_logged_in, draft_po):
        client_logged_in.get(
            reverse('purchase_orders:po_submit', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'


@pytest.mark.django_db
class TestApprove:
    def test_admin_approves_reaches_approved(
        self, client, pending_po, approver_user, approval_rule
    ):
        client.force_login(approver_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved', 'notes': 'ok'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'approved'

    def test_duplicate_approval_blocked(
        self, client, pending_po, approver_user, approval_rule
    ):
        client.force_login(approver_user)
        url = reverse('purchase_orders:po_approve', args=[pending_po.pk])
        client.post(url, {'decision': 'approved'})
        client.post(url, {'decision': 'approved'})
        assert pending_po.approvals.filter(approver=approver_user).count() == 1


@pytest.mark.django_db
class TestReject:
    def test_reject_returns_to_draft(
        self, client, pending_po, admin_user
    ):
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_reject', args=[pending_po.pk]),
            {'decision': 'rejected', 'notes': 'nope'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'draft'
        assert pending_po.approvals.filter(decision='rejected').count() == 1

    def test_invalid_reject_form_surfaces_error(
        self, client, pending_po, admin_user
    ):
        """Regression for D-13 — silent failure is unacceptable."""
        client.force_login(admin_user)
        # Missing `decision` field
        resp = client.post(
            reverse('purchase_orders:po_reject', args=[pending_po.pk]),
            {},
            follow=True,
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'pending_approval'  # unchanged
        # error message surfaced
        messages = [m.message for m in resp.context['messages']]
        assert any('invalid' in m.lower() or 'required' in m.lower() for m in messages)


@pytest.mark.django_db
class TestDispatchHappyPath:
    def test_dispatch_advances_status_on_email_success(
        self, client, approved_po, admin_user, settings
    ):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        from django.core import mail
        mail.outbox = []

        client.force_login(admin_user)
        resp = client.post(
            reverse('purchase_orders:po_dispatch', args=[approved_po.pk]),
            {'dispatch_method': 'email', 'notes': ''},
        )
        assert resp.status_code == 302
        approved_po.refresh_from_db()
        assert approved_po.status == 'sent'
        assert approved_po.dispatches.count() == 1
        assert approved_po.dispatches.first().sent_to_email == approved_po.vendor.email
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [approved_po.vendor.email]

    def test_dispatch_email_failure_does_not_advance_status(
        self, client, approved_po, admin_user, settings, monkeypatch
    ):
        """Regression for D-05."""
        client.force_login(admin_user)

        def boom(*a, **kw):
            raise RuntimeError('SMTP down')
        monkeypatch.setattr('purchase_orders.views.send_mail', boom)

        client.post(
            reverse('purchase_orders:po_dispatch', args=[approved_po.pk]),
            {'dispatch_method': 'email', 'notes': ''},
        )
        approved_po.refresh_from_db()
        assert approved_po.status == 'approved'  # unchanged
        assert approved_po.dispatches.count() == 0  # no partial commit


@pytest.mark.django_db
class TestTerminalTransitions:
    def test_sent_to_received(self, client, approved_po, admin_user, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_dispatch', args=[approved_po.pk]),
            {'dispatch_method': 'manual', 'notes': ''},
        )
        client.post(
            reverse('purchase_orders:po_mark_received', args=[approved_po.pk]))
        approved_po.refresh_from_db()
        assert approved_po.status == 'received'

    def test_received_to_closed(
        self, client, approved_po, admin_user
    ):
        approved_po.status = 'received'; approved_po.save()
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_close', args=[approved_po.pk]))
        approved_po.refresh_from_db()
        assert approved_po.status == 'closed'

    def test_closed_to_anything_blocked(
        self, client, approved_po, admin_user
    ):
        approved_po.status = 'closed'; approved_po.save()
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_cancel', args=[approved_po.pk]))
        approved_po.refresh_from_db()
        assert approved_po.status == 'closed'

    def test_cancel_reopen_round_trip(
        self, client, draft_po, admin_user
    ):
        client.force_login(admin_user)
        client.post(reverse('purchase_orders:po_cancel', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'cancelled'
        client.post(reverse('purchase_orders:po_reopen', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'
