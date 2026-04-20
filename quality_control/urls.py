from django.urls import path
from . import views

app_name = 'quality_control'

urlpatterns = [
    # ── Submodule 1: QC Checklists ──
    path('', views.checklist_list_view, name='checklist_list'),
    path('checklists/', views.checklist_list_view, name='checklist_list_alt'),
    path('checklists/create/', views.checklist_create_view, name='checklist_create'),
    path('checklists/<int:pk>/', views.checklist_detail_view, name='checklist_detail'),
    path('checklists/<int:pk>/edit/', views.checklist_edit_view, name='checklist_edit'),
    path('checklists/<int:pk>/delete/', views.checklist_delete_view, name='checklist_delete'),
    path('checklists/<int:pk>/toggle-active/', views.checklist_toggle_active_view, name='checklist_toggle_active'),

    # ── Submodule 2: Inspection Routing ──
    path('routes/', views.route_list_view, name='route_list'),
    path('routes/create/', views.route_create_view, name='route_create'),
    path('routes/<int:pk>/', views.route_detail_view, name='route_detail'),
    path('routes/<int:pk>/edit/', views.route_edit_view, name='route_edit'),
    path('routes/<int:pk>/delete/', views.route_delete_view, name='route_delete'),

    # ── Submodule 3: Quarantine Management ──
    path('quarantine/', views.quarantine_list_view, name='quarantine_list'),
    path('quarantine/create/', views.quarantine_create_view, name='quarantine_create'),
    path('quarantine/<int:pk>/', views.quarantine_detail_view, name='quarantine_detail'),
    path('quarantine/<int:pk>/edit/', views.quarantine_edit_view, name='quarantine_edit'),
    path('quarantine/<int:pk>/delete/', views.quarantine_delete_view, name='quarantine_delete'),
    path('quarantine/<int:pk>/review/', views.quarantine_review_view, name='quarantine_review'),
    path('quarantine/<int:pk>/release/', views.quarantine_release_view, name='quarantine_release'),

    # ── Submodule 4: Defect Reports ──
    path('defects/', views.defect_list_view, name='defect_list'),
    path('defects/create/', views.defect_create_view, name='defect_create'),
    path('defects/<int:pk>/', views.defect_detail_view, name='defect_detail'),
    path('defects/<int:pk>/edit/', views.defect_edit_view, name='defect_edit'),
    path('defects/<int:pk>/delete/', views.defect_delete_view, name='defect_delete'),
    path('defects/<int:pk>/investigate/', views.defect_investigate_view, name='defect_investigate'),
    path('defects/<int:pk>/resolve/', views.defect_resolve_view, name='defect_resolve'),
    path('defects/<int:pk>/scrap/', views.defect_scrap_view, name='defect_scrap'),
    path('defects/<int:pk>/photos/<int:photo_pk>/delete/', views.defect_photo_delete_view, name='defect_photo_delete'),

    # ── Submodule 4: Scrap Write-Offs ──
    path('scrap/', views.scrap_list_view, name='scrap_list'),
    path('scrap/create/', views.scrap_create_view, name='scrap_create'),
    path('scrap/<int:pk>/', views.scrap_detail_view, name='scrap_detail'),
    path('scrap/<int:pk>/edit/', views.scrap_edit_view, name='scrap_edit'),
    path('scrap/<int:pk>/delete/', views.scrap_delete_view, name='scrap_delete'),
    path('scrap/<int:pk>/approve/', views.scrap_approve_view, name='scrap_approve'),
    path('scrap/<int:pk>/reject/', views.scrap_reject_view, name='scrap_reject'),
    path('scrap/<int:pk>/post/', views.scrap_post_view, name='scrap_post'),
]
