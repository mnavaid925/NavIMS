from django.urls import path
from . import api_views

app_name = 'barcode_rfid_api'

urlpatterns = [
    path('scan/', api_views.scan_view, name='scan'),
    path('batch-scan/', api_views.batch_scan_view, name='batch_scan'),
    path('rfid-read/', api_views.rfid_read_view, name='rfid_read'),
    path('heartbeat/', api_views.heartbeat_view, name='heartbeat'),
]
