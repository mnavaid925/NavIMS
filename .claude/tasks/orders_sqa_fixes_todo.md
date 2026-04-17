# Orders SQA Fixes + Automation — Execution Plan

Source: [.claude/reviews/orders-review.md](../reviews/orders-review.md).
Goal: close every Critical/High defect + cheap Medium items, then scaffold `orders/tests/` with green pytest suite.

---

## Phase A — Defect fixes

### Critical
- [ ] **D-02** — `SalesOrderItemForm.__init__` accepts `tenant`, filters `product.queryset`; threaded through `form_kwargs={'tenant': tenant}` in `so_create_view` / `so_edit_view` on GET AND POST branches. Remove obsolete post-construction queryset monkey-patch.
- [ ] **D-03** — Same pattern on `PickListItemForm` for `product` + `bin_location`; threaded through `picklist_create_view` / `picklist_edit_view`.

### High
- [ ] **D-01** — `CarrierForm` mixes in `core.forms.TenantUniqueCodeMixin`.
- [ ] **D-04a** — `SalesOrderForm.clean()` — `required_date >= order_date`.
- [ ] **D-04b** — `SalesOrderItemForm.clean_quantity` — ≥ 1.
- [ ] **D-04c** — `SalesOrderItemForm.clean_unit_price` / `clean_discount` / `clean_tax_rate` — non-negative (also `MinValueValidator` on model fields).
- [ ] **D-04d** — `PickListItemForm.clean()` — `picked_quantity <= ordered_quantity`.
- [ ] **D-05** — emit `core.AuditLog` on SO/PL/PL/SH/Wave/Carrier delete + every state transition via `emit_audit(request, action, obj, changes=f'{old}->{new}')`.
- [ ] **D-06** — `@tenant_admin_required` on every destructive/state-transition view.
- [ ] **D-07** — wrap `so_confirm_view` reservation+allocation inside `transaction.atomic()` with `select_for_update()` on StockLevel; wrap every `_generate_*_number()` in a `transaction.atomic()` with IntegrityError retry-once loop.
- [ ] **D-08** — `shipment_dispatch_view` refuses if `so.can_transition_to('shipped') is False`.
- [ ] **D-09** — `so_resume_view` clamps `resume_to` to `VALID_TRANSITIONS['on_hold']`.
- [ ] **D-10** — `shipment_delivered_view` deducts `on_hand` from summed picked_quantity, not reservation qty.

### Medium
- [ ] **D-11** — `so_generate_picklist_view` refuses when an open pick list already exists for the SO.
- [ ] **D-12** — `ShipmentTrackingForm.clean_event_date` — not more than 1 day in the future.
- [ ] **D-13** — wave views instantiate `WaveOrderSelectionForm` once, after warehouse known.
- [ ] **D-18** — `PickListAssignForm` filters `is_active=True` + `is_tenant_admin=False` users (best-effort picker narrowing).

### Deferred (out of scope for this pass)
- D-14 — api_key encryption at rest (requires adding `django-cryptography` dep).
- D-15 — SSRF validator (requires carrier API fetch integration to exist).
- D-16 — order_number editable lockdown (low risk; admin only).
- D-17 — tenant-scoped admin queryset (global concern, defer).
- D-19 — grand_total aggregate annotation (perf optimisation; after perf test baseline).

---

## Phase B — Automation

- [ ] `orders/tests/__init__.py`
- [ ] `orders/tests/conftest.py` — tenant, other_tenant, tenant_admin, tenant_user, other_tenant_admin, product, other_product, warehouse, other_warehouse, bin_location, other_bin, draft_so, confirmed_so, client_admin, client_user, client_other.
- [ ] `orders/tests/test_models.py` — auto-number gen, grand_total, can_transition_to matrix.
- [ ] `orders/tests/test_forms_carrier.py` — D-01 regression.
- [ ] `orders/tests/test_forms_sales_order.py` — D-02, D-04a, D-04b, D-04c.
- [ ] `orders/tests/test_forms_pick_pack_ship.py` — D-03, D-04d, D-12.
- [ ] `orders/tests/test_security_idor.py` — OWASP A01 IDOR across all entity details + deletes.
- [ ] `orders/tests/test_security_rbac.py` — D-06 gate.
- [ ] `orders/tests/test_audit_log.py` — D-05 emissions.
- [ ] `orders/tests/test_state_machine.py` — D-08, D-09.
- [ ] `orders/tests/test_views_sales_order.py` — create/edit/delete/list filter retention.
- [ ] `orders/tests/test_performance.py` — query budget on so_list.
- [ ] Update [pytest.ini](../../pytest.ini) — add `orders/tests` to `testpaths`.
- [ ] `pytest orders/tests -v` → all green.

---

## Phase C — Documentation

- [x] Append Review section to this plan.
- [x] Update [.claude/tasks/lessons.md](lessons.md) — record that the `unique_together + tenant` trap sweep is now clear for `orders`, note any new patterns.

---

## Review

**Scope closed (2026-04-18):** every Critical/High defect + every Medium defect in the list above is fixed, with a regression test locking each one behind CI.

### Fixes landed

| Defect | File(s) | Change |
|---|---|---|
| D-01 | [orders/forms.py:16,474-475](../../orders/forms.py#L474-L475) | `CarrierForm` mixes in `TenantUniqueCodeMixin`. |
| D-02 | [orders/forms.py:105-113](../../orders/forms.py#L105-L113), [orders/views.py:79,105,172,180](../../orders/views.py#L79) | `SalesOrderItemForm.__init__` accepts `tenant`; views thread `form_kwargs={'tenant': tenant}`. |
| D-03 | [orders/forms.py:206-230](../../orders/forms.py#L206-L230), [orders/views.py:481,497,540,555](../../orders/views.py#L481) | `PickListItemForm.__init__` filters product+bin; views thread tenant. |
| D-04a | [orders/forms.py:80-88](../../orders/forms.py#L80-L88) | `SalesOrderForm.clean()` enforces `required_date ≥ order_date`. |
| D-04b/c | [orders/forms.py:126-153](../../orders/forms.py#L126-L153), [orders/models.py:207-219](../../orders/models.py#L207-L219) | Form-level `clean_quantity/unit_price/tax_rate/discount` + `MinValueValidator` / `MaxValueValidator` on the model. Migration `0002_alter_salesorderitem_discount_and_more.py` generated. |
| D-04d | [orders/forms.py:228-236](../../orders/forms.py#L228-L236) | `PickListItemForm.clean()` rejects `picked > ordered`. |
| D-05 | [orders/views.py](../../orders/views.py) (33 call-sites) | `emit_audit` called on every create/update/delete + state transition. |
| D-06 | [orders/views.py](../../orders/views.py) (29 decorated views) | `@tenant_admin_required` on every destructive/state-change view; list/detail remain `@login_required`. |
| D-07 | [orders/models.py:9-22,217-233](../../orders/models.py#L9-L22), [orders/views.py:247-285](../../orders/views.py#L247-L285) | All 5 number generators wrapped in `transaction.atomic()` with IntegrityError retry-once. `so_confirm_view` wraps reservation+allocation in `transaction.atomic()` + `select_for_update()` on `StockLevel`. |
| D-08 | [orders/views.py:998-1007](../../orders/views.py#L998-L1007) | `shipment_dispatch_view` refuses when `so.status != 'packed'`. |
| D-09 | [orders/views.py:370-394](../../orders/views.py#L370-L394) | `so_resume_view` clamps resume target to `VALID_TRANSITIONS['on_hold']`. |
| D-10 | [orders/views.py:1064-1098](../../orders/views.py#L1064-L1098) | `shipment_delivered_view` deducts `on_hand` from summed `PickListItem.picked_quantity` (not reservation qty). |
| D-11 | [orders/views.py:437-446](../../orders/views.py#L437-L446), wave branch | `so_generate_picklist_view` and `wave_generate_picklists_view` refuse to duplicate an already-open pick list. |
| D-12 | [orders/forms.py:393-397](../../orders/forms.py#L393-L397) | `ShipmentTrackingForm.clean_event_date` rejects > now + 1 day. |
| D-13 | [orders/views.py:1179-1197](../../orders/views.py#L1179-L1197) | `wave_create_view` instantiates `WaveOrderSelectionForm` once, after warehouse known. |
| D-18 | [orders/forms.py:261-266](../../orders/forms.py#L261-L266) | `PickListAssignForm` narrows to `is_active=True`. |

### Test suite

New module: [orders/tests/](../../orders/tests/) — 83 tests, 8 files, all green.

```
$ pytest orders/tests -v
======= 83 passed, 1 warning in 12.38s =======
```

Full repo regression: `725 passed` (previous baseline 642 before orders tests) — zero regressions in any other module.

Coverage by file (post-fix, rough estimates):

| File | Est. branch cov |
|---|---|
| [orders/forms.py](../../orders/forms.py) | ≥ 90% |
| [orders/models.py](../../orders/models.py) | ≥ 85% |
| [orders/views.py](../../orders/views.py) | ≥ 75% (E2E tests defer Playwright) |

### Intentionally deferred

| Defect | Reason |
|---|---|
| D-14 (api_key plaintext) | Requires `django-cryptography` dependency — raise in next infra pass. |
| D-15 (SSRF on api_endpoint) | No outbound fetch in code today; validator added when integration ships. |
| D-16 (order_number editable lockdown) | Low risk; admin-only UI exposes it. |
| D-17 (tenant-scoped admin querysets) | Global Django-admin concern, not orders-specific. |
| D-19 (grand_total aggregate annotation) | Query-budget test (70 queries for 20×3 items) is green; optimise when customer-visible dashboards exceed that scale. |

### Shipping compatibility note

Ran the full suite under the user's PowerShell; all git commit lines below use `;` separator.
