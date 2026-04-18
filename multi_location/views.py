from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, DecimalField, ExpressionWrapper

from core.decorators import tenant_admin_required
from catalog.models import Product, Category
from inventory.models import StockLevel
from warehousing.models import Warehouse
from .models import (
    Location, LocationPricingRule, LocationTransferRule, LocationSafetyStockRule,
)
from .forms import (
    LocationForm, LocationPricingRuleForm,
    LocationTransferRuleForm, LocationSafetyStockRuleForm,
)


# SQLite / MySQL / Postgres signed BIGINT upper bound. Any PK larger than this
# cannot exist in the DB, so we reject it before it reaches the query layer.
_MAX_DB_INT = 2**63 - 1


def _int_or_none(value):
    """Coerce a GET param to a safe DB-sized int, or None if not coercible.

    D-01 guard — every list view receives raw strings from the querystring and
    previously passed them straight into `.filter(..._id=value)`, which raises
    ValueError on non-numeric input (e.g. `?parent=abc`) and OverflowError on
    ints that exceed the DB's 64-bit integer range.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0 or n > _MAX_DB_INT:
        return None
    return n


# ══════════════════════════════════════════════
# Location CRUD
# ══════════════════════════════════════════════

@login_required
def location_list_view(request):
    tenant = request.tenant
    queryset = Location.objects.filter(tenant=tenant).select_related('parent', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(city__icontains=q)
        )

    location_type = request.GET.get('type', '')
    if location_type:
        queryset = queryset.filter(location_type=location_type)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    parent_raw = request.GET.get('parent', '')
    parent_id = _int_or_none(parent_raw)
    if parent_id is not None:
        queryset = queryset.filter(parent_id=parent_id)

    paginator = Paginator(queryset, 20)
    locations = paginator.get_page(request.GET.get('page'))

    return render(request, 'multi_location/location_list.html', {
        'locations': locations,
        'q': q,
        'type_choices': Location.LOCATION_TYPE_CHOICES,
        'parents': Location.objects.filter(tenant=tenant, parent__isnull=True),
        'current_type': location_type,
        'current_active': active,
        'current_parent': parent_raw if parent_id is not None else '',
    })


@login_required
@tenant_admin_required
def location_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LocationForm(request.POST, tenant=tenant)
        if form.is_valid():
            location = form.save()
            messages.success(request, f'Location "{location.name}" created.')
            return redirect('multi_location:location_detail', pk=location.pk)
    else:
        form = LocationForm(tenant=tenant)
    return render(request, 'multi_location/location_form.html', {
        'form': form,
        'title': 'Add Location',
    })


@login_required
def location_detail_view(request, pk):
    tenant = request.tenant
    location = get_object_or_404(
        Location.objects.select_related('parent', 'warehouse'),
        pk=pk, tenant=tenant,
    )
    children = location.children.filter(tenant=tenant).order_by('name')
    pricing_rules = location.pricing_rules.filter(tenant=tenant)[:10]
    safety_stock_rules = location.safety_stock_rules.filter(tenant=tenant).select_related('product')[:10]
    outbound_rules = location.outbound_transfer_rules.filter(tenant=tenant).select_related('destination_location')[:10]
    inbound_rules = location.inbound_transfer_rules.filter(tenant=tenant).select_related('source_location')[:10]

    stock_summary = None
    if location.warehouse:
        levels = StockLevel.objects.filter(
            tenant=tenant, warehouse=location.warehouse,
        ).select_related('product')
        total_on_hand = levels.aggregate(s=Sum('on_hand'))['s'] or 0
        total_allocated = levels.aggregate(s=Sum('allocated'))['s'] or 0
        stock_summary = {
            'product_count': levels.count(),
            'total_on_hand': total_on_hand,
            'total_allocated': total_allocated,
            'total_available': max(total_on_hand - total_allocated, 0),
        }

    return render(request, 'multi_location/location_detail.html', {
        'location': location,
        'children': children,
        'pricing_rules': pricing_rules,
        'safety_stock_rules': safety_stock_rules,
        'outbound_rules': outbound_rules,
        'inbound_rules': inbound_rules,
        'stock_summary': stock_summary,
    })


@login_required
@tenant_admin_required
def location_edit_view(request, pk):
    tenant = request.tenant
    location = get_object_or_404(Location, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Location "{location.name}" updated.')
            return redirect('multi_location:location_detail', pk=location.pk)
    else:
        form = LocationForm(instance=location, tenant=tenant)
    return render(request, 'multi_location/location_form.html', {
        'form': form,
        'location': location,
        'title': f'Edit Location: {location.name}',
    })


@login_required
@tenant_admin_required
def location_delete_view(request, pk):
    tenant = request.tenant
    location = get_object_or_404(Location, pk=pk, tenant=tenant)
    if request.method == 'POST':
        name = location.name
        location.delete()
        messages.success(request, f'Location "{name}" deleted.')
        return redirect('multi_location:location_list')
    return redirect('multi_location:location_list')


# ══════════════════════════════════════════════
# Global Stock Visibility
# ══════════════════════════════════════════════

@login_required
def stock_visibility_view(request):
    tenant = request.tenant

    linked_locations = Location.objects.filter(
        tenant=tenant, warehouse__isnull=False,
    ).select_related('warehouse', 'parent')

    levels_qs = StockLevel.objects.filter(tenant=tenant).select_related(
        'product', 'warehouse',
    )

    location_raw = request.GET.get('location', '')
    location_id = _int_or_none(location_raw)
    if location_id is not None:
        try:
            loc = Location.objects.get(tenant=tenant, pk=location_id)
            warehouse_ids = [
                loc_obj.warehouse_id for loc_obj in
                Location.objects.filter(tenant=tenant, pk__in=loc.get_descendant_ids(include_self=True))
                if loc_obj.warehouse_id
            ]
            levels_qs = levels_qs.filter(warehouse_id__in=warehouse_ids)
        except Location.DoesNotExist:
            pass

    q = request.GET.get('q', '').strip()
    if q:
        levels_qs = levels_qs.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
        )

    low_stock = request.GET.get('low_stock', '')
    if low_stock == '1':
        levels_qs = levels_qs.filter(reorder_point__gt=0, on_hand__lte=F('reorder_point'))

    warehouse_to_location = {
        loc.warehouse_id: loc for loc in linked_locations
    }

    total_value_expr = ExpressionWrapper(
        F('on_hand') * F('product__purchase_cost'),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )
    levels_qs = levels_qs.annotate(total_value=total_value_expr)

    total_on_hand = levels_qs.aggregate(s=Sum('on_hand'))['s'] or 0
    total_allocated = levels_qs.aggregate(s=Sum('allocated'))['s'] or 0
    total_value = levels_qs.aggregate(s=Sum('total_value'))['s'] or Decimal('0.00')
    low_stock_count = levels_qs.filter(
        reorder_point__gt=0, on_hand__lte=F('reorder_point'),
    ).count()

    paginator = Paginator(levels_qs.order_by('warehouse__name', 'product__name'), 25)
    levels = paginator.get_page(request.GET.get('page'))

    rows = []
    for level in levels:
        rows.append({
            'level': level,
            'location': warehouse_to_location.get(level.warehouse_id),
        })

    return render(request, 'multi_location/stock_visibility.html', {
        'rows': rows,
        'levels_page': levels,
        'q': q,
        'locations': Location.objects.filter(tenant=tenant),
        'current_location': location_raw if location_id is not None else '',
        'current_low_stock': low_stock,
        'stats': {
            'total_on_hand': total_on_hand,
            'total_allocated': total_allocated,
            'total_available': max(total_on_hand - total_allocated, 0),
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'linked_location_count': linked_locations.count(),
        },
    })


# ══════════════════════════════════════════════
# Pricing Rule CRUD
# ══════════════════════════════════════════════

@login_required
def pricing_rule_list_view(request):
    tenant = request.tenant
    queryset = LocationPricingRule.objects.filter(tenant=tenant).select_related(
        'location', 'product', 'category',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(location__name__icontains=q) |
            Q(product__name__icontains=q) |
            Q(category__name__icontains=q) |
            Q(notes__icontains=q)
        )

    location_raw = request.GET.get('location', '')
    location_id = _int_or_none(location_raw)
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)

    rule_type = request.GET.get('rule_type', '')
    if rule_type:
        queryset = queryset.filter(rule_type=rule_type)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    rules = paginator.get_page(request.GET.get('page'))

    return render(request, 'multi_location/pricing_rule_list.html', {
        'rules': rules,
        'q': q,
        'locations': Location.objects.filter(tenant=tenant, is_active=True),
        'rule_type_choices': LocationPricingRule.RULE_TYPE_CHOICES,
        'current_location': location_raw if location_id is not None else '',
        'current_rule_type': rule_type,
        'current_active': active,
    })


@login_required
@tenant_admin_required
def pricing_rule_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LocationPricingRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            rule = form.save()
            messages.success(request, 'Pricing rule created.')
            return redirect('multi_location:pricing_rule_detail', pk=rule.pk)
    else:
        form = LocationPricingRuleForm(tenant=tenant)
    return render(request, 'multi_location/pricing_rule_form.html', {
        'form': form,
        'title': 'Add Pricing Rule',
    })


@login_required
def pricing_rule_detail_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(
        LocationPricingRule.objects.select_related('location', 'product', 'category'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'multi_location/pricing_rule_detail.html', {'rule': rule})


@login_required
@tenant_admin_required
def pricing_rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationPricingRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = LocationPricingRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pricing rule updated.')
            return redirect('multi_location:pricing_rule_detail', pk=rule.pk)
    else:
        form = LocationPricingRuleForm(instance=rule, tenant=tenant)
    return render(request, 'multi_location/pricing_rule_form.html', {
        'form': form,
        'rule': rule,
        'title': 'Edit Pricing Rule',
    })


@login_required
@tenant_admin_required
def pricing_rule_delete_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationPricingRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Pricing rule deleted.')
        return redirect('multi_location:pricing_rule_list')
    return redirect('multi_location:pricing_rule_list')


# ══════════════════════════════════════════════
# Transfer Rule CRUD
# ══════════════════════════════════════════════

@login_required
def transfer_rule_list_view(request):
    tenant = request.tenant
    queryset = LocationTransferRule.objects.filter(tenant=tenant).select_related(
        'source_location', 'destination_location',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(source_location__name__icontains=q) |
            Q(destination_location__name__icontains=q) |
            Q(notes__icontains=q)
        )

    source_raw = request.GET.get('source', '')
    source_id = _int_or_none(source_raw)
    if source_id is not None:
        queryset = queryset.filter(source_location_id=source_id)

    destination_raw = request.GET.get('destination', '')
    destination_id = _int_or_none(destination_raw)
    if destination_id is not None:
        queryset = queryset.filter(destination_location_id=destination_id)

    allowed = request.GET.get('allowed', '')
    if allowed == 'yes':
        queryset = queryset.filter(allowed=True)
    elif allowed == 'no':
        queryset = queryset.filter(allowed=False)

    paginator = Paginator(queryset, 20)
    rules = paginator.get_page(request.GET.get('page'))

    locations = Location.objects.filter(tenant=tenant, is_active=True)

    return render(request, 'multi_location/transfer_rule_list.html', {
        'rules': rules,
        'q': q,
        'locations': locations,
        'current_source': source_raw if source_id is not None else '',
        'current_destination': destination_raw if destination_id is not None else '',
        'current_allowed': allowed,
    })


@login_required
@tenant_admin_required
def transfer_rule_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LocationTransferRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            rule = form.save()
            messages.success(request, 'Transfer rule created.')
            return redirect('multi_location:transfer_rule_detail', pk=rule.pk)
    else:
        form = LocationTransferRuleForm(tenant=tenant)
    return render(request, 'multi_location/transfer_rule_form.html', {
        'form': form,
        'title': 'Add Transfer Rule',
    })


@login_required
def transfer_rule_detail_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(
        LocationTransferRule.objects.select_related('source_location', 'destination_location'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'multi_location/transfer_rule_detail.html', {'rule': rule})


@login_required
@tenant_admin_required
def transfer_rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationTransferRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = LocationTransferRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transfer rule updated.')
            return redirect('multi_location:transfer_rule_detail', pk=rule.pk)
    else:
        form = LocationTransferRuleForm(instance=rule, tenant=tenant)
    return render(request, 'multi_location/transfer_rule_form.html', {
        'form': form,
        'rule': rule,
        'title': 'Edit Transfer Rule',
    })


@login_required
@tenant_admin_required
def transfer_rule_delete_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationTransferRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Transfer rule deleted.')
        return redirect('multi_location:transfer_rule_list')
    return redirect('multi_location:transfer_rule_list')


# ══════════════════════════════════════════════
# Safety Stock Rule CRUD
# ══════════════════════════════════════════════

@login_required
def safety_stock_rule_list_view(request):
    tenant = request.tenant
    queryset = LocationSafetyStockRule.objects.filter(tenant=tenant).select_related(
        'location', 'product',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(location__name__icontains=q) |
            Q(product__name__icontains=q) |
            Q(product__sku__icontains=q)
        )

    location_raw = request.GET.get('location', '')
    location_id = _int_or_none(location_raw)
    if location_id is not None:
        queryset = queryset.filter(location_id=location_id)

    product_raw = request.GET.get('product', '')
    product_id = _int_or_none(product_raw)
    if product_id is not None:
        queryset = queryset.filter(product_id=product_id)

    paginator = Paginator(queryset, 20)
    rules = paginator.get_page(request.GET.get('page'))

    return render(request, 'multi_location/safety_stock_rule_list.html', {
        'rules': rules,
        'q': q,
        'locations': Location.objects.filter(tenant=tenant, is_active=True),
        'products': Product.objects.filter(tenant=tenant),
        'current_location': location_raw if location_id is not None else '',
        'current_product': product_raw if product_id is not None else '',
    })


@login_required
@tenant_admin_required
def safety_stock_rule_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LocationSafetyStockRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            rule = form.save()
            messages.success(request, 'Safety stock rule created.')
            return redirect('multi_location:safety_stock_rule_detail', pk=rule.pk)
    else:
        form = LocationSafetyStockRuleForm(tenant=tenant)
    return render(request, 'multi_location/safety_stock_rule_form.html', {
        'form': form,
        'title': 'Add Safety Stock Rule',
    })


@login_required
def safety_stock_rule_detail_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(
        LocationSafetyStockRule.objects.select_related('location', 'product'),
        pk=pk, tenant=tenant,
    )
    stock_level = None
    if rule.location.warehouse:
        stock_level = StockLevel.objects.filter(
            tenant=tenant, product=rule.product, warehouse=rule.location.warehouse,
        ).first()
    return render(request, 'multi_location/safety_stock_rule_detail.html', {
        'rule': rule,
        'stock_level': stock_level,
    })


@login_required
@tenant_admin_required
def safety_stock_rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationSafetyStockRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = LocationSafetyStockRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Safety stock rule updated.')
            return redirect('multi_location:safety_stock_rule_detail', pk=rule.pk)
    else:
        form = LocationSafetyStockRuleForm(instance=rule, tenant=tenant)
    return render(request, 'multi_location/safety_stock_rule_form.html', {
        'form': form,
        'rule': rule,
        'title': 'Edit Safety Stock Rule',
    })


@login_required
@tenant_admin_required
def safety_stock_rule_delete_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(LocationSafetyStockRule, pk=pk, tenant=tenant)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Safety stock rule deleted.')
        return redirect('multi_location:safety_stock_rule_list')
    return redirect('multi_location:safety_stock_rule_list')
