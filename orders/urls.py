from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # ── Sales Orders ──
    path('', views.so_list_view, name='so_list'),
    path('create/', views.so_create_view, name='so_create'),
    path('<int:pk>/', views.so_detail_view, name='so_detail'),
    path('<int:pk>/edit/', views.so_edit_view, name='so_edit'),
    path('<int:pk>/delete/', views.so_delete_view, name='so_delete'),
    path('<int:pk>/confirm/', views.so_confirm_view, name='so_confirm'),
    path('<int:pk>/cancel/', views.so_cancel_view, name='so_cancel'),
    path('<int:pk>/hold/', views.so_hold_view, name='so_hold'),
    path('<int:pk>/resume/', views.so_resume_view, name='so_resume'),
    path('<int:pk>/close/', views.so_close_view, name='so_close'),
    path('<int:pk>/reopen/', views.so_reopen_view, name='so_reopen'),
    path('<int:pk>/generate-picklist/', views.so_generate_picklist_view, name='so_generate_picklist'),

    # ── Pick Lists ──
    path('pick-lists/', views.picklist_list_view, name='picklist_list'),
    path('pick-lists/create/', views.picklist_create_view, name='picklist_create'),
    path('pick-lists/<int:pk>/', views.picklist_detail_view, name='picklist_detail'),
    path('pick-lists/<int:pk>/edit/', views.picklist_edit_view, name='picklist_edit'),
    path('pick-lists/<int:pk>/delete/', views.picklist_delete_view, name='picklist_delete'),
    path('pick-lists/<int:pk>/assign/', views.picklist_assign_view, name='picklist_assign'),
    path('pick-lists/<int:pk>/start/', views.picklist_start_view, name='picklist_start'),
    path('pick-lists/<int:pk>/complete/', views.picklist_complete_view, name='picklist_complete'),
    path('pick-lists/<int:pk>/cancel/', views.picklist_cancel_view, name='picklist_cancel'),

    # ── Packing Lists ──
    path('packing-lists/', views.packinglist_list_view, name='packinglist_list'),
    path('packing-lists/create/', views.packinglist_create_view, name='packinglist_create'),
    path('packing-lists/<int:pk>/', views.packinglist_detail_view, name='packinglist_detail'),
    path('packing-lists/<int:pk>/edit/', views.packinglist_edit_view, name='packinglist_edit'),
    path('packing-lists/<int:pk>/delete/', views.packinglist_delete_view, name='packinglist_delete'),
    path('packing-lists/<int:pk>/start/', views.packinglist_start_view, name='packinglist_start'),
    path('packing-lists/<int:pk>/complete/', views.packinglist_complete_view, name='packinglist_complete'),
    path('packing-lists/<int:pk>/cancel/', views.packinglist_cancel_view, name='packinglist_cancel'),

    # ── Shipments ──
    path('shipments/', views.shipment_list_view, name='shipment_list'),
    path('shipments/create/', views.shipment_create_view, name='shipment_create'),
    path('shipments/<int:pk>/', views.shipment_detail_view, name='shipment_detail'),
    path('shipments/<int:pk>/edit/', views.shipment_edit_view, name='shipment_edit'),
    path('shipments/<int:pk>/delete/', views.shipment_delete_view, name='shipment_delete'),
    path('shipments/<int:pk>/dispatch/', views.shipment_dispatch_view, name='shipment_dispatch'),
    path('shipments/<int:pk>/in-transit/', views.shipment_in_transit_view, name='shipment_in_transit'),
    path('shipments/<int:pk>/delivered/', views.shipment_delivered_view, name='shipment_delivered'),
    path('shipments/<int:pk>/cancel/', views.shipment_cancel_view, name='shipment_cancel'),
    path('shipments/<int:pk>/add-tracking/', views.shipment_add_tracking_view, name='shipment_add_tracking'),

    # ── Wave Planning ──
    path('waves/', views.wave_list_view, name='wave_list'),
    path('waves/create/', views.wave_create_view, name='wave_create'),
    path('waves/<int:pk>/', views.wave_detail_view, name='wave_detail'),
    path('waves/<int:pk>/edit/', views.wave_edit_view, name='wave_edit'),
    path('waves/<int:pk>/delete/', views.wave_delete_view, name='wave_delete'),
    path('waves/<int:pk>/release/', views.wave_release_view, name='wave_release'),
    path('waves/<int:pk>/start/', views.wave_start_view, name='wave_start'),
    path('waves/<int:pk>/complete/', views.wave_complete_view, name='wave_complete'),
    path('waves/<int:pk>/cancel/', views.wave_cancel_view, name='wave_cancel'),
    path('waves/<int:pk>/generate-picklists/', views.wave_generate_picklists_view, name='wave_generate_picklists'),

    # ── Carriers ──
    path('carriers/', views.carrier_list_view, name='carrier_list'),
    path('carriers/create/', views.carrier_create_view, name='carrier_create'),
    path('carriers/<int:pk>/', views.carrier_detail_view, name='carrier_detail'),
    path('carriers/<int:pk>/edit/', views.carrier_edit_view, name='carrier_edit'),
    path('carriers/<int:pk>/delete/', views.carrier_delete_view, name='carrier_delete'),

    # ── Shipping Rates ──
    path('shipping-rates/', views.shippingrate_list_view, name='shippingrate_list'),
    path('shipping-rates/create/', views.shippingrate_create_view, name='shippingrate_create'),
    path('shipping-rates/<int:pk>/edit/', views.shippingrate_edit_view, name='shippingrate_edit'),
    path('shipping-rates/<int:pk>/delete/', views.shippingrate_delete_view, name='shippingrate_delete'),
]
