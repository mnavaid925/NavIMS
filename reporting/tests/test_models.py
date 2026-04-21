"""Tests for `reporting.models.ReportSnapshot`."""
from datetime import date
from decimal import Decimal

import pytest

from reporting.models import ReportSnapshot


@pytest.mark.django_db
def test_report_number_auto_generated(tenant, tenant_admin):
    snap = ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='t1',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    assert snap.report_number.startswith('RPT-')
    assert len(snap.report_number) == 9  # RPT-00001


@pytest.mark.django_db
def test_report_number_increments_within_tenant(tenant, tenant_admin):
    a = ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='a',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    b = ReportSnapshot.objects.create(
        tenant=tenant, report_type='aging', title='b',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    assert a.report_number == 'RPT-00001'
    assert b.report_number == 'RPT-00002'


@pytest.mark.django_db
def test_report_number_numbered_per_tenant(tenant, other_tenant, tenant_admin, other_tenant_admin):
    """Each tenant's sequence is independent — both start at RPT-00001."""
    a = ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='t1',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    b = ReportSnapshot.objects.create(
        tenant=other_tenant, report_type='valuation', title='ot1',
        parameters={}, summary={}, data={}, generated_by=other_tenant_admin,
    )
    assert a.report_number == 'RPT-00001'
    assert b.report_number == 'RPT-00001'


@pytest.mark.django_db
def test_str_shows_number_and_title(tenant, tenant_admin):
    snap = ReportSnapshot.objects.create(
        tenant=tenant, report_type='abc', title='ABC X',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    s = str(snap)
    assert 'RPT-00001' in s and 'ABC X' in s


@pytest.mark.django_db
def test_unique_together_tenant_report_number(tenant, tenant_admin):
    """Two snapshots in the same tenant cannot share a report_number."""
    ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='t1', report_number='RPT-00100',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    with pytest.raises(Exception):
        ReportSnapshot.objects.create(
            tenant=tenant, report_type='aging', title='t2', report_number='RPT-00100',
            parameters={}, summary={}, data={}, generated_by=tenant_admin,
        )


@pytest.mark.django_db
def test_ordering_newest_first(tenant, tenant_admin):
    a = ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='a',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    b = ReportSnapshot.objects.create(
        tenant=tenant, report_type='aging', title='b',
        parameters={}, summary={}, data={}, generated_by=tenant_admin,
    )
    ids = list(ReportSnapshot.objects.values_list('pk', flat=True))
    assert ids.index(b.pk) < ids.index(a.pk)


@pytest.mark.django_db
def test_json_fields_persist_dicts_and_lists(tenant, tenant_admin):
    snap = ReportSnapshot.objects.create(
        tenant=tenant, report_type='valuation', title='t1',
        parameters={'as_of': '2026-04-21', 'filter': {'cat': 'A'}},
        summary={'total_value': '1000.00'},
        data={'columns': ['sku', 'value'], 'rows': [{'sku': 'X', 'value': '10'}]},
        generated_by=tenant_admin,
    )
    snap.refresh_from_db()
    assert snap.parameters['filter'] == {'cat': 'A'}
    assert snap.data['rows'][0]['sku'] == 'X'
