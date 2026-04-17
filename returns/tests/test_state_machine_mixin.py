"""D-25: StateMachineMixin from core/state_machine.py drives all 4 models."""
import pytest

from core.state_machine import StateMachineMixin
from returns.models import (
    ReturnAuthorization, ReturnInspection, Disposition, RefundCredit,
)


pytestmark = pytest.mark.django_db


class TestMixinIntegration:
    @pytest.mark.parametrize('model_cls', [
        ReturnAuthorization, ReturnInspection, Disposition, RefundCredit,
    ])
    def test_model_inherits_mixin(self, model_cls):
        assert issubclass(model_cls, StateMachineMixin), (
            f'{model_cls.__name__} must mix in StateMachineMixin'
        )

    @pytest.mark.parametrize('model_cls', [
        ReturnAuthorization, ReturnInspection, Disposition, RefundCredit,
    ])
    def test_mixin_is_sole_source_of_can_transition_to(self, model_cls):
        """The model must not override can_transition_to — the mixin is authoritative."""
        # `can_transition_to` should be resolved from the mixin, not re-declared.
        assert model_cls.can_transition_to is StateMachineMixin.can_transition_to

    def test_unknown_state_returns_empty_transitions(self, draft_rma):
        draft_rma.status = 'nonexistent_state'
        assert draft_rma.can_transition_to('draft') is False

    def test_terminal_state_has_no_transitions(self, draft_rma):
        draft_rma.status = 'closed'
        for target in ['draft', 'pending', 'approved', 'received', 'cancelled']:
            assert draft_rma.can_transition_to(target) is False
