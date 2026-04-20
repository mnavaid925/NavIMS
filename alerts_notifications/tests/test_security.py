"""OWASP-aligned security tests — A01 cross-tenant IDOR, CSRF 405, RBAC 403."""
import pytest
from django.urls import reverse

from alerts_notifications.models import Alert, NotificationRule


# ── A01 Broken Access Control — Cross-tenant IDOR sweep ───────────────────

@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'alerts_notifications:alert_detail',
    'alerts_notifications:alert_edit',
])
def test_A01_cross_tenant_alert_get_404(client_admin, foreign_alert, url_name):
    r = client_admin.get(reverse(url_name, args=[foreign_alert.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'alerts_notifications:alert_acknowledge',
    'alerts_notifications:alert_resolve',
    'alerts_notifications:alert_dismiss',
    'alerts_notifications:alert_delete',
])
def test_A01_cross_tenant_alert_post_404(client_admin, foreign_alert, url_name):
    r = client_admin.post(reverse(url_name, args=[foreign_alert.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'alerts_notifications:rule_detail',
    'alerts_notifications:rule_edit',
])
def test_A01_cross_tenant_rule_get_404(client_admin, foreign_rule, url_name):
    r = client_admin.get(reverse(url_name, args=[foreign_rule.pk]))
    assert r.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', [
    'alerts_notifications:rule_delete',
    'alerts_notifications:rule_toggle_active',
])
def test_A01_cross_tenant_rule_post_404(client_admin, foreign_rule, url_name):
    r = client_admin.post(reverse(url_name, args=[foreign_rule.pk]))
    assert r.status_code == 404


# ── CSRF — @require_POST rejects GET on every mutation endpoint ──────────

@pytest.mark.django_db
@pytest.mark.parametrize('url_name,fixture_name', [
    ('alerts_notifications:alert_acknowledge', 'new_alert'),
    ('alerts_notifications:alert_resolve', 'acknowledged_alert'),
    ('alerts_notifications:alert_dismiss', 'new_alert'),
    ('alerts_notifications:alert_delete', 'new_alert'),
    ('alerts_notifications:rule_delete', 'rule'),
    ('alerts_notifications:rule_toggle_active', 'rule'),
])
def test_CSRF_get_on_post_endpoint_returns_405(client_admin, request, url_name, fixture_name):
    obj = request.getfixturevalue(fixture_name)
    r = client_admin.get(reverse(url_name, args=[obj.pk]))
    assert r.status_code == 405


# ── A01 RBAC — non-admin cannot mutate ───────────────────────────────────

@pytest.mark.django_db
def test_non_admin_cannot_create_alert(client_user):
    r = client_user.post(reverse('alerts_notifications:alert_create'), {
        'alert_type': 'low_stock', 'severity': 'warning', 'title': 'x',
    })
    assert r.status_code == 403


@pytest.mark.django_db
def test_non_admin_cannot_acknowledge(client_user, new_alert):
    r = client_user.post(reverse('alerts_notifications:alert_acknowledge', args=[new_alert.pk]))
    assert r.status_code == 403
    new_alert.refresh_from_db()
    assert new_alert.status == 'new'


@pytest.mark.django_db
def test_non_admin_cannot_create_rule(client_user):
    r = client_user.post(reverse('alerts_notifications:rule_create'), {
        'code': '', 'name': 'x',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'is_active': 'on',
    })
    assert r.status_code == 403


# ── A03 XSS via topbar JSON — escapeHtml() in place ──────────────────────

@pytest.mark.django_db
def test_A03_inbox_json_contains_escapeHtml_client_side(client_admin, new_alert):
    """Server returns raw JSON; escaping is the client's job via escapeHtml().

    Verify both: (a) JSON contains the literal string (no server-side escape),
    (b) templates/partials/topbar.html calls escapeHtml on every tainted field.
    """
    from pathlib import Path
    new_alert.title = '<script>alert(1)</script>'
    new_alert.save()
    r = client_admin.get(reverse('alerts_notifications:alert_inbox_json'))
    data = r.json()
    assert '<script>' in data['items'][0]['title']
    topbar = Path('templates/partials/topbar.html').read_text(encoding='utf-8')
    assert 'escapeHtml' in topbar
    # Ensure every user-tainted value is passed through escapeHtml
    assert 'escapeHtml(a.title)' in topbar
    assert 'escapeHtml(a.alert_number)' in topbar
    assert 'escapeHtml(a.alert_type_display)' in topbar


# ── A09 Logging — emit_audit on every mutation ──────────────────────────

@pytest.mark.django_db
def test_A09_acknowledge_emits_audit(client_admin, new_alert):
    from core.models import AuditLog
    before = AuditLog.objects.filter(model_name='Alert', object_id=str(new_alert.pk)).count()
    client_admin.post(reverse('alerts_notifications:alert_acknowledge', args=[new_alert.pk]))
    after = AuditLog.objects.filter(model_name='Alert', object_id=str(new_alert.pk)).count()
    assert after == before + 1
