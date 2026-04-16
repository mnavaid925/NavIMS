import json
from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.conf import settings as django_settings

from catalog.models import Product
from core.models import AuditLog
from vendors.models import Vendor
from .models import (
    PurchaseOrder, PurchaseOrderItem, ApprovalRule,
    PurchaseOrderApproval, PurchaseOrderDispatch,
)
from .forms import (
    PurchaseOrderForm,
    PurchaseOrderItemFormSet,
    ApprovalRuleForm,
    PurchaseOrderApprovalForm,
    PurchaseOrderDispatchForm,
)


# ──────────────────────────────────────────────
# Decorators / helpers
# ──────────────────────────────────────────────

def tenant_admin_required(view_func):
    """Require an authenticated tenant admin (D-02).

    Why: approve / reject / dispatch / close / cancel / reopen / delete
    and approval-rule mutations are high-impact and must not be callable
    by standard tenant users.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and getattr(user, 'is_tenant_admin', False)):
            messages.error(
                request,
                'You do not have permission to perform this action.',
            )
            return redirect('purchase_orders:po_list')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _audit(request, action, po, changes=None):
    """Write an AuditLog row for a PO mutation (D-12)."""
    AuditLog.objects.create(
        tenant=request.tenant,
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name='PurchaseOrder',
        object_id=str(po.pk),
        changes=json.dumps(changes or {}, default=str),
        ip_address=request.META.get('REMOTE_ADDR') or None,
    )


# ──────────────────────────────────────────────
# Purchase Order CRUD views
# ──────────────────────────────────────────────

@login_required
def po_list_view(request):
    tenant = request.tenant
    queryset = (
        PurchaseOrder.objects.filter(tenant=tenant)
        .select_related('vendor', 'created_by')
        .prefetch_related(Prefetch('items'))  # D-10: cache items for total props
    )

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(po_number__icontains=q) | Q(vendor__company_name__icontains=q)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    # Filter by vendor
    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        try:
            queryset = queryset.filter(vendor_id=int(vendor_id))
        except (TypeError, ValueError):
            vendor_id = ''

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    if date_from:
        queryset = queryset.filter(order_date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        queryset = queryset.filter(order_date__lte=date_to)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    purchase_orders = paginator.get_page(page_number)

    # Wire `items` cache onto each paged PO so grand_total is query-free (D-10)
    for po in purchase_orders:
        po._items_cache = list(po.items.all())

    context = {
        'purchase_orders': purchase_orders,
        'q': q,
        'status_choices': PurchaseOrder.STATUS_CHOICES,
        # D-14: align vendor queryset with PO create form
        'vendors': Vendor.objects.filter(
            tenant=tenant, is_active=True, status='active',
        ),
        'current_status': status,
        'current_vendor': vendor_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'purchase_orders/po_list.html', context)


@login_required
def po_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, tenant=tenant)
        formset = PurchaseOrderItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                po = form.save(commit=False)
                po.created_by = request.user
                po.save()
                formset.instance = po
                items = formset.save(commit=False)
                for item in items:
                    item.tenant = tenant
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()
            _audit(request, 'po.create', po, {'po_number': po.po_number})
            messages.success(request, f'Purchase Order "{po.po_number}" created successfully.')
            return redirect('purchase_orders:po_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm(tenant=tenant)
        formset = PurchaseOrderItemFormSet(prefix='items')

    # Filter product queryset for formset
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create Purchase Order',
    }
    return render(request, 'purchase_orders/po_form.html', context)


@login_required
def po_detail_view(request, pk):
    tenant = request.tenant
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('vendor', 'created_by'),
        pk=pk, tenant=tenant,
    )
    items = po.items.all().select_related('product')
    approvals = po.approvals.all().select_related('approver')
    dispatches = po.dispatches.all().select_related('sent_by')
    approval_form = PurchaseOrderApprovalForm()

    # Status timeline data — D-15: include partially_received
    status_order = [
        'draft', 'pending_approval', 'approved', 'sent',
        'partially_received', 'received', 'closed',
    ]
    status_labels = {
        'draft': 'Draft',
        'pending_approval': 'Pending Approval',
        'approved': 'Approved',
        'sent': 'Sent',
        'partially_received': 'Partially Received',
        'received': 'Received',
        'closed': 'Closed',
    }
    current_idx = status_order.index(po.status) if po.status in status_order else -1
    timeline = []
    for i, s in enumerate(status_order):
        if po.status == 'cancelled':
            state = 'cancelled'
        elif i < current_idx:
            state = 'completed'
        elif i == current_idx:
            state = 'current'
        else:
            state = 'upcoming'
        timeline.append({'status': s, 'label': status_labels[s], 'state': state})

    context = {
        'po': po,
        'items': items,
        'approvals': approvals,
        'dispatches': dispatches,
        'approval_form': approval_form,
        'timeline': timeline,
    }
    return render(request, 'purchase_orders/po_detail.html', context)


@login_required
def po_edit_view(request, pk):
    tenant = request.tenant
    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if po.status != 'draft':
        messages.warning(request, 'Only draft purchase orders can be edited.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po, tenant=tenant)
        formset = PurchaseOrderItemFormSet(request.POST, instance=po, prefix='items')
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                items = formset.save(commit=False)
                for item in items:
                    item.tenant = tenant
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()
            _audit(request, 'po.edit', po, {'po_number': po.po_number})
            messages.success(request, f'Purchase Order "{po.po_number}" updated successfully.')
            return redirect('purchase_orders:po_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm(instance=po, tenant=tenant)
        formset = PurchaseOrderItemFormSet(instance=po, prefix='items')

    # Filter product queryset for formset
    products = Product.objects.filter(tenant=tenant, status='active')
    for f in formset.forms:
        f.fields['product'].queryset = products
        f.fields['product'].empty_label = '— Select Product —'

    context = {
        'form': form,
        'formset': formset,
        'title': 'Edit Purchase Order',
        'po': po,
    }
    return render(request, 'purchase_orders/po_form.html', context)


@login_required
def po_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_list')

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if po.status != 'draft':
        messages.warning(request, 'Only draft purchase orders can be deleted.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    # Allow creator OR tenant admin (D-02 / D-09)
    is_admin = getattr(request.user, 'is_tenant_admin', False)
    if po.created_by_id != request.user.id and not is_admin:
        messages.error(request, 'You do not have permission to delete this PO.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    po_number = po.po_number
    _audit(request, 'po.delete', po, {'po_number': po_number})
    po.delete()
    messages.success(request, f'Purchase Order "{po_number}" deleted successfully.')
    return redirect('purchase_orders:po_list')


# ──────────────────────────────────────────────
# Status transition views
# ──────────────────────────────────────────────

@login_required
def po_submit_for_approval_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if not po.items.exists():
        messages.warning(request, 'Cannot submit a purchase order with no line items.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    if not po.can_transition_to('pending_approval'):
        messages.warning(request, f'Cannot submit PO in "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    with transaction.atomic():
        # D-01: clear stale approvals from previous rejection cycles so the
        #       PO can be approved on this new cycle.
        po.approvals.all().delete()
        po.status = 'pending_approval'
        po.save()
    _audit(request, 'po.submit', po, {'po_number': po.po_number})
    messages.success(request, f'Purchase Order "{po.po_number}" submitted for approval.')
    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_approve_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if po.status != 'pending_approval':
        messages.warning(request, 'This purchase order is not pending approval.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    # D-03: creators cannot self-approve (SOD)
    if po.created_by_id == request.user.id:
        messages.warning(request, 'Creators cannot approve their own purchase orders.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    # Check if user already approved
    if po.approvals.filter(approver=request.user).exists():
        messages.warning(request, 'You have already submitted your approval for this PO.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    form = PurchaseOrderApprovalForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            approval = form.save(commit=False)
            approval.tenant = tenant
            approval.purchase_order = po
            approval.approver = request.user
            approval.decision = 'approved'
            approval.save()

            # Check if approval threshold is met
            status_now = po.approval_status
            if status_now == 'approved':
                po.status = 'approved'
                po.save()

        _audit(request, 'po.approve', po, {
            'po_number': po.po_number,
            'threshold_met': status_now == 'approved',
        })
        if status_now == 'approved':
            messages.success(request, f'Purchase Order "{po.po_number}" has been approved.')
        else:
            messages.success(request, 'Your approval has been recorded. Awaiting additional approvals.')
    else:
        messages.error(request, 'Invalid approval form.')

    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_reject_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if po.status != 'pending_approval':
        messages.warning(request, 'This purchase order is not pending approval.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    form = PurchaseOrderApprovalForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            # Remove any existing approval by this user
            po.approvals.filter(approver=request.user).delete()

            approval = form.save(commit=False)
            approval.tenant = tenant
            approval.purchase_order = po
            approval.approver = request.user
            approval.decision = 'rejected'
            approval.save()

            po.status = 'draft'
            po.save()
        _audit(request, 'po.reject', po, {'po_number': po.po_number})
        messages.success(request, f'Purchase Order "{po.po_number}" has been rejected and returned to draft.')
    else:
        # D-13: surface invalid-form error
        messages.error(
            request,
            'Invalid rejection form — a decision value is required.',
        )

    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_dispatch_view(request, pk):
    tenant = request.tenant
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('vendor', 'created_by'),
        pk=pk, tenant=tenant,
    )

    if not po.can_transition_to('sent'):
        messages.warning(request, f'Cannot dispatch PO from "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    items = po.items.all().select_related('product')

    if request.method == 'POST':
        form = PurchaseOrderDispatchForm(request.POST)
        if form.is_valid():
            # D-04: recipient is ALWAYS the vendor's on-file email — NEVER user-controlled.
            vendor_email = (po.vendor.email or '').strip()
            dispatch_method = form.cleaned_data['dispatch_method']

            # Email body (plain text)
            lines = [
                f'Purchase Order: {po.po_number}',
                f'Date: {po.order_date}',
                f'Payment Terms: {po.get_payment_terms_display()}',
                '',
                'Line Items:',
                '-' * 50,
            ]
            for item in items:
                lines.append(
                    f'  {item.product.name} (SKU: {item.product.sku}) '
                    f'x {item.quantity} @ ${item.unit_price} = ${item.line_total}'
                )
            lines.extend([
                '-' * 50,
                f'Subtotal: ${po.subtotal}',
                f'Tax: ${po.tax_total}',
                f'Discount: -${po.discount_total}',
                f'Grand Total: ${po.grand_total}',
                '',
            ])
            if po.shipping_address:
                lines.append(f'Ship To: {po.shipping_address}')
            if po.notes:
                lines.append(f'Notes: {po.notes}')
            from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@navims.local')

            # D-05: advance status only AFTER email succeeds.
            email_ok = True
            email_error = None
            if dispatch_method == 'email':
                if not vendor_email:
                    messages.error(
                        request,
                        'Vendor has no email on file. Update vendor record or choose another dispatch method.',
                    )
                    return redirect('purchase_orders:po_detail', pk=po.pk)
                try:
                    send_mail(
                        subject=f'Purchase Order {po.po_number} from {tenant.name}',
                        message='\n'.join(lines),
                        from_email=from_email,
                        recipient_list=[vendor_email],
                        fail_silently=False,
                    )
                except Exception as exc:
                    email_ok = False
                    email_error = str(exc)

            if not email_ok:
                messages.error(
                    request,
                    f'Dispatch email failed: {email_error}. PO status unchanged; please retry.',
                )
                return redirect('purchase_orders:po_detail', pk=po.pk)

            # Persist dispatch + advance status atomically only on success
            with transaction.atomic():
                dispatch = form.save(commit=False)
                dispatch.tenant = tenant
                dispatch.purchase_order = po
                dispatch.sent_by = request.user
                dispatch.sent_to_email = vendor_email if dispatch_method == 'email' else ''
                dispatch.save()
                po.status = 'sent'
                po.save()

            _audit(request, 'po.dispatch', po, {
                'po_number': po.po_number,
                'method': dispatch_method,
                'recipient': dispatch.sent_to_email,
            })

            if dispatch_method == 'email':
                messages.success(
                    request,
                    f'Purchase Order "{po.po_number}" dispatched via email to {vendor_email}.',
                )
            else:
                messages.success(
                    request,
                    f'Purchase Order "{po.po_number}" dispatched via {dispatch.get_dispatch_method_display()}.',
                )
            return redirect('purchase_orders:po_detail', pk=po.pk)
    else:
        form = PurchaseOrderDispatchForm(initial={'dispatch_method': 'email'})

    context = {
        'form': form,
        'po': po,
        'items': items,
    }
    return render(request, 'purchase_orders/po_dispatch.html', context)


@login_required
@tenant_admin_required
def po_mark_received_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if not po.can_transition_to('received'):
        messages.warning(request, f'Cannot mark PO as received from "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    po.status = 'received'
    po.save()
    _audit(request, 'po.mark_received', po, {'po_number': po.po_number})
    messages.success(request, f'Purchase Order "{po.po_number}" marked as fully received.')
    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_close_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if not po.can_transition_to('closed'):
        messages.warning(request, f'Cannot close PO from "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    po.status = 'closed'
    po.save()
    _audit(request, 'po.close', po, {'po_number': po.po_number})
    messages.success(request, f'Purchase Order "{po.po_number}" has been closed.')
    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_cancel_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if not po.can_transition_to('cancelled'):
        messages.warning(request, f'Cannot cancel PO in "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    po.status = 'cancelled'
    po.save()
    _audit(request, 'po.cancel', po, {'po_number': po.po_number})
    messages.success(request, f'Purchase Order "{po.po_number}" has been cancelled.')
    return redirect('purchase_orders:po_detail', pk=po.pk)


@login_required
@tenant_admin_required
def po_reopen_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:po_detail', pk=pk)

    po = get_object_or_404(PurchaseOrder, pk=pk, tenant=tenant)

    if not po.can_transition_to('draft'):
        messages.warning(request, f'Cannot reopen PO from "{po.get_status_display()}" status.')
        return redirect('purchase_orders:po_detail', pk=po.pk)

    with transaction.atomic():
        po.status = 'draft'
        po.approvals.all().delete()
        po.save()
    _audit(request, 'po.reopen', po, {'po_number': po.po_number})
    messages.success(request, f'Purchase Order "{po.po_number}" reopened as draft.')
    return redirect('purchase_orders:po_detail', pk=po.pk)


# ──────────────────────────────────────────────
# Approval Rules CRUD
# ──────────────────────────────────────────────

@login_required
@tenant_admin_required
def approval_rule_list_view(request):
    tenant = request.tenant
    queryset = ApprovalRule.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(name__icontains=q)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    rules = paginator.get_page(page_number)

    context = {
        'rules': rules,
        'q': q,
    }
    return render(request, 'purchase_orders/approval_rule_list.html', context)


@login_required
@tenant_admin_required
def approval_rule_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = ApprovalRuleForm(request.POST, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Approval rule "{form.instance.name}" created successfully.')
            return redirect('purchase_orders:approval_rule_list')
    else:
        form = ApprovalRuleForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Approval Rule',
    }
    return render(request, 'purchase_orders/approval_rule_form.html', context)


@login_required
@tenant_admin_required
def approval_rule_edit_view(request, pk):
    tenant = request.tenant
    rule = get_object_or_404(ApprovalRule, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = ApprovalRuleForm(request.POST, instance=rule, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Approval rule "{rule.name}" updated successfully.')
            return redirect('purchase_orders:approval_rule_list')
    else:
        form = ApprovalRuleForm(instance=rule, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Approval Rule',
        'rule': rule,
    }
    return render(request, 'purchase_orders/approval_rule_form.html', context)


@login_required
@tenant_admin_required
def approval_rule_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('purchase_orders:approval_rule_list')

    rule = get_object_or_404(ApprovalRule, pk=pk, tenant=tenant)
    rule.delete()
    messages.success(request, 'Approval rule deleted successfully.')
    return redirect('purchase_orders:approval_rule_list')


# ──────────────────────────────────────────────
# Pending Approvals view
# ──────────────────────────────────────────────

@login_required
@tenant_admin_required
def approval_list_view(request):
    tenant = request.tenant

    # POs that are pending approval and current user has not yet approved/rejected
    queryset = (
        PurchaseOrder.objects.filter(tenant=tenant, status='pending_approval')
        .exclude(approvals__approver=request.user)
        # D-03: do not surface PO a tenant-admin created themselves (can't self-approve anyway)
        .exclude(created_by=request.user)
        .select_related('vendor', 'created_by')
    )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    pending_orders = paginator.get_page(page_number)

    context = {
        'pending_orders': pending_orders,
    }
    return render(request, 'purchase_orders/approval_list.html', context)
