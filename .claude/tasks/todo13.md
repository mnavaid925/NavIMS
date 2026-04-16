# Module 13: Inventory Forecasting & Planning - Implementation Plan

## Module Overview
Module 13: Inventory Forecasting & Planning.
App name: `forecasting/`
URL prefix: `/forecasting/`

## Sub-Modules (4)

### 1. Demand Forecasting
Use historical sales data to predict future demand per product per warehouse.

**Models:**
- **DemandForecast** (`FC-00001`) — forecast header
  - Fields: tenant, forecast_number, name, product (FK), warehouse (FK), method (moving_avg/exp_smoothing/linear_regression/seasonal), period_type (weekly/monthly/quarterly), history_periods (int), forecast_periods (int), confidence_pct, status (draft/approved/archived), notes, created_by, created_at, updated_at
  - Auto-number `FC-00001` pattern
  - unique_together = (tenant, forecast_number)
- **DemandForecastLine** — per-period lines
  - Fields: tenant, forecast (FK), period_index, period_label, period_start_date, period_end_date, historical_qty, forecast_qty, adjusted_qty (after seasonality), notes

**Views:** list, create, detail, edit, delete, **generate** (runs forecast from sales-order history and auto-creates lines).

### 2. Reorder Point (ROP) Calculation
Per product×warehouse ROP definitions and alerts when stock falls below the threshold.

**Models:**
- **ReorderPoint** — per product×warehouse ROP rule
  - Fields: tenant, product (FK), warehouse (FK), avg_daily_usage (decimal), lead_time_days, safety_stock_qty (int, copied from SafetyStock or manual), rop_qty (int, computed), min_qty, max_qty, reorder_qty (int, EOQ or fixed), is_active, last_calculated_at, notes
  - unique_together = (tenant, product, warehouse)
- **ReorderAlert** (`ROA-00001`) — triggered when current stock ≤ ROP
  - Fields: tenant, alert_number, rop (FK), product (FK), warehouse (FK), current_qty, rop_qty, suggested_order_qty, status (new/acknowledged/ordered/closed), triggered_at, acknowledged_by, acknowledged_at, notes
  - Auto-number `ROA-00001`
  - VALID_TRANSITIONS: new→acknowledged/closed, acknowledged→ordered/closed, ordered→closed

**Views:** rop_list/create/detail/edit/delete, rop_recalculate (bulk), alert_list/detail/acknowledge/close.

### 3. Safety Stock Calculation
Buffer stock per product×warehouse using fixed, statistical, or percentage method.

**Models:**
- **SafetyStock** — calculation record
  - Fields: tenant, product (FK), warehouse (FK), method (fixed/statistical/percentage), service_level (decimal 0.50–0.99), avg_demand, demand_std_dev, avg_lead_time_days, lead_time_std_dev, safety_stock_qty (int, computed), calculated_at, notes
  - unique_together = (tenant, product, warehouse)
  - Formula (statistical): Z(service_level) × √((LT × σ_d²) + (μ_d² × σ_LT²))

**Views:** list, create, detail, edit, delete, recalculate.

### 4. Seasonality Planning
Monthly/quarterly demand multipliers applied to forecasts.

**Models:**
- **SeasonalityProfile** — named profile (per category or product)
  - Fields: tenant, name, description, category (FK, optional), product (FK, optional), period_type (month/quarter), is_active, created_by, created_at, updated_at
- **SeasonalityPeriod** — inline child per period
  - Fields: tenant, profile (FK), period_number (1–12 for month, 1–4 for quarter), period_label (auto: Jan/Feb or Q1/Q2), demand_multiplier (decimal, 1.00 = baseline), notes
  - unique_together = (profile, period_number)

**Views:** profile list/create/detail/edit/delete (with inline period formset).

## Integration Points
- `catalog.Product` — FK target for all forecasting records
- `catalog.Category` — FK for seasonality profiles
- `warehousing.Warehouse` — FK for all records
- `orders.SalesOrderItem` — source for historical demand aggregation
- `inventory.StockLevel` — source for current on-hand qty (alert trigger)

## Files to Create

**App skeleton:**
- `forecasting/__init__.py`
- `forecasting/apps.py`
- `forecasting/models.py` (6 models)
- `forecasting/forms.py` (forms for each + seasonality inline formset)
- `forecasting/views.py` (~26 views)
- `forecasting/urls.py`
- `forecasting/admin.py`
- `forecasting/migrations/__init__.py`
- `forecasting/management/__init__.py`
- `forecasting/management/commands/__init__.py`
- `forecasting/management/commands/seed_forecasting.py`

**Templates (`templates/forecasting/`):**
- **Demand Forecasting:** `forecast_list.html`, `forecast_form.html`, `forecast_detail.html`, `forecast_generate.html`
- **Reorder Point:** `rop_list.html`, `rop_form.html`, `rop_detail.html`, `alert_list.html`, `alert_detail.html`, `alert_acknowledge_form.html`
- **Safety Stock:** `safety_stock_list.html`, `safety_stock_form.html`, `safety_stock_detail.html`
- **Seasonality:** `profile_list.html`, `profile_form.html`, `profile_detail.html`

## Files to Modify
- `config/settings.py` — add `'forecasting'` to `INSTALLED_APPS`
- `config/urls.py` — add `path('forecasting/', include('forecasting.urls'))`
- `templates/partials/sidebar.html` — add "Forecasting & Planning" menu with 4 sub-links (Forecasts, Reorder Points, Safety Stock, Seasonality) plus Alerts shortcut
- `README.md` — update project structure + move module to Implemented + update seed list + demo data counts

## Implementation Checklist
- [ ] App setup (`forecasting/` with all __init__.py files)
- [ ] Models: DemandForecast, DemandForecastLine, ReorderPoint, ReorderAlert, SafetyStock, SeasonalityProfile, SeasonalityPeriod
- [ ] Forms: all model forms + SeasonalityPeriod inline formset + generate forecast form
- [ ] Views: list/create/detail/edit/delete for each + generate forecast + recalculate ROP + acknowledge alert
- [ ] URLs: all routes registered
- [ ] Admin: all models registered with inlines
- [ ] Templates (all 16 templates) following established pattern (filters, CRUD actions, status badges)
- [ ] Seeder: `seed_forecasting.py` — idempotent, tenant-scoped, creates demo forecasts/ROPs/alerts/safety stocks/seasonality profiles
- [ ] Register in `config/settings.py` INSTALLED_APPS
- [ ] Register in `config/urls.py`
- [ ] Add sidebar navigation
- [ ] Update README.md
- [ ] Run `makemigrations` + `migrate`
- [ ] Run `seed_forecasting`
- [ ] Verify in browser as tenant admin
- [ ] Provide one-line git commits per changed/created file

## Business Rules
- **ROP formula:** `rop_qty = round(avg_daily_usage × lead_time_days) + safety_stock_qty`
- **Suggested order qty:** `max_qty − current_qty` (bounded below by `reorder_qty`)
- **Safety stock (statistical):** `Z × √((LT × σ_d²) + (μ_d² × σ_LT²))` where Z = NORMSINV(service_level). Use a Z-score lookup for common service levels (0.90→1.28, 0.95→1.645, 0.975→1.96, 0.99→2.33).
- **Seasonality application:** `adjusted_qty = forecast_qty × multiplier` from the matching SeasonalityPeriod for the line's period start date.
- **Alert generation:** expose a "Check ROP Alerts" button on the ROP list that scans StockLevel and creates alerts where current available_qty ≤ rop_qty (idempotent — skip if an open alert already exists for same rop).
- **Forecasting methods:**
  - Moving average: mean of last N historical periods
  - Exponential smoothing: α=0.3, `F_t = α·A_{t-1} + (1−α)·F_{t-1}`
  - Linear regression: simple least-squares trend line over history
  - Seasonal: moving average × matched seasonality multiplier

## Filter/CRUD Compliance (per CLAUDE.md)
- Every list has search + status/warehouse/product filters passed from view via proper context
- Every list row has View/Edit/Delete in Actions column
- Every detail has Edit/Delete/Back in sidebar
- All choices passed as context (`status_choices`, `method_choices`, etc.)
- FK filters use `|stringformat:"d"` for pk comparison

## Review Section

### Implemented
- Created `forecasting/` app with 7 models, ~26 views, all CRUD + action endpoints, 16 templates, seeder, admin registration.
- Registered in `config/settings.py` INSTALLED_APPS and `config/urls.py` (prefix `/forecasting/`).
- Added sidebar submenu "Forecasting & Planning" with 5 links: Demand Forecasts, Reorder Points, Reorder Alerts, Safety Stock, Seasonality Profiles.
- Migrations created & applied cleanly (`forecasting.0001_initial`).
- Seeder runs idempotently; produced: 5 ROPs, 3/2/1 alerts, 4 safety stocks, 2 seasonality profiles, 3 forecasts per tenant (3 tenants total).
- `python manage.py check` passes with zero issues.
- README updated: project structure, seed list, demo data bullets, Module 14 moved from Planned → Implemented.

### Business Logic Delivered
- **Demand Forecasting:** moving average, exponential smoothing, linear regression, seasonal; pulls historical demand from `orders.SalesOrderItem`; generates N future period lines with optional seasonality adjustment.
- **Reorder Point:** ROP = round(avg_daily_usage × lead_time_days) + safety_stock_qty; recomputed on save; "Check ROP Alerts" scans `inventory.StockLevel` for all active ROPs and creates alerts (idempotent — skips if an open alert already exists for the same ROP).
- **Safety Stock:** Fixed / Statistical (Z × √(LT·σ_d² + μ_d²·σ_LT²)) / Percentage methods with Z-score lookup for service levels 0.50–0.99.
- **Seasonality Planning:** Monthly (12) or quarterly (4) multipliers per profile; `multiplier_for_date()` helper applies the right period at forecast-generation time.

### Filter/CRUD Compliance
- Every list has search + status/method/warehouse filters, `|stringformat:"d"` for FK-pk comparison.
- Every list row has View/Edit/Delete in Actions column with POST-only delete + confirm dialog.
- Every detail has Edit/Delete/Back actions in sidebar.
- Choices (`status_choices`, `method_choices`, `period_type_choices`) passed from view context.

### Files Created / Modified
- Created: `forecasting/__init__.py`, `apps.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `migrations/__init__.py`, `migrations/0001_initial.py`, `management/__init__.py`, `management/commands/__init__.py`, `management/commands/seed_forecasting.py`
- Templates: 16 files in `templates/forecasting/`
- Modified: `config/settings.py`, `config/urls.py`, `templates/partials/sidebar.html`, `README.md`

