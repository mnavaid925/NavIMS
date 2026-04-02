from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    Tenant,
    User,
    Role,
    Permission,
    RolePermission,
    UserRole,
    UserInvite,
    Subscription,
    AuditLog,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'plan', 'is_active', 'created_at')
    list_filter = ('plan', 'is_active')
    search_fields = ('name', 'slug', 'domain')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'tenant', 'is_tenant_admin', 'is_staff')
    list_filter = ('is_tenant_admin', 'is_staff', 'is_superuser', 'tenant')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Tenant Info', {'fields': ('tenant', 'phone', 'avatar', 'job_title', 'is_tenant_admin')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Tenant Info', {'fields': ('tenant', 'phone', 'job_title', 'is_tenant_admin')}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'is_system_role', 'created_at')
    list_filter = ('is_system_role', 'tenant')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename', 'module')
    list_filter = ('module',)
    search_fields = ('name', 'codename')


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission')
    list_filter = ('role',)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_at')
    list_filter = ('role',)


@admin.register(UserInvite)
class UserInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'tenant', 'status', 'invited_by', 'created_at', 'expires_at')
    list_filter = ('status', 'tenant')
    search_fields = ('email',)
    readonly_fields = ('token',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'plan', 'status', 'max_users', 'max_warehouses', 'current_period_end')
    list_filter = ('plan', 'status')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'user', 'tenant', 'created_at')
    list_filter = ('action', 'model_name', 'tenant')
    search_fields = ('action', 'model_name', 'object_id')
    readonly_fields = ('tenant', 'user', 'action', 'model_name', 'object_id', 'changes', 'ip_address', 'created_at')
