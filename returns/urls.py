from django.urls import path
from . import views

app_name = 'returns'

urlpatterns = [
    # ── RMA (Return Authorization) ──
    path('', views.rma_list_view, name='rma_list'),
    path('create/', views.rma_create_view, name='rma_create'),
    path('<int:pk>/', views.rma_detail_view, name='rma_detail'),
    path('<int:pk>/edit/', views.rma_edit_view, name='rma_edit'),
    path('<int:pk>/delete/', views.rma_delete_view, name='rma_delete'),
    path('<int:pk>/submit/', views.rma_submit_view, name='rma_submit'),
    path('<int:pk>/approve/', views.rma_approve_view, name='rma_approve'),
    path('<int:pk>/reject/', views.rma_reject_view, name='rma_reject'),
    path('<int:pk>/receive/', views.rma_receive_view, name='rma_receive'),
    path('<int:pk>/close/', views.rma_close_view, name='rma_close'),
    path('<int:pk>/cancel/', views.rma_cancel_view, name='rma_cancel'),

    # ── Return Inspections ──
    path('inspections/', views.inspection_list_view, name='inspection_list'),
    path('inspections/create/', views.inspection_create_view, name='inspection_create'),
    path('inspections/<int:pk>/', views.inspection_detail_view, name='inspection_detail'),
    path('inspections/<int:pk>/edit/', views.inspection_edit_view, name='inspection_edit'),
    path('inspections/<int:pk>/delete/', views.inspection_delete_view, name='inspection_delete'),
    path('inspections/<int:pk>/start/', views.inspection_start_view, name='inspection_start'),
    path('inspections/<int:pk>/complete/', views.inspection_complete_view, name='inspection_complete'),

    # ── Dispositions ──
    path('dispositions/', views.disposition_list_view, name='disposition_list'),
    path('dispositions/create/', views.disposition_create_view, name='disposition_create'),
    path('dispositions/<int:pk>/', views.disposition_detail_view, name='disposition_detail'),
    path('dispositions/<int:pk>/edit/', views.disposition_edit_view, name='disposition_edit'),
    path('dispositions/<int:pk>/delete/', views.disposition_delete_view, name='disposition_delete'),
    path('dispositions/<int:pk>/process/', views.disposition_process_view, name='disposition_process'),
    path('dispositions/<int:pk>/cancel/', views.disposition_cancel_view, name='disposition_cancel'),

    # ── Refunds / Credits ──
    path('refunds/', views.refund_list_view, name='refund_list'),
    path('refunds/create/', views.refund_create_view, name='refund_create'),
    path('refunds/<int:pk>/', views.refund_detail_view, name='refund_detail'),
    path('refunds/<int:pk>/edit/', views.refund_edit_view, name='refund_edit'),
    path('refunds/<int:pk>/delete/', views.refund_delete_view, name='refund_delete'),
    path('refunds/<int:pk>/process/', views.refund_process_view, name='refund_process'),
    path('refunds/<int:pk>/fail/', views.refund_fail_view, name='refund_fail'),
    path('refunds/<int:pk>/cancel/', views.refund_cancel_view, name='refund_cancel'),
]
