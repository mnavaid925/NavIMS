from decimal import Decimal

import pytest
from django.urls import reverse

from inventory.models import StockAdjustment, StockLevel
from returns.models import (
    Disposition, DispositionItem, ReturnInspectionItem,
)


pytestmark = pytest.mark.django_db


class TestDispositionProcessRestock:
    def test_restock_creates_stock_adjustment_and_increments_on_hand(
        self, client_admin, tenant, product, warehouse, disposition_pending_restock,
    ):
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=10, allocated=0, on_order=0,
        )
        resp = client_admin.post(
            reverse('returns:disposition_process', args=[disposition_pending_restock.pk])
        )
        assert resp.status_code == 302
        disposition_pending_restock.refresh_from_db()
        assert disposition_pending_restock.status == 'processed'
        sl = StockLevel.objects.get(tenant=tenant, product=product, warehouse=warehouse)
        assert sl.on_hand == 12  # 10 + 2
        adj = StockAdjustment.objects.filter(stock_level=sl)
        assert adj.count() == 1
        assert adj.first().adjustment_type == 'increase'
        assert adj.first().reason == 'return'

    def test_restock_of_defective_refused_at_view_level(
        self, client_admin, tenant, received_rma, warehouse, product,
        inspection_completed,
    ):
        """D-02 defence-in-depth: even if the form is bypassed the view refuses."""
        ins_item = inspection_completed.items.first()
        ins_item.restockable = False
        ins_item.condition = 'defective'
        ins_item.save()
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='restock', warehouse=warehouse, status='pending',
        )
        DispositionItem.objects.create(
            tenant=tenant, disposition=disp, inspection_item=ins_item,
            product=product, qty=1,
        )
        resp = client_admin.post(reverse('returns:disposition_process', args=[disp.pk]))
        assert resp.status_code == 302
        disp.refresh_from_db()
        assert disp.status == 'pending'
        assert StockAdjustment.objects.count() == 0

    def test_restock_qty_exceeding_qty_passed_refused_at_view(
        self, client_admin, tenant, received_rma, warehouse, product, inspection_completed,
    ):
        """D-11 defence-in-depth at view layer."""
        ins_item = inspection_completed.items.first()  # qty_passed = 2
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='restock', warehouse=warehouse, status='pending',
        )
        DispositionItem.objects.create(
            tenant=tenant, disposition=disp, inspection_item=ins_item,
            product=product, qty=5,
        )
        resp = client_admin.post(reverse('returns:disposition_process', args=[disp.pk]))
        assert resp.status_code == 302
        disp.refresh_from_db()
        assert disp.status == 'pending'


class TestDispositionProcessScrap:
    def test_scrap_decrements_on_hand_symmetrically(
        self, client_admin, tenant, received_rma, inspection_completed, warehouse, product,
    ):
        """D-20: scrap path now actually reduces on_hand."""
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=10, allocated=0, on_order=0,
        )
        ins_item = inspection_completed.items.first()
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='scrap', warehouse=warehouse, status='pending',
        )
        DispositionItem.objects.create(
            tenant=tenant, disposition=disp, inspection_item=ins_item,
            product=product, qty=2,
        )
        resp = client_admin.post(reverse('returns:disposition_process', args=[disp.pk]))
        assert resp.status_code == 302
        sl = StockLevel.objects.get(tenant=tenant, product=product, warehouse=warehouse)
        assert sl.on_hand == 8  # 10 - 2
        adj = StockAdjustment.objects.filter(stock_level=sl).first()
        assert adj.adjustment_type == 'decrease'
        assert adj.reason == 'damage'

    def test_scrap_clamps_on_hand_at_zero(
        self, client_admin, tenant, received_rma, inspection_completed, warehouse, product,
    ):
        """D-20 edge: never drop below zero."""
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=1, allocated=0, on_order=0,
        )
        ins_item = inspection_completed.items.first()
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='scrap', warehouse=warehouse, status='pending',
        )
        DispositionItem.objects.create(
            tenant=tenant, disposition=disp, inspection_item=ins_item,
            product=product, qty=5,
        )
        client_admin.post(reverse('returns:disposition_process', args=[disp.pk]))
        sl = StockLevel.objects.get(tenant=tenant, product=product, warehouse=warehouse)
        assert sl.on_hand == 0


class TestDispositionDoubleProcess:
    def test_cannot_reprocess_a_processed_disposition(
        self, client_admin, tenant, product, warehouse, disposition_pending_restock,
    ):
        """D-03: second process call on an already-processed disposition is a no-op
        (transitions table refuses 'processed' → 'processed')."""
        StockLevel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=10, allocated=0, on_order=0,
        )
        client_admin.post(reverse('returns:disposition_process', args=[disposition_pending_restock.pk]))
        client_admin.post(reverse('returns:disposition_process', args=[disposition_pending_restock.pk]))
        sl = StockLevel.objects.get(tenant=tenant, product=product, warehouse=warehouse)
        # Only one increment should have been applied.
        assert sl.on_hand == 12
        assert StockAdjustment.objects.count() == 1
