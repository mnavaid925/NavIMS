from django.urls import path

from . import views

app_name = 'reporting'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('<slug:report_type>/', views.snapshot_list_view, name='snapshot_list'),
    path('<slug:report_type>/generate/', views.snapshot_generate_view, name='snapshot_generate'),
    path('<slug:report_type>/<int:pk>/', views.snapshot_detail_view, name='snapshot_detail'),
    path('<slug:report_type>/<int:pk>/delete/', views.snapshot_delete_view, name='snapshot_delete'),
    path('<slug:report_type>/<int:pk>/export/csv/', views.snapshot_export_csv_view, name='snapshot_export_csv'),
    path('<slug:report_type>/<int:pk>/export/pdf/', views.snapshot_export_pdf_view, name='snapshot_export_pdf'),
]
