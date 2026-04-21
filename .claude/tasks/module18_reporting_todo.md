# Module 18: Reporting & Analytics — Implementation Plan

**Status:** APPROVED — implementation in progress
**Target app name:** `reporting`
**URL prefix:** `/reporting/`

**Goal:** Build a new Django app `reporting/` delivering **21 analytics reports** grouped in **5 sections**, as saveable report snapshots users can generate, filter, view in-browser (with Chart.js visualizations), and export to CSV/PDF.

**Conventions:** Mirror `quality_control` / `alerts_notifications` layout. Reuse `core.decorators.tenant_admin_required` + `emit_audit`, `core.forms.TenantUniqueCodeMixin`, and the `_save_with_number_retry` pattern.

---

## Locked Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Single `ReportSnapshot` model** with `report_type` discriminator + JSON data | 21 concrete models = 21 migrations, 21 admin pages, 21 seed fragments, massive duplicate boilerplate. All reports share the same shape (metadata + params + computed summary + table). `data` is rendered to HTML/CSV/PDF/Chart.js — typed columns gain nothing. |
| 2 | **Registry pattern** (`reporting/registry.py`) | Map `report_type` → `{display_name, section, service_fn, form_class, csv_columns}`. Generic views dispatch via registry. Adding a new report = 1 compute fn + 1 form + 1 registry entry + 1 detail template fragment. No migration. |
| 3 | **Save snapshots** (not compute-on-render) | Historical auditability ("what did valuation look like 3 months ago?") + expensive computations not re-run on every view. Consistent with stocktaking/valuation persistence. |
| 4 | **Chart.js in v1** | Bar / pie / line charts per report driven by JSON in `snapshot.data.chart`. CDN-loaded in the detail template. |
| 5 | **Scope: 21 reports**, Module 1 (Admin) excluded | Trimmed from 26 — dropped Stock On-Hand (overlaps Valuation), Adjustments (overlaps Stocktaking Variance), Putaway (overlaps Receiving/GRN), Cross-Dock (overlaps Stock Transfers), Barcode/RFID scan activity (thin value). |

---

## The 21 Reports (final scope)

### Section 1: Inventory & Stock (6)
| # | report_type | Title | Data source |
|---|---|---|---|
| 1 | `valuation` | Inventory Valuation | `StockLevel × unit_cost` (ValuationEntry latest / Product.cost) |
| 2 | `aging` | Aging Analysis | `StockLevel` + last movement date (adjustments / transfers / delivered sales) |
| 3 | `abc` | ABC Analysis | `SalesOrderItem` in period × unit_cost → Pareto 80/15/5 |
| 4 | `turnover` | Stock Turnover Ratio | COGS / avg inventory over period |
| 5 | `reservations` | Reservations Report | `InventoryReservation` by status / product / warehouse |
| 6 | `multi_location` | Multi-Location Stock Roll-up | `Location` hierarchy → `StockLevel` aggregate |

### Section 2: Procurement (4)
| # | report_type | Title | Data source |
|---|---|---|---|
| 7 | `po_summary` | PO Summary | `PurchaseOrder` + items — by status, vendor, value, period |
| 8 | `vendor_performance` | Vendor Performance | `VendorPerformanceReview` + on-time delivery ratio from POs/GRNs |
| 9 | `three_way_match` | 3-Way Match Variance | `ThreeWayMatch` — variance per PO↔GRN↔Invoice |
| 10 | `receiving_grn` | Receiving / GRN | `GoodsReceiptNote` + items — received qty, variances, period |

### Section 3: Warehouse Ops (4)
| # | report_type | Title | Data source |
|---|---|---|---|
| 11 | `stock_transfers` | Stock Transfers | `StockTransfer` + items — by status, route, period |
| 12 | `stocktake_variance` | Stocktaking Variance | `StockCount` + `StockVarianceAdjustment` — variance per count |
| 13 | `quality_control` | Quality Control | `QuarantineRecord` + `DefectReport` by status/severity/type |
| 14 | `scrap_writeoff` | Scrap Write-Off | `ScrapWriteOff` — approved/posted by period, value, reason |

### Section 4: Sales & Fulfillment (4)
| # | report_type | Title | Data source |
|---|---|---|---|
| 15 | `so_summary` | Sales Order Summary | `SalesOrder` + items — status, customer, value, period |
| 16 | `fulfillment` | Fulfillment (Pick/Pack/Ship) | `PickList` + `PackingList` + `Shipment` throughput, SLA |
| 17 | `shipment_carrier` | Shipment / Carrier | `Shipment` by carrier, status, tracking events, period |
| 18 | `returns_rma` | Returns (RMA) | `ReturnAuthorization` + items + dispositions + refunds |

### Section 5: Tracking & Ops (3)
| # | report_type | Title | Data source |
|---|---|---|---|
| 19 | `lot_expiry` | Lot / Serial / Expiry | `LotBatch` + `SerialNumber` + `ExpiryAlert` — near/expired |
| 20 | `forecast_vs_actual` | Forecast vs Actual | `DemandForecastLine` vs delivered `SalesOrderItem` in period |
| 21 | `alerts_log` | Alerts & Notifications Log | `Alert` + `NotificationDelivery` — by type/status/period |

---

## Architecture at a Glance

```
reporting/
├── models.py              # Single ReportSnapshot model (report_type discriminator)
├── registry.py            # REPORTS dict mapping report_type → metadata
├── services.py            # 21 compute_<type>(tenant, **params) -> {summary, data, chart}
├── forms.py               # 21 form classes + BaseReportForm
├── views.py               # 7 generic dispatcher views (list/generate/detail/delete/csv/pdf/index)
├── urls.py                # ~8 URL patterns using <slug:report_type> arg
└── templates/reporting/
    ├── index.html         # 5-section landing page
    ├── snapshot_list.html # Generic list (filters on report_type arg)
    ├── snapshot_form.html # Generic form (renders form for report_type)
    ├── snapshot_detail.html # Generic detail (summary + Chart.js + table)
    └── partials/
        ├── _chart_*.html  # Per-report chart config (optional overrides)
        └── _summary_*.html # Per-report summary-card layouts
```

### URL structure (generic — 8 routes total, not 21×6)

```
/reporting/                                 → index_view
/reporting/<report_type>/                   → snapshot_list_view
/reporting/<report_type>/generate/          → snapshot_generate_view
/reporting/<report_type>/<pk>/              → snapshot_detail_view
/reporting/<report_type>/<pk>/delete/       → snapshot_delete_view (POST)
/reporting/<report_type>/<pk>/export/csv/   → snapshot_export_csv_view
/reporting/<report_type>/<pk>/export/pdf/   → snapshot_export_pdf_view
```

---

## Phase 1 — App skeleton + model + project wiring

- [ ] `reporting/__init__.py`, `apps.py`, `admin.py`, `models.py`, `registry.py` (empty stub), `urls.py` (empty with app_name), `forms.py` (empty), `services.py` (empty), `views.py` (empty)
- [ ] `reporting/models.py` — `ReportSnapshot`:
  - `tenant`, `report_number` (auto `RPT-NNNNN` via `_save_with_number_retry`), `report_type` (choices from registry), `title`, `as_of_date`, `period_start`, `period_end`, `warehouse`, `category`, `parameters` JSONField, `summary` JSONField, `data` JSONField, `generated_by`, `generated_at`, `notes`, `created_at`, `updated_at`
  - Indexes `(tenant, report_type)`, `(tenant, generated_at)`
  - `unique_together = ('tenant', 'report_number')`
- [ ] `reporting/admin.py` — `TenantScopedAdmin` registration
- [ ] Add `'reporting'` to `config/settings.py` INSTALLED_APPS
- [ ] Add URL include in `config/urls.py`
- [ ] Run `python manage.py makemigrations reporting`

## Phase 2 — Services (21 compute functions)

- [ ] `reporting/services.py` — one `compute_<slug>(tenant, **params) -> {summary, data, chart}` per report, grouped by section with clear headers.

## Phase 3 — Forms

- [ ] `reporting/forms.py` — `BaseReportForm` (title, warehouse, category, notes) + 21 subclasses with report-specific params (as_of_date, period, thresholds, etc.). All accept `tenant=` kwarg; FKs scoped to tenant.

## Phase 4 — Registry + Views + URLs + Templates

- [ ] `reporting/registry.py` — `REPORTS: dict[str, ReportSpec]` where each entry has `slug, title, section, icon, service_fn, form_class, csv_columns, chart_type, description`.
- [ ] `reporting/views.py` — 7 generic views dispatching via `REPORTS[report_type]`.
- [ ] `reporting/urls.py` — 8 patterns.
- [ ] Templates: `index.html`, `snapshot_list.html`, `snapshot_form.html`, `snapshot_detail.html`.

## Phase 5 — Sidebar + Chart.js

- [ ] `templates/partials/sidebar.html` — add IMS 18 block with 5 section submenus (each has the child reports inline).
- [ ] Load Chart.js CDN in `snapshot_detail.html`; render chart from `snapshot.data.chart`.

## Phase 6 — Seed + Tests

- [ ] `reporting/management/commands/seed_reporting.py` — idempotent, generates one snapshot per report type per tenant.
- [ ] `reporting/tests/conftest.py` + `test_models.py` + `test_services.py` + `test_views.py` + `test_security.py`.

## Phase 7 — README + Verification + Commits

- [ ] Update `README.md` (project tree, Implemented modules, seed list, demo data bullets).
- [ ] `python manage.py migrate` → clean.
- [ ] `python manage.py seed_reporting` → idempotent (twice in a row).
- [ ] Manual smoke: login as `admin_acme`, generate one report per section, confirm CSV/PDF/Chart.js render.
- [ ] `pytest reporting/tests` green.
- [ ] Per-file PowerShell-safe git commits at the end.

---

## Out of scope (v2 candidates)

- Scheduled / auto-generated reports (cron — add later, matches `alerts_notifications` scanner pattern)
- Email dispatch of report attachments
- Report favorites / per-user saved parameter sets
- Drill-down from chart to source records

---

## Review — COMPLETED 2026-04-21

### Outcomes

- **21 reports, 5 sections, 1 model**: `ReportSnapshot` (with `report_type` discriminator) persists every generated report.
- **7 URL patterns cover all 21 reports** via a `<slug:report_type>` URL arg that dispatches through `reporting.registry.REPORTS`.
- **51 reporting tests pass** (models / services / forms / views / security). Project-wide total: **1671 tests pass** (1620 prior + 51 new) — zero regressions.
- **105 seeded snapshots** (21 report types × 5 tenants) generated idempotently by `python manage.py seed_reporting`.
- **Chart.js 4.4.1** loaded from CDN on detail page; bar/pie/doughnut/line driven by `snapshot.data.chart`.
- **CSV export** streamed via `csv.writer`; **PDF export** rendered via reportlab landscape A4 with summary + data tables.
- **Sidebar**: IMS 18 block with 5 section sub-menus + 21 leaf report items + Overview.
- **Security guards verified by tests**: cross-tenant IDOR returns 404 on detail/delete/CSV/PDF; wrong-report-type-for-pk returns 404; @require_POST enforces 405 on GET delete; non-admin tenant users get 403 on generate/delete; anonymous redirected to login.

### Deviations from plan

- **Single model, not 4 separate typed models** — user approved the pivot when scope jumped from 4 → 21 reports (concrete-per-report would have meant 21 migrations, 21 admin pages, 21 seed fragments for no typing gain on JSON `data`).
- **Field-name regressions fixed during Phase 6 seed verification**:
  - `Vendor.company_name` (not `name`)
  - `Alert.triggered_at` (not `created_at`)
  - `DemandForecastLine.period_start_date` / `period_end_date` / `forecast_qty`
  - `GoodsReceiptNote` has no direct `vendor` / `warehouse` FK — vendor resolved via `purchase_order.vendor`
  - `SalesOrder` reverse accessors are `pick_lists` / `packing_lists` / `shipments` (underscore, not camel-case)
  - `PurchaseOrder` / `SalesOrder` have no `total_amount` — totals computed from summed items with discount + tax_rate
  - `Shipment.shipped_date` (not `dispatched_at`) and `actual_delivery_date` (not `delivered_at`)
  - `ThreeWayMatch` has `po_total` / `grn_total` / `invoice_total` fields — variance computed as `|po_total - invoice_total|`
  - `VendorPerformance` (not `VendorPerformanceReview`); no `overall_score` field — computed as avg of `delivery_rating` / `quality_rating` / `compliance_rating`.

### Files created (20) / modified (4)

All listed in the "Files to be CREATED / MODIFIED" sections above. Per-file PowerShell-safe commit commands issued at end of main session output.
