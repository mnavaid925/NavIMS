from django.urls import path
from . import views

app_name = 'forecasting'

urlpatterns = [
    # ── Demand Forecasts ──
    path('', views.forecast_list_view, name='forecast_list'),
    path('forecasts/create/', views.forecast_create_view, name='forecast_create'),
    path('forecasts/<int:pk>/', views.forecast_detail_view, name='forecast_detail'),
    path('forecasts/<int:pk>/edit/', views.forecast_edit_view, name='forecast_edit'),
    path('forecasts/<int:pk>/delete/', views.forecast_delete_view, name='forecast_delete'),
    path('forecasts/<int:pk>/generate/', views.forecast_generate_view, name='forecast_generate'),

    # ── Reorder Points ──
    path('reorder-points/', views.rop_list_view, name='rop_list'),
    path('reorder-points/create/', views.rop_create_view, name='rop_create'),
    path('reorder-points/<int:pk>/', views.rop_detail_view, name='rop_detail'),
    path('reorder-points/<int:pk>/edit/', views.rop_edit_view, name='rop_edit'),
    path('reorder-points/<int:pk>/delete/', views.rop_delete_view, name='rop_delete'),
    path('reorder-points/check-alerts/', views.rop_check_alerts_view, name='rop_check_alerts'),

    # ── Reorder Alerts ──
    path('alerts/', views.alert_list_view, name='alert_list'),
    path('alerts/<int:pk>/', views.alert_detail_view, name='alert_detail'),
    path('alerts/<int:pk>/acknowledge/', views.alert_acknowledge_view, name='alert_acknowledge'),
    path('alerts/<int:pk>/ordered/', views.alert_mark_ordered_view, name='alert_mark_ordered'),
    path('alerts/<int:pk>/close/', views.alert_close_view, name='alert_close'),
    path('alerts/<int:pk>/delete/', views.alert_delete_view, name='alert_delete'),

    # ── Safety Stock ──
    path('safety-stock/', views.safety_stock_list_view, name='safety_stock_list'),
    path('safety-stock/create/', views.safety_stock_create_view, name='safety_stock_create'),
    path('safety-stock/<int:pk>/', views.safety_stock_detail_view, name='safety_stock_detail'),
    path('safety-stock/<int:pk>/edit/', views.safety_stock_edit_view, name='safety_stock_edit'),
    path('safety-stock/<int:pk>/delete/', views.safety_stock_delete_view, name='safety_stock_delete'),
    path('safety-stock/<int:pk>/recalc/', views.safety_stock_recalc_view, name='safety_stock_recalc'),

    # ── Seasonality Profiles ──
    path('seasonality/', views.profile_list_view, name='profile_list'),
    path('seasonality/create/', views.profile_create_view, name='profile_create'),
    path('seasonality/<int:pk>/', views.profile_detail_view, name='profile_detail'),
    path('seasonality/<int:pk>/edit/', views.profile_edit_view, name='profile_edit'),
    path('seasonality/<int:pk>/delete/', views.profile_delete_view, name='profile_delete'),
]
