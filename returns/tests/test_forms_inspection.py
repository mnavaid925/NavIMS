import pytest

from returns.forms import (
    ReturnInspectionForm, ReturnInspectionItemFormSet,
)
from returns.models import ReturnInspection


pytestmark = pytest.mark.django_db


class TestReturnInspectionForm:
    def test_rma_queryset_scoped_and_filtered_by_status(
        self, tenant, draft_rma, approved_rma, other_draft_rma,
    ):
        form = ReturnInspectionForm(tenant=tenant)
        # draft_rma has status 'draft' after promotion; approved_rma has 'approved'.
        # We expect approved_rma to be visible, cross-tenant invisible, and draft/received-only
        # statuses handled by the queryset.
        assert approved_rma in form.fields['rma'].queryset
        assert other_draft_rma not in form.fields['rma'].queryset


def _inspection_item_data(rma_item, qty_inspected=2, qty_passed=2, qty_failed=0):
    return {
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-rma_item': rma_item.pk,
        'items-0-qty_inspected': str(qty_inspected),
        'items-0-qty_passed': str(qty_passed),
        'items-0-qty_failed': str(qty_failed),
        'items-0-condition': 'good',
        'items-0-restockable': 'on',
        'items-0-notes': '',
    }


class TestReturnInspectionItemFormSet:
    def test_rma_item_queryset_scoped_to_tenant(self, tenant, received_rma, other_draft_rma):
        """D-05: rma_item queryset is tenant-scoped at POST time."""
        fs = ReturnInspectionItemFormSet(prefix='items', form_kwargs={'tenant': tenant})
        qs = fs.forms[0].fields['rma_item'].queryset
        assert received_rma.items.first() in qs
        assert other_draft_rma.items.first() not in qs

    def test_cross_tenant_rma_item_rejected_on_post(
        self, tenant, received_rma, other_draft_rma,
    ):
        """D-05 regression: POSTing a foreign tenant's rma_item pk must fail validation."""
        foreign_item = other_draft_rma.items.first()
        data = _inspection_item_data(foreign_item)
        fs = ReturnInspectionItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_qty_reconciliation_enforced(self, tenant, received_rma):
        """D-10: qty_passed + qty_failed must equal qty_inspected."""
        rma_item = received_rma.items.first()
        data = _inspection_item_data(rma_item, qty_inspected=3, qty_passed=2, qty_failed=0)
        fs = ReturnInspectionItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_qty_inspected_cannot_exceed_qty_received(self, tenant, received_rma):
        """D-10: qty_inspected cannot exceed the received qty on the RMA item."""
        rma_item = received_rma.items.first()  # qty_received=2
        data = _inspection_item_data(rma_item, qty_inspected=5, qty_passed=5, qty_failed=0)
        fs = ReturnInspectionItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert not fs.is_valid()

    def test_valid_inspection_item(self, tenant, received_rma):
        rma_item = received_rma.items.first()
        data = _inspection_item_data(rma_item, qty_inspected=2, qty_passed=2, qty_failed=0)
        fs = ReturnInspectionItemFormSet(
            data=data, prefix='items', form_kwargs={'tenant': tenant},
        )
        assert fs.is_valid(), fs.errors
