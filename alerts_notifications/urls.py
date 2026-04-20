from django.urls import path

from . import views

app_name = 'alerts_notifications'

urlpatterns = [
    # Dashboard
    path('', views.alert_dashboard_view, name='dashboard'),

    # Alert inbox
    path('alerts/', views.alert_list_view, name='alert_list'),
    path('alerts/create/', views.alert_create_view, name='alert_create'),
    path('alerts/<int:pk>/', views.alert_detail_view, name='alert_detail'),
    path('alerts/<int:pk>/acknowledge/', views.alert_acknowledge_view, name='alert_acknowledge'),
    path('alerts/<int:pk>/resolve/', views.alert_resolve_view, name='alert_resolve'),
    path('alerts/<int:pk>/dismiss/', views.alert_dismiss_view, name='alert_dismiss'),
    path('alerts/<int:pk>/delete/', views.alert_delete_view, name='alert_delete'),
    path('alerts/inbox.json', views.alert_inbox_json_view, name='alert_inbox_json'),

    # Notification rules
    path('rules/', views.rule_list_view, name='rule_list'),
    path('rules/create/', views.rule_create_view, name='rule_create'),
    path('rules/<int:pk>/', views.rule_detail_view, name='rule_detail'),
    path('rules/<int:pk>/edit/', views.rule_edit_view, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete_view, name='rule_delete'),
    path('rules/<int:pk>/toggle-active/', views.rule_toggle_active_view, name='rule_toggle_active'),

    # Delivery audit log
    path('deliveries/', views.delivery_list_view, name='delivery_list'),
    path('deliveries/<int:pk>/', views.delivery_detail_view, name='delivery_detail'),
]
