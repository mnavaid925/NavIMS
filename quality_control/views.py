from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import tenant_admin_required, emit_audit

from warehousing.models import Warehouse
from inventory.models import StockAdjustment, StockLevel

from .models import (
    QCChecklist,
    InspectionRoute,
    QuarantineRecord,
    DefectReport, DefectPhoto,
    ScrapWriteOff,
)
from .forms import (
    QCChecklistForm, QCChecklistItemFormSet,
    InspectionRouteForm, InspectionRouteRuleFormSet,
    QuarantineRecordForm, QuarantineReleaseForm,
    DefectReportForm, DefectPhotoFormSet,
    ScrapWriteOffForm,
)


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 1: QC Checklists
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def checklist_list_view(request):
    tenant = request.tenant
    qs = (
        QCChecklist.objects.filter(tenant=tenant)
        .select_related('product', 'vendor', 'category')
        .annotate(item_count=Count('items'))
        .order_by('name')
    )

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))

    applies_to = request.GET.get('applies_to', '')
    if applies_to:
        qs = qs.filter(applies_to=applies_to)

    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'quality_control/checklist_list.html', {
        'checklists': page,
        'q': q,
        'current_applies_to': applies_to,
        'current_active': active,
        'applies_to_choices': QCChecklist.APPLIES_TO_CHOICES,
    })


@login_required
@tenant_admin_required
def checklist_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = QCChecklistForm(request.POST, tenant=tenant)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = tenant
                obj.created_by = request.user
                obj.save()
                formset = QCChecklistItemFormSet(
                    request.POST, instance=obj, form_kwargs={'tenant': tenant},
                )
                if formset.is_valid():
                    items = formset.save(commit=False)
                    for item in items:
                        item.tenant = tenant
                        item.save()
                    for item in formset.deleted_objects:
                        item.delete()
                else:
                    transaction.set_rollback(True)
                    return render(request, 'quality_control/checklist_form.html', {
                        'form': form, 'formset': formset, 'title': 'New QC Checklist',
                    })
            emit_audit(request, 'create', obj)
            messages.success(request, f'Checklist "{obj.code}" created.')
            return redirect('quality_control:checklist_detail', pk=obj.pk)
        formset = QCChecklistItemFormSet(request.POST, form_kwargs={'tenant': tenant})
    else:
        form = QCChecklistForm(tenant=tenant)
        formset = QCChecklistItemFormSet(form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/checklist_form.html', {
        'form': form, 'formset': formset, 'title': 'New QC Checklist',
    })


@login_required
def checklist_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QCChecklist.objects.select_related('product', 'vendor', 'category', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = obj.items.all()
    return render(request, 'quality_control/checklist_detail.html', {
        'checklist': obj, 'items': items,
    })


@login_required
@tenant_admin_required
def checklist_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(QCChecklist, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = QCChecklistForm(request.POST, instance=obj, tenant=tenant)
        formset = QCChecklistItemFormSet(
            request.POST, instance=obj, form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                items = formset.save(commit=False)
                for item in items:
                    item.tenant = tenant
                    item.save()
                for item in formset.deleted_objects:
                    item.delete()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Checklist "{obj.code}" updated.')
            return redirect('quality_control:checklist_detail', pk=obj.pk)
    else:
        form = QCChecklistForm(instance=obj, tenant=tenant)
        formset = QCChecklistItemFormSet(instance=obj, form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/checklist_form.html', {
        'form': form, 'formset': formset, 'checklist': obj, 'title': f'Edit {obj.code}',
    })


@login_required
@tenant_admin_required
@require_POST
def checklist_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(QCChecklist, pk=pk, tenant=tenant)
    code = obj.code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Checklist "{code}" deleted.')
    return redirect('quality_control:checklist_list')


@login_required
@tenant_admin_required
@require_POST
def checklist_toggle_active_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(QCChecklist, pk=pk, tenant=tenant)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active', 'updated_at'])
    emit_audit(request, 'toggle_active', obj, changes=f'is_active={obj.is_active}')
    state = 'activated' if obj.is_active else 'deactivated'
    messages.success(request, f'Checklist "{obj.code}" {state}.')
    return redirect('quality_control:checklist_detail', pk=obj.pk)


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 2: Inspection Routing
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def route_list_view(request):
    tenant = request.tenant
    qs = (
        InspectionRoute.objects.filter(tenant=tenant)
        .select_related('source_warehouse', 'qc_zone', 'putaway_zone')
        .annotate(rule_count=Count('rules'))
        .order_by('priority', 'name')
    )

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(source_warehouse_id=warehouse_id)

    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'quality_control/route_list.html', {
        'routes': page,
        'q': q,
        'current_warehouse': warehouse_id,
        'current_active': active,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
    })


@login_required
@tenant_admin_required
def route_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = InspectionRouteForm(request.POST, tenant=tenant)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = tenant
                obj.save()
                formset = InspectionRouteRuleFormSet(
                    request.POST, instance=obj, form_kwargs={'tenant': tenant},
                )
                if formset.is_valid():
                    rules = formset.save(commit=False)
                    for rule in rules:
                        rule.tenant = tenant
                        rule.save()
                    for rule in formset.deleted_objects:
                        rule.delete()
                else:
                    transaction.set_rollback(True)
                    return render(request, 'quality_control/route_form.html', {
                        'form': form, 'formset': formset, 'title': 'New Inspection Route',
                    })
            emit_audit(request, 'create', obj)
            messages.success(request, f'Route "{obj.code}" created.')
            return redirect('quality_control:route_detail', pk=obj.pk)
        formset = InspectionRouteRuleFormSet(request.POST, form_kwargs={'tenant': tenant})
    else:
        form = InspectionRouteForm(tenant=tenant)
        formset = InspectionRouteRuleFormSet(form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/route_form.html', {
        'form': form, 'formset': formset, 'title': 'New Inspection Route',
    })


@login_required
def route_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        InspectionRoute.objects.select_related('source_warehouse', 'qc_zone', 'putaway_zone'),
        pk=pk, tenant=tenant,
    )
    rules = obj.rules.select_related('product', 'vendor', 'category', 'checklist')
    return render(request, 'quality_control/route_detail.html', {
        'route': obj, 'rules': rules,
    })


@login_required
@tenant_admin_required
def route_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(InspectionRoute, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = InspectionRouteForm(request.POST, instance=obj, tenant=tenant)
        formset = InspectionRouteRuleFormSet(
            request.POST, instance=obj, form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                rules = formset.save(commit=False)
                for rule in rules:
                    rule.tenant = tenant
                    rule.save()
                for rule in formset.deleted_objects:
                    rule.delete()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Route "{obj.code}" updated.')
            return redirect('quality_control:route_detail', pk=obj.pk)
    else:
        form = InspectionRouteForm(instance=obj, tenant=tenant)
        formset = InspectionRouteRuleFormSet(instance=obj, form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/route_form.html', {
        'form': form, 'formset': formset, 'route': obj, 'title': f'Edit {obj.code}',
    })


@login_required
@tenant_admin_required
@require_POST
def route_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(InspectionRoute, pk=pk, tenant=tenant)
    code = obj.code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Route "{code}" deleted.')
    return redirect('quality_control:route_list')


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 3: Quarantine Management
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def quarantine_list_view(request):
    tenant = request.tenant
    qs = QuarantineRecord.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('product', 'warehouse', 'zone', 'grn', 'lot', 'held_by')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(quarantine_number__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(product__name__icontains=q)
            | Q(reason_notes__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    reason = request.GET.get('reason', '')
    if reason:
        qs = qs.filter(reason=reason)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'quality_control/quarantine_list.html', {
        'records': page,
        'q': q,
        'current_status': status,
        'current_reason': reason,
        'current_warehouse': warehouse_id,
        'status_choices': QuarantineRecord.STATUS_CHOICES,
        'reason_choices': QuarantineRecord.REASON_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
    })


@login_required
@tenant_admin_required
def quarantine_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = QuarantineRecordForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.held_by = request.user
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Quarantine "{obj.quarantine_number}" created.')
            return redirect('quality_control:quarantine_detail', pk=obj.pk)
    else:
        form = QuarantineRecordForm(tenant=tenant)
    return render(request, 'quality_control/quarantine_form.html', {
        'form': form, 'title': 'New Quarantine Hold',
    })


@login_required
def quarantine_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QuarantineRecord.objects.select_related(
            'product', 'warehouse', 'zone', 'grn', 'lot', 'held_by', 'released_by',
        ),
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    defect_reports = obj.defect_reports.filter(deleted_at__isnull=True)
    scrap_writeoffs = obj.scrap_writeoffs.filter(deleted_at__isnull=True)
    release_form = QuarantineReleaseForm()
    return render(request, 'quality_control/quarantine_detail.html', {
        'record': obj,
        'defect_reports': defect_reports,
        'scrap_writeoffs': scrap_writeoffs,
        'release_form': release_form,
    })


@login_required
@tenant_admin_required
def quarantine_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QuarantineRecord, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.status not in ('active', 'under_review'):
        messages.error(request, 'Only active or under-review quarantines can be edited.')
        return redirect('quality_control:quarantine_detail', pk=obj.pk)
    if request.method == 'POST':
        form = QuarantineRecordForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Quarantine "{obj.quarantine_number}" updated.')
            return redirect('quality_control:quarantine_detail', pk=obj.pk)
    else:
        form = QuarantineRecordForm(instance=obj, tenant=tenant)
    return render(request, 'quality_control/quarantine_form.html', {
        'form': form, 'record': obj, 'title': f'Edit {obj.quarantine_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def quarantine_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QuarantineRecord, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.status != 'active':
        messages.error(request, 'Only active quarantines can be deleted. Use release instead.')
        return redirect('quality_control:quarantine_detail', pk=obj.pk)
    obj.deleted_at = timezone.now()
    obj.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'delete', obj)
    messages.success(request, f'Quarantine "{obj.quarantine_number}" deleted.')
    return redirect('quality_control:quarantine_list')


@login_required
@tenant_admin_required
@require_POST
def quarantine_review_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QuarantineRecord, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if not obj.can_transition_to('under_review'):
        messages.error(request, f'Cannot move to "under review" from "{obj.get_status_display()}".')
        return redirect('quality_control:quarantine_detail', pk=obj.pk)
    old = obj.status
    obj.status = 'under_review'
    obj.save(update_fields=['status', 'updated_at'])
    emit_audit(request, 'review', obj, changes=f'{old}->under_review')
    messages.success(request, f'Quarantine "{obj.quarantine_number}" moved to review.')
    return redirect('quality_control:quarantine_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def quarantine_release_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        QuarantineRecord, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    form = QuarantineReleaseForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid disposition.')
        return redirect('quality_control:quarantine_detail', pk=obj.pk)
    disposition = form.cleaned_data['disposition']
    notes = form.cleaned_data.get('notes', '')
    new_status = 'scrapped' if disposition == 'scrap' else 'released'
    # D-05: route every status write through the state machine.
    if not obj.can_transition_to(new_status):
        messages.error(
            request,
            f'Cannot transition from "{obj.get_status_display()}" to "{new_status}".',
        )
        return redirect('quality_control:quarantine_detail', pk=obj.pk)

    with transaction.atomic():
        old = obj.status
        if disposition == 'scrap':
            obj.status = 'scrapped'
            # Auto-create a pending ScrapWriteOff. The caller still has to
            # approve + post it to actually mutate StockLevel.
            ScrapWriteOff.objects.create(
                tenant=tenant,
                quarantine_record=obj,
                product=obj.product,
                warehouse=obj.warehouse,
                quantity=obj.quantity,
                unit_cost=0,
                reason=f'Auto-scrap from quarantine {obj.quarantine_number}',
                approval_status='pending',
                requested_by=request.user,
            )
        else:
            obj.status = 'released'
        obj.release_disposition = disposition
        obj.release_notes = notes
        obj.released_by = request.user
        obj.released_at = timezone.now()
        obj.save()
        emit_audit(
            request, 'release', obj,
            changes=f'{old}->{obj.status} ({disposition})',
        )
    messages.success(
        request,
        f'Quarantine "{obj.quarantine_number}" — {obj.get_status_display()} ({obj.get_release_disposition_display()}).',
    )
    return redirect('quality_control:quarantine_detail', pk=obj.pk)


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 4: Defect & Scrap Reporting — Defect Reports
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def defect_list_view(request):
    tenant = request.tenant
    qs = DefectReport.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('product', 'warehouse', 'lot', 'serial', 'reported_by')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(defect_number__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(product__name__icontains=q)
            | Q(description__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    severity = request.GET.get('severity', '')
    if severity:
        qs = qs.filter(severity=severity)

    defect_type = request.GET.get('defect_type', '')
    if defect_type:
        qs = qs.filter(defect_type=defect_type)

    source = request.GET.get('source', '')
    if source:
        qs = qs.filter(source=source)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'quality_control/defect_list.html', {
        'defects': page,
        'q': q,
        'current_status': status,
        'current_severity': severity,
        'current_defect_type': defect_type,
        'current_source': source,
        'status_choices': DefectReport.STATUS_CHOICES,
        'severity_choices': DefectReport.SEVERITY_CHOICES,
        'defect_type_choices': DefectReport.DEFECT_TYPE_CHOICES,
        'source_choices': DefectReport.SOURCE_CHOICES,
    })


@login_required
@tenant_admin_required
def defect_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = DefectReportForm(request.POST, tenant=tenant)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = tenant
                obj.reported_by = request.user
                obj.save()
                formset = DefectPhotoFormSet(
                    request.POST, request.FILES, instance=obj,
                    form_kwargs={'tenant': tenant},
                )
                if formset.is_valid():
                    photos = formset.save(commit=False)
                    for photo in photos:
                        photo.tenant = tenant
                        photo.save()
                    for photo in formset.deleted_objects:
                        photo.delete()
                else:
                    transaction.set_rollback(True)
                    return render(request, 'quality_control/defect_form.html', {
                        'form': form, 'formset': formset, 'title': 'New Defect Report',
                    })
            emit_audit(request, 'create', obj)
            messages.success(request, f'Defect "{obj.defect_number}" reported.')
            return redirect('quality_control:defect_detail', pk=obj.pk)
        formset = DefectPhotoFormSet(request.POST, request.FILES, form_kwargs={'tenant': tenant})
    else:
        form = DefectReportForm(tenant=tenant)
        formset = DefectPhotoFormSet(form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/defect_form.html', {
        'form': form, 'formset': formset, 'title': 'New Defect Report',
    })


@login_required
def defect_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        DefectReport.objects.select_related(
            'product', 'warehouse', 'lot', 'serial', 'grn',
            'quarantine_record', 'reported_by', 'resolved_by',
        ),
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    photos = obj.photos.all()
    scrap_writeoffs = obj.scrap_writeoffs.filter(deleted_at__isnull=True)
    return render(request, 'quality_control/defect_detail.html', {
        'defect': obj, 'photos': photos, 'scrap_writeoffs': scrap_writeoffs,
    })


@login_required
@tenant_admin_required
def defect_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        DefectReport, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.status in ('resolved', 'scrapped'):
        messages.error(request, 'Resolved / scrapped defects cannot be edited.')
        return redirect('quality_control:defect_detail', pk=obj.pk)
    if request.method == 'POST':
        form = DefectReportForm(request.POST, instance=obj, tenant=tenant)
        formset = DefectPhotoFormSet(
            request.POST, request.FILES, instance=obj,
            form_kwargs={'tenant': tenant},
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                photos = formset.save(commit=False)
                for photo in photos:
                    photo.tenant = tenant
                    photo.save()
                for photo in formset.deleted_objects:
                    photo.delete()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Defect "{obj.defect_number}" updated.')
            return redirect('quality_control:defect_detail', pk=obj.pk)
    else:
        form = DefectReportForm(instance=obj, tenant=tenant)
        formset = DefectPhotoFormSet(instance=obj, form_kwargs={'tenant': tenant})
    return render(request, 'quality_control/defect_form.html', {
        'form': form, 'formset': formset, 'defect': obj, 'title': f'Edit {obj.defect_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def defect_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        DefectReport, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.status != 'open':
        messages.error(request, 'Only open defects can be deleted.')
        return redirect('quality_control:defect_detail', pk=obj.pk)
    obj.deleted_at = timezone.now()
    obj.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'delete', obj)
    messages.success(request, f'Defect "{obj.defect_number}" deleted.')
    return redirect('quality_control:defect_list')


def _transition_defect(request, pk, new_status, audit_action):
    tenant = request.tenant
    obj = get_object_or_404(
        DefectReport, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if not obj.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from "{obj.get_status_display()}" to "{new_status}".')
        return redirect('quality_control:defect_detail', pk=obj.pk)
    old = obj.status
    obj.status = new_status
    if new_status in ('resolved', 'scrapped'):
        obj.resolved_by = request.user
        obj.resolved_at = timezone.now()
    obj.save()
    emit_audit(request, audit_action, obj, changes=f'{old}->{new_status}')
    messages.success(request, f'Defect "{obj.defect_number}" — {obj.get_status_display()}.')
    return redirect('quality_control:defect_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def defect_investigate_view(request, pk):
    return _transition_defect(request, pk, 'investigating', 'investigate')


@login_required
@tenant_admin_required
@require_POST
def defect_resolve_view(request, pk):
    return _transition_defect(request, pk, 'resolved', 'resolve')


@login_required
@tenant_admin_required
@require_POST
def defect_scrap_view(request, pk):
    return _transition_defect(request, pk, 'scrapped', 'scrap')


@login_required
@tenant_admin_required
@require_POST
def defect_photo_delete_view(request, pk, photo_pk):
    tenant = request.tenant
    defect = get_object_or_404(
        DefectReport, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    # D-11: only allow photo deletion while the defect is still being worked on.
    # Once resolved/scrapped the photo is evidence and must stay.
    if defect.status not in ('open', 'investigating'):
        messages.error(
            request,
            f'Cannot remove photos from a {defect.get_status_display()} defect.',
        )
        return redirect('quality_control:defect_detail', pk=defect.pk)
    photo = get_object_or_404(DefectPhoto, pk=photo_pk, defect_report=defect, tenant=tenant)
    photo.delete()
    emit_audit(request, 'delete_photo', defect)
    messages.success(request, 'Photo removed.')
    return redirect('quality_control:defect_detail', pk=defect.pk)


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 4: Defect & Scrap Reporting — Scrap Write-Offs
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def scrap_list_view(request):
    tenant = request.tenant
    qs = ScrapWriteOff.objects.filter(
        tenant=tenant, deleted_at__isnull=True,
    ).select_related('product', 'warehouse', 'defect_report', 'quarantine_record', 'approved_by')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(scrap_number__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(product__name__icontains=q)
            | Q(reason__icontains=q)
        )

    status = request.GET.get('approval_status', '')
    if status:
        qs = qs.filter(approval_status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'quality_control/scrap_list.html', {
        'writeoffs': page,
        'q': q,
        'current_approval_status': status,
        'current_warehouse': warehouse_id,
        'approval_status_choices': ScrapWriteOff.APPROVAL_STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
    })


@login_required
@tenant_admin_required
def scrap_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ScrapWriteOffForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.requested_by = request.user
            obj.approval_status = 'pending'
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Scrap "{obj.scrap_number}" created (pending approval).')
            return redirect('quality_control:scrap_detail', pk=obj.pk)
    else:
        form = ScrapWriteOffForm(tenant=tenant)
    return render(request, 'quality_control/scrap_form.html', {
        'form': form, 'title': 'New Scrap Write-Off',
    })


@login_required
def scrap_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff.objects.select_related(
            'product', 'warehouse', 'defect_report', 'quarantine_record',
            'requested_by', 'approved_by', 'posted_by', 'stock_adjustment',
        ),
        pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    return render(request, 'quality_control/scrap_detail.html', {'scrap': obj})


@login_required
@tenant_admin_required
def scrap_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.approval_status != 'pending':
        messages.error(request, 'Only pending scrap records can be edited.')
        return redirect('quality_control:scrap_detail', pk=obj.pk)
    if request.method == 'POST':
        form = ScrapWriteOffForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Scrap "{obj.scrap_number}" updated.')
            return redirect('quality_control:scrap_detail', pk=obj.pk)
    else:
        form = ScrapWriteOffForm(instance=obj, tenant=tenant)
    return render(request, 'quality_control/scrap_form.html', {
        'form': form, 'scrap': obj, 'title': f'Edit {obj.scrap_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def scrap_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    if obj.approval_status != 'pending':
        messages.error(request, 'Only pending scrap records can be deleted.')
        return redirect('quality_control:scrap_detail', pk=obj.pk)
    obj.deleted_at = timezone.now()
    obj.save(update_fields=['deleted_at', 'updated_at'])
    emit_audit(request, 'delete', obj)
    messages.success(request, f'Scrap "{obj.scrap_number}" deleted.')
    return redirect('quality_control:scrap_list')


@login_required
@tenant_admin_required
@require_POST
def scrap_approve_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    # D-05: route through StateMachineMixin.
    if not obj.can_transition_to('approved'):
        messages.error(
            request,
            f'Cannot approve from "{obj.get_approval_status_display()}".',
        )
        return redirect('quality_control:scrap_detail', pk=obj.pk)
    # Segregation of duties — requester cannot self-approve.
    if obj.requested_by_id == request.user.id and not request.user.is_superuser:
        messages.error(request, 'The requester cannot approve their own scrap request.')
        return redirect('quality_control:scrap_detail', pk=obj.pk)
    obj.approval_status = 'approved'
    obj.approved_by = request.user
    obj.approved_at = timezone.now()
    obj.save()
    emit_audit(request, 'approve', obj, changes='pending->approved')
    messages.success(request, f'Scrap "{obj.scrap_number}" approved.')
    return redirect('quality_control:scrap_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def scrap_reject_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    # D-05: route through StateMachineMixin.
    if not obj.can_transition_to('rejected'):
        messages.error(
            request,
            f'Cannot reject from "{obj.get_approval_status_display()}".',
        )
        return redirect('quality_control:scrap_detail', pk=obj.pk)
    old = obj.approval_status
    obj.approval_status = 'rejected'
    obj.save()
    emit_audit(request, 'reject', obj, changes=f'{old}->rejected')
    messages.success(request, f'Scrap "{obj.scrap_number}" rejected.')
    return redirect('quality_control:scrap_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def scrap_post_view(request, pk):
    """Post an approved scrap write-off: create a decrease StockAdjustment
    atomically against the product's StockLevel in the target warehouse."""
    tenant = request.tenant
    obj = get_object_or_404(
        ScrapWriteOff, pk=pk, tenant=tenant, deleted_at__isnull=True,
    )
    # D-05: pre-flight check using the state machine — cheaper short-circuit
    # than locking the row, but the authoritative re-check happens inside
    # the atomic block below (D-01).
    if not obj.can_transition_to('posted'):
        messages.error(
            request,
            f'Cannot post from "{obj.get_approval_status_display()}".',
        )
        return redirect('quality_control:scrap_detail', pk=obj.pk)

    try:
        with transaction.atomic():
            # D-01: re-lock the ScrapWriteOff row and re-check its approval_status
            # under the same transaction as the StockLevel mutation. Without this,
            # two concurrent POSTs could both observe `approval_status='approved'`
            # from their pre-atomic in-memory reads and each decrement on_hand.
            obj = ScrapWriteOff.objects.select_for_update().get(pk=obj.pk, tenant=tenant)
            if not obj.can_transition_to('posted'):
                raise ValueError(
                    f'Scrap "{obj.scrap_number}" is no longer postable (status={obj.get_approval_status_display()}).'
                )
            stock_level = (
                StockLevel.objects
                .select_for_update()
                .filter(tenant=tenant, product=obj.product, warehouse=obj.warehouse)
                .first()
            )
            if stock_level is None:
                raise ValueError(
                    f'No StockLevel row for product "{obj.product.sku}" at warehouse "{obj.warehouse.code}".'
                )
            if obj.quantity > stock_level.on_hand:
                raise ValueError(
                    f'Cannot scrap {obj.quantity}: only {stock_level.on_hand} on hand.'
                )
            on_hand_before = stock_level.on_hand
            adjustment = StockAdjustment(
                tenant=tenant,
                stock_level=stock_level,
                adjustment_type='decrease',
                quantity=obj.quantity,
                reason='damage',
                notes=f'Scrap {obj.scrap_number}: {obj.reason}',
                adjusted_by=request.user,
            )
            adjustment.save()
            adjustment.apply_adjustment()
            obj.stock_adjustment = adjustment
            obj.approval_status = 'posted'
            obj.posted_by = request.user
            obj.posted_at = timezone.now()
            obj.save()
            # D-09: enrich audit payload with adjustment + on_hand transition
            emit_audit(
                request, 'post', obj,
                changes=f'approved->posted; adj={adjustment.adjustment_number}; on_hand {on_hand_before}->{stock_level.on_hand}',
            )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('quality_control:scrap_detail', pk=obj.pk)

    messages.success(
        request,
        f'Scrap "{obj.scrap_number}" posted — {obj.quantity} units written off via {adjustment.adjustment_number}.',
    )
    return redirect('quality_control:scrap_detail', pk=obj.pk)
