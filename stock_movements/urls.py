from django.urls import path
from . import views

app_name = 'stock_movements'

urlpatterns = [
    # Stock Transfers
    path('transfers/', views.transfer_list_view, name='transfer_list'),
    path('transfers/create/', views.transfer_create_view, name='transfer_create'),
    path('transfers/<int:pk>/', views.transfer_detail_view, name='transfer_detail'),
    path('transfers/<int:pk>/edit/', views.transfer_edit_view, name='transfer_edit'),
    path('transfers/<int:pk>/delete/', views.transfer_delete_view, name='transfer_delete'),
    path('transfers/<int:pk>/transition/<str:new_status>/', views.transfer_transition_view, name='transfer_transition'),
    path('transfers/<int:pk>/receive/', views.transfer_receive_view, name='transfer_receive'),

    # Transfer Approval Workflow
    path('approval-rules/', views.approval_rule_list_view, name='approval_rule_list'),
    path('approval-rules/create/', views.approval_rule_create_view, name='approval_rule_create'),
    path('approval-rules/<int:pk>/edit/', views.approval_rule_edit_view, name='approval_rule_edit'),
    path('approval-rules/<int:pk>/delete/', views.approval_rule_delete_view, name='approval_rule_delete'),
    path('pending-approvals/', views.pending_approval_list_view, name='pending_approval_list'),
    path('transfers/<int:pk>/approve/', views.transfer_approve_view, name='transfer_approve'),

    # Transfer Routes
    path('routes/', views.route_list_view, name='route_list'),
    path('routes/create/', views.route_create_view, name='route_create'),
    path('routes/<int:pk>/', views.route_detail_view, name='route_detail'),
    path('routes/<int:pk>/edit/', views.route_edit_view, name='route_edit'),
    path('routes/<int:pk>/delete/', views.route_delete_view, name='route_delete'),
]
