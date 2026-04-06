from django.urls import path
from . import views

app_name = 'warehousing'

urlpatterns = [
    # Warehouses
    path('', views.warehouse_list_view, name='warehouse_list'),
    path('create/', views.warehouse_create_view, name='warehouse_create'),
    path('<int:pk>/', views.warehouse_detail_view, name='warehouse_detail'),
    path('<int:pk>/edit/', views.warehouse_edit_view, name='warehouse_edit'),
    path('<int:pk>/delete/', views.warehouse_delete_view, name='warehouse_delete'),
    path('<int:pk>/map/', views.warehouse_map_view, name='warehouse_map'),

    # Zones
    path('zones/', views.zone_list_view, name='zone_list'),
    path('zones/create/', views.zone_create_view, name='zone_create'),
    path('zones/<int:pk>/', views.zone_detail_view, name='zone_detail'),
    path('zones/<int:pk>/edit/', views.zone_edit_view, name='zone_edit'),
    path('zones/<int:pk>/delete/', views.zone_delete_view, name='zone_delete'),

    # Aisles
    path('aisles/', views.aisle_list_view, name='aisle_list'),
    path('aisles/create/', views.aisle_create_view, name='aisle_create'),
    path('aisles/<int:pk>/', views.aisle_detail_view, name='aisle_detail'),
    path('aisles/<int:pk>/edit/', views.aisle_edit_view, name='aisle_edit'),
    path('aisles/<int:pk>/delete/', views.aisle_delete_view, name='aisle_delete'),

    # Racks
    path('racks/', views.rack_list_view, name='rack_list'),
    path('racks/create/', views.rack_create_view, name='rack_create'),
    path('racks/<int:pk>/', views.rack_detail_view, name='rack_detail'),
    path('racks/<int:pk>/edit/', views.rack_edit_view, name='rack_edit'),
    path('racks/<int:pk>/delete/', views.rack_delete_view, name='rack_delete'),

    # Bins
    path('bins/', views.bin_list_view, name='bin_list'),
    path('bins/create/', views.bin_create_view, name='bin_create'),
    path('bins/<int:pk>/', views.bin_detail_view, name='bin_detail'),
    path('bins/<int:pk>/edit/', views.bin_edit_view, name='bin_edit'),
    path('bins/<int:pk>/delete/', views.bin_delete_view, name='bin_delete'),

    # Cross-Docking
    path('cross-docking/', views.crossdock_list_view, name='crossdock_list'),
    path('cross-docking/create/', views.crossdock_create_view, name='crossdock_create'),
    path('cross-docking/<int:pk>/', views.crossdock_detail_view, name='crossdock_detail'),
    path('cross-docking/<int:pk>/edit/', views.crossdock_edit_view, name='crossdock_edit'),
    path('cross-docking/<int:pk>/delete/', views.crossdock_delete_view, name='crossdock_delete'),
    path('cross-docking/<int:pk>/status/', views.crossdock_status_view, name='crossdock_status'),
    path('cross-docking/<int:pk>/reopen/', views.crossdock_reopen_view, name='crossdock_reopen'),
]
