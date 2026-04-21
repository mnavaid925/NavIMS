from django.urls import path

from . import views

app_name = 'accounting'

urlpatterns = [
    # Overview & landings
    path('', views.overview_view, name='overview'),
    path('ap/', views.ap_dashboard_view, name='ap_dashboard'),
    path('ar/', views.ar_dashboard_view, name='ar_dashboard'),
    path('journal/', views.journal_dashboard_view, name='journal_dashboard'),
    path('tax/', views.tax_dashboard_view, name='tax_dashboard'),
    path('trial-balance/', views.trial_balance_view, name='trial_balance'),
    path('tax-calculator/', views.tax_calculator_view, name='tax_calculator'),

    # Chart of Accounts
    path('coa/', views.coa_list_view, name='coa_list'),
    path('coa/create/', views.coa_create_view, name='coa_create'),
    path('coa/<int:pk>/', views.coa_detail_view, name='coa_detail'),
    path('coa/<int:pk>/edit/', views.coa_edit_view, name='coa_edit'),
    path('coa/<int:pk>/delete/', views.coa_delete_view, name='coa_delete'),

    # Fiscal Periods
    path('periods/', views.period_list_view, name='period_list'),
    path('periods/create/', views.period_create_view, name='period_create'),
    path('periods/<int:pk>/', views.period_detail_view, name='period_detail'),
    path('periods/<int:pk>/edit/', views.period_edit_view, name='period_edit'),
    path('periods/<int:pk>/delete/', views.period_delete_view, name='period_delete'),
    path('periods/<int:pk>/close/', views.period_close_view, name='period_close'),
    path('periods/<int:pk>/reopen/', views.period_reopen_view, name='period_reopen'),

    # Customers
    path('customers/', views.customer_list_view, name='customer_list'),
    path('customers/create/', views.customer_create_view, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail_view, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit_view, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete_view, name='customer_delete'),

    # Tax Jurisdictions
    path('tax-jurisdictions/', views.jurisdiction_list_view, name='jurisdiction_list'),
    path('tax-jurisdictions/create/', views.jurisdiction_create_view, name='jurisdiction_create'),
    path('tax-jurisdictions/<int:pk>/', views.jurisdiction_detail_view, name='jurisdiction_detail'),
    path('tax-jurisdictions/<int:pk>/edit/', views.jurisdiction_edit_view, name='jurisdiction_edit'),
    path('tax-jurisdictions/<int:pk>/delete/', views.jurisdiction_delete_view, name='jurisdiction_delete'),

    # Tax Rules
    path('tax-rules/', views.tax_rule_list_view, name='tax_rule_list'),
    path('tax-rules/create/', views.tax_rule_create_view, name='tax_rule_create'),
    path('tax-rules/<int:pk>/', views.tax_rule_detail_view, name='tax_rule_detail'),
    path('tax-rules/<int:pk>/edit/', views.tax_rule_edit_view, name='tax_rule_edit'),
    path('tax-rules/<int:pk>/delete/', views.tax_rule_delete_view, name='tax_rule_delete'),

    # AP Bills
    path('bills/', views.ap_bill_list_view, name='ap_bill_list'),
    path('bills/create/', views.ap_bill_create_view, name='ap_bill_create'),
    path('bills/<int:pk>/', views.ap_bill_detail_view, name='ap_bill_detail'),
    path('bills/<int:pk>/edit/', views.ap_bill_edit_view, name='ap_bill_edit'),
    path('bills/<int:pk>/delete/', views.ap_bill_delete_view, name='ap_bill_delete'),
    path('bills/<int:pk>/submit/', views.ap_bill_submit_view, name='ap_bill_submit'),
    path('bills/<int:pk>/approve/', views.ap_bill_approve_view, name='ap_bill_approve'),
    path('bills/<int:pk>/post/', views.ap_bill_post_view, name='ap_bill_post'),
    path('bills/<int:pk>/mark-paid/', views.ap_bill_mark_paid_view, name='ap_bill_mark_paid'),
    path('bills/<int:pk>/void/', views.ap_bill_void_view, name='ap_bill_void'),
    path('bills/<int:pk>/queue-sync/', views.ap_bill_queue_sync_view, name='ap_bill_queue_sync'),

    # AR Invoices
    path('invoices/', views.ar_invoice_list_view, name='ar_invoice_list'),
    path('invoices/create/', views.ar_invoice_create_view, name='ar_invoice_create'),
    path('invoices/<int:pk>/', views.ar_invoice_detail_view, name='ar_invoice_detail'),
    path('invoices/<int:pk>/edit/', views.ar_invoice_edit_view, name='ar_invoice_edit'),
    path('invoices/<int:pk>/delete/', views.ar_invoice_delete_view, name='ar_invoice_delete'),
    path('invoices/<int:pk>/send/', views.ar_invoice_send_view, name='ar_invoice_send'),
    path('invoices/<int:pk>/mark-paid/', views.ar_invoice_mark_paid_view, name='ar_invoice_mark_paid'),
    path('invoices/<int:pk>/void/', views.ar_invoice_void_view, name='ar_invoice_void'),
    path('invoices/<int:pk>/queue-sync/', views.ar_invoice_queue_sync_view, name='ar_invoice_queue_sync'),

    # Journal Entries
    path('journal-entries/', views.journal_entry_list_view, name='journal_entry_list'),
    path('journal-entries/create/', views.journal_entry_create_view, name='journal_entry_create'),
    path('journal-entries/<int:pk>/', views.journal_entry_detail_view, name='journal_entry_detail'),
    path('journal-entries/<int:pk>/edit/', views.journal_entry_edit_view, name='journal_entry_edit'),
    path('journal-entries/<int:pk>/delete/', views.journal_entry_delete_view, name='journal_entry_delete'),
    path('journal-entries/<int:pk>/post/', views.journal_entry_post_view, name='journal_entry_post'),
    path('journal-entries/<int:pk>/void/', views.journal_entry_void_view, name='journal_entry_void'),
    path('journal-entries/<int:pk>/queue-sync/', views.journal_entry_queue_sync_view, name='journal_entry_queue_sync'),

    # Generate-from-source
    path('generate/ap-bill/<int:invoice_pk>/', views.generate_ap_bill_from_invoice_view, name='generate_ap_bill_from_invoice'),
    path('generate/ar-invoice/<int:shipment_pk>/', views.generate_ar_invoice_from_shipment_view, name='generate_ar_invoice_from_shipment'),
    path('generate/journal/<str:source_type>/<int:source_pk>/', views.generate_journal_from_source_view, name='generate_journal_from_source'),
]
