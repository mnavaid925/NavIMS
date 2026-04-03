from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q

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

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(company_name__icontains=q) | Q(email__icontains=q) | Q(tax_id__icontains=q)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        queryset = queryset.filter(status=status)

    # Filter by vendor type
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
def vendor_create_view(request):
    tenant = request.tenant

    if request.method == 'POST':
        form = VendorForm(request.POST, tenant=tenant)
        if form.is_valid():
            vendor = form.save()
            messages.success(request, f'Vendor "{vendor.company_name}" created successfully.')
            return redirect('vendors:vendor_list')
    else:
        form = VendorForm(tenant=tenant)

    context = {
        'form': form,
        'title': 'Add Vendor',
    }
    return render(request, 'vendors/vendor_form.html', context)


@login_required
def vendor_detail_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    performances = vendor.performances.all().select_related('reviewed_by')
    contracts = vendor.contracts.all()
    communications = vendor.communications.all().select_related('communicated_by')

    performance_form = VendorPerformanceForm()
    contract_form = VendorContractForm()
    communication_form = VendorCommunicationForm()

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
def vendor_edit_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorForm(request.POST, instance=vendor, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Vendor "{vendor.company_name}" updated successfully.')
            return redirect('vendors:vendor_detail', pk=vendor.pk)
    else:
        form = VendorForm(instance=vendor, tenant=tenant)

    context = {
        'form': form,
        'title': 'Edit Vendor',
        'vendor': vendor,
    }
    return render(request, 'vendors/vendor_form.html', context)


@login_required
def vendor_delete_view(request, pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_list')

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    vendor_name = vendor.company_name
    vendor.delete()
    messages.success(request, f'Vendor "{vendor_name}" deleted successfully.')
    return redirect('vendors:vendor_list')


# ──────────────────────────────────────────────
# Vendor Performance views (inline from detail)
# ──────────────────────────────────────────────

@login_required
def vendor_performance_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorPerformanceForm(request.POST)
        if form.is_valid():
            performance = form.save(commit=False)
            performance.tenant = tenant
            performance.vendor = vendor
            performance.reviewed_by = request.user
            performance.save()
            messages.success(request, 'Performance review added successfully.')

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
def vendor_performance_delete_view(request, pk, performance_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    performance = get_object_or_404(VendorPerformance, pk=performance_pk, vendor=vendor, tenant=tenant)
    performance.delete()
    messages.success(request, 'Performance review deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)


# ──────────────────────────────────────────────
# Vendor Contract views (inline from detail)
# ──────────────────────────────────────────────

@login_required
def vendor_contract_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.tenant = tenant
            contract.vendor = vendor
            contract.save()
            messages.success(request, f'Contract "{contract.title}" added successfully.')

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
def vendor_contract_delete_view(request, pk, contract_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    contract = get_object_or_404(VendorContract, pk=contract_pk, vendor=vendor, tenant=tenant)
    contract.delete()
    messages.success(request, 'Contract deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)


# ──────────────────────────────────────────────
# Vendor Communication views (inline from detail)
# ──────────────────────────────────────────────

@login_required
def vendor_communication_add_view(request, pk):
    tenant = request.tenant
    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)

    if request.method == 'POST':
        form = VendorCommunicationForm(request.POST)
        if form.is_valid():
            comm = form.save(commit=False)
            comm.tenant = tenant
            comm.vendor = vendor
            comm.communicated_by = request.user
            comm.save()
            messages.success(request, 'Communication logged successfully.')

    return redirect('vendors:vendor_detail', pk=vendor.pk)


@login_required
def vendor_communication_delete_view(request, pk, comm_pk):
    tenant = request.tenant

    if request.method != 'POST':
        return redirect('vendors:vendor_detail', pk=pk)

    vendor = get_object_or_404(Vendor, pk=pk, tenant=tenant)
    comm = get_object_or_404(VendorCommunication, pk=comm_pk, vendor=vendor, tenant=tenant)
    comm.delete()
    messages.success(request, 'Communication deleted successfully.')
    return redirect('vendors:vendor_detail', pk=vendor.pk)
