from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.utils import timezone

from catalog.models import Product
from warehousing.models import Warehouse, Bin
from orders.models import SalesOrder
from inventory.models import StockAdjustment, StockLevel
from .models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)
from .forms import (
    ReturnAuthorizationForm, ReturnAuthorizationItemFormSet,
    ReturnInspectionForm, ReturnInspectionItemFormSet,
    DispositionForm, DispositionItemFormSet,
    RefundCreditForm,
)


# ══════════════════════════════════════════════
# Return Authorization (RMA) CRUD
# ══════════════════════════════════════════════

@login_required
def rma_list_view(request):
    tenant = request.tenant
    queryset = ReturnAuthorization.objects.filter(tenant=tenant).select_related(
        'sales_order', 'warehouse', 'created_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(rma_number__icontains=q) | Q(customer_name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    reason = request.GET.get('reason', '')
    if reason:
        queryset = queryset.filter(reason=reason)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    rmas = paginator.get_page(page_number)

    context = {
        'rmas': rmas,
        'q': q,
        'status_choices': ReturnAuthorization.STATUS_CHOICES,
        'reason_choices': ReturnAuthorization.REASON_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_reason': reason,
        'current_warehouse': warehouse_id,
    }
    return render(request, 'returns/rma_list.html', context)


@login_required
def rma_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ReturnAuthorizationForm(request.POST, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            rma = form.save(commit=False)
            rma.created_by = request.user
            rma.save()
            formset.instance = rma
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'RMA "{rma.rma_number}" created successfully.')
            return redirect('returns:rma_detail', pk=rma.pk)
    else:
        form = ReturnAuthorizationForm(tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    return render(request, 'returns/rma_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create RMA',
    })


@login_required
def rma_edit_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = ReturnAuthorizationForm(request.POST, instance=rma, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(request.POST, instance=rma, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'RMA "{rma.rma_number}" updated successfully.')
            return redirect('returns:rma_detail', pk=rma.pk)
    else:
        form = ReturnAuthorizationForm(instance=rma, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(instance=rma, prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    return render(request, 'returns/rma_form.html', {
        'form': form,
        'formset': formset,
        'rma': rma,
        'title': f'Edit RMA {rma.rma_number}',
    })


@login_required
def rma_detail_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(
        ReturnAuthorization.objects.select_related('sales_order', 'warehouse', 'created_by', 'approved_by'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'returns/rma_detail.html', {
        'rma': rma,
        'items': rma.items.select_related('product').all(),
        'inspections': rma.inspections.all(),
        'dispositions': rma.dispositions.all(),
        'refunds': rma.refunds.all(),
    })


@login_required
def rma_delete_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = rma.rma_number
        rma.delete()
        messages.success(request, f'RMA "{num}" deleted.')
        return redirect('returns:rma_list')
    return redirect('returns:rma_list')


@login_required
def rma_submit_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('pending'):
        rma.status = 'pending'
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" submitted for approval.')
    else:
        messages.error(request, 'Cannot submit RMA in current status.')
    return redirect('returns:rma_detail', pk=pk)


@login_required
def rma_approve_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('approved'):
        rma.status = 'approved'
        rma.approved_by = request.user
        rma.approved_at = timezone.now()
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" approved.')
    else:
        messages.error(request, 'Cannot approve RMA in current status.')
    return redirect('returns:rma_detail', pk=pk)


@login_required
def rma_reject_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('rejected'):
        rma.status = 'rejected'
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" rejected.')
    else:
        messages.error(request, 'Cannot reject RMA in current status.')
    return redirect('returns:rma_detail', pk=pk)


@login_required
def rma_receive_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('received'):
        rma.status = 'received'
        rma.received_at = timezone.now()
        for item in rma.items.all():
            if item.qty_received == 0:
                item.qty_received = item.qty_requested
                item.save()
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" marked as received.')
    else:
        messages.error(request, 'Cannot mark RMA as received in current status.')
    return redirect('returns:rma_detail', pk=pk)


@login_required
def rma_close_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('closed'):
        rma.status = 'closed'
        rma.closed_at = timezone.now()
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" closed.')
    else:
        messages.error(request, 'Cannot close RMA in current status.')
    return redirect('returns:rma_detail', pk=pk)


@login_required
def rma_cancel_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant)
    if rma.can_transition_to('cancelled'):
        rma.status = 'cancelled'
        rma.save()
        messages.success(request, f'RMA "{rma.rma_number}" cancelled.')
    else:
        messages.error(request, 'Cannot cancel RMA in current status.')
    return redirect('returns:rma_detail', pk=pk)


# ══════════════════════════════════════════════
# Return Inspection CRUD
# ══════════════════════════════════════════════

@login_required
def inspection_list_view(request):
    tenant = request.tenant
    queryset = ReturnInspection.objects.filter(tenant=tenant).select_related('rma', 'inspector')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(inspection_number__icontains=q) | Q(rma__rma_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    result = request.GET.get('result', '')
    if result:
        queryset = queryset.filter(overall_result=result)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    inspections = paginator.get_page(page_number)

    return render(request, 'returns/inspection_list.html', {
        'inspections': inspections,
        'q': q,
        'status_choices': ReturnInspection.STATUS_CHOICES,
        'result_choices': ReturnInspection.RESULT_CHOICES,
        'current_status': status,
        'current_result': result,
    })


@login_required
def inspection_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ReturnInspectionForm(request.POST, tenant=tenant)
        formset = ReturnInspectionItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            insp = form.save()
            formset.instance = insp
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Inspection "{insp.inspection_number}" created.')
            return redirect('returns:inspection_detail', pk=insp.pk)
    else:
        form = ReturnInspectionForm(tenant=tenant)
        formset = ReturnInspectionItemFormSet(prefix='items')

    rma_items = ReturnAuthorizationItem.objects.filter(tenant=tenant)
    for f in formset.forms:
        f.fields['rma_item'].queryset = rma_items
        f.fields['rma_item'].empty_label = '— Select Return Item —'

    return render(request, 'returns/inspection_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Inspection',
    })


@login_required
def inspection_edit_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = ReturnInspectionForm(request.POST, instance=insp, tenant=tenant)
        formset = ReturnInspectionItemFormSet(request.POST, instance=insp, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Inspection "{insp.inspection_number}" updated.')
            return redirect('returns:inspection_detail', pk=insp.pk)
    else:
        form = ReturnInspectionForm(instance=insp, tenant=tenant)
        formset = ReturnInspectionItemFormSet(instance=insp, prefix='items')

    rma_items = ReturnAuthorizationItem.objects.filter(tenant=tenant)
    for f in formset.forms:
        f.fields['rma_item'].queryset = rma_items
        f.fields['rma_item'].empty_label = '— Select Return Item —'

    return render(request, 'returns/inspection_form.html', {
        'form': form,
        'formset': formset,
        'inspection': insp,
        'title': f'Edit Inspection {insp.inspection_number}',
    })


@login_required
def inspection_detail_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(
        ReturnInspection.objects.select_related('rma', 'inspector'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'returns/inspection_detail.html', {
        'inspection': insp,
        'items': insp.items.select_related('rma_item__product').all(),
    })


@login_required
def inspection_delete_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = insp.inspection_number
        insp.delete()
        messages.success(request, f'Inspection "{num}" deleted.')
        return redirect('returns:inspection_list')
    return redirect('returns:inspection_list')


@login_required
def inspection_start_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant)
    if insp.can_transition_to('in_progress'):
        insp.status = 'in_progress'
        insp.started_at = timezone.now()
        insp.save()
        messages.success(request, 'Inspection started.')
    else:
        messages.error(request, 'Cannot start inspection in current status.')
    return redirect('returns:inspection_detail', pk=pk)


@login_required
def inspection_complete_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant)
    if insp.can_transition_to('completed'):
        insp.status = 'completed'
        insp.completed_at = timezone.now()
        if not insp.inspected_date:
            insp.inspected_date = timezone.now().date()
        insp.save()
        messages.success(request, 'Inspection completed.')
    else:
        messages.error(request, 'Cannot complete inspection in current status.')
    return redirect('returns:inspection_detail', pk=pk)


# ══════════════════════════════════════════════
# Disposition CRUD
# ══════════════════════════════════════════════

@login_required
def disposition_list_view(request):
    tenant = request.tenant
    queryset = Disposition.objects.filter(tenant=tenant).select_related('rma', 'warehouse', 'processed_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(disposition_number__icontains=q) | Q(rma__rma_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    decision = request.GET.get('decision', '')
    if decision:
        queryset = queryset.filter(decision=decision)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    dispositions = paginator.get_page(page_number)

    return render(request, 'returns/disposition_list.html', {
        'dispositions': dispositions,
        'q': q,
        'status_choices': Disposition.STATUS_CHOICES,
        'decision_choices': Disposition.DECISION_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_decision': decision,
        'current_warehouse': warehouse_id,
    })


@login_required
def disposition_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = DispositionForm(request.POST, tenant=tenant)
        formset = DispositionItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            disp = form.save()
            formset.instance = disp
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Disposition "{disp.disposition_number}" created.')
            return redirect('returns:disposition_detail', pk=disp.pk)
    else:
        form = DispositionForm(tenant=tenant)
        formset = DispositionItemFormSet(prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    bins = Bin.objects.filter(tenant=tenant, is_active=True)
    inspection_items = ReturnInspectionItem.objects.filter(tenant=tenant)
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'
        f.fields['destination_bin'].queryset = bins
        f.fields['destination_bin'].empty_label = '— Select Bin (optional) —'
        f.fields['inspection_item'].queryset = inspection_items
        f.fields['inspection_item'].empty_label = '— Select Inspection Item —'

    return render(request, 'returns/disposition_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Disposition',
    })


@login_required
def disposition_edit_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = DispositionForm(request.POST, instance=disp, tenant=tenant)
        formset = DispositionItemFormSet(request.POST, instance=disp, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'Disposition "{disp.disposition_number}" updated.')
            return redirect('returns:disposition_detail', pk=disp.pk)
    else:
        form = DispositionForm(instance=disp, tenant=tenant)
        formset = DispositionItemFormSet(instance=disp, prefix='items')

    products = Product.objects.filter(tenant=tenant, status='active')
    bins = Bin.objects.filter(tenant=tenant, is_active=True)
    inspection_items = ReturnInspectionItem.objects.filter(tenant=tenant)
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'
        f.fields['destination_bin'].queryset = bins
        f.fields['destination_bin'].empty_label = '— Select Bin (optional) —'
        f.fields['inspection_item'].queryset = inspection_items
        f.fields['inspection_item'].empty_label = '— Select Inspection Item —'

    return render(request, 'returns/disposition_form.html', {
        'form': form,
        'formset': formset,
        'disposition': disp,
        'title': f'Edit Disposition {disp.disposition_number}',
    })


@login_required
def disposition_detail_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(
        Disposition.objects.select_related('rma', 'warehouse', 'inspection', 'processed_by'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'returns/disposition_detail.html', {
        'disposition': disp,
        'items': disp.items.select_related('product', 'destination_bin').all(),
    })


@login_required
def disposition_delete_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = disp.disposition_number
        disp.delete()
        messages.success(request, f'Disposition "{num}" deleted.')
        return redirect('returns:disposition_list')
    return redirect('returns:disposition_list')


@login_required
def disposition_process_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant)
    if not disp.can_transition_to('processed'):
        messages.error(request, 'Cannot process disposition in current status.')
        return redirect('returns:disposition_detail', pk=pk)

    if disp.decision == 'restock':
        for item in disp.items.select_related('product').all():
            if item.qty <= 0:
                continue
            stock, _ = StockLevel.objects.get_or_create(
                tenant=tenant,
                product=item.product,
                warehouse=disp.warehouse,
                defaults={'on_hand': 0, 'allocated': 0, 'on_order': 0},
            )
            StockAdjustment.objects.create(
                tenant=tenant,
                stock_level=stock,
                adjustment_type='increase',
                reason='return',
                quantity=item.qty,
                notes=f'Restock from RMA {disp.rma.rma_number} — Disposition {disp.disposition_number}',
                adjusted_by=request.user,
            )
            stock.on_hand += item.qty
            stock.save()
    elif disp.decision == 'scrap':
        for item in disp.items.select_related('product').all():
            if item.qty <= 0:
                continue
            stock = StockLevel.objects.filter(
                tenant=tenant, product=item.product, warehouse=disp.warehouse,
            ).first()
            if not stock:
                continue
            StockAdjustment.objects.create(
                tenant=tenant,
                stock_level=stock,
                adjustment_type='decrease',
                reason='damage',
                quantity=item.qty,
                notes=f'Scrap from RMA {disp.rma.rma_number} — Disposition {disp.disposition_number}',
                adjusted_by=request.user,
            )

    disp.status = 'processed'
    disp.processed_by = request.user
    disp.processed_at = timezone.now()
    disp.save()
    messages.success(request, f'Disposition "{disp.disposition_number}" processed.')
    return redirect('returns:disposition_detail', pk=pk)


@login_required
def disposition_cancel_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant)
    if disp.can_transition_to('cancelled'):
        disp.status = 'cancelled'
        disp.save()
        messages.success(request, 'Disposition cancelled.')
    else:
        messages.error(request, 'Cannot cancel disposition.')
    return redirect('returns:disposition_detail', pk=pk)


# ══════════════════════════════════════════════
# Refund / Credit CRUD
# ══════════════════════════════════════════════

@login_required
def refund_list_view(request):
    tenant = request.tenant
    queryset = RefundCredit.objects.filter(tenant=tenant).select_related('rma', 'processed_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(refund_number__icontains=q) | Q(rma__rma_number__icontains=q) | Q(reference_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    type_filter = request.GET.get('type', '')
    if type_filter:
        queryset = queryset.filter(type=type_filter)

    method = request.GET.get('method', '')
    if method:
        queryset = queryset.filter(method=method)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    refunds = paginator.get_page(page_number)

    return render(request, 'returns/refund_list.html', {
        'refunds': refunds,
        'q': q,
        'status_choices': RefundCredit.STATUS_CHOICES,
        'type_choices': RefundCredit.TYPE_CHOICES,
        'method_choices': RefundCredit.METHOD_CHOICES,
        'current_status': status,
        'current_type': type_filter,
        'current_method': method,
    })


@login_required
def refund_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = RefundCreditForm(request.POST, tenant=tenant)
        if form.is_valid():
            refund = form.save()
            messages.success(request, f'Refund "{refund.refund_number}" created.')
            return redirect('returns:refund_detail', pk=refund.pk)
    else:
        form = RefundCreditForm(tenant=tenant)

    return render(request, 'returns/refund_form.html', {
        'form': form,
        'title': 'Create Refund / Credit',
    })


@login_required
def refund_edit_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = RefundCreditForm(request.POST, instance=refund, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Refund "{refund.refund_number}" updated.')
            return redirect('returns:refund_detail', pk=refund.pk)
    else:
        form = RefundCreditForm(instance=refund, tenant=tenant)

    return render(request, 'returns/refund_form.html', {
        'form': form,
        'refund': refund,
        'title': f'Edit Refund {refund.refund_number}',
    })


@login_required
def refund_detail_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(
        RefundCredit.objects.select_related('rma', 'processed_by'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'returns/refund_detail.html', {'refund': refund})


@login_required
def refund_delete_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant)
    if request.method == 'POST':
        num = refund.refund_number
        refund.delete()
        messages.success(request, f'Refund "{num}" deleted.')
        return redirect('returns:refund_list')
    return redirect('returns:refund_list')


@login_required
def refund_process_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant)
    if refund.can_transition_to('processed'):
        refund.status = 'processed'
        refund.processed_by = request.user
        refund.processed_at = timezone.now()
        refund.save()
        messages.success(request, f'Refund "{refund.refund_number}" processed.')
    else:
        messages.error(request, 'Cannot process refund in current status.')
    return redirect('returns:refund_detail', pk=pk)


@login_required
def refund_fail_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant)
    if refund.can_transition_to('failed'):
        refund.status = 'failed'
        refund.save()
        messages.success(request, f'Refund "{refund.refund_number}" marked as failed.')
    else:
        messages.error(request, 'Cannot mark refund as failed.')
    return redirect('returns:refund_detail', pk=pk)


@login_required
def refund_cancel_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant)
    if refund.can_transition_to('cancelled'):
        refund.status = 'cancelled'
        refund.save()
        messages.success(request, 'Refund cancelled.')
    else:
        messages.error(request, 'Cannot cancel refund.')
    return redirect('returns:refund_detail', pk=pk)
