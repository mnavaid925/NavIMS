from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def dashboard_view(request):
    stats = {
        'total_products': 0,
        'active_orders': 0,
        'warehouses': 0,
        'low_stock_alerts': 0,
    }
    recent_orders = []
    low_stock_items = []

    context = {
        'stats': stats,
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
    }
    return render(request, 'dashboard/index.html', context)
