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
│   └── administration/
│       ├── tenant_list.html    # Tenant listing
│       ├── tenant_form.html    # Tenant create/edit
│       ├── tenant_detail.html  # Tenant details & subscription
│       ├── subscription_list.html
│       ├── subscription_form.html
│       ├── role_list.html      # Roles & permissions
│       ├── role_form.html      # Role create/edit
│       └── settings.html       # Tenant customization settings
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
   ```

   To reset and re-seed:
   ```bash
   python manage.py seed --flush
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

---

## Application Modules

### Module 1: Multi-Tenant Administration (Implemented)

| Feature                  | Description                                           |
|--------------------------|-------------------------------------------------------|
| Tenant Onboarding        | Automated provisioning of new tenant environments     |
| Subscription Management  | Pricing plans, billing cycles, feature access per tenant |
| Role-Based Access Control| Granular permission settings for users within each tenant |
| Theme & Customization    | White-labeling with custom branding, logo, and colors |

### Planned Modules (see IMS.md)

| #  | Module                          | Description                                    |
|----|---------------------------------|------------------------------------------------|
| 1  | Product & Catalog Management    | SKU, categories, attributes, pricing           |
| 2  | Vendor / Supplier Management    | Supplier directory, performance tracking       |
| 3  | Purchase Order Management       | PO creation, approval workflows, tracking      |
| 4  | Receiving & Putaway             | GRN, three-way matching, quality inspection    |
| 5  | Warehousing & Bin Management    | Warehouse structure, bin capacity, mapping      |
| 6  | Inventory Tracking & Control    | Real-time stock, valuation, reservations       |
| 7  | Stock Movement & Transfers      | Inter/intra-warehouse transfers                |
| 8  | Lot & Serial Number Tracking    | Batch/serial tracking, expiry management       |
| 9  | Order Management & Fulfillment  | Sales orders, pick-pack-ship, wave planning    |
| 10 | Returns Management (RMA)        | Return authorization, inspection, disposition  |
| 11 | Stocktaking & Cycle Counting    | Physical inventory, cycle counts, variance     |
| 12 | Multi-Location Management       | Location hierarchy, global stock visibility    |
| 13 | Inventory Forecasting & Planning| Demand forecasting, reorder points, safety stock|
| 14 | Barcode & RFID Integration      | Label generation, scanner integration          |
| 15 | Quality Control & Inspection    | QC checklists, quarantine, defect reporting    |
| 16 | Alerts & Notifications          | Low stock, overstock, expiry, workflow alerts  |
| 17 | Reporting & Analytics           | Valuation, turnover, aging, ABC analysis       |
| 18 | Accounting & Financial Integration| AP/AR sync, journal entries, tax management  |
| 19 | Third-Party Integrations & API  | E-commerce, ERP, accounting software sync      |
| 20 | System Administration & Security| RBAC, audit trail, UOM, data import/export     |

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
