# Module 16 — Quality Control SQA Hardening PR — Plan

**Branch:** `main` (direct work).
**Date:** 2026-04-20.
**Source report:** [.claude/reviews/quality_control-review.md](../reviews/quality_control-review.md).
**Goal:** land D-01 through D-11 fixes + a first-wave automated test suite in a single hardening pass.

---

## A. Defect Fixes

| ID | Sev | Approach | Target file(s) |
|---|---|---|---|
| D-01 | **High** | Inside the atomic block of `scrap_post_view`, re-fetch the scrap with `select_for_update().get(pk=obj.pk)` and re-check `approval_status == 'approved'`. Abort with user-facing error on mismatch. | [quality_control/views.py](../../quality_control/views.py) |
| D-02 | Medium | In `checklist_list_view` annotate `Count('items')`; in `route_list_view` annotate `Count('rules')`. Render `{{ c.item_count }}` / `{{ r.rule_count }}` in templates. Add query-budget guard in `test_performance.py`. | views.py + 2 templates |
| D-03 | Medium | Add `FileExtensionValidator(['jpg','jpeg','png','gif','webp'])` + custom `validate_image_size` (≤ 5 MB) on `DefectPhoto.image`. Add `clean_image` in `DefectPhotoForm` that re-reads magic bytes. Add explicit `FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024`. | models.py, forms.py, settings.py |
| D-04 | Medium | In each form's `__init__`, when editing, union the filtered queryset with the currently-assigned instance FK so historical records stay editable: `qs = base_qs \| Model.objects.filter(pk=self.instance.<fk>_id)`. Apply to every `is_active=True` FK in forms.py. | forms.py |
| D-05 | Low | Route every scrap state write through `can_transition_to()`. Do the same for `quarantine_release_view`. Keep `VALID_TRANSITIONS` authoritative. | views.py |
| D-06 | Medium | Introduce a tiny `templatetags/quality_control_tags.py` with a `querystring` tag that merges current `request.GET` minus overridden keys. Update all 5 list templates to use `?{% querystring page=N %}`. | new templatetags module + 5 templates |
| D-07 | Low | Add `clean()` to `DefectReportForm`: `lot.product_id == cleaned['product'].pk`, `serial.product_id == cleaned['product'].pk`. | forms.py |
| D-08 | Low | Add `clean()` to `InspectionRouteRuleForm` mirroring `QCChecklistForm.clean()` scope logic. | forms.py |
| D-09 | Low | `emit_audit(..., 'post', obj, changes=f'approved->posted; adj={adjustment.adjustment_number}; on_hand {before}->{after}')`. | views.py |
| D-10 | Info | Add `'OPTIONS': {'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"}` to `DATABASES['default']`. | settings.py |
| D-11 | Low | Gate `defect_photo_delete_view` with `if defect.status not in ('open','investigating'): redirect + error`. Matches the UI's existing conditional display. | views.py |

---

## B. Test Scaffolding (first-wave)

Layout:

```
quality_control/tests/
├── __init__.py
├── conftest.py
├── test_models.py
├── test_forms.py
├── test_views_checklists.py
├── test_views_routes.py
├── test_views_quarantine.py
├── test_views_defects.py
├── test_views_scrap.py
├── test_security.py
├── test_performance.py
└── test_regression.py        # D-01..D-11 regressions bundled here
```

Also:
- Register `quality_control/tests` in [pytest.ini:testpaths](../../pytest.ini).

Target first-wave test count: **50–60 tests** across the 10 files. Coverage aim ≥ 85% branch on views.py, ≥ 90% on forms.py + models.py.

---

## C. Verification gates

- [ ] `python manage.py check` — clean.
- [ ] `python manage.py makemigrations quality_control --dry-run` — expect 1 new migration for D-03 validator on DefectPhoto.
- [ ] `pytest quality_control/tests -q` — 100% green.
- [ ] `pytest` (full suite) — no regressions in other modules from settings.py changes.
- [ ] Manual Django-shell reproduction of D-01 race (before fix) vs post-fix threaded regression test.
- [ ] `python manage.py seed_quality_control --flush` still idempotent.

---

## D. Files expected to change / be created

**Modified:**
- `quality_control/views.py` (D-01, D-05, D-09, D-11)
- `quality_control/forms.py` (D-03, D-04, D-07, D-08)
- `quality_control/models.py` (D-03 validators)
- `config/settings.py` (D-03 upload cap, D-10 strict mode)
- `templates/quality_control/checklist_list.html` (D-02, D-06)
- `templates/quality_control/route_list.html` (D-02, D-06)
- `templates/quality_control/quarantine_list.html` (D-06)
- `templates/quality_control/defect_list.html` (D-06)
- `templates/quality_control/scrap_list.html` (D-06)
- `pytest.ini` (testpaths)

**Created:**
- `quality_control/templatetags/__init__.py`
- `quality_control/templatetags/quality_control_tags.py`
- `quality_control/migrations/0002_*.py` (D-03 validators)
- `quality_control/tests/__init__.py`
- `quality_control/tests/conftest.py`
- `quality_control/tests/test_models.py`
- `quality_control/tests/test_forms.py`
- `quality_control/tests/test_views_checklists.py`
- `quality_control/tests/test_views_routes.py`
- `quality_control/tests/test_views_quarantine.py`
- `quality_control/tests/test_views_defects.py`
- `quality_control/tests/test_views_scrap.py`
- `quality_control/tests/test_security.py`
- `quality_control/tests/test_performance.py`
- `quality_control/tests/test_regression.py`

**Estimated:** ~19 modified/created files, ~32 commits (one per file).

---

## E. Checklist

- [ ] D-01 fix + reproduction documented
- [ ] D-02 fix + templates updated
- [ ] D-03 model + form + settings updated; new migration
- [ ] D-04 fix applied to all active-filtered FKs in forms.py
- [ ] D-05 state-machine routing
- [ ] D-06 querystring tag + 5 templates updated
- [ ] D-07 defect form clean()
- [ ] D-08 route rule form clean()
- [ ] D-09 audit payload
- [ ] D-10 MySQL strict mode
- [ ] D-11 photo delete gate
- [ ] tests/ scaffold (11 files)
- [ ] pytest.ini testpaths entry
- [ ] `pytest quality_control/tests` green
- [ ] `pytest` whole-repo no regressions
- [ ] README Module 16 test count updated
- [ ] Per-file git commit list emitted

---

## Review Section — 2026-04-20

### Outcome

**All 11 defects fixed, 82 tests scaffolded, 0 regressions across the repo.**

- `python manage.py check` — 0 issues.
- `pytest quality_control/tests -q` — **82 passed** in 20 s.
- `pytest` (full repo) — **1519 passed** in 45 s.

### Before / after verifications captured in shell

| Defect | Evidence |
|---|---|
| D-01 | Before fix: `on_hand 100→96, StockAdjustments=2` after concurrent POST. After fix: `on_hand 100→98, StockAdjustments=1`. |
| D-02 | Before: 18 checklists → 23 queries. After: 28 checklists → 5 queries (constant w.r.t. row count). |
| D-03 | Rejects PE masquerade (`MZ` signature), `.txt`, 6 MB image, SVG payload (all 4 surface as image-field errors). |
| D-04 | Deactivated product re-appears in form queryset; `form.is_valid()` → True on edit. |

### Deviations from plan

- **D-09** bundled into the D-01 edit (same view, same line range) — counted as one commit.
- **D-10** bundled into the D-03 `settings.py` edit — counted as one commit.
- **D-01 threaded regression** dropped in favour of a deterministic monkey-patch simulation in [test_regression.py](../../quality_control/tests/test_regression.py) — SQLite (our test DB) serialises writes at the table level so real threaded races can't be reproduced, and the threaded test tripped `database table is locked` during CI. The monkey-patch forces the exact code path (stale in-memory `approval_status='approved'` meeting a committed `'posted'` inside the atomic block) and works on any DB backend. A sequential `test_D01_scrap_post_sequential_second_call_refuses` complements it.
- **`order_by()` added to annotated querysets** in `checklist_list_view` and `route_list_view` to silence `UnorderedObjectListWarning` on paginator — small cleanup alongside D-02.
- **`tests/__init__.py`** created alongside the other test files (plan listed it separately).
- **Migration created:** `quality_control/migrations/0002_alter_defectphoto_image.py` for D-03 validators.

### Files modified (13) / created (15)

**Modified:**
- [quality_control/views.py](../../quality_control/views.py) — D-01, D-02 (Count annotation + order_by), D-05, D-09, D-11
- [quality_control/models.py](../../quality_control/models.py) — D-03 validators (`validate_defect_photo_size`, `validate_defect_photo_magic`) + `ImageField` validator list
- [quality_control/forms.py](../../quality_control/forms.py) — D-04 `_include_current` helper applied across 6 forms, D-03 `DefectPhotoForm.clean_image`, D-07 defect lot/serial match, D-08 route-rule scope guard
- [config/settings.py](../../config/settings.py) — D-03 explicit `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE`, D-10 MariaDB `STRICT_TRANS_TABLES`
- [templates/quality_control/checklist_list.html](../../templates/quality_control/checklist_list.html) — D-02 (`item_count` annotation), D-06 (querystring tag on paginator)
- [templates/quality_control/route_list.html](../../templates/quality_control/route_list.html) — D-02 (`rule_count` annotation), D-06
- [templates/quality_control/quarantine_list.html](../../templates/quality_control/quarantine_list.html) — D-06
- [templates/quality_control/defect_list.html](../../templates/quality_control/defect_list.html) — D-06
- [templates/quality_control/scrap_list.html](../../templates/quality_control/scrap_list.html) — D-06
- [pytest.ini](../../pytest.ini) — `quality_control/tests` appended to `testpaths`
- [README.md](../../README.md) — file-tree entry expanded with test count + fix notes, coverage table bumped (1169 → 1251)

**Created:**
- [quality_control/templatetags/__init__.py](../../quality_control/templatetags/__init__.py)
- [quality_control/templatetags/quality_control_tags.py](../../quality_control/templatetags/quality_control_tags.py) — `querystring` simple_tag
- [quality_control/migrations/0002_alter_defectphoto_image.py](../../quality_control/migrations/0002_alter_defectphoto_image.py) — auto-generated (D-03)
- [quality_control/tests/__init__.py](../../quality_control/tests/__init__.py)
- [quality_control/tests/conftest.py](../../quality_control/tests/conftest.py)
- [quality_control/tests/test_models.py](../../quality_control/tests/test_models.py) — 13 tests
- [quality_control/tests/test_forms.py](../../quality_control/tests/test_forms.py) — 13 tests
- [quality_control/tests/test_views_checklists.py](../../quality_control/tests/test_views_checklists.py) — 9 tests
- [quality_control/tests/test_views_routes.py](../../quality_control/tests/test_views_routes.py) — 4 tests
- [quality_control/tests/test_views_quarantine.py](../../quality_control/tests/test_views_quarantine.py) — 8 tests
- [quality_control/tests/test_views_defects.py](../../quality_control/tests/test_views_defects.py) — 8 tests
- [quality_control/tests/test_views_scrap.py](../../quality_control/tests/test_views_scrap.py) — 10 tests
- [quality_control/tests/test_security.py](../../quality_control/tests/test_security.py) — 12 tests (OWASP A01 × 6, A03 × 1, A08 × 2, A09 × 1, CSRF × 2)
- [quality_control/tests/test_performance.py](../../quality_control/tests/test_performance.py) — 2 tests (D-02 budgets)
- [quality_control/tests/test_regression.py](../../quality_control/tests/test_regression.py) — 3 tests (D-01 simulated race, D-01 sequential, D-09 audit payload) + D-04 bundled

### Exit gate status

- [x] Zero Critical / High defects open
- [x] `pytest quality_control/tests` green (82/82)
- [x] `pytest` full-repo green (1519/1519)
- [x] Every OWASP category in §2.1 has at least one assertion or documented dismissal
- [x] Seed command still idempotent
- [x] List views within query budget (≤ 12)
- [x] Scrap-post race guard regression green
- [x] D-03 (upload hygiene) remediated
- [x] README Module 16 test count updated (82; total 1251)
- [x] Per-file git commit list emitted (see bottom of this file / final assistant message)

### Lessons captured

1. **Form `ModelChoiceField` queryset filters like `is_active=True` silently break edit of historical records** — always union with the currently-assigned instance FK in `__init__`. New helper `_include_current()` in `quality_control/forms.py` is reusable across modules.
2. **`transaction.atomic()` + `select_for_update()` on dependent rows only is not sufficient** — must also re-lock the subject row and re-check its state inside the atomic block, otherwise two concurrent writers both commit.
3. **SQLite tests can't reliably simulate row-lock races** — use a monkey-patched `select_for_update()` that forces the concurrent commit at the exact seam, and make the threaded variant MySQL/Postgres-only.
4. **`.update()` bypasses `save()`-time column mirrors** — when testing a state-machine guard that reads a mirrored field, set BOTH columns in the simulation or the guard may be silently bypassed.
