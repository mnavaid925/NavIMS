from django.urls import path
from . import views

app_name = 'lot_tracking'

urlpatterns = [
    # Lot / Batch
    path('lots/', views.lot_list_view, name='lot_list'),
    path('lots/create/', views.lot_create_view, name='lot_create'),
    path('lots/<int:pk>/', views.lot_detail_view, name='lot_detail'),
    path('lots/<int:pk>/edit/', views.lot_edit_view, name='lot_edit'),
    path('lots/<int:pk>/delete/', views.lot_delete_view, name='lot_delete'),
    path('lots/<int:pk>/transition/<str:new_status>/', views.lot_transition_view, name='lot_transition'),
    path('lots/<int:pk>/trace/', views.lot_trace_view, name='lot_trace'),

    # Serial Numbers
    path('serials/', views.serial_list_view, name='serial_list'),
    path('serials/create/', views.serial_create_view, name='serial_create'),
    path('serials/<int:pk>/', views.serial_detail_view, name='serial_detail'),
    path('serials/<int:pk>/edit/', views.serial_edit_view, name='serial_edit'),
    path('serials/<int:pk>/delete/', views.serial_delete_view, name='serial_delete'),
    path('serials/<int:pk>/transition/<str:new_status>/', views.serial_transition_view, name='serial_transition'),
    path('serials/<int:pk>/trace/', views.serial_trace_view, name='serial_trace'),

    # Expiry Management
    path('expiry/', views.expiry_dashboard_view, name='expiry_dashboard'),
    path('expiry/alerts/', views.expiry_alert_list_view, name='expiry_alert_list'),
    path('expiry/alerts/<int:pk>/acknowledge/', views.expiry_acknowledge_view, name='expiry_acknowledge'),

    # Traceability
    path('traceability/', views.traceability_list_view, name='traceability_list'),
    path('traceability/create/', views.traceability_create_view, name='traceability_create'),
    path('traceability/<int:pk>/', views.traceability_detail_view, name='traceability_detail'),
]
