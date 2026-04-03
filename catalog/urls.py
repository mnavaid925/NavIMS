from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    # Categories
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/create/', views.category_create_view, name='category_create'),
    path('categories/<int:pk>/', views.category_detail_view, name='category_detail'),
    path('categories/<int:pk>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_view, name='category_delete'),

    # Products
    path('products/', views.product_list_view, name='product_list'),
    path('products/create/', views.product_create_view, name='product_create'),
    path('products/<int:pk>/', views.product_detail_view, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_edit_view, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete_view, name='product_delete'),

    # Product Images (inline from detail page)
    path('products/<int:pk>/images/upload/', views.product_image_upload_view, name='product_image_upload'),
    path('products/<int:pk>/images/<int:image_pk>/delete/', views.product_image_delete_view, name='product_image_delete'),

    # Product Documents (inline from detail page)
    path('products/<int:pk>/documents/upload/', views.product_document_upload_view, name='product_document_upload'),
    path('products/<int:pk>/documents/<int:doc_pk>/delete/', views.product_document_delete_view, name='product_document_delete'),
]
