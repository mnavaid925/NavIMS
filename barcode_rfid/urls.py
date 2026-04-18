from django.urls import path
from . import views

app_name = 'barcode_rfid'

urlpatterns = [
    # ── Submodule 1: Label Templates ──
    path('', views.label_template_list_view, name='label_template_list'),
    path('label-templates/', views.label_template_list_view, name='label_template_list_alt'),
    path('label-templates/create/', views.label_template_create_view, name='label_template_create'),
    path('label-templates/<int:pk>/', views.label_template_detail_view, name='label_template_detail'),
    path('label-templates/<int:pk>/edit/', views.label_template_edit_view, name='label_template_edit'),
    path('label-templates/<int:pk>/delete/', views.label_template_delete_view, name='label_template_delete'),

    # ── Submodule 1: Print Jobs ──
    path('label-jobs/', views.label_job_list_view, name='label_job_list'),
    path('label-jobs/create/', views.label_job_create_view, name='label_job_create'),
    path('label-jobs/<int:pk>/', views.label_job_detail_view, name='label_job_detail'),
    path('label-jobs/<int:pk>/edit/', views.label_job_edit_view, name='label_job_edit'),
    path('label-jobs/<int:pk>/delete/', views.label_job_delete_view, name='label_job_delete'),
    path('label-jobs/<int:pk>/pdf/', views.label_job_render_pdf_view, name='label_job_pdf'),
    path('label-jobs/<int:pk>/queue/', views.label_job_queue_view, name='label_job_queue'),
    path('label-jobs/<int:pk>/start-printing/', views.label_job_start_printing_view, name='label_job_start_printing'),
    path('label-jobs/<int:pk>/mark-printed/', views.label_job_mark_printed_view, name='label_job_mark_printed'),
    path('label-jobs/<int:pk>/mark-failed/', views.label_job_mark_failed_view, name='label_job_mark_failed'),
    path('label-jobs/<int:pk>/cancel/', views.label_job_cancel_view, name='label_job_cancel'),

    # ── Submodule 2: Scanner Devices ──
    path('devices/', views.device_list_view, name='device_list'),
    path('devices/create/', views.device_create_view, name='device_create'),
    path('devices/<int:pk>/', views.device_detail_view, name='device_detail'),
    path('devices/<int:pk>/edit/', views.device_edit_view, name='device_edit'),
    path('devices/<int:pk>/delete/', views.device_delete_view, name='device_delete'),
    path('devices/<int:pk>/rotate-token/', views.device_rotate_token_view, name='device_rotate_token'),

    # ── Submodule 2: Scan Events ──
    path('scan-events/', views.scan_event_list_view, name='scan_event_list'),
    path('scan-events/<int:pk>/', views.scan_event_detail_view, name='scan_event_detail'),

    # ── Submodule 3: RFID Tags ──
    path('rfid-tags/', views.rfid_tag_list_view, name='rfid_tag_list'),
    path('rfid-tags/create/', views.rfid_tag_create_view, name='rfid_tag_create'),
    path('rfid-tags/<int:pk>/', views.rfid_tag_detail_view, name='rfid_tag_detail'),
    path('rfid-tags/<int:pk>/edit/', views.rfid_tag_edit_view, name='rfid_tag_edit'),
    path('rfid-tags/<int:pk>/delete/', views.rfid_tag_delete_view, name='rfid_tag_delete'),
    path('rfid-tags/<int:pk>/activate/', views.rfid_tag_activate_view, name='rfid_tag_activate'),
    path('rfid-tags/<int:pk>/deactivate/', views.rfid_tag_deactivate_view, name='rfid_tag_deactivate'),
    path('rfid-tags/<int:pk>/mark-lost/', views.rfid_tag_mark_lost_view, name='rfid_tag_mark_lost'),
    path('rfid-tags/<int:pk>/mark-damaged/', views.rfid_tag_mark_damaged_view, name='rfid_tag_mark_damaged'),
    path('rfid-tags/<int:pk>/retire/', views.rfid_tag_retire_view, name='rfid_tag_retire'),

    # ── Submodule 3: RFID Readers ──
    path('rfid-readers/', views.rfid_reader_list_view, name='rfid_reader_list'),
    path('rfid-readers/create/', views.rfid_reader_create_view, name='rfid_reader_create'),
    path('rfid-readers/<int:pk>/', views.rfid_reader_detail_view, name='rfid_reader_detail'),
    path('rfid-readers/<int:pk>/edit/', views.rfid_reader_edit_view, name='rfid_reader_edit'),
    path('rfid-readers/<int:pk>/delete/', views.rfid_reader_delete_view, name='rfid_reader_delete'),

    # ── Submodule 3: RFID Read Events ──
    path('rfid-reads/', views.rfid_read_event_list_view, name='rfid_read_list'),
    path('rfid-reads/<int:pk>/', views.rfid_read_event_detail_view, name='rfid_read_detail'),

    # ── Submodule 4: Batch Scanning ──
    path('batch-sessions/', views.batch_session_list_view, name='batch_session_list'),
    path('batch-sessions/create/', views.batch_session_create_view, name='batch_session_create'),
    path('batch-sessions/<int:pk>/', views.batch_session_detail_view, name='batch_session_detail'),
    path('batch-sessions/<int:pk>/edit/', views.batch_session_edit_view, name='batch_session_edit'),
    path('batch-sessions/<int:pk>/delete/', views.batch_session_delete_view, name='batch_session_delete'),
    path('batch-sessions/<int:pk>/complete/', views.batch_session_complete_view, name='batch_session_complete'),
    path('batch-sessions/<int:pk>/cancel/', views.batch_session_cancel_view, name='batch_session_cancel'),
]
