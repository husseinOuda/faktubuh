# pdf_generator.py  (v0.1.5)
"""
مولّد فواتير PDF احترافي (A4):
  - ترويسة بالهوية البصرية (شعار + بيانات الجهة + عنوان الفاتورة)
  - بيانات العميل والفاتورة في صناديق منظمة
  - جدول أصناف يشبه Excel: رأس ملوّن، صفوف متناوبة، خطوط، محاذاة أرقام
  - ملخص مالي + ملاحظات
  - ختم وتوقيع (صور اختيارية stamp.png / signature.png أو رسم تلقائي)
  - تذييل بترقيم الصفحات ورمز QR
"""

import io
import os
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

import arabic_reshaper
import qrcode
from bidi.algorithm import get_display
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from theme import (
    BRAND_BLUE,
    BRAND_LIGHT,
    BRAND_NAVY,
    COMPANY,
    STATUS_COLORS,
    TABLE_GRID,
    TABLE_ZEBRA,
)
from ui.components.invoice_utils import format_money, round_money

# =========================
# المسارات والخطوط
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

FONT = "Arabic"
FONT_BOLD = "ArabicBold"

pdfmetrics.registerFont(
    TTFont(FONT, os.path.join(ASSETS_DIR, "Cairo-Regular.ttf"))
)

_bold_path = os.path.join(ASSETS_DIR, "static", "Cairo-Bold.ttf")
if os.path.exists(_bold_path):
    pdfmetrics.registerFont(TTFont(FONT_BOLD, _bold_path))
else:
    # لا يوجد خط عريض → نستخدم العادي حتى لا يتعطل التصدير
    pdfmetrics.registerFont(
        TTFont(FONT_BOLD, os.path.join(ASSETS_DIR, "Cairo-Regular.ttf"))
    )

# =========================
# ثوابت التصميم
# =========================
PAGE_W, PAGE_H = A4                 # 595 x 842 pt
MARGIN_X = 36
CONTENT_W = PAGE_W - 2 * MARGIN_X   # 523 pt

HEADER_H = 108                      # ارتفاع الترويسة في الصفحة الأولى
MINI_HEADER_H = 26                  # ترويسة مصغّرة في الصفحات التالية
FOOTER_H = 66                       # المساحة المحجوزة للتذييل

C_NAVY = colors.HexColor(BRAND_NAVY)
C_BLUE = colors.HexColor(BRAND_BLUE)
C_LIGHT = colors.HexColor(BRAND_LIGHT)
C_GRID = colors.HexColor(TABLE_GRID)
C_ZEBRA = colors.HexColor(TABLE_ZEBRA)
C_MUTED = colors.HexColor("#64748b")
C_TEXT = colors.HexColor("#111827")

# خط Cairo لا يحتوي رمز ₪ لذلك تُكتب العملة كلمة في الـ PDF
CURRENCY_WORD = "شيكل"

_STATUS_LABELS = {
    "paid": "مدفوعة",
    "unpaid": "غير مدفوعة",
    "cancelled": "ملغاة",
}


# =========================
# أدوات النص العربي
# =========================
def fix_arabic(text):
    """تشكيل الحروف العربية + ترتيب الاتجاه (RTL) لسطر واحد."""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def wrap_ar(text, font, size, max_width):
    """
    يقسّم النص المنطقي إلى أسطر حسب العرض ثم يطبّق RTL لكل سطر على حدة،
    فتظهر الأسطر الطويلة بالترتيب الصحيح (التفاف صحيح للعربية).
    يرجع نصاً جاهزاً لـ Paragraph (مع <br/>).
    """
    text = str(text or "").strip()
    if not text:
        return ""

    result_lines = []

    for raw_line in text.splitlines() or [""]:
        words = raw_line.split()
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            width = pdfmetrics.stringWidth(
                arabic_reshaper.reshape(candidate), font, size
            )

            if width <= max_width or not current:
                current = candidate
            else:
                result_lines.append(current)
                current = word

        result_lines.append(current)

    return "<br/>".join(escape(fix_arabic(line)) for line in result_lines)


def _format_qty(qty):
    try:
        value = float(qty)
    except (TypeError, ValueError):
        return str(qty or "")
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _money_pdf(value, with_currency=True):
    """مبلغ للـ PDF: أرقام بخانتين عشريتين + كلمة العملة."""
    text = format_money(value, symbol=False)
    if not with_currency:
        return text
    return escape(fix_arabic(f"{text} {CURRENCY_WORD}"))


# =========================
# أنماط الفقرات
# =========================
def _style(name, size=10, bold=False, align=2, color=C_TEXT, leading=None):
    return ParagraphStyle(
        name=name,
        fontName=FONT_BOLD if bold else FONT,
        fontSize=size,
        leading=leading or size * 1.55,
        alignment=align,          # 0 يسار، 1 وسط، 2 يمين
        textColor=color,
    )


ST_CELL = _style("cell", 10)
ST_CELL_C = _style("cell_c", 10, align=1)
ST_CELL_NUM = _style("cell_num", 10, align=2)
ST_HEAD = _style("head", 10.5, bold=True, align=1, color=colors.white)
ST_LABEL = _style("label", 9.5, bold=True, color=C_NAVY)
ST_BOX_TITLE = _style("box_title", 9.5, bold=True, color=colors.white, align=2)
ST_SUM_LABEL = _style("sum_label", 10.5)
ST_SUM_VALUE = _style("sum_value", 10.5, align=0)
ST_TOTAL_LABEL = _style("tot_label", 12, bold=True, color=colors.white)
ST_TOTAL_VALUE = _style("tot_value", 12, bold=True, color=colors.white, align=0)
ST_NOTES = _style("notes", 10, leading=15)


# =========================
# عناصر مرسومة (ختم + توقيع)
# =========================
class SignatureBox(Flowable):
    """خانة توقيع: صورة اختيارية فوق خط، والعنوان تحته."""

    def __init__(self, label, image_path=None, sub_label="",
                 width=150, height=84):
        super().__init__()
        self.label = label
        self.sub_label = sub_label
        self.image_path = image_path
        self.width = width
        self.height = height

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        line_y = 30
        pad = 14

        if self.image_path and os.path.exists(self.image_path):
            try:
                c.drawImage(
                    self.image_path,
                    pad, line_y + 4,
                    width=self.width - 2 * pad,
                    height=self.height - line_y - 6,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            except Exception:
                pass

        c.setStrokeColor(C_MUTED)
        c.setLineWidth(0.8)
        c.line(pad, line_y, self.width - pad, line_y)

        c.setFillColor(C_NAVY)
        c.setFont(FONT_BOLD, 10)
        c.drawCentredString(self.width / 2, line_y - 14, fix_arabic(self.label))

        if self.sub_label:
            c.setFillColor(C_MUTED)
            c.setFont(FONT, 8.5)
            c.drawCentredString(
                self.width / 2, line_y - 26, fix_arabic(self.sub_label)
            )


class StampBox(Flowable):
    """
    ختم الجهة: يستخدم assets/stamp.png إن وُجد، وإلا يُرسم ختم دائري
    بالهوية البصرية (اسم الجهة + كلمة «معتمد» + التاريخ).
    """

    def __init__(self, company_name, date_text, image_path=None,
                 width=150, height=84):
        super().__init__()
        self.company_name = company_name
        self.date_text = date_text
        self.image_path = image_path
        self.width = width
        self.height = height

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        cx, cy = self.width / 2, self.height / 2 + 4

        if self.image_path and os.path.exists(self.image_path):
            try:
                size = self.height - 6
                c.drawImage(
                    self.image_path,
                    cx - size / 2, cy - size / 2,
                    width=size, height=size,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                return
            except Exception:
                pass  # نكمل بالختم المرسوم

        stamp_color = colors.HexColor("#1d4ed8")
        radius = min(self.width, self.height) / 2 - 4

        c.saveState()
        c.translate(cx, cy)
        c.rotate(-10)
        c.setStrokeColor(stamp_color)
        c.setFillColor(stamp_color)
        c.setStrokeAlpha(0.75)
        c.setFillAlpha(0.8)

        c.setLineWidth(2.2)
        c.circle(0, 0, radius, stroke=1, fill=0)
        c.setLineWidth(0.8)
        c.circle(0, 0, radius - 5, stroke=1, fill=0)

        # اسم الجهة (إنجليزي أو عربي) في الأعلى
        name = str(self.company_name or "").strip()
        is_ascii = name.isascii()
        text = name.upper() if is_ascii else fix_arabic(name)
        font = "Helvetica-Bold" if is_ascii else FONT_BOLD
        size = 9
        while size > 6 and pdfmetrics.stringWidth(text, font, size) > radius * 1.5:
            size -= 0.5
        c.setFont(font, size)
        c.drawCentredString(0, radius * 0.38, text)

        # كلمة معتمد
        c.setFont(FONT_BOLD, 15)
        c.drawCentredString(0, -4, fix_arabic("معتمد"))

        # التاريخ
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(0, -radius * 0.45, str(self.date_text or ""))

        c.restoreState()


# =========================
# ترويسة وتذييل الصفحات
# =========================
_LOGO_CACHE = {}


def _crop_logo():
    """يقصّ هوامش الشعار الشفافة/البيضاء ويرجع (صورة جاهزة للرسم، نسبة العرض/الارتفاع)."""
    if "logo" in _LOGO_CACHE:
        return _LOGO_CACHE["logo"]

    path = os.path.join(ASSETS_DIR, "logo.png")
    result = (None, 1.0)

    if os.path.exists(path):
        try:
            img = PILImage.open(path).convert("RGBA")

            # المحتوى = بكسلات غير شفافة وليست بيضاء تقريباً
            opaque = img.split()[-1].point(lambda a: 255 if a > 10 else 0)
            not_white = img.convert("L").point(lambda v: 255 if v < 245 else 0)
            content = PILImage.composite(
                not_white, PILImage.new("L", img.size, 0), opaque
            )
            bbox = content.getbbox()

            if bbox:
                pad = 12
                img = img.crop((
                    max(bbox[0] - pad, 0),
                    max(bbox[1] - pad, 0),
                    min(bbox[2] + pad, img.width),
                    min(bbox[3] + pad, img.height),
                ))

            result = (ImageReader(img), img.width / img.height)
        except Exception:
            result = (None, 1.0)

    _LOGO_CACHE["logo"] = result
    return result


def _company_lines():
    lines = []
    if COMPANY.get("tagline"):
        lines.append(COMPANY["tagline"])

    contact = []
    if COMPANY.get("phone"):
        contact.append(f"هاتف: {COMPANY['phone']}")
    if COMPANY.get("email"):
        contact.append(COMPANY["email"])
    if contact:
        lines.append("  |  ".join(contact))

    if COMPANY.get("address"):
        lines.append(COMPANY["address"])
    if COMPANY.get("tax_no"):
        lines.append(f"الرقم الضريبي: {COMPANY['tax_no']}")
    return lines


def _draw_name(c, name, x, y, size, right=True):
    """يرسم اسماً بالخط المناسب (لاتيني → Helvetica، عربي → Cairo)."""
    if not name:
        return
    is_ascii = name.isascii()
    c.setFont("Helvetica-Bold" if is_ascii else FONT_BOLD, size)
    text = name if is_ascii else fix_arabic(name)
    if right:
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_first_header(c, invoice_number):
    top = PAGE_H

    # الشريط الرئيسي + خط لوني رفيع أسفله
    c.setFillColor(C_NAVY)
    c.rect(0, top - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
    c.setFillColor(C_BLUE)
    c.rect(0, top - HEADER_H - 4, PAGE_W, 4, stroke=0, fill=1)

    # صندوق أبيض للشعار (يمين)
    box = 80
    box_x = PAGE_W - MARGIN_X - box
    box_y = top - HEADER_H + (HEADER_H - box) / 2
    c.setFillColor(colors.white)
    c.roundRect(box_x, box_y, box, box, 10, stroke=0, fill=1)

    logo, ratio = _crop_logo()
    if logo is not None:
        inner = box - 10
        w = inner if ratio >= 1 else inner * ratio
        h = inner / ratio if ratio >= 1 else inner
        c.drawImage(
            logo,
            box_x + (box - w) / 2, box_y + (box - h) / 2,
            width=w, height=h, mask="auto",
        )

    # اسم الجهة وبياناتها (يمين الشعار)
    text_right = box_x - 14
    y = top - 40

    c.setFillColor(colors.white)
    _draw_name(c, str(COMPANY.get("name") or "").strip(), text_right, y, 19)

    c.setFillColor(colors.HexColor("#bfd3f7"))
    c.setFont(FONT, 9.5)
    y -= 20
    for line in _company_lines()[:3]:
        c.drawRightString(text_right, y, fix_arabic(line))
        y -= 14

    # عنوان الفاتورة (يسار)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 30)
    c.drawString(MARGIN_X, top - 52, fix_arabic("فاتورة"))

    c.setFillColor(colors.HexColor("#8fb1ee"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN_X + 1, top - 70, "I N V O I C E")

    # رقم الفاتورة داخل شارة
    num = str(invoice_number or "")
    is_ascii = num.isascii()
    font = "Helvetica-Bold" if is_ascii else FONT_BOLD
    shown = num if is_ascii else fix_arabic(num)
    tw = pdfmetrics.stringWidth(shown, font, 10.5)
    c.setFillColor(C_BLUE)
    c.roundRect(MARGIN_X, top - 98, tw + 22, 20, 10, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(font, 10.5)
    c.drawString(MARGIN_X + 11, top - 91.5, shown)


def _draw_mini_header(c, invoice_number):
    top = PAGE_H
    c.setFillColor(C_NAVY)
    c.rect(0, top - MINI_HEADER_H, PAGE_W, MINI_HEADER_H, stroke=0, fill=1)
    c.setFillColor(C_BLUE)
    c.rect(0, top - MINI_HEADER_H - 2, PAGE_W, 2, stroke=0, fill=1)

    c.setFillColor(colors.white)
    _draw_name(
        c, str(COMPANY.get("name") or "").strip(),
        PAGE_W - MARGIN_X, top - 17, 10.5,
    )

    c.setFont(FONT, 10)
    c.drawString(
        MARGIN_X, top - 17,
        f"{fix_arabic('فاتورة رقم')}  {invoice_number}",
    )


def _draw_cancelled_watermark(c):
    c.saveState()
    c.setFillColor(colors.HexColor("#b91c1c"))
    c.setFillAlpha(0.10)
    c.setFont(FONT_BOLD, 120)
    c.translate(PAGE_W / 2, PAGE_H / 2 - 30)
    c.rotate(35)
    c.drawCentredString(0, 0, fix_arabic("ملغاة"))
    c.restoreState()


def _make_canvas_class(qr_reader):
    """
    كانفاس يؤجّل رسم التذييل إلى نهاية البناء ليعرف العدد الكلي للصفحات
    (صفحة 1 من 3)، ويرسم رمز QR وملاحظة الشكر وبيانات التواصل.
    """

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_pages = []

        def showPage(self):
            self._saved_pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_pages)
            for state in self._saved_pages:
                self.__dict__.update(state)
                self._draw_footer(total)
                super().showPage()
            super().save()

        def _draw_footer(self, total_pages):
            c = self
            y_line = FOOTER_H - 8

            c.setStrokeColor(C_GRID)
            c.setLineWidth(1)
            c.line(MARGIN_X, y_line, PAGE_W - MARGIN_X, y_line)

            # شريط لوني سفلي
            c.setFillColor(C_NAVY)
            c.rect(0, 0, PAGE_W, 8, stroke=0, fill=1)

            # QR (يسار)
            if qr_reader is not None:
                c.drawImage(
                    qr_reader, MARGIN_X, 14, width=44, height=44, mask="auto"
                )

            # ملاحظة الشكر + بيانات التواصل (وسط)
            note = COMPANY.get("footer_note") or ""
            c.setFillColor(C_NAVY)
            c.setFont(FONT_BOLD, 11)
            c.drawCentredString(PAGE_W / 2, 38, fix_arabic(note))

            contact = [x for x in (
                COMPANY.get("phone"), COMPANY.get("email"),
                COMPANY.get("address"),
            ) if x]
            if contact:
                c.setFillColor(C_MUTED)
                c.setFont(FONT, 8.5)
                c.drawCentredString(
                    PAGE_W / 2, 24, fix_arabic("  |  ".join(contact))
                )

            # ترقيم الصفحات (يمين)
            c.setFillColor(C_MUTED)
            c.setFont(FONT, 9)
            c.drawRightString(
                PAGE_W - MARGIN_X, 30,
                fix_arabic(f"صفحة {self._pageNumber} من {total_pages}"),
            )

    return NumberedCanvas


# =========================
# بناء أجزاء الفاتورة
# =========================
def _plain_table_style(extra=None):
    base = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    return TableStyle(base + (extra or []))


def _info_section(invoice_number, client, invoice_date, status):
    """صندوقان: بيانات العميل (يمين) وبيانات الفاتورة (يسار)."""
    box_w = (CONTENT_W - 14) / 2

    # ---- بيانات العميل ----
    client_text = wrap_ar(client, FONT_BOLD, 13, box_w - 28)
    client_box = Table(
        [
            [Paragraph(fix_arabic("بيانات العميل"), ST_BOX_TITLE)],
            [Paragraph(client_text, _style("client_name", 13, bold=True))],
        ],
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
        ("TOPPADDING", (0, 1), (-1, 1), 12),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # ---- بيانات الفاتورة ----
    status_color = colors.HexColor(STATUS_COLORS.get(status, BRAND_NAVY))
    status_text = _STATUS_LABELS.get(status, status or "")

    rows = [
        [
            Paragraph(escape(fix_arabic(str(invoice_number))),
                      _style("v_num", 10.5, bold=True, align=0)),
            Paragraph(fix_arabic("رقم الفاتورة"), ST_LABEL),
        ],
        [
            Paragraph(escape(str(invoice_date)),
                      _style("v_date", 10.5, align=0)),
            Paragraph(fix_arabic("تاريخ الإصدار"), ST_LABEL),
        ],
    ]
    if status:
        rows.append([
            Paragraph(
                escape(fix_arabic(status_text)),
                _style("v_status", 10.5, bold=True, align=0, color=status_color),
            ),
            Paragraph(fix_arabic("الحالة"), ST_LABEL),
        ])

    inv_inner = Table(rows, colWidths=[box_w - 100, 100])
    inv_inner.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), C_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, C_GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    inv_box = Table(
        [
            [Paragraph(fix_arabic("بيانات الفاتورة"), ST_BOX_TITLE)],
            [inv_inner],
        ],
        colWidths=[box_w],
    )
    inv_box.setStyle(TableStyle([
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

    # ترتيب اليسار → اليمين: الفاتورة | فراغ | العميل
    outer = Table([[inv_box, "", client_box]], colWidths=[box_w, 14, box_w])
    outer.setStyle(_plain_table_style())
    return outer


def _items_table(items):
    """جدول الأصناف بنمط Excel (من اليمين: # ثم الصنف ... ثم الإجمالي)."""
    # عروض الأعمدة من اليسار لليمين
    widths = [80, 70, 62, 148, 128, 35]
    assert abs(sum(widths) - CONTENT_W) < 1

    name_w, desc_w = widths[4] - 18, widths[3] - 18

    header = [
        Paragraph(fix_arabic("الإجمالي"), ST_HEAD),
        Paragraph(fix_arabic("السعر"), ST_HEAD),
        Paragraph(fix_arabic("الكمية"), ST_HEAD),
        Paragraph(fix_arabic("الوصف"), ST_HEAD),
        Paragraph(fix_arabic("الصنف"), ST_HEAD),
        Paragraph("#", ST_HEAD),
    ]
    data = [header]

    for number, item in enumerate(items, start=1):
        name, desc, qty, price, item_total = item[:5]

        data.append([
            Paragraph(_money_pdf(item_total, False), ST_CELL_NUM),
            Paragraph(_money_pdf(price, False), ST_CELL_NUM),
            Paragraph(_format_qty(qty), ST_CELL_C),
            Paragraph(wrap_ar(desc, FONT, 10, desc_w) or "—", ST_CELL),
            Paragraph(wrap_ar(name, FONT, 10, name_w), ST_CELL),
            Paragraph(str(number), ST_CELL_C),
        ])

    table = Table(data, colWidths=widths, repeatRows=1)

    style = [
        # الرأس
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 2, C_BLUE),
        # الشبكة (خطوط هادئة تشبه Excel)
        ("GRID", (0, 0), (-1, -1), 0.5, C_GRID),
        ("BOX", (0, 0), (-1, -1), 1, C_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        # عمود الترقيم بخلفية خفيفة
        ("BACKGROUND", (5, 1), (5, -1), C_LIGHT),
    ]

    # صفوف متناوبة (الصف الثاني، الرابع ... من البيانات)
    for row in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, row), (4, row), C_ZEBRA))

    table.setStyle(TableStyle(style))
    return table


def _summary_and_notes(subtotal, discount_percent, discount_amount,
                       tax_percent, tax_amount, total, notes):
    totals_w = 262
    gap = 14
    notes_w = CONTENT_W - totals_w - gap

    rows = [
        [
            Paragraph(_money_pdf(subtotal), ST_SUM_VALUE),
            Paragraph(fix_arabic("المجموع الفرعي"), ST_SUM_LABEL),
        ],
        [
            Paragraph(_money_pdf(discount_amount), ST_SUM_VALUE),
            Paragraph(
                escape(fix_arabic(f"الخصم ({discount_percent:g}%)")),
                ST_SUM_LABEL,
            ),
        ],
        [
            Paragraph(_money_pdf(tax_amount), ST_SUM_VALUE),
            Paragraph(
                escape(fix_arabic(f"الضريبة ({tax_percent:g}%)")),
                ST_SUM_LABEL,
            ),
        ],
        [
            Paragraph(_money_pdf(total), ST_TOTAL_VALUE),
            Paragraph(fix_arabic("الإجمالي النهائي"), ST_TOTAL_LABEL),
        ],
    ]

    totals = Table(rows, colWidths=[totals_w - 136, 136])
    totals.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, C_NAVY),
        ("LINEBELOW", (0, 0), (-1, -3), 0.5, C_GRID),
        ("BACKGROUND", (0, 0), (-1, -2), colors.white),
        ("BACKGROUND", (1, 0), (1, -2), C_LIGHT),
        ("BACKGROUND", (0, -1), (-1, -1), C_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -2), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 6),
        ("TOPPADDING", (0, -1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
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


def _signature_block(invoice_date):
    """يسار: المستلم | وسط: الختم | يمين: توقيع المُصدِر."""
    cell_w = CONTENT_W / 3

    signature_img = os.path.join(ASSETS_DIR, "signature.png")
    stamp_img = os.path.join(ASSETS_DIR, "stamp.png")

    receiver = SignatureBox("توقيع المستلم", width=cell_w)
    stamp = StampBox(
        COMPANY.get("name"), invoice_date, stamp_img, width=cell_w
    )
    issuer = SignatureBox(
        "توقيع المُصدِر", signature_img,
        sub_label=COMPANY.get("signatory", ""),
        width=cell_w,
    )

    block = Table([[receiver, stamp, issuer]], colWidths=[cell_w] * 3)
    block.setStyle(_plain_table_style([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return block


def _make_qr(invoice_number, client, invoice_date, subtotal,
             discount_amount, tax_amount, total):
    payload = (
        f"Invoice: {invoice_number}\n"
        f"Client: {client}\n"
        f"Date: {invoice_date}\n"
        f"Subtotal: {subtotal}\n"
        f"Discount: {discount_amount}\n"
        f"Tax: {tax_amount}\n"
        f"Total: {total}"
    )
    image = qrcode.make(payload)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


# =========================
# البناء الأساسي
# =========================
def _build_invoice_pdf(
    file_path,
    invoice_number,
    items,
    client,
    invoice_date,
    subtotal,
    discount_percent,
    discount_amount,
    tax_percent,
    tax_amount,
    total,
    notes,
    status,
):
    invoice_date = invoice_date or datetime.now().strftime("%Y-%m-%d")
    client = client or "غير محدد"

    items_total = round_money(sum(float(item[4]) for item in items))
    subtotal = round_money(subtotal or items_total)
    discount_percent = round_money(discount_percent)
    discount_amount = round_money(discount_amount)
    tax_percent = round_money(tax_percent)
    tax_amount = round_money(tax_amount)

    taxable_amount = round_money(subtotal - discount_amount)
    total = round_money(total or (taxable_amount + tax_amount))

    # ---- قوالب الصفحات ----
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
        if status == "cancelled":
            _draw_cancelled_watermark(c)
        _draw_first_header(c, invoice_number)

    def on_later(c, doc):
        if status == "cancelled":
            _draw_cancelled_watermark(c)
        _draw_mini_header(c, invoice_number)

    doc = BaseDocTemplate(
        file_path,
        pagesize=A4,
        title=f"Invoice {invoice_number}",
        author=str(COMPANY.get("name") or ""),
        subject="Invoice",
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first,
                     autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])

    # ---- المحتوى ----
    elements = [
        _info_section(invoice_number, client, invoice_date, status),
        Spacer(1, 16),
        _items_table(items),
        Spacer(1, 16),
        KeepTogether([
            _summary_and_notes(
                subtotal, discount_percent, discount_amount,
                tax_percent, tax_amount, total, notes,
            ),
        ]),
        Spacer(1, 22),
        KeepTogether([_signature_block(invoice_date)]),
    ]

    qr = _make_qr(
        invoice_number, client, invoice_date,
        subtotal, discount_amount, tax_amount, total,
    )

    doc.build(elements, canvasmaker=_make_canvas_class(qr))
    return file_path


# =========================
# الواجهات العامة (نفس التواقيع القديمة)
# =========================
def generate_pdf(
        invoice_id,
        invoice_number,
        items,
        client="غير محدد",
        invoice_date=None,
        subtotal=0,
        discount_percent=0,
        discount_amount=0,
        tax_percent=0,
        tax_amount=0,
        total=0,
        notes="",
        status=None
    ):
    """فاتورة محفوظة → invoice_<id>.pdf (items: صفوف (name, desc, qty, price, total))."""
    file_name = f"invoice_{invoice_id}.pdf"

    return _build_invoice_pdf(
        file_name,
        invoice_number,
        items,
        client,
        invoice_date,
        subtotal,
        discount_percent,
        discount_amount,
        tax_percent,
        tax_amount,
        total,
        notes or "",
        status,
    )


def generate_temp_pdf(client_name, items, summary=None, notes=""):
    """
    معاينة/طباعة فاتورة غير محفوظة بنفس التصميم النهائي.
    items: قواميس {name, desc, qty, price, total} كما في صفحة الإنشاء.
    """
    summary = summary or {}
    notes = notes or summary.get("notes", "")

    pdf_path = os.path.join(tempfile.gettempdir(), "invoice_preview.pdf")

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

    return _build_invoice_pdf(
        pdf_path,
        "مسودة",
        rows,
        client_name,
        datetime.now().strftime("%Y-%m-%d"),
        summary.get("subtotal", 0),
        summary.get("discount_percent", 0),
        summary.get("discount_amount", 0),
        summary.get("tax_percent", 0),
        summary.get("tax_amount", 0),
        summary.get("total", 0),
        notes,
        None,
    )
