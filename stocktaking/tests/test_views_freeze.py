"""Freeze CRUD + POST-only release (D-01) + IDOR."""
import pytest
from django.urls import reverse

from stocktaking.models import StocktakeFreeze


@pytest.mark.django_db
class TestFreezeList:
    def test_list_loads(self, client_admin, freeze):
        r = client_admin.get(reverse('stocktaking:freeze_list'))
        assert r.status_code == 200
        assert freeze.freeze_number.encode() in r.content

    def test_filter_by_status(self, client_admin, tenant, warehouse, freeze):
        StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse, status='released',
        )
        r = client_admin.get(reverse('stocktaking:freeze_list'), {'status': 'released'})
        assert r.status_code == 200
        assert freeze.freeze_number.encode() not in r.content


@pytest.mark.django_db
class TestFreezeCreate:
    def test_create(self, client_admin, tenant, warehouse):
        r = client_admin.post(reverse('stocktaking:freeze_create'), {
            'warehouse': warehouse.pk, 'reason': 'EOY', 'notes': '',
        })
        assert r.status_code == 302
        f = StocktakeFreeze.objects.get(tenant=tenant)
        assert f.status == 'active'
        assert f.frozen_at is not None
        assert f.frozen_by is not None


@pytest.mark.django_db
class TestFreezeRelease:
    def test_release_requires_post(self, client_admin, freeze):
        """D-01 regression — release must reject GET."""
        url = reverse('stocktaking:freeze_release', args=[freeze.pk])
        r = client_admin.get(url)
        assert r.status_code == 405
        freeze.refresh_from_db()
        assert freeze.status == 'active'

    def test_release_via_post(self, client_admin, freeze):
        url = reverse('stocktaking:freeze_release', args=[freeze.pk])
        r = client_admin.post(url)
        assert r.status_code == 302
        freeze.refresh_from_db()
        assert freeze.status == 'released'
        assert freeze.released_at is not None

    def test_cannot_release_already_released(
        self, client_admin, tenant, warehouse,
    ):
        f = StocktakeFreeze.objects.create(
            tenant=tenant, warehouse=warehouse, status='released',
        )
        url = reverse('stocktaking:freeze_release', args=[f.pk])
        r = client_admin.post(url, follow=True)
        assert b'Freeze is not active' in r.content


@pytest.mark.django_db
class TestFreezeDelete:
    def test_delete(self, client_admin, freeze):
        url = reverse('stocktaking:freeze_delete', args=[freeze.pk])
        r = client_admin.post(url)
        assert r.status_code == 302
        assert not StocktakeFreeze.objects.filter(pk=freeze.pk).exists()

    def test_delete_get_is_noop(self, client_admin, freeze):
        url = reverse('stocktaking:freeze_delete', args=[freeze.pk])
        client_admin.get(url)
        assert StocktakeFreeze.objects.filter(pk=freeze.pk).exists()


@pytest.mark.django_db
class TestFreezeIdor:
    def test_cross_tenant_edit_404(self, client_other, freeze):
        r = client_other.get(reverse('stocktaking:freeze_edit', args=[freeze.pk]))
        assert r.status_code == 404

    def test_cross_tenant_release_404(self, client_other, freeze):
        r = client_other.post(reverse('stocktaking:freeze_release', args=[freeze.pk]))
        assert r.status_code == 404

    def test_cross_tenant_delete_404(self, client_other, freeze):
        r = client_other.post(reverse('stocktaking:freeze_delete', args=[freeze.pk]))
        assert r.status_code == 404
