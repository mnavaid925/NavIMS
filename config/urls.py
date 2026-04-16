from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('accounts/', include('accounts.urls')),
    path('administration/', include('administration.urls')),
    path('catalog/', include('catalog.urls')),
    path('vendors/', include('vendors.urls')),
    path('purchase-orders/', include('purchase_orders.urls')),
    path('receiving/', include('receiving.urls')),
    path('warehousing/', include('warehousing.urls')),
    path('inventory/', include('inventory.urls')),
    path('stock-movements/', include('stock_movements.urls')),
    path('lot-tracking/', include('lot_tracking.urls')),
    path('orders/', include('orders.urls')),
    path('returns/', include('returns.urls')),
    path('stocktaking/', include('stocktaking.urls')),
    path('multi-location/', include('multi_location.urls')),
    path('forecasting/', include('forecasting.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
