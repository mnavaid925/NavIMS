"""Form-layer tests — tenant injection, clean_code, cross-tenant M2M guard, notes cap."""
import pytest

from alerts_notifications.forms import AlertForm, AlertResolveForm, NotificationRuleForm
from alerts_notifications.models import NotificationRule


@pytest.mark.django_db
def test_alert_form_tenant_scoped_product_queryset(tenant, product, other_product):
    form = AlertForm(tenant=tenant)
    # Product queryset filtered to current tenant
    pks = list(form.fields['product'].queryset.values_list('pk', flat=True))
    assert product.pk in pks
    assert other_product.pk not in pks


@pytest.mark.django_db
def test_alert_form_rejects_cross_tenant_product(tenant, other_product):
    form = AlertForm(data={
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'probe', 'message': '',
        'product': other_product.pk, 'warehouse': '',
    }, tenant=tenant)
    assert not form.is_valid()
    assert 'product' in form.errors


@pytest.mark.django_db
def test_alert_form_happy_path(tenant, product, warehouse):
    form = AlertForm(data={
        'alert_type': 'low_stock', 'severity': 'warning',
        'title': 'probe', 'message': '',
        'product': product.pk, 'warehouse': warehouse.pk,
    }, tenant=tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_rule_form_auto_code_on_blank(tenant, tenant_admin):
    form = NotificationRuleForm(data={
        'code': '', 'name': 'X', 'description': '',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'notify_email': 'on', 'notify_inbox': 'on',
        'is_active': 'on',
    }, tenant=tenant)
    assert form.is_valid(), form.errors
    obj = form.save()
    assert obj.code.startswith('NR-')


@pytest.mark.django_db
def test_rule_form_rejects_cross_tenant_recipients(tenant, other_tenant_admin):
    form = NotificationRuleForm(data={
        'code': '', 'name': 'X',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'recipient_users': [other_tenant_admin.pk],
        'is_active': 'on',
    }, tenant=tenant)
    assert not form.is_valid()
    assert 'recipient_users' in form.errors


@pytest.mark.django_db
def test_rule_form_unique_code_enforced_at_form_layer(tenant):
    NotificationRule.objects.create(tenant=tenant, code='NR-99999', name='Existing', alert_type='low_stock')
    form = NotificationRuleForm(data={
        'code': 'NR-99999', 'name': 'Dup',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'is_active': 'on',
    }, tenant=tenant)
    assert not form.is_valid()
    assert 'code' in form.errors


@pytest.mark.django_db
def test_rule_form_duplicate_code_allowed_across_tenants(tenant, other_tenant):
    NotificationRule.objects.create(tenant=tenant, code='NR-00001', name='A', alert_type='low_stock')
    form = NotificationRuleForm(data={
        'code': 'NR-00001', 'name': 'B',
        'alert_type': 'low_stock', 'min_severity': 'warning',
        'is_active': 'on',
    }, tenant=other_tenant)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_resolve_form_rejects_oversize_notes(tenant):
    """D-04: AlertResolveForm.notes enforces max_length=2000 at form layer."""
    form = AlertResolveForm(data={'notes': 'x' * 2001})
    assert not form.is_valid()
    assert 'notes' in form.errors
