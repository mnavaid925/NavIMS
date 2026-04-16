# Catalog Module — SQA Follow-up: Defect Fixes + Test Suite

Source: `.claude/Test.md` (2026-04-17 SQA review)
Goal: remediate High/Medium severity defects and establish pytest automation.

## Scope

- **Fix** D-02 (negative pricing) and D-04 (markup-0 overwrite).
- **Verify** D-02 / D-04 / TC-IMG-005 behaviour before/after fix.
- **Scaffold** `catalog/tests/` with pytest + factory-boy.
- **Write** unit, form, view, security tests covering the fixes.

## Out of scope (deferred to their own PRs)

- D-01 (magic-byte file-upload validation) — needs `python-magic` + CSP + nosniff headers.
- D-03 (orphan file cleanup) — needs `django-cleanup` or signal wiring.
- D-05 (RBAC) — needs integration with `core.Role` permission set.
- D-06 (AuditLog emit) — cross-cutting, module-wide change.

## Task list

### A. Verification
- [ ] Read [catalog/models.py](../../catalog/models.py) pricing fields — confirm no `MinValueValidator` present
- [ ] Read [catalog/forms.py:178-182](../../catalog/forms.py#L178-L182) — confirm `if not markup:` bug
- [ ] Read [catalog/forms.py:256-263](../../catalog/forms.py#L256-L263) — note ext-only validation (D-01, deferred)

### B. D-02 fix — non-negative validators
- [ ] Add `MinValueValidator(Decimal('0'))` to: `purchase_cost`, `wholesale_price`, `retail_price`, `markup_percentage`, `weight`, `length`, `width`, `height`
- [ ] Generate migration: `python manage.py makemigrations catalog`
- [ ] Migration name: `0002_add_non_negative_validators.py`

### C. D-04 fix — markup overwrite
- [ ] Change `if not markup:` to `if markup in (None, '')`
- [ ] Keep auto-calc behavior when field left blank

### D. Test suite scaffold
- [ ] Create `catalog/tests/__init__.py`
- [ ] Create `catalog/tests/conftest.py` — fixtures: tenant, other_tenant, user, client_logged_in, department, category, product
- [ ] Create `catalog/tests/factories.py` — factory-boy factories (optional but recommended)
- [ ] Ensure `pytest.ini` or `pyproject.toml` configures `DJANGO_SETTINGS_MODULE=config.settings`

### E. Test files
- [ ] `test_models.py` — TC-CAT-002/003 (hierarchy), TC-IMG-006 (primary invariant), slug regen
- [ ] `test_forms.py` — TC-PROD-005/006 (pricing), TC-PROD-016 (markup=0 preserved **post-fix**), TC-CAT-004 (circular prevention)
- [ ] `test_views_product.py` — TC-PROD-001 (create), TC-PROD-003 (duplicate SKU), tenant isolation, XSS escape
- [ ] `test_security.py` — TC-SEC-001 (auth required), TC-SEC-002 (cross-tenant 404), TC-PROD-007 (negative price blocked **post-fix**)

### F. Run
- [ ] `python -m pytest catalog/tests/ -v`
- [ ] Confirm all green, especially post-fix cases

### G. Commit (one command per file, PowerShell `;` safe)

## Review — 2026-04-17

### What was done

1. **Verified D-02 + D-04 manually** via Django shell: both reproducible on the un-patched code.
2. **D-02 fix:** added `MinValueValidator(Decimal('0'))` to 8 fields on `catalog.Product`:
   `purchase_cost`, `wholesale_price`, `retail_price`, `markup_percentage`,
   `weight`, `length`, `width`, `height`.
   Migration generated as `catalog/migrations/0002_alter_product_height_alter_product_length_and_more.py` and applied to the dev DB.
3. **D-04 fix:** made `markup_percentage` optional on the form and changed the auto-compute guard from `if not markup:` → `if markup is None`, so user-entered `0` is no longer silently overwritten. Auto-compute still fires on blank input.
4. **Discovered and fixed D-12 (new):** `tenant` isn't a `ProductForm` field, so Django's default `validate_unique` excluded it from the `unique_together(tenant, sku)` check — duplicate SKUs only failed at the DB layer (500). Added `clean_sku()` that filters by `self.tenant` to surface a friendly form error. Included the duplicate-SKU test to lock this in.
5. **Test scaffold:** `config/settings_test.py` (SQLite in-memory, MD5 hasher), `pytest.ini`, `catalog/tests/{__init__.py,conftest.py}`.
6. **Test files (40 tests total):**
   - `test_models.py` — hierarchy levels, slug regeneration, primary-image invariant, SKU uniqueness-per-tenant.
   - `test_forms.py` — cross-check pricing rules, D-02 parametric guards (8 fields × negative), D-04 three-path verification (0 preserved, blank auto-computes, explicit preserved), category circular-prevention.
   - `test_views_product.py` — login redirect, create happy path, duplicate SKU (D-12), invalid-status param, search by SKU, delete cascade.
   - `test_security.py` — auth required on 4 URLs, cross-tenant IDOR for product/category, stored-XSS escaping, SQLi search query safe, CSRF enforced on delete.
7. **Pytest result:** `40 passed in 9.34s`.

### Notes & deferred items

- D-01 (magic-byte file-upload validation), D-03 (orphan file cleanup), D-05 (RBAC), D-06 (AuditLog) remain open — tracked in `.claude/Test.md` §6.1.
- Test DB is SQLite in-memory. Production DB remains MySQL untouched.
- Applied catalog migration to the dev MySQL DB: `0002_alter_product_height_alter_product_length_and_more` (this is a runtime-safe schema-level change — only alters column validators).

### Lessons captured

- Added D-12 to watch-list: **whenever `tenant` is not a form field, Django's `unique_together` check will exclude it.** Every `ModelForm` that relies on `unique_together(tenant, …)` must add a `clean_<field>` guard or the duplicate will escape to the DB.

