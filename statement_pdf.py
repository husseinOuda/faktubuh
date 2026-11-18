# statement_pdf.py
"""
كشف حساب العميل PDF (A4) بنفس هوية الفاتورة وسندات القبض:

  ترويسة بالشعار ← بيانات العميل وبيانات الكشف ← شريط ملخص (افتتاحي، مدين،
  دائن، ختامي) ← جدول الحركات برصيد تراكمي ← الرصيد المستحق رقماً وكتابةً
  ← ختم وتوقيعات ← تذييل بترقيم الصفحات ورمز QR.

الاستخدام:
    from database import get_client_statement
    statement = get_client_statement(client_id, start, end)
    path = generate_statement_pdf(statement)
"""

import os
from datetime import date as _date
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

from arabic_words import amount_to_words
from pdf_generator import (
    CONTENT_W,
    COMPANY,
    C_BLUE,
    C_GRID,
    C_LIGHT,
    C_MUTED,
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
    ST_LABEL,
    _draw_first_header,
    _draw_mini_header,
    _make_canvas_class,
    _money_pdf,
    _plain_table_style,
    _style,
    fix_arabic,
    wrap_ar,
)
from voucher_pdf import _make_qr, _signature_block
from ui.components.invoice_utils import format_money

_RED = colors.HexColor("#b91c1c")
_GREEN = colors.HexColor("#15803d")
_GREY = colors.HexColor("#9ca3af")

_STATE_TEXT = {"debit": "عليه", "credit": "له", "zero": "مسدّد"}
_KIND_TEXT = {"invoice": "فاتورة", "receipt": "سند قبض", "manual": "تسديد"}

# عروض الأعمدة من اليسار لليمين: الرصيد | دائن | مدين | البيان | المستند | التاريخ | #
_COLS = [86, 72, 72, 124, 78, 63, 28]


def _p(text, style):
    return Paragraph(escape(fix_arabic(str(text or ""))), style)


def _signed(amount, with_state=True):
    """رصيد للعرض: القيمة المطلقة + (عليه/له)."""
    state = "debit" if amount > 0.005 else "credit" if amount < -0.005 else "zero"
    text = format_money(abs(amount), symbol=False)

    if with_state and state != "zero":
        text = f"{text} {_STATE_TEXT[state]}"

    return text, state


def _state_color(state):
    return _RED if state == "debit" else _GREEN if state == "credit" else C_NAVY


def _period_text(statement):
    start, end = statement.get("start"), statement.get("end")

    if start and end:
        return f"{start}  →  {end}"

    if start:
        return f"من {start}"

    if end:
        return f"حتى {end}"

    return "كل الفترات"


# =========================
# أجزاء الكشف
# =========================
def _info_section(statement, issued):
    client = statement["client"]
    box_w = (CONTENT_W - 14) / 2

    # ---- بيانات العميل (يمين) ----
    lines = [wrap_ar(client["name"], FONT_BOLD, 13, box_w - 28)]
    small = _style("st_client_small", 9.5, color=C_MUTED, leading=14)

    contact = []
    if client.get("phone"):
        contact.append(f"هاتف: {client['phone']}")
    if client.get("email"):
        contact.append(f"بريد: {client['email']}")
    if client.get("address"):
        contact.append(f"العنوان: {client['address']}")

    body = [[Paragraph(lines[0], _style("st_client", 13, bold=True))]]

    for text in contact:
        body.append([
            Paragraph(wrap_ar(text, FONT, 9.5, box_w - 28), small)
        ])

    inner = Table(body, colWidths=[box_w - 24])
    inner.setStyle(_plain_table_style([("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))

    client_box = Table(
        [[Paragraph(fix_arabic("بيانات العميل"), ST_BOX_TITLE)], [inner]],
        colWidths=[box_w],
    )
    client_box.setStyle(TableStyle([
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

    # ---- بيانات الكشف (يسار) ----
    rows = [
        [_p(_period_text(statement), _style("st_v1", 10.5, bold=True, align=0)),
         Paragraph(fix_arabic("الفترة"), ST_LABEL)],
        [Paragraph(escape(issued), _style("st_v2", 10.5, align=0)),
         Paragraph(fix_arabic("تاريخ الإصدار"), ST_LABEL)],
        [Paragraph(str(len(statement["rows"])),
                   _style("st_v3", 10.5, align=0)),
         Paragraph(fix_arabic("عدد الحركات"), ST_LABEL)],
    ]

    meta_inner = Table(rows, colWidths=[box_w - 100, 100])
    meta_inner.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), C_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    meta_box = Table(
        [[Paragraph(fix_arabic("بيانات الكشف"), ST_BOX_TITLE)], [meta_inner]],
        colWidths=[box_w],
    )
    meta_box.setStyle(TableStyle([
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

    outer = Table([[meta_box, "", client_box]], colWidths=[box_w, 14, box_w])
    outer.setStyle(_plain_table_style())
    return outer


def _summary_strip(statement):
    """أربع خانات من اليمين: افتتاحي | مدين | دائن | ختامي."""
    opening_text, opening_state = _signed(statement["opening"])
    closing_text, closing_state = _signed(statement["closing"])

    cells = [
        ("الرصيد الافتتاحي", opening_text, _state_color(opening_state)),
        ("إجمالي المدين (فواتير)",
         format_money(statement["total_debit"], symbol=False), C_NAVY),
        ("إجمالي الدائن (مقبوضات)",
         format_money(statement["total_credit"], symbol=False), _GREEN),
        ("الرصيد الختامي", closing_text, _state_color(closing_state)),
    ]

    ordered = list(reversed(cells))     # الرسم من اليسار
    col_w = CONTENT_W / len(cells)

    head = [
        Paragraph(
            fix_arabic(title),
            _style("st_sum_h", 9, bold=True, align=1, color=colors.white),
        )
        for title, _v, _c in ordered
    ]
    vals = [
        Paragraph(
            escape(fix_arabic(value)),
            _style("st_sum_v", 11.5, bold=True, align=1, color=color),
        )
        for _t, value, color in ordered
    ]

    table = Table([head, vals], colWidths=[col_w] * len(cells))
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


def _movements_table(statement):
    cell = _style("st_cell", 9)
    cell_c = _style("st_cell_c", 9, align=1)
    cell_num = _style("st_cell_num", 9, align=2)
    cell_grey = _style("st_cell_g", 9, color=_GREY)
    desc_w = _COLS[3] - 14

    header = [
        Paragraph(fix_arabic(title), ST_HEAD)
        for title in ("الرصيد", "دائن", "مدين", "البيان", "المستند",
                      "التاريخ", "#")
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
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (6, 1), (6, -1), C_LIGHT),
    ]

    def money_cell(value, color=None, muted=False):
        if not value:
            return Paragraph("—", _style("st_dash", 9, align=1, color=_GREY))

        return Paragraph(
            escape(format_money(value, symbol=False)),
            _style("st_money", 9, align=2, color=color or colors.HexColor("#111827")),
        )

    def balance_cell(amount, muted=False):
        text, state = _signed(amount)
        color = _GREY if muted else _state_color(state)
        return Paragraph(
            escape(fix_arabic(text)),
            _style("st_bal", 9, bold=True, align=2, color=color),
        )

    row_no = 0

    # الرصيد الافتتاحي
    if statement["start"] or abs(statement["opening"]) > 0.005:
        data.append([
            balance_cell(statement["opening"]),
            money_cell(0), money_cell(0),
            Paragraph(wrap_ar("رصيد افتتاحي (مُرحَّل)", FONT_BOLD, 9, desc_w),
                      _style("st_open", 9, bold=True)),
            "", "", "",
        ])
        style.append(("BACKGROUND", (0, len(data) - 1), (5, len(data) - 1), C_LIGHT))

    for entry in statement["rows"]:
        row_no += 1
        muted = entry["cancelled"]
        text_style = cell_grey if muted else cell

        ref = f"{_KIND_TEXT.get(entry['kind'], '')} {entry['ref'] or ''}".strip()

        data.append([
            balance_cell(entry["balance"], muted),
            money_cell(entry["credit"], _GREEN),
            money_cell(entry["debit"], _RED if not muted else _GREY),
            Paragraph(wrap_ar(entry["description"], FONT, 9, desc_w), text_style),
            Paragraph(wrap_ar(ref, FONT, 9, _COLS[4] - 14), text_style),
            Paragraph(escape(str(entry["date"] or "")), cell_c),
            Paragraph(str(row_no), cell_c),
        ])

        if row_no % 2 == 0:
            style.append((
                "BACKGROUND", (0, len(data) - 1), (5, len(data) - 1), C_ZEBRA
            ))

    # صف الإجماليات
    closing_text, closing_state = _signed(statement["closing"])
    total_style = _style("st_tot", 9.5, bold=True, align=2, color=colors.white)

    data.append([
        Paragraph(escape(fix_arabic(closing_text)), total_style),
        Paragraph(escape(format_money(statement["total_credit"], symbol=False)),
                  total_style),
        Paragraph(escape(format_money(statement["total_debit"], symbol=False)),
                  total_style),
        Paragraph(fix_arabic("الإجمالي"),
                  _style("st_tot_l", 10, bold=True, color=colors.white)),
        "", "", "",
    ])
    last = len(data) - 1
    style += [
        ("BACKGROUND", (0, last), (-1, last), C_NAVY),
        ("SPAN", (3, last), (6, last)),
    ]

    table = Table(data, colWidths=_COLS, repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _balance_banner(statement):
    """شريط الرصيد المستحق رقماً وكتابةً."""
    closing = statement["closing"]
    text, state = _signed(closing, with_state=False)
    color = _state_color(state)

    if state == "zero":
        headline = "الحساب مسدّد — لا يوجد رصيد مستحق"
        words = ""
    else:
        who = "على العميل" if state == "debit" else "للعميل"
        headline = f"الرصيد المستحق {who}"
        words = amount_to_words(abs(closing))

    label_w = 150
    amount_p = Paragraph(
        escape(_money_pdf(abs(closing))),
        _style("st_ban_amt", 20, bold=True, align=1, color=color),
    )
    label_p = Paragraph(
        escape(fix_arabic(headline)),
        _style("st_ban_lbl", 12, bold=True, align=1, color=colors.white),
    )

    rows = [[amount_p, label_p]]
    row_styles = [
        ("BACKGROUND", (0, 0), (0, 0), C_LIGHT),
        ("BACKGROUND", (1, 0), (1, 0), color),
        ("BOX", (0, 0), (-1, -1), 0.8, C_GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]

    if words:
        rows.append([
            Paragraph(
                wrap_ar(words, FONT_BOLD, 10.5, CONTENT_W - label_w - 28),
                _style("st_ban_w", 10.5, bold=True, leading=16, color=C_NAVY),
            ),
            Paragraph(fix_arabic("المبلغ كتابةً"), ST_LABEL),
        ])
        row_styles += [
            ("BACKGROUND", (1, 1), (1, 1), C_LIGHT),
            ("BOX", (0, 1), (-1, 1), 0.8, C_GRID),
            ("LEFTPADDING", (0, 1), (-1, 1), 12),
            ("RIGHTPADDING", (0, 1), (-1, 1), 12),
        ]

    table = Table(rows, colWidths=[CONTENT_W - label_w, label_w])
    table.setStyle(TableStyle(row_styles))
    return table


# =========================
# البناء
# =========================
def generate_statement_pdf(statement, file_path=None):
    """
    statement: قاموس من database.get_client_statement
    يرجع مسار الملف (statement_<client_id>.pdf افتراضياً).
    """
    client = statement["client"]
    file_path = file_path or f"statement_{client['id']}.pdf"

    today = _date.today()
    issued = today.isoformat()
    number = f"ST-{today:%Y%m%d}-{client['id']}"

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
        _draw_first_header(
            c, number, title="كشف حساب", subtitle="S T A T E M E N T"
        )

    def on_later(c, doc):
        _draw_mini_header(c, number, label="كشف حساب رقم")

    doc = BaseDocTemplate(
        file_path,
        pagesize=A4,
        title=f"Statement {client['name']}",
        author=str(COMPANY.get("name") or ""),
        subject="Account Statement",
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first,
                     autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])

    elements = [
        _info_section(statement, issued),
        Spacer(1, 14),
        _summary_strip(statement),
        Spacer(1, 14),
        _movements_table(statement),
        Spacer(1, 14),
        KeepTogether([_balance_banner(statement)]),
        Spacer(1, 24),
        KeepTogether([
            _signature_block(issued, "اعتماد العميل", "توقيع المحاسب")
        ]),
    ]

    closing_text, _state = _signed(statement["closing"])
    qr = _make_qr([
        f"Statement: {number}",
        f"Client: {client['name']}",
        f"Balance: {closing_text}",
        f"Date: {issued}",
    ])

    doc.build(elements, canvasmaker=_make_canvas_class(qr))
    return file_path
