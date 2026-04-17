from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import tenant_admin_required, emit_audit
from inventory.models import StockAdjustment, StockLevel
from warehousing.models import Warehouse
from .models import (
    ReturnAuthorization, ReturnAuthorizationItem,
    ReturnInspection, ReturnInspectionItem,
    Disposition, DispositionItem,
    RefundCredit,
)
from .forms import (
    NON_RESTOCKABLE_CONDITIONS,
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
    queryset = ReturnAuthorization.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('sales_order', 'warehouse', 'created_by')

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

    return render(request, 'returns/rma_list.html', {
        'rmas': rmas,
        'q': q,
        'status_choices': ReturnAuthorization.STATUS_CHOICES,
        'reason_choices': ReturnAuthorization.REASON_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_reason': reason,
        'current_warehouse': warehouse_id,
    })


@login_required
def rma_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ReturnAuthorizationForm(request.POST, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(
            request.POST, prefix='items', form_kwargs={'tenant': tenant},
        )
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
            emit_audit(request, 'rma_created', rma)
            messages.success(request, f'RMA "{rma.rma_number}" created successfully.')
            return redirect('returns:rma_detail', pk=rma.pk)
    else:
        form = ReturnAuthorizationForm(tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(
            prefix='items', form_kwargs={'tenant': tenant},
        )

    return render(request, 'returns/rma_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create RMA',
    })


@login_required
def rma_edit_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if rma.status not in ('draft', 'rejected'):
        messages.error(request, f'Cannot edit RMA in "{rma.get_status_display()}" status.')
        return redirect('returns:rma_detail', pk=pk)
    if request.method == 'POST':
        form = ReturnAuthorizationForm(request.POST, instance=rma, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(
            request.POST, instance=rma, prefix='items', form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'rma_updated', rma)
            messages.success(request, f'RMA "{rma.rma_number}" updated successfully.')
            return redirect('returns:rma_detail', pk=rma.pk)
    else:
        form = ReturnAuthorizationForm(instance=rma, tenant=tenant)
        formset = ReturnAuthorizationItemFormSet(
            instance=rma, prefix='items', form_kwargs={'tenant': tenant},
        )

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
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    return render(request, 'returns/rma_detail.html', {
        'rma': rma,
        'items': rma.items.select_related('product').all(),
        'inspections': rma.inspections.all(),
        'dispositions': rma.dispositions.all(),
        'refunds': rma.refunds.all(),
    })


@tenant_admin_required
@require_POST
def rma_delete_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(
        ReturnAuthorization, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if rma.status != 'draft':
        messages.error(request, 'Only draft RMAs can be deleted.')
        return redirect('returns:rma_list')
    if rma.refunds.filter(status='processed').exists() or rma.dispositions.filter(status='processed').exists():
        messages.error(request, 'Cannot delete RMA with processed refunds or dispositions.')
        return redirect('returns:rma_detail', pk=pk)
    num = rma.rma_number
    rma.deleted_at = timezone.now()
    rma.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'rma_deleted', rma, changes=f'rma_number={num} soft_delete=true')
    messages.success(request, f'RMA "{num}" deleted.')
    return redirect('returns:rma_list')


def _transition_rma(request, pk, new_status, action_label, set_fields=None):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not rma.can_transition_to(new_status):
        messages.error(request, f'Cannot {action_label} RMA in "{rma.get_status_display()}" status.')
        return redirect('returns:rma_detail', pk=pk)
    old = rma.status
    rma.status = new_status
    if set_fields:
        for name, value in set_fields.items():
            setattr(rma, name, value)
    rma.save()
    emit_audit(request, f'rma_{action_label}', rma, changes=f'{old}->{new_status}')
    messages.success(request, f'RMA "{rma.rma_number}" {action_label}.')
    return redirect('returns:rma_detail', pk=pk)


@tenant_admin_required
@require_POST
def rma_submit_view(request, pk):
    return _transition_rma(request, pk, 'pending', 'submitted')


@tenant_admin_required
@require_POST
def rma_approve_view(request, pk):
    tenant = request.tenant
    rma = get_object_or_404(ReturnAuthorization, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if rma.created_by_id and rma.created_by_id == request.user.id and not request.user.is_superuser:
        messages.error(request, 'You cannot approve an RMA you created (segregation of duties).')
        return redirect('returns:rma_detail', pk=pk)
    if not rma.can_transition_to('approved'):
        messages.error(request, f'Cannot approve RMA in "{rma.get_status_display()}" status.')
        return redirect('returns:rma_detail', pk=pk)
    old = rma.status
    rma.status = 'approved'
    rma.approved_by = request.user
    rma.approved_at = timezone.now()
    rma.save()
    emit_audit(request, 'rma_approved', rma, changes=f'{old}->approved')
    messages.success(request, f'RMA "{rma.rma_number}" approved.')
    return redirect('returns:rma_detail', pk=pk)


@tenant_admin_required
@require_POST
def rma_reject_view(request, pk):
    return _transition_rma(request, pk, 'rejected', 'rejected')


@tenant_admin_required
@require_POST
def rma_receive_view(request, pk):
    return _transition_rma(request, pk, 'received', 'received', set_fields={'received_at': timezone.now()})


@tenant_admin_required
@require_POST
def rma_close_view(request, pk):
    return _transition_rma(request, pk, 'closed', 'closed', set_fields={'closed_at': timezone.now()})


@tenant_admin_required
@require_POST
def rma_cancel_view(request, pk):
    return _transition_rma(request, pk, 'cancelled', 'cancelled')


# ══════════════════════════════════════════════
# Return Inspection CRUD
# ══════════════════════════════════════════════

@login_required
def inspection_list_view(request):
    tenant = request.tenant
    queryset = ReturnInspection.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('rma', 'inspector')

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
        formset = ReturnInspectionItemFormSet(
            request.POST, prefix='items', form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            insp = form.save()
            formset.instance = insp
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'inspection_created', insp)
            messages.success(request, f'Inspection "{insp.inspection_number}" created.')
            return redirect('returns:inspection_detail', pk=insp.pk)
    else:
        form = ReturnInspectionForm(tenant=tenant)
        formset = ReturnInspectionItemFormSet(
            prefix='items', form_kwargs={'tenant': tenant},
        )

    return render(request, 'returns/inspection_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Inspection',
    })


@login_required
def inspection_edit_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if insp.status == 'completed':
        messages.error(request, 'Completed inspections are immutable.')
        return redirect('returns:inspection_detail', pk=pk)
    if request.method == 'POST':
        form = ReturnInspectionForm(request.POST, instance=insp, tenant=tenant)
        formset = ReturnInspectionItemFormSet(
            request.POST, instance=insp, prefix='items', form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'inspection_updated', insp)
            messages.success(request, f'Inspection "{insp.inspection_number}" updated.')
            return redirect('returns:inspection_detail', pk=insp.pk)
    else:
        form = ReturnInspectionForm(instance=insp, tenant=tenant)
        formset = ReturnInspectionItemFormSet(
            instance=insp, prefix='items', form_kwargs={'tenant': tenant},
        )

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
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    return render(request, 'returns/inspection_detail.html', {
        'inspection': insp,
        'items': insp.items.select_related('rma_item__product').all(),
    })


@tenant_admin_required
@require_POST
def inspection_delete_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(
        ReturnInspection, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if insp.status == 'completed' and insp.dispositions.filter(deleted_at__isnull=True).exists():
        messages.error(request, 'Cannot delete completed inspection with linked dispositions.')
        return redirect('returns:inspection_detail', pk=pk)
    num = insp.inspection_number
    insp.deleted_at = timezone.now()
    insp.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'inspection_deleted', insp, changes=f'inspection_number={num} soft_delete=true')
    messages.success(request, f'Inspection "{num}" deleted.')
    return redirect('returns:inspection_list')


@tenant_admin_required
@require_POST
def inspection_start_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not insp.can_transition_to('in_progress'):
        messages.error(request, 'Cannot start inspection in current status.')
        return redirect('returns:inspection_detail', pk=pk)
    old = insp.status
    insp.status = 'in_progress'
    insp.started_at = timezone.now()
    insp.save()
    emit_audit(request, 'inspection_started', insp, changes=f'{old}->in_progress')
    messages.success(request, 'Inspection started.')
    return redirect('returns:inspection_detail', pk=pk)


@tenant_admin_required
@require_POST
def inspection_complete_view(request, pk):
    tenant = request.tenant
    insp = get_object_or_404(ReturnInspection, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not insp.can_transition_to('completed'):
        messages.error(request, 'Cannot complete inspection in current status.')
        return redirect('returns:inspection_detail', pk=pk)
    old = insp.status
    insp.status = 'completed'
    insp.completed_at = timezone.now()
    if not insp.inspected_date:
        insp.inspected_date = timezone.now().date()
    insp.save()
    emit_audit(request, 'inspection_completed', insp, changes=f'{old}->completed')
    messages.success(request, 'Inspection completed.')
    return redirect('returns:inspection_detail', pk=pk)


# ══════════════════════════════════════════════
# Disposition CRUD
# ══════════════════════════════════════════════

@login_required
def disposition_list_view(request):
    tenant = request.tenant
    queryset = Disposition.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('rma', 'warehouse', 'processed_by')

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
        formset = DispositionItemFormSet(
            request.POST, prefix='items', form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            disp = form.save()
            formset.instance = disp
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'disposition_created', disp)
            messages.success(request, f'Disposition "{disp.disposition_number}" created.')
            return redirect('returns:disposition_detail', pk=disp.pk)
    else:
        form = DispositionForm(tenant=tenant)
        formset = DispositionItemFormSet(
            prefix='items', form_kwargs={'tenant': tenant},
        )

    return render(request, 'returns/disposition_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Disposition',
    })


@login_required
def disposition_edit_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if disp.status == 'processed':
        messages.error(request, 'Processed dispositions are immutable.')
        return redirect('returns:disposition_detail', pk=pk)
    if request.method == 'POST':
        form = DispositionForm(request.POST, instance=disp, tenant=tenant)
        formset = DispositionItemFormSet(
            request.POST, instance=disp, prefix='items', form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            emit_audit(request, 'disposition_updated', disp)
            messages.success(request, f'Disposition "{disp.disposition_number}" updated.')
            return redirect('returns:disposition_detail', pk=disp.pk)
    else:
        form = DispositionForm(instance=disp, tenant=tenant)
        formset = DispositionItemFormSet(
            instance=disp, prefix='items', form_kwargs={'tenant': tenant},
        )

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
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    return render(request, 'returns/disposition_detail.html', {
        'disposition': disp,
        'items': disp.items.select_related('product', 'destination_bin').all(),
    })


@tenant_admin_required
@require_POST
def disposition_delete_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(
        Disposition, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if disp.status == 'processed':
        messages.error(request, 'Processed dispositions cannot be deleted.')
        return redirect('returns:disposition_detail', pk=pk)
    num = disp.disposition_number
    disp.deleted_at = timezone.now()
    disp.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'disposition_deleted', disp, changes=f'disposition_number={num} soft_delete=true')
    messages.success(request, f'Disposition "{num}" deleted.')
    return redirect('returns:disposition_list')


@tenant_admin_required
@require_POST
def disposition_process_view(request, pk):
    """Process a disposition — atomically apply stock effects.

    Concurrency: the disposition row is locked via `select_for_update` so a
    double-click produces exactly one set of `StockAdjustment` rows.
    """
    tenant = request.tenant
    # Cheap existence check first so cross-tenant / missing PKs return 404,
    # not 500 from a raw .get() inside the atomic block.
    get_object_or_404(Disposition, pk=pk, tenant=tenant, deleted_at__isnull=True)
    with transaction.atomic():
        disp = (
            Disposition.objects.select_for_update()
            .select_related('rma', 'warehouse')
            .get(pk=pk, tenant=tenant)
        )
        if not disp.can_transition_to('processed'):
            messages.error(
                request,
                f'Cannot process disposition in "{disp.get_status_display()}" status.',
            )
            return redirect('returns:disposition_detail', pk=pk)

        items = list(
            disp.items.select_related('product', 'inspection_item').all()
        )

        if disp.decision == 'restock':
            # D-02 / D-11 guard (defence-in-depth — form already enforces).
            for item in items:
                ins_item = item.inspection_item
                if ins_item is None:
                    messages.error(request, 'Restock requires a linked inspection item on every line.')
                    return redirect('returns:disposition_detail', pk=pk)
                if not ins_item.restockable or ins_item.condition in NON_RESTOCKABLE_CONDITIONS:
                    messages.error(
                        request,
                        f'Item {item.product.name} is flagged non-restockable '
                        f'({ins_item.get_condition_display()}) — cannot restock.',
                    )
                    return redirect('returns:disposition_detail', pk=pk)
                if item.qty > ins_item.qty_passed:
                    messages.error(
                        request,
                        f'Restock qty {item.qty} exceeds inspection qty_passed '
                        f'{ins_item.qty_passed} for {item.product.name}.',
                    )
                    return redirect('returns:disposition_detail', pk=pk)

        for item in items:
            if item.qty <= 0:
                continue
            stock, _ = StockLevel.objects.select_for_update().get_or_create(
                tenant=tenant, product=item.product, warehouse=disp.warehouse,
                defaults={'on_hand': 0, 'allocated': 0, 'on_order': 0},
            )
            if disp.decision == 'restock':
                StockAdjustment.objects.create(
                    tenant=tenant, stock_level=stock,
                    adjustment_type='increase', reason='return',
                    quantity=item.qty,
                    notes=f'Restock from RMA {disp.rma.rma_number} — Disposition {disp.disposition_number}',
                    adjusted_by=request.user,
                )
                stock.on_hand += item.qty
                stock.save()
            elif disp.decision == 'scrap':
                StockAdjustment.objects.create(
                    tenant=tenant, stock_level=stock,
                    adjustment_type='decrease', reason='damage',
                    quantity=item.qty,
                    notes=f'Scrap from RMA {disp.rma.rma_number} — Disposition {disp.disposition_number}',
                    adjusted_by=request.user,
                )
                # D-20: scrap path now actually decrements on_hand symmetrically.
                # Never drive on_hand below zero — clamp at 0 and record the floor.
                stock.on_hand = max(0, stock.on_hand - item.qty)
                stock.save()
            # liquidate / repair / return_to_vendor have no stock-level effect —
            # they are tracked via the AuditLog emission below.

        old = disp.status
        disp.status = 'processed'
        disp.processed_by = request.user
        disp.processed_at = timezone.now()
        disp.save()
        emit_audit(
            request, 'disposition_processed', disp,
            changes=f'{old}->processed decision={disp.decision}',
        )

    messages.success(request, f'Disposition "{disp.disposition_number}" processed.')
    return redirect('returns:disposition_detail', pk=pk)


@tenant_admin_required
@require_POST
def disposition_cancel_view(request, pk):
    tenant = request.tenant
    disp = get_object_or_404(Disposition, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not disp.can_transition_to('cancelled'):
        messages.error(request, 'Cannot cancel disposition.')
        return redirect('returns:disposition_detail', pk=pk)
    old = disp.status
    disp.status = 'cancelled'
    disp.save()
    emit_audit(request, 'disposition_cancelled', disp, changes=f'{old}->cancelled')
    messages.success(request, 'Disposition cancelled.')
    return redirect('returns:disposition_detail', pk=pk)


# ══════════════════════════════════════════════
# Refund / Credit CRUD
# ══════════════════════════════════════════════

@login_required
def refund_list_view(request):
    tenant = request.tenant
    queryset = RefundCredit.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('rma', 'processed_by')

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
            emit_audit(request, 'refund_created', refund)
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
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if refund.status == 'processed':
        messages.error(request, 'Processed refunds are immutable.')
        return redirect('returns:refund_detail', pk=pk)
    if request.method == 'POST':
        form = RefundCreditForm(request.POST, instance=refund, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'refund_updated', refund)
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
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    return render(request, 'returns/refund_detail.html', {'refund': refund})


@tenant_admin_required
@require_POST
def refund_delete_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(
        RefundCredit, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if refund.status == 'processed':
        messages.error(request, 'Processed refunds cannot be deleted.')
        return redirect('returns:refund_detail', pk=pk)
    num = refund.refund_number
    refund.deleted_at = timezone.now()
    refund.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'refund_deleted', refund, changes=f'refund_number={num} soft_delete=true')
    messages.success(request, f'Refund "{num}" deleted.')
    return redirect('returns:refund_list')


@tenant_admin_required
@require_POST
def refund_process_view(request, pk):
    tenant = request.tenant
    get_object_or_404(RefundCredit, pk=pk, tenant=tenant, deleted_at__isnull=True)
    with transaction.atomic():
        refund = RefundCredit.objects.select_for_update().get(pk=pk, tenant=tenant)
        if not refund.can_transition_to('processed'):
            messages.error(request, f'Cannot process refund in "{refund.get_status_display()}" status.')
            return redirect('returns:refund_detail', pk=pk)
        old = refund.status
        refund.status = 'processed'
        refund.processed_by = request.user
        refund.processed_at = timezone.now()
        refund.save()
        emit_audit(request, 'refund_processed', refund, changes=f'{old}->processed amount={refund.amount}')
    messages.success(request, f'Refund "{refund.refund_number}" processed.')
    return redirect('returns:refund_detail', pk=pk)


@tenant_admin_required
@require_POST
def refund_fail_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not refund.can_transition_to('failed'):
        messages.error(request, 'Cannot mark refund as failed.')
        return redirect('returns:refund_detail', pk=pk)
    old = refund.status
    refund.status = 'failed'
    refund.save()
    emit_audit(request, 'refund_failed', refund, changes=f'{old}->failed')
    messages.success(request, f'Refund "{refund.refund_number}" marked as failed.')
    return redirect('returns:refund_detail', pk=pk)


@tenant_admin_required
@require_POST
def refund_cancel_view(request, pk):
    tenant = request.tenant
    refund = get_object_or_404(RefundCredit, pk=pk, tenant=tenant, deleted_at__isnull=True)
    if not refund.can_transition_to('cancelled'):
        messages.error(request, 'Cannot cancel refund.')
        return redirect('returns:refund_detail', pk=pk)
    old = refund.status
    refund.status = 'cancelled'
    refund.save()
    emit_audit(request, 'refund_cancelled', refund, changes=f'{old}->cancelled')
    messages.success(request, 'Refund cancelled.')
    return redirect('returns:refund_detail', pk=pk)
