# goods_receipt_pdf.py
"""
مستند استلام البضاعة PDF (A4) بنفس هوية أمر الشراء:

  ترويسة بالشعار ← صندوقا المورد وبيانات الاستلام (رقم المستند، أمر الشراء،
  فاتورة المورد، التاريخ) ← جدول الأصناف (المطلوب، المستلم سابقاً، المستلم
  الآن، المتبقي) ← ملاحظات ← ختم وتوقيعات (المستلم / المورد أو السائق).
"""

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
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
    C_BLUE,
    C_GRID,
    C_NAVY,
    C_ZEBRA,
    FONT,
    FONT_BOLD,
    FOOTER_H,
    HEADER_H,
    MARGIN_X,
    MINI_HEADER_H,
    PAGE_H,
    ST_BOX_TITLE,
    ST_HEAD,
    ST_NOTES,
    _draw_cancelled_watermark,
    _draw_first_header,
    _draw_mini_header,
    _make_canvas_class,
    _style,
    fix_arabic,
    wrap_ar,
)
from purchase_pdf import _BAD, _OK, _meta_box, _supplier_box, _two_boxes
from voucher_pdf import _make_qr, _signature_block

# من اليسار لليمين: المتبقي | الآن | سابقاً | المطلوب | الوصف | الصنف | #
_COLS = [64, 72, 76, 62, 98, 123, 40]


def _qty(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _items_table(items):
    cell = _style("gr_cell", 9.5)
    cell_c = _style("gr_cell_c", 9.5, align=1)
    cell_bold = _style("gr_cell_b", 10, bold=True, align=1, color=_OK)

    header = [
        Paragraph(fix_arabic(title), ST_HEAD)
        for title in ("المتبقي", "مستلم الآن", "مستلم سابقاً",
                      "المطلوب", "الوصف", "الصنف", "#")
    ]
    data = [header]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 2, C_BLUE),
        ("GRID", (0, 0), (-1, -1), 0.5, C_GRID),
        ("BOX", (0, 0), (-1, -1), 1, C_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]

    for index, item in enumerate(items, start=1):
        remaining = float(item["remaining"])

        data.append([
            Paragraph(
                escape(_qty(remaining)),
                _style("gr_rem", 9.5, bold=True, align=1,
                       color=_BAD if remaining > 0.000001 else _OK),
            ),
            Paragraph(escape(_qty(item["qty"])), cell_bold),
            Paragraph(escape(_qty(item["before"])), cell_c),
            Paragraph(escape(_qty(item["ordered"])), cell_c),
            Paragraph(
                wrap_ar(item.get("desc") or "—", FONT, 9.5, _COLS[4] - 14),
                cell,
            ),
            Paragraph(wrap_ar(item["name"], FONT_BOLD, 10, _COLS[5] - 14),
                      _style("gr_name", 10, bold=True)),
            Paragraph(str(index), cell_c),
        ])

        if index % 2 == 0:
            style.append(("BACKGROUND", (0, index), (-1, index), C_ZEBRA))

    table = Table(data, colWidths=_COLS, repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def generate_goods_receipt_pdf(receipt, items, po=None, supplier=None,
                               file_path=None):
    """
    receipt:  قاموس من purchases_db.get_goods_receipt
    items:    من purchases_db.get_goods_receipt_items
    po:       (اختياري) أمر الشراء لعرض رقم فاتورة المورد
    supplier: (اختياري) قاموس المورد لإظهار الهاتف والعنوان
    """
    file_path = file_path or f"goods_receipt_{receipt['id']}.pdf"
    number = receipt["receipt_number"]
    cancelled = receipt.get("status") == "cancelled"
    supplier = supplier or {"name": receipt["supplier"]}
    invoice_no = (po or {}).get("supplier_invoice_no") or receipt.get(
        "supplier_invoice_no", ""
    )
    box_w = (CONTENT_W - 14) / 2

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
            c, number, title="استلام بضاعة",
            subtitle="G O O D S   R E C E I P T",
        )

    def on_later(c, doc):
        if cancelled:
            _draw_cancelled_watermark(c, "ملغى")
        _draw_mini_header(c, number, label="استلام بضاعة رقم")

    doc = BaseDocTemplate(
        file_path,
        pagesize=A4,
        title=f"Goods Receipt {number}",
        author=str(COMPANY.get("name") or ""),
        subject="Goods Receipt",
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first,
                     autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])

    meta = _meta_box(
        "بيانات الاستلام",
        [
            ("رقم الاستلام", number, True, None),
            ("أمر الشراء", receipt["po_number"] or "—", False, None),
            ("رقم فاتورة المورد", invoice_no or "—", False, None),
            ("تاريخ الاستلام", receipt["date"], False, None),
            ("الحالة", "ملغى" if cancelled else "فعّال", True,
             _BAD if cancelled else _OK),
        ],
        box_w,
    )

    elements = [
        _two_boxes(meta, _supplier_box(supplier, box_w), box_w),
        Spacer(1, 16),
        _items_table(items),
    ]

    notes = (receipt.get("notes") or "").strip()

    if notes:
        notes_box = Table(
            [
                [Paragraph(fix_arabic("ملاحظات"), ST_BOX_TITLE)],
                [Paragraph(wrap_ar(notes, FONT, 10, CONTENT_W - 24), ST_NOTES)],
            ],
            colWidths=[CONTENT_W],
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
        elements += [Spacer(1, 16), KeepTogether([notes_box])]

    elements += [
        Spacer(1, 26),
        KeepTogether([
            _signature_block(receipt["date"], "توقيع المورد / السائق",
                             "توقيع المستلم")
        ]),
    ]

    qr = _make_qr([
        f"Goods Receipt: {number}",
        f"PO: {receipt['po_number'] or '-'}",
        f"Supplier: {receipt['supplier']}",
        f"Date: {receipt['date']}",
        f"Qty: {_qty(receipt['total_qty'])}",
    ])

    doc.build(elements, canvasmaker=_make_canvas_class(qr))
    return file_path
