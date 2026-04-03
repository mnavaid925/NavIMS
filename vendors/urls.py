from django.urls import path
from . import views

app_name = 'vendors'

urlpatterns = [
    # Vendors CRUD
    path('', views.vendor_list_view, name='vendor_list'),
    path('create/', views.vendor_create_view, name='vendor_create'),
    path('<int:pk>/', views.vendor_detail_view, name='vendor_detail'),
    path('<int:pk>/edit/', views.vendor_edit_view, name='vendor_edit'),
    path('<int:pk>/delete/', views.vendor_delete_view, name='vendor_delete'),

    # Performance Tracking CRUD
    path('performance/', views.performance_list_view, name='performance_list'),
    path('performance/create/', views.performance_create_view, name='performance_create'),
    path('performance/<int:pk>/edit/', views.performance_edit_view, name='performance_edit'),
    path('performance/<int:pk>/delete/', views.performance_delete_view, name='performance_delete'),

    # Contracts & Terms CRUD
    path('contracts/', views.contract_list_view, name='contract_list'),
    path('contracts/create/', views.contract_create_view, name='contract_create'),
    path('contracts/<int:pk>/edit/', views.contract_edit_view, name='contract_edit'),
    path('contracts/<int:pk>/delete/', views.contract_delete_view, name='contract_delete'),

    # Communication Log CRUD
    path('communications/', views.communication_list_view, name='communication_list'),
    path('communications/create/', views.communication_create_view, name='communication_create'),
    path('communications/<int:pk>/edit/', views.communication_edit_view, name='communication_edit'),
    path('communications/<int:pk>/delete/', views.communication_delete_view, name='communication_delete'),

    # Performance Reviews (inline from detail page)
    path('<int:pk>/performance/add/', views.vendor_performance_add_view, name='vendor_performance_add'),
    path('<int:pk>/performance/<int:performance_pk>/delete/', views.vendor_performance_delete_view, name='vendor_performance_delete'),

    # Contracts (inline from detail page)
    path('<int:pk>/contracts/add/', views.vendor_contract_add_view, name='vendor_contract_add'),
    path('<int:pk>/contracts/<int:contract_pk>/delete/', views.vendor_contract_delete_view, name='vendor_contract_delete'),

    # Communications (inline from detail page)
    path('<int:pk>/communications/add/', views.vendor_communication_add_view, name='vendor_communication_add'),
    path('<int:pk>/communications/<int:comm_pk>/delete/', views.vendor_communication_delete_view, name='vendor_communication_delete'),
]
