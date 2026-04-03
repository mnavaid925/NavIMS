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
