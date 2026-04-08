# NavIMS - Inventory Management System

A comprehensive, multi-tenant Inventory Management System built with Django 4.2 and Bootstrap 5. NavIMS provides a clean, intuitive, and fully responsive dashboard with blue and white theme, supporting multiple layout modes, dark/light themes, and extensive customization options.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running the Application](#running-the-application)
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
│   └── inventory/
│       ├── stock_level_list.html       # Stock levels with warehouse & low-stock filters
│       ├── stock_level_detail.html     # Stock level details with quantity breakdown
│       ├── stock_adjust_form.html      # Stock adjustment form
│       ├── stock_adjustment_list.html  # Adjustment history with type & reason filters
│       ├── stock_adjustment_detail.html# Adjustment details
│       ├── stock_status_list.html      # Stock status with status & warehouse filters
│       ├── stock_status_detail.html    # Status details with transition history
│       ├── stock_status_transition_form.html  # Status transition form
│       ├── stock_status_transition_list.html  # Transition history list
│       ├── valuation_dashboard.html    # Valuation dashboard with summary cards
│       ├── valuation_detail.html       # Product valuation with cost layers
│       ├── valuation_config_form.html  # Valuation method configuration
│       ├── reservation_list.html       # Reservations with status & warehouse filters
│       ├── reservation_form.html       # Reservation create/edit
│       └── reservation_detail.html     # Reservation details with status timeline
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
   ```

---

## Running the Application

```bash
python manage.py runserver
```

Open your browser and navigate to: **http://127.0.0.1:8000**

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

### Planned Modules (see IMS.md)

| #  | Module                          | Description                                    |
|----|---------------------------------|------------------------------------------------|
| 8  | Stock Movement & Transfers      | Inter/intra-warehouse transfers                |
| 9  | Lot & Serial Number Tracking    | Batch/serial tracking, expiry management       |
| 10 | Order Management & Fulfillment  | Sales orders, pick-pack-ship, wave planning    |
| 11 | Returns Management (RMA)        | Return authorization, inspection, disposition  |
| 12 | Stocktaking & Cycle Counting    | Physical inventory, cycle counts, variance     |
| 13 | Multi-Location Management       | Location hierarchy, global stock visibility    |
| 14 | Inventory Forecasting & Planning| Demand forecasting, reorder points, safety stock|
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
