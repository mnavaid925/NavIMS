from django.urls import path
from . import views

app_name = 'multi_location'

urlpatterns = [
    # ── Locations ──
    path('', views.location_list_view, name='location_list'),
    path('locations/create/', views.location_create_view, name='location_create'),
    path('locations/<int:pk>/', views.location_detail_view, name='location_detail'),
    path('locations/<int:pk>/edit/', views.location_edit_view, name='location_edit'),
    path('locations/<int:pk>/delete/', views.location_delete_view, name='location_delete'),

    # ── Global Stock Visibility ──
    path('stock-visibility/', views.stock_visibility_view, name='stock_visibility'),

    # ── Pricing Rules ──
    path('pricing-rules/', views.pricing_rule_list_view, name='pricing_rule_list'),
    path('pricing-rules/create/', views.pricing_rule_create_view, name='pricing_rule_create'),
    path('pricing-rules/<int:pk>/', views.pricing_rule_detail_view, name='pricing_rule_detail'),
    path('pricing-rules/<int:pk>/edit/', views.pricing_rule_edit_view, name='pricing_rule_edit'),
    path('pricing-rules/<int:pk>/delete/', views.pricing_rule_delete_view, name='pricing_rule_delete'),

    # ── Transfer Rules ──
    path('transfer-rules/', views.transfer_rule_list_view, name='transfer_rule_list'),
    path('transfer-rules/create/', views.transfer_rule_create_view, name='transfer_rule_create'),
    path('transfer-rules/<int:pk>/', views.transfer_rule_detail_view, name='transfer_rule_detail'),
    path('transfer-rules/<int:pk>/edit/', views.transfer_rule_edit_view, name='transfer_rule_edit'),
    path('transfer-rules/<int:pk>/delete/', views.transfer_rule_delete_view, name='transfer_rule_delete'),

    # ── Safety Stock Rules ──
    path('safety-stock-rules/', views.safety_stock_rule_list_view, name='safety_stock_rule_list'),
    path('safety-stock-rules/create/', views.safety_stock_rule_create_view, name='safety_stock_rule_create'),
    path('safety-stock-rules/<int:pk>/', views.safety_stock_rule_detail_view, name='safety_stock_rule_detail'),
    path('safety-stock-rules/<int:pk>/edit/', views.safety_stock_rule_edit_view, name='safety_stock_rule_edit'),
    path('safety-stock-rules/<int:pk>/delete/', views.safety_stock_rule_delete_view, name='safety_stock_rule_delete'),
]
