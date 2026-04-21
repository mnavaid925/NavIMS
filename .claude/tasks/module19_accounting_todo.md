# Module 19 — Accounting & Financial Integration — Todo

Started: 2026-04-22.
Plan: `C:\Users\user\.claude\plans\eager-giggling-hejlsberg.md` (approved).

## Scope
- Integration staging layer + lightweight double-entry GL (Chart of Accounts, FiscalPeriod, Customer, TaxJurisdiction, TaxRule, APBill, APBillLine, ARInvoice, ARInvoiceLine, JournalEntry, JournalLine).
- Scan commands + manual generate button; no Django signals; zero invasive changes to purchase_orders / orders / inventory.
- Two new fields on `catalog.Product`: `tax_category`, `hsn_code`.

## Checklist

### App skeleton & wiring
- [x] Create `accounting/` app with `apps.py`, `__init__.py`
- [x] Create `accounting/migrations/`, `management/commands/`, `tests/` with `__init__.py`
- [x] Register in `config/settings.py` INSTALLED_APPS
- [x] Mount URLs in `config/urls.py` at `/accounting/`

### Catalog changes (Module 19 dependency)
- [x] Add `Product.tax_category` + `Product.hsn_code` to `catalog/models.py`
- [x] Update `catalog/forms.py` ProductForm to include both
- [x] Update `catalog/admin.py` Product list_filter/display
- [x] Update `templates/catalog/product_form.html` to render both fields
- [ ] Run `makemigrations catalog` → generates `0003_product_tax_category_hsn_code.py`

### Accounting models (11)
- [ ] `accounting/models.py` — ChartOfAccount, FiscalPeriod, Customer, TaxJurisdiction, TaxRule, APBill, APBillLine, ARInvoice, ARInvoiceLine, JournalEntry, JournalLine
- [ ] Apply `_save_with_number_retry`, `StateMachineMixin`, soft-delete, `unique_together(tenant, X)`
- [ ] `sync_status` CharField on APBill, ARInvoice, JournalEntry
- [ ] Run `makemigrations accounting` → generates `0001_initial.py`
- [ ] Run `migrate`

### Forms
- [ ] `accounting/forms.py` — 11 ModelForms + 3 inline formsets (APBillLine, ARInvoiceLine, JournalLine)
- [ ] Tenant-aware `__init__(tenant=None)` on every form
- [ ] `TenantUniqueCodeMixin` on forms with `unique_together(tenant, code)`

### Views & URLs
- [ ] `accounting/views.py` — CRUD for all 11 models + 3 dashboards + trial balance + tax calculator + 3 generate-from-source endpoints
- [ ] `accounting/urls.py` — app_name='accounting'
- [ ] Apply `@login_required` + `@tenant_admin_required` + `@require_POST` + `emit_audit` triad on mutations
- [ ] Tenant-None guard on every create view

### Templates (28)
- [ ] `templates/accounting/overview.html`
- [ ] `ap_dashboard.html`, `ar_dashboard.html`, `trial_balance.html`, `tax_calculator.html`
- [ ] List + form + detail for 8 CRUD models (24 templates)

### Admin
- [ ] `accounting/admin.py` — TenantScopedAdmin for all 11 models

### Sidebar
- [ ] `templates/partials/sidebar.html` — add IMS 19 block (5 sub-items)

### Management commands (4)
- [ ] `seed_accounting.py` (idempotent per-tenant)
- [ ] `generate_ap_bills.py` (scan matched VendorInvoices → APBill)
- [ ] `generate_ar_invoices.py` (scan delivered Shipments → ARInvoice)
- [ ] `generate_journal_entries.py` (scan unposted StockAdjustment/ScrapWriteOff → JournalEntry)

### Tests
- [ ] `conftest.py` — fixtures
- [ ] `test_models.py`, `test_forms.py`
- [ ] `test_views_coa.py`, `test_views_periods.py`, `test_views_customers.py`, `test_views_tax.py`
- [ ] `test_views_ap.py`, `test_views_ar.py`, `test_views_journal.py`
- [ ] `test_commands.py` (idempotency)
- [ ] `test_security.py` (OWASP A01/A03/A08/A09)
- [ ] `test_performance.py`

### Verification
- [ ] `pytest.ini` testpaths includes `accounting/tests`
- [ ] README Module 19 block + install steps + demo data
- [ ] `python manage.py makemigrations accounting catalog && python manage.py migrate`
- [ ] `python manage.py seed_accounting` (idempotent check)
- [ ] `python manage.py generate_ap_bills` / `generate_ar_invoices` / `generate_journal_entries`
- [ ] UI smoke test as `admin_acme`
- [ ] `pytest` full project

### Git snippet
- [ ] PowerShell-safe bulk-commit list at end of conversation
