from django.urls import path
from . import views

app_name = 'stocktaking'

urlpatterns = [
    # ── Stock Counts ──
    path('', views.count_list_view, name='count_list'),
    path('counts/create/', views.count_create_view, name='count_create'),
    path('counts/<int:pk>/', views.count_detail_view, name='count_detail'),
    path('counts/<int:pk>/edit/', views.count_edit_view, name='count_edit'),
    path('counts/<int:pk>/delete/', views.count_delete_view, name='count_delete'),
    path('counts/<int:pk>/sheet/', views.count_sheet_view, name='count_sheet'),
    path('counts/<int:pk>/start/', views.count_start_view, name='count_start'),
    path('counts/<int:pk>/review/', views.count_review_view, name='count_review'),
    path('counts/<int:pk>/cancel/', views.count_cancel_view, name='count_cancel'),

    # ── Cycle Count Schedules ──
    path('schedules/', views.schedule_list_view, name='schedule_list'),
    path('schedules/create/', views.schedule_create_view, name='schedule_create'),
    path('schedules/<int:pk>/', views.schedule_detail_view, name='schedule_detail'),
    path('schedules/<int:pk>/edit/', views.schedule_edit_view, name='schedule_edit'),
    path('schedules/<int:pk>/delete/', views.schedule_delete_view, name='schedule_delete'),
    path('schedules/<int:pk>/run/', views.schedule_run_view, name='schedule_run'),

    # ── Warehouse Freezes ──
    path('freezes/', views.freeze_list_view, name='freeze_list'),
    path('freezes/create/', views.freeze_create_view, name='freeze_create'),
    path('freezes/<int:pk>/edit/', views.freeze_edit_view, name='freeze_edit'),
    path('freezes/<int:pk>/release/', views.freeze_release_view, name='freeze_release'),
    path('freezes/<int:pk>/delete/', views.freeze_delete_view, name='freeze_delete'),

    # ── Variance Adjustments ──
    path('adjustments/', views.adjustment_list_view, name='adjustment_list'),
    path('adjustments/create/', views.adjustment_create_view, name='adjustment_create'),
    path('adjustments/<int:pk>/', views.adjustment_detail_view, name='adjustment_detail'),
    path('adjustments/<int:pk>/edit/', views.adjustment_edit_view, name='adjustment_edit'),
    path('adjustments/<int:pk>/delete/', views.adjustment_delete_view, name='adjustment_delete'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve_view, name='adjustment_approve'),
    path('adjustments/<int:pk>/reject/', views.adjustment_reject_view, name='adjustment_reject'),
    path('adjustments/<int:pk>/post/', views.adjustment_post_view, name='adjustment_post'),
]
