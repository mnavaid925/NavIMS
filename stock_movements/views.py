from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import Product
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
# Helpers
# ──────────────────────────────────────────────

def _parse_transfer_items(request, tenant):
    """
    D-01: tenant-scope every product reference posted via the parallel item
    arrays. Returns (items, errors) where each item is a dict ready for
    StockTransferItem.objects.create(...) and errors is a list of human-readable
    messages. Skips empty rows.
    """
    product_ids = request.POST.getlist('item_product')
    quantities = request.POST.getlist('item_quantity')
    notes_list = request.POST.getlist('item_notes')

    items = []
    errors = []
    valid_pks = set(
        Product.objects.filter(tenant=tenant, pk__in=[
            int(pid) for pid in product_ids if pid and pid.isdigit()
        ]).values_list('pk', flat=True)
    )

    for i, raw_pid in enumerate(product_ids):
        raw_qty = quantities[i] if i < len(quantities) else ''
        if not raw_pid and not raw_qty:
            continue
        if not raw_pid or not raw_qty:
            errors.append(f'Row {i + 1}: product and quantity are both required.')
            continue
        try:
            pid = int(raw_pid)
            qty = int(raw_qty)
        except (TypeError, ValueError):
            errors.append(f'Row {i + 1}: product and quantity must be numeric.')
            continue
        if qty < 1:
            errors.append(f'Row {i + 1}: quantity must be at least 1.')
            continue
        if pid not in valid_pks:
            errors.append(f'Row {i + 1}: product does not belong to your tenant.')
            continue
        items.append({
            'product_id': pid,
            'quantity': qty,
            'notes': notes_list[i] if i < len(notes_list) else '',
        })
    return items, errors


def _resolve_initial_status(tenant, item_count):
    """
    D-09: consult the smallest matching active TransferApprovalRule. If a rule
    matches and requires_approval is True, start the transfer in
    `pending_approval`; otherwise leave it as `draft`.
    """
    rule = (
        TransferApprovalRule.objects
        .filter(tenant=tenant, is_active=True, min_items__lte=item_count)
        .filter(Q(max_items__isnull=True) | Q(max_items__gte=item_count))
        .order_by('min_items')
        .first()
    )
    if rule and rule.requires_approval:
        return 'pending_approval'
    return 'draft'


# ──────────────────────────────────────────────
# Sub-module 1 & 2: Stock Transfers
# ──────────────────────────────────────────────

@login_required
def transfer_list_view(request):
    tenant = request.tenant
    queryset = (
        StockTransfer.objects.filter(tenant=tenant)
        .select_related('source_warehouse', 'destination_warehouse', 'requested_by')
        .annotate(_items_count=Count('items'))
        .order_by('-created_at')
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
        # D-01: parse + tenant-validate item rows BEFORE saving the transfer.
        items, item_errors = _parse_transfer_items(request, tenant)
        if form.is_valid() and not item_errors and items:
            with transaction.atomic():
                transfer = form.save(commit=False)
                transfer.tenant = tenant
                transfer.requested_by = request.user
                # D-09: consult approval rules to choose initial status.
                transfer.status = _resolve_initial_status(tenant, len(items))
                transfer.save()
                for it in items:
                    StockTransferItem.objects.create(
                        tenant=tenant, transfer=transfer, **it,
                    )
            messages.success(request, f'Transfer {transfer.transfer_number} created successfully.')
            return redirect('stock_movements:transfer_detail', pk=transfer.pk)
        for err in item_errors:
            messages.error(request, err)
        if form.is_valid() and not items and not item_errors:
            messages.error(request, 'Add at least one item with a product and quantity.')
        item_form = StockTransferItemForm(tenant=tenant, prefix='item')
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
        items, item_errors = _parse_transfer_items(request, tenant)
        if form.is_valid() and not item_errors and items:
            with transaction.atomic():
                form.save()
                transfer.items.all().delete()
                for it in items:
                    StockTransferItem.objects.create(
                        tenant=tenant, transfer=transfer, **it,
                    )
            messages.success(request, f'Transfer {transfer.transfer_number} updated successfully.')
            return redirect('stock_movements:transfer_detail', pk=transfer.pk)
        for err in item_errors:
            messages.error(request, err)
        if form.is_valid() and not items and not item_errors:
            messages.error(request, 'Add at least one item with a product and quantity.')
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

    # D-05: requester cannot approve their own transfer.
    if new_status == 'approved' and transfer.requested_by_id == request.user.id:
        messages.error(request, 'You cannot approve a transfer you requested.')
        return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    # D-03: refuse to complete when any item is short-received. Previously the
    # code force-overwrote received_quantity = quantity, silently destroying
    # partial-receipt data. Direct the user through the receive flow instead.
    if new_status == 'completed':
        short_items = [
            it for it in transfer.items.all()
            if it.received_quantity < it.quantity
        ]
        if short_items:
            messages.error(
                request,
                f'Cannot complete: {len(short_items)} item(s) are still short-received. '
                'Use the Receive form to record the remaining quantities.',
            )
            return redirect('stock_movements:transfer_detail', pk=transfer.pk)

    transfer.status = new_status
    if new_status == 'approved':
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
    elif new_status == 'in_transit':
        transfer.shipped_at = timezone.now()
    elif new_status == 'completed':
        transfer.completed_at = timezone.now()
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
        # D-06: validate every input before persisting; surface field-level
        # errors instead of silently swallowing ValueError or out-of-range qty.
        items = list(transfer.items.select_related('product'))
        errors = {}
        parsed = {}
        for item in items:
            raw = request.POST.get(f'received_qty_{item.pk}', '').strip()
            if raw == '':
                continue
            try:
                qty = int(raw)
            except (ValueError, TypeError):
                errors[item.pk] = f'"{raw}" is not a whole number.'
                continue
            if qty < 0:
                errors[item.pk] = 'Received quantity cannot be negative.'
                continue
            if qty > item.quantity:
                errors[item.pk] = (
                    f'Received quantity ({qty}) exceeds transfer quantity ({item.quantity}).'
                )
                continue
            parsed[item.pk] = qty

        if errors:
            for msg in errors.values():
                messages.error(request, msg)
            context = {'transfer': transfer, 'items': items, 'errors': errors}
            return render(request, 'stock_movements/transfer_receive_form.html', context)

        with transaction.atomic():
            for item in items:
                if item.pk in parsed:
                    item.received_quantity = parsed[item.pk]
                    item.save()

            all_received = all(it.received_quantity >= it.quantity for it in items)
            if all_received:
                transfer.status = 'completed'
                transfer.completed_at = timezone.now()
                transfer.save()
                messages.success(
                    request, f'Transfer {transfer.transfer_number} fully received and completed.',
                )
            else:
                messages.success(
                    request, f'Received quantities updated for {transfer.transfer_number}.',
                )
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

    # D-05: requester cannot approve their own transfer (segregation of duties).
    if transfer.requested_by_id == request.user.id:
        messages.error(request, 'You cannot approve a transfer you requested.')
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

    # D-07: select_related + annotated items count to avoid N+1 when the
    # template iterates and dereferences source/destination/requested_by and
    # calls `total_items` for each row.
    related_transfers = (
        StockTransfer.objects
        .filter(
            tenant=tenant,
            source_warehouse=route.source_warehouse,
            destination_warehouse=route.destination_warehouse,
        )
        .select_related('source_warehouse', 'destination_warehouse', 'requested_by')
        .annotate(_items_count=Count('items'))
        .order_by('-created_at')[:10]
    )

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
