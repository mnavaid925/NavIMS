from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from warehousing.models import Warehouse
from .models import (
    StockTransfer, StockTransferItem,
    TransferApprovalRule, TransferApproval,
    TransferRoute,
)
from .forms import (
    StockTransferForm, StockTransferItemForm,
    TransferApprovalRuleForm, TransferApprovalForm,
    TransferRouteForm,
)


# ──────────────────────────────────────────────
# Sub-module 1 & 2: Stock Transfers
# ──────────────────────────────────────────────

@login_required
def transfer_list_view(request):
    tenant = request.tenant
    queryset = StockTransfer.objects.filter(tenant=tenant).select_related(
        'source_warehouse', 'destination_warehouse', 'requested_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(transfer_number__icontains=q)
            | Q(source_warehouse__name__icontains=q)
            | Q(destination_warehouse__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    transfer_type = request.GET.get('type', '')
    if transfer_type:
        queryset = queryset.filter(transfer_type=transfer_type)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(
            Q(source_warehouse_id=warehouse_id) | Q(destination_warehouse_id=warehouse_id)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    transfers = paginator.get_page(page_number)

    warehouses = Warehouse.objects.filter(tenant=tenant, is_active=True)

    context = {
        'transfers': transfers,
        'q': q,
        'status_choices': StockTransfer.STATUS_CHOICES,
        'type_choices': StockTransfer.TRANSFER_TYPE_CHOICES,
        'current_status': status,
        'current_type': transfer_type,
        'warehouses': warehouses,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'stock_movements/transfer_list.html', context)


@login_required
def transfer_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = StockTransferForm(request.POST, tenant=tenant)
        item_form = StockTransferItemForm(request.POST, tenant=tenant, prefix='item')
        if form.is_valid():
            transfer = form.save(commit=False)
            transfer.tenant = tenant
            transfer.requested_by = request.user
            transfer.save()

            # Handle multiple items from dynamic form
            product_ids = request.POST.getlist('item_product')
            quantities = request.POST.getlist('item_quantity')
            item_notes_list = request.POST.getlist('item_notes')

            for i in range(len(product_ids)):
                if product_ids[i] and quantities[i]:
                    StockTransferItem.objects.create(
                        tenant=tenant,
                        transfer=transfer,
                        product_id=int(product_ids[i]),
                        quantity=int(quantities[i]),
                        notes=item_notes_list[i] if i < len(item_notes_list) else '',
                    )

            messages.success(request, f'Transfer {transfer.transfer_number} created successfully.')
            return redirect('stock_movements:transfer_detail', pk=transfer.pk)
    else:
        form = StockTransferForm(tenant=tenant)
        item_form = StockTransferItemForm(tenant=tenant, prefix='item')

    context = {
        'form': form,
        'item_form': item_form,
        'title': 'Create Transfer',
    }
    return render(request, 'stock_movements/transfer_form.html', context)


@login_required
def transfer_detail_view(request, pk):
    tenant = request.tenant
    transfer = get_object_or_404(
        StockTransfer, pk=pk, tenant=tenant,
    )
    items = transfer.items.select_related('product')
    approvals = transfer.approvals.select_related('approved_by')
    routes = TransferRoute.objects.filter(
        tenant=tenant,
        source_warehouse=transfer.source_warehouse,
        destination_warehouse=transfer.destination_warehouse,
        is_active=True,
    ) if transfer.destination_warehouse else TransferRoute.objects.none()

    context = {
        'transfer': transfer,
        'items': items,
        'approvals': approvals,
        'routes': routes,
    }
    return render(request, 'stock_movements/transfer_detail.html', context)


@login_required
def transfer_edit_view(request, pk):
    tenant = request.tenant
    transfer = get_object_or_404(StockTransfer, pk=pk, tenant=tenant)

    if transfer.status not in ('draft', 'pending_approval'):
        messages.warning(request, 'Only draft or pending transfers can be edited.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    if request.method == 'POST':
        form = StockTransferForm(request.POST, instance=transfer, tenant=tenant)
        if form.is_valid():
            form.save()

            # Clear and re-add items
            transfer.items.all().delete()
            product_ids = request.POST.getlist('item_product')
            quantities = request.POST.getlist('item_quantity')
            item_notes_list = request.POST.getlist('item_notes')

            for i in range(len(product_ids)):
                if product_ids[i] and quantities[i]:
                    StockTransferItem.objects.create(
                        tenant=tenant,
                        transfer=transfer,
                        product_id=int(product_ids[i]),
                        quantity=int(quantities[i]),
                        notes=item_notes_list[i] if i < len(item_notes_list) else '',
                    )

            messages.success(request, f'Transfer {transfer.transfer_number} updated successfully.')
            return redirect('stock_movements:transfer_detail', pk=transfer.pk)
    else:
        form = StockTransferForm(instance=transfer, tenant=tenant)

    item_form = StockTransferItemForm(tenant=tenant, prefix='item')
    items = transfer.items.select_related('product')

    context = {
        'form': form,
        'item_form': item_form,
        'transfer': transfer,
        'items': items,
        'title': 'Edit Transfer',
    }
    return render(request, 'stock_movements/transfer_form.html', context)


@login_required
def transfer_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('stock_movements:transfer_list')

    tenant = request.tenant
    transfer = get_object_or_404(StockTransfer, pk=pk, tenant=tenant)

    if transfer.status not in ('draft', 'cancelled'):
        messages.warning(request, 'Only draft or cancelled transfers can be deleted.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    transfer.delete()
    messages.success(request, 'Transfer deleted successfully.')
    return redirect('stock_movements:transfer_list')


@login_required
def transfer_transition_view(request, pk, new_status):
    if request.method != 'POST':
        return redirect('stock_movements:transfer_list')

    tenant = request.tenant
    transfer = get_object_or_404(StockTransfer, pk=pk, tenant=tenant)

    if not transfer.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from {transfer.get_status_display()} to {new_status}.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    old_status = transfer.status
    transfer.status = new_status

    if new_status == 'approved':
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
    elif new_status == 'in_transit':
        transfer.shipped_at = timezone.now()
    elif new_status == 'completed':
        transfer.completed_at = timezone.now()
        # Mark all items as fully received if not already
        for item in transfer.items.all():
            if item.received_quantity < item.quantity:
                item.received_quantity = item.quantity
                item.save()

    transfer.save()

    messages.success(request, f'Transfer status changed to {transfer.get_status_display()}.')
    return redirect('stock_movements:transfer_detail', pk=transfer.pk)


@login_required
def transfer_receive_view(request, pk):
    tenant = request.tenant
    transfer = get_object_or_404(StockTransfer, pk=pk, tenant=tenant)

    if transfer.status != 'in_transit':
        messages.warning(request, 'Only in-transit transfers can be received.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    if request.method == 'POST':
        items = transfer.items.all()
        for item in items:
            qty_key = f'received_qty_{item.pk}'
            received = request.POST.get(qty_key, '')
            if received:
                try:
                    received_qty = int(received)
                    if 0 <= received_qty <= item.quantity:
                        item.received_quantity = received_qty
                        item.save()
                except (ValueError, TypeError):
                    pass

        # Check if all items fully received
        all_received = all(
            item.received_quantity >= item.quantity
            for item in transfer.items.all()
        )
        if all_received:
            transfer.status = 'completed'
            transfer.completed_at = timezone.now()
            transfer.save()
            messages.success(request, f'Transfer {transfer.transfer_number} fully received and completed.')
        else:
            messages.success(request, f'Received quantities updated for {transfer.transfer_number}.')

        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    items = transfer.items.select_related('product')
    context = {
        'transfer': transfer,
        'items': items,
    }
    return render(request, 'stock_movements/transfer_receive_form.html', context)


# ──────────────────────────────────────────────
# Sub-module 3: Transfer Approval Workflow
# ──────────────────────────────────────────────

@login_required
def approval_rule_list_view(request):
    tenant = request.tenant
    queryset = TransferApprovalRule.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(name__icontains=q)

    active = request.GET.get('active', '')
    if active == 'yes':
        queryset = queryset.filter(is_active=True)
    elif active == 'no':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    rules = paginator.get_page(page_number)

    context = {
        'rules': rules,
        'q': q,
        'current_active': active,
    }
    return render(request, 'stock_movements/approval_rule_list.html', context)


@login_required
def approval_rule_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = TransferApprovalRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.tenant = tenant
            rule.save()
            messages.success(request, f'Approval rule "{rule.name}" created successfully.')
            return redirect('stock_movements:approval_rule_list')
    else:
        form = TransferApprovalRuleForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Approval Rule',
    }
    return render(request, 'stock_movements/approval_rule_form.html', context)


@login_required
def approval_rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(TransferApprovalRule, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = TransferApprovalRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Approval rule "{rule.name}" updated successfully.')
            return redirect('stock_movements:approval_rule_list')
    else:
        form = TransferApprovalRuleForm(instance=rule, tenant=tenant)

    context = {
        'form': form,
        'rule': rule,
        'title': 'Edit Approval Rule',
    }
    return render(request, 'stock_movements/approval_rule_form.html', context)


@login_required
def approval_rule_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('stock_movements:approval_rule_list')

    tenant = request.tenant
    rule = get_object_or_404(TransferApprovalRule, pk=pk, tenant=tenant)
    rule.delete()
    messages.success(request, 'Approval rule deleted successfully.')
    return redirect('stock_movements:approval_rule_list')


@login_required
def pending_approval_list_view(request):
    tenant = request.tenant
    queryset = StockTransfer.objects.filter(
        tenant=tenant,
        status='pending_approval',
    ).select_related('source_warehouse', 'destination_warehouse', 'requested_by')

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    transfers = paginator.get_page(page_number)

    context = {
        'transfers': transfers,
    }
    return render(request, 'stock_movements/pending_approval_list.html', context)


@login_required
def transfer_approve_view(request, pk):
    tenant = request.tenant
    transfer = get_object_or_404(StockTransfer, pk=pk, tenant=tenant)

    if transfer.status != 'pending_approval':
        messages.warning(request, 'This transfer is not pending approval.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    if request.method == 'POST':
        form = TransferApprovalForm(request.POST)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.tenant = tenant
            approval.transfer = transfer
            approval.approved_by = request.user
            approval.save()

            if approval.decision == 'approved':
                transfer.status = 'approved'
                transfer.approved_by = request.user
                transfer.approved_at = timezone.now()
                transfer.save()
                messages.success(request, f'Transfer {transfer.transfer_number} approved.')
            else:
                transfer.status = 'cancelled'
                transfer.save()
                messages.warning(request, f'Transfer {transfer.transfer_number} rejected.')

            return redirect('stock_movements:transfer_detail', pk=transfer.pk)
    else:
        form = TransferApprovalForm()

    items = transfer.items.select_related('product')

    context = {
        'form': form,
        'transfer': transfer,
        'items': items,
    }
    return render(request, 'stock_movements/transfer_approval_form.html', context)


# ──────────────────────────────────────────────
# Sub-module 4: Transfer Routing
# ──────────────────────────────────────────────

@login_required
def route_list_view(request):
    tenant = request.tenant
    queryset = TransferRoute.objects.filter(tenant=tenant).select_related(
        'source_warehouse', 'destination_warehouse',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(source_warehouse__name__icontains=q)
            | Q(destination_warehouse__name__icontains=q)
        )

    method = request.GET.get('method', '')
    if method:
        queryset = queryset.filter(transit_method=method)

    active = request.GET.get('active', '')
    if active == 'yes':
        queryset = queryset.filter(is_active=True)
    elif active == 'no':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    routes = paginator.get_page(page_number)

    context = {
        'routes': routes,
        'q': q,
        'method_choices': TransferRoute.TRANSIT_METHOD_CHOICES,
        'current_method': method,
        'current_active': active,
    }
    return render(request, 'stock_movements/route_list.html', context)


@login_required
def route_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = TransferRouteForm(request.POST, tenant=tenant)
        if form.is_valid():
            route = form.save(commit=False)
            route.tenant = tenant
            route.save()
            messages.success(request, f'Route "{route.name}" created successfully.')
            return redirect('stock_movements:route_detail', pk=route.pk)
    else:
        form = TransferRouteForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Transfer Route',
    }
    return render(request, 'stock_movements/route_form.html', context)


@login_required
def route_detail_view(request, pk):
    tenant = request.tenant
    route = get_object_or_404(TransferRoute, pk=pk, tenant=tenant)

    # Find transfers that used this route
    related_transfers = StockTransfer.objects.filter(
        tenant=tenant,
        source_warehouse=route.source_warehouse,
        destination_warehouse=route.destination_warehouse,
    ).order_by('-created_at')[:10]

    context = {
        'route': route,
        'related_transfers': related_transfers,
    }
    return render(request, 'stock_movements/route_detail.html', context)


@login_required
def route_edit_view(request, pk):
    tenant = request.tenant
    route = get_object_or_404(TransferRoute, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = TransferRouteForm(request.POST, instance=route, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Route "{route.name}" updated successfully.')
            return redirect('stock_movements:route_detail', pk=route.pk)
    else:
        form = TransferRouteForm(instance=route, tenant=tenant)

    context = {
        'form': form,
        'route': route,
        'title': 'Edit Transfer Route',
    }
    return render(request, 'stock_movements/route_form.html', context)


@login_required
def route_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('stock_movements:route_list')

    tenant = request.tenant
    route = get_object_or_404(TransferRoute, pk=pk, tenant=tenant)
    route.delete()
    messages.success(request, 'Transfer route deleted successfully.')
    return redirect('stock_movements:route_list')
