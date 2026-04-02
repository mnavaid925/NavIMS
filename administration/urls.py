from django.urls import path
from . import views

app_name = 'administration'

urlpatterns = [
    path('tenants/', views.tenant_list_view, name='tenant_list'),
    path('tenants/create/', views.tenant_create_view, name='tenant_create'),
    path('tenants/<int:pk>/', views.tenant_detail_view, name='tenant_detail'),
    path('tenants/<int:pk>/edit/', views.tenant_edit_view, name='tenant_edit'),
    path('tenants/<int:pk>/delete/', views.tenant_delete_view, name='tenant_delete'),
    path('subscriptions/', views.subscription_list_view, name='subscription_list'),
    path('subscriptions/<int:pk>/edit/', views.subscription_edit_view, name='subscription_edit'),
    path('roles/', views.role_list_view, name='role_list'),
    path('roles/create/', views.role_create_view, name='role_create'),
    path('roles/<int:pk>/edit/', views.role_edit_view, name='role_edit'),
    path('roles/<int:pk>/delete/', views.role_delete_view, name='role_delete'),
    path('settings/', views.settings_view, name='settings'),
]
