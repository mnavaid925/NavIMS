from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q

from .decorators import tenant_admin_required, emit_audit
from .models import Vendor, VendorPerformance, VendorContract, VendorCommunication
from .forms import (
    VendorForm,
    VendorPerformanceForm,
    VendorContractForm,
    VendorCommunicationForm,
)


# ──────────────────────────────────────────────
# Vendor CRUD views
# ──────────────────────────────────────────────

@login_required
def vendor_list_view(request):
    tenant = request.tenant
    queryset = Vendor.objects.filter(tenant=tenant)

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(company_name__icontains=q) | Q(email__icontains=q) | Q(tax_id__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    vendor_type = request.GET.get('vendor_type', '')
    if vendor_type:
        queryset = queryset.filter(vendor_type=vendor_type)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    vendors = paginator.get_page(page_number)

    context = {
        'vendors': vendors,
        'q': q,
        'status_choices': Vendor.STATUS_CHOICES,
        'vendor_type_choices': Vendor.VENDOR_TYPE_CHOICES,
        'current_status': status,
        'current_vendor_type': vendor_type,
    }
    return render(request, 'vendors/vendor_list.html', context)


@login_required
@tenant_admin_required
def vendor_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorForm(request.POST, tenant=tenant)
        if form.is_valid():
            vendor = form.save()
            emit_audit(request, 'vendor.create', vendor)
            messages.success(request, f'Vendor "{vendor.company_name}" created successfully.')
            return redirect('vendors:vendor_list')
    else:
        form = VendorForm(tenant=tenant)

    return render(request, 'vendors/vendor_form.html', {'form': form, 'title': 'Add Vendor'})


@login_required
def vendor_detail_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    performances = vendor.performances.all().select_related('reviewed_by')
    contracts = vendor.contracts.all()
    communications = vendor.communications.all().select_related('communicated_by')

    performance_form = VendorPerformanceForm(tenant=tenant, initial={'vendor': vendor})
    contract_form = VendorContractForm(tenant=tenant, initial={'vendor': vendor})
    communication_form = VendorCommunicationForm(tenant=tenant, initial={'vendor': vendor})

    context = {
        'vendor': vendor,
        'performances': performances,
        'contracts': contracts,
        'communications': communications,
        'performance_form': performance_form,
        'contract_form': contract_form,
        'communication_form': communication_form,
    }
    return render(request, 'vendors/vendor_detail.html', context)


@login_required
@tenant_admin_required
def vendor_edit_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorForm(request.POST, instance=vendor, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'vendor.update', vendor)
            messages.success(request, f'Vendor "{vendor.company_name}" updated successfully.')
            return redirect('vendors:vendor_detail', pk=vendor.pk)
    else:
        form = VendorForm(instance=vendor, tenant=tenant)

    return render(request, 'vendors/vendor_form.html', {
        'form': form, 'title': 'Edit Vendor', 'vendor': vendor,
    })


@login_required
@tenant_admin_required
def vendor_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_list')

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    vendor_name = vendor.company_name
    vendor_pk = vendor.pk
    vendor.delete()
    # emit_audit after delete: construct a throwaway instance so model_name is correct.
    _AuditStub = type('Vendor', (), {'pk': vendor_pk})
    emit_audit(request, 'vendor.delete', _AuditStub(), changes=f'Deleted vendor: {vendor_name}')
    messages.success(request, f'Vendor "{vendor_name}" deleted successfully.')
    return redirect('vendors:vendor_list')


# ──────────────────────────────────────────────
# Performance Tracking list view
# ──────────────────────────────────────────────

@login_required
def performance_list_view(request):
    tenant = request.tenant
    queryset = VendorPerformance.objects.filter(tenant=tenant).select_related('vendor', 'reviewed_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(vendor__company_name__icontains=q) | Q(notes__icontains=q)
        )

    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    performances = paginator.get_page(page_number)

    context = {
        'performances': performances,
        'q': q,
        'vendors': Vendor.objects.filter(tenant=tenant, is_active=True),
        'current_vendor': vendor_id,
    }
    return render(request, 'vendors/performance_list.html', context)


@login_required
@tenant_admin_required
def performance_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorPerformanceForm(request.POST, tenant=tenant)
        if form.is_valid():
            performance = form.save(commit=False)
            performance.reviewed_by = request.user
            performance.save()
            emit_audit(request, 'performance.create', performance)
            messages.success(request, 'Performance review added successfully.')
            return redirect('vendors:performance_list')
    else:
        form = VendorPerformanceForm(tenant=tenant)

    return render(request, 'vendors/performance_form.html', {
        'form': form, 'title': 'Add Performance Review',
    })


@login_required
@tenant_admin_required
def performance_edit_view(request, pk):
    tenant = request.tenant
    performance = get_object_or_404(VendorPerformance, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorPerformanceForm(request.POST, instance=performance, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'performance.update', performance)
            messages.success(request, 'Performance review updated successfully.')
            return redirect('vendors:performance_list')
    else:
        form = VendorPerformanceForm(instance=performance, tenant=tenant)

    return render(request, 'vendors/performance_form.html', {
        'form': form, 'title': 'Edit Performance Review', 'performance': performance,
    })


@login_required
@tenant_admin_required
def performance_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:performance_list')

    performance = get_object_or_404(VendorPerformance, pk=pk, tenant=tenant)
    perf_pk = performance.pk
    performance.delete()
    _AuditStub = type('VendorPerformance', (), {'pk': perf_pk})
    emit_audit(request, 'performance.delete', _AuditStub())
    messages.success(request, 'Performance review deleted successfully.')
    return redirect('vendors:performance_list')


# ──────────────────────────────────────────────
# Contract list view
# ──────────────────────────────────────────────

@login_required
def contract_list_view(request):
    tenant = request.tenant
    queryset = VendorContract.objects.filter(tenant=tenant).select_related('vendor')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(contract_number__icontains=q) | Q(title__icontains=q) | Q(vendor__company_name__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    contracts = paginator.get_page(page_number)

    context = {
        'contracts': contracts,
        'q': q,
        'status_choices': VendorContract.CONTRACT_STATUS_CHOICES,
        'vendors': Vendor.objects.filter(tenant=tenant, is_active=True),
        'current_status': status,
        'current_vendor': vendor_id,
    }
    return render(request, 'vendors/contract_list.html', context)


@login_required
@tenant_admin_required
def contract_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorContractForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            contract = form.save()
            emit_audit(request, 'contract.create', contract)
            messages.success(request, f'Contract "{contract.title}" created successfully.')
            return redirect('vendors:contract_list')
    else:
        form = VendorContractForm(tenant=tenant)

    return render(request, 'vendors/contract_form.html', {'form': form, 'title': 'Add Contract'})


@login_required
@tenant_admin_required
def contract_edit_view(request, pk):
    tenant = request.tenant
    contract = get_object_or_404(VendorContract, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorContractForm(request.POST, request.FILES, instance=contract, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'contract.update', contract)
            messages.success(request, f'Contract "{contract.title}" updated successfully.')
            return redirect('vendors:contract_list')
    else:
        form = VendorContractForm(instance=contract, tenant=tenant)

    return render(request, 'vendors/contract_form.html', {
        'form': form, 'title': 'Edit Contract', 'contract': contract,
    })


@login_required
@tenant_admin_required
def contract_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:contract_list')

    contract = get_object_or_404(VendorContract, pk=pk, tenant=tenant)
    contract_pk = contract.pk
    contract_title = contract.title
    contract.delete()
    _AuditStub = type('VendorContract', (), {'pk': contract_pk})
    emit_audit(request, 'contract.delete', _AuditStub(), changes=f'Deleted contract: {contract_title}')
    messages.success(request, 'Contract deleted successfully.')
    return redirect('vendors:contract_list')


# ──────────────────────────────────────────────
# Communication Log list view
# ──────────────────────────────────────────────

@login_required
def communication_list_view(request):
    tenant = request.tenant
    queryset = VendorCommunication.objects.filter(tenant=tenant).select_related('vendor', 'communicated_by')

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(subject__icontains=q) | Q(message__icontains=q) | Q(vendor__company_name__icontains=q)
        )

    comm_type = request.GET.get('type', '')
    if comm_type:
        queryset = queryset.filter(communication_type=comm_type)

    vendor_id = request.GET.get('vendor', '')
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    communications = paginator.get_page(page_number)

    context = {
        'communications': communications,
        'q': q,
        'type_choices': VendorCommunication.COMM_TYPE_CHOICES,
        'vendors': Vendor.objects.filter(tenant=tenant, is_active=True),
        'current_type': comm_type,
        'current_vendor': vendor_id,
    }
    return render(request, 'vendors/communication_list.html', context)


@login_required
@tenant_admin_required
def communication_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorCommunicationForm(request.POST, tenant=tenant)
        if form.is_valid():
            comm = form.save(commit=False)
            comm.communicated_by = request.user
            comm.save()
            emit_audit(request, 'communication.create', comm)
            messages.success(request, 'Communication logged successfully.')
            return redirect('vendors:communication_list')
    else:
        form = VendorCommunicationForm(tenant=tenant)

    return render(request, 'vendors/communication_form.html', {
        'form': form, 'title': 'Log Communication',
    })


@login_required
@tenant_admin_required
def communication_edit_view(request, pk):
    tenant = request.tenant
    comm = get_object_or_404(VendorCommunication, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorCommunicationForm(request.POST, instance=comm, tenant=tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'communication.update', comm)
            messages.success(request, f'Communication "{comm.subject}" updated successfully.')
            return redirect('vendors:communication_list')
    else:
        form = VendorCommunicationForm(instance=comm, tenant=tenant)

    return render(request, 'vendors/communication_form.html', {
        'form': form, 'title': 'Edit Communication', 'communication': comm,
    })


@login_required
@tenant_admin_required
def communication_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:communication_list')

    comm = get_object_or_404(VendorCommunication, pk=pk, tenant=tenant)
    comm_pk = comm.pk
    comm.delete()
    _AuditStub = type('VendorCommunication', (), {'pk': comm_pk})
    emit_audit(request, 'communication.delete', _AuditStub())
    messages.success(request, 'Communication deleted successfully.')
    return redirect('vendors:communication_list')


# ──────────────────────────────────────────────
# Inline-from-detail handlers (D-11, D-14)
# ──────────────────────────────────────────────

@login_required
@tenant_admin_required
def vendor_performance_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorPerformanceForm(request.POST, tenant=tenant)
        if form.is_valid():
            performance = form.save(commit=False)
            performance.tenant = tenant
            performance.vendor = vendor
            performance.reviewed_by = request.user
            performance.save()
            emit_audit(request, 'performance.create', performance)
            messages.success(request, 'Performance review added successfully.')
        else:
            messages.error(request, _form_error_text(form))

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
@tenant_admin_required
def vendor_performance_delete_view(request, pk, performance_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    performance = get_object_or_404(VendorPerformance, pk=performance_pk, vendor=vendor, tenant=tenant)
    perf_pk = performance.pk
    performance.delete()
    _AuditStub = type('VendorPerformance', (), {'pk': perf_pk})
    emit_audit(request, 'performance.delete', _AuditStub())
    messages.success(request, 'Performance review deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
@tenant_admin_required
def vendor_contract_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorContractForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.tenant = tenant
            contract.vendor = vendor
            contract.save()
            emit_audit(request, 'contract.create', contract)
            messages.success(request, f'Contract "{contract.title}" added successfully.')
        else:
            messages.error(request, _form_error_text(form))

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
@tenant_admin_required
def vendor_contract_delete_view(request, pk, contract_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    contract = get_object_or_404(VendorContract, pk=contract_pk, vendor=vendor, tenant=tenant)
    contract_pk_val = contract.pk
    contract.delete()
    _AuditStub = type('VendorContract', (), {'pk': contract_pk_val})
    emit_audit(request, 'contract.delete', _AuditStub())
    messages.success(request, 'Contract deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
@tenant_admin_required
def vendor_communication_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorCommunicationForm(request.POST, tenant=tenant)
        if form.is_valid():
            comm = form.save(commit=False)
            comm.tenant = tenant
            comm.vendor = vendor
            comm.communicated_by = request.user
            comm.save()
            emit_audit(request, 'communication.create', comm)
            messages.success(request, 'Communication logged successfully.')
        else:
            messages.error(request, _form_error_text(form))

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
@tenant_admin_required
def vendor_communication_delete_view(request, pk, comm_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    comm = get_object_or_404(VendorCommunication, pk=comm_pk, vendor=vendor, tenant=tenant)
    comm_pk_val = comm.pk
    comm.delete()
    _AuditStub = type('VendorCommunication', (), {'pk': comm_pk_val})
    emit_audit(request, 'communication.delete', _AuditStub())
    messages.success(request, 'Communication deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)


def _form_error_text(form):
    parts = []
    for field, errors in form.errors.items():
        label = 'Form' if field == '__all__' else field.replace('_', ' ').title()
        for err in errors:
            parts.append(f'{label}: {err}')
    return ' | '.join(parts) if parts else 'Form submission was invalid.'
