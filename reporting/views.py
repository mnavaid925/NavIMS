"""Generic dispatcher views for Module 18 — Reporting & Analytics.

Every view is keyed by `report_type` (the registry slug). The view looks up the
report spec in `reporting.registry.REPORTS`, then dispatches to the right
compute service / form / template. 7 URL patterns cover all 21 reports.
"""
import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import emit_audit, tenant_admin_required

from .models import ReportSnapshot
from .registry import REPORTS, SECTIONS, get_report, resolve, sections_with_reports


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _spec_or_404(report_type):
    spec = get_report(report_type)
    if not spec:
        raise Http404(f'Unknown report type: {report_type}')
    return spec


def _json_default(value):
    """JSON encoder for Decimal / date / datetime — safe to pass to json.dumps."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _form_params_to_compute_kwargs(cleaned_data):
    """Translate form.cleaned_data into the kwargs expected by compute_* services."""
    out = {}
    for k, v in cleaned_data.items():
        if k in ('title', 'notes'):
            continue
        out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Index (landing page)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def index_view(request):
    tenant = getattr(request, 'tenant', None)
    recent = []
    if tenant:
        recent = (ReportSnapshot.objects.filter(tenant=tenant)
                  .select_related('generated_by')
                  .order_by('-generated_at')[:10])
    return render(request, 'reporting/index.html', {
        'sections': list(sections_with_reports()),
        'recent': recent,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Per-report views
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def snapshot_list_view(request, report_type):
    spec = _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    qs = ReportSnapshot.objects.filter(tenant=tenant, report_type=report_type).select_related('generated_by', 'warehouse')

    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(title__icontains=q) | Q(report_number__icontains=q) | Q(notes__icontains=q))

    warehouse_id = request.GET.get('warehouse', '').strip()
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    date_from = request.GET.get('date_from', '').strip()
    if date_from:
        qs = qs.filter(generated_at__date__gte=date_from)
    date_to = request.GET.get('date_to', '').strip()
    if date_to:
        qs = qs.filter(generated_at__date__lte=date_to)

    # Pass warehouse options for filter dropdown
    from warehousing.models import Warehouse
    warehouses = Warehouse.objects.filter(tenant=tenant) if tenant else Warehouse.objects.none()

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'reporting/snapshot_list.html', {
        'spec': spec,
        'report_type': report_type,
        'snapshots': page_obj,
        'warehouses': warehouses,
        'section_meta': SECTIONS.get(spec['section'], {}),
    })


@login_required
@tenant_admin_required
def snapshot_generate_view(request, report_type):
    spec = _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        messages.error(request, 'A tenant context is required to generate reports. Log in as a tenant admin.')
        return redirect('reporting:index')

    form_class = resolve(spec['form'])
    service_fn = resolve(spec['service'])

    if request.method == 'POST':
        form = form_class(request.POST, tenant=tenant)
        if form.is_valid():
            cleaned = form.cleaned_data
            compute_kwargs = _form_params_to_compute_kwargs(cleaned)
            result = service_fn(tenant, **compute_kwargs)
            # Serialize parameters (FKs → pk / name for traceability)
            params_for_save = {}
            for k, v in compute_kwargs.items():
                if hasattr(v, 'pk'):
                    params_for_save[k] = {'pk': v.pk, 'label': str(v)}
                elif isinstance(v, (date, datetime)):
                    params_for_save[k] = v.isoformat()
                elif isinstance(v, Decimal):
                    params_for_save[k] = str(v)
                else:
                    params_for_save[k] = v
            snap = ReportSnapshot.objects.create(
                tenant=tenant,
                report_type=report_type,
                title=cleaned.get('title') or spec['title'],
                as_of_date=cleaned.get('as_of_date'),
                period_start=cleaned.get('period_start'),
                period_end=cleaned.get('period_end'),
                warehouse=cleaned.get('warehouse'),
                category=cleaned.get('category'),
                parameters=params_for_save,
                summary=json.loads(json.dumps(result.get('summary', {}), default=_json_default)),
                data=json.loads(json.dumps(result.get('data', {}), default=_json_default)),
                generated_by=request.user,
                notes=cleaned.get('notes') or '',
            )
            emit_audit(request, 'create', snap, changes=f'Generated {spec["title"]} report')
            messages.success(request, f'Generated {snap.report_number} — {snap.title}.')
            return redirect('reporting:snapshot_detail', report_type=report_type, pk=snap.pk)
    else:
        initial = {'title': spec['title']}
        form = form_class(tenant=tenant, initial=initial)

    return render(request, 'reporting/snapshot_form.html', {
        'spec': spec,
        'report_type': report_type,
        'form': form,
        'section_meta': SECTIONS.get(spec['section'], {}),
    })


@login_required
def snapshot_detail_view(request, report_type, pk):
    spec = _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    snap = get_object_or_404(ReportSnapshot, pk=pk, tenant=tenant, report_type=report_type)

    data = snap.data or {}
    rows = data.get('rows', [])
    columns = data.get('columns', [c[1] for c in spec.get('csv_columns', [])])
    headers = {c[1]: c[0] for c in spec.get('csv_columns', [])}
    chart = data.get('chart')
    chart_json = json.dumps(chart, default=_json_default) if chart else 'null'

    return render(request, 'reporting/snapshot_detail.html', {
        'spec': spec,
        'report_type': report_type,
        'snap': snap,
        'summary': snap.summary or {},
        'rows': rows,
        'columns': columns,
        'column_headers': headers,
        'chart_json': chart_json,
        'section_meta': SECTIONS.get(spec['section'], {}),
    })


@login_required
@tenant_admin_required
@require_POST
def snapshot_delete_view(request, report_type, pk):
    _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    snap = get_object_or_404(ReportSnapshot, pk=pk, tenant=tenant, report_type=report_type)
    number = snap.report_number
    emit_audit(request, 'delete', snap, changes=f'Deleted report {number}')
    snap.delete()
    messages.success(request, f'Deleted report {number}.')
    return redirect('reporting:snapshot_list', report_type=report_type)


@login_required
def snapshot_export_csv_view(request, report_type, pk):
    spec = _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    snap = get_object_or_404(ReportSnapshot, pk=pk, tenant=tenant, report_type=report_type)

    data = snap.data or {}
    rows = data.get('rows', [])
    csv_cols = spec.get('csv_columns', [])
    if not csv_cols:
        headers = list(rows[0].keys()) if rows else []
        csv_cols = [(h, h) for h in headers]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([h for h, _ in csv_cols])
    for r in rows:
        writer.writerow([_csv_cell(r.get(k, '')) for _, k in csv_cols])

    response = HttpResponse(buf.getvalue(), content_type='text/csv')
    filename = f'{snap.report_number}_{report_type}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _csv_cell(value):
    if value is None:
        return ''
    return str(value)


@login_required
def snapshot_export_pdf_view(request, report_type, pk):
    spec = _spec_or_404(report_type)
    tenant = getattr(request, 'tenant', None)
    snap = get_object_or_404(ReportSnapshot, pk=pk, tenant=tenant, report_type=report_type)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        )
    except ImportError:
        messages.error(request, 'reportlab is not available; PDF export disabled.')
        return redirect('reporting:snapshot_detail', report_type=report_type, pk=pk)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    h1 = styles['Heading1']
    h3 = styles['Heading3']
    normal = styles['BodyText']

    story = []
    story.append(Paragraph(f"{snap.report_number} — {snap.title}", h1))
    story.append(Paragraph(f"Report type: {spec['title']}", normal))
    story.append(Paragraph(f"Generated: {snap.generated_at.strftime('%Y-%m-%d %H:%M')}", normal))
    if snap.generated_by:
        story.append(Paragraph(f"Generated by: {snap.generated_by.get_username()}", normal))
    story.append(Spacer(1, 8))

    # Summary block
    if snap.summary:
        story.append(Paragraph('Summary', h3))
        summary_rows = [[str(k), str(v)] for k, v in snap.summary.items() if not isinstance(v, (dict, list))]
        if summary_rows:
            tbl = Table([['Metric', 'Value']] + summary_rows, colWidths=[60 * mm, 120 * mm])
            tbl.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 8))

    # Data table (truncated to first 200 rows for PDF sanity)
    data = snap.data or {}
    rows = data.get('rows', [])[:200]
    csv_cols = spec.get('csv_columns') or [(k, k) for k in (rows[0].keys() if rows else [])]
    if rows:
        story.append(Paragraph(f'Data ({len(rows)} rows shown)', h3))
        header = [h for h, _ in csv_cols]
        body = [[str(r.get(k, ''))[:60] for _, k in csv_cols] for r in rows]
        tbl = Table([header] + body, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph('No rows to display.', normal))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'{snap.report_number}_{report_type}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
