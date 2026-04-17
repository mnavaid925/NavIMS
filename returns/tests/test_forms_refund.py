from decimal import Decimal

import pytest

from returns.forms import RefundCreditForm
from returns.models import RefundCredit


pytestmark = pytest.mark.django_db


def _refund_data(rma, amount='10.00', currency='USD'):
    return {
        'rma': rma.pk,
        'type': 'refund',
        'method': 'card',
        'amount': amount,
        'currency': currency,
        'reference_number': '',
        'notes': '',
    }


class TestRefundCreditForm:
    def test_valid_refund(self, tenant, received_rma):
        form = RefundCreditForm(data=_refund_data(received_rma, '5.00'), tenant=tenant)
        assert form.is_valid(), form.errors

    def test_amount_exceeding_rma_total_rejected(self, tenant, received_rma):
        """D-01: refund must not exceed rma.total_value."""
        form = RefundCreditForm(
            data=_refund_data(received_rma, '9999999.99'), tenant=tenant,
        )
        assert not form.is_valid()
        assert 'amount' in form.errors

    def test_zero_amount_refund_rejected(self, tenant, received_rma):
        """D-17: zero-amount refund is a no-op."""
        form = RefundCreditForm(data=_refund_data(received_rma, '0.00'), tenant=tenant)
        assert not form.is_valid()
        assert 'amount' in form.errors

    def test_negative_amount_rejected(self, tenant, received_rma):
        form = RefundCreditForm(data=_refund_data(received_rma, '-1.00'), tenant=tenant)
        assert not form.is_valid()

    def test_non_iso_currency_rejected(self, tenant, received_rma):
        """D-13: currency must be a 3-letter ISO 4217 code."""
        form = RefundCreditForm(
            data=_refund_data(received_rma, '5.00', currency='XYZ123'), tenant=tenant,
        )
        assert not form.is_valid()
        assert 'currency' in form.errors

    def test_lowercase_currency_is_normalised(self, tenant, received_rma):
        form = RefundCreditForm(
            data=_refund_data(received_rma, '5.00', currency='usd'), tenant=tenant,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data['currency'] == 'USD'

    def test_rma_queryset_only_received_or_closed(
        self, tenant, received_rma, other_draft_rma, delivered_so, warehouse,
    ):
        from returns.models import ReturnAuthorization
        separate_draft = ReturnAuthorization.objects.create(
            tenant=tenant, sales_order=delivered_so, customer_name='X',
            requested_date='2026-04-18', warehouse=warehouse, status='draft',
        )
        form = RefundCreditForm(tenant=tenant)
        assert received_rma in form.fields['rma'].queryset
        assert separate_draft not in form.fields['rma'].queryset
        assert other_draft_rma not in form.fields['rma'].queryset

    def test_refund_cap_considers_prior_refunds(self, tenant, received_rma):
        """Remaining refund cap = total_value - already-refunded. total_value here = 20."""
        RefundCredit.objects.create(
            tenant=tenant, rma=received_rma, amount=Decimal('15.00'),
            currency='USD', status='pending',
        )
        # 15 of 20 used → 5 remaining; 10 should now be rejected.
        form = RefundCreditForm(data=_refund_data(received_rma, '10.00'), tenant=tenant)
        assert not form.is_valid()
        # But 5 is allowed.
        form2 = RefundCreditForm(data=_refund_data(received_rma, '5.00'), tenant=tenant)
        assert form2.is_valid(), form2.errors

    def test_cancelled_refunds_do_not_consume_cap(self, tenant, received_rma):
        RefundCredit.objects.create(
            tenant=tenant, rma=received_rma, amount=Decimal('20.00'),
            currency='USD', status='cancelled',
        )
        form = RefundCreditForm(data=_refund_data(received_rma, '20.00'), tenant=tenant)
        assert form.is_valid(), form.errors
