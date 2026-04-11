from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from core.models import User
from .models import (
    SalesOrder, SalesOrderItem, PickList, PickListItem,
    PackingList, Shipment, ShipmentTracking,
    WavePlan, WaveOrderAssignment, Carrier, ShippingRate,
)
from .forms import (
    SalesOrderForm, SalesOrderItemFormSet,
    PickListForm, PickListItemFormSet, PickListAssignForm,
    PackingListForm, ShipmentForm, ShipmentTrackingForm,
    WavePlanForm, WaveOrderSelectionForm,
    CarrierForm, ShippingRateForm,
)


# ══════════════════════════════════════════════
# Sales Order CRUD
# ══════════════════════════════════════════════

@login_required
def so_list_view(request):
    tenant = request.tenant
    queryset = SalesOrder.objects.filter(tenant=tenant).select_related('warehouse', 'created_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(order_number__icontains=q) | Q(customer_name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    date_from = request.GET.get('date_from', '')
    if date_from:
        queryset = queryset.filter(order_date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        queryset = queryset.filter(order_date__lte=date_to)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    sales_orders = paginator.get_page(page_number)

    context = {
        'sales_orders': sales_orders,
        'q': q,
        'status_choices': SalesOrder.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_warehouse': warehouse_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'orders/so_list.html', context)


@login_required
def so_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = SalesOrderForm(request.POST, tenant=tenant)
        formset = SalesOrderItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            so = form.save(commit=False)
            so.created_by = request.user
            so.save()
            formset.instance = so
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Sales Order "{so.order_number}" created successfully.')
            return redirect('orders:so_detail', pk=so.pk)
    else:
        form = SalesOrderForm(tenant=tenant)
        formset = SalesOrderItemFormSet(prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Sales Order',
    }
    return render(request, 'orders/so_form.html', context)


@login_required
def so_detail_view(request, pk):
    tenant = request.tenant
    so = get_object_or_404(
        SalesOrder.objects.select_related('warehouse', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = so.items.all().select_related('product')
    pick_lists = so.pick_lists.all().select_related('warehouse', 'assigned_to')
    packing_lists = so.packing_lists.all().select_related('pick_list', 'packed_by')
    shipments = so.shipments.all().select_related('carrier', 'shipped_by')

    # Status timeline
    status_order = ['draft', 'confirmed', 'in_fulfillment', 'picked', 'packed', 'shipped', 'delivered', 'closed']
    status_labels = {
        'draft': 'Draft',
        'confirmed': 'Confirmed',
        'in_fulfillment': 'Fulfillment',
        'picked': 'Picked',
        'packed': 'Packed',
        'shipped': 'Shipped',
        'delivered': 'Delivered',
        'closed': 'Closed',
    }
    current_idx = status_order.index(so.status) if so.status in status_order else -1
    timeline = []
    for i, s in enumerate(status_order):
        if so.status in ('cancelled', 'on_hold'):
            state = 'cancelled'
        elif i < current_idx:
            state = 'completed'
        elif i == current_idx:
            state = 'current'
        else:
            state = 'upcoming'
        timeline.append({'status': s, 'label': status_labels[s], 'state': state})

    context = {
        'so': so,
        'items': items,
        'pick_lists': pick_lists,
        'packing_lists': packing_lists,
        'shipments': shipments,
        'timeline': timeline,
    }
    return render(request, 'orders/so_detail.html', context)


@login_required
def so_edit_view(request, pk):
    tenant = request.tenant
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)

    if so.status != 'draft':
        messages.warning(request, 'Only draft sales orders can be edited.')
        return redirect('orders:so_detail', pk=so.pk)

    if request.method == 'POST':
        form = SalesOrderForm(request.POST, instance=so, tenant=tenant)
        formset = SalesOrderItemFormSet(request.POST, instance=so, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Sales Order "{so.order_number}" updated successfully.')
            return redirect('orders:so_detail', pk=so.pk)
    else:
        form = SalesOrderForm(instance=so, tenant=tenant)
        formset = SalesOrderItemFormSet(instance=so, prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Sales Order',
        'so': so,
    }
    return render(request, 'orders/so_form.html', context)


@login_required
def so_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_list')
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)
    if so.status != 'draft':
        messages.warning(request, 'Only draft sales orders can be deleted.')
        return redirect('orders:so_detail', pk=so.pk)
    order_number = so.order_number
    so.delete()
    messages.success(request, f'Sales Order "{order_number}" deleted successfully.')
    return redirect('orders:so_list')


# ══════════════════════════════════════════════
# Sales Order Status Transitions
# ══════════════════════════════════════════════

@login_required
def so_confirm_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)

    if not so.items.exists():
        messages.warning(request, 'Cannot confirm an order with no line items.')
        return redirect('orders:so_detail', pk=so.pk)

    if not so.can_transition_to('confirmed'):
        messages.warning(request, f'Cannot confirm order in "{so.get_status_display()}" status.')
        return redirect('orders:so_detail', pk=so.pk)

    # Check stock availability and create reservations
    from inventory.models import StockLevel, InventoryReservation
    insufficient = []
    for item in so.items.select_related('product'):
        stock = StockLevel.objects.filter(
            tenant=tenant, product=item.product, warehouse=so.warehouse,
        ).first()
        available = stock.available if stock else 0
        if available < item.quantity:
            insufficient.append(
                f'{item.product.name}: need {item.quantity}, available {available}'
            )

    if insufficient:
        messages.warning(
            request,
            'Insufficient stock for: ' + '; '.join(insufficient),
        )
        return redirect('orders:so_detail', pk=so.pk)

    # Create reservations and update allocated
    for item in so.items.select_related('product'):
        stock = StockLevel.objects.get(
            tenant=tenant, product=item.product, warehouse=so.warehouse,
        )
        stock.allocated += item.quantity
        stock.save()

        res = InventoryReservation(tenant=tenant)
        res.product = item.product
        res.warehouse = so.warehouse
        res.quantity = item.quantity
        res.reference_type = 'sales_order'
        res.reference_number = so.order_number
        res.status = 'confirmed'
        res.reserved_by = request.user
        res.save()

    so.status = 'confirmed'
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" confirmed. Inventory reserved.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_cancel_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)

    if not so.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel order in "{so.get_status_display()}" status.')
        return redirect('orders:so_detail', pk=so.pk)

    # Release reservations
    from inventory.models import StockLevel, InventoryReservation
    reservations = InventoryReservation.objects.filter(
        tenant=tenant, reference_type='sales_order', reference_number=so.order_number,
        status__in=['pending', 'confirmed'],
    )
    for res in reservations:
        stock = StockLevel.objects.filter(
            tenant=tenant, product=res.product, warehouse=res.warehouse,
        ).first()
        if stock:
            stock.allocated = max(stock.allocated - res.quantity, 0)
            stock.save()
        res.status = 'released'
        res.save()

    so.status = 'cancelled'
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" cancelled. Reservations released.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_hold_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)
    if not so.can_transition_to('on_hold'):
        messages.warning(request, f'Cannot put order on hold from "{so.get_status_display()}" status.')
        return redirect('orders:so_detail', pk=so.pk)
    so.status = 'on_hold'
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" placed on hold.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_resume_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)
    if so.status != 'on_hold':
        messages.warning(request, 'Order is not on hold.')
        return redirect('orders:so_detail', pk=so.pk)

    # Determine resume status based on fulfillment progress
    if so.shipments.filter(status='dispatched').exists():
        resume_to = 'shipped'
    elif so.packing_lists.filter(status='completed').exists():
        resume_to = 'packed'
    elif so.pick_lists.filter(status='completed').exists():
        resume_to = 'picked'
    elif so.pick_lists.exists():
        resume_to = 'in_fulfillment'
    else:
        resume_to = 'confirmed'

    so.status = resume_to
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" resumed to {so.get_status_display()}.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_close_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)
    if not so.can_transition_to('closed'):
        messages.warning(request, f'Cannot close order from "{so.get_status_display()}" status.')
        return redirect('orders:so_detail', pk=so.pk)
    so.status = 'closed'
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" closed.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_reopen_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)
    if not so.can_transition_to('draft'):
        messages.warning(request, f'Cannot reopen order from "{so.get_status_display()}" status.')
        return redirect('orders:so_detail', pk=so.pk)
    so.status = 'draft'
    so.save()
    messages.success(request, f'Sales Order "{so.order_number}" reopened as draft.')
    return redirect('orders:so_detail', pk=so.pk)


@login_required
def so_generate_picklist_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:so_detail', pk=pk)
    so = get_object_or_404(SalesOrder, pk=pk, tenant=tenant)

    if so.status not in ('confirmed', 'in_fulfillment'):
        messages.warning(request, 'Can only generate pick lists for confirmed or in-fulfillment orders.')
        return redirect('orders:so_detail', pk=so.pk)

    pick_list = PickList(tenant=tenant)
    pick_list.sales_order = so
    pick_list.warehouse = so.warehouse
    pick_list.created_by = request.user
    pick_list.save()

    for item in so.items.select_related('product'):
        PickListItem.objects.create(
            tenant=tenant,
            pick_list=pick_list,
            product=item.product,
            ordered_quantity=item.quantity,
        )

    if so.status == 'confirmed':
        so.status = 'in_fulfillment'
        so.save()

    messages.success(request, f'Pick List "{pick_list.pick_number}" generated for order {so.order_number}.')
    return redirect('orders:picklist_detail', pk=pick_list.pk)


# ══════════════════════════════════════════════
# Pick List CRUD & Actions
# ══════════════════════════════════════════════

@login_required
def picklist_list_view(request):
    tenant = request.tenant
    queryset = PickList.objects.filter(tenant=tenant).select_related(
        'sales_order', 'warehouse', 'assigned_to',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(pick_number__icontains=q) | Q(sales_order__order_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    pick_lists = paginator.get_page(page_number)

    context = {
        'pick_lists': pick_lists,
        'q': q,
        'status_choices': PickList.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'orders/picklist_list.html', context)


@login_required
def picklist_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = PickListForm(request.POST, tenant=tenant)
        formset = PickListItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            pl = form.save(commit=False)
            pl.created_by = request.user
            pl.save()
            formset.instance = pl
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Pick List "{pl.pick_number}" created successfully.')
            return redirect('orders:picklist_detail', pk=pl.pk)
    else:
        form = PickListForm(tenant=tenant)
        formset = PickListItemFormSet(prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    bins = Bin.objects.filter(tenant=tenant, is_active=True)
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'
        f.fields['bin_location'].queryset = bins
        f.fields['bin_location'].empty_label = '— Select Bin (optional) —'
        f.fields['bin_location'].required = False

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Pick List',
    }
    return render(request, 'orders/picklist_form.html', context)


@login_required
def picklist_detail_view(request, pk):
    tenant = request.tenant
    pl = get_object_or_404(
        PickList.objects.select_related('sales_order', 'warehouse', 'assigned_to', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = pl.items.all().select_related('product', 'bin_location')
    assign_form = PickListAssignForm(tenant=tenant)

    context = {
        'pl': pl,
        'items': items,
        'assign_form': assign_form,
    }
    return render(request, 'orders/picklist_detail.html', context)


@login_required
def picklist_edit_view(request, pk):
    tenant = request.tenant
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)

    if pl.status not in ('pending', 'assigned'):
        messages.warning(request, 'Only pending or assigned pick lists can be edited.')
        return redirect('orders:picklist_detail', pk=pl.pk)

    if request.method == 'POST':
        form = PickListForm(request.POST, instance=pl, tenant=tenant)
        formset = PickListItemFormSet(request.POST, instance=pl, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Pick List "{pl.pick_number}" updated successfully.')
            return redirect('orders:picklist_detail', pk=pl.pk)
    else:
        form = PickListForm(instance=pl, tenant=tenant)
        formset = PickListItemFormSet(instance=pl, prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    bins = Bin.objects.filter(tenant=tenant, is_active=True)
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'
        f.fields['bin_location'].queryset = bins
        f.fields['bin_location'].empty_label = '— Select Bin (optional) —'
        f.fields['bin_location'].required = False

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Pick List',
        'pl': pl,
    }
    return render(request, 'orders/picklist_form.html', context)


@login_required
def picklist_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:picklist_list')
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)
    if pl.status != 'pending':
        messages.warning(request, 'Only pending pick lists can be deleted.')
        return redirect('orders:picklist_detail', pk=pl.pk)
    pick_number = pl.pick_number
    pl.delete()
    messages.success(request, f'Pick List "{pick_number}" deleted successfully.')
    return redirect('orders:picklist_list')


@login_required
def picklist_assign_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:picklist_detail', pk=pk)
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('assigned'):
        messages.warning(request, f'Cannot assign pick list in "{pl.get_status_display()}" status.')
        return redirect('orders:picklist_detail', pk=pl.pk)
    form = PickListAssignForm(request.POST, tenant=tenant)
    if form.is_valid():
        pl.assigned_to = form.cleaned_data['assigned_to']
        pl.status = 'assigned'
        pl.save()
        messages.success(request, f'Pick List "{pl.pick_number}" assigned to {pl.assigned_to.get_full_name() or pl.assigned_to.username}.')
    return redirect('orders:picklist_detail', pk=pl.pk)


@login_required
def picklist_start_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:picklist_detail', pk=pk)
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('in_progress'):
        messages.warning(request, f'Cannot start pick list in "{pl.get_status_display()}" status.')
        return redirect('orders:picklist_detail', pk=pl.pk)
    pl.status = 'in_progress'
    pl.started_at = timezone.now()
    pl.save()
    messages.success(request, f'Pick List "{pl.pick_number}" started.')
    return redirect('orders:picklist_detail', pk=pl.pk)


@login_required
def picklist_complete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:picklist_detail', pk=pk)
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('completed'):
        messages.warning(request, f'Cannot complete pick list in "{pl.get_status_display()}" status.')
        return redirect('orders:picklist_detail', pk=pl.pk)
    pl.status = 'completed'
    pl.completed_at = timezone.now()
    pl.save()

    # Auto-progress SO to 'picked' if all pick lists are completed
    so = pl.sales_order
    if so and so.status == 'in_fulfillment':
        all_completed = not so.pick_lists.exclude(status__in=['completed', 'cancelled']).exists()
        if all_completed:
            so.status = 'picked'
            so.save()

    messages.success(request, f'Pick List "{pl.pick_number}" completed.')
    return redirect('orders:picklist_detail', pk=pl.pk)


@login_required
def picklist_cancel_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:picklist_detail', pk=pk)
    pl = get_object_or_404(PickList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel pick list in "{pl.get_status_display()}" status.')
        return redirect('orders:picklist_detail', pk=pl.pk)
    pl.status = 'cancelled'
    pl.save()
    messages.success(request, f'Pick List "{pl.pick_number}" cancelled.')
    return redirect('orders:picklist_detail', pk=pl.pk)


# ══════════════════════════════════════════════
# Packing List CRUD & Actions
# ══════════════════════════════════════════════

@login_required
def packinglist_list_view(request):
    tenant = request.tenant
    queryset = PackingList.objects.filter(tenant=tenant).select_related(
        'sales_order', 'pick_list', 'packed_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(packing_number__icontains=q) | Q(sales_order__order_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    packing_lists = paginator.get_page(page_number)

    context = {
        'packing_lists': packing_lists,
        'q': q,
        'status_choices': PackingList.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'orders/packinglist_list.html', context)


@login_required
def packinglist_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = PackingListForm(request.POST, tenant=tenant)
        if form.is_valid():
            pl = form.save(commit=False)
            pl.save()
            messages.success(request, f'Packing List "{pl.packing_number}" created successfully.')
            return redirect('orders:packinglist_detail', pk=pl.pk)
    else:
        form = PackingListForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Packing List',
    }
    return render(request, 'orders/packinglist_form.html', context)


@login_required
def packinglist_detail_view(request, pk):
    tenant = request.tenant
    pl = get_object_or_404(
        PackingList.objects.select_related('sales_order', 'pick_list', 'packed_by'),
        pk=pk, tenant=tenant,
    )
    pick_items = pl.pick_list.items.all().select_related('product', 'bin_location') if pl.pick_list else []

    context = {
        'pl': pl,
        'pick_items': pick_items,
    }
    return render(request, 'orders/packinglist_detail.html', context)


@login_required
def packinglist_edit_view(request, pk):
    tenant = request.tenant
    pl = get_object_or_404(PackingList, pk=pk, tenant=tenant)
    if pl.status != 'pending':
        messages.warning(request, 'Only pending packing lists can be edited.')
        return redirect('orders:packinglist_detail', pk=pl.pk)

    if request.method == 'POST':
        form = PackingListForm(request.POST, instance=pl, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Packing List "{pl.packing_number}" updated successfully.')
            return redirect('orders:packinglist_detail', pk=pl.pk)
    else:
        form = PackingListForm(instance=pl, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Packing List',
        'pl': pl,
    }
    return render(request, 'orders/packinglist_form.html', context)


@login_required
def packinglist_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:packinglist_list')
    pl = get_object_or_404(PackingList, pk=pk, tenant=tenant)
    if pl.status != 'pending':
        messages.warning(request, 'Only pending packing lists can be deleted.')
        return redirect('orders:packinglist_detail', pk=pl.pk)
    packing_number = pl.packing_number
    pl.delete()
    messages.success(request, f'Packing List "{packing_number}" deleted successfully.')
    return redirect('orders:packinglist_list')


@login_required
def packinglist_start_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:packinglist_detail', pk=pk)
    pl = get_object_or_404(PackingList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('in_progress'):
        messages.warning(request, f'Cannot start packing from "{pl.get_status_display()}" status.')
        return redirect('orders:packinglist_detail', pk=pl.pk)
    pl.status = 'in_progress'
    pl.save()
    messages.success(request, f'Packing List "{pl.packing_number}" started.')
    return redirect('orders:packinglist_detail', pk=pl.pk)


@login_required
def packinglist_complete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:packinglist_detail', pk=pk)
    pl = get_object_or_404(PackingList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('completed'):
        messages.warning(request, f'Cannot complete packing from "{pl.get_status_display()}" status.')
        return redirect('orders:packinglist_detail', pk=pl.pk)
    pl.status = 'completed'
    pl.packed_by = request.user
    pl.packed_at = timezone.now()
    pl.save()

    # Auto-progress SO to 'packed' if all packing lists are completed
    so = pl.sales_order
    if so and so.status == 'picked':
        all_completed = not so.packing_lists.exclude(status__in=['completed', 'cancelled']).exists()
        if all_completed:
            so.status = 'packed'
            so.save()

    messages.success(request, f'Packing List "{pl.packing_number}" completed.')
    return redirect('orders:packinglist_detail', pk=pl.pk)


@login_required
def packinglist_cancel_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:packinglist_detail', pk=pk)
    pl = get_object_or_404(PackingList, pk=pk, tenant=tenant)
    if not pl.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel packing from "{pl.get_status_display()}" status.')
        return redirect('orders:packinglist_detail', pk=pl.pk)
    pl.status = 'cancelled'
    pl.save()
    messages.success(request, f'Packing List "{pl.packing_number}" cancelled.')
    return redirect('orders:packinglist_detail', pk=pl.pk)


# ══════════════════════════════════════════════
# Shipment CRUD & Actions
# ══════════════════════════════════════════════

@login_required
def shipment_list_view(request):
    tenant = request.tenant
    queryset = Shipment.objects.filter(tenant=tenant).select_related(
        'sales_order', 'carrier', 'shipped_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(shipment_number__icontains=q)
            | Q(sales_order__order_number__icontains=q)
            | Q(tracking_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    carrier_id = request.GET.get('carrier', '')
    if carrier_id:
        queryset = queryset.filter(carrier_id=carrier_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    shipments = paginator.get_page(page_number)

    context = {
        'shipments': shipments,
        'q': q,
        'status_choices': Shipment.STATUS_CHOICES,
        'carriers': Carrier.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_carrier': carrier_id,
    }
    return render(request, 'orders/shipment_list.html', context)


@login_required
def shipment_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ShipmentForm(request.POST, tenant=tenant)
        if form.is_valid():
            sh = form.save(commit=False)
            sh.save()
            messages.success(request, f'Shipment "{sh.shipment_number}" created successfully.')
            return redirect('orders:shipment_detail', pk=sh.pk)
    else:
        form = ShipmentForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Shipment',
    }
    return render(request, 'orders/shipment_form.html', context)


@login_required
def shipment_detail_view(request, pk):
    tenant = request.tenant
    sh = get_object_or_404(
        Shipment.objects.select_related('sales_order', 'carrier', 'packing_list', 'shipped_by'),
        pk=pk, tenant=tenant,
    )
    tracking_events = sh.tracking_events.all()
    tracking_form = ShipmentTrackingForm()

    context = {
        'sh': sh,
        'tracking_events': tracking_events,
        'tracking_form': tracking_form,
    }
    return render(request, 'orders/shipment_detail.html', context)


@login_required
def shipment_edit_view(request, pk):
    tenant = request.tenant
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if sh.status != 'pending':
        messages.warning(request, 'Only pending shipments can be edited.')
        return redirect('orders:shipment_detail', pk=sh.pk)

    if request.method == 'POST':
        form = ShipmentForm(request.POST, instance=sh, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Shipment "{sh.shipment_number}" updated successfully.')
            return redirect('orders:shipment_detail', pk=sh.pk)
    else:
        form = ShipmentForm(instance=sh, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Shipment',
        'sh': sh,
    }
    return render(request, 'orders/shipment_form.html', context)


@login_required
def shipment_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_list')
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if sh.status != 'pending':
        messages.warning(request, 'Only pending shipments can be deleted.')
        return redirect('orders:shipment_detail', pk=sh.pk)
    shipment_number = sh.shipment_number
    sh.delete()
    messages.success(request, f'Shipment "{shipment_number}" deleted successfully.')
    return redirect('orders:shipment_list')


@login_required
def shipment_dispatch_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_detail', pk=pk)
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if not sh.can_transition_to('dispatched'):
        messages.warning(request, f'Cannot dispatch shipment in "{sh.get_status_display()}" status.')
        return redirect('orders:shipment_detail', pk=sh.pk)
    sh.status = 'dispatched'
    sh.shipped_date = timezone.now()
    sh.shipped_by = request.user
    sh.save()

    # Auto-progress SO to 'shipped'
    so = sh.sales_order
    if so and so.status in ('packed', 'in_fulfillment', 'picked'):
        so.status = 'shipped'
        so.save()

    messages.success(request, f'Shipment "{sh.shipment_number}" dispatched.')
    return redirect('orders:shipment_detail', pk=sh.pk)


@login_required
def shipment_in_transit_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_detail', pk=pk)
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if not sh.can_transition_to('in_transit'):
        messages.warning(request, f'Cannot mark as in-transit from "{sh.get_status_display()}" status.')
        return redirect('orders:shipment_detail', pk=sh.pk)
    sh.status = 'in_transit'
    sh.save()
    messages.success(request, f'Shipment "{sh.shipment_number}" marked as in transit.')
    return redirect('orders:shipment_detail', pk=sh.pk)


@login_required
def shipment_delivered_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_detail', pk=pk)
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if not sh.can_transition_to('delivered'):
        messages.warning(request, f'Cannot mark as delivered from "{sh.get_status_display()}" status.')
        return redirect('orders:shipment_detail', pk=sh.pk)
    sh.status = 'delivered'
    sh.actual_delivery_date = timezone.now().date()
    sh.save()

    # Auto-progress SO to 'delivered' and release allocated stock
    so = sh.sales_order
    if so and so.status == 'shipped':
        so.status = 'delivered'
        so.save()

        # Decrement on_hand and release allocated
        from inventory.models import StockLevel, InventoryReservation
        reservations = InventoryReservation.objects.filter(
            tenant=tenant, reference_type='sales_order', reference_number=so.order_number,
            status='confirmed',
        )
        for res in reservations:
            stock = StockLevel.objects.filter(
                tenant=tenant, product=res.product, warehouse=res.warehouse,
            ).first()
            if stock:
                stock.on_hand = max(stock.on_hand - res.quantity, 0)
                stock.allocated = max(stock.allocated - res.quantity, 0)
                stock.save()
            res.status = 'released'
            res.save()

    messages.success(request, f'Shipment "{sh.shipment_number}" delivered.')
    return redirect('orders:shipment_detail', pk=sh.pk)


@login_required
def shipment_cancel_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_detail', pk=pk)
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    if not sh.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel shipment in "{sh.get_status_display()}" status.')
        return redirect('orders:shipment_detail', pk=sh.pk)
    sh.status = 'cancelled'
    sh.save()
    messages.success(request, f'Shipment "{sh.shipment_number}" cancelled.')
    return redirect('orders:shipment_detail', pk=sh.pk)


@login_required
def shipment_add_tracking_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shipment_detail', pk=pk)
    sh = get_object_or_404(Shipment, pk=pk, tenant=tenant)
    form = ShipmentTrackingForm(request.POST)
    if form.is_valid():
        event = form.save(commit=False)
        event.tenant = tenant
        event.shipment = sh
        event.save()
        messages.success(request, 'Tracking event added successfully.')
    else:
        messages.error(request, 'Invalid tracking form. Please check the data.')
    return redirect('orders:shipment_detail', pk=sh.pk)


# ══════════════════════════════════════════════
# Wave Planning CRUD & Actions
# ══════════════════════════════════════════════

@login_required
def wave_list_view(request):
    tenant = request.tenant
    queryset = WavePlan.objects.filter(tenant=tenant).select_related('warehouse', 'created_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(wave_number__icontains=q)

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    waves = paginator.get_page(page_number)

    context = {
        'waves': waves,
        'q': q,
        'status_choices': WavePlan.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'orders/wave_list.html', context)


@login_required
def wave_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = WavePlanForm(request.POST, tenant=tenant)
        order_form = WaveOrderSelectionForm(request.POST, tenant=tenant)
        if form.is_valid():
            wave = form.save(commit=False)
            wave.created_by = request.user
            wave.save()
            # Add selected orders
            order_form = WaveOrderSelectionForm(request.POST, tenant=tenant, warehouse=wave.warehouse)
            if order_form.is_valid():
                for order in order_form.cleaned_data.get('orders', []):
                    WaveOrderAssignment.objects.create(
                        tenant=tenant,
                        wave_plan=wave,
                        sales_order=order,
                    )
            messages.success(request, f'Wave Plan "{wave.wave_number}" created successfully.')
            return redirect('orders:wave_detail', pk=wave.pk)
    else:
        form = WavePlanForm(tenant=tenant)
        order_form = WaveOrderSelectionForm(tenant=tenant)

    context = {
        'form': form,
        'order_form': order_form,
        'title': 'Create Wave Plan',
    }
    return render(request, 'orders/wave_form.html', context)


@login_required
def wave_detail_view(request, pk):
    tenant = request.tenant
    wave = get_object_or_404(
        WavePlan.objects.select_related('warehouse', 'created_by'),
        pk=pk, tenant=tenant,
    )
    assignments = wave.assignments.all().select_related('sales_order')
    pick_lists = wave.pick_lists.all().select_related('warehouse', 'assigned_to')

    context = {
        'wave': wave,
        'assignments': assignments,
        'pick_lists': pick_lists,
    }
    return render(request, 'orders/wave_detail.html', context)


@login_required
def wave_edit_view(request, pk):
    tenant = request.tenant
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if wave.status != 'draft':
        messages.warning(request, 'Only draft wave plans can be edited.')
        return redirect('orders:wave_detail', pk=wave.pk)

    if request.method == 'POST':
        form = WavePlanForm(request.POST, instance=wave, tenant=tenant)
        order_form = WaveOrderSelectionForm(request.POST, tenant=tenant, warehouse=wave.warehouse)
        if form.is_valid():
            form.save()
            if order_form.is_valid():
                # Sync orders
                wave.assignments.all().delete()
                for order in order_form.cleaned_data.get('orders', []):
                    WaveOrderAssignment.objects.create(
                        tenant=tenant,
                        wave_plan=wave,
                        sales_order=order,
                    )
            messages.success(request, f'Wave Plan "{wave.wave_number}" updated successfully.')
            return redirect('orders:wave_detail', pk=wave.pk)
    else:
        form = WavePlanForm(instance=wave, tenant=tenant)
        order_form = WaveOrderSelectionForm(
            tenant=tenant,
            warehouse=wave.warehouse,
            initial={'orders': wave.orders.all()},
        )

    context = {
        'form': form,
        'order_form': order_form,
        'title': 'Edit Wave Plan',
        'wave': wave,
    }
    return render(request, 'orders/wave_form.html', context)


@login_required
def wave_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_list')
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if wave.status != 'draft':
        messages.warning(request, 'Only draft wave plans can be deleted.')
        return redirect('orders:wave_detail', pk=wave.pk)
    wave_number = wave.wave_number
    wave.delete()
    messages.success(request, f'Wave Plan "{wave_number}" deleted successfully.')
    return redirect('orders:wave_list')


@login_required
def wave_release_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_detail', pk=pk)
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if not wave.can_transition_to('released'):
        messages.warning(request, f'Cannot release wave from "{wave.get_status_display()}" status.')
        return redirect('orders:wave_detail', pk=wave.pk)
    wave.status = 'released'
    wave.released_at = timezone.now()
    wave.save()
    messages.success(request, f'Wave Plan "{wave.wave_number}" released.')
    return redirect('orders:wave_detail', pk=wave.pk)


@login_required
def wave_start_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_detail', pk=pk)
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if not wave.can_transition_to('in_progress'):
        messages.warning(request, f'Cannot start wave from "{wave.get_status_display()}" status.')
        return redirect('orders:wave_detail', pk=wave.pk)
    wave.status = 'in_progress'
    wave.save()
    messages.success(request, f'Wave Plan "{wave.wave_number}" started.')
    return redirect('orders:wave_detail', pk=wave.pk)


@login_required
def wave_complete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_detail', pk=pk)
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if not wave.can_transition_to('completed'):
        messages.warning(request, f'Cannot complete wave from "{wave.get_status_display()}" status.')
        return redirect('orders:wave_detail', pk=wave.pk)
    wave.status = 'completed'
    wave.completed_at = timezone.now()
    wave.save()
    messages.success(request, f'Wave Plan "{wave.wave_number}" completed.')
    return redirect('orders:wave_detail', pk=wave.pk)


@login_required
def wave_cancel_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_detail', pk=pk)
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)
    if not wave.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel wave from "{wave.get_status_display()}" status.')
        return redirect('orders:wave_detail', pk=wave.pk)
    wave.status = 'cancelled'
    wave.save()
    messages.success(request, f'Wave Plan "{wave.wave_number}" cancelled.')
    return redirect('orders:wave_detail', pk=wave.pk)


@login_required
def wave_generate_picklists_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:wave_detail', pk=pk)
    wave = get_object_or_404(WavePlan, pk=pk, tenant=tenant)

    if wave.status not in ('released', 'in_progress'):
        messages.warning(request, 'Can only generate pick lists for released or in-progress waves.')
        return redirect('orders:wave_detail', pk=wave.pk)

    # Generate one pick list per order in the wave
    count = 0
    for assignment in wave.assignments.select_related('sales_order'):
        so = assignment.sales_order
        if so.status not in ('confirmed', 'in_fulfillment'):
            continue

        pick_list = PickList(tenant=tenant)
        pick_list.sales_order = so
        pick_list.wave_plan = wave
        pick_list.warehouse = wave.warehouse
        pick_list.created_by = request.user
        pick_list.save()

        for item in so.items.select_related('product'):
            PickListItem.objects.create(
                tenant=tenant,
                pick_list=pick_list,
                product=item.product,
                ordered_quantity=item.quantity,
            )

        if so.status == 'confirmed':
            so.status = 'in_fulfillment'
            so.save()
        count += 1

    if wave.status == 'released':
        wave.status = 'in_progress'
        wave.save()

    messages.success(request, f'{count} pick list(s) generated for wave {wave.wave_number}.')
    return redirect('orders:wave_detail', pk=wave.pk)


# ══════════════════════════════════════════════
# Carrier CRUD
# ══════════════════════════════════════════════

@login_required
def carrier_list_view(request):
    tenant = request.tenant
    queryset = Carrier.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(code__icontains=q)
        )

    active_filter = request.GET.get('active', '')
    if active_filter == 'active':
        queryset = queryset.filter(is_active=True)
    elif active_filter == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    carriers = paginator.get_page(page_number)

    context = {
        'carriers': carriers,
        'q': q,
        'current_active': active_filter,
    }
    return render(request, 'orders/carrier_list.html', context)


@login_required
def carrier_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = CarrierForm(request.POST, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Carrier "{form.instance.name}" created successfully.')
            return redirect('orders:carrier_detail', pk=form.instance.pk)
    else:
        form = CarrierForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Carrier',
    }
    return render(request, 'orders/carrier_form.html', context)


@login_required
def carrier_detail_view(request, pk):
    tenant = request.tenant
    carrier = get_object_or_404(Carrier, pk=pk, tenant=tenant)
    rates = carrier.rates.all()
    shipments = carrier.shipments.all().select_related('sales_order')[:10]

    context = {
        'carrier': carrier,
        'rates': rates,
        'shipments': shipments,
    }
    return render(request, 'orders/carrier_detail.html', context)


@login_required
def carrier_edit_view(request, pk):
    tenant = request.tenant
    carrier = get_object_or_404(Carrier, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = CarrierForm(request.POST, instance=carrier, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Carrier "{carrier.name}" updated successfully.')
            return redirect('orders:carrier_detail', pk=carrier.pk)
    else:
        form = CarrierForm(instance=carrier, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Carrier',
        'carrier': carrier,
    }
    return render(request, 'orders/carrier_form.html', context)


@login_required
def carrier_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:carrier_list')
    carrier = get_object_or_404(Carrier, pk=pk, tenant=tenant)
    name = carrier.name
    carrier.delete()
    messages.success(request, f'Carrier "{name}" deleted successfully.')
    return redirect('orders:carrier_list')


# ══════════════════════════════════════════════
# Shipping Rate CRUD
# ══════════════════════════════════════════════

@login_required
def shippingrate_list_view(request):
    tenant = request.tenant
    queryset = ShippingRate.objects.filter(tenant=tenant).select_related('carrier')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(carrier__name__icontains=q) | Q(service_level__icontains=q)
        )

    carrier_id = request.GET.get('carrier', '')
    if carrier_id:
        queryset = queryset.filter(carrier_id=carrier_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    rates = paginator.get_page(page_number)

    context = {
        'rates': rates,
        'q': q,
        'carriers': Carrier.objects.filter(tenant=tenant, is_active=True),
        'current_carrier': carrier_id,
    }
    return render(request, 'orders/shippingrate_list.html', context)


@login_required
def shippingrate_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ShippingRateForm(request.POST, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shipping rate created successfully.')
            return redirect('orders:shippingrate_list')
    else:
        form = ShippingRateForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Shipping Rate',
    }
    return render(request, 'orders/shippingrate_form.html', context)


@login_required
def shippingrate_edit_view(request, pk):
    tenant = request.tenant
    rate = get_object_or_404(ShippingRate, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ShippingRateForm(request.POST, instance=rate, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shipping rate updated successfully.')
            return redirect('orders:shippingrate_list')
    else:
        form = ShippingRateForm(instance=rate, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Shipping Rate',
        'rate': rate,
    }
    return render(request, 'orders/shippingrate_form.html', context)


@login_required
def shippingrate_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('orders:shippingrate_list')
    rate = get_object_or_404(ShippingRate, pk=pk, tenant=tenant)
    rate.delete()
    messages.success(request, 'Shipping rate deleted successfully.')
    return redirect('orders:shippingrate_list')
