# NavIMS - Inventory Management System

A comprehensive, multi-tenant Inventory Management System built with Django 4.2 and Bootstrap 5. NavIMS provides a clean, intuitive, and fully responsive dashboard with blue and white theme, supporting multiple layout modes, dark/light themes, and extensive customization options.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Demo Credentials](#demo-credentials)
- [Application Modules](#application-modules)
- [Dashboard Features](#dashboard-features)
- [Multi-Tenancy Architecture](#multi-tenancy-architecture)
- [Browser Compatibility](#browser-compatibility)

---

## Features

### Core Features
- Multi-tenant SaaS architecture with tenant isolation
- Role-Based Access Control (RBAC) with granular permissions
- User management with invite system
- Subscription and pricing plan management
- White-labeling / tenant customization (logo, colors, branding)
- Comprehensive audit logging

### Dashboard Layout
- Vertical, Horizontal & Detached layout modes
- Light & Dark themes
- Fluid & Boxed width options
- Fixed & Scrollable positions
- Light & Dark topbar variants
- Default, Compact, Small Icon & Icon Hover sidebar sizes
- Light, Dark & Colored sidebar themes
- LTR & RTL support
- Animated preloader
- Theme settings panel for live customization

### Authentication
- Login with remember me
- Registration with automatic tenant provisioning
- Forgot password flow
- User invitation with token-based acceptance
- Session management

### User Management
- User listing with search and status filters
- User invite via email with role assignment
- User profile with avatar, contact info, and job title
- Password change functionality
- User activation/deactivation

---

## Tech Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Backend     | Python 3.10+, Django 4.2          |
| Frontend    | Bootstrap 5.3.2, Remix Icon 4.1.0|
| Database    | SQLite (default), PostgreSQL ready|
| Forms       | django-crispy-forms + crispy-bootstrap5 |
| Images      | Pillow                            |
| Slugs       | python-slugify                    |
| Barcodes    | python-barcode, qrcode            |
| PDFs        | reportlab                         |
| JavaScript  | jQuery 3.7.1, Custom Theme Manager|

---

## Project Structure

```
NavIMS/
├── config/                     # Django project configuration
│   ├── settings.py             # Settings with multi-tenant config
│   ├── urls.py                 # Root URL configuration
│   ├── wsgi.py                 # WSGI entry point
│   └── asgi.py                 # ASGI entry point
│
├── core/                       # Core app - multi-tenancy backbone
│   ├── models.py               # Tenant, User, Role, Permission, Subscription, AuditLog
│   ├── middleware.py            # TenantMiddleware (sets request.tenant)
│   ├── context_processors.py   # Template context for current tenant
│   ├── decorators.py           # tenant_admin_required + emit_audit (shared across modules)
│   ├── forms.py                # TenantUniqueCodeMixin (for unique_together(tenant, X) form-layer guard)
│   ├── state_machine.py        # StateMachineMixin (shared can_transition_to helper driven by VALID_TRANSITIONS)
│   ├── admin.py                # Django admin registrations
│   └── management/
│       └── commands/
│           └── seed.py         # Database seeder with demo data
│
├── accounts/                   # Authentication & user management
│   ├── forms.py                # Login, Register, Profile, Invite, Password forms
│   ├── views.py                # Auth views, user CRUD, invitations
│   └── urls.py                 # Account URL routes
│
├── administration/             # Module 1: Multi-Tenant Administration
│   ├── models.py               # PricingPlan, TenantCustomization, BillingHistory
│   ├── forms.py                # Tenant, Subscription, Role, Customization forms
│   ├── views.py                # Tenant CRUD, subscriptions, RBAC, settings
│   └── urls.py                 # Administration URL routes
│
├── catalog/                    # Module 2: Product & Catalog Management
│   ├── models.py               # Category, Product, ProductAttribute, ProductImage, ProductDocument
│   ├── forms.py                # Category, Product, Attribute formset, Image, Document forms
│   ├── views.py                # Full CRUD for categories, products, images, documents (14 views)
│   ├── urls.py                 # Catalog URL routes
│   ├── admin.py                # Admin registration with inlines
│   └── management/
│       └── commands/
│           └── seed_catalog.py # Catalog seeder with demo data
│
├── purchase_orders/            # Module 3: Purchase Order Management
│   ├── models.py               # PurchaseOrder, PurchaseOrderItem, ApprovalRule, PurchaseOrderApproval, PurchaseOrderDispatch
│   ├── forms.py                # PO form, line item formset, dispatch, approval rule & approval forms
│   ├── views.py                # PO CRUD, dispatch with email, status transitions, approval workflows (19 views)
│   ├── urls.py                 # Purchase order URL routes
│   ├── admin.py                # Admin registration with inlines
│   └── management/
│       └── commands/
│           └── seed_purchase_orders.py  # PO seeder with demo data
│
├── receiving/                  # Module 5: Receiving & Putaway
│   ├── models.py               # GoodsReceiptNote, VendorInvoice, ThreeWayMatch, QualityInspection, PutawayTask, WarehouseLocation
│   ├── forms.py                # GRN, Invoice, Match, Inspection, Location, Putaway forms
│   ├── views.py                # Full CRUD for receiving & putaway workflows
│   ├── urls.py                 # Receiving URL routes
│   ├── admin.py                # Admin registration
│   └── management/
│       └── commands/
│           └── seed_receiving.py   # Receiving seeder with demo data
│
├── warehousing/                # Module 6: Warehousing & Bin Management
│   ├── models.py               # Warehouse, Zone, Aisle, Rack, Bin, CrossDockOrder, CrossDockItem
│   ├── forms.py                # Warehouse, Zone, Aisle, Rack, Bin, CrossDock forms
│   ├── views.py                # Full CRUD for all warehouse entities + cross-docking
│   ├── urls.py                 # Warehousing URL routes
│   ├── admin.py                # Admin registration
│   └── management/
│       └── commands/
│           └── seed_warehousing.py  # Warehousing seeder with demo data
│
├── inventory/                  # Module 7: Inventory Tracking & Control
│   ├── models.py               # StockLevel, StockAdjustment, StockStatus, StockStatusTransition, ValuationConfig, InventoryValuation, ValuationEntry, InventoryReservation
│   ├── forms.py                # StockAdjustment, StockStatusTransition, ValuationConfig, InventoryReservation forms
│   ├── views.py                # Stock levels, status management, valuation, reservations (19 views)
│   ├── urls.py                 # Inventory URL routes
│   ├── admin.py                # Admin registration for all 8 models
│   └── management/
│       └── commands/
│           └── seed_inventory.py   # Inventory seeder with demo data
│
├── stock_movements/            # Module 8: Stock Movement & Transfers
│   ├── models.py               # StockTransfer, StockTransferItem, TransferApprovalRule, TransferApproval, TransferRoute
│   ├── forms.py                # Transfer, TransferItem, ApprovalRule, Approval, Route forms
│   ├── views.py                # Transfers CRUD, approval workflow, routes, receiving (18 views)
│   ├── urls.py                 # Stock movements URL routes
│   ├── admin.py                # Admin registration with transfer item inline
│   └── management/
│       └── commands/
│           └── seed_stock_movements.py  # Stock movements seeder with demo data
│
├── lot_tracking/               # Module 9: Lot & Serial Number Tracking
│   ├── models.py               # LotBatch, SerialNumber, ExpiryAlert, TraceabilityLog
│   ├── forms.py                # LotBatch, SerialNumber, ExpiryAcknowledge, TraceabilityLog forms
│   ├── views.py                # Lots, serials, expiry dashboard, traceability (20 views)
│   ├── urls.py                 # Lot tracking URL routes
│   ├── admin.py                # Admin registration for all 4 models
│   └── management/
│       └── commands/
│           ├── seed_lot_tracking.py       # Lot tracking seeder with demo data
│           └── generate_expiry_alerts.py  # Idempotent daily alert generation (approaching/expired lots)
│
├── stocktaking/                # Module 12: Stocktaking & Cycle Counting
│   ├── models.py               # StocktakeFreeze, CycleCountSchedule, StockCount, StockCountItem, StockVarianceAdjustment + _save_with_number_retry
│   ├── forms.py                # Freeze, Schedule, StockCount, StockCountItem (clean_counted_qty guard), VarianceAdjustment forms
│   ├── views.py                # POST-only transitions, atomic posting, double-post + sheet + delete guards, AuditLog emission
│   ├── urls.py                 # Stocktaking URL routes
│   ├── admin.py                # Admin registration with inlines
│   ├── tests/                  # 123 tests — state machines, critical-path posting, D-01/D-02/D-03/D-04/D-05/D-09/D-11/D-15 regression guards
│   └── management/
│       └── commands/
│           └── seed_stocktaking.py  # Stocktaking seeder with demo data
│
├── multi_location/             # Module 13: Multi-Location Management
│   ├── models.py               # Location (self-referential hierarchy), LocationPricingRule, LocationTransferRule, LocationSafetyStockRule
│   ├── forms.py                # Location, PricingRule, TransferRule, SafetyStockRule forms
│   ├── views.py                # Full CRUD for locations + rule models + aggregated global stock visibility dashboard
│   ├── urls.py                 # Multi-Location URL routes
│   ├── admin.py                # Admin registration for all 4 models
│   └── management/
│       └── commands/
│           └── seed_multi_location.py  # Multi-location seeder with demo data
│
├── forecasting/                # Module 14: Inventory Forecasting & Planning
│   ├── models.py               # DemandForecast, DemandForecastLine, ReorderPoint, ReorderAlert, SafetyStock, SeasonalityProfile, SeasonalityPeriod
│   ├── forms.py                # Forecast, ROP, Alert acknowledge, SafetyStock, SeasonalityProfile + SeasonalityPeriod inline formset
│   ├── views.py                # Full CRUD for forecasts/ROPs/alerts/safety-stock/seasonality + generate forecast + ROP alert scan + safety-stock recalc
│   ├── urls.py                 # Forecasting URL routes
│   ├── admin.py                # Admin registration with inlines
│   └── management/
│       └── commands/
│           └── seed_forecasting.py  # Forecasting seeder with demo data
│
├── barcode_rfid/               # Module 15: Barcode & RFID Integration
│   ├── models.py               # LabelTemplate, LabelPrintJob, ScannerDevice, ScanEvent, RFIDTag, RFIDReader, RFIDReadEvent, BatchScanSession, BatchScanItem — TenantUniqueCodeMixin + StateMachineMixin + _save_with_number_retry
│   ├── forms.py                # 7 ModelForms + BatchScanItemFormSet (tenant-aware form_kwargs, zone-vs-warehouse cross-validation)
│   ├── views.py                # 36 views — label template/job CRUD + PDF render, device CRUD + token rotate, RFID tag/reader CRUD + state transitions, batch session CRUD + inline formset + complete/cancel; triad @tenant_admin_required + @require_POST + emit_audit on every destructive/transition endpoint
│   ├── rendering.py            # PDF rendering (reportlab + python-barcode + qrcode) for LabelPrintJob — CODE128/EAN13/UPC-A/QR/mixed
│   ├── api_views.py            # Device-facing JSON API — POST /api/barcode-rfid/{scan,batch-scan,rfid-read,heartbeat}/ with `Authorization: Device <token>` auth, tenant derived from device never payload
│   ├── api_urls.py             # API URL routes
│   ├── urls.py                 # Web URL routes
│   ├── admin.py                # TenantScopedAdmin registrations for all 9 models
│   ├── tests/                  # 158 tests — models/forms/views/security/API covering IDOR, RBAC, state-machine, @require_POST, unique_together trap, formset tenant-injection, API token auth
│   └── management/
│       └── commands/
│           └── seed_barcode_rfid.py  # Idempotent per-tenant seeder (templates, jobs, devices, RFID tags/readers/reads, batch sessions)
│
├── reporting/                 # Module 18: Reporting & Analytics
│   ├── models.py               # ReportSnapshot — single table with `report_type` discriminator (21 slugs), `parameters`/`summary`/`data` JSONFields, RPT-NNNNN auto-number via `_save_with_number_retry`, unique_together(tenant, report_number)
│   ├── registry.py             # REPORTS dict mapping 21 report_type slugs → {title, section, service, form, chart_type, csv_columns, icon} + SECTIONS metadata for the 5-section sidebar
│   ├── services.py             # 21 pure `compute_<slug>(tenant, **params) → {summary, data, chart}` functions covering Inventory Valuation / Aging / ABC / Stock Turnover / Reservations / Multi-Location / PO Summary / Vendor Performance / 3-Way Match Variance / Receiving-GRN / Stock Transfers / Stocktake Variance / Quality Control / Scrap Write-Off / SO Summary / Fulfillment / Shipment-Carrier / Returns-RMA / Lot-Expiry / Forecast-vs-Actual / Alerts-Log
│   ├── forms.py                # BaseReportForm + 21 subclasses via AsOfDateMixin / PeriodMixin; tenant-scoped warehouse/category querysets (formset-FK IDOR closed), threshold / period-ordering validation
│   ├── views.py                # 7 generic dispatcher views keyed by `<slug:report_type>` — index / list (paginated + search + warehouse/date filters) / generate (POST creates snapshot, redirects to detail) / detail / delete (POST-only) / export CSV / export PDF (reportlab landscape A4); triad @tenant_admin_required + @require_POST + emit_audit on generate/delete
│   ├── urls.py                 # 7 URL patterns cover all 21 reports — adding a new report type requires zero URL changes
│   ├── admin.py                # TenantScopedAdmin registration for ReportSnapshot
│   ├── templatetags/           # `dictkey`, `humanize_key`, `is_simple` filters powering the generic detail template
│   ├── tests/                  # 51 tests — models (auto-number, unique_together, tenant-scoped sequence), services (valuation totals, aging buckets, ABC thresholds, regression guards against Vendor.company_name / Alert.triggered_at / DemandForecastLine.period_start_date / GRN.purchase_order.vendor schemas), forms (period ordering, threshold sum, cross-tenant FK rejection), views (list/detail/delete/CSV/PDF for each report type), security (cross-tenant IDOR on detail/delete/CSV/PDF, wrong-report-type IDOR, POST-only on delete, RBAC on generate/delete, anonymous redirected)
│   └── management/
│       └── commands/
│           └── seed_reporting.py   # Idempotent per-tenant seeder — generates one snapshot of each of the 21 report types against existing seeded data (105 snapshots across 5 tenants)
│
├── alerts_notifications/      # Module 17: Alerts & Notifications
│   ├── models.py               # Alert (StateMachineMixin + soft-delete + ALN-NNNNN auto-number + dedup_key), NotificationRule (TenantUniqueCodeMixin + NR-NNNNN), NotificationDelivery (audit log with unique(alert, recipient, channel))
│   ├── forms.py                # AlertForm, NotificationRuleForm (with recipient_users M2M), AlertResolveForm
│   ├── views.py                # ~18 views — alert dashboard/list/detail/form + acknowledge/resolve/dismiss/delete state transitions, rule CRUD + toggle-active, delivery audit log, alert_inbox_json_view for topbar bell hydration; triad @tenant_admin_required + @require_POST + emit_audit on every destructive/transition endpoint
│   ├── urls.py                 # URL routes (app_name='alerts_notifications')
│   ├── admin.py                # TenantScopedAdmin registrations for all 3 models
│   └── management/
│       └── commands/
│           ├── seed_alerts_notifications.py  # Idempotent per-tenant seeder (6 default NotificationRules, 6 sample Alerts)
│           ├── generate_stock_alerts.py      # Scan StockLevel → low_stock / out_of_stock
│           ├── generate_overstock_alerts.py  # Scan LocationSafetyStockRule.max_stock_qty vs StockLevel.on_hand → overstock
│           ├── alerts_scan_expiry.py         # Scan LotBatch.expiry_date → expiry_approaching / expired (named distinctly to avoid collision with lot_tracking.generate_expiry_alerts)
│           ├── generate_workflow_alerts.py   # Scan PO pending-approval stale hours + shipment estimated_delivery overdue → po_approval_pending / shipment_delayed
│           └── dispatch_notifications.py     # For every undelivered Alert, expand matching NotificationRule.recipient_users, send_mail() per email-channel rule, write NotificationDelivery audit row
│
├── quality_control/            # Module 16: Quality Control & Inspection
│   ├── models.py               # QCChecklist, QCChecklistItem, InspectionRoute, InspectionRouteRule, QuarantineRecord, DefectReport, DefectPhoto (ImageField with FileExtensionValidator + size + magic-byte guards), ScrapWriteOff — TenantUniqueCodeMixin + StateMachineMixin + _save_with_number_retry + soft-delete (deleted_at) on top-level docs
│   ├── forms.py                # 7 ModelForms + 3 inline formsets (tenant-aware form_kwargs, zone-vs-warehouse cross-validation, applies-to scoping guards, lot/serial-vs-product match, queryset-union helper so historical FK targets stay editable)
│   ├── views.py                # 35 views — checklist CRUD + toggle_active, route CRUD with inline rules, quarantine CRUD + review/release (auto-creates ScrapWriteOff on scrap disposition), defect CRUD + investigate/resolve/scrap + photo deletion (gated to open/investigating), scrap CRUD + approve/reject/post routed through `can_transition_to()`; post re-fetches the row with `select_for_update()` inside the atomic block (double-post race guard); audit payload records adjustment_number + on_hand delta; triad @tenant_admin_required + @require_POST + emit_audit on every destructive/transition endpoint; segregation-of-duties (requester ≠ approver) on scrap approval
│   ├── templatetags/           # `querystring` template tag — preserves current filter GET params across pagination links
│   ├── urls.py                 # URL routes
│   ├── admin.py                # TenantScopedAdmin registrations with QCChecklistItemInline, InspectionRouteRuleInline, DefectPhotoInline
│   ├── tests/                  # 82 tests — models/forms/views/security/performance/regression covering state machines, IDOR, RBAC, OWASP A01/A03/A08/A09, D-01 race (monkey-patched simulation), D-02 N+1 budgets, D-04 queryset trap, D-07 lot/serial match, D-11 photo-delete gate
│   └── management/
│       └── commands/
│           └── seed_quality_control.py  # Idempotent per-tenant seeder (checklists, routes, quarantines, defects, scrap write-offs — posted scrap creates a real StockAdjustment)
│
├── returns/                    # Module 11: Returns Management (RMA)
│   ├── models.py               # ReturnAuthorization, ReturnAuthorizationItem, ReturnInspection, ReturnInspectionItem, Disposition, DispositionItem, RefundCredit (all 4 top-level models mix in core.state_machine.StateMachineMixin + soft-delete via deleted_at)
│   ├── forms.py                # Tenant-scoped ModelForms + 3 inline formsets with form_kwargs={'tenant': tenant} (closes formset-FK IDOR); refund cap / currency / restock-of-defective guards
│   ├── views.py                # CRUD + 14 transition endpoints — each wrapped in @tenant_admin_required + @require_POST + emit_audit; disposition process is transaction.atomic() with select_for_update(); scrap path decrements on_hand symmetrically with restock
│   ├── urls.py                 # Returns URL routes
│   ├── admin.py                # TenantScopedAdmin base filters admin queryset by request.user.tenant for non-superusers
│   └── management/
│       └── commands/
│           └── seed_returns.py # Returns seeder with demo data (per sub-model idempotency)
│
├── orders/                     # Module 10: Order Management & Fulfillment
│   ├── models.py               # Carrier, ShippingRate, SalesOrder, SalesOrderItem, WavePlan, WaveOrderAssignment, PickList, PickListItem, PackingList, Shipment, ShipmentTracking
│   ├── forms.py                # SalesOrder, SalesOrderItem formset, PickList, PickListItem formset, PackingList, Shipment, ShipmentTracking, WavePlan, WaveOrderSelection, Carrier, ShippingRate forms
│   ├── views.py                # Full CRUD for all entities + status transitions + inventory integration (58 views)
│   ├── urls.py                 # Orders URL routes
│   ├── admin.py                # Admin registration for all 11 models
│   └── management/
│       └── commands/
│           └── seed_orders.py  # Orders seeder with demo data
│
├── dashboard/                  # Dashboard app
│   ├── views.py                # Dashboard view with stats
│   └── urls.py                 # Dashboard URL route
│
├── templates/                  # All HTML templates
│   ├── base.html               # Master layout template
│   ├── partials/               # Reusable template components
│   │   ├── topbar.html         # Top navigation bar
│   │   ├── sidebar.html        # Side navigation menu
│   │   ├── footer.html         # Page footer
│   │   ├── preloader.html      # Loading spinner
│   │   └── theme_settings.html # Theme customizer offcanvas panel
│   ├── auth/                   # Authentication pages
│   │   ├── login.html          # Login page
│   │   ├── register.html       # Registration page
│   │   ├── forgot_password.html# Password reset page
│   │   └── accept_invite.html  # Invitation acceptance page
│   ├── dashboard/
│   │   └── index.html          # Dashboard with stats & activity
│   ├── accounts/
│   │   ├── profile.html        # User profile & password change
│   │   ├── user_list.html      # User management table
│   │   └── user_invite.html    # Send user invitation
│   ├── administration/
│   │   ├── tenant_list.html    # Tenant listing
│   │   ├── tenant_form.html    # Tenant create/edit
│   │   ├── tenant_detail.html  # Tenant details & subscription
│   │   ├── subscription_list.html
│   │   ├── subscription_form.html
│   │   ├── role_list.html      # Roles & permissions
│   │   ├── role_form.html      # Role create/edit
│   │   └── settings.html       # Tenant customization settings
│   ├── catalog/
│   │   ├── category_list.html  # Category listing with filters
│   │   ├── category_form.html  # Category create/edit
│   │   ├── category_detail.html# Category details with children & products
│   │   ├── product_list.html   # Product listing with filters
│   │   ├── product_form.html   # Product create/edit with attributes
│   │   └── product_detail.html # Product details with images & documents
│   ├── purchase_orders/
│   │   ├── po_list.html        # PO listing with search, status/vendor/date filters
│   │   ├── po_form.html        # PO create/edit with dynamic line item formset
│   │   ├── po_detail.html      # PO details with status timeline, items, dispatch & approval history
│   │   ├── po_dispatch.html    # PO dispatch form with email sending and PO summary preview
│   │   ├── approval_list.html  # Pending approvals for current user
│   │   ├── approval_rule_list.html  # Approval rules management
│   │   └── approval_rule_form.html  # Approval rule create/edit
│   ├── receiving/
│   │   ├── grn_list.html       # GRN listing with filters
│   │   ├── grn_form.html       # GRN create/edit
│   │   ├── grn_detail.html     # GRN details with items
│   │   ├── invoice_list.html   # Vendor invoice listing
│   │   ├── invoice_form.html   # Invoice create/edit
│   │   ├── invoice_detail.html # Invoice details
│   │   ├── match_list.html     # Three-way match listing
│   │   ├── match_detail.html   # Match details
│   │   ├── inspection_list.html    # Quality inspection listing
│   │   ├── inspection_form.html    # Inspection create/edit
│   │   ├── inspection_detail.html  # Inspection details
│   │   ├── location_list.html  # Warehouse location listing
│   │   ├── location_form.html  # Location create/edit
│   │   ├── location_detail.html# Location details
│   │   ├── putaway_list.html   # Putaway task listing
│   │   ├── putaway_form.html   # Putaway create/edit
│   │   └── putaway_detail.html # Putaway details
│   ├── warehousing/
│   │   ├── warehouse_list.html # Warehouse listing with filters
│   │   ├── warehouse_form.html # Warehouse create/edit
│   │   ├── warehouse_detail.html   # Warehouse details with zones
│   │   ├── warehouse_map.html  # Warehouse visual map
│   │   ├── zone_list.html      # Zone listing
│   │   ├── zone_form.html      # Zone create/edit
│   │   ├── zone_detail.html    # Zone details
│   │   ├── bin_list.html       # Bin listing
│   │   ├── bin_form.html       # Bin create/edit
│   │   ├── bin_detail.html     # Bin details
│   │   ├── crossdock_list.html # Cross-dock order listing
│   │   ├── crossdock_form.html # Cross-dock create/edit
│   │   └── crossdock_detail.html   # Cross-dock details with timeline
│   ├── inventory/
│   │   ├── stock_level_list.html       # Stock levels with warehouse & low-stock filters
│   │   ├── stock_level_detail.html     # Stock level details with quantity breakdown
│   │   ├── stock_adjust_form.html      # Stock adjustment form
│   │   ├── stock_adjustment_list.html  # Adjustment history with type & reason filters
│   │   ├── stock_adjustment_detail.html# Adjustment details
│   │   ├── stock_status_list.html      # Stock status with status & warehouse filters
│   │   ├── stock_status_detail.html    # Status details with transition history
│   │   ├── stock_status_transition_form.html  # Status transition form
│   │   ├── stock_status_transition_list.html  # Transition history list
│   │   ├── valuation_dashboard.html    # Valuation dashboard with summary cards
│   │   ├── valuation_detail.html       # Product valuation with cost layers
│   │   ├── valuation_config_form.html  # Valuation method configuration
│   │   ├── reservation_list.html       # Reservations with status & warehouse filters
│   │   ├── reservation_form.html       # Reservation create/edit
│   │   └── reservation_detail.html     # Reservation details with status timeline
│   ├── stock_movements/
│   │   ├── transfer_list.html          # Transfer listing with status/type/warehouse filters
│   │   ├── transfer_form.html          # Transfer create/edit with dynamic line items
│   │   ├── transfer_detail.html        # Transfer details with status timeline & actions
│   │   ├── transfer_receive_form.html  # Receive items with quantity inputs
│   │   ├── approval_rule_list.html     # Approval rules management
│   │   ├── approval_rule_form.html     # Approval rule create/edit
│   │   ├── pending_approval_list.html  # Pending transfer approvals
│   │   ├── transfer_approval_form.html # Approve/reject transfer form
│   │   ├── route_list.html             # Transfer routes with method/active filters
│   │   ├── route_form.html             # Route create/edit
│   │   └── route_detail.html           # Route details with related transfers
│   ├── lot_tracking/
│   │   ├── lot_list.html               # Lot/batch listing with status/warehouse filters
│   │   ├── lot_form.html               # Lot create/edit with product, warehouse, GRN
│   │   ├── lot_detail.html             # Lot details with serials, trace logs, expiry alerts
│   │   ├── lot_trace.html              # Forward/backward lot traceability timeline
│   │   ├── serial_list.html            # Serial number listing with status/warehouse filters
│   │   ├── serial_form.html            # Serial number register/edit
│   │   ├── serial_detail.html          # Serial details with trace history
│   │   ├── serial_trace.html           # Serial number full trace timeline
│   │   ├── expiry_dashboard.html       # Expiry management dashboard with stat cards
│   │   ├── expiry_alert_list.html      # Expiry alerts with type/acknowledged filters
│   │   ├── expiry_acknowledge_form.html# Acknowledge expiry alert
│   │   ├── traceability_list.html      # Full traceability audit log with filters
│   │   ├── traceability_detail.html    # Traceability log entry details
│   │   └── traceability_form.html      # Manual traceability log entry
│   ├── barcode_rfid/
│   │   ├── label_template_list.html    # Label template listing with type/active filters
│   │   ├── label_template_form.html    # Label template create/edit
│   │   ├── label_template_detail.html  # Template detail with recent jobs
│   │   ├── label_job_list.html         # Print job listing with status/target-type filters
│   │   ├── label_job_form.html         # Print job create/edit
│   │   ├── label_job_detail.html       # Print job detail with state-transition buttons + PDF link
│   │   ├── device_list.html            # Scanner device listing with status/type filters
│   │   ├── device_form.html            # Device register/edit
│   │   ├── device_detail.html          # Device detail with API token + rotate-token action + recent scans
│   │   ├── scan_event_list.html        # Scan event ledger with scan_type/status filters
│   │   ├── scan_event_detail.html      # Scan event detail
│   │   ├── rfid_tag_list.html          # RFID tag listing with status/type filters
│   │   ├── rfid_tag_form.html          # RFID tag register/edit
│   │   ├── rfid_tag_detail.html        # Tag detail with state transitions + recent reads
│   │   ├── rfid_reader_list.html       # Reader listing with status/warehouse filters
│   │   ├── rfid_reader_form.html       # Reader register/edit
│   │   ├── rfid_reader_detail.html     # Reader detail with recent reads
│   │   ├── rfid_read_list.html         # RFID read event ledger with direction filter
│   │   ├── rfid_read_detail.html       # RFID read detail
│   │   ├── batch_session_list.html     # Batch session listing with status/purpose/warehouse filters
│   │   ├── batch_session_form.html     # Batch session create/edit with inline item formset
│   │   └── batch_session_detail.html   # Batch session detail with items + complete/cancel actions
│   ├── alerts_notifications/
│   │   ├── alert_dashboard.html        # KPI cards + open-by-type breakdown + recent-alerts table
│   │   ├── alert_list.html             # Alert inbox with search + status/severity/type/warehouse filters + action buttons
│   │   ├── alert_detail.html           # Alert detail with source-object card + delivery log + sidebar actions (Acknowledge / Resolve / Dismiss / Delete)
│   │   ├── alert_form.html             # Manual alert create form
│   │   ├── rule_list.html              # Notification rule listing with alert-type / active filters
│   │   ├── rule_form.html              # Rule create/edit with recipient-users multi-select
│   │   ├── rule_detail.html            # Rule detail with recipients list + matching-alerts table + actions
│   │   ├── delivery_list.html          # Notification delivery audit log with status/channel filters
│   │   ├── delivery_detail.html        # Single-delivery detail view
│   │   └── partials/
│   │       ├── _alert_badge.html       # Severity + status pill fragment (reusable)
│   │       └── _alert_inbox_item.html  # Topbar-dropdown row fragment
│   ├── reporting/
│   │   ├── index.html                  # 5-section landing page with report cards + Recent Snapshots table
│   │   ├── snapshot_list.html          # Saved-snapshots list per report type with search + warehouse/date filters + CSV/PDF/delete action buttons
│   │   ├── snapshot_form.html          # Generic generate form — renders any of the 21 report-specific forms
│   │   └── snapshot_detail.html        # KPI summary cards + Chart.js (bar/pie/doughnut/line) + data table + sidebar actions (Export CSV / Export PDF / Regenerate / Delete)
│   ├── quality_control/
│   │   ├── checklist_list.html         # QC checklist listing with scope/active filters
│   │   ├── checklist_form.html         # Checklist create/edit with inline item formset
│   │   ├── checklist_detail.html       # Checklist detail with items + toggle-active action
│   │   ├── route_list.html             # Inspection route listing with warehouse/active filters
│   │   ├── route_form.html             # Route create/edit with inline rule formset
│   │   ├── route_detail.html           # Route detail with rules
│   │   ├── quarantine_list.html        # Quarantine listing with status/reason/warehouse filters
│   │   ├── quarantine_form.html        # Quarantine create/edit
│   │   ├── quarantine_detail.html      # Quarantine detail with release form + linked defects/scrap
│   │   ├── defect_list.html            # Defect listing with status/severity/type/source filters
│   │   ├── defect_form.html            # Defect create/edit with inline photo formset
│   │   ├── defect_detail.html          # Defect detail with photos + investigate/resolve/scrap actions
│   │   ├── scrap_list.html             # Scrap listing with approval-status/warehouse filters
│   │   ├── scrap_form.html             # Scrap create/edit
│   │   └── scrap_detail.html           # Scrap detail with approve/reject/post actions
│   └── orders/
│       ├── so_list.html                # Sales order listing with status/warehouse/date filters
│       ├── so_form.html                # Sales order create/edit with inline line item formset
│       ├── so_detail.html              # Sales order details with timeline, items, pick/pack/ship sections
│       ├── picklist_list.html          # Pick list listing with status/warehouse filters
│       ├── picklist_form.html          # Pick list create/edit with item formset
│       ├── picklist_detail.html        # Pick list details with items and assign/start/complete actions
│       ├── packinglist_list.html       # Packing list listing with status filters
│       ├── packinglist_form.html       # Packing list create/edit with dimensions
│       ├── packinglist_detail.html     # Packing list details with picked items
│       ├── shipment_list.html          # Shipment listing with status/carrier filters
│       ├── shipment_form.html          # Shipment create/edit
│       ├── shipment_detail.html        # Shipment details with tracking events timeline
│       ├── wave_list.html              # Wave plan listing with status/warehouse filters
│       ├── wave_form.html              # Wave plan create/edit with order multi-select
│       ├── wave_detail.html            # Wave plan details with assigned orders and pick lists
│       ├── carrier_list.html           # Carrier listing with active/inactive filter
│       ├── carrier_form.html           # Carrier create/edit
│       ├── carrier_detail.html         # Carrier details with rates and shipments
│       ├── shippingrate_list.html      # Shipping rate listing with carrier filter
│       └── shippingrate_form.html      # Shipping rate create/edit
│
├── static/                     # Static assets
│   ├── css/
│   │   └── style.css           # Custom theme CSS (blue & white)
│   ├── js/
│   │   └── app.js              # Theme manager, sidebar, utilities
│   └── images/                 # Favicon & static images
│
├── requirements.txt            # Python dependencies
├── manage.py                   # Django management script
└── IMS.md                      # Full IMS specification (20 modules)
```

---

## Installation

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)
- Git

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/mnavaid925/NavIMS.git
   cd NavIMS
   ```

2. **Create and activate virtual environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run database migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Seed demo data**
   ```bash
   python manage.py seed
   python manage.py seed_catalog
   python manage.py seed_vendors
   python manage.py seed_purchase_orders
   python manage.py seed_receiving
   python manage.py seed_warehousing
   python manage.py seed_inventory
   python manage.py seed_stock_movements
   python manage.py seed_lot_tracking
   python manage.py seed_orders
   python manage.py seed_returns
   python manage.py seed_stocktaking
   python manage.py seed_multi_location
   python manage.py seed_forecasting
   python manage.py seed_barcode_rfid
   python manage.py seed_quality_control
   python manage.py seed_alerts_notifications
   python manage.py seed_reporting
   ```

   To reset and re-seed:
   ```bash
   python manage.py seed --flush
   python manage.py seed_catalog --flush
   python manage.py seed_vendors --flush
   python manage.py seed_purchase_orders --flush
   python manage.py seed_receiving --flush
   python manage.py seed_warehousing --flush
   python manage.py seed_inventory --flush
   python manage.py seed_stock_movements --flush
   python manage.py seed_lot_tracking --flush
   python manage.py seed_orders --flush
   python manage.py seed_returns --flush
   python manage.py seed_stocktaking --flush
   python manage.py seed_multi_location --flush
   python manage.py seed_forecasting --flush
   python manage.py seed_barcode_rfid --flush
   python manage.py seed_quality_control --flush
   python manage.py seed_alerts_notifications --flush
   python manage.py seed_reporting --flush
   ```

   After seeding, run the alert scanners and dispatcher (safe to schedule in cron):
   ```bash
   python manage.py generate_stock_alerts
   python manage.py generate_overstock_alerts
   python manage.py alerts_scan_expiry
   python manage.py generate_workflow_alerts
   python manage.py dispatch_notifications
   ```

---

## Running the Application

```bash
python manage.py runserver
```

Open your browser and navigate to: **http://127.0.0.1:8000**

---

## Testing

NavIMS ships with an automated test suite covering models, forms, views, security (OWASP-aligned), and performance guardrails. Tests run against a separate in-memory SQLite database with a fast password hasher — they do not touch your development DB and require no extra configuration.

### Test stack

| Layer                 | Tool                              |
|-----------------------|-----------------------------------|
| Runner                | `pytest` + `pytest-django`        |
| Test settings         | `config/settings_test.py` (SQLite `:memory:`, MD5 hasher) |
| Coverage (optional)   | `coverage` + `pytest-cov`         |
| Security (optional)   | `bandit`, `pip-audit`             |

All testing dependencies are already declared in `requirements.txt`.

### Running the suite

```bash
# From the project root, with the venv activated
pytest
```

Run a specific module's suite:

```bash
pytest receiving/tests
pytest stock_movements/tests
pytest warehousing/tests -k "security"
```

Run a single test:

```bash
pytest stock_movements/tests/test_views_transfers.py::TestTransferCreate::test_D01_cross_tenant_product_rejected
```

### Suite layout

Each tested module follows the same structure:

```
<module>/tests/
  __init__.py
  conftest.py              # shared tenant / user / fixture objects
  test_models.py           # model invariants, properties, auto-number
  test_forms.py            # clean() rules, tenant scoping, boundary checks
  test_views_*.py          # integration + cross-tenant IDOR + status transitions
  test_security.py         # OWASP A01 / A03 / A08 mapped
  test_performance.py      # django_assert_max_num_queries N+1 budgets
```

Reference implementation: [receiving/tests/](./receiving/tests/) and [stock_movements/tests/](./stock_movements/tests/).

### Coverage by module

| Module            | Tests | Focus |
|-------------------|-------|-------|
| catalog           | 40    | Product / Category / Attributes / Images / Documents |
| vendors           | 78    | Vendors, contracts, communications, document upload validation |
| purchase_orders   | 70    | PO CRUD, approval workflow, dispatch, line-item IDOR |
| receiving         | 76    | GRN, Vendor Invoice (3-way match), Quality Inspection, Putaway |
| warehousing       | 104   | Warehouse/Zone/Aisle/Rack/Bin hierarchy, cross-docking, unique-code traps |
| inventory         | 90    | Stock levels, adjustments, status transitions, valuation, reservations |
| stock_movements   | 69    | Transfers (inter/intra), approvals, routes, receive flow |
| lot_tracking      | 115   | Lot/batch, serials, expiry alerts, traceability, idempotent alert-generation command |
| orders            | 83    | Sales orders, pick/pack/ship, waves, carriers — cross-tenant IDOR on inline formsets, state-machine integrity, delivery deduction, audit-log + RBAC gates |
| returns           | 150   | RMA, inspection, disposition, refund — refund cap + currency, restock-of-defective refusal, ledger symmetry, 14-endpoint CSRF coverage, formset IDOR across 3 inline formsets, soft-delete + admin tenant scope + shared `core.state_machine` mixin |
| stocktaking       | 136   | Freeze, cycle schedule, stock count, variance adjustment — atomic posting via `apply_adjustment('correction')` (single canonical write path), double-post guard, POST-only transitions, `@tenant_admin_required` RBAC across 16 destructive views, AuditLog, negative-qty validator, zone-vs-warehouse cross-validation, schedule-run idempotency |
| barcode_rfid      | 158   | Label templates/jobs, scanner devices, RFID tags/readers/reads, batch scanning — state-machine transitions with can_transition_to + @require_POST + @tenant_admin_required + emit_audit, unique_together(tenant,X) form-layer guards via `TenantUniqueCodeMixin`, inline-formset tenant-injection refusal, zone-vs-warehouse cross-validation, device API token auth (tenant derived from device never payload), PDF render smoke test |
| quality_control   | 82    | QC checklists, inspection routes, quarantine, defect reports (with photo uploads), scrap write-offs — OWASP A01/A03/A08/A09 matrix, D-01 scrap-post race guard (monkey-patched simulation), D-02 N+1 budgets, D-03 upload hygiene (ext + size + magic bytes), D-04 queryset-union regression, D-07 lot/serial vs product match, D-11 photo-delete gate, segregation-of-duties on scrap approval, atomic `decrease` StockAdjustment via `apply_adjustment()` |
| alerts_notifications | 101 | Alert CRUD + state machine + inbox JSON, NotificationRule CRUD + toggle-active, Delivery audit log, 4 scanners + dispatcher — OWASP A01 IDOR sweep across 10 endpoints, CSRF 405 on @require_POST, RBAC 403 on tenant_admin_required, A03 XSS via topbar escapeHtml(), A09 AuditLog on every mutation, D-01/D-02 superuser-tenant-None create guard, D-04 notes cap 2000/16384, D-06 uuid4 dedup_key, D-11 rule_list |length budget, min_severity threshold matching, dispatcher idempotency via unique_together(alert, recipient, channel) |
| reporting         | 51    | `ReportSnapshot` single-model + 21-slug registry — auto-number RPT-NNNNN, per-tenant sequence independence, JSON field round-trip; services invariants (valuation totals, aging bucket classification, ABC threshold split, turnover shape); forms (a+b<100, period ordering, tenant-scoped warehouse/category queryset, cross-tenant FK rejection); views for each of the 21 report types (list/generate/detail/delete/CSV/PDF); security — cross-tenant IDOR on detail/delete/CSV/PDF, wrong-report-type-for-pk IDOR, POST-only on delete (405 on GET), RBAC 403 on generate/delete for non-admin, anonymous redirected; regression guards against Vendor.company_name / Alert.triggered_at / DemandForecastLine.period_start_date / GRN.purchase_order.vendor schemas |
| **Total**         | **1671** | |

Run `pytest` at the project root to execute all modules in one pass (~25 s on a warm cache).

### What the suite guards against

Each module's `test_security.py` + `test_regression.py` files codify real defects that surfaced during SQA review. Notable categories:

- **Cross-tenant IDOR** — foreign-tenant FK injection via `request.POST` on every write path that accepts IDs (products, PO items, GRN items, transfer items).
- **`unique_together(tenant, X)` form-bypass** — duplicate detection at form layer, before the DB raises `IntegrityError`.
- **Status-machine transitions** — `can_transition_to` coverage, segregation-of-duties (requester cannot self-approve), terminal-state enforcement.
- **File upload hygiene** — extension whitelist, size caps, SVG/executable blocks on `VendorInvoice.document` and `VendorContract.document`.
- **Race conditions** — atomic auto-numbering with `IntegrityError` retry for `GRN-NNNNN`, `TRF-NNNNN`, `PO-NNNNN`, `LOT-NNNNN`, `FRZ-NNNNN`, `CNT-NNNNN`, `VADJ-NNNNN`, etc.
- **CSRF via GET** — every state-mutating view carries `@require_POST`; server-side enforcement, never relying on template-level POST forms alone.
- **Atomic multi-write flows** — stock-level mutations across `StockAdjustment` + `StockLevel` rows wrap in `transaction.atomic()` + `select_for_update()` so partial failures roll back cleanly (stocktaking post, returns process).
- **N+1 queries** — `django_assert_max_num_queries` budgets on every list view and multi-item detail view.
- **Financial reconciliation** — three-way match must compare all three totals (PO ↔ Invoice ↔ GRN).
- **RBAC on destructive ops** — `@tenant_admin_required` gates every create / edit / delete / status-transition endpoint; non-admin tenant users are limited to reads.
- **Security-grade audit trail** — `core.AuditLog` rows emitted on every mutating request alongside any domain-level log.
- **Refund / credit caps** — `RefundCreditForm.clean()` rejects `amount ≤ 0` and `amount > rma.total_value - already_refunded` (sums non-cancelled refunds), closing the over-refund class.
- **Soft-delete + admin tenant scope** — top-level returns models use `deleted_at` soft-delete; list / detail / transition queries filter `deleted_at__isnull=True`. `TenantScopedAdmin` keeps tenant admins out of other tenants' `/admin/` rows.
- **Segregation of duties** — `rma_approve_view` refuses if `rma.created_by == request.user`, enforcing the "creator ≠ approver" rule on financial flows.

### Shared helpers

Recurring cross-cutting fixes have been lifted into `core/` so new modules pick them up by default instead of reinventing them:

- **[`core.decorators.tenant_admin_required`](./core/decorators.py)** — `@login_required`-compatible decorator that additionally requires `user.is_tenant_admin` (or `is_superuser`). Apply to every create/edit/delete/transition view.
- **[`core.decorators.emit_audit`](./core/decorators.py)** — one-line `AuditLog` emission: `emit_audit(request, 'delete', instance, changes='…')`. Silently no-ops when `request.tenant` is unset.
- **[`core.forms.TenantUniqueCodeMixin`](./core/forms.py)** — generalised form-layer guard for `unique_together = ('tenant', <field>)`. Mix into any `ModelForm` whose tenant is injected in `save()` instead of being a form field; set `tenant_unique_field = '<field_name>'` and call `self._clean_tenant_unique_field('<field_name>')` from `clean_<field>()`.
- **[`core.state_machine.StateMachineMixin`](./core/state_machine.py)** — declare `VALID_TRANSITIONS: dict[str, list[str]]` on a model and mix in `StateMachineMixin` to get `can_transition_to(new_status)` for free. Replaces the copy-paste method that lived in five modules. First adopted in `returns/`; other modules (`vendors`, `orders`, `receiving`, `lot_tracking`, `stock_movements`) can migrate in ~20 lines each.
- **Soft-delete pattern** — top-level domain models expose a nullable `deleted_at = DateTimeField` and their delete views set `deleted_at = timezone.now()` instead of calling `.delete()`. List + detail + transition queries filter `deleted_at__isnull=True` at every call site; `AuditLog` records the deletion. Adopted in `returns/` (D-15); recommended for any module where audit traceability outweighs storage cost.
- **Admin tenant scoping (`TenantScopedAdmin` pattern)** — `ModelAdmin.get_queryset` filters rows by `request.user.tenant` when the user is a tenant admin, bypassed for superusers. Closes the "tenant admin sees every tenant in /admin/" cross-tenant exposure. Reference: [returns/admin.py](./returns/admin.py).

### Writing new tests

Use the `conftest.py` fixtures already established — do not redefine `tenant`, `user`, `client_logged_in`, etc. The canonical fixture pattern:

```python
@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        username="qa_user", password="qa_pass_123!",
        tenant=tenant, is_tenant_admin=True,
    )
```

A second-tenant fixture (`other_tenant`, `other_user`, `other_product`, `other_warehouse`) is provided everywhere — use it to exercise cross-tenant IDOR scenarios.

When you fix a defect, add a regression test named `test_D<NN>_<short_description>` so the intent is searchable and traceable back to the SQA review in `.claude/reviews/`.

---

## Demo Credentials

The seed command creates the following demo accounts:

| Role             | Username        | Password  | Tenant              |
|------------------|-----------------|-----------|----------------------|
| Super Admin      | admin           | admin123  | None (global access) |
| Tenant Admin     | admin_acme      | demo123   | Acme Industries      |
| Tenant Admin     | admin_global    | demo123   | Global Supplies Co   |
| Tenant Admin     | admin_techware  | demo123   | TechWare Solutions   |

> **Note:** The super admin (`admin`) has no tenant assigned. Login as a tenant admin to see tenant-specific data.

### Demo Data Includes
- 4 pricing plans (Free, Starter, Professional, Enterprise)
- 3 tenants with subscriptions
- 3 tenant admin users + 8 regular users
- 4 roles per tenant (Admin, Manager, Warehouse Staff, Viewer)
- 11 global permissions across IMS modules
- Tenant customizations with different brand colors
- 3 pending user invitations
- 21 categories per tenant (3 departments, 6 categories, 12 sub-categories)
- 12 products per tenant with pricing, dimensions, and custom attributes
- 32 product attributes per tenant
- 5 vendors per tenant with contacts, addresses, and terms
- 5 vendor performance reviews per tenant
- 5 vendor contracts per tenant
- 5 vendor communication logs per tenant
- 3 approval rules per tenant (low/medium/high value thresholds)
- 8 purchase orders per tenant across all statuses (draft through closed)
- 16 PO line items per tenant with pricing, tax, and discounts
- 5 PO approval records per tenant
- 6 warehouse locations per tenant
- 6 goods receipt notes per tenant
- 6 vendor invoices per tenant
- 6 three-way matches per tenant
- 6 quality inspections per tenant
- 6 putaway tasks per tenant
- 2 warehouses per tenant with zones, aisles, racks, and bins
- 3 cross-dock orders per tenant
- 16 stock levels per tenant (8 products x 2 warehouses)
- 20+ stock status records per tenant (active, damaged, on-hold)
- 4 stock adjustments per tenant
- 3 stock status transitions per tenant
- 35+ valuation entries (cost layers) per tenant
- 16 inventory valuations per tenant
- 4 inventory reservations per tenant across statuses
- 1 valuation configuration per tenant (weighted average default)
- 3 transfer approval rules per tenant (small/medium/large)
- 3 transfer routes per tenant (primary/return/express)
- 6 stock transfers per tenant across all statuses (draft through completed)
- ~17 transfer items per tenant
- 4 transfer approval records per tenant
- 8 lot/batches per tenant (active, quarantine, expired, consumed, recalled)
- 12 serial numbers per tenant across all statuses
- 5 expiry alerts per tenant (approaching, expired, recalled)
- 10 traceability logs per tenant (received, transferred, sold, etc.)
- 4 shipping carriers per tenant (FedEx, UPS, DHL, USPS)
- 6 shipping rates per tenant across carriers and service levels
- 8 sales orders per tenant across all statuses (draft through delivered)
- ~16 sales order line items per tenant with pricing, tax, and discounts
- 1 wave plan per tenant with 4 assigned orders
- 5 pick lists per tenant with items (in_progress and completed)
- 3 packing lists per tenant (completed with dimensions)
- 2 shipments per tenant with tracking events (dispatched and delivered)
- 5 RMAs per tenant across all statuses (draft through closed)
- ~10 RMA line items per tenant linked to sales order items
- 2 return inspections per tenant with per-item condition and restockable flags
- 2 dispositions per tenant with decisions (restock/repair/scrap/liquidate)
- 2 refund/credit records per tenant across types and methods
- 2 cycle count schedules per tenant (weekly Class A, monthly Class B)
- 1 active warehouse freeze per tenant (year-end count)
- 3 stock counts per tenant (draft cycle, in-progress blind cycle, adjusted full)
- ~18 stock count items per tenant (6 per count)
- 1 posted variance adjustment per tenant with real inventory posting
- 2 seasonality profiles per tenant (monthly summer peak, quarterly holiday season)
- 16 seasonality period multipliers per tenant (12 monthly + 4 quarterly)
- 4 safety stock configurations per tenant across fixed / statistical / percentage methods
- 5 reorder point rules per tenant with auto-computed ROP quantities
- 3 reorder alerts per tenant across new / acknowledged / ordered statuses
- 3 demand forecasts per tenant (monthly moving average, quarterly seasonal, monthly linear regression)
- ~30 forecast lines per tenant (historical + projected)
- 3 label templates per tenant (product CODE128, bin QR, shipping mixed)
- 2 label print jobs per tenant (1 printed + 1 draft)
- 3 scanner devices per tenant (2 handheld Zebra/Honeywell + 1 Samsung tablet under maintenance)
- 10 scan events per tenant across receive / pick / count / lookup / transfer
- 8 RFID tags per tenant across all statuses (active, unassigned, inactive, lost, damaged, retired)
- 2 RFID readers per tenant (1 fixed gate + 1 handheld)
- 15 RFID read events per tenant with varying direction, signal strength, and antenna
- 2 batch scan sessions per tenant (receiving completed + counting active) with ~8 items total
- 3 QC checklists per tenant (1 global, 1 product-scoped, 1 vendor-scoped) with 3-5 items each and mix of critical/non-critical checks
- 2 inspection routes per tenant (standard + express) with 2 rules each (product/vendor/category scoping)
- 4 quarantine records per tenant across all statuses (active, under_review, released, scrapped)
- 5 defect reports per tenant across severities (minor/major/critical) and sources (receiving, stocktaking, customer_return, production)
- 2 scrap write-offs per tenant (1 pending, 1 posted — posted creates a real negative StockAdjustment inside transaction.atomic + select_for_update)
- 6 notification rules per tenant (one per alert type: out_of_stock, low_stock, overstock, expired, po_approval_pending, shipment_delayed) with all tenant admins as recipients
- 6 sample alerts per tenant across all statuses (new / acknowledged / resolved) and all alert categories, wired to real products, warehouses, lots, POs, and shipments
- 21 report snapshots per tenant (one of each of the 21 report types in Module 18 — inventory valuation, aging, ABC, turnover, reservations, multi-location, PO summary, vendor performance, 3-way match variance, receiving/GRN, stock transfers, stocktake variance, quality control, scrap write-off, SO summary, fulfillment, shipment/carrier, returns/RMA, lot/expiry, forecast vs actual, alerts log)

---

## Application Modules

### Module 1: Multi-Tenant Administration (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Tenant Onboarding        | Automated provisioning of new tenant environments     |
| Subscription Management  | Pricing plans, billing cycles, feature access per tenant |
| Role-Based Access Control| Granular permission settings for users within each tenant |
| Theme & Customization    | White-labeling with custom branding, logo, and colors |

### Module 2: Product & Catalog Management (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| SKU Management           | Unique SKU identification, barcode, brand, manufacturer |
| Product Categorization   | Hierarchical 3-level grouping (Department > Category > Sub-category) |
| Product Attributes       | Custom EAV attributes (text, number, boolean, selection) per product |
| Pricing & Costing        | Purchase cost, wholesale price, retail price, markup percentage |
| Product Imagery          | Multiple image uploads per product with primary image support |
| Product Documents        | File attachments (manuals, safety sheets, datasheets, warranties) |

### Module 3: Vendor / Supplier Management (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Supplier Directory       | Vendor CRUD with type, status, payment terms, lead time |
| Performance Tracking     | Delivery, quality, compliance ratings with overall score |
| Contracts & Terms        | Contract management with documents, MOQ, payment terms |
| Communication Log        | Email, phone, meeting, and note tracking per vendor   |

### Module 4: Purchase Order Management (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| PO Creation & Drafting   | Manual PO creation with auto-generated PO numbers     |
| Line Item Management     | Dynamic line items with product, qty, price, tax, discount |
| Approval Workflows       | Multi-tier approval routing based on configurable PO value thresholds |
| PO Dispatch              | Send POs to vendors via Email, EDI, or Manual delivery with dispatch history tracking |
| PO Status Tracking       | Visual status timeline (Draft > Approved > Sent > Received > Closed) with real-time progress |
| Approval Rules           | Configurable rules with min/max amounts and required approval counts |
| Pending Approvals        | Dedicated view for approvers to review and act on POs |

### Module 5: Receiving & Putaway (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Goods Receipt Notes      | GRN creation linked to POs with line item receiving   |
| Vendor Invoices          | Invoice recording and management per vendor           |
| Three-Way Matching       | PO vs GRN vs Invoice matching with variance detection |
| Quality Inspections      | Inspection checklists with pass/fail/conditional results |
| Warehouse Locations      | Location management for putaway destinations          |
| Putaway Tasks            | Task assignment for moving received goods to locations |

### Module 6: Warehousing & Bin Management (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Warehouse Management     | Full CRUD for warehouses with type, contact, location |
| Zone Management          | Zones within warehouses (receiving, storage, shipping) |
| Aisle & Rack Management  | Aisle and rack hierarchy within zones                 |
| Bin Management           | Bins with capacity tracking (weight, volume, quantity) |
| Cross-Docking            | Cross-dock orders with status workflow and item tracking |
| Warehouse Map            | Visual map view of warehouse structure                |

### Module 7: Inventory Tracking & Control (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Real-Time Stock Levels   | On-Hand, Allocated, Available, On-Order per product per warehouse |
| Stock Adjustments        | Manual stock corrections with type, reason, and audit trail |
| Stock Status Management  | Categorize stock as Active, Damaged, Expired, or On-Hold |
| Status Transitions       | Move quantities between statuses with transition logging |
| Inventory Valuation      | Calculate total value using FIFO, LIFO, or Weighted Average |
| Cost Layers              | Track individual cost entries for accurate valuation  |
| Valuation Configuration  | Tenant-level setting for valuation method             |
| Inventory Reservations   | Lock stock for sales orders or jobs with status workflow (Pending > Confirmed > Released) |

### Module 8: Stock Movement & Transfers (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Inter-Warehouse Transfers| Move stock between different physical warehouses      |
| Intra-Warehouse Transfers| Move stock between bins/zones within the same warehouse |
| Transfer Approval Workflow| Configurable rules with approve/reject decisions     |
| Transfer Routing         | Predefined routes with transit method, duration, distance |
| Transfer Receiving       | Receive items with partial quantity support            |
| Status Workflow          | Draft → Pending Approval → Approved → In Transit → Completed |

### Module 9: Lot & Serial Number Tracking (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Lot/Batch Generation     | Auto-generated LOT numbers with GRN traceability      |
| Serial Number Tracking   | 1-to-1 item tracking with warranty and status workflow |
| Shelf-Life & Expiry      | Expiry dashboard, approaching/expired alerts, FEFO support |
| Traceability & Genealogy | Full forward/backward trace logs for lots and serials |
| Expiry Alerts            | Configurable alerts with acknowledge workflow         |

### Module 10: Order Management & Fulfillment (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Sales Order Processing   | Manual order entry with auto-generated SO numbers, customer info, line items with pricing/tax/discount |
| Order Status Workflow    | Draft → Confirmed → In Fulfillment → Picked → Packed → Shipped → Delivered → Closed (+ Cancelled, On Hold) |
| Pick List Management     | Generate pick lists from orders, assign pickers, track picked quantities per bin location |
| Packing Verification     | Create packing lists from completed picks, record dimensions, weight, packaging type |
| Shipment Dispatch        | Create shipments with carrier, tracking number, shipping cost, dispatch and delivery tracking |
| Shipment Tracking        | Manual tracking event entry with status, location, and timestamp timeline |
| Wave Planning            | Group multiple orders into waves for efficient warehouse picking, generate consolidated pick lists |
| Carrier Management       | Carrier directory with contact info and API endpoint placeholders for future integration |
| Shipping Rates           | Rate configuration per carrier/service level with base cost, per-kg cost, and transit days |
| Inventory Integration    | Auto-reserve stock on order confirmation, release on cancellation, decrement on delivery |

### Module 11: Returns Management (RMA) (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Return Merchandise Authorization | Create and track RMAs linked to sales orders with reason, customer details, requested/expected dates, status workflow (Draft → Pending → Approved → Received → Closed) |
| Return Inspection        | Inspection tickets per RMA with inspector assignment, per-item condition (Good/Minor/Major Damage/Missing Parts/Defective), qty passed/failed, restockable flag, overall result |
| Disposition Routing      | Decide per-return disposition (Restock, Repair, Liquidate, Scrap, Return to Vendor) with warehouse and destination bin; processing auto-creates inventory adjustments |
| Credit/Refund Processing | Refunds and credit notes with type (Refund/Credit Note/Store Credit/Exchange), method, amount, reference number, status workflow |
| Inventory Integration    | Restock disposition increases stock-on-hand and creates StockAdjustment; scrap disposition decreases stock with damage reason |

### Module 12: Stocktaking & Cycle Counting (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Full Physical Inventory  | Warehouse freeze tickets to block movements during a complete count; tied to full-type stock counts |
| Cycle Count Scheduling   | Configurable recurring schedules (daily/weekly/monthly/quarterly) with ABC-class targeting and zone filters; "Run Now" generates a count document and is idempotent per schedule/day |
| Stock Count Sheets       | Count document auto-populated from StockLevel snapshot; per-item counted qty entry, with variance and reason code per line; server-side `MinValueValidator(0)` rejects negatives; sheet becomes read-only after submission |
| Blind Counts             | Per-count flag that hides expected system quantities from counters to prevent bias |
| Variance Analysis        | Aggregated variance qty and value per count with reason-code classification |
| Adjustment Workflow      | Pending → Approved → Posted with POST-only `@require_POST` transitions; posting is wrapped in `transaction.atomic()` + `select_for_update()` on `StockLevel`; uses `StockAdjustment.apply_adjustment()` with `adjustment_type='correction'` as the single canonical write path, so ledger `quantity` equals resulting `on_hand` by definition; double-post prevented by count-status guard; every state change emits `core.AuditLog` |
| Status Workflow          | Counts: Draft → In Progress → Counted → Reviewed → Adjusted (adjusted counts cannot be deleted); freezes: Active → Released |
| Race-safe Numbering      | `FRZ-`, `CNT-`, `VADJ-` numbers generated via `_save_with_number_retry()` — retries on `IntegrityError` so TOCTOU races surface as retries, not 500s |
| Zone/Warehouse Validation | Form-layer `clean()` on freeze, schedule, and count forms rejects zones that belong to a different warehouse than the selected one |
| RBAC                     | `@tenant_admin_required` on all 16 destructive/state-change views (create/edit/delete + release/run/start/review/cancel/approve/reject/post); non-admin tenant users retain list + detail reads and count-sheet access |

### Module 13: Multi-Location Management (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Location Hierarchy Setup | Self-referential `Location` tree modelling Parent Company → Regional DC → Distribution Center → Retail Store, with optional link to a physical `warehousing.Warehouse` for stock roll-up |
| Global Stock Visibility  | Aggregated view over `inventory.StockLevel` joined through linked warehouses, filterable by location sub-tree, product search, and low-stock toggle, with total on-hand / available / value / low-stock stat cards |
| Location Pricing Rules   | Per-location pricing overrides (markup %, markdown %, fixed adjustment, price override) scoped to a specific product, category, or all products, with priority ordering and effective date range |
| Location Transfer Rules  | Source→destination transfer policy per location pair (allowed/blocked, max qty, lead time, approval requirement, priority) with `unique_together` guarantee on `(source, destination)` |
| Location Safety Stock Rules | Per-location × product safety-stock / reorder-point / max-stock overrides, uniquely scoped per location-product pair, with current stock-level comparison on the detail page |

### Module 14: Inventory Forecasting & Planning (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Demand Forecasting       | Auto-generate demand forecasts (moving average, exponential smoothing, linear regression, seasonal) from historical sales-order data, with configurable history/projection horizons and period types (weekly/monthly/quarterly) |
| Reorder Point (ROP) Calculation | Per product×warehouse ROP rules with formula ROP = (Avg Daily Usage × Lead Time Days) + Safety Stock; auto-recalculated on save |
| Reorder Alerts           | On-demand scan of active ROPs vs current `StockLevel` available qty; auto-creates alerts with status workflow New → Acknowledged → Ordered → Closed |
| Safety Stock Calculation | Fixed / Statistical (Z × √((LT × σ_d²) + (μ_d² × σ_LT²))) / Percentage methods; service level → Z-score lookup (0.90→1.28, 0.95→1.645, 0.99→2.33) |
| Seasonality Planning     | Monthly or quarterly demand multipliers per profile; applied to forecast lines to produce seasonality-adjusted quantities |
| Profile Targeting        | Seasonality profiles can be scoped to a category, a product, or used globally |

### Module 15: Barcode & RFID Integration (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Label Generation         | Design barcode / QR / mixed label templates (CODE128, CODE39, EAN-13, EAN-8, UPC-A, QR, Data Matrix, PDF417) with configurable paper size, content fields, and copies-per-label. Print jobs auto-number (`LPJ-NNNNN`) and follow a `draft → queued → printing → printed` state machine (with `failed` and `cancelled` branches). Live PDF rendering via reportlab + python-barcode + qrcode; downloadable inline from the job detail page. |
| Mobile/Handheld Scanner Integration | Register scan devices (handheld, fixed, mobile phone, tablet, wearable) with auto-generated per-device API tokens, battery-level tracking, user/warehouse assignment, and last-seen-at heartbeat. `ScanEvent` ledger captures every scan with barcode value + symbology + resolved object type (product / lot / serial / bin / RFID / unmatched). |
| RFID Tag Management      | Passive / active / semi-active tag registration with EPC code, frequency band (LF / HF / UHF / Microwave), linked-object routing (product / lot / serial / bin / pallet), and state machine (`unassigned → active → inactive / lost / damaged / retired`). RFID readers (fixed gate, handheld, integrated, vehicle-mount) register per warehouse + zone with antenna count and status. Read events accumulate read counts and first-/last-seen timestamps on the tag. |
| Batch Scanning           | Session-based multi-item capture (`BSS-NNNNN`) grouped by purpose (receiving, counting, picking, putaway, transfer, audit) with an inline item formset. Sessions follow `active → completed / cancelled`; on complete, the total-items counter snapshots child rows atomically. |
| Device Scan API          | Token-authenticated JSON endpoints — `POST /api/barcode-rfid/{scan,batch-scan,rfid-read,heartbeat}/` — for real-time device input. Auth via `Authorization: Device <token>` header; tenant context always derived from the matched device, never trusted from payload. Auto-resolves barcodes against serial → lot → RFID → product.sku → product.barcode → bin.code. |
| RBAC + Audit             | Every create / edit / delete / state-change view carries the `@tenant_admin_required` + `@require_POST` + `emit_audit` triad; reads stay open to all tenant users. `TenantScopedAdmin` scopes admin visibility per tenant. |

### Module 16: Quality Control & Inspection (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| QC Checklists            | Define mandatory / optional quality checks (`QCC-NNNNN`) scoped globally, per-product, per-vendor, or per-category. Each checklist contains an ordered list of items with check type (visual / measurement / boolean / text / photo), expected value, and `is_critical` flag. A failing critical item is the policy trigger for auto-quarantining the received quantity. |
| Inspection Routing       | Define inspection routes (`IR-NNNNN`) that send received items to a QC zone before they reach main putaway. Each route has a source warehouse, QC zone, optional default putaway zone, and a priority. Inline `InspectionRouteRule` rows match inbound items by `all` / `product` / `vendor` / `category` and auto-attach the appropriate `QCChecklist` when a rule fires. Priority ordering lets express routes bypass slower checks for trusted vendors. |
| Quarantine Management    | Hold defective / suspicious items in a restricted zone (`QR-NNNNN`) with full state machine (`active → under_review → released / scrapped`). Release requires a `disposition` (return_to_stock / rework / scrap / return_to_vendor). Scrapping auto-creates a pending `ScrapWriteOff`. Soft-delete (`deleted_at`) preserves the hold history; delete only allowed while `active`. |
| Defect Reporting         | Log defects (`DEF-NNNNN`) with product, lot, serial, quantity, defect type (visual / functional / packaging / labeling / expiry / contamination / other), severity (minor / major / critical), source (receiving / stocktaking / customer_return / production), and a free-text description. Inline photo uploads (`quality_control/defect_photos/`) with captions. Optional link to a `QuarantineRecord` for traceability. State machine: `open → investigating → resolved / scrapped`; soft-delete while open. |
| Scrap Write-Offs         | Write-off defective / quarantined stock (`SCR-NNNNN`) with quantity × unit cost → computed total value. Approval workflow (`pending → approved → posted`, with `rejected` branch). Posting is wrapped in `transaction.atomic()` + `select_for_update()` on the `StockLevel` row and creates a canonical negative `inventory.StockAdjustment` (type=`decrease`, reason=`damage`), so the ledger stays consistent with `on_hand`. Segregation-of-duties: the requester cannot self-approve. |
| Stock integration        | Quarantine is a logical hold (no physical stock move); scrap posting is the *only* path that decrements `StockLevel.on_hand`. Every mutation re-uses `StockAdjustment.apply_adjustment()` — the single canonical write path already exercised by `stocktaking` and `returns`. |
| RBAC + Audit             | Every create / edit / delete / state-change view carries the `@tenant_admin_required` + `@require_POST` + `emit_audit` triad; reads stay open to all tenant users. `TenantScopedAdmin` scopes admin visibility per tenant. |

### Module 17: Alerts & Notifications (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Low Stock & Out-of-Stock Alerts | `generate_stock_alerts` scanner reads `inventory.StockLevel`: `available <= 0` emits a `critical out_of_stock` alert, `needs_reorder` emits a `warning low_stock` alert. Every alert stores threshold + current value and links to the stock_level row for one-click navigation. |
| Overstock Alerts         | `generate_overstock_alerts` scanner reads `multi_location.LocationSafetyStockRule.max_stock_qty` (> 0) and flags any `StockLevel.on_hand > max_stock_qty` at a warehouse that maps to a location with a rule. No schema change to `inventory.StockLevel` — thresholds come from the existing location-rule table. |
| Expiry Alerts            | `alerts_scan_expiry` scanner reads `LotBatch.expiry_date` (active lots only): `expiry_date < today` → `critical expired`; within `--days-ahead N` (default 30) → `warning expiry_approaching`. Named `alerts_scan_expiry` to avoid colliding with the pre-existing `lot_tracking.generate_expiry_alerts` (which still populates `lot_tracking.ExpiryAlert`; the two systems now coexist, with `alerts_notifications.Alert` as the canonical inbox going forward). |
| Workflow Triggers        | `generate_workflow_alerts` scanner covers two sources: (a) `PurchaseOrder.status='pending_approval'` AND `updated_at` older than `--po-stale-hours` (default 48) → `po_approval_pending`; (b) `Shipment.estimated_delivery_date + --grace-days < today` with status in pending/dispatched/in_transit → `shipment_delayed`. An `import_failed` enum value is reserved for a future sprint when a central import-log model lands. |
| Alert State Machine      | Every `Alert` carries `StateMachineMixin` with `VALID_TRANSITIONS = {new: [acknowledged, dismissed], acknowledged: [resolved, dismissed], resolved: [], dismissed: []}`. Views enforce transitions server-side (`can_transition_to` + `@require_POST` + `emit_audit`), preventing drive-by status edits via GET. |
| Dedup by Day             | Every scanner computes `dedup_key = "{alert_type}:{source_kind}:{source_pk}:{YYYY-MM-DD}"` and skips creation if the tenant already has that key. Safe to run every scanner multiple times per day — no duplicate alerts. |
| Notification Rules       | Tenant admins configure `NotificationRule` rows (`NR-NNNNN`) that bind an `alert_type` + `min_severity` threshold to a `recipient_users` M2M + email/in-app channel flags. Rules can be toggled active/inactive without deletion. |
| Email Dispatch + Audit   | `dispatch_notifications` command iterates all open alerts without a matching delivery, resolves matching active rules, expands recipients, calls `django.core.mail.send_mail()` for email channels, and writes a `NotificationDelivery` row per (alert, recipient, channel). Delivery failures (e.g. missing email) are logged with error_message for visibility; idempotent via `unique_together(alert, recipient, channel)`. |
| Topbar Bell Integration  | The existing topbar bell dropdown now hydrates from `alert_inbox_json` on every page load, showing the current tenant's top-5 unread alerts with severity-coded icons, each deep-linking to the alert detail. |
| RBAC + Audit             | Every create/edit/delete/state-change view carries the `@tenant_admin_required` + `@require_POST` + `emit_audit` triad; reads stay open to all tenant users. `TenantScopedAdmin` scopes admin visibility per tenant. |

### Module 18: Reporting & Analytics (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| 21 analytics reports, 5 sections | One Django app (`reporting/`) delivers every report as a saveable, exportable `ReportSnapshot` snapshot. Reports are grouped into **Inventory & Stock** (Inventory Valuation, Aging Analysis, ABC Analysis, Stock Turnover, Reservations, Multi-Location Stock Roll-up), **Procurement** (PO Summary, Vendor Performance, 3-Way Match Variance, Receiving/GRN), **Warehouse Ops** (Stock Transfers, Stocktake Variance, Quality Control, Scrap Write-Off), **Sales & Fulfillment** (SO Summary, Fulfillment pick/pack/ship throughput, Shipment/Carrier, Returns/RMA), and **Tracking & Ops** (Lot/Serial/Expiry, Forecast vs Actual, Alerts & Notifications Log). |
| Single `ReportSnapshot` model | Table-per-report was unjustifiable at 21 reports (21 migrations × 21 admin pages × 21 seeds). Chosen design: one model with a `report_type` discriminator + `parameters`/`summary`/`data` JSONFields; each generation persists `RPT-NNNNN` auto-numbered via `_save_with_number_retry` with `unique_together(tenant, report_number)`. Adding a new report type requires zero migrations. |
| Registry-driven dispatch | `reporting/registry.py` maps 21 slugs → `{title, section, service_fn, form_class, chart_type, csv_columns, icon}`. The 7 generic views (index / list / generate / detail / delete / export-CSV / export-PDF) resolve the right compute service and form via the registry — adding a 22nd report is one registry entry + one compute function + one form subclass. |
| Pure compute services    | `reporting/services.py` has 21 `compute_<slug>(tenant, **params) → {summary, data, chart}` functions — unit-testable without HTTP and reused by the `seed_reporting` command + CSV/PDF exporters + views. JSON-serializable primitives throughout (Decimal→str, date→ISO). |
| Save snapshots, not compute-on-render | Each generation freezes the computed data at that point in time — so historical reports stay answerable even after inventory/orders change. Views orchestrate `form → service → save snapshot → redirect to detail`. |
| Chart.js visualizations  | Every report carries a `chart` payload (bar / pie / doughnut / line) in `snapshot.data.chart`. The detail template loads Chart.js 4.4.1 from CDN and renders the config client-side with a fixed 10-colour palette. |
| CSV + PDF exports        | CSV streamed via `csv.writer` + attachment Content-Disposition. PDF rendered via reportlab (landscape A4) with summary KPI table + data table (truncated to 200 rows) + metadata header; returned inline for in-browser viewing. |
| Tenant-scoped forms      | `BaseReportForm` + `AsOfDateMixin` / `PeriodMixin`; every subclass's `warehouse` / `category` / `vendor` / `carrier` queryset is filtered to the current tenant at form `__init__`, closing formset-FK IDOR. ABC enforces `a_threshold + b_threshold < 100`; Turnover / PO / SO / others enforce `period_end ≥ period_start`. |
| RBAC + audit + POST-only | `generate` and `delete` carry the `@login_required + @tenant_admin_required + @require_POST + emit_audit` triad; reads (`list`, `detail`, `CSV`, `PDF`) are open to all authenticated tenant users. Cross-tenant access on any endpoint returns 404. |
| Idempotent seed          | `seed_reporting` generates one snapshot per report type per tenant (21 × 5 tenants = 105 snapshots) by running each compute service against existing seeded data. Safe to run multiple times; `--flush` clears first. |
| 5-section sidebar        | `templates/partials/sidebar.html` gains an IMS 18 block with a top-level "Reporting & Analytics" entry that expands into 5 sub-sections (Inventory & Stock, Procurement, Warehouse Ops, Sales & Fulfillment, Tracking & Ops) plus an Overview link — each sub-section lists its reports as leaf items. |

### Planned Modules (see IMS.md)

| #  | Module                          | Description                                    |
|----|---------------------------------|------------------------------------------------|
| 19 | Accounting & Financial Integration| AP/AR sync, journal entries, tax management  |
| 20 | Third-Party Integrations & API  | E-commerce, ERP, accounting software sync      |
| 21 | System Administration & Security| RBAC, audit trail, UOM, data import/export     |

---

## Dashboard Features

### Layout Options

| Option            | Values                                      |
|-------------------|---------------------------------------------|
| Layout            | Vertical, Horizontal, Detached              |
| Theme             | Light, Dark                                 |
| Topbar Color      | Light, Dark                                 |
| Sidebar Color     | Light, Dark, Colored (gradient)             |
| Sidebar Size      | Default (250px), Compact (180px), Small Icon (70px), Icon Hover |
| Layout Width      | Fluid, Boxed                                |
| Layout Position   | Fixed, Scrollable                           |
| Direction         | LTR, RTL                                    |

All settings are persisted in `localStorage` and apply instantly without page reload.

### Theme Customization
Click the gear icon in the top-right corner to open the Theme Settings panel. All changes are applied live and saved to the browser's local storage.

---

## Multi-Tenancy Architecture

NavIMS uses a **shared database, shared schema** multi-tenancy approach:

- Each `Tenant` represents an isolated organization
- All data models include a `tenant` foreign key for data isolation
- `TenantMiddleware` automatically sets `request.tenant` from the authenticated user
- All views filter queries by `request.tenant` to enforce data boundaries
- The super admin (`tenant=None`) can access cross-tenant administration
- New tenants are automatically provisioned during registration

### Data Flow
```
User Registration
  └── Creates Tenant (with auto-generated slug)
       └── Creates User (is_tenant_admin=True)
            └── Creates Subscription (default plan)
                 └── Redirects to Dashboard
```

---

## Browser Compatibility

| Browser           | Platform              | Status     |
|-------------------|-----------------------|------------|
| Google Chrome     | Windows, Mac, Linux   | Supported  |
| Mozilla Firefox   | Windows, Mac, Linux   | Supported  |
| Safari            | Mac                   | Supported  |
| Microsoft Edge    | Windows               | Supported  |
| Other WebKit      | Various               | Supported  |

---

## License

This project is licensed under the terms included in the [LICENSE](LICENSE) file.
