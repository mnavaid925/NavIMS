from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.utils import timezone

from catalog.models import Product
from vendors.models import Vendor
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from core.models import User
from .models import (
    GoodsReceiptNote, GoodsReceiptNoteItem, VendorInvoice,
    ThreeWayMatch, QualityInspection, QualityInspectionItem,
    WarehouseLocation, PutawayTask,
)
from .forms import (
    GoodsReceiptNoteForm, GoodsReceiptNoteItemFormSet,
    VendorInvoiceForm, ThreeWayMatchForm,
    QualityInspectionForm, QualityInspectionItemFormSet,
    WarehouseLocationForm, PutawayTaskForm,
)


# ──────────────────────────────────────────────
# Goods Receipt Note (GRN) CRUD
# ──────────────────────────────────────────────

@login_required
def grn_list_view(request):
    tenant = request.tenant
    queryset = GoodsReceiptNote.objects.filter(tenant=tenant).select_related(
        'purchase_order', 'purchase_order__vendor', 'received_by', 'created_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(grn_number__icontains=q)
            | Q(purchase_order__po_number__icontains=q)
            | Q(purchase_order__vendor__company_name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    po_id = request.GET.get('po', '')
    if po_id:
        queryset = queryset.filter(purchase_order_id=po_id)

    date_from = request.GET.get('date_from', '')
    if date_from:
        queryset = queryset.filter(received_date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        queryset = queryset.filter(received_date__lte=date_to)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    grns = paginator.get_page(page_number)

    context = {
        'grns': grns,
        'q': q,
        'status_choices': GoodsReceiptNote.STATUS_CHOICES,
        'purchase_orders': PurchaseOrder.objects.filter(tenant=tenant).exclude(status__in=['draft', 'cancelled']),
        'current_status': status,
        'current_po': po_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'receiving/grn_list.html', context)


@login_required
def grn_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = GoodsReceiptNoteForm(request.POST, tenant=tenant)
        formset = GoodsReceiptNoteItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            grn = form.save(commit=False)
            grn.created_by = request.user
            grn.received_by = request.user
            grn.save()
            formset.instance = grn
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                if item.po_item_id and not item.product_id:
                    item.product = item.po_item.product
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'GRN "{grn.grn_number}" created successfully.')
            return redirect('receiving:grn_detail', pk=grn.pk)
    else:
        form = GoodsReceiptNoteForm(tenant=tenant)
        formset = GoodsReceiptNoteItemFormSet(prefix='items')

    # Filter querysets for formset
    po_items = PurchaseOrderItem.objects.filter(tenant=tenant)
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['po_item'].queryset = po_items
        f.fields['po_item'].empty_label = '— Select PO Item —'
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Goods Receipt Note',
    }
    return render(request, 'receiving/grn_form.html', context)


@login_required
def grn_detail_view(request, pk):
    tenant = request.tenant
    grn = get_object_or_404(
        GoodsReceiptNote.objects.select_related(
            'purchase_order', 'purchase_order__vendor', 'received_by', 'created_by',
        ),
        pk=pk, tenant=tenant,
    )
    items = grn.items.all().select_related('po_item', 'product')
    inspections = grn.inspections.all().select_related('inspector')
    putaway_tasks = grn.putaway_tasks.all().select_related('product', 'suggested_location', 'assigned_location')

    # Status timeline
    status_order = ['draft', 'inspecting', 'completed']
    status_labels = {
        'draft': 'Draft',
        'inspecting': 'Inspecting',
        'completed': 'Completed',
    }
    current_idx = status_order.index(grn.status) if grn.status in status_order else -1
    timeline = []
    for i, s in enumerate(status_order):
        if grn.status == 'cancelled':
            state = 'cancelled'
        elif i < current_idx:
            state = 'completed'
        elif i == current_idx:
            state = 'current'
        else:
            state = 'upcoming'
        timeline.append({'status': s, 'label': status_labels[s], 'state': state})

    context = {
        'grn': grn,
        'items': items,
        'inspections': inspections,
        'putaway_tasks': putaway_tasks,
        'timeline': timeline,
    }
    return render(request, 'receiving/grn_detail.html', context)


@login_required
def grn_edit_view(request, pk):
    tenant = request.tenant
    grn = get_object_or_404(GoodsReceiptNote, pk=pk, tenant=tenant)

    if grn.status != 'draft':
        messages.warning(request, 'Only draft GRNs can be edited.')
        return redirect('receiving:grn_detail', pk=grn.pk)

    if request.method == 'POST':
        form = GoodsReceiptNoteForm(request.POST, instance=grn, tenant=tenant)
        formset = GoodsReceiptNoteItemFormSet(request.POST, instance=grn, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                if item.po_item_id and not item.product_id:
                    item.product = item.po_item.product
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, f'GRN "{grn.grn_number}" updated successfully.')
            return redirect('receiving:grn_detail', pk=grn.pk)
    else:
        form = GoodsReceiptNoteForm(instance=grn, tenant=tenant)
        formset = GoodsReceiptNoteItemFormSet(instance=grn, prefix='items')

    po_items = PurchaseOrderItem.objects.filter(tenant=tenant)
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['po_item'].queryset = po_items
        f.fields['po_item'].empty_label = '— Select PO Item —'
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Goods Receipt Note',
        'grn': grn,
    }
    return render(request, 'receiving/grn_form.html', context)


@login_required
def grn_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:grn_list')

    grn = get_object_or_404(GoodsReceiptNote, pk=pk, tenant=tenant)
    if grn.status != 'draft':
        messages.warning(request, 'Only draft GRNs can be deleted.')
        return redirect('receiving:grn_detail', pk=grn.pk)

    grn_number = grn.grn_number
    grn.delete()
    messages.success(request, f'GRN "{grn_number}" deleted successfully.')
    return redirect('receiving:grn_list')


@login_required
def grn_transition_view(request, pk, new_status):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:grn_detail', pk=pk)

    grn = get_object_or_404(GoodsReceiptNote, pk=pk, tenant=tenant)

    if not grn.can_transition_to(new_status):
        messages.warning(request, f'Cannot transition GRN from "{grn.get_status_display()}" to "{new_status}".')
        return redirect('receiving:grn_detail', pk=grn.pk)

    grn.status = new_status
    grn.save()

    # If GRN completed, update PO status
    if new_status == 'completed':
        grn.update_po_status()

    status_label = dict(GoodsReceiptNote.STATUS_CHOICES).get(new_status, new_status)
    messages.success(request, f'GRN "{grn.grn_number}" status changed to {status_label}.')
    return redirect('receiving:grn_detail', pk=grn.pk)


# ──────────────────────────────────────────────
# Vendor Invoice CRUD
# ──────────────────────────────────────────────

@login_required
def invoice_list_view(request):
    tenant = request.tenant
    queryset = VendorInvoice.objects.filter(tenant=tenant).select_related(
        'vendor', 'purchase_order', 'created_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(invoice_number__icontains=q) | Q(vendor__company_name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    date_from = request.GET.get('date_from', '')
    if date_from:
        queryset = queryset.filter(invoice_date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        queryset = queryset.filter(invoice_date__lte=date_to)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    invoices = paginator.get_page(page_number)

    context = {
        'invoices': invoices,
        'q': q,
        'status_choices': VendorInvoice.STATUS_CHOICES,
        'vendors': Vendor.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_vendor': vendor_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'receiving/invoice_list.html', context)


@login_required
def invoice_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorInvoiceForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            messages.success(request, f'Vendor Invoice "{invoice.invoice_number}" created successfully.')
            return redirect('receiving:invoice_detail', pk=invoice.pk)
    else:
        form = VendorInvoiceForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Vendor Invoice',
    }
    return render(request, 'receiving/invoice_form.html', context)


@login_required
def invoice_detail_view(request, pk):
    tenant = request.tenant
    invoice = get_object_or_404(
        VendorInvoice.objects.select_related('vendor', 'purchase_order', 'created_by'),
        pk=pk, tenant=tenant,
    )
    matches = invoice.three_way_matches.all().select_related('purchase_order', 'grn')

    context = {
        'invoice': invoice,
        'matches': matches,
    }
    return render(request, 'receiving/invoice_detail.html', context)


@login_required
def invoice_edit_view(request, pk):
    tenant = request.tenant
    invoice = get_object_or_404(VendorInvoice, pk=pk, tenant=tenant)

    if invoice.status not in ('draft', 'pending_match'):
        messages.warning(request, 'Only draft or pending match invoices can be edited.')
        return redirect('receiving:invoice_detail', pk=invoice.pk)

    if request.method == 'POST':
        form = VendorInvoiceForm(request.POST, request.FILES, instance=invoice, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Vendor Invoice "{invoice.invoice_number}" updated successfully.')
            return redirect('receiving:invoice_detail', pk=invoice.pk)
    else:
        form = VendorInvoiceForm(instance=invoice, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Vendor Invoice',
        'invoice': invoice,
    }
    return render(request, 'receiving/invoice_form.html', context)


@login_required
def invoice_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:invoice_list')

    invoice = get_object_or_404(VendorInvoice, pk=pk, tenant=tenant)
    if invoice.status != 'draft':
        messages.warning(request, 'Only draft invoices can be deleted.')
        return redirect('receiving:invoice_detail', pk=invoice.pk)

    inv_number = invoice.invoice_number
    invoice.delete()
    messages.success(request, f'Vendor Invoice "{inv_number}" deleted successfully.')
    return redirect('receiving:invoice_list')


@login_required
def invoice_transition_view(request, pk, new_status):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:invoice_detail', pk=pk)

    invoice = get_object_or_404(VendorInvoice, pk=pk, tenant=tenant)

    if not invoice.can_transition_to(new_status):
        messages.warning(request, f'Cannot transition invoice from "{invoice.get_status_display()}" to "{new_status}".')
        return redirect('receiving:invoice_detail', pk=invoice.pk)

    invoice.status = new_status
    invoice.save()

    status_label = dict(VendorInvoice.STATUS_CHOICES).get(new_status, new_status)
    messages.success(request, f'Invoice "{invoice.invoice_number}" status changed to {status_label}.')
    return redirect('receiving:invoice_detail', pk=invoice.pk)


# ──────────────────────────────────────────────
# Three-Way Match
# ──────────────────────────────────────────────

@login_required
def match_list_view(request):
    tenant = request.tenant
    queryset = ThreeWayMatch.objects.filter(tenant=tenant).select_related(
        'purchase_order', 'grn', 'vendor_invoice', 'created_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(match_number__icontains=q) | Q(purchase_order__po_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    matches = paginator.get_page(page_number)

    context = {
        'matches': matches,
        'q': q,
        'status_choices': ThreeWayMatch.MATCH_STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'receiving/match_list.html', context)


@login_required
def match_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ThreeWayMatchForm(request.POST, tenant=tenant)
        if form.is_valid():
            match = form.save(commit=False)
            match.created_by = request.user
            match.save()
            match.perform_match()
            messages.success(request, f'Three-Way Match "{match.match_number}" created and analyzed.')
            return redirect('receiving:match_detail', pk=match.pk)
    else:
        form = ThreeWayMatchForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Three-Way Match',
    }
    return render(request, 'receiving/match_form.html', context)


@login_required
def match_detail_view(request, pk):
    tenant = request.tenant
    match = get_object_or_404(
        ThreeWayMatch.objects.select_related(
            'purchase_order', 'purchase_order__vendor', 'grn', 'vendor_invoice',
            'created_by', 'resolved_by',
        ),
        pk=pk, tenant=tenant,
    )

    # Build comparison data
    po = match.purchase_order
    grn = match.grn
    po_items = po.items.all().select_related('product')
    grn_items = grn.items.all().select_related('po_item', 'product')

    # Build lookup dict to avoid N+1 queries
    grn_item_by_po = {item.po_item_id: item for item in grn_items}

    comparison = []
    for po_item in po_items:
        grn_item = grn_item_by_po.get(po_item.pk)
        comparison.append({
            'product': po_item.product,
            'po_qty': po_item.quantity,
            'po_price': po_item.unit_price,
            'po_total': po_item.line_total,
            'grn_qty': grn_item.quantity_received if grn_item else 0,
            'qty_match': (grn_item.quantity_received == po_item.quantity) if grn_item else False,
        })

    context = {
        'match': match,
        'comparison': comparison,
    }
    return render(request, 'receiving/match_detail.html', context)


@login_required
def match_resolve_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:match_detail', pk=pk)

    match = get_object_or_404(ThreeWayMatch, pk=pk, tenant=tenant)

    if match.status not in ('discrepancy', 'pending'):
        messages.warning(request, 'Only pending or discrepancy matches can be resolved.')
        return redirect('receiving:match_detail', pk=match.pk)

    notes = request.POST.get('resolution_notes', '')
    match.status = 'resolved'
    match.resolved_by = request.user
    match.resolved_at = timezone.now()
    if notes:
        match.discrepancy_notes = notes
    match.save()

    messages.success(request, f'Match "{match.match_number}" has been resolved.')
    return redirect('receiving:match_detail', pk=match.pk)


@login_required
def match_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:match_list')

    match = get_object_or_404(ThreeWayMatch, pk=pk, tenant=tenant)
    if match.status not in ('pending', 'discrepancy'):
        messages.warning(request, 'Only pending or discrepancy matches can be deleted.')
        return redirect('receiving:match_detail', pk=match.pk)

    match_number = match.match_number
    match.delete()
    messages.success(request, f'Match "{match_number}" deleted successfully.')
    return redirect('receiving:match_list')


# ──────────────────────────────────────────────
# Quality Inspection
# ──────────────────────────────────────────────

@login_required
def inspection_list_view(request):
    tenant = request.tenant
    queryset = QualityInspection.objects.filter(tenant=tenant).select_related(
        'grn', 'inspector', 'created_by',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(inspection_number__icontains=q) | Q(grn__grn_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    inspections = paginator.get_page(page_number)

    context = {
        'inspections': inspections,
        'q': q,
        'status_choices': QualityInspection.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'receiving/inspection_list.html', context)


@login_required
def inspection_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = QualityInspectionForm(request.POST, tenant=tenant)
        formset = QualityInspectionItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            inspection = form.save(commit=False)
            inspection.created_by = request.user
            inspection.save()
            formset.instance = inspection
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                if item.grn_item_id and not item.product_id:
                    item.product = item.grn_item.product
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()

            # Transition GRN to inspecting
            grn = inspection.grn
            if grn.can_transition_to('inspecting'):
                grn.status = 'inspecting'
                grn.save()

            messages.success(request, f'Inspection "{inspection.inspection_number}" created successfully.')
            return redirect('receiving:inspection_detail', pk=inspection.pk)
    else:
        form = QualityInspectionForm(tenant=tenant)
        formset = QualityInspectionItemFormSet(prefix='items')

    grn_items = GoodsReceiptNoteItem.objects.filter(tenant=tenant)
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['grn_item'].queryset = grn_items
        f.fields['grn_item'].empty_label = '— Select GRN Item —'
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Quality Inspection',
    }
    return render(request, 'receiving/inspection_form.html', context)


@login_required
def inspection_detail_view(request, pk):
    tenant = request.tenant
    inspection = get_object_or_404(
        QualityInspection.objects.select_related('grn', 'inspector', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = inspection.items.all().select_related('grn_item', 'product')

    context = {
        'inspection': inspection,
        'items': items,
    }
    return render(request, 'receiving/inspection_detail.html', context)


@login_required
def inspection_edit_view(request, pk):
    tenant = request.tenant
    inspection = get_object_or_404(QualityInspection, pk=pk, tenant=tenant)

    if inspection.status not in ('pending', 'in_progress'):
        messages.warning(request, 'Only pending or in-progress inspections can be edited.')
        return redirect('receiving:inspection_detail', pk=inspection.pk)

    if request.method == 'POST':
        form = QualityInspectionForm(request.POST, instance=inspection, tenant=tenant)
        formset = QualityInspectionItemFormSet(request.POST, instance=inspection, prefix='items')
        if form.is_valid() and formset.is_valid():
            form.save()
            items = formset.save(commit=False)
            for item in items:
                item.tenant = tenant
                if item.grn_item_id and not item.product_id:
                    item.product = item.grn_item.product
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()

            if inspection.status == 'pending':
                inspection.status = 'in_progress'
                inspection.save()

            messages.success(request, f'Inspection "{inspection.inspection_number}" updated successfully.')
            return redirect('receiving:inspection_detail', pk=inspection.pk)
    else:
        form = QualityInspectionForm(instance=inspection, tenant=tenant)
        formset = QualityInspectionItemFormSet(instance=inspection, prefix='items')

    grn_items = GoodsReceiptNoteItem.objects.filter(tenant=tenant)
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['grn_item'].queryset = grn_items
        f.fields['grn_item'].empty_label = '— Select GRN Item —'
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Quality Inspection',
        'inspection': inspection,
    }
    return render(request, 'receiving/inspection_form.html', context)


@login_required
def inspection_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:inspection_list')

    inspection = get_object_or_404(QualityInspection, pk=pk, tenant=tenant)
    if inspection.status != 'pending':
        messages.warning(request, 'Only pending inspections can be deleted.')
        return redirect('receiving:inspection_detail', pk=inspection.pk)

    insp_number = inspection.inspection_number
    inspection.delete()
    messages.success(request, f'Inspection "{insp_number}" deleted successfully.')
    return redirect('receiving:inspection_list')


@login_required
def inspection_complete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:inspection_detail', pk=pk)

    inspection = get_object_or_404(QualityInspection, pk=pk, tenant=tenant)

    if inspection.status == 'completed':
        messages.warning(request, 'This inspection is already completed.')
        return redirect('receiving:inspection_detail', pk=inspection.pk)

    inspection.status = 'completed'
    inspection.save()
    messages.success(request, f'Inspection "{inspection.inspection_number}" marked as completed.')
    return redirect('receiving:inspection_detail', pk=inspection.pk)


# ──────────────────────────────────────────────
# Warehouse Location CRUD
# ──────────────────────────────────────────────

@login_required
def location_list_view(request):
    tenant = request.tenant
    queryset = WarehouseLocation.objects.filter(tenant=tenant).select_related('parent')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))

    location_type = request.GET.get('type', '')
    if location_type:
        queryset = queryset.filter(location_type=location_type)

    active_filter = request.GET.get('active', '')
    if active_filter == 'active':
        queryset = queryset.filter(is_active=True)
    elif active_filter == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    locations = paginator.get_page(page_number)

    context = {
        'locations': locations,
        'q': q,
        'type_choices': WarehouseLocation.LOCATION_TYPE_CHOICES,
        'current_type': location_type,
        'current_active': active_filter,
    }
    return render(request, 'receiving/location_list.html', context)


@login_required
def location_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = WarehouseLocationForm(request.POST, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Location "{form.instance.code}" created successfully.')
            return redirect('receiving:location_detail', pk=form.instance.pk)
    else:
        form = WarehouseLocationForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Warehouse Location',
    }
    return render(request, 'receiving/location_form.html', context)


@login_required
def location_detail_view(request, pk):
    tenant = request.tenant
    location = get_object_or_404(
        WarehouseLocation.objects.select_related('parent'),
        pk=pk, tenant=tenant,
    )
    children = location.children.all()
    putaway_tasks = PutawayTask.objects.filter(
        tenant=tenant,
    ).filter(
        Q(suggested_location=location) | Q(assigned_location=location)
    ).select_related('product', 'grn')[:10]

    context = {
        'location': location,
        'children': children,
        'putaway_tasks': putaway_tasks,
    }
    return render(request, 'receiving/location_detail.html', context)


@login_required
def location_edit_view(request, pk):
    tenant = request.tenant
    location = get_object_or_404(WarehouseLocation, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = WarehouseLocationForm(request.POST, instance=location, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Location "{location.code}" updated successfully.')
            return redirect('receiving:location_detail', pk=location.pk)
    else:
        form = WarehouseLocationForm(instance=location, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Warehouse Location',
        'location': location,
    }
    return render(request, 'receiving/location_form.html', context)


@login_required
def location_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:location_list')

    location = get_object_or_404(WarehouseLocation, pk=pk, tenant=tenant)

    if location.children.exists():
        messages.warning(request, 'Cannot delete a location that has child locations.')
        return redirect('receiving:location_detail', pk=location.pk)

    code = location.code
    location.delete()
    messages.success(request, f'Location "{code}" deleted successfully.')
    return redirect('receiving:location_list')


# ──────────────────────────────────────────────
# Putaway Task CRUD
# ──────────────────────────────────────────────

@login_required
def putaway_list_view(request):
    tenant = request.tenant
    queryset = PutawayTask.objects.filter(tenant=tenant).select_related(
        'grn', 'product', 'suggested_location', 'assigned_location', 'assigned_to',
    )

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(task_number__icontains=q) | Q(product__name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    tasks = paginator.get_page(page_number)

    context = {
        'tasks': tasks,
        'q': q,
        'status_choices': PutawayTask.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'receiving/putaway_list.html', context)


@login_required
def putaway_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = PutawayTaskForm(request.POST, tenant=tenant)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            # Auto-suggest location if not specified
            if not task.suggested_location:
                task.suggested_location = PutawayTask.suggest_location(tenant, task.quantity)
            task.save()
            messages.success(request, f'Putaway Task "{task.task_number}" created successfully.')
            return redirect('receiving:putaway_detail', pk=task.pk)
    else:
        form = PutawayTaskForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Create Putaway Task',
    }
    return render(request, 'receiving/putaway_form.html', context)


@login_required
def putaway_detail_view(request, pk):
    tenant = request.tenant
    task = get_object_or_404(
        PutawayTask.objects.select_related(
            'grn', 'grn_item', 'product', 'suggested_location',
            'assigned_location', 'assigned_to', 'created_by',
        ),
        pk=pk, tenant=tenant,
    )

    # Status timeline
    status_order = ['pending', 'assigned', 'in_progress', 'completed']
    status_labels = {
        'pending': 'Pending',
        'assigned': 'Assigned',
        'in_progress': 'In Progress',
        'completed': 'Completed',
    }
    current_idx = status_order.index(task.status) if task.status in status_order else -1
    timeline = []
    for i, s in enumerate(status_order):
        if task.status == 'cancelled':
            state = 'cancelled'
        elif i < current_idx:
            state = 'completed'
        elif i == current_idx:
            state = 'current'
        else:
            state = 'upcoming'
        timeline.append({'status': s, 'label': status_labels[s], 'state': state})

    context = {
        'task': task,
        'timeline': timeline,
    }
    return render(request, 'receiving/putaway_detail.html', context)


@login_required
def putaway_edit_view(request, pk):
    tenant = request.tenant
    task = get_object_or_404(PutawayTask, pk=pk, tenant=tenant)

    if task.status not in ('pending', 'assigned'):
        messages.warning(request, 'Only pending or assigned tasks can be edited.')
        return redirect('receiving:putaway_detail', pk=task.pk)

    if request.method == 'POST':
        form = PutawayTaskForm(request.POST, instance=task, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Putaway Task "{task.task_number}" updated successfully.')
            return redirect('receiving:putaway_detail', pk=task.pk)
    else:
        form = PutawayTaskForm(instance=task, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Putaway Task',
        'task': task,
    }
    return render(request, 'receiving/putaway_form.html', context)


@login_required
def putaway_delete_view(request, pk):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:putaway_list')

    task = get_object_or_404(PutawayTask, pk=pk, tenant=tenant)
    if task.status != 'pending':
        messages.warning(request, 'Only pending tasks can be deleted.')
        return redirect('receiving:putaway_detail', pk=task.pk)

    task_number = task.task_number
    task.delete()
    messages.success(request, f'Putaway Task "{task_number}" deleted successfully.')
    return redirect('receiving:putaway_list')


@login_required
def putaway_transition_view(request, pk, new_status):
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:putaway_detail', pk=pk)

    task = get_object_or_404(PutawayTask, pk=pk, tenant=tenant)

    if not task.can_transition_to(new_status):
        messages.warning(request, f'Cannot transition task from "{task.get_status_display()}" to "{new_status}".')
        return redirect('receiving:putaway_detail', pk=task.pk)

    task.status = new_status
    if new_status == 'completed':
        task.completed_at = timezone.now()
        # Update warehouse location quantity
        location = task.assigned_location or task.suggested_location
        if location:
            location.current_quantity += task.quantity
            location.save()
    task.save()

    status_label = dict(PutawayTask.STATUS_CHOICES).get(new_status, new_status)
    messages.success(request, f'Putaway Task "{task.task_number}" status changed to {status_label}.')
    return redirect('receiving:putaway_detail', pk=task.pk)


@login_required
def putaway_generate_view(request, grn_pk):
    """Auto-generate putaway tasks for all items in a completed GRN."""
    tenant = request.tenant
    if request.method != 'POST':
        return redirect('receiving:grn_detail', pk=grn_pk)

    grn = get_object_or_404(GoodsReceiptNote, pk=grn_pk, tenant=tenant)

    if grn.status != 'completed':
        messages.warning(request, 'Putaway tasks can only be generated for completed GRNs.')
        return redirect('receiving:grn_detail', pk=grn.pk)

    created_count = 0
    for grn_item in grn.items.all().select_related('product'):
        # Skip if putaway task already exists for this item
        if grn_item.putaway_tasks.exists():
            continue

        suggested = PutawayTask.suggest_location(tenant, grn_item.quantity_received)
        PutawayTask.objects.create(
            tenant=tenant,
            grn=grn,
            grn_item=grn_item,
            product=grn_item.product,
            quantity=grn_item.quantity_received,
            suggested_location=suggested,
            created_by=request.user,
        )
        created_count += 1

    if created_count > 0:
        messages.success(request, f'{created_count} putaway task(s) generated for GRN "{grn.grn_number}".')
    else:
        messages.info(request, 'No new putaway tasks needed. All items already have tasks assigned.')
    return redirect('receiving:grn_detail', pk=grn.pk)
