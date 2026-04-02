import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Tenant,
    User,
    Role,
    Permission,
    RolePermission,
    UserRole,
    UserInvite,
    Subscription,
)
from administration.models import PricingPlan, TenantCustomization


class Command(BaseCommand):
    help = "Seed the database with demo data for NavIMS. Idempotent by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Clear existing seed data before re-seeding (preserves superuser).",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        self._create_superuser()
        plans = self._create_pricing_plans()
        tenants = self._create_tenants()
        tenant_admins = self._create_tenant_admins(tenants)
        regular_users = self._create_regular_users(tenants)
        roles = self._create_roles(tenants)
        permissions = self._create_permissions()
        self._create_role_permissions(roles, permissions)
        self._create_subscriptions(tenants, plans)
        self._assign_user_roles(tenant_admins, regular_users, roles)
        self._create_tenant_customizations(tenants)
        self._create_user_invites(tenants, tenant_admins, roles)

        self._print_credentials()

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def _flush(self):
        self.stdout.write(self.style.WARNING("Flushing existing seed data..."))
        UserInvite.objects.all().delete()
        UserRole.objects.all().delete()
        RolePermission.objects.all().delete()
        TenantCustomization.objects.all().delete()
        Subscription.objects.all().delete()
        Permission.objects.all().delete()
        Role.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Tenant.objects.all().delete()
        PricingPlan.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Flush complete."))

    # ------------------------------------------------------------------
    # 1. Superuser
    # ------------------------------------------------------------------

    def _create_superuser(self):
        user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@navims.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password("admin123")
            user.save()
            self.stdout.write(self.style.SUCCESS("Created superuser: admin"))
        else:
            self.stdout.write("Superuser 'admin' already exists — skipped.")

    # ------------------------------------------------------------------
    # 2. Pricing Plans
    # ------------------------------------------------------------------

    def _create_pricing_plans(self):
        plan_data = [
            {
                "name": "Free",
                "slug": "free",
                "price": Decimal("0.00"),
                "max_users": 2,
                "max_warehouses": 1,
                "max_products": 100,
                "description": "Get started with basic inventory management.",
            },
            {
                "name": "Starter",
                "slug": "starter",
                "price": Decimal("29.00"),
                "max_users": 5,
                "max_warehouses": 2,
                "max_products": 500,
                "description": "For small teams managing multiple locations.",
            },
            {
                "name": "Professional",
                "slug": "professional",
                "price": Decimal("79.00"),
                "max_users": 20,
                "max_warehouses": 5,
                "max_products": 5000,
                "description": "Advanced features for growing businesses.",
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "price": Decimal("199.00"),
                "max_users": 999,
                "max_warehouses": 50,
                "max_products": 999999,
                "description": "Unlimited power for large organisations.",
            },
        ]

        plans = {}
        for data in plan_data:
            slug = data.pop("slug")
            plan, created = PricingPlan.objects.get_or_create(
                slug=slug, defaults=data
            )
            plans[slug] = plan
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created plan: {plan.name}"))
            else:
                self.stdout.write(f"Plan '{plan.name}' already exists — skipped.")

        return plans

    # ------------------------------------------------------------------
    # 3. Tenants
    # ------------------------------------------------------------------

    def _create_tenants(self):
        tenant_data = [
            {
                "name": "Acme Industries",
                "slug": "acme-industries",
                "plan": "professional",
                "primary_color": "#3b82f6",
            },
            {
                "name": "Global Supplies Co",
                "slug": "global-supplies",
                "plan": "starter",
                "primary_color": "#10b981",
            },
            {
                "name": "TechWare Solutions",
                "slug": "techware-solutions",
                "plan": "enterprise",
                "primary_color": "#8b5cf6",
            },
        ]

        tenants = {}
        for data in tenant_data:
            slug = data["slug"]
            tenant, created = Tenant.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": data["name"],
                    "plan": data["plan"],
                    "primary_color": data["primary_color"],
                    "is_active": True,
                },
            )
            tenants[slug] = tenant
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created tenant: {tenant.name}"))
            else:
                self.stdout.write(f"Tenant '{tenant.name}' already exists — skipped.")

        return tenants

    # ------------------------------------------------------------------
    # 4. Tenant Admin Users
    # ------------------------------------------------------------------

    def _create_tenant_admins(self, tenants):
        admin_data = [
            {
                "username": "admin_acme",
                "first_name": "Alice",
                "last_name": "Morgan",
                "email": "alice@acme-industries.com",
                "job_title": "Operations Director",
                "tenant_slug": "acme-industries",
            },
            {
                "username": "admin_global",
                "first_name": "Bob",
                "last_name": "Chen",
                "email": "bob@globalsupplies.com",
                "job_title": "Supply Chain Manager",
                "tenant_slug": "global-supplies",
            },
            {
                "username": "admin_techware",
                "first_name": "Carol",
                "last_name": "Davis",
                "email": "carol@techware.com",
                "job_title": "CTO",
                "tenant_slug": "techware-solutions",
            },
        ]

        admins = {}
        for data in admin_data:
            tenant = tenants[data.pop("tenant_slug")]
            username = data["username"]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    **{k: v for k, v in data.items() if k != "username"},
                    "tenant": tenant,
                    "is_tenant_admin": True,
                },
            )
            if created:
                user.set_password("demo123")
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Created tenant admin: {username}")
                )
            else:
                self.stdout.write(
                    f"Tenant admin '{username}' already exists — skipped."
                )
            admins[tenant.slug] = user

        return admins

    # ------------------------------------------------------------------
    # 5. Regular Users
    # ------------------------------------------------------------------

    def _create_regular_users(self, tenants):
        user_data = [
            # Acme Industries — 3 users
            {
                "username": "john_acme",
                "first_name": "John",
                "last_name": "Smith",
                "email": "john@acme-industries.com",
                "job_title": "Warehouse Manager",
                "tenant_slug": "acme-industries",
            },
            {
                "username": "maria_acme",
                "first_name": "Maria",
                "last_name": "Garcia",
                "email": "maria@acme-industries.com",
                "job_title": "Inventory Clerk",
                "tenant_slug": "acme-industries",
            },
            {
                "username": "james_acme",
                "first_name": "James",
                "last_name": "Wilson",
                "email": "james@acme-industries.com",
                "job_title": "Purchasing Agent",
                "tenant_slug": "acme-industries",
            },
            # Global Supplies Co — 2 users
            {
                "username": "sarah_global",
                "first_name": "Sarah",
                "last_name": "Lee",
                "email": "sarah@globalsupplies.com",
                "job_title": "Warehouse Manager",
                "tenant_slug": "global-supplies",
            },
            {
                "username": "david_global",
                "first_name": "David",
                "last_name": "Patel",
                "email": "david@globalsupplies.com",
                "job_title": "Inventory Clerk",
                "tenant_slug": "global-supplies",
            },
            # TechWare Solutions — 3 users
            {
                "username": "emma_techware",
                "first_name": "Emma",
                "last_name": "Brown",
                "email": "emma@techware.com",
                "job_title": "Warehouse Manager",
                "tenant_slug": "techware-solutions",
            },
            {
                "username": "liam_techware",
                "first_name": "Liam",
                "last_name": "Nguyen",
                "email": "liam@techware.com",
                "job_title": "Inventory Clerk",
                "tenant_slug": "techware-solutions",
            },
            {
                "username": "olivia_techware",
                "first_name": "Olivia",
                "last_name": "Martinez",
                "email": "olivia@techware.com",
                "job_title": "Purchasing Agent",
                "tenant_slug": "techware-solutions",
            },
        ]

        users = {}
        for data in user_data:
            tenant = tenants[data.pop("tenant_slug")]
            username = data["username"]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    **{k: v for k, v in data.items() if k != "username"},
                    "tenant": tenant,
                },
            )
            if created:
                user.set_password("demo123")
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created user: {username}"))
            else:
                self.stdout.write(f"User '{username}' already exists — skipped.")
            users.setdefault(tenant.slug, []).append(user)

        return users

    # ------------------------------------------------------------------
    # 6. Roles (per tenant)
    # ------------------------------------------------------------------

    def _create_roles(self, tenants):
        role_definitions = [
            {
                "name": "Admin",
                "slug": "admin",
                "description": "Full access to all tenant features.",
                "is_system_role": True,
            },
            {
                "name": "Manager",
                "slug": "manager",
                "description": "Can manage inventory, orders, and view reports.",
                "is_system_role": False,
            },
            {
                "name": "Warehouse Staff",
                "slug": "warehouse-staff",
                "description": "Can manage warehouse operations and inventory.",
                "is_system_role": False,
            },
            {
                "name": "Viewer",
                "slug": "viewer",
                "description": "Read-only access to dashboards and reports.",
                "is_system_role": False,
            },
        ]

        roles = {}  # { tenant_slug: { role_slug: Role } }
        for tenant in tenants.values():
            roles[tenant.slug] = {}
            for rd in role_definitions:
                role, created = Role.objects.get_or_create(
                    tenant=tenant,
                    slug=rd["slug"],
                    defaults={
                        "name": rd["name"],
                        "description": rd["description"],
                        "is_system_role": rd["is_system_role"],
                    },
                )
                roles[tenant.slug][rd["slug"]] = role
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created role: {role.name} ({tenant.name})"
                        )
                    )

        return roles

    # ------------------------------------------------------------------
    # 7. Permissions (global)
    # ------------------------------------------------------------------

    def _create_permissions(self):
        permission_data = [
            ("view_products", "View Products", "inventory"),
            ("add_products", "Add Products", "inventory"),
            ("edit_products", "Edit Products", "inventory"),
            ("delete_products", "Delete Products", "inventory"),
            ("view_orders", "View Orders", "purchasing"),
            ("manage_orders", "Manage Orders", "purchasing"),
            ("view_warehouses", "View Warehouses", "warehousing"),
            ("manage_warehouses", "Manage Warehouses", "warehousing"),
            ("view_reports", "View Reports", "reporting"),
            ("manage_users", "Manage Users", "users"),
            ("manage_settings", "Manage Settings", "settings"),
        ]

        permissions = {}
        for codename, name, module in permission_data:
            perm, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={"name": name, "module": module},
            )
            permissions[codename] = perm
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created permission: {codename}")
                )

        return permissions

    # ------------------------------------------------------------------
    # Role-Permission mapping
    # ------------------------------------------------------------------

    def _create_role_permissions(self, roles, permissions):
        all_perms = list(permissions.keys())

        mapping = {
            "admin": all_perms,
            "manager": [
                "view_products",
                "add_products",
                "edit_products",
                "view_orders",
                "manage_orders",
                "view_warehouses",
                "view_reports",
                "manage_users",
            ],
            "warehouse-staff": [
                "view_products",
                "add_products",
                "edit_products",
                "view_warehouses",
                "manage_warehouses",
            ],
            "viewer": [
                "view_products",
                "view_orders",
                "view_warehouses",
                "view_reports",
            ],
        }

        count = 0
        for tenant_slug, tenant_roles in roles.items():
            for role_slug, role in tenant_roles.items():
                for codename in mapping.get(role_slug, []):
                    _, created = RolePermission.objects.get_or_create(
                        role=role, permission=permissions[codename]
                    )
                    if created:
                        count += 1

        if count:
            self.stdout.write(
                self.style.SUCCESS(f"Created {count} role-permission assignments.")
            )

    # ------------------------------------------------------------------
    # 8. Subscriptions
    # ------------------------------------------------------------------

    def _create_subscriptions(self, tenants, plans):
        now = timezone.now()
        tenant_plan_map = {
            "acme-industries": "professional",
            "global-supplies": "starter",
            "techware-solutions": "enterprise",
        }

        plan_user_limits = {
            "free": 2,
            "starter": 5,
            "professional": 20,
            "enterprise": 999,
        }
        plan_wh_limits = {
            "free": 1,
            "starter": 2,
            "professional": 5,
            "enterprise": 50,
        }

        for slug, plan_slug in tenant_plan_map.items():
            tenant = tenants[slug]
            sub, created = Subscription.objects.get_or_create(
                tenant=tenant,
                defaults={
                    "plan": plan_slug,
                    "status": "active",
                    "max_users": plan_user_limits[plan_slug],
                    "max_warehouses": plan_wh_limits[plan_slug],
                    "current_period_start": now,
                    "current_period_end": now + timedelta(days=30),
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created subscription: {tenant.name} ({plan_slug})"
                    )
                )

    # ------------------------------------------------------------------
    # 9. UserRole assignments
    # ------------------------------------------------------------------

    def _assign_user_roles(self, tenant_admins, regular_users, roles):
        count = 0

        # Tenant admins get the Admin role
        for tenant_slug, admin_user in tenant_admins.items():
            admin_role = roles[tenant_slug]["admin"]
            _, created = UserRole.objects.get_or_create(
                user=admin_user, role=admin_role
            )
            if created:
                count += 1

        # Regular users get roles based on job title
        job_role_map = {
            "Warehouse Manager": "manager",
            "Inventory Clerk": "warehouse-staff",
            "Purchasing Agent": "viewer",
        }

        for tenant_slug, users in regular_users.items():
            for user in users:
                role_slug = job_role_map.get(user.job_title, "viewer")
                role = roles[tenant_slug][role_slug]
                _, created = UserRole.objects.get_or_create(
                    user=user, role=role
                )
                if created:
                    count += 1

        if count:
            self.stdout.write(
                self.style.SUCCESS(f"Created {count} user-role assignments.")
            )

    # ------------------------------------------------------------------
    # 10. TenantCustomization
    # ------------------------------------------------------------------

    def _create_tenant_customizations(self, tenants):
        customization_data = {
            "acme-industries": {
                "primary_color": "#3b82f6",
                "secondary_color": "#1e40af",
                "company_address": "123 Industrial Blvd, Chicago, IL 60601",
                "company_phone": "+1-312-555-0100",
                "company_email": "info@acme-industries.com",
            },
            "global-supplies": {
                "primary_color": "#10b981",
                "secondary_color": "#047857",
                "company_address": "456 Commerce St, Austin, TX 73301",
                "company_phone": "+1-512-555-0200",
                "company_email": "hello@globalsupplies.com",
            },
            "techware-solutions": {
                "primary_color": "#8b5cf6",
                "secondary_color": "#6d28d9",
                "company_address": "789 Tech Park Dr, San Jose, CA 95101",
                "company_phone": "+1-408-555-0300",
                "company_email": "support@techware.com",
            },
        }

        for slug, data in customization_data.items():
            tenant = tenants[slug]
            cust, created = TenantCustomization.objects.get_or_create(
                tenant=tenant, defaults=data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created customization for: {tenant.name}"
                    )
                )

    # ------------------------------------------------------------------
    # 11. UserInvites
    # ------------------------------------------------------------------

    def _create_user_invites(self, tenants, tenant_admins, roles):
        now = timezone.now()
        invite_data = [
            {
                "tenant_slug": "acme-industries",
                "email": "newbie@acme-industries.com",
                "role_slug": "warehouse-staff",
            },
            {
                "tenant_slug": "acme-industries",
                "email": "intern@acme-industries.com",
                "role_slug": "viewer",
            },
            {
                "tenant_slug": "global-supplies",
                "email": "recruit@globalsupplies.com",
                "role_slug": "manager",
            },
        ]

        count = 0
        for data in invite_data:
            tenant = tenants[data["tenant_slug"]]
            admin_user = tenant_admins[data["tenant_slug"]]
            role = roles[data["tenant_slug"]][data["role_slug"]]

            invite, created = UserInvite.objects.get_or_create(
                tenant=tenant,
                email=data["email"],
                defaults={
                    "role": role,
                    "invited_by": admin_user,
                    "status": "pending",
                    "expires_at": now + timedelta(days=7),
                },
            )
            if created:
                count += 1

        if count:
            self.stdout.write(
                self.style.SUCCESS(f"Created {count} pending user invites.")
            )

    # ------------------------------------------------------------------
    # Print credentials
    # ------------------------------------------------------------------

    def _print_credentials(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seeding complete!"))
        self.stdout.write("")
        self.stdout.write("Login Credentials:")
        self.stdout.write("------------------------------------")
        self.stdout.write("Super Admin:    admin / admin123")
        self.stdout.write("Acme Admin:     admin_acme / demo123")
        self.stdout.write("Global Admin:   admin_global / demo123")
        self.stdout.write("TechWare Admin: admin_techware / demo123")
        self.stdout.write("------------------------------------")
        self.stdout.write(
            self.style.NOTICE("NOTE: Login as a tenant admin to see module data.")
        )
