from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import tenant_admin_required, emit_audit

from warehousing.models import Warehouse

from .models import (
    LabelTemplate, LabelPrintJob,
    ScannerDevice, ScanEvent,
    RFIDTag, RFIDReader, RFIDReadEvent,
    BatchScanSession, BatchScanItem,
)
from .forms import (
    LabelTemplateForm, LabelPrintJobForm,
    ScannerDeviceForm,
    RFIDTagForm, RFIDReaderForm,
    BatchScanSessionForm, BatchScanItemFormSet,
)
from .rendering import render_label_job_pdf


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 1: Label Generation — LabelTemplate CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def label_template_list_view(request):
    tenant = request.tenant
    qs = LabelTemplate.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))

    label_type = request.GET.get('label_type', '')
    if label_type:
        qs = qs.filter(label_type=label_type)

    active = request.GET.get('active', '')
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/label_template_list.html', {
        'templates': page,
        'q': q,
        'current_label_type': label_type,
        'current_active': active,
        'label_type_choices': LabelTemplate.LABEL_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def label_template_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LabelTemplateForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.created_by = request.user
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Label template "{obj.code}" created.')
            return redirect('barcode_rfid:label_template_detail', pk=obj.pk)
    else:
        form = LabelTemplateForm(tenant=tenant)
    return render(request, 'barcode_rfid/label_template_form.html', {
        'form': form, 'title': 'New Label Template',
    })


@login_required
def label_template_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelTemplate, pk=pk, tenant=tenant)
    recent_jobs = obj.print_jobs.all()[:10]
    return render(request, 'barcode_rfid/label_template_detail.html', {
        'template': obj, 'recent_jobs': recent_jobs,
    })


@login_required
@tenant_admin_required
def label_template_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelTemplate, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = LabelTemplateForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Label template "{obj.code}" updated.')
            return redirect('barcode_rfid:label_template_detail', pk=obj.pk)
    else:
        form = LabelTemplateForm(instance=obj, tenant=tenant)
    return render(request, 'barcode_rfid/label_template_form.html', {
        'form': form, 'template': obj, 'title': f'Edit {obj.code}',
    })


@login_required
@tenant_admin_required
@require_POST
def label_template_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelTemplate, pk=pk, tenant=tenant)
    code = obj.code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Label template "{code}" deleted.')
    return redirect('barcode_rfid:label_template_list')


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 1: Label Generation — LabelPrintJob CRUD + transitions
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def label_job_list_view(request):
    tenant = request.tenant
    qs = LabelPrintJob.objects.filter(tenant=tenant).select_related('template', 'printed_by')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(job_number__icontains=q) | Q(target_display__icontains=q) | Q(template__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    target_type = request.GET.get('target_type', '')
    if target_type:
        qs = qs.filter(target_type=target_type)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/label_job_list.html', {
        'jobs': page,
        'q': q,
        'current_status': status,
        'current_target_type': target_type,
        'status_choices': LabelPrintJob.STATUS_CHOICES,
        'target_type_choices': LabelPrintJob.TARGET_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def label_job_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = LabelPrintJobForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.created_by = request.user
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Print job "{obj.job_number}" created.')
            return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    else:
        form = LabelPrintJobForm(tenant=tenant)
    return render(request, 'barcode_rfid/label_job_form.html', {
        'form': form, 'title': 'New Print Job',
    })


@login_required
def label_job_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        LabelPrintJob.objects.select_related('template', 'printed_by', 'created_by'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'barcode_rfid/label_job_detail.html', {'job': obj})


@login_required
@tenant_admin_required
def label_job_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelPrintJob, pk=pk, tenant=tenant)
    if obj.status not in ('draft', 'failed'):
        messages.error(request, 'Only draft or failed jobs can be edited.')
        return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    if request.method == 'POST':
        form = LabelPrintJobForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Print job "{obj.job_number}" updated.')
            return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    else:
        form = LabelPrintJobForm(instance=obj, tenant=tenant)
    return render(request, 'barcode_rfid/label_job_form.html', {
        'form': form, 'job': obj, 'title': f'Edit {obj.job_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def label_job_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelPrintJob, pk=pk, tenant=tenant)
    if obj.status == 'printed':
        messages.error(request, 'Printed jobs cannot be deleted. Cancel instead.')
        return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    num = obj.job_number
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Print job "{num}" deleted.')
    return redirect('barcode_rfid:label_job_list')


def _transition_job(request, pk, new_status, audit_action):
    tenant = request.tenant
    obj = get_object_or_404(LabelPrintJob, pk=pk, tenant=tenant)
    if not obj.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from "{obj.get_status_display()}" to "{new_status}".')
        return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    old = obj.status
    obj.status = new_status
    if new_status == 'printed':
        obj.printed_at = timezone.now()
        obj.printed_by = request.user
    obj.save()
    emit_audit(request, audit_action, obj, changes=f'{old}->{new_status}')
    messages.success(request, f'Job "{obj.job_number}" — {obj.get_status_display()}.')
    return redirect('barcode_rfid:label_job_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def label_job_queue_view(request, pk):
    return _transition_job(request, pk, 'queued', 'queue')


@login_required
@tenant_admin_required
@require_POST
def label_job_start_printing_view(request, pk):
    return _transition_job(request, pk, 'printing', 'start_printing')


@login_required
@tenant_admin_required
@require_POST
def label_job_mark_printed_view(request, pk):
    return _transition_job(request, pk, 'printed', 'mark_printed')


@login_required
@tenant_admin_required
@require_POST
def label_job_mark_failed_view(request, pk):
    return _transition_job(request, pk, 'failed', 'mark_failed')


@login_required
@tenant_admin_required
@require_POST
def label_job_cancel_view(request, pk):
    return _transition_job(request, pk, 'cancelled', 'cancel')


@login_required
def label_job_render_pdf_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(LabelPrintJob, pk=pk, tenant=tenant)
    try:
        pdf_bytes = render_label_job_pdf(obj)
    except Exception as exc:  # pragma: no cover — surfaced to user
        messages.error(request, f'Failed to render PDF: {exc}')
        return redirect('barcode_rfid:label_job_detail', pk=obj.pk)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{obj.job_number}.pdf"'
    return response


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 2: Scanner Device CRUD + Scan Event list
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def device_list_view(request):
    tenant = request.tenant
    qs = ScannerDevice.objects.filter(tenant=tenant).select_related('assigned_to', 'assigned_warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(device_code__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    device_type = request.GET.get('device_type', '')
    if device_type:
        qs = qs.filter(device_type=device_type)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/device_list.html', {
        'devices': page,
        'q': q,
        'current_status': status,
        'current_device_type': device_type,
        'status_choices': ScannerDevice.STATUS_CHOICES,
        'device_type_choices': ScannerDevice.DEVICE_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def device_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = ScannerDeviceForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Device "{obj.device_code}" registered.')
            return redirect('barcode_rfid:device_detail', pk=obj.pk)
    else:
        form = ScannerDeviceForm(tenant=tenant)
    return render(request, 'barcode_rfid/device_form.html', {
        'form': form, 'title': 'Register Scanner Device',
    })


@login_required
def device_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScannerDevice.objects.select_related('assigned_to', 'assigned_warehouse'),
        pk=pk, tenant=tenant,
    )
    recent_scans = obj.scan_events.select_related('user', 'warehouse')[:20]
    return render(request, 'barcode_rfid/device_detail.html', {
        'device': obj, 'recent_scans': recent_scans,
    })


@login_required
@tenant_admin_required
def device_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(ScannerDevice, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = ScannerDeviceForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Device "{obj.device_code}" updated.')
            return redirect('barcode_rfid:device_detail', pk=obj.pk)
    else:
        form = ScannerDeviceForm(instance=obj, tenant=tenant)
    return render(request, 'barcode_rfid/device_form.html', {
        'form': form, 'device': obj, 'title': f'Edit {obj.device_code}',
    })


@login_required
@tenant_admin_required
@require_POST
def device_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(ScannerDevice, pk=pk, tenant=tenant)
    code = obj.device_code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Device "{code}" deleted.')
    return redirect('barcode_rfid:device_list')


@login_required
@tenant_admin_required
@require_POST
def device_rotate_token_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(ScannerDevice, pk=pk, tenant=tenant)
    obj.rotate_token()
    emit_audit(request, 'rotate_token', obj)
    messages.success(request, f'API token rotated for device "{obj.device_code}". Update your device with the new token.')
    return redirect('barcode_rfid:device_detail', pk=obj.pk)


@login_required
def scan_event_list_view(request):
    tenant = request.tenant
    qs = ScanEvent.objects.filter(tenant=tenant).select_related('device', 'user', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(barcode_value__icontains=q) | Q(resolved_display__icontains=q)
        )

    scan_type = request.GET.get('scan_type', '')
    if scan_type:
        qs = qs.filter(scan_type=scan_type)

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/scan_event_list.html', {
        'events': page,
        'q': q,
        'current_scan_type': scan_type,
        'current_status': status,
        'scan_type_choices': ScanEvent.SCAN_TYPE_CHOICES,
        'status_choices': ScanEvent.STATUS_CHOICES,
    })


@login_required
def scan_event_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        ScanEvent.objects.select_related('device', 'user', 'warehouse'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'barcode_rfid/scan_event_detail.html', {'event': obj})


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 3: RFID Tags
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def rfid_tag_list_view(request):
    tenant = request.tenant
    qs = RFIDTag.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(epc_code__icontains=q) | Q(linked_display__icontains=q))

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    tag_type = request.GET.get('tag_type', '')
    if tag_type:
        qs = qs.filter(tag_type=tag_type)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/rfid_tag_list.html', {
        'tags': page,
        'q': q,
        'current_status': status,
        'current_tag_type': tag_type,
        'status_choices': RFIDTag.STATUS_CHOICES,
        'tag_type_choices': RFIDTag.TAG_TYPE_CHOICES,
    })


@login_required
@tenant_admin_required
def rfid_tag_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = RFIDTagForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'RFID tag "{obj.epc_code}" registered.')
            return redirect('barcode_rfid:rfid_tag_detail', pk=obj.pk)
    else:
        form = RFIDTagForm(tenant=tenant)
    return render(request, 'barcode_rfid/rfid_tag_form.html', {
        'form': form, 'title': 'Register RFID Tag',
    })


@login_required
def rfid_tag_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(RFIDTag, pk=pk, tenant=tenant)
    recent_reads = obj.read_events.select_related('reader')[:20]
    return render(request, 'barcode_rfid/rfid_tag_detail.html', {
        'tag': obj, 'recent_reads': recent_reads,
    })


@login_required
@tenant_admin_required
def rfid_tag_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(RFIDTag, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = RFIDTagForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'RFID tag "{obj.epc_code}" updated.')
            return redirect('barcode_rfid:rfid_tag_detail', pk=obj.pk)
    else:
        form = RFIDTagForm(instance=obj, tenant=tenant)
    return render(request, 'barcode_rfid/rfid_tag_form.html', {
        'form': form, 'tag': obj, 'title': f'Edit {obj.epc_code}',
    })


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(RFIDTag, pk=pk, tenant=tenant)
    epc = obj.epc_code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'RFID tag "{epc}" deleted.')
    return redirect('barcode_rfid:rfid_tag_list')


def _transition_tag(request, pk, new_status, audit_action):
    tenant = request.tenant
    obj = get_object_or_404(RFIDTag, pk=pk, tenant=tenant)
    if not obj.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from "{obj.get_status_display()}" to "{new_status}".')
        return redirect('barcode_rfid:rfid_tag_detail', pk=obj.pk)
    old = obj.status
    obj.status = new_status
    obj.save()
    emit_audit(request, audit_action, obj, changes=f'{old}->{new_status}')
    messages.success(request, f'Tag "{obj.epc_code}" — {obj.get_status_display()}.')
    return redirect('barcode_rfid:rfid_tag_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_activate_view(request, pk):
    return _transition_tag(request, pk, 'active', 'activate')


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_deactivate_view(request, pk):
    return _transition_tag(request, pk, 'inactive', 'deactivate')


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_mark_lost_view(request, pk):
    return _transition_tag(request, pk, 'lost', 'mark_lost')


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_mark_damaged_view(request, pk):
    return _transition_tag(request, pk, 'damaged', 'mark_damaged')


@login_required
@tenant_admin_required
@require_POST
def rfid_tag_retire_view(request, pk):
    return _transition_tag(request, pk, 'retired', 'retire')


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 3: RFID Readers
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def rfid_reader_list_view(request):
    tenant = request.tenant
    qs = RFIDReader.objects.filter(tenant=tenant).select_related('warehouse', 'zone')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(reader_code__icontains=q) | Q(name__icontains=q))

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/rfid_reader_list.html', {
        'readers': page,
        'q': q,
        'current_status': status,
        'current_warehouse': warehouse_id,
        'status_choices': RFIDReader.STATUS_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
    })


@login_required
@tenant_admin_required
def rfid_reader_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = RFIDReaderForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Reader "{obj.reader_code}" registered.')
            return redirect('barcode_rfid:rfid_reader_detail', pk=obj.pk)
    else:
        form = RFIDReaderForm(tenant=tenant)
    return render(request, 'barcode_rfid/rfid_reader_form.html', {
        'form': form, 'title': 'Register RFID Reader',
    })


@login_required
def rfid_reader_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        RFIDReader.objects.select_related('warehouse', 'zone'),
        pk=pk, tenant=tenant,
    )
    recent_reads = obj.read_events.select_related('tag')[:20]
    return render(request, 'barcode_rfid/rfid_reader_detail.html', {
        'reader': obj, 'recent_reads': recent_reads,
    })


@login_required
@tenant_admin_required
def rfid_reader_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(RFIDReader, pk=pk, tenant=tenant)
    if request.method == 'POST':
        form = RFIDReaderForm(request.POST, instance=obj, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Reader "{obj.reader_code}" updated.')
            return redirect('barcode_rfid:rfid_reader_detail', pk=obj.pk)
    else:
        form = RFIDReaderForm(instance=obj, tenant=tenant)
    return render(request, 'barcode_rfid/rfid_reader_form.html', {
        'form': form, 'reader': obj, 'title': f'Edit {obj.reader_code}',
    })


@login_required
@tenant_admin_required
@require_POST
def rfid_reader_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(RFIDReader, pk=pk, tenant=tenant)
    code = obj.reader_code
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Reader "{code}" deleted.')
    return redirect('barcode_rfid:rfid_reader_list')


@login_required
def rfid_read_event_list_view(request):
    tenant = request.tenant
    qs = RFIDReadEvent.objects.filter(tenant=tenant).select_related('tag', 'reader')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(tag__epc_code__icontains=q) | Q(reader__reader_code__icontains=q))

    direction = request.GET.get('direction', '')
    if direction:
        qs = qs.filter(direction=direction)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/rfid_read_list.html', {
        'reads': page,
        'q': q,
        'current_direction': direction,
        'direction_choices': RFIDReadEvent.DIRECTION_CHOICES,
    })


@login_required
def rfid_read_event_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        RFIDReadEvent.objects.select_related('tag', 'reader'),
        pk=pk, tenant=tenant,
    )
    return render(request, 'barcode_rfid/rfid_read_detail.html', {'read': obj})


# ═══════════════════════════════════════════════════════════════════════════
# Submodule 4: Batch Scanning
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def batch_session_list_view(request):
    tenant = request.tenant
    qs = BatchScanSession.objects.filter(tenant=tenant).select_related('user', 'warehouse', 'device')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(session_number__icontains=q) | Q(notes__icontains=q))

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    purpose = request.GET.get('purpose', '')
    if purpose:
        qs = qs.filter(purpose=purpose)

    warehouse_id = request.GET.get('warehouse', '')
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'barcode_rfid/batch_session_list.html', {
        'sessions': page,
        'q': q,
        'current_status': status,
        'current_purpose': purpose,
        'current_warehouse': warehouse_id,
        'status_choices': BatchScanSession.STATUS_CHOICES,
        'purpose_choices': BatchScanSession.PURPOSE_CHOICES,
        'warehouses': Warehouse.objects.filter(tenant=tenant, is_active=True),
    })


@login_required
@tenant_admin_required
def batch_session_create_view(request):
    tenant = request.tenant
    if request.method == 'POST':
        form = BatchScanSessionForm(request.POST, tenant=tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.user = request.user
            obj.created_by = request.user
            obj.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Batch session "{obj.session_number}" started.')
            return redirect('barcode_rfid:batch_session_detail', pk=obj.pk)
    else:
        form = BatchScanSessionForm(tenant=tenant)
    return render(request, 'barcode_rfid/batch_session_form.html', {
        'form': form, 'formset': None, 'title': 'Start Batch Scanning Session',
    })


@login_required
def batch_session_detail_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(
        BatchScanSession.objects.select_related('user', 'warehouse', 'zone', 'device', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = obj.items.all()
    return render(request, 'barcode_rfid/batch_session_detail.html', {
        'session': obj, 'items': items,
    })


@login_required
@tenant_admin_required
def batch_session_edit_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(BatchScanSession, pk=pk, tenant=tenant)
    if obj.status != 'active':
        messages.error(request, 'Only active sessions can be edited.')
        return redirect('barcode_rfid:batch_session_detail', pk=obj.pk)
    if request.method == 'POST':
        form = BatchScanSessionForm(request.POST, instance=obj, tenant=tenant)
        formset = BatchScanItemFormSet(request.POST, instance=obj, form_kwargs={'tenant': tenant})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                items = formset.save(commit=False)
                for item in items:
                    item.tenant = tenant
                    item.save()
                for item in formset.deleted_objects:
                    item.delete()
                obj.recalc_total()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Session "{obj.session_number}" updated.')
            return redirect('barcode_rfid:batch_session_detail', pk=obj.pk)
    else:
        form = BatchScanSessionForm(instance=obj, tenant=tenant)
        formset = BatchScanItemFormSet(instance=obj, form_kwargs={'tenant': tenant})
    return render(request, 'barcode_rfid/batch_session_form.html', {
        'form': form, 'formset': formset, 'session': obj, 'title': f'Edit {obj.session_number}',
    })


@login_required
@tenant_admin_required
@require_POST
def batch_session_delete_view(request, pk):
    tenant = request.tenant
    obj = get_object_or_404(BatchScanSession, pk=pk, tenant=tenant)
    num = obj.session_number
    emit_audit(request, 'delete', obj)
    obj.delete()
    messages.success(request, f'Session "{num}" deleted.')
    return redirect('barcode_rfid:batch_session_list')


def _transition_session(request, pk, new_status, audit_action):
    tenant = request.tenant
    obj = get_object_or_404(BatchScanSession, pk=pk, tenant=tenant)
    if not obj.can_transition_to(new_status):
        messages.error(request, f'Cannot transition from "{obj.get_status_display()}" to "{new_status}".')
        return redirect('barcode_rfid:batch_session_detail', pk=obj.pk)
    with transaction.atomic():
        old = obj.status
        obj.status = new_status
        if new_status == 'completed':
            obj.completed_at = timezone.now()
            obj.total_items_scanned = obj.items.count()
        obj.save()
        emit_audit(request, audit_action, obj, changes=f'{old}->{new_status}')
    messages.success(request, f'Session "{obj.session_number}" — {obj.get_status_display()}.')
    return redirect('barcode_rfid:batch_session_detail', pk=obj.pk)


@login_required
@tenant_admin_required
@require_POST
def batch_session_complete_view(request, pk):
    return _transition_session(request, pk, 'completed', 'complete')


@login_required
@tenant_admin_required
@require_POST
def batch_session_cancel_view(request, pk):
    return _transition_session(request, pk, 'cancelled', 'cancel')
