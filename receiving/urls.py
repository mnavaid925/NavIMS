from django.urls import path
from . import views

app_name = 'receiving'

urlpatterns = [
    # GRN CRUD
    path('grns/', views.grn_list_view, name='grn_list'),
    path('grns/create/', views.grn_create_view, name='grn_create'),
    path('grns/<int:pk>/', views.grn_detail_view, name='grn_detail'),
    path('grns/<int:pk>/edit/', views.grn_edit_view, name='grn_edit'),
    path('grns/<int:pk>/delete/', views.grn_delete_view, name='grn_delete'),
    path('grns/<int:pk>/transition/<str:new_status>/', views.grn_transition_view, name='grn_transition'),

    # Vendor Invoice CRUD
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/create/', views.invoice_create_view, name='invoice_create'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.invoice_edit_view, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.invoice_delete_view, name='invoice_delete'),
    path('invoices/<int:pk>/transition/<str:new_status>/', views.invoice_transition_view, name='invoice_transition'),

    # Three-Way Match
    path('matches/', views.match_list_view, name='match_list'),
    path('matches/create/', views.match_create_view, name='match_create'),
    path('matches/<int:pk>/', views.match_detail_view, name='match_detail'),
    path('matches/<int:pk>/resolve/', views.match_resolve_view, name='match_resolve'),
    path('matches/<int:pk>/delete/', views.match_delete_view, name='match_delete'),

    # Quality Inspection
    path('inspections/', views.inspection_list_view, name='inspection_list'),
    path('inspections/create/', views.inspection_create_view, name='inspection_create'),
    path('inspections/<int:pk>/', views.inspection_detail_view, name='inspection_detail'),
    path('inspections/<int:pk>/edit/', views.inspection_edit_view, name='inspection_edit'),
    path('inspections/<int:pk>/delete/', views.inspection_delete_view, name='inspection_delete'),
    path('inspections/<int:pk>/complete/', views.inspection_complete_view, name='inspection_complete'),

    # Warehouse Locations
    path('locations/', views.location_list_view, name='location_list'),
    path('locations/create/', views.location_create_view, name='location_create'),
    path('locations/<int:pk>/', views.location_detail_view, name='location_detail'),
    path('locations/<int:pk>/edit/', views.location_edit_view, name='location_edit'),
    path('locations/<int:pk>/delete/', views.location_delete_view, name='location_delete'),

    # Putaway Tasks
    path('putaway/', views.putaway_list_view, name='putaway_list'),
    path('putaway/create/', views.putaway_create_view, name='putaway_create'),
    path('putaway/<int:pk>/', views.putaway_detail_view, name='putaway_detail'),
    path('putaway/<int:pk>/edit/', views.putaway_edit_view, name='putaway_edit'),
    path('putaway/<int:pk>/delete/', views.putaway_delete_view, name='putaway_delete'),
    path('putaway/<int:pk>/transition/<str:new_status>/', views.putaway_transition_view, name='putaway_transition'),
    path('putaway/generate/<int:grn_pk>/', views.putaway_generate_view, name='putaway_generate'),
]
