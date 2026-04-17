import pytest

from returns.forms import DispositionForm, DispositionItemFormSet
from returns.models import (
    Disposition, DispositionItem, ReturnInspectionItem,
)


pytestmark = pytest.mark.django_db


class TestDispositionForm:
    def test_rma_queryset_only_received_or_closed(
        self, tenant, received_rma, other_draft_rma, delivered_so, warehouse,
    ):
        from returns.models import ReturnAuthorization
        separate_draft = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='X',
            requested_date='2026-04-18', warehouse=warehouse, status='draft',
        )
        form = DispositionForm(tenant=tenant)
        assert received_rma in form.fields['rma'].queryset
        assert separate_draft not in form.fields['rma'].queryset
        assert other_draft_rma not in form.fields['rma'].queryset

    def test_warehouse_and_inspection_tenant_scoped(self, tenant, warehouse, other_warehouse):
        form = DispositionForm(tenant=tenant)
        assert warehouse in form.fields['warehouse'].queryset
        assert other_warehouse not in form.fields['warehouse'].queryset


def _item_data(ins_item, product, qty=1, bin_pk=''):
    return {
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-inspection_item': ins_item.pk,
        'items-0-product': product.pk,
        'items-0-qty': str(qty),
        'items-0-destination_bin': bin_pk,
        'items-0-notes': '',
    }


class TestDispositionItemFormSet:
    def test_all_fk_fields_tenant_scoped(
        self, tenant, product, other_product, bin_location, other_bin,
        inspection_completed, other_draft_rma,
    ):
        """D-05: product, destination_bin, inspection_item all tenant-filtered."""
        fs = DispositionItemFormSet(prefix='items', form_kwargs={'tenant': tenant})
        f = fs.forms[0]
        assert product in f.fields['product'].queryset
        assert other_product not in f.fields['product'].queryset
        assert bin_location in f.fields['destination_bin'].queryset
        assert other_bin not in f.fields['destination_bin'].queryset
        assert inspection_completed.items.first() in f.fields['inspection_item'].queryset

    def test_qty_cannot_exceed_inspection_qty(
        self, tenant, disposition_pending_restock, product,
    ):
        """D-11: disposition qty cannot exceed inspection qty_inspected."""
        ins_item = disposition_pending_restock.items.first().inspection_item
        data = _item_data(ins_item, product, qty=999)
        fs = DispositionItemFormSet(
            data=data, instance=disposition_pending_restock,
            prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_restock_of_defective_item_rejected(
        self, tenant, received_rma, warehouse, product, inspection_completed,
    ):
        """D-02: restock refused when inspection item is not restockable."""
        ins_item = inspection_completed.items.first()
        ins_item.condition = 'defective'
        ins_item.restockable = False
        ins_item.save()
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='restock', warehouse=warehouse, status='pending',
        )
        data = _item_data(ins_item, product, qty=1)
        fs = DispositionItemFormSet(
            data=data, instance=disp, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_restock_qty_cannot_exceed_qty_passed(
        self, tenant, received_rma, warehouse, product, inspection_completed,
    ):
        """D-11: restock qty cannot exceed inspection qty_passed."""
        ins_item = inspection_completed.items.first()  # qty_passed=2
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='restock', warehouse=warehouse, status='pending',
        )
        data = _item_data(ins_item, product, qty=5)
        fs = DispositionItemFormSet(
            data=data, instance=disp, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_valid_restock_passes(
        self, tenant, received_rma, warehouse, product, inspection_completed,
    ):
        ins_item = inspection_completed.items.first()  # qty_passed=2
        disp = Disposition.objects.create(
            tenant=tenant, rma=received_rma, inspection=inspection_completed,
            decision='restock', warehouse=warehouse, status='pending',
        )
        data = _item_data(ins_item, product, qty=2)
        fs = DispositionItemFormSet(
            data=data, instance=disp, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert fs.is_valid(), fs.errors
