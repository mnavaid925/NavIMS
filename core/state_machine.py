"""Shared state-machine helpers for tenant-scoped domain models.

Any model with a finite `status` field and a `VALID_TRANSITIONS` table should
mix in `StateMachineMixin` instead of hand-rolling `can_transition_to`. The
mixin also provides `transition_to()` — a single helper that checks the
transition is allowed, sets the new status, and optionally sets extra fields
(e.g. timestamps / actor FKs).

Lesson #25 (returns SQA): by the time five modules had copy-pasted the same
`can_transition_to` method onto their state-machine models, the helper
belonged in `core/`. Adopt incrementally; existing modules can switch
whenever they next need to touch a status-related model.
"""


class StateMachineMixin:
    """Provides `can_transition_to(new_status)` against `VALID_TRANSITIONS`.

    Expected class attribute:
        VALID_TRANSITIONS: dict[str, list[str]]
            Maps a current status to the set of statuses reachable from it.
            Terminal states map to an empty list.

    The model must also expose `self.status` (the current state).
    """

    VALID_TRANSITIONS: dict = {}

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])
