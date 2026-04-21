"""Accounting & Financial Integration views (Module 19).

Organized into sections:
  1. Overview / dashboards / trial balance / tax calculator
  2. Chart of Accounts CRUD
  3. Fiscal Periods CRUD + open/close
  4. Customers CRUD
  5. Tax Jurisdictions CRUD
  6. Tax Rules CRUD
  7. AP Bills CRUD + state transitions + sync
  8. AR Invoices CRUD + state transitions + sync
  9. Journal Entries CRUD + state transitions + sync
 10. Generate-from-source endpoints
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import tenant_admin_required, emit_audit

from .forms import (
    ChartOfAccountForm, FiscalPeriodForm, CustomerForm,
    TaxJurisdictionForm, TaxRuleForm,
    APBillForm, APBillLineFormSet,
    ARInvoiceForm, ARInvoiceLineFormSet,
    JournalEntryForm, JournalLineFormSet,
)
from .models import (
    ChartOfAccount, FiscalPeriod, Customer,
    TaxJurisdiction, TaxRule,
    APBill, APBillLine, ARInvoice, ARInvoiceLine,
    JournalEntry, JournalLine,
)


ZERO = Decimal('0')
_AGING_BUCKETS = [('current', 0, 30), ('31-60', 31, 60), ('61-90', 61, 90), ('over_90', 91, 99999)]


def _tenant_or_empty(request, model, **extra_filters):
    """Return a tenant-filtered queryset (or .none() if superuser has no tenant)."""
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return model.objects.none()
    qs = model.objects.filter(tenant=tenant, **extra_filters)
    if hasattr(model, 'deleted_at'):
        qs = qs.filter(deleted_at__isnull=True)
    return qs


def _aging_buckets(qs, date_field='due_date'):
    today = date.today()
    buckets = {label: {'count': 0, 'total': ZERO} for label, _, _ in _AGING_BUCKETS}
    for rec in qs:
        d = getattr(rec, date_field) or rec.invoice_date if hasattr(rec, 'invoice_date') else getattr(rec, date_field)
        if d is None:
            days_overdue = 0
        else:
            days_overdue = max(0, (today - d).days)
        for label, lo, hi in _AGING_BUCKETS:
            if lo <= days_overdue <= hi:
                buckets[label]['count'] += 1
                buckets[label]['total'] += getattr(rec, 'total_amount', ZERO) or ZERO
                break
    return buckets


# ═══════════════════════════════════════════════════════════════════════════
# 1. Overview, dashboards, trial balance, tax calculator
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def overview_view(request):
    bills = _tenant_or_empty(request, APBill)
    invoices = _tenant_or_empty(request, ARInvoice)
    entries = _tenant_or_empty(request, JournalEntry)
    rules = _tenant_or_empty(request, TaxRule)
    context = {
        'section_title': 'Accounting & Finance',
        'ap_total': bills.exclude(status__in=('paid', 'voided')).aggregate(t=Sum('total_amount'))['t'] or ZERO,
        'ap_count': bills.exclude(status__in=('paid', 'voided')).count(),
        'ap_pending_sync': bills.filter(sync_status__in=('pending', 'queued')).count(),
        'ar_total': invoices.exclude(status__in=('paid', 'voided')).aggregate(t=Sum('total_amount'))['t'] or ZERO,
        'ar_count': invoices.exclude(status__in=('paid', 'voided')).count(),
        'ar_pending_sync': invoices.filter(sync_status__in=('pending', 'queued')).count(),
        'je_total': entries.filter(status='posted').count(),
        'je_draft': entries.filter(status='draft').count(),
        'je_pending_sync': entries.filter(sync_status__in=('pending', 'queued')).count(),
        'tax_rule_count': rules.filter(is_active=True).count(),
        'tax_jurisdiction_count': _tenant_or_empty(request, TaxJurisdiction).filter(is_active=True).count(),
    }
    return render(request, 'accounting/overview.html', context)


@login_required
def ap_dashboard_view(request):
    bills = _tenant_or_empty(request, APBill).select_related('vendor')
    open_bills = bills.exclude(status__in=('paid', 'voided'))
    context = {
        'bills': open_bills.order_by('-bill_date')[:25],
        'total_open': open_bills.aggregate(t=Sum('total_amount'))['t'] or ZERO,
        'count_open': open_bills.count(),
        'count_draft': bills.filter(status='draft').count(),
        'count_posted': bills.filter(status='posted').count(),
        'count_paid': bills.filter(status='paid').count(),
        'aging': _aging_buckets(open_bills, 'due_date'),
        'sync_breakdown': dict(bills.values_list('sync_status').annotate(c=Sum('id'))) or {},
        'sync_counts': {s: bills.filter(sync_status=s).count() for s, _ in [
            ('pending', 0), ('queued', 0), ('synced', 0), ('failed', 0)]},
    }
    return render(request, 'accounting/ap_dashboard.html', context)


@login_required
def ar_dashboard_view(request):
    invoices = _tenant_or_empty(request, ARInvoice).select_related('customer')
    open_inv = invoices.exclude(status__in=('paid', 'voided'))
    context = {
        'invoices': open_inv.order_by('-invoice_date')[:25],
        'total_open': open_inv.aggregate(t=Sum('total_amount'))['t'] or ZERO,
        'count_open': open_inv.count(),
        'count_draft': invoices.filter(status='draft').count(),
        'count_sent': invoices.filter(status='sent').count(),
        'count_paid': invoices.filter(status='paid').count(),
        'aging': _aging_buckets(open_inv, 'due_date'),
        'sync_counts': {s: invoices.filter(sync_status=s).count() for s, _ in [
            ('pending', 0), ('queued', 0), ('synced', 0), ('failed', 0)]},
    }
    return render(request, 'accounting/ar_dashboard.html', context)


@login_required
def journal_dashboard_view(request):
    entries = _tenant_or_empty(request, JournalEntry).select_related('fiscal_period')
    context = {
        'entries': entries.order_by('-entry_date')[:50],
        'count_total': entries.count(),
        'count_draft': entries.filter(status='draft').count(),
        'count_posted': entries.filter(status='posted').count(),
        'count_voided': entries.filter(status='voided').count(),
        'sync_counts': {s: entries.filter(sync_status=s).count() for s, _ in [
            ('pending', 0), ('queued', 0), ('synced', 0), ('failed', 0)]},
    }
    return render(request, 'accounting/journal_dashboard.html', context)


@login_required
def tax_dashboard_view(request):
    rules = _tenant_or_empty(request, TaxRule).select_related('jurisdiction')
    jurisdictions = _tenant_or_empty(request, TaxJurisdiction)
    context = {
        'jurisdictions': jurisdictions.order_by('code'),
        'rules': rules.filter(is_active=True).order_by('jurisdiction__code', 'tax_category')[:50],
        'count_jurisdictions': jurisdictions.count(),
        'count_rules_active': rules.filter(is_active=True).count(),
    }
    return render(request, 'accounting/tax_dashboard.html', context)


@login_required
def trial_balance_view(request):
    accounts = _tenant_or_empty(request, ChartOfAccount).filter(is_active=True).order_by('code')
    # Aggregate posted journal lines per account
    posted_lines = (
        JournalLine.objects
        .filter(entry__tenant=getattr(request, 'tenant', None), entry__status='posted',
                entry__deleted_at__isnull=True)
        .values('gl_account_id')
        .annotate(debit=Sum('debit_amount'), credit=Sum('credit_amount'))
    )
    by_account = {row['gl_account_id']: row for row in posted_lines}
    rows = []
    total_debit = total_credit = ZERO
    for acc in accounts:
        agg = by_account.get(acc.pk, {})
        debit = agg.get('debit') or ZERO
        credit = agg.get('credit') or ZERO
        net = debit - credit
        rows.append({'account': acc, 'debit': debit, 'credit': credit, 'net': net})
        total_debit += debit
        total_credit += credit
    context = {
        'rows': rows,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': total_debit == total_credit,
    }
    return render(request, 'accounting/trial_balance.html', context)


@login_required
def tax_calculator_view(request):
    tenant = getattr(request, 'tenant', None)
    jurisdictions = _tenant_or_empty(request, TaxJurisdiction).filter(is_active=True)
    from catalog.models import Product
    products = Product.objects.none() if tenant is None else Product.objects.filter(
        tenant=tenant, is_active=True)

    result = None
    if request.method == 'POST' and tenant is not None:
        prod_pk = request.POST.get('product')
        jur_pk = request.POST.get('jurisdiction')
        amount = request.POST.get('amount', '0').strip() or '0'
        try:
            amount_dec = Decimal(amount)
        except Exception:  # noqa: BLE001
            amount_dec = ZERO

        product = products.filter(pk=prod_pk).first()
        jurisdiction = jurisdictions.filter(pk=jur_pk).first()
        if product and jurisdiction:
            today = date.today()
            rule = (
                TaxRule.objects.filter(
                    tenant=tenant, jurisdiction=jurisdiction,
                    tax_category=product.tax_category, is_active=True,
                    effective_date__lte=today,
                )
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
                .order_by('-effective_date').first()
            )
            if rule:
                tax = (amount_dec * rule.tax_rate / Decimal('100')).quantize(Decimal('0.01'))
                result = {
                    'product': product, 'jurisdiction': jurisdiction, 'rule': rule,
                    'amount': amount_dec, 'tax': tax, 'total': amount_dec + tax,
                }
            else:
                messages.warning(request,
                                 f'No active tax rule for {product.get_tax_category_display()} in {jurisdiction.code}.')
    context = {
        'products': products.order_by('name')[:500],
        'jurisdictions': jurisdictions.order_by('code'),
        'result': result,
    }
    return render(request, 'accounting/tax_calculator.html', context)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Chart of Accounts CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def coa_list_view(request):
    qs = _tenant_or_empty(request, ChartOfAccount)
    q = request.GET.get('q', '').strip()
    account_type = request.GET.get('account_type', '').strip()
    active = request.GET.get('active', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    if account_type:
        qs = qs.filter(account_type=account_type)
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    context = {
        'accounts': qs.order_by('code'),
        'account_type_choices': ChartOfAccount.ACCOUNT_TYPE_CHOICES,
    }
    return render(request, 'accounting/chart_of_account_list.html', context)


@login_required
@tenant_admin_required
def coa_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin to create accounts.')
        return redirect('accounting:coa_list')
    if request.method == 'POST':
        form = ChartOfAccountForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            acc = form.save()
            emit_audit(request, 'create', acc, changes=f'code={acc.code}')
            messages.success(request, f'Account {acc.code} created.')
            return redirect('accounting:coa_detail', pk=acc.pk)
    else:
        form = ChartOfAccountForm(tenant=request.tenant)
    return render(request, 'accounting/chart_of_account_form.html',
                  {'form': form, 'mode': 'create'})


@login_required
def coa_detail_view(request, pk):
    acc = get_object_or_404(_tenant_or_empty(request, ChartOfAccount), pk=pk)
    return render(request, 'accounting/chart_of_account_detail.html', {'account': acc})


@login_required
@tenant_admin_required
def coa_edit_view(request, pk):
    acc = get_object_or_404(_tenant_or_empty(request, ChartOfAccount), pk=pk)
    if request.method == 'POST':
        form = ChartOfAccountForm(request.POST, instance=acc, tenant=request.tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', acc)
            messages.success(request, f'Account {acc.code} updated.')
            return redirect('accounting:coa_detail', pk=acc.pk)
    else:
        form = ChartOfAccountForm(instance=acc, tenant=request.tenant)
    return render(request, 'accounting/chart_of_account_form.html',
                  {'form': form, 'account': acc, 'mode': 'edit'})


@login_required
@tenant_admin_required
@require_POST
def coa_delete_view(request, pk):
    acc = get_object_or_404(_tenant_or_empty(request, ChartOfAccount), pk=pk)
    code = acc.code
    acc.delete()
    emit_audit(request, 'delete', acc, changes=f'code={code}')
    messages.success(request, f'Account {code} deleted.')
    return redirect('accounting:coa_list')


# ═══════════════════════════════════════════════════════════════════════════
# 3. Fiscal Periods CRUD + open/close
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def period_list_view(request):
    qs = _tenant_or_empty(request, FiscalPeriod)
    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)
    context = {
        'periods': qs.order_by('-start_date'),
        'status_choices': FiscalPeriod.STATUS_CHOICES,
    }
    return render(request, 'accounting/fiscal_period_list.html', context)


@login_required
@tenant_admin_required
def period_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:period_list')
    if request.method == 'POST':
        form = FiscalPeriodForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            period = form.save()
            emit_audit(request, 'create', period)
            messages.success(request, f'Period {period.period_number} created.')
            return redirect('accounting:period_detail', pk=period.pk)
    else:
        form = FiscalPeriodForm(tenant=request.tenant)
    return render(request, 'accounting/fiscal_period_form.html',
                  {'form': form, 'mode': 'create'})


@login_required
def period_detail_view(request, pk):
    period = get_object_or_404(_tenant_or_empty(request, FiscalPeriod), pk=pk)
    entries = period.journal_entries.filter(deleted_at__isnull=True).order_by('-entry_date')[:50]
    return render(request, 'accounting/fiscal_period_detail.html',
                  {'period': period, 'entries': entries})


@login_required
@tenant_admin_required
def period_edit_view(request, pk):
    period = get_object_or_404(_tenant_or_empty(request, FiscalPeriod), pk=pk)
    if request.method == 'POST':
        form = FiscalPeriodForm(request.POST, instance=period, tenant=request.tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', period)
            messages.success(request, f'Period {period.period_number} updated.')
            return redirect('accounting:period_detail', pk=period.pk)
    else:
        form = FiscalPeriodForm(instance=period, tenant=request.tenant)
    return render(request, 'accounting/fiscal_period_form.html',
                  {'form': form, 'period': period, 'mode': 'edit'})


@login_required
@tenant_admin_required
@require_POST
def period_delete_view(request, pk):
    period = get_object_or_404(_tenant_or_empty(request, FiscalPeriod), pk=pk)
    if period.journal_entries.exists():
        messages.error(request, 'Cannot delete a period that has journal entries.')
        return redirect('accounting:period_detail', pk=pk)
    num = period.period_number
    period.delete()
    emit_audit(request, 'delete', period, changes=f'period={num}')
    messages.success(request, f'Period {num} deleted.')
    return redirect('accounting:period_list')


@login_required
@tenant_admin_required
@require_POST
def period_close_view(request, pk):
    period = get_object_or_404(_tenant_or_empty(request, FiscalPeriod), pk=pk)
    if not period.can_transition_to('closed'):
        messages.error(request, 'Cannot close this period from its current status.')
        return redirect('accounting:period_detail', pk=pk)
    period.status = 'closed'
    period.closed_at = timezone.now()
    period.closed_by = request.user
    period.save()
    emit_audit(request, 'close', period)
    messages.success(request, f'Period {period.period_number} closed.')
    return redirect('accounting:period_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def period_reopen_view(request, pk):
    period = get_object_or_404(_tenant_or_empty(request, FiscalPeriod), pk=pk)
    if not period.can_transition_to('open'):
        messages.error(request, 'Cannot reopen this period.')
        return redirect('accounting:period_detail', pk=pk)
    period.status = 'open'
    period.closed_at = None
    period.save()
    emit_audit(request, 'reopen', period)
    messages.success(request, f'Period {period.period_number} reopened.')
    return redirect('accounting:period_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Customers CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def customer_list_view(request):
    qs = _tenant_or_empty(request, Customer)
    q = request.GET.get('q', '').strip()
    active = request.GET.get('active', '').strip()
    if q:
        qs = qs.filter(Q(customer_number__icontains=q) | Q(company_name__icontains=q)
                       | Q(contact_email__icontains=q))
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    return render(request, 'accounting/customer_list.html',
                  {'customers': qs.order_by('company_name')})


@login_required
@tenant_admin_required
def customer_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:customer_list')
    if request.method == 'POST':
        form = CustomerForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            cust = form.save()
            emit_audit(request, 'create', cust)
            messages.success(request, f'Customer {cust.customer_number} created.')
            return redirect('accounting:customer_detail', pk=cust.pk)
    else:
        form = CustomerForm(tenant=request.tenant)
    return render(request, 'accounting/customer_form.html',
                  {'form': form, 'mode': 'create'})


@login_required
def customer_detail_view(request, pk):
    cust = get_object_or_404(_tenant_or_empty(request, Customer), pk=pk)
    invoices = cust.invoices.filter(deleted_at__isnull=True).order_by('-invoice_date')[:25]
    return render(request, 'accounting/customer_detail.html',
                  {'customer': cust, 'invoices': invoices})


@login_required
@tenant_admin_required
def customer_edit_view(request, pk):
    cust = get_object_or_404(_tenant_or_empty(request, Customer), pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=cust, tenant=request.tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', cust)
            messages.success(request, f'Customer {cust.customer_number} updated.')
            return redirect('accounting:customer_detail', pk=cust.pk)
    else:
        form = CustomerForm(instance=cust, tenant=request.tenant)
    return render(request, 'accounting/customer_form.html',
                  {'form': form, 'customer': cust, 'mode': 'edit'})


@login_required
@tenant_admin_required
@require_POST
def customer_delete_view(request, pk):
    cust = get_object_or_404(_tenant_or_empty(request, Customer), pk=pk)
    num = cust.customer_number
    cust.deleted_at = timezone.now()
    cust.save()
    emit_audit(request, 'delete', cust, changes=f'customer={num}')
    messages.success(request, f'Customer {num} archived.')
    return redirect('accounting:customer_list')


# ═══════════════════════════════════════════════════════════════════════════
# 5. Tax Jurisdictions CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def jurisdiction_list_view(request):
    qs = _tenant_or_empty(request, TaxJurisdiction)
    q = request.GET.get('q', '').strip()
    active = request.GET.get('active', '').strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    return render(request, 'accounting/tax_jurisdiction_list.html',
                  {'jurisdictions': qs.order_by('code')})


@login_required
@tenant_admin_required
def jurisdiction_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:jurisdiction_list')
    if request.method == 'POST':
        form = TaxJurisdictionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save()
            emit_audit(request, 'create', obj)
            messages.success(request, f'Jurisdiction {obj.code} created.')
            return redirect('accounting:jurisdiction_detail', pk=obj.pk)
    else:
        form = TaxJurisdictionForm(tenant=request.tenant)
    return render(request, 'accounting/tax_jurisdiction_form.html',
                  {'form': form, 'mode': 'create'})


@login_required
def jurisdiction_detail_view(request, pk):
    obj = get_object_or_404(_tenant_or_empty(request, TaxJurisdiction), pk=pk)
    rules = obj.rules.filter(tenant=request.tenant).order_by('-effective_date', 'tax_category')
    return render(request, 'accounting/tax_jurisdiction_detail.html',
                  {'jurisdiction': obj, 'rules': rules})


@login_required
@tenant_admin_required
def jurisdiction_edit_view(request, pk):
    obj = get_object_or_404(_tenant_or_empty(request, TaxJurisdiction), pk=pk)
    if request.method == 'POST':
        form = TaxJurisdictionForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', obj)
            messages.success(request, f'Jurisdiction {obj.code} updated.')
            return redirect('accounting:jurisdiction_detail', pk=obj.pk)
    else:
        form = TaxJurisdictionForm(instance=obj, tenant=request.tenant)
    return render(request, 'accounting/tax_jurisdiction_form.html',
                  {'form': form, 'jurisdiction': obj, 'mode': 'edit'})


@login_required
@tenant_admin_required
@require_POST
def jurisdiction_delete_view(request, pk):
    obj = get_object_or_404(_tenant_or_empty(request, TaxJurisdiction), pk=pk)
    if obj.rules.exists():
        messages.error(request, 'Cannot delete a jurisdiction with tax rules.')
        return redirect('accounting:jurisdiction_detail', pk=pk)
    code = obj.code
    obj.delete()
    emit_audit(request, 'delete', obj, changes=f'code={code}')
    messages.success(request, f'Jurisdiction {code} deleted.')
    return redirect('accounting:jurisdiction_list')


# ═══════════════════════════════════════════════════════════════════════════
# 6. Tax Rules CRUD
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def tax_rule_list_view(request):
    qs = _tenant_or_empty(request, TaxRule).select_related('jurisdiction')
    q = request.GET.get('q', '').strip()
    tax_category = request.GET.get('tax_category', '').strip()
    jurisdiction = request.GET.get('jurisdiction', '').strip()
    active = request.GET.get('active', '').strip()
    if q:
        qs = qs.filter(Q(rule_number__icontains=q) | Q(description__icontains=q))
    if tax_category:
        qs = qs.filter(tax_category=tax_category)
    if jurisdiction:
        qs = qs.filter(jurisdiction_id=jurisdiction)
    if active == 'active':
        qs = qs.filter(is_active=True)
    elif active == 'inactive':
        qs = qs.filter(is_active=False)
    context = {
        'rules': qs.order_by('-effective_date', 'jurisdiction__code'),
        'tax_category_choices': TaxRule.TAX_CATEGORY_CHOICES,
        'jurisdictions': _tenant_or_empty(request, TaxJurisdiction).order_by('code'),
    }
    return render(request, 'accounting/tax_rule_list.html', context)


@login_required
@tenant_admin_required
def tax_rule_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:tax_rule_list')
    if request.method == 'POST':
        form = TaxRuleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            rule = form.save()
            emit_audit(request, 'create', rule)
            messages.success(request, f'Tax rule {rule.rule_number} created.')
            return redirect('accounting:tax_rule_detail', pk=rule.pk)
    else:
        form = TaxRuleForm(tenant=request.tenant)
    return render(request, 'accounting/tax_rule_form.html',
                  {'form': form, 'mode': 'create'})


@login_required
def tax_rule_detail_view(request, pk):
    rule = get_object_or_404(
        _tenant_or_empty(request, TaxRule).select_related('jurisdiction'), pk=pk,
    )
    return render(request, 'accounting/tax_rule_detail.html', {'rule': rule})


@login_required
@tenant_admin_required
def tax_rule_edit_view(request, pk):
    rule = get_object_or_404(_tenant_or_empty(request, TaxRule), pk=pk)
    if request.method == 'POST':
        form = TaxRuleForm(request.POST, instance=rule, tenant=request.tenant)
        if form.is_valid():
            form.save()
            emit_audit(request, 'update', rule)
            messages.success(request, f'Tax rule {rule.rule_number} updated.')
            return redirect('accounting:tax_rule_detail', pk=rule.pk)
    else:
        form = TaxRuleForm(instance=rule, tenant=request.tenant)
    return render(request, 'accounting/tax_rule_form.html',
                  {'form': form, 'rule': rule, 'mode': 'edit'})


@login_required
@tenant_admin_required
@require_POST
def tax_rule_delete_view(request, pk):
    rule = get_object_or_404(_tenant_or_empty(request, TaxRule), pk=pk)
    num = rule.rule_number
    rule.delete()
    emit_audit(request, 'delete', rule, changes=f'rule={num}')
    messages.success(request, f'Tax rule {num} deleted.')
    return redirect('accounting:tax_rule_list')


# ═══════════════════════════════════════════════════════════════════════════
# 7. AP Bills CRUD + state transitions + sync
# ═══════════════════════════════════════════════════════════════════════════

def _render_ap_bill_form(request, bill=None):
    tenant = request.tenant
    if request.method == 'POST':
        form = APBillForm(request.POST, instance=bill, tenant=tenant)
        formset = APBillLineFormSet(request.POST, instance=bill, form_kwargs={'tenant': tenant})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save()
                formset.instance = obj
                formset.save()
                obj.recompute_totals()
                obj.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])
            emit_audit(request, 'update' if bill else 'create', obj)
            messages.success(request, f'Bill {obj.bill_number} saved.')
            return redirect('accounting:ap_bill_detail', pk=obj.pk)
    else:
        form = APBillForm(instance=bill, tenant=tenant)
        formset = APBillLineFormSet(instance=bill, form_kwargs={'tenant': tenant})
    return render(request, 'accounting/ap_bill_form.html',
                  {'form': form, 'formset': formset, 'bill': bill,
                   'mode': 'edit' if bill else 'create'})


@login_required
def ap_bill_list_view(request):
    qs = _tenant_or_empty(request, APBill).select_related('vendor')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    sync_status = request.GET.get('sync_status', '').strip()
    if q:
        qs = qs.filter(Q(bill_number__icontains=q) | Q(vendor__company_name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if sync_status:
        qs = qs.filter(sync_status=sync_status)
    context = {
        'bills': qs.order_by('-bill_date', '-id'),
        'status_choices': APBill.STATUS_CHOICES,
        'sync_status_choices': [(s, lbl) for s, lbl in [
            ('pending', 'Pending'), ('queued', 'Queued'),
            ('synced', 'Synced'), ('failed', 'Failed')]],
    }
    return render(request, 'accounting/ap_bill_list.html', context)


@login_required
@tenant_admin_required
def ap_bill_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:ap_bill_list')
    return _render_ap_bill_form(request)


@login_required
def ap_bill_detail_view(request, pk):
    bill = get_object_or_404(
        _tenant_or_empty(request, APBill).select_related('vendor', 'source_invoice',
                                                         'source_po', 'source_grn',
                                                         'journal_entry'),
        pk=pk,
    )
    return render(request, 'accounting/ap_bill_detail.html',
                  {'bill': bill, 'lines': bill.lines.select_related('gl_account', 'product')})


@login_required
@tenant_admin_required
def ap_bill_edit_view(request, pk):
    bill = get_object_or_404(_tenant_or_empty(request, APBill), pk=pk)
    if bill.status not in ('draft', 'pending_approval'):
        messages.error(request, 'Only draft or pending bills can be edited.')
        return redirect('accounting:ap_bill_detail', pk=pk)
    return _render_ap_bill_form(request, bill=bill)


@login_required
@tenant_admin_required
@require_POST
def ap_bill_delete_view(request, pk):
    bill = get_object_or_404(_tenant_or_empty(request, APBill), pk=pk)
    if bill.status not in ('draft', 'voided'):
        messages.error(request, 'Only draft or voided bills can be deleted.')
        return redirect('accounting:ap_bill_detail', pk=pk)
    num = bill.bill_number
    bill.deleted_at = timezone.now()
    bill.save()
    emit_audit(request, 'delete', bill, changes=f'bill={num}')
    messages.success(request, f'Bill {num} archived.')
    return redirect('accounting:ap_bill_list')


def _ap_bill_transition(request, pk, target, audit_action):
    bill = get_object_or_404(_tenant_or_empty(request, APBill), pk=pk)
    if not bill.can_transition_to(target):
        messages.error(request, f'Cannot move bill from {bill.status} to {target}.')
        return redirect('accounting:ap_bill_detail', pk=pk)
    bill.status = target
    if target == 'posted':
        bill.posted_at = timezone.now()
    if target == 'paid':
        bill.paid_at = timezone.now()
    bill.save()
    emit_audit(request, audit_action, bill)
    messages.success(request, f'Bill {bill.bill_number} → {bill.get_status_display()}.')
    return redirect('accounting:ap_bill_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def ap_bill_submit_view(request, pk):
    return _ap_bill_transition(request, pk, 'pending_approval', 'submit')


@login_required
@tenant_admin_required
@require_POST
def ap_bill_approve_view(request, pk):
    return _ap_bill_transition(request, pk, 'approved', 'approve')


@login_required
@tenant_admin_required
@require_POST
def ap_bill_post_view(request, pk):
    bill = get_object_or_404(_tenant_or_empty(request, APBill), pk=pk)
    if not bill.can_transition_to('posted'):
        messages.error(request, f'Cannot post bill from {bill.status}.')
        return redirect('accounting:ap_bill_detail', pk=pk)
    if bill.created_by_id and bill.created_by_id == request.user.id:
        messages.error(request, 'Segregation of duties: creator cannot post their own bill.')
        return redirect('accounting:ap_bill_detail', pk=pk)
    with transaction.atomic():
        locked = APBill.objects.select_for_update().get(pk=bill.pk)
        if locked.status != bill.status:
            messages.warning(request, 'Bill status changed; refresh and retry.')
            return redirect('accounting:ap_bill_detail', pk=pk)
        # Ensure a journal entry exists
        if locked.journal_entry is None:
            period = _open_period_for_date(request.tenant, locked.bill_date)
            if period is None:
                messages.error(request, 'No open fiscal period covers this bill date.')
                return redirect('accounting:ap_bill_detail', pk=pk)
            je = _build_journal_for_ap_bill(locked, period, request.user)
            locked.journal_entry = je
        locked.status = 'posted'
        locked.posted_at = timezone.now()
        locked.save()
    emit_audit(request, 'post', locked,
               changes=f'journal_entry={locked.journal_entry.entry_number if locked.journal_entry else ""}')
    messages.success(request, f'Bill {locked.bill_number} posted.')
    return redirect('accounting:ap_bill_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def ap_bill_mark_paid_view(request, pk):
    return _ap_bill_transition(request, pk, 'paid', 'mark_paid')


@login_required
@tenant_admin_required
@require_POST
def ap_bill_void_view(request, pk):
    return _ap_bill_transition(request, pk, 'voided', 'void')


@login_required
@tenant_admin_required
@require_POST
def ap_bill_queue_sync_view(request, pk):
    bill = get_object_or_404(_tenant_or_empty(request, APBill), pk=pk)
    bill.sync_status = 'queued'
    bill.sync_error = ''
    bill.save(update_fields=['sync_status', 'sync_error'])
    emit_audit(request, 'queue_sync', bill)
    messages.success(request, f'Bill {bill.bill_number} queued for sync.')
    return redirect('accounting:ap_bill_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# 8. AR Invoices CRUD + state transitions + sync
# ═══════════════════════════════════════════════════════════════════════════

def _render_ar_invoice_form(request, invoice=None):
    tenant = request.tenant
    if request.method == 'POST':
        form = ARInvoiceForm(request.POST, instance=invoice, tenant=tenant)
        formset = ARInvoiceLineFormSet(request.POST, instance=invoice,
                                       form_kwargs={'tenant': tenant})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save()
                formset.instance = obj
                formset.save()
                obj.recompute_totals()
                obj.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])
            emit_audit(request, 'update' if invoice else 'create', obj)
            messages.success(request, f'Invoice {obj.invoice_number} saved.')
            return redirect('accounting:ar_invoice_detail', pk=obj.pk)
    else:
        form = ARInvoiceForm(instance=invoice, tenant=tenant)
        formset = ARInvoiceLineFormSet(instance=invoice, form_kwargs={'tenant': tenant})
    return render(request, 'accounting/ar_invoice_form.html',
                  {'form': form, 'formset': formset, 'invoice': invoice,
                   'mode': 'edit' if invoice else 'create'})


@login_required
def ar_invoice_list_view(request):
    qs = _tenant_or_empty(request, ARInvoice).select_related('customer')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    sync_status = request.GET.get('sync_status', '').strip()
    if q:
        qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer__company_name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if sync_status:
        qs = qs.filter(sync_status=sync_status)
    context = {
        'invoices': qs.order_by('-invoice_date', '-id'),
        'status_choices': ARInvoice.STATUS_CHOICES,
        'sync_status_choices': [('pending', 'Pending'), ('queued', 'Queued'),
                                ('synced', 'Synced'), ('failed', 'Failed')],
    }
    return render(request, 'accounting/ar_invoice_list.html', context)


@login_required
@tenant_admin_required
def ar_invoice_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:ar_invoice_list')
    return _render_ar_invoice_form(request)


@login_required
def ar_invoice_detail_view(request, pk):
    invoice = get_object_or_404(
        _tenant_or_empty(request, ARInvoice).select_related(
            'customer', 'source_so', 'source_shipment', 'journal_entry'),
        pk=pk,
    )
    return render(request, 'accounting/ar_invoice_detail.html',
                  {'invoice': invoice,
                   'lines': invoice.lines.select_related('gl_account', 'product')})


@login_required
@tenant_admin_required
def ar_invoice_edit_view(request, pk):
    invoice = get_object_or_404(_tenant_or_empty(request, ARInvoice), pk=pk)
    if invoice.status not in ('draft',):
        messages.error(request, 'Only draft invoices can be edited.')
        return redirect('accounting:ar_invoice_detail', pk=pk)
    return _render_ar_invoice_form(request, invoice=invoice)


@login_required
@tenant_admin_required
@require_POST
def ar_invoice_delete_view(request, pk):
    invoice = get_object_or_404(_tenant_or_empty(request, ARInvoice), pk=pk)
    if invoice.status not in ('draft', 'voided'):
        messages.error(request, 'Only draft or voided invoices can be deleted.')
        return redirect('accounting:ar_invoice_detail', pk=pk)
    num = invoice.invoice_number
    invoice.deleted_at = timezone.now()
    invoice.save()
    emit_audit(request, 'delete', invoice, changes=f'invoice={num}')
    messages.success(request, f'Invoice {num} archived.')
    return redirect('accounting:ar_invoice_list')


def _ar_invoice_transition(request, pk, target, audit_action):
    invoice = get_object_or_404(_tenant_or_empty(request, ARInvoice), pk=pk)
    if not invoice.can_transition_to(target):
        messages.error(request, f'Cannot move invoice from {invoice.status} to {target}.')
        return redirect('accounting:ar_invoice_detail', pk=pk)
    invoice.status = target
    if target == 'sent':
        invoice.sent_at = timezone.now()
        if invoice.journal_entry is None:
            period = _open_period_for_date(request.tenant, invoice.invoice_date)
            if period is None:
                messages.error(request, 'No open fiscal period covers this invoice date.')
                return redirect('accounting:ar_invoice_detail', pk=pk)
            invoice.journal_entry = _build_journal_for_ar_invoice(invoice, period, request.user)
    if target == 'paid':
        invoice.paid_at = timezone.now()
    invoice.save()
    emit_audit(request, audit_action, invoice)
    messages.success(request, f'Invoice {invoice.invoice_number} → {invoice.get_status_display()}.')
    return redirect('accounting:ar_invoice_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def ar_invoice_send_view(request, pk):
    return _ar_invoice_transition(request, pk, 'sent', 'send')


@login_required
@tenant_admin_required
@require_POST
def ar_invoice_mark_paid_view(request, pk):
    return _ar_invoice_transition(request, pk, 'paid', 'mark_paid')


@login_required
@tenant_admin_required
@require_POST
def ar_invoice_void_view(request, pk):
    return _ar_invoice_transition(request, pk, 'voided', 'void')


@login_required
@tenant_admin_required
@require_POST
def ar_invoice_queue_sync_view(request, pk):
    invoice = get_object_or_404(_tenant_or_empty(request, ARInvoice), pk=pk)
    invoice.sync_status = 'queued'
    invoice.sync_error = ''
    invoice.save(update_fields=['sync_status', 'sync_error'])
    emit_audit(request, 'queue_sync', invoice)
    messages.success(request, f'Invoice {invoice.invoice_number} queued for sync.')
    return redirect('accounting:ar_invoice_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Journal Entries CRUD + state transitions + sync
# ═══════════════════════════════════════════════════════════════════════════

def _render_journal_entry_form(request, entry=None):
    tenant = request.tenant
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, instance=entry, tenant=tenant)
        formset = JournalLineFormSet(request.POST, instance=entry, form_kwargs={'tenant': tenant})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save()
                formset.instance = obj
                formset.save()
                obj.recompute_totals()
                obj.save(update_fields=['total_debit', 'total_credit'])
            emit_audit(request, 'update' if entry else 'create', obj)
            messages.success(request, f'Entry {obj.entry_number} saved.')
            return redirect('accounting:journal_entry_detail', pk=obj.pk)
    else:
        form = JournalEntryForm(instance=entry, tenant=tenant)
        formset = JournalLineFormSet(instance=entry, form_kwargs={'tenant': tenant})
    return render(request, 'accounting/journal_entry_form.html',
                  {'form': form, 'formset': formset, 'entry': entry,
                   'mode': 'edit' if entry else 'create'})


@login_required
def journal_entry_list_view(request):
    qs = _tenant_or_empty(request, JournalEntry).select_related('fiscal_period')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    source_type = request.GET.get('source_type', '').strip()
    sync_status = request.GET.get('sync_status', '').strip()
    if q:
        qs = qs.filter(Q(entry_number__icontains=q) | Q(description__icontains=q)
                       | Q(source_reference__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if source_type:
        qs = qs.filter(source_type=source_type)
    if sync_status:
        qs = qs.filter(sync_status=sync_status)
    context = {
        'entries': qs.order_by('-entry_date', '-id'),
        'status_choices': JournalEntry.STATUS_CHOICES,
        'source_type_choices': JournalEntry.SOURCE_TYPE_CHOICES,
        'sync_status_choices': [('pending', 'Pending'), ('queued', 'Queued'),
                                ('synced', 'Synced'), ('failed', 'Failed')],
    }
    return render(request, 'accounting/journal_entry_list.html', context)


@login_required
@tenant_admin_required
def journal_entry_create_view(request):
    if getattr(request, 'tenant', None) is None:
        messages.error(request, 'You must be logged in as a tenant admin.')
        return redirect('accounting:journal_entry_list')
    return _render_journal_entry_form(request)


@login_required
def journal_entry_detail_view(request, pk):
    entry = get_object_or_404(
        _tenant_or_empty(request, JournalEntry).select_related('fiscal_period'),
        pk=pk,
    )
    return render(request, 'accounting/journal_entry_detail.html',
                  {'entry': entry,
                   'lines': entry.lines.select_related('gl_account')})


@login_required
@tenant_admin_required
def journal_entry_edit_view(request, pk):
    entry = get_object_or_404(_tenant_or_empty(request, JournalEntry), pk=pk)
    if entry.status != 'draft':
        messages.error(request, 'Only draft entries can be edited.')
        return redirect('accounting:journal_entry_detail', pk=pk)
    return _render_journal_entry_form(request, entry=entry)


@login_required
@tenant_admin_required
@require_POST
def journal_entry_delete_view(request, pk):
    entry = get_object_or_404(_tenant_or_empty(request, JournalEntry), pk=pk)
    if entry.status not in ('draft', 'voided'):
        messages.error(request, 'Only draft or voided entries can be deleted.')
        return redirect('accounting:journal_entry_detail', pk=pk)
    num = entry.entry_number
    entry.deleted_at = timezone.now()
    entry.save()
    emit_audit(request, 'delete', entry, changes=f'entry={num}')
    messages.success(request, f'Entry {num} archived.')
    return redirect('accounting:journal_entry_list')


@login_required
@tenant_admin_required
@require_POST
def journal_entry_post_view(request, pk):
    entry = get_object_or_404(_tenant_or_empty(request, JournalEntry), pk=pk)
    if not entry.can_transition_to('posted'):
        messages.error(request, 'Cannot post entry from current status.')
        return redirect('accounting:journal_entry_detail', pk=pk)
    if entry.created_by_id and entry.created_by_id == request.user.id:
        messages.error(request, 'Segregation of duties: creator cannot post their own entry.')
        return redirect('accounting:journal_entry_detail', pk=pk)
    with transaction.atomic():
        locked = JournalEntry.objects.select_for_update().get(pk=entry.pk)
        if locked.status != 'draft':
            messages.warning(request, 'Entry status changed; refresh and retry.')
            return redirect('accounting:journal_entry_detail', pk=pk)
        locked.recompute_totals()
        if not locked.is_balanced:
            messages.error(request,
                           f'Debits ({locked.total_debit}) ≠ Credits ({locked.total_credit}); cannot post.')
            return redirect('accounting:journal_entry_detail', pk=pk)
        if locked.fiscal_period.status != 'open':
            messages.error(request, 'Fiscal period is closed; cannot post.')
            return redirect('accounting:journal_entry_detail', pk=pk)
        locked.status = 'posted'
        locked.posted_at = timezone.now()
        locked.posted_by = request.user
        locked.save()
    emit_audit(request, 'post', locked)
    messages.success(request, f'Entry {locked.entry_number} posted.')
    return redirect('accounting:journal_entry_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def journal_entry_void_view(request, pk):
    entry = get_object_or_404(_tenant_or_empty(request, JournalEntry), pk=pk)
    if not entry.can_transition_to('voided'):
        messages.error(request, 'Cannot void entry from current status.')
        return redirect('accounting:journal_entry_detail', pk=pk)
    entry.status = 'voided'
    entry.save()
    emit_audit(request, 'void', entry)
    messages.success(request, f'Entry {entry.entry_number} voided.')
    return redirect('accounting:journal_entry_detail', pk=pk)


@login_required
@tenant_admin_required
@require_POST
def journal_entry_queue_sync_view(request, pk):
    entry = get_object_or_404(_tenant_or_empty(request, JournalEntry), pk=pk)
    entry.sync_status = 'queued'
    entry.sync_error = ''
    entry.save(update_fields=['sync_status', 'sync_error'])
    emit_audit(request, 'queue_sync', entry)
    messages.success(request, f'Entry {entry.entry_number} queued for sync.')
    return redirect('accounting:journal_entry_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Helpers — period resolution + journal builders
# ═══════════════════════════════════════════════════════════════════════════

def _open_period_for_date(tenant, target_date):
    """Find the earliest open fiscal period covering `target_date`.

    Falls back to any open period if no range matches (dev convenience).
    """
    if tenant is None or target_date is None:
        return None
    qs = FiscalPeriod.objects.filter(tenant=tenant, status='open')
    exact = qs.filter(start_date__lte=target_date, end_date__gte=target_date).first()
    return exact or qs.order_by('-start_date').first()


def _coa_by_type(tenant, account_type):
    return (
        ChartOfAccount.objects
        .filter(tenant=tenant, account_type=account_type, is_active=True)
        .order_by('code').first()
    )


def _build_journal_for_ap_bill(bill, period, user):
    """Create a draft JournalEntry for a posted AP bill: Dr Inventory/Expense, Cr AP Liability."""
    tenant = bill.tenant
    expense_account = _coa_by_type(tenant, 'expense') or _coa_by_type(tenant, 'asset')
    liability_account = _coa_by_type(tenant, 'liability')
    tax_account = ChartOfAccount.objects.filter(
        tenant=tenant, account_type='liability', code__icontains='2100', is_active=True,
    ).first() or liability_account
    entry = JournalEntry.objects.create(
        tenant=tenant,
        entry_date=bill.bill_date,
        fiscal_period=period,
        source_type='ap_bill',
        source_reference=bill.bill_number,
        source_id=str(bill.pk),
        description=f'AP Bill {bill.bill_number} — {bill.vendor.company_name}',
        created_by=user,
    )
    if expense_account and liability_account:
        JournalLine.objects.create(
            entry=entry, gl_account=expense_account, line_order=1,
            debit_amount=bill.subtotal,
            description=f'Purchase expense for {bill.bill_number}',
        )
        if bill.tax_amount and tax_account:
            JournalLine.objects.create(
                entry=entry, gl_account=tax_account, line_order=2,
                debit_amount=bill.tax_amount,
                description='Input tax',
            )
        JournalLine.objects.create(
            entry=entry, gl_account=liability_account, line_order=3,
            credit_amount=bill.total_amount,
            description=f'AP liability to {bill.vendor.company_name}',
        )
        entry.recompute_totals()
        entry.save(update_fields=['total_debit', 'total_credit'])
    return entry


def _build_journal_for_ar_invoice(invoice, period, user):
    """Create a draft JournalEntry for a sent AR invoice: Dr AR, Cr Revenue."""
    tenant = invoice.tenant
    ar_account = _coa_by_type(tenant, 'asset')
    revenue_account = _coa_by_type(tenant, 'revenue')
    tax_account = ChartOfAccount.objects.filter(
        tenant=tenant, account_type='liability', code__icontains='2100', is_active=True,
    ).first() or _coa_by_type(tenant, 'liability')
    entry = JournalEntry.objects.create(
        tenant=tenant,
        entry_date=invoice.invoice_date,
        fiscal_period=period,
        source_type='ar_invoice',
        source_reference=invoice.invoice_number,
        source_id=str(invoice.pk),
        description=f'AR Invoice {invoice.invoice_number} — {invoice.customer.company_name}',
        created_by=user,
    )
    if ar_account and revenue_account:
        JournalLine.objects.create(
            entry=entry, gl_account=ar_account, line_order=1,
            debit_amount=invoice.total_amount,
            description=f'AR from {invoice.customer.company_name}',
        )
        JournalLine.objects.create(
            entry=entry, gl_account=revenue_account, line_order=2,
            credit_amount=invoice.subtotal,
            description=f'Revenue for {invoice.invoice_number}',
        )
        if invoice.tax_amount and tax_account:
            JournalLine.objects.create(
                entry=entry, gl_account=tax_account, line_order=3,
                credit_amount=invoice.tax_amount,
                description='Output tax',
            )
        entry.recompute_totals()
        entry.save(update_fields=['total_debit', 'total_credit'])
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 11. Generate-from-source endpoints
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@tenant_admin_required
@require_POST
def generate_ap_bill_from_invoice_view(request, invoice_pk):
    from receiving.models import VendorInvoice
    inv = get_object_or_404(
        VendorInvoice.objects.filter(tenant=request.tenant), pk=invoice_pk,
    )
    existing = APBill.objects.filter(tenant=request.tenant, source_invoice=inv,
                                     deleted_at__isnull=True).first()
    if existing:
        messages.info(request, f'Bill {existing.bill_number} already exists for this invoice.')
        return redirect('accounting:ap_bill_detail', pk=existing.pk)

    expense_account = _coa_by_type(request.tenant, 'expense')
    if not expense_account:
        messages.error(request, 'No expense account found. Run `seed_accounting` first.')
        return redirect('accounting:ap_bill_list')

    with transaction.atomic():
        bill = APBill.objects.create(
            tenant=request.tenant,
            vendor=inv.vendor,
            source_invoice=inv,
            source_po=inv.purchase_order,
            bill_date=inv.invoice_date,
            due_date=inv.due_date,
            subtotal=inv.subtotal,
            tax_amount=inv.tax_amount,
            total_amount=inv.total_amount,
            description=f'Generated from vendor invoice {inv.invoice_number}',
            created_by=request.user,
        )
        APBillLine.objects.create(
            bill=bill, gl_account=expense_account,
            description=f'Vendor invoice {inv.invoice_number}',
            quantity=1, unit_price=inv.subtotal, tax_rate=0, line_order=1,
        )
    emit_audit(request, 'generate', bill, changes=f'from=vendor_invoice:{inv.invoice_number}')
    messages.success(request, f'Bill {bill.bill_number} generated from {inv.invoice_number}.')
    return redirect('accounting:ap_bill_detail', pk=bill.pk)


@login_required
@tenant_admin_required
@require_POST
def generate_ar_invoice_from_shipment_view(request, shipment_pk):
    from orders.models import Shipment
    shipment = get_object_or_404(
        Shipment.objects.select_related('sales_order').filter(tenant=request.tenant),
        pk=shipment_pk,
    )
    so = shipment.sales_order
    existing = ARInvoice.objects.filter(tenant=request.tenant, source_shipment=shipment,
                                        deleted_at__isnull=True).first()
    if existing:
        messages.info(request, f'Invoice {existing.invoice_number} already exists for this shipment.')
        return redirect('accounting:ar_invoice_detail', pk=existing.pk)

    revenue_account = _coa_by_type(request.tenant, 'revenue')
    if not revenue_account:
        messages.error(request, 'No revenue account found. Run `seed_accounting` first.')
        return redirect('accounting:ar_invoice_list')

    customer_name = (so.customer_name or '').strip() or 'Walk-in Customer'
    customer, _ = Customer.objects.get_or_create(
        tenant=request.tenant, company_name=customer_name,
        defaults={'contact_email': so.customer_email or '',
                  'contact_phone': so.customer_phone or '',
                  'billing_address': so.billing_address or ''},
    )
    with transaction.atomic():
        invoice = ARInvoice.objects.create(
            tenant=request.tenant,
            customer=customer,
            source_so=so, source_shipment=shipment,
            invoice_date=shipment.shipped_date.date() if shipment.shipped_date else so.order_date,
            due_date=(so.order_date + timedelta(days=30)) if so.order_date else None,
            subtotal=so.subtotal,
            tax_amount=so.tax_total,
            total_amount=so.grand_total,
            created_by=request.user,
        )
        ARInvoiceLine.objects.create(
            invoice=invoice, gl_account=revenue_account,
            description=f'Shipment {shipment.shipment_number} for SO {so.order_number}',
            quantity=1, unit_price=so.subtotal, tax_rate=0, line_order=1,
        )
    emit_audit(request, 'generate', invoice,
               changes=f'from=shipment:{shipment.shipment_number}')
    messages.success(request, f'Invoice {invoice.invoice_number} generated from {shipment.shipment_number}.')
    return redirect('accounting:ar_invoice_detail', pk=invoice.pk)


@login_required
@tenant_admin_required
@require_POST
def generate_journal_from_source_view(request, source_type, source_pk):
    valid = {'stock_adjustment', 'scrap_writeoff'}
    if source_type not in valid:
        raise Http404('Unsupported source_type')
    if source_type == 'stock_adjustment':
        from inventory.models import StockAdjustment
        src = get_object_or_404(StockAdjustment.objects.select_related('stock_level__product'),
                                pk=source_pk)
        if getattr(src.stock_level, 'product', None) and src.stock_level.product.tenant_id != request.tenant.id:
            raise Http404('Cross-tenant access denied')
        source_ref = src.adjustment_number
        description = f'Stock adjustment {src.adjustment_number} ({src.get_reason_display()})'
    else:  # scrap_writeoff
        from quality_control.models import ScrapWriteOff
        src = get_object_or_404(ScrapWriteOff.objects.filter(tenant=request.tenant), pk=source_pk)
        source_ref = src.scrap_number
        description = f'Scrap write-off {src.scrap_number}'

    existing = JournalEntry.objects.filter(
        tenant=request.tenant, source_type=source_type, source_id=str(source_pk),
        deleted_at__isnull=True,
    ).first()
    if existing:
        messages.info(request, f'Entry {existing.entry_number} already exists.')
        return redirect('accounting:journal_entry_detail', pk=existing.pk)

    period = _open_period_for_date(request.tenant, timezone.now().date())
    if period is None:
        messages.error(request, 'No open fiscal period. Create one first.')
        return redirect('accounting:journal_entry_list')

    entry = JournalEntry.objects.create(
        tenant=request.tenant,
        entry_date=timezone.now().date(),
        fiscal_period=period,
        source_type=source_type,
        source_reference=source_ref,
        source_id=str(source_pk),
        description=description,
        created_by=request.user,
    )
    emit_audit(request, 'generate', entry, changes=f'source={source_type}:{source_pk}')
    messages.success(request, f'Draft entry {entry.entry_number} created. Add lines and post.')
    return redirect('accounting:journal_entry_edit', pk=entry.pk)
