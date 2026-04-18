"""PDF rendering for barcode/QR labels.

`render_label_job_pdf(job)` returns PDF bytes for a LabelPrintJob.

Uses reportlab for PDF layout, python-barcode for linear barcodes, and qrcode
for QR codes. All rendering is synchronous and CPU-bound — fine for label
quantities in the hundreds; for tens of thousands, offload to a background
worker (out of scope for this module).
"""
from io import BytesIO

import barcode
from barcode.writer import ImageWriter
import qrcode
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas


# Map our stored symbology → python-barcode code.
_BARCODE_CODE_MAP = {
    'code128': 'code128',
    'code39': 'code39',
    'ean13': 'ean13',
    'ean8': 'ean8',
    'upca': 'upca',
    # QR / DataMatrix / PDF417 are handled separately (non-linear).
}

_PAPER_SIZE_MAP = {
    'a4': A4,
    'letter': letter,
    # Single-label stock sizes — the page itself is the label.
    'label_small': (40 * mm, 20 * mm),
    'label_medium': (60 * mm, 40 * mm),
    'label_large': (100 * mm, 60 * mm),
}


def _render_linear_barcode(symbology, value):
    """Return PNG bytes of a linear barcode for `value`."""
    code = _BARCODE_CODE_MAP.get(symbology, 'code128')
    barcode_cls = barcode.get_barcode_class(code)
    buffer = BytesIO()
    writer = ImageWriter()
    # write() expects the buffer; format defaults to PNG.
    barcode_cls(value, writer=writer).write(buffer, options={'write_text': True, 'quiet_zone': 2})
    buffer.seek(0)
    return buffer


def _render_qr(value):
    """Return PNG bytes of a QR code for `value`."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def _label_value_for_job(job):
    """Derive the scannable value for a job.

    Priority: target_display if set and non-trivial, else a synthetic encoding
    of target_type + target_id + job_number. Callers can override the value
    by populating target_display with a pre-resolved SKU / EPC / bin code.
    """
    if job.target_display and job.target_display.strip():
        return job.target_display.strip()
    if job.target_id:
        return f"{job.target_type.upper()}-{job.target_id:06d}"
    return job.job_number


def render_label_job_pdf(job):
    """Return PDF bytes containing `job.quantity * template.copies_per_label` labels."""
    template = job.template
    page_size = _PAPER_SIZE_MAP.get(template.paper_size, A4)
    buffer = BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=page_size)
    page_w, page_h = page_size

    value = _label_value_for_job(job)
    total_copies = max(1, int(job.quantity or 1)) * max(1, int(template.copies_per_label or 1))

    # For full-page stock (A4/Letter), tile N labels per page. For label stock,
    # one label per page.
    is_sheet = template.paper_size in ('a4', 'letter')

    label_w = template.width_mm * mm
    label_h = template.height_mm * mm

    if is_sheet:
        cols = max(1, int(page_w // label_w))
        rows = max(1, int(page_h // label_h))
        per_page = cols * rows
    else:
        cols = rows = 1
        per_page = 1
        label_w = page_w
        label_h = page_h

    for i in range(total_copies):
        if i > 0 and i % per_page == 0:
            c.showPage()
        idx_on_page = i % per_page
        col = idx_on_page % cols
        row = idx_on_page // cols
        x0 = col * label_w
        y0 = page_h - (row + 1) * label_h
        _draw_single_label(c, job, value, x0, y0, label_w, label_h)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def _draw_single_label(c, job, value, x, y, w, h):
    """Draw one label at (x, y) with width w and height h onto canvas c."""
    template = job.template
    padding = 2 * mm
    inner_w = w - 2 * padding
    inner_h = h - 2 * padding

    # Header text row: name / sku
    text_y = y + h - padding - 3 * mm
    if template.includes_name and job.target_display:
        c.setFont('Helvetica-Bold', 7)
        c.drawString(x + padding, text_y, job.target_display[:40])
        text_y -= 3 * mm

    # Decide code image area — bottom 60% of label
    code_h = inner_h * 0.55
    code_y = y + padding
    code_w = inner_w

    if template.label_type == 'qr' or template.symbology == 'qr':
        img_buffer = _render_qr(value)
        side = min(code_h, code_w)
        c.drawImage(ImageReader(img_buffer), x + (w - side) / 2, code_y, side, side, preserveAspectRatio=True)
    elif template.label_type == 'mixed':
        # Left half: linear barcode, right half: QR
        linear_buffer = _render_linear_barcode(template.symbology, value)
        qr_buffer = _render_qr(value)
        half_w = code_w / 2
        c.drawImage(ImageReader(linear_buffer), x + padding, code_y, half_w - 2, code_h, preserveAspectRatio=True)
        side = min(code_h, half_w - 2)
        c.drawImage(ImageReader(qr_buffer), x + padding + half_w + 1, code_y + (code_h - side) / 2, side, side, preserveAspectRatio=True)
    else:
        img_buffer = _render_linear_barcode(template.symbology, value)
        c.drawImage(ImageReader(img_buffer), x + padding, code_y, code_w, code_h, preserveAspectRatio=True)

    # Footer: value + job#
    c.setFont('Helvetica', 5)
    c.drawString(x + padding, y + padding - 1 * mm if False else y + 0.5 * mm, f"{value}  |  {job.job_number}")

    # Border (1pt)
    c.setLineWidth(0.3)
    c.rect(x, y, w, h)
