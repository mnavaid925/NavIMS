from django.urls import path
from . import views

app_name = 'purchase_orders'

urlpatterns = [
    # PO CRUD
    path('', views.po_list_view, name='po_list'),
    path('create/', views.po_create_view, name='po_create'),
    path('<int:pk>/', views.po_detail_view, name='po_detail'),
    path('<int:pk>/edit/', views.po_edit_view, name='po_edit'),
    path('<int:pk>/delete/', views.po_delete_view, name='po_delete'),

    # Status transitions
    path('<int:pk>/submit/', views.po_submit_for_approval_view, name='po_submit'),
    path('<int:pk>/approve/', views.po_approve_view, name='po_approve'),
    path('<int:pk>/reject/', views.po_reject_view, name='po_reject'),
    path('<int:pk>/dispatch/', views.po_dispatch_view, name='po_dispatch'),
    path('<int:pk>/mark-received/', views.po_mark_received_view, name='po_mark_received'),
    path('<int:pk>/close/', views.po_close_view, name='po_close'),
    path('<int:pk>/cancel/', views.po_cancel_view, name='po_cancel'),
    path('<int:pk>/reopen/', views.po_reopen_view, name='po_reopen'),

    # Approval rules CRUD
    path('approval-rules/', views.approval_rule_list_view, name='approval_rule_list'),
    path('approval-rules/create/', views.approval_rule_create_view, name='approval_rule_create'),
    path('approval-rules/<int:pk>/edit/', views.approval_rule_edit_view, name='approval_rule_edit'),
    path('approval-rules/<int:pk>/delete/', views.approval_rule_delete_view, name='approval_rule_delete'),

    # Pending approvals
    path('approvals/', views.approval_list_view, name='approval_list'),
]
