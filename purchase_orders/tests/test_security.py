import pytest
from django.urls import reverse

from core.models import AuditLog


@pytest.mark.django_db
class TestLoginRequired:
    @pytest.mark.parametrize("url_name,args", [
        ('purchase_orders:po_list', []),
        ('purchase_orders:po_create', []),
        ('purchase_orders:approval_rule_list', []),
        ('purchase_orders:approval_list', []),
    ])
    def test_anonymous_redirected_to_login(self, client, url_name, args):
        resp = client.get(reverse(url_name, args=args))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp['Location']


@pytest.mark.django_db
class TestRBAC:
    """Regression for D-02 — non-admin cannot trigger sensitive state changes."""

    def test_non_admin_cannot_approve(
        self, client, non_admin_user, pending_po, approval_rule
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'pending_approval'
        assert pending_po.approvals.filter(approver=non_admin_user).count() == 0

    def test_non_admin_cannot_reject(
        self, client, non_admin_user, pending_po
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('purchase_orders:po_reject', args=[pending_po.pk]),
            {'decision': 'rejected'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'pending_approval'

    def test_non_admin_cannot_cancel(
        self, client, non_admin_user, draft_po
    ):
        client.force_login(non_admin_user)
        client.post(reverse('purchase_orders:po_cancel', args=[draft_po.pk]))
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'

    def test_non_admin_cannot_dispatch(
        self, client, non_admin_user, approved_po
    ):
        client.force_login(non_admin_user)
        client.post(
            reverse('purchase_orders:po_dispatch', args=[approved_po.pk]),
            {'dispatch_method': 'manual', 'notes': ''},
        )
        approved_po.refresh_from_db()
        assert approved_po.status == 'approved'


@pytest.mark.django_db
class TestSelfApprovalBlocked:
    """Regression for D-03 — PO creator cannot approve their own PO."""

    def test_creator_cannot_self_approve(
        self, client, admin_user, pending_po, approval_rule
    ):
        # admin_user is the creator (see `draft_po` fixture)
        assert pending_po.created_by_id == admin_user.id
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved', 'notes': 'me'},
        )
        pending_po.refresh_from_db()
        assert pending_po.status == 'pending_approval'
        assert pending_po.approvals.filter(approver=admin_user).count() == 0


@pytest.mark.django_db
class TestDataExfilBlocked:
    """Regression for D-04 — dispatch cannot target arbitrary external email."""

    def test_attacker_email_ignored_server_pins_vendor_email(
        self, client, admin_user, approved_po, settings
    ):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        from django.core import mail
        mail.outbox = []
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:po_dispatch', args=[approved_po.pk]),
            {
                'dispatch_method': 'email',
                'sent_to_email': 'attacker@evil.example',  # malicious input
                'notes': '',
            },
        )
        approved_po.refresh_from_db()
        dispatch = approved_po.dispatches.first()
        assert dispatch is not None
        # Recipient is the vendor email, NOT the attacker input
        assert dispatch.sent_to_email == approved_po.vendor.email
        assert 'attacker@evil.example' not in dispatch.sent_to_email
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [approved_po.vendor.email]


@pytest.mark.django_db
class TestCrossTenantIDOR:
    def test_cross_tenant_rule_delete_404(
        self, client, admin_user, other_tenant
    ):
        from purchase_orders.models import ApprovalRule
        rule = ApprovalRule.objects.create(
            tenant=other_tenant, name="X",
            min_amount=0, max_amount=100, required_approvals=1,
        )
        client.force_login(admin_user)
        client.post(
            reverse('purchase_orders:approval_rule_delete', args=[rule.pk]))
        assert ApprovalRule.objects.filter(pk=rule.pk).exists()


@pytest.mark.django_db
class TestCSRFAndMethods:
    @pytest.mark.parametrize("url_name", [
        'purchase_orders:po_submit', 'purchase_orders:po_approve',
        'purchase_orders:po_reject', 'purchase_orders:po_mark_received',
        'purchase_orders:po_close', 'purchase_orders:po_cancel',
        'purchase_orders:po_reopen', 'purchase_orders:po_delete',
    ])
    def test_get_on_transition_is_safe(
        self, client, admin_user, draft_po, url_name
    ):
        client.force_login(admin_user)
        resp = client.get(reverse(url_name, args=[draft_po.pk]))
        assert resp.status_code == 302
        draft_po.refresh_from_db()
        assert draft_po.status == 'draft'


@pytest.mark.django_db
class TestXSS:
    def test_notes_escaped_on_detail(self, client_logged_in, draft_po):
        draft_po.notes = '<script>alert(1)</script>'
        draft_po.save()
        resp = client_logged_in.get(
            reverse('purchase_orders:po_detail', args=[draft_po.pk]))
        assert b'<script>alert(1)</script>' not in resp.content
        assert b'&lt;script&gt;' in resp.content


@pytest.mark.django_db
class TestAuditLog:
    """Regression for D-12 — forensic trail on every sensitive mutation."""

    def test_approve_writes_audit(
        self, client, pending_po, approver_user, approval_rule
    ):
        client.force_login(approver_user)
        client.post(
            reverse('purchase_orders:po_approve', args=[pending_po.pk]),
            {'decision': 'approved'},
        )
        assert AuditLog.objects.filter(
            action='po.approve',
            object_id=str(pending_po.pk),
        ).exists()

    def test_cancel_writes_audit(self, client, admin_user, draft_po):
        client.force_login(admin_user)
        client.post(reverse('purchase_orders:po_cancel', args=[draft_po.pk]))
        assert AuditLog.objects.filter(
            action='po.cancel',
            object_id=str(draft_po.pk),
        ).exists()

    def test_delete_writes_audit(self, client, admin_user, draft_po):
        pk = draft_po.pk
        client.force_login(admin_user)
        client.post(reverse('purchase_orders:po_delete', args=[pk]))
        assert AuditLog.objects.filter(
            action='po.delete', object_id=str(pk),
        ).exists()
