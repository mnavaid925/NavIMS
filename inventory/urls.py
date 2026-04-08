from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Stock Levels
    path('stock-levels/', views.stock_level_list_view, name='stock_level_list'),
    path('stock-levels/<int:pk>/', views.stock_level_detail_view, name='stock_level_detail'),
    path('stock-levels/<int:pk>/adjust/', views.stock_adjust_view, name='stock_adjust'),

    # Stock Adjustments
    path('adjustments/', views.stock_adjustment_list_view, name='stock_adjustment_list'),
    path('adjustments/<int:pk>/', views.stock_adjustment_detail_view, name='stock_adjustment_detail'),

    # Stock Status
    path('stock-status/', views.stock_status_list_view, name='stock_status_list'),
    path('stock-status/<int:pk>/', views.stock_status_detail_view, name='stock_status_detail'),
    path('stock-status/transition/', views.stock_status_transition_view, name='stock_status_transition'),
    path('stock-status/transitions/', views.stock_status_transition_list_view, name='stock_status_transition_list'),

    # Inventory Valuation
    path('valuation/', views.valuation_dashboard_view, name='valuation_dashboard'),
    path('valuation/<int:pk>/', views.valuation_detail_view, name='valuation_detail'),
    path('valuation/config/', views.valuation_config_view, name='valuation_config'),
    path('valuation/recalculate/', views.valuation_recalculate_view, name='valuation_recalculate'),

    # Reservations
    path('reservations/', views.reservation_list_view, name='reservation_list'),
    path('reservations/create/', views.reservation_create_view, name='reservation_create'),
    path('reservations/<int:pk>/', views.reservation_detail_view, name='reservation_detail'),
    path('reservations/<int:pk>/edit/', views.reservation_edit_view, name='reservation_edit'),
    path('reservations/<int:pk>/delete/', views.reservation_delete_view, name='reservation_delete'),
    path('reservations/<int:pk>/transition/<str:new_status>/', views.reservation_transition_view, name='reservation_transition'),
]
