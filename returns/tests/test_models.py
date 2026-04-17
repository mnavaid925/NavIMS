from datetime import date
from decimal import Decimal

import pytest

from returns.models import (
    ReturnAuthorization, ReturnInspection, Disposition, RefundCredit,
)


pytestmark = pytest.mark.django_db


class TestRMANumberGeneration:
    def test_first_rma_gets_00001(self, draft_rma):
        assert draft_rma.rma_number == 'RMA-00001'

    def test_sequential_numbers(self, tenant, delivered_so, warehouse):
        r1 = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='a',
            requested_date=date(2026, 4, 18), warehouse=warehouse,
        )
        r2 = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='b',
            requested_date=date(2026, 4, 18), warehouse=warehouse,
        )
        assert (r1.rma_number, r2.rma_number) == ('RMA-00001', 'RMA-00002')

    def test_number_is_tenant_scoped(self, draft_rma, other_draft_rma):
        assert draft_rma.rma_number == 'RMA-00001'
        assert other_draft_rma.rma_number == 'RMA-00001'

    def test_inspection_prefix(self, tenant, approved_rma):
        insp = ReturnInspection.objects.create(tenant=tenant, rma=approved_rma)
        assert insp.inspection_number.startswith('RINS-')

    def test_disposition_prefix(self, tenant, received_rma, warehouse):
        d = Disposition.objects.create(
            tenant=tenant, rma=received_rma, decision='restock', warehouse=warehouse,
        )
        assert d.disposition_number.startswith('DISP-')

    def test_refund_prefix(self, tenant, received_rma):
        r = RefundCredit.objects.create(
            tenant=tenant, rma=received_rma, amount=Decimal('1'), currency='USD',
        )
        assert r.refund_number.startswith('REF-')


class TestRMAStateMachine:
    @pytest.mark.parametrize('from_state, to_state, allowed', [
        ('draft', 'pending', True),
        ('draft', 'approved', False),
        ('draft', 'cancelled', True),
        ('pending', 'approved', True),
        ('pending', 'rejected', True),
        ('pending', 'closed', False),
        ('approved', 'received', True),
        ('approved', 'closed', False),
        ('rejected', 'draft', True),
        ('received', 'closed', True),
        ('closed', 'cancelled', False),
        ('cancelled', 'draft', True),
    ])
    def test_transitions(self, draft_rma, from_state, to_state, allowed):
        draft_rma.status = from_state
        assert draft_rma.can_transition_to(to_state) is allowed


class TestInspectionStateMachine:
    @pytest.mark.parametrize('from_state, to_state, allowed', [
        ('pending', 'in_progress', True),
        ('pending', 'completed', False),
        ('in_progress', 'completed', True),
        ('in_progress', 'cancelled', True),
        ('completed', 'pending', False),
        ('cancelled', 'pending', True),
    ])
    def test_transitions(self, tenant, approved_rma, from_state, to_state, allowed):
        insp = ReturnInspection.objects.create(tenant=tenant, rma=approved_rma, status=from_state)
        assert insp.can_transition_to(to_state) is allowed


class TestDispositionStateMachine:
    @pytest.mark.parametrize('from_state, to_state, allowed', [
        ('pending', 'processed', True),
        ('pending', 'cancelled', True),
        ('processed', 'pending', False),
        ('cancelled', 'pending', True),
    ])
    def test_transitions(self, tenant, received_rma, warehouse, from_state, to_state, allowed):
        d = Disposition.objects.create(
            tenant=tenant, rma=received_rma, decision='restock',
            warehouse=warehouse, status=from_state,
        )
        assert d.can_transition_to(to_state) is allowed


class TestRefundStateMachine:
    @pytest.mark.parametrize('from_state, to_state, allowed', [
        ('pending', 'processed', True),
        ('pending', 'failed', True),
        ('pending', 'cancelled', True),
        ('processed', 'cancelled', False),
        ('failed', 'pending', True),
        ('cancelled', 'pending', True),
    ])
    def test_transitions(self, tenant, received_rma, from_state, to_state, allowed):
        r = RefundCredit.objects.create(
            tenant=tenant, rma=received_rma, amount=Decimal('1'),
            currency='USD', status=from_state,
        )
        assert r.can_transition_to(to_state) is allowed


class TestRMACalculations:
    def test_total_value(self, draft_rma):
        assert draft_rma.total_value == Decimal('20.00')

    def test_total_qty_requested(self, draft_rma):
        assert draft_rma.total_qty_requested == 2

    def test_total_qty_received_starts_zero(self, draft_rma):
        assert draft_rma.total_qty_received == 0
