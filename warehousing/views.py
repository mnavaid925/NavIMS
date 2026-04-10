from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product
from .models import (
    Warehouse, Zone, Aisle, Rack, Bin,
    CrossDockOrder, CrossDockItem,
)
from .forms import (
    WarehouseForm, ZoneForm, AisleForm, RackForm, BinForm,
    CrossDockOrderForm, CrossDockItemFormSet,
)


# ──────────────────────────────────────────────
# Warehouse CRUD views
# ──────────────────────────────────────────────

@login_required
def warehouse_list_view(request):
    tenant = request.tenant
    queryset = Warehouse.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    wh_type = request.GET.get('type', '')
    if wh_type:
        queryset = queryset.filter(warehouse_type=wh_type)

    active = request.GET.get('active', '')
    if active == 'active':
        queryset = queryset.filter(is_active=True)
    elif active == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    warehouses = paginator.get_page(page_number)

    context = {
        'warehouses': warehouses,
        'q': q,
        'type_choices': Warehouse.WAREHOUSE_TYPE_CHOICES,
        'current_type': wh_type,
        'current_active': active,
    }
    return render(request, 'warehousing/warehouse_list.html', context)


@login_required
def warehouse_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = WarehouseForm(request.POST, tenant=tenant)
        if form.is_valid():
            warehouse = form.save()
            messages.success(request, f'Warehouse "{warehouse.name}" created successfully.')
            return redirect('warehousing:warehouse_detail', pk=warehouse.pk)
    else:
        form = WarehouseForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Warehouse',
    }
    return render(request, 'warehousing/warehouse_form.html', context)


@login_required
def warehouse_detail_view(request, pk):
    tenant = request.tenant
    warehouse = get_object_or_404(Warehouse, pk=pk, tenant=tenant)
    zones = warehouse.zones.all()

    context = {
        'warehouse': warehouse,
        'zones': zones,
    }
    return render(request, 'warehousing/warehouse_detail.html', context)


@login_required
def warehouse_edit_view(request, pk):
    tenant = request.tenant
    warehouse = get_object_or_404(Warehouse, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Warehouse "{warehouse.name}" updated successfully.')
            return redirect('warehousing:warehouse_detail', pk=warehouse.pk)
    else:
        form = WarehouseForm(instance=warehouse, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Warehouse',
        'warehouse': warehouse,
    }
    return render(request, 'warehousing/warehouse_form.html', context)


@login_required
def warehouse_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:warehouse_list')

    warehouse = get_object_or_404(Warehouse, pk=pk, tenant=tenant)

    zone_count = warehouse.zones.count()
    if zone_count > 0:
        messages.error(
            request,
            f'Cannot delete "{warehouse.name}" — it has {zone_count} zone{"s" if zone_count != 1 else ""}. '
            f'Delete or reassign them first.',
        )
        return redirect('warehousing:warehouse_detail', pk=warehouse.pk)

    name = warehouse.name
    warehouse.delete()
    messages.success(request, f'Warehouse "{name}" deleted successfully.')
    return redirect('warehousing:warehouse_list')


@login_required
def warehouse_map_view(request, pk):
    tenant = request.tenant
    warehouse = get_object_or_404(Warehouse, pk=pk, tenant=tenant)
    zones = warehouse.zones.filter(is_active=True).prefetch_related(
        'aisles__racks__bins',
        'bins',
    )

    total_bins = Bin.objects.filter(zone__warehouse=warehouse).count()
    occupied_bins = Bin.objects.filter(zone__warehouse=warehouse, is_occupied=True).count()

    context = {
        'warehouse': warehouse,
        'zones': zones,
        'total_bins': total_bins,
        'occupied_bins': occupied_bins,
        'available_bins': total_bins - occupied_bins,
    }
    return render(request, 'warehousing/warehouse_map.html', context)


# ──────────────────────────────────────────────
# Zone CRUD views
# ──────────────────────────────────────────────

@login_required
def zone_list_view(request):
    tenant = request.tenant
    queryset = Zone.objects.filter(tenant=tenant).select_related('warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    zone_type = request.GET.get('type', '')
    if zone_type:
        queryset = queryset.filter(zone_type=zone_type)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    zones = paginator.get_page(page_number)

    context = {
        'zones': zones,
        'q': q,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'type_choices': Zone.ZONE_TYPE_CHOICES,
        'current_warehouse': warehouse_id,
        'current_type': zone_type,
    }
    return render(request, 'warehousing/zone_list.html', context)


@login_required
def zone_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ZoneForm(request.POST, tenant=tenant)
        if form.is_valid():
            zone = form.save()
            messages.success(request, f'Zone "{zone.name}" created successfully.')
            return redirect('warehousing:zone_detail', pk=zone.pk)
    else:
        initial = {}
        warehouse_id = request.GET.get('warehouse')
        if warehouse_id:
            initial['warehouse'] = warehouse_id
        form = ZoneForm(tenant=tenant, initial=initial)

    context = {
        'form': form,
        'title': 'Add Zone',
    }
    return render(request, 'warehousing/zone_form.html', context)


@login_required
def zone_detail_view(request, pk):
    tenant = request.tenant
    zone = get_object_or_404(Zone.objects.select_related('warehouse'), pk=pk, tenant=tenant)
    aisles = zone.aisles.all()
    floor_bins = zone.bins.filter(rack__isnull=True)

    context = {
        'zone': zone,
        'aisles': aisles,
        'floor_bins': floor_bins,
    }
    return render(request, 'warehousing/zone_detail.html', context)


@login_required
def zone_edit_view(request, pk):
    tenant = request.tenant
    zone = get_object_or_404(Zone, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ZoneForm(request.POST, instance=zone, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Zone "{zone.name}" updated successfully.')
            return redirect('warehousing:zone_detail', pk=zone.pk)
    else:
        form = ZoneForm(instance=zone, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Zone',
        'zone': zone,
    }
    return render(request, 'warehousing/zone_form.html', context)


@login_required
def zone_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:zone_list')

    zone = get_object_or_404(Zone, pk=pk, tenant=tenant)

    aisle_count = zone.aisles.count()
    bin_count = zone.bins.count()
    if aisle_count > 0 or bin_count > 0:
        parts = []
        if aisle_count > 0:
            parts.append(f'{aisle_count} aisle{"s" if aisle_count != 1 else ""}')
        if bin_count > 0:
            parts.append(f'{bin_count} bin{"s" if bin_count != 1 else ""}')
        messages.error(
            request,
            f'Cannot delete "{zone.name}" — it has {" and ".join(parts)}. '
            f'Delete or reassign them first.',
        )
        return redirect('warehousing:zone_detail', pk=zone.pk)

    name = zone.name
    zone.delete()
    messages.success(request, f'Zone "{name}" deleted successfully.')
    return redirect('warehousing:zone_list')


# ──────────────────────────────────────────────
# Aisle CRUD views
# ──────────────────────────────────────────────

@login_required
def aisle_list_view(request):
    tenant = request.tenant
    queryset = Aisle.objects.filter(tenant=tenant).select_related('zone', 'zone__warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    zone_id = request.GET.get('zone', '')
    if zone_id:
        queryset = queryset.filter(zone_id=zone_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    aisles = paginator.get_page(page_number)

    context = {
        'aisles': aisles,
        'q': q,
        'zones': Zone.objects.filter(tenant=tenant, is_active=True).select_related('warehouse'),
        'current_zone': zone_id,
    }
    return render(request, 'warehousing/aisle_list.html', context)


@login_required
def aisle_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = AisleForm(request.POST, tenant=tenant)
        if form.is_valid():
            aisle = form.save()
            messages.success(request, f'Aisle "{aisle.name}" created successfully.')
            return redirect('warehousing:aisle_detail', pk=aisle.pk)
    else:
        initial = {}
        zone_id = request.GET.get('zone')
        if zone_id:
            initial['zone'] = zone_id
        form = AisleForm(tenant=tenant, initial=initial)

    context = {
        'form': form,
        'title': 'Add Aisle',
    }
    return render(request, 'warehousing/aisle_form.html', context)


@login_required
def aisle_detail_view(request, pk):
    tenant = request.tenant
    aisle = get_object_or_404(
        Aisle.objects.select_related('zone', 'zone__warehouse'),
        pk=pk, tenant=tenant,
    )
    racks = aisle.racks.all()

    context = {
        'aisle': aisle,
        'racks': racks,
    }
    return render(request, 'warehousing/aisle_detail.html', context)


@login_required
def aisle_edit_view(request, pk):
    tenant = request.tenant
    aisle = get_object_or_404(Aisle, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = AisleForm(request.POST, instance=aisle, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Aisle "{aisle.name}" updated successfully.')
            return redirect('warehousing:aisle_detail', pk=aisle.pk)
    else:
        form = AisleForm(instance=aisle, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Aisle',
        'aisle': aisle,
    }
    return render(request, 'warehousing/aisle_form.html', context)


@login_required
def aisle_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:aisle_list')

    aisle = get_object_or_404(Aisle, pk=pk, tenant=tenant)

    rack_count = aisle.racks.count()
    if rack_count > 0:
        messages.error(
            request,
            f'Cannot delete "{aisle.name}" — it has {rack_count} rack{"s" if rack_count != 1 else ""}. '
            f'Delete or reassign them first.',
        )
        return redirect('warehousing:aisle_detail', pk=aisle.pk)

    name = aisle.name
    aisle.delete()
    messages.success(request, f'Aisle "{name}" deleted successfully.')
    return redirect('warehousing:aisle_list')


# ──────────────────────────────────────────────
# Rack CRUD views
# ──────────────────────────────────────────────

@login_required
def rack_list_view(request):
    tenant = request.tenant
    queryset = Rack.objects.filter(tenant=tenant).select_related('aisle', 'aisle__zone', 'aisle__zone__warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    aisle_id = request.GET.get('aisle', '')
    if aisle_id:
        queryset = queryset.filter(aisle_id=aisle_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    racks = paginator.get_page(page_number)

    context = {
        'racks': racks,
        'q': q,
        'aisles': Aisle.objects.filter(tenant=tenant, is_active=True).select_related('zone'),
        'current_aisle': aisle_id,
    }
    return render(request, 'warehousing/rack_list.html', context)


@login_required
def rack_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = RackForm(request.POST, tenant=tenant)
        if form.is_valid():
            rack = form.save()
            messages.success(request, f'Rack "{rack.name}" created successfully.')
            return redirect('warehousing:rack_detail', pk=rack.pk)
    else:
        initial = {}
        aisle_id = request.GET.get('aisle')
        if aisle_id:
            initial['aisle'] = aisle_id
        form = RackForm(tenant=tenant, initial=initial)

    context = {
        'form': form,
        'title': 'Add Rack',
    }
    return render(request, 'warehousing/rack_form.html', context)


@login_required
def rack_detail_view(request, pk):
    tenant = request.tenant
    rack = get_object_or_404(
        Rack.objects.select_related('aisle', 'aisle__zone', 'aisle__zone__warehouse'),
        pk=pk, tenant=tenant,
    )
    bins = rack.bins.all()

    context = {
        'rack': rack,
        'bins': bins,
    }
    return render(request, 'warehousing/rack_detail.html', context)


@login_required
def rack_edit_view(request, pk):
    tenant = request.tenant
    rack = get_object_or_404(Rack, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = RackForm(request.POST, instance=rack, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Rack "{rack.name}" updated successfully.')
            return redirect('warehousing:rack_detail', pk=rack.pk)
    else:
        form = RackForm(instance=rack, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Rack',
        'rack': rack,
    }
    return render(request, 'warehousing/rack_form.html', context)


@login_required
def rack_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:rack_list')

    rack = get_object_or_404(Rack, pk=pk, tenant=tenant)

    bin_count = rack.bins.count()
    if bin_count > 0:
        messages.error(
            request,
            f'Cannot delete "{rack.name}" — it has {bin_count} bin{"s" if bin_count != 1 else ""}. '
            f'Delete or reassign them first.',
        )
        return redirect('warehousing:rack_detail', pk=rack.pk)

    name = rack.name
    rack.delete()
    messages.success(request, f'Rack "{name}" deleted successfully.')
    return redirect('warehousing:rack_list')


# ──────────────────────────────────────────────
# Bin CRUD views
# ──────────────────────────────────────────────

@login_required
def bin_list_view(request):
    tenant = request.tenant
    queryset = Bin.objects.filter(tenant=tenant).select_related('zone', 'zone__warehouse', 'rack')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    zone_id = request.GET.get('zone', '')
    if zone_id:
        queryset = queryset.filter(zone_id=zone_id)

    bin_type = request.GET.get('type', '')
    if bin_type:
        queryset = queryset.filter(bin_type=bin_type)

    capacity = request.GET.get('capacity', '')
    if capacity == 'available':
        queryset = queryset.filter(is_occupied=False)
    elif capacity == 'occupied':
        queryset = queryset.filter(is_occupied=True)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    bins = paginator.get_page(page_number)

    context = {
        'bins': bins,
        'q': q,
        'zones': Zone.objects.filter(tenant=tenant, is_active=True).select_related('warehouse'),
        'type_choices': Bin.BIN_TYPE_CHOICES,
        'current_zone': zone_id,
        'current_type': bin_type,
        'current_capacity': capacity,
    }
    return render(request, 'warehousing/bin_list.html', context)


@login_required
def bin_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = BinForm(request.POST, tenant=tenant)
        if form.is_valid():
            bin_obj = form.save()
            messages.success(request, f'Bin "{bin_obj.name}" created successfully.')
            return redirect('warehousing:bin_detail', pk=bin_obj.pk)
    else:
        initial = {}
        zone_id = request.GET.get('zone')
        if zone_id:
            initial['zone'] = zone_id
        rack_id = request.GET.get('rack')
        if rack_id:
            initial['rack'] = rack_id
        form = BinForm(tenant=tenant, initial=initial)

    context = {
        'form': form,
        'title': 'Add Bin',
    }
    return render(request, 'warehousing/bin_form.html', context)


@login_required
def bin_detail_view(request, pk):
    tenant = request.tenant
    bin_obj = get_object_or_404(
        Bin.objects.select_related('zone', 'zone__warehouse', 'rack', 'rack__aisle'),
        pk=pk, tenant=tenant,
    )

    context = {
        'bin': bin_obj,
    }
    return render(request, 'warehousing/bin_detail.html', context)


@login_required
def bin_edit_view(request, pk):
    tenant = request.tenant
    bin_obj = get_object_or_404(Bin, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = BinForm(request.POST, instance=bin_obj, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Bin "{bin_obj.name}" updated successfully.')
            return redirect('warehousing:bin_detail', pk=bin_obj.pk)
    else:
        form = BinForm(instance=bin_obj, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Bin',
        'bin': bin_obj,
    }
    return render(request, 'warehousing/bin_form.html', context)


@login_required
def bin_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:bin_list')

    bin_obj = get_object_or_404(Bin, pk=pk, tenant=tenant)

    if bin_obj.is_occupied:
        messages.error(
            request,
            f'Cannot delete "{bin_obj.name}" — it is currently occupied. '
            f'Empty the bin before deleting.',
        )
        return redirect('warehousing:bin_detail', pk=bin_obj.pk)

    name = bin_obj.name
    bin_obj.delete()
    messages.success(request, f'Bin "{name}" deleted successfully.')
    return redirect('warehousing:bin_list')


# ──────────────────────────────────────────────
# Cross-Dock CRUD views
# ──────────────────────────────────────────────

@login_required
def crossdock_list_view(request):
    tenant = request.tenant
    queryset = CrossDockOrder.objects.filter(tenant=tenant).select_related('created_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(order_number__icontains=q) | Q(source__icontains=q) | Q(destination__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    priority = request.GET.get('priority', '')
    if priority:
        queryset = queryset.filter(priority=priority)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    orders = paginator.get_page(page_number)

    context = {
        'orders': orders,
        'q': q,
        'status_choices': CrossDockOrder.STATUS_CHOICES,
        'priority_choices': CrossDockOrder.PRIORITY_CHOICES,
        'current_status': status,
        'current_priority': priority,
    }
    return render(request, 'warehousing/crossdock_list.html', context)


@login_required
def crossdock_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = CrossDockOrderForm(request.POST, tenant=tenant)
        formset = CrossDockItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            formset.instance = order
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Cross-Dock Order "{order.order_number}" created successfully.')
            return redirect('warehousing:crossdock_detail', pk=order.pk)
    else:
        form = CrossDockOrderForm(tenant=tenant)
        formset = CrossDockItemFormSet(prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product (optional) —'
        f.fields['product'].required = False

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Cross-Dock Order',
    }
    return render(request, 'warehousing/crossdock_form.html', context)


@login_required
def crossdock_detail_view(request, pk):
    tenant = request.tenant
    order = get_object_or_404(
        CrossDockOrder.objects.select_related('created_by'),
        pk=pk, tenant=tenant,
    )
    items = order.items.all().select_related('product')

    # Status timeline
    status_order = ['pending', 'in_transit', 'at_dock', 'processing', 'dispatched', 'completed']
    status_labels = {
        'pending': 'Pending',
        'in_transit': 'In Transit',
        'at_dock': 'At Dock',
        'processing': 'Processing',
        'dispatched': 'Dispatched',
        'completed': 'Completed',
    }
    current_idx = status_order.index(order.status) if order.status in status_order else -1
    timeline = []
    for i, s in enumerate(status_order):
        if order.status == 'cancelled':
            state = 'cancelled'
        elif i < current_idx:
            state = 'completed'
        elif i == current_idx:
            state = 'current'
        else:
            state = 'upcoming'
        timeline.append({'status': s, 'label': status_labels[s], 'state': state})

    context = {
        'order': order,
        'items': items,
        'timeline': timeline,
    }
    return render(request, 'warehousing/crossdock_detail.html', context)


@login_required
def crossdock_edit_view(request, pk):
    tenant = request.tenant
    order = get_object_or_404(CrossDockOrder, pk=pk, tenant=tenant)

    if order.status != 'pending':
        messages.warning(request, 'Only pending cross-dock orders can be edited.')
        return redirect('warehousing:crossdock_detail', pk=order.pk)

    if request.method == 'POST':
        form = CrossDockOrderForm(request.POST, instance=order, tenant=tenant)
        formset = CrossDockItemFormSet(request.POST, instance=order, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Cross-Dock Order "{order.order_number}" updated successfully.')
            return redirect('warehousing:crossdock_detail', pk=order.pk)
    else:
        form = CrossDockOrderForm(instance=order, tenant=tenant)
        formset = CrossDockItemFormSet(instance=order, prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product (optional) —'
        f.fields['product'].required = False

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Cross-Dock Order',
        'order': order,
    }
    return render(request, 'warehousing/crossdock_form.html', context)


@login_required
def crossdock_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:crossdock_list')

    order = get_object_or_404(CrossDockOrder, pk=pk, tenant=tenant)

    if order.status != 'pending':
        messages.warning(request, 'Only pending cross-dock orders can be deleted.')
        return redirect('warehousing:crossdock_detail', pk=order.pk)

    order_number = order.order_number
    order.delete()
    messages.success(request, f'Cross-Dock Order "{order_number}" deleted successfully.')
    return redirect('warehousing:crossdock_list')


@login_required
def crossdock_status_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:crossdock_detail', pk=pk)

    order = get_object_or_404(CrossDockOrder, pk=pk, tenant=tenant)
    new_status = request.POST.get('new_status', '')

    if not order.can_transition_to(new_status):
        messages.warning(request, f'Cannot transition from "{order.get_status_display()}" to "{new_status}".')
        return redirect('warehousing:crossdock_detail', pk=order.pk)

    # Auto-set timestamps on certain transitions
    if new_status == 'at_dock' and not order.actual_arrival:
        order.actual_arrival = timezone.now()
    elif new_status == 'dispatched' and not order.actual_departure:
        order.actual_departure = timezone.now()

    order.status = new_status
    order.save()

    status_display = dict(CrossDockOrder.STATUS_CHOICES).get(new_status, new_status)
    messages.success(request, f'Cross-Dock Order "{order.order_number}" status changed to {status_display}.')
    return redirect('warehousing:crossdock_detail', pk=order.pk)


@login_required
def crossdock_reopen_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('warehousing:crossdock_detail', pk=pk)

    order = get_object_or_404(CrossDockOrder, pk=pk, tenant=tenant)

    if not order.can_transition_to('pending'):
        messages.warning(request, f'Cannot reopen order from "{order.get_status_display()}" status.')
        return redirect('warehousing:crossdock_detail', pk=order.pk)

    order.status = 'pending'
    order.actual_arrival = None
    order.actual_departure = None
    order.save()
    messages.success(request, f'Cross-Dock Order "{order.order_number}" reopened as pending.')
    return redirect('warehousing:crossdock_detail', pk=order.pk)
