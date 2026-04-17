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
│           └── seed_lot_tracking.py  # Lot tracking seeder with demo data
│
├── stocktaking/                # Module 12: Stocktaking & Cycle Counting
│   ├── models.py               # StocktakeFreeze, CycleCountSchedule, StockCount, StockCountItem, StockVarianceAdjustment
│   ├── forms.py                # Freeze, Schedule, StockCount, StockCountItem, VarianceAdjustment forms
│   ├── views.py                # Full CRUD for counts, schedules, freezes, adjustments + count sheet + inventory posting
│   ├── urls.py                 # Stocktaking URL routes
│   ├── admin.py                # Admin registration with inlines
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
├── returns/                    # Module 11: Returns Management (RMA)
│   ├── models.py               # ReturnAuthorization, ReturnAuthorizationItem, ReturnInspection, ReturnInspectionItem, Disposition, DispositionItem, RefundCredit
│   ├── forms.py                # RMA, RMA item formset, Inspection, Inspection item formset, Disposition, Disposition item formset, RefundCredit forms
│   ├── views.py                # Full CRUD for RMA, Inspection, Disposition, Refund + status transitions + restock/scrap inventory integration
│   ├── urls.py                 # Returns URL routes
│   ├── admin.py                # Admin registration with inlines
│   └── management/
│       └── commands/
│           └── seed_returns.py # Returns seeder with demo data
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
   git clone <repository-url>
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
| lot_tracking      | 108   | Lot/batch, serials, expiry alerts, traceability |
| **Total**         | **641** | |

Run `pytest` at the project root to execute all modules in one pass (~25 s on a warm cache).

### What the suite guards against

Each module's `test_security.py` + `test_regression.py` files codify real defects that surfaced during SQA review. Notable categories:

- **Cross-tenant IDOR** — foreign-tenant FK injection via `request.POST` on every write path that accepts IDs (products, PO items, GRN items, transfer items).
- **`unique_together(tenant, X)` form-bypass** — duplicate detection at form layer, before the DB raises `IntegrityError`.
- **Status-machine transitions** — `can_transition_to` coverage, segregation-of-duties (requester cannot self-approve), terminal-state enforcement.
- **File upload hygiene** — extension whitelist, size caps, SVG/executable blocks on `VendorInvoice.document` and `VendorContract.document`.
- **Race conditions** — atomic auto-numbering with `IntegrityError` retry for `GRN-NNNNN`, `TRF-NNNNN`, `PO-NNNNN`, `LOT-NNNNN`, etc.
- **N+1 queries** — `django_assert_max_num_queries` budgets on every list view and multi-item detail view.
- **Financial reconciliation** — three-way match must compare all three totals (PO ↔ Invoice ↔ GRN).

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
| Cycle Count Scheduling   | Configurable recurring schedules (daily/weekly/monthly/quarterly) with ABC-class targeting and zone filters; "Run Now" generates a count document |
| Stock Count Sheets       | Count document auto-populated from StockLevel snapshot; per-item counted qty entry, with variance and reason code per line |
| Blind Counts             | Per-count flag that hides expected system quantities from counters to prevent bias |
| Variance Analysis        | Aggregated variance qty and value per count with reason-code classification |
| Adjustment Workflow      | Pending → Approved → Posted; posting creates `inventory.StockAdjustment` records and updates `StockLevel.on_hand` + `last_counted_at` |
| Status Workflow          | Counts: Draft → In Progress → Counted → Reviewed → Adjusted; freezes: Active → Released |

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

### Planned Modules (see IMS.md)

| #  | Module                          | Description                                    |
|----|---------------------------------|------------------------------------------------|
| 15 | Barcode & RFID Integration      | Label generation, scanner integration          |
| 16 | Quality Control & Inspection    | QC checklists, quarantine, defect reporting    |
| 17 | Alerts & Notifications          | Low stock, overstock, expiry, workflow alerts  |
| 18 | Reporting & Analytics           | Valuation, turnover, aging, ABC analysis       |
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
