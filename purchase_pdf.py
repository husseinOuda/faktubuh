# purchase_pdf.py
"""
PDF أمر الشراء (A4) بنفس هوية الفاتورة:
ترويسة بالشعار، صندوقا المورد وأمر الشراء (مع رقم فاتورة المورد)، جدول
أصناف، ملخص مالي يتضمن المدفوع والمتبقي، ملاحظات، ختم وتوقيع، وتذييل بـ QR.
"""

import io
import os
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from pdf_generator import (
    CONTENT_W,
    COMPANY,
    C_GRID,
    C_LIGHT,
    C_NAVY,
    FOOTER_H,
    HEADER_H,
    MARGIN_X,
    MINI_HEADER_H,
    PAGE_H,
    ST_BOX_TITLE,
    ST_LABEL,
    ST_NOTES,
    ST_SUM_LABEL,
    ST_TOTAL_LABEL,
    ST_TOTAL_VALUE,
    FONT,
    FONT_BOLD,
    _draw_cancelled_watermark,
    _draw_first_header,
    _draw_mini_header,
    _items_table,
    _make_canvas_class,
    _money_pdf,
    _plain_table_style,
    _signature_block,
    _style,
    fix_arabic,
    wrap_ar,
)
from ui.components.invoice_utils import round_money

_OK = colors.HexColor("#15803d")
_WARN = colors.HexColor("#c2410c")
_BAD = colors.HexColor("#b91c1c")

_PAY_LABELS = {
    "unpaid": ("غير مسدد", _BAD),
    "partial": ("مسدد جزئياً", _WARN),
    "paid": ("مسدد", _OK),
}


# =========================
# صندوقا المورد وأمر الشراء
# =========================
def _supplier_box(supplier, box_w):
    """صندوق «بيانات المورد» (مشترك مع مستند الاستلام)."""
    name = (supplier or {}).get("name") or "غير محدد"
    lines = [
        Paragraph(
            wrap_ar(name, FONT_BOLD, 13, box_w - 28),
            _style("sup_name", 13, bold=True),
        )
    ]

    for text in (
        (supplier or {}).get("phone"),
        (supplier or {}).get("email"),
        (supplier or {}).get("address"),
    ):
        if text:
            lines.append(Paragraph(
                wrap_ar(text, FONT, 9.5, box_w - 28),
                _style("sup_line", 9.5, color=colors.HexColor("#475569")),
            ))

    supplier_inner = Table([[line] for line in lines], colWidths=[box_w - 24])
    supplier_inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    box = Table(
        [
            [Paragraph(fix_arabic("بيانات المورد"), ST_BOX_TITLE)],
            [supplier_inner],
        ],
        colWidths=[box_w],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return box


def _meta_box(title, fields, box_w):
    """
    صندوق بيانات المستند: fields = [(التسمية, القيمة, bold, color)] —
    (مشترك مع مستند الاستلام).
    """
    def value(text, bold=False, color=None):
        return Paragraph(
            escape(fix_arabic(str(text))),
            _style("po_v", 10.5, bold=bold, align=0,
                   color=color or colors.HexColor("#111827")),
        )

    rows = [
        [value(text, bold, color), Paragraph(fix_arabic(label), ST_LABEL)]
        for label, text, bold, color in fields
    ]

    inner = Table(rows, colWidths=[box_w - 130, 130])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), C_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    box = Table(
        [[Paragraph(fix_arabic(title), ST_BOX_TITLE)], [inner]],
        colWidths=[box_w],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, 0), 12),
        ("RIGHTPADDING", (0, 0), (-1, 0), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING", (0, 1), (-1, 1), 0),
        ("RIGHTPADDING", (0, 1), (-1, 1), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
    ]))
    return box


def _two_boxes(meta_box, supplier_box, box_w):
    """ترتيب اليسار → اليمين: المستند | فراغ | المورد."""
    outer = Table([[meta_box, "", supplier_box]], colWidths=[box_w, 14, box_w])
    outer.setStyle(_plain_table_style())
    return outer


def _info_section(po_number, supplier, invoice_no, date, pay_status,
                  cancelled):
    box_w = (CONTENT_W - 14) / 2

    if cancelled:
        status_text, status_color = "ملغى", _BAD
    else:
        status_text, status_color = _PAY_LABELS.get(
            pay_status, _PAY_LABELS["unpaid"]
        )

    meta = _meta_box(
        "بيانات أمر الشراء",
        [
            ("رقم أمر الشراء", po_number, True, None),
            ("رقم فاتورة المورد", invoice_no or "—", False, None),
            ("التاريخ", date, False, None),
            ("الحالة", status_text, True, status_color),
        ],
        box_w,
    )

    return _two_boxes(meta, _supplier_box(supplier, box_w), box_w)


# =========================
# الملخص المالي + الملاحظات
# =========================
def _summary_and_notes(subtotal, discount_percent, discount_amount,
                       tax_percent, tax_amount, total, paid, remaining,
                       notes):
    totals_w = 262
    gap = 14
    notes_w = CONTENT_W - totals_w - gap

    def label(text):
        return Paragraph(escape(fix_arabic(text)), ST_SUM_LABEL)

    def money(value, color=None, bold=False):
        style = _style("po_money", 10.5, bold=bold, align=0,
                       color=color or colors.HexColor("#111827"))
        return Paragraph(_money_pdf(value), style)

    rows = [
        [money(subtotal), label("المجموع الفرعي")],
        [money(discount_amount), label(f"الخصم ({discount_percent:g}%)")],
        [money(tax_amount), label(f"الضريبة ({tax_percent:g}%)")],
        [
            Paragraph(_money_pdf(total), ST_TOTAL_VALUE),
            Paragraph(fix_arabic("الإجمالي"), ST_TOTAL_LABEL),
        ],
        [money(paid, _OK, True), label("المدفوع")],
        [
            money(remaining, _BAD if remaining > 0.005 else _OK, True),
            label("المتبقي"),
        ],
    ]

    totals = Table(rows, colWidths=[totals_w - 136, 136])
    totals.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, C_NAVY),
        ("LINEBELOW", (0, 0), (-1, 2), 0.5, C_GRID),
        ("LINEBELOW", (0, 4), (-1, 4), 0.5, C_GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BACKGROUND", (1, 0), (1, 2), C_LIGHT),
        ("BACKGROUND", (1, 4), (1, 5), C_LIGHT),
        ("BACKGROUND", (0, 3), (-1, 3), C_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 3), (-1, 3), 9),
        ("BOTTOMPADDING", (0, 3), (-1, 3), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    notes = (notes or "").strip()

    if notes:
        notes_box = Table(
            [
                [Paragraph(fix_arabic("ملاحظات"), ST_BOX_TITLE)],
                [Paragraph(wrap_ar(notes, FONT, 10, notes_w - 24), ST_NOTES)],
            ],
            colWidths=[notes_w],
        )
        notes_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fffbeb")),
            ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 1), (-1, 1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ]))
    else:
        notes_box = ""

    outer = Table([[totals, "", notes_box]], colWidths=[totals_w, gap, notes_w])
    outer.setStyle(_plain_table_style())
    return outer


def _make_qr(lines):
    image = qrcode.make("\n".join(lines))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


# =========================
# البناء الأساسي
# =========================
def _build_po_pdf(file_path, *, po_number, supplier, invoice_no, date, items,
                  subtotal, discount_percent, discount_amount, tax_percent,
                  tax_amount, total, paid, notes, pay_status, cancelled):

    date = date or datetime.now().strftime("%Y-%m-%d")

    items_total = round_money(sum(float(item[4]) for item in items))
    subtotal = round_money(subtotal or items_total)
    discount_percent = round_money(discount_percent)
    discount_amount = round_money(discount_amount)
    tax_percent = round_money(tax_percent)
    tax_amount = round_money(tax_amount)
    total = round_money(
        total or (subtotal - discount_amount + tax_amount)
    )
    paid = round_money(paid or 0)
    remaining = 0.0 if cancelled else max(round_money(total - paid), 0.0)

    frame_kwargs = dict(
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0
    )
    first_frame = Frame(
        MARGIN_X, FOOTER_H,
        CONTENT_W, PAGE_H - FOOTER_H - HEADER_H - 24,
        id="first", **frame_kwargs,
    )
    later_frame = Frame(
        MARGIN_X, FOOTER_H,
        CONTENT_W, PAGE_H - FOOTER_H - MINI_HEADER_H - 22,
        id="later", **frame_kwargs,
    )

    def on_first(c, doc):
        if cancelled:
            _draw_cancelled_watermark(c, "ملغى")
        _draw_first_header(
            c, po_number, title="أمر شراء",
            subtitle="P U R C H A S E   O R D E R",
        )

    def on_later(c, doc):
        if cancelled:
            _draw_cancelled_watermark(c, "ملغى")
        _draw_mini_header(c, po_number, label="أمر شراء رقم")

    doc = BaseDocTemplate(
        file_path,
        pagesize=A4,
        title=f"Purchase Order {po_number}",
        author=str(COMPANY.get("name") or ""),
        subject="Purchase Order",
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first,
                     autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])

    elements = [
        _info_section(po_number, supplier, invoice_no, date, pay_status,
                      cancelled),
        Spacer(1, 16),
        _items_table(items),
        Spacer(1, 16),
        KeepTogether([
            _summary_and_notes(
                subtotal, discount_percent, discount_amount,
                tax_percent, tax_amount, total, paid, remaining, notes,
            ),
        ]),
        Spacer(1, 22),
        KeepTogether([_signature_block(date)]),
    ]

    qr = _make_qr([
        f"Purchase Order: {po_number}",
        f"Supplier: {(supplier or {}).get('name', '')}",
        f"Supplier Invoice: {invoice_no or '-'}",
        f"Date: {date}",
        f"Total: {total}",
        f"Paid: {paid}",
    ])

    doc.build(elements, canvasmaker=_make_canvas_class(qr))
    return file_path


# =========================
# الواجهات العامة
# =========================
def generate_purchase_order_pdf(po, items, supplier=None, file_path=None):
    """
    po:       قاموس من purchases_db.get_purchase_order
    items:    قواميس من purchases_db.get_purchase_order_items
    supplier: قاموس من purchases_db.get_supplier (اختياري: يضيف الهاتف والعنوان)
    """
    file_path = file_path or f"purchase_order_{po['id']}.pdf"
    supplier = supplier or {"name": po["supplier"]}

    rows = [
        (i["name"], i.get("desc", ""), i["qty"], i["price"], i["total"])
        for i in items
    ]

    return _build_po_pdf(
        file_path,
        po_number=po["po_number"],
        supplier=supplier,
        invoice_no=po.get("supplier_invoice_no", ""),
        date=po["date"],
        items=rows,
        subtotal=po["subtotal"],
        discount_percent=po["discount_percent"],
        discount_amount=po["discount_amount"],
        tax_percent=po["tax_percent"],
        tax_amount=po["tax_amount"],
        total=po["total"],
        paid=po["paid"],
        notes=po.get("notes", ""),
        pay_status=po.get("pay_status"),
        cancelled=po.get("status") == "cancelled",
    )


def generate_temp_purchase_pdf(supplier, items, summary=None, notes="",
                               invoice_no="", date=None, paid=0):
    """
    معاينة/طباعة أمر شراء غير محفوظ بنفس التصميم النهائي.
    items: قواميس {name, desc, qty, price, total} كما في صفحة الإنشاء.
    """
    summary = summary or {}

    pdf_path = os.path.join(tempfile.gettempdir(), "purchase_order_preview.pdf")

    rows = [
        (
            item.get("name", ""),
            item.get("desc", ""),
            item.get("qty", 0),
            item.get("price", 0),
            item.get("total", 0),
        )
        for item in items
    ]

    total = summary.get("total", 0)

    if paid and paid >= total - 0.005 and total:
        pay_status = "paid"
    elif paid:
        pay_status = "partial"
    else:
        pay_status = "unpaid"

    return _build_po_pdf(
        pdf_path,
        po_number="مسودة",
        supplier=supplier,
        invoice_no=invoice_no,
        date=date,
        items=rows,
        subtotal=summary.get("subtotal", 0),
        discount_percent=summary.get("discount_percent", 0),
        discount_amount=summary.get("discount_amount", 0),
        tax_percent=summary.get("tax_percent", 0),
        tax_amount=summary.get("tax_amount", 0),
        total=total,
        paid=paid,
        notes=notes,
        pay_status=pay_status,
        cancelled=False,
    )
