# voucher_pdf.py
"""
PDF احترافي لسندات القبض وسندات الصرف (A4) بنفس هوية الفاتورة:
ترويسة بالشعار، بيانات السند، المبلغ رقماً وكتابةً، ملخص الفاتورة/المصروف،
ختم وتوقيعات، وتذييل برمز QR.
"""

import os

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
from xml.sax.saxutils import escape

from arabic_words import amount_to_words
from database import payment_method_label
from pdf_generator import (
    ASSETS_DIR,
    CONTENT_W,
    COMPANY,
    C_BLUE,
    C_GRID,
    C_LIGHT,
    C_MUTED,
    C_NAVY,
    FONT,
    FONT_BOLD,
    FOOTER_H,
    HEADER_H,
    MARGIN_X,
    MINI_HEADER_H,
    PAGE_H,
    SignatureBox,
    StampBox,
    ST_BOX_TITLE,
    ST_LABEL,
    _draw_cancelled_watermark,
    _draw_first_header,
    _draw_mini_header,
    _make_canvas_class,
    _money_pdf,
    _plain_table_style,
    _style,
    fix_arabic,
    wrap_ar,
)

import io
import qrcode
from reportlab.lib.utils import ImageReader

LABEL_W = 140          # عرض عمود التسميات (موحّد في كل أقسام السند)

_OK_COLOR = colors.HexColor("#15803d")
_BAD_COLOR = colors.HexColor("#b91c1c")


# =========================
# أدوات صغيرة
# =========================
def _p(text, style):
    """فقرة نص عربي/مختلط في سطر واحد."""
    return Paragraph(escape(fix_arabic(str(text or ""))), style)


def _label(text):
    return Paragraph(fix_arabic(text), ST_LABEL)


def _box_style(extra=None):
    base = [
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    return TableStyle(base + (extra or []))


# =========================
# أجزاء السند
# =========================
def _info_section(party_title, party_name, number, date, number_label, cancelled):
    """يمين: الطرف الآخر (دافع/مستفيد) — يسار: بيانات السند."""
    box_w = (CONTENT_W - 14) / 2

    party_text = wrap_ar(party_name or "غير محدد", FONT_BOLD, 13, box_w - 28)
    party_box = Table(
        [
            [Paragraph(fix_arabic(party_title), ST_BOX_TITLE)],
            [Paragraph(party_text, _style("vp_party", 13, bold=True))],
        ],
        colWidths=[box_w],
    )
    party_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, 1), 12),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    status_color = _BAD_COLOR if cancelled else _OK_COLOR
    rows = [
        [_p(number, _style("vp_num", 10.5, bold=True, align=0)),
         _label(number_label)],
        [Paragraph(escape(str(date)), _style("vp_date", 10.5, align=0)),
         _label("التاريخ")],
        [_p("ملغى" if cancelled else "فعّال",
            _style("vp_status", 10.5, bold=True, align=0, color=status_color)),
         _label("الحالة")],
    ]

    inner = Table(rows, colWidths=[box_w - 100, 100])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), C_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    data_box = Table(
        [[Paragraph(fix_arabic("بيانات السند"), ST_BOX_TITLE)], [inner]],
        colWidths=[box_w],
    )
    data_box.setStyle(TableStyle([
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

    outer = Table([[data_box, "", party_box]], colWidths=[box_w, 14, box_w])
    outer.setStyle(_plain_table_style())
    return outer


def _amount_banner(amount):
    """شريط المبلغ الكبير: التسمية (يمين، كحلي) + الرقم (يسار)."""
    label_w = LABEL_W

    table = Table(
        [[
            Paragraph(
                escape(_money_pdf(amount)),
                _style("vp_amount", 22, bold=True, align=1, color=C_NAVY),
            ),
            Paragraph(
                fix_arabic("المبلغ"),
                _style("vp_amount_lbl", 13, bold=True, align=1,
                       color=colors.white),
            ),
        ]],
        colWidths=[CONTENT_W - label_w, label_w],
        rowHeights=[48],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), C_LIGHT),
        ("BACKGROUND", (1, 0), (1, 0), C_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _details_table(rows):
    """جدول تفاصيل (قيمة | تسمية) — rows: [(التسمية, القيمة, wrap?)]."""
    label_w = LABEL_W
    value_w = CONTENT_W - label_w
    data = []

    for label, value, wrap in rows:
        if wrap:
            cell = Paragraph(
                wrap_ar(value, FONT, 10, value_w - 28),
                _style("vp_val", 10, leading=15),
            )
        else:
            cell = _p(value, _style("vp_val1", 10.5, align=2))

        data.append([cell, _label(label)])

    table = Table(data, colWidths=[value_w, label_w])
    table.setStyle(_box_style([
        ("BACKGROUND", (1, 0), (1, -1), C_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, C_GRID),
    ]))
    return table


def _words_box(amount):
    words = amount_to_words(amount)
    label_w = LABEL_W
    value_w = CONTENT_W - label_w

    table = Table(
        [[
            Paragraph(
                wrap_ar(words, FONT_BOLD, 11, value_w - 28),
                _style("vp_words", 11, bold=True, leading=17, color=C_NAVY),
            ),
            _label("المبلغ كتابةً"),
        ]],
        colWidths=[value_w, label_w],
    )
    table.setStyle(_box_style([("BACKGROUND", (1, 0), (1, 0), C_LIGHT)]))
    return table


def _summary_table(headers_values):
    """شريط ملخص من 3 أعمدة: [(العنوان, القيمة, لون اختياري)] من اليمين لليسار."""
    n = len(headers_values)
    col_w = CONTENT_W / n

    # الترتيب المنطقي (الأول = الأقرب لليمين) → ترتيب الرسم من اليسار
    ordered = list(reversed(headers_values))

    head = [
        Paragraph(
            fix_arabic(title),
            _style("vp_sum_h", 9.5, bold=True, align=1, color=colors.white),
        )
        for title, _v, _c in ordered
    ]
    vals = [
        Paragraph(
            escape(_money_pdf(value)),
            _style("vp_sum_v", 11.5, bold=True, align=1,
                   color=color or colors.HexColor("#111827")),
        )
        for _t, value, color in ordered
    ]

    table = Table([head, vals], colWidths=[col_w] * n)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, C_GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _signature_block(date, left_label, right_label):
    """يسار: الطرف الآخر | وسط: الختم | يمين: توقيع الجهة."""
    cell_w = CONTENT_W / 3

    other = SignatureBox(left_label, width=cell_w)
    stamp = StampBox(
        COMPANY.get("name"), date,
        os.path.join(ASSETS_DIR, "stamp.png"), width=cell_w,
    )
    issuer = SignatureBox(
        right_label, os.path.join(ASSETS_DIR, "signature.png"),
        sub_label=COMPANY.get("signatory", ""), width=cell_w,
    )

    block = Table([[other, stamp, issuer]], colWidths=[cell_w] * 3)
    block.setStyle(_plain_table_style([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return block


def _make_qr(lines):
    image = qrcode.make("\n".join(lines))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


# =========================
# البناء العام
# =========================
def _build_voucher_pdf(
    file_path, *, title, subtitle, doc_subject, number, date, cancelled,
    party_title, party_name, number_label, mini_label, amount,
    detail_rows, summary, left_sign, right_sign, qr_lines,
):
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
        _draw_first_header(c, number, title=title, subtitle=subtitle)

    def on_later(c, doc):
        if cancelled:
            _draw_cancelled_watermark(c, "ملغى")
        _draw_mini_header(c, number, label=mini_label)

    doc = BaseDocTemplate(
        file_path,
        pagesize=A4,
        title=f"{doc_subject} {number}",
        author=str(COMPANY.get("name") or ""),
        subject=doc_subject,
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first,
                     autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])

    elements = [
        _info_section(party_title, party_name, number, date,
                      number_label, cancelled),
        Spacer(1, 16),
        _amount_banner(amount),
        Spacer(1, 8),
        _words_box(amount),
        Spacer(1, 14),
        _details_table(detail_rows),
    ]

    if summary:
        elements += [Spacer(1, 14), KeepTogether([_summary_table(summary)])]

    elements += [
        Spacer(1, 26),
        KeepTogether([_signature_block(date, left_sign, right_sign)]),
    ]

    doc.build(elements, canvasmaker=_make_canvas_class(_make_qr(qr_lines)))
    return file_path


# =========================
# سند قبض
# =========================
def generate_receipt_pdf(receipt, summary=None, file_path=None):
    """
    receipt: قاموس من database.get_receipt
    summary: اختياري من database.get_receipt_invoice_summary
    يرجع مسار الملف (receipt_<id>.pdf افتراضياً).
    """
    file_path = file_path or f"receipt_{receipt['id']}.pdf"

    rows = [("طريقة الدفع", payment_method_label(receipt["payment_method"]), False)]

    if receipt.get("reference"):
        rows.append(("رقم الشيك / المرجع", receipt["reference"], False))

    if receipt.get("invoice_number"):
        rows.append(("عن فاتورة رقم", receipt["invoice_number"], False))
    else:
        rows.append(("نوع الدفعة", "دفعة على الحساب", False))

    if receipt.get("notes"):
        rows.append(("البيان", receipt["notes"], True))

    summary_cells = None

    if summary:
        summary_cells = [
            ("إجمالي الفاتورة", summary["total"], None),
            ("إجمالي المحصّل", summary["collected"], _OK_COLOR),
            ("المتبقي", summary["remaining"],
             _BAD_COLOR if summary["remaining"] > 0.005 else _OK_COLOR),
        ]

    return _build_voucher_pdf(
        file_path,
        title="سند قبض",
        subtitle="R E C E I P T   V O U C H E R",
        doc_subject="Receipt Voucher",
        number=receipt["receipt_number"],
        date=receipt["date"],
        cancelled=receipt.get("status") == "cancelled",
        party_title="استلمنا من السيد/ة",
        party_name=receipt["client"],
        number_label="رقم السند",
        mini_label="سند قبض رقم",
        amount=receipt["amount"],
        detail_rows=rows,
        summary=summary_cells,
        left_sign="توقيع الدافع",
        right_sign="توقيع المستلم",
        qr_lines=[
            f"Receipt: {receipt['receipt_number']}",
            f"From: {receipt['client']}",
            f"Date: {receipt['date']}",
            f"Amount: {receipt['amount']}",
        ],
    )


# =========================
# سند صرف
# =========================
def generate_payment_voucher_pdf(voucher, summary=None, file_path=None):
    """
    voucher: قاموس من database.get_payment_voucher
    summary: اختياري من database.get_voucher_expense_summary
    """
    file_path = file_path or f"payment_{voucher['id']}.pdf"

    rows = [("طريقة الدفع", payment_method_label(voucher["payment_method"]), False)]

    if voucher.get("reference"):
        rows.append(("رقم الشيك / المرجع", voucher["reference"], False))

    if voucher.get("expense_number"):
        rows.append((
            "عن مصروف رقم",
            f"{voucher['expense_number']} — {voucher.get('expense_title') or ''}",
            False,
        ))

    if voucher.get("category") and voucher["category"] != "غير مصنف":
        rows.append(("التصنيف", voucher["category"], False))

    if voucher.get("notes"):
        rows.append(("البيان", voucher["notes"], True))

    summary_cells = None

    if summary:
        summary_cells = [
            ("إجمالي المصروف", summary["total"], None),
            ("إجمالي المدفوع", summary["paid"], _OK_COLOR),
            ("المتبقي", summary["remaining"],
             _BAD_COLOR if summary["remaining"] > 0.005 else _OK_COLOR),
        ]

    return _build_voucher_pdf(
        file_path,
        title="سند صرف",
        subtitle="P A Y M E N T   V O U C H E R",
        doc_subject="Payment Voucher",
        number=voucher["voucher_number"],
        date=voucher["date"],
        cancelled=voucher.get("status") == "cancelled",
        party_title="صرفنا إلى السيد/ة",
        party_name=voucher["payee"],
        number_label="رقم السند",
        mini_label="سند صرف رقم",
        amount=voucher["amount"],
        detail_rows=rows,
        summary=summary_cells,
        left_sign="توقيع المستلم",
        right_sign="توقيع المُصدِر",
        qr_lines=[
            f"Payment: {voucher['voucher_number']}",
            f"To: {voucher['payee']}",
            f"Date: {voucher['date']}",
            f"Amount: {voucher['amount']}",
        ],
    )
