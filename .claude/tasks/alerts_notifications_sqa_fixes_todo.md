# Alerts & Notifications — SQA Fix + Automation Plan

**Date:** 2026-04-20
**Report source:** [.claude/reviews/alerts_notifications-review.md](.claude/reviews/alerts_notifications-review.md)
**Target branch:** `main`
**Execution mode:** Fix-in-place + scaffold tests

---

## Scope

### Defects to fix (ordered by severity)

| ID | Severity | Summary | Files touched |
|---|---|---|---|
| D-01 | Critical | `alert_create_view` 500s when `tenant=None` (superuser submit) | `alerts_notifications/views.py` |
| D-02 | Critical | `rule_create_view` 500s when `tenant=None` (superuser submit) | `alerts_notifications/views.py` |
| D-03 | High (policy) | Missing `alert_edit_view` + URL | `alerts_notifications/views.py`, `urls.py`, `templates/alerts_notifications/alert_form.html` |
| D-04 | Medium | Unbounded `Alert.notes` growth on resolve | `alerts_notifications/forms.py`, `views.py` |
| D-06 | Medium | Manual `dedup_key` uses float timestamp (race-collision risk) | `alerts_notifications/views.py` |
| D-07 | Medium | Dispatcher uses `except Exception` — too broad | `alerts_notifications/management/commands/dispatch_notifications.py` |
| D-09 | Low | Dead `products` context in `alert_list_view` | `alerts_notifications/views.py` |
| D-11 | Low | `rule_list` `.count()` per row (N+1 risk at scale) | `templates/alerts_notifications/rule_list.html` |

### Defects deferred (out of scope for this pass)

- **D-05** — not a real defect, watch-item only.
- **D-08** — being addressed by the test-suite scaffolding (this plan's Phase B).
- **D-10** — TenantScopedAdmin consolidation: touches 5+ modules, warrants its own PR.
- **D-12** — scanner naming cosmetic: would force cron-config rewrites; leave as-is.
- **D-13** — `import_failed` enum reserved; docstring comment only.

### Test suite targets

Create `alerts_notifications/tests/` with pytest files matching the convention used in `stocktaking/tests/`:

- `__init__.py`, `conftest.py`
- `test_models.py` — model invariants, state machine, auto-numbering, dedup
- `test_forms.py` — tenant injection + clean_code + recipient M2M guard
- `test_views_alerts.py` — CRUD + state transitions + inbox JSON + **D-01 regression**
- `test_views_rules.py` — CRUD + toggle-active + **D-02 regression**
- `test_views_deliveries.py` — delivery log read-only
- `test_security.py` — OWASP A01 cross-tenant IDOR sweep + CSRF + RBAC
- `test_scanners.py` — 4 scanners (dedup, happy path, edge cases)
- `test_dispatcher.py` — dispatch_notifications idempotency + failure logging
- `test_regression.py` — named `test_D04_notes_capped` and similar

Register the new path in `pytest.ini`.

---

## Phase A — Critical fixes (D-01, D-02)

**Pattern:** add a tenant guard at the top of the two create views, before any form construction.

```python
@login_required
@tenant_admin_required
def alert_create_view(request):
    tenant = request.tenant
    if tenant is None:
        messages.error(request, 'No tenant context — log in as a tenant admin to create alerts.')
        return redirect('alerts_notifications:alert_list')
    # ... existing code
```

Apply the same guard to `rule_create_view`.

**Verification:** re-run the Django Test Client POST as superuser — must return 302 (not 500), and `Alert.objects.filter(tenant__isnull=True).exists()` must be False.

---

## Phase B — Medium fixes (D-04, D-06, D-07)

### D-04: Cap `Alert.notes` on resolve

Two layers of defence:

1. **Form layer** — promote `AlertResolveForm.notes` validation:
   ```python
   notes = forms.CharField(
       required=False,
       max_length=2000,
       widget=forms.Textarea(attrs={...}),
   )
   ```
2. **View layer** — validate via the form in `alert_resolve_view` instead of raw `request.POST.get('notes', '')`, and truncate the resulting alert.notes to 16 KB hard cap.

### D-06: Replace timestamp dedup_key with uuid

```python
import uuid
obj.dedup_key = f'manual:{uuid.uuid4().hex}'
```

### D-07: Narrow dispatcher exception handling

```python
import smtplib
try:
    send_mail(...)
except (smtplib.SMTPException, OSError, ConnectionError) as exc:
    # log & continue
```

---

## Phase C — High/Low policy fixes (D-03, D-09, D-11)

### D-03: Add `alert_edit_view`

- Only manual alerts (`dedup_key.startswith('manual:')`) may be edited — scanner-generated alerts are read-only.
- URL: `alerts/<int:pk>/edit/`
- View reuses `AlertForm` + existing `alert_form.html` template.
- Add Edit button to alert detail sidebar (conditional on manual origin).

### D-09: Remove `products` context

Delete the `products` key from `alert_list_view`'s render context — template doesn't use it. Saves one query per list-page load.

### D-11: Replace `.count()` with `|length` in rule_list

```html
<td><small>{{ r.recipient_users.all|length }} user{{ r.recipient_users.all|length|pluralize }}</small></td>
```

Uses the prefetched cache — zero extra queries per row.

---

## Phase D — Test suite scaffolding

Minimum viable test set:

| File | Tests target | Count |
|---|---|---|
| `conftest.py` | tenant / user / product / warehouse / stock_level / lot / fixtures | — |
| `test_models.py` | auto-number, state machine, dedup uniqueness, __str__ | ~10 |
| `test_forms.py` | tenant-scoped querysets, cross-tenant rejection, unique code | ~8 |
| `test_views_alerts.py` | list / detail / create / ack / resolve / dismiss / delete / inbox JSON / D-01 regression | ~14 |
| `test_views_rules.py` | rule CRUD + toggle-active + D-02 regression | ~8 |
| `test_views_deliveries.py` | delivery list + detail | ~3 |
| `test_security.py` | IDOR sweep (parametrised), CSRF 405, RBAC 403 | ~12 |
| `test_scanners.py` | each of 4 scanners: happy path + dedup + edge | ~10 |
| `test_dispatcher.py` | send, idempotent, failed-email, SMTP exception caught | ~5 |
| `test_regression.py` | D-04 notes cap | ~2 |
| **Total** | | **~72** |

**Target pass rate:** 100%. **Target line coverage:** ≥80% on models/forms/views.

---

## Phase E — Verify + document

1. Run `pytest alerts_notifications/tests -v` — capture pass/fail count.
2. Append a Review section to this file with results.
3. If any new lesson surfaces (e.g. the tenant=None guard pattern), append to `.claude/tasks/lessons.md`.

---

## Tasks (tracked via TodoWrite)

- [x] Phase A: D-01 + D-02 tenant guards
- [x] Phase B: D-04 notes cap, D-06 uuid dedup, D-07 narrow except
- [x] Phase C: D-03 edit view, D-09 clean context, D-11 |length
- [x] Verification: Django shell reproduce before/after for each critical
- [x] Phase D: write all test files + register testpaths
- [x] Phase E: run pytest; append review

---

## Review — 2026-04-21

### What was delivered

| Defect | Fix | File(s) |
|---|---|---|
| D-01 Critical | Tenant=None guard at top of `alert_create_view` returns 302 with `messages.error` instead of 500-crashing on `_generate_number()`. | [alerts_notifications/views.py:140-145](alerts_notifications/views.py#L140-L145) |
| D-02 Critical | Same guard pattern in `rule_create_view`. | [alerts_notifications/views.py:329-333](alerts_notifications/views.py#L329-L333) |
| D-03 High (policy) | New `alert_edit_view` + URL `alerts/<int:pk>/edit/`; scanner-generated alerts (non-`manual:` dedup_key) are refused with a flash message and redirect. Detail sidebar now exposes the Edit button conditionally. | `alerts_notifications/views.py`, `urls.py`, `templates/alerts_notifications/alert_detail.html`, `alert_form.html` |
| D-04 Medium | `AlertResolveForm.notes` gains `max_length=2000`; `alert_resolve_view` validates via the form and caps the combined `alert.notes` to 16 KB. | `alerts_notifications/forms.py`, `views.py` |
| D-06 Medium | Manual `dedup_key` now uses `uuid.uuid4().hex` instead of a float timestamp — eliminates the sub-microsecond collision race. | `alerts_notifications/views.py` |
| D-07 Medium | Dispatcher catches `(smtplib.SMTPException, OSError, ConnectionError)` instead of bare `Exception`. | `alerts_notifications/management/commands/dispatch_notifications.py` |
| D-09 Low | Dead `products` context removed from `alert_list_view`; `from catalog.models import Product` import also removed. | `alerts_notifications/views.py` |
| D-11 Low | `rule_list.html` now uses `{{ r.recipient_users.all\|length }}` (prefetched) instead of `.count()` (fresh query per row). | `templates/alerts_notifications/rule_list.html` |

### Test suite scaffolded

10 test files + `__init__.py` in `alerts_notifications/tests/`. Registered in `pytest.ini` testpaths. **101 tests, 100% passing in 19 s.**

| File | Tests | Coverage focus |
|---|---|---|
| `conftest.py` | — | Fixtures matching stocktaking/quality_control convention |
| `test_models.py` | 13 | Auto-number + state machine + dedup unique + __str__ + tenant-scoping |
| `test_forms.py` | 8 | Tenant injection + clean_code + cross-tenant M2M + notes max_length |
| `test_views_alerts.py` | 21 | CRUD + state transitions + inbox JSON + **D-01 + D-03 regression** |
| `test_views_rules.py` | 9 | Rule CRUD + toggle-active + **D-02 regression** |
| `test_views_deliveries.py` | 3 | Read-only list/detail + cross-tenant 404 |
| `test_security.py` | 21 | Parametrised IDOR sweep + CSRF 405 + RBAC 403 + A03 XSS static-check + A09 AuditLog |
| `test_scanners.py` | 15 | 4 scanners: happy path, dedup, edge cases, --dry-run, --grace-days |
| `test_dispatcher.py` | 5 | Send, idempotent, failed-email, inactive-rule skip, min-severity threshold |
| `test_performance.py` | 3 | Query budgets (alert_list ≤ 15, rule_list ≤ 12 **guards D-11**, delivery_list ≤ 12) |
| `test_regression.py` | 3 | Named `D04_50K_rejected`, `D04_2K_accepted`, `D06_uuid_dedup_key` |

**Full project suite: 1620 passed, 1 warning in 51 s — no regression in other modules.**

### Verification evidence

Pre-fix (from original SQA review): `alert_create` + `rule_create` POST as superuser → HTTP 500 with stack trace. Post-fix:

```
D-01 (alert_create superuser): status=302  ✅
D-02 (rule_create superuser):  status=302  ✅
D-04 (50 KB notes):  rejected, notes unchanged, status=acknowledged (no resolve)  ✅
D-04 (2 KB notes):   accepted, resolve succeeded, notes_len=2000                  ✅
D-06: dedup_key = "manual:<32-hex-uuid>"                                          ✅
D-03: manual alert edit → 200; scanner alert edit → 302 (flash error)             ✅
```

### Lesson captured

A new pattern-level rule has been added to `.claude/tasks/lessons.md`:

> **Create-views that auto-generate per-tenant sequence numbers (e.g. `ALN-NNNNN`) MUST guard `tenant is None` at the top of the view.** Without the guard, `obj.save()` → `_generate_number()` → `self.tenant` → `RelatedObjectDoesNotExist` → 500. Pattern: `if tenant is None: messages.error(...); return redirect(list_view)`. Affects any module where a superuser can reach the create URL.

### Deferred items (out of scope, documented in §Scope)

- **D-05** — watch-item only.
- **D-08** — addressed (suite delivered).
- **D-10** — `TenantScopedAdmin` lift-to-core: separate PR touching 5+ modules.
- **D-12** — scanner naming: would force cron rewrites.
- **D-13** — `import_failed` enum: documented in plan.
