# pdf_generator.py

import arabic_reshaper
import os
import qrcode
import tempfile
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from datetime import datetime

from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet
)

from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Image, Paragraph, Spacer, KeepTogether
)

from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ui.components.invoice_utils import format_money, round_money

# تسجيل الخط
pdfmetrics.registerFont(TTFont('Arabic', 'assets/Cairo-Regular.ttf'))


def fix_arabic(text):
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def _format_qty(qty):
    try:
        value = float(qty)
    except (TypeError, ValueError):
        return str(qty or "")
    return str(int(value)) if value.is_integer() else f"{value:g}"


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
        notes=""
    ):
    file_name = f"invoice_{invoice_id}.pdf"
    doc = SimpleDocTemplate(file_name)

    elements = []
    invoice_date = invoice_date or datetime.now().strftime("%Y-%m-%d")
    items_total = round_money(sum(float(item[4]) for item in items))

    subtotal = round_money(subtotal or items_total)
    discount_percent = round_money(discount_percent)
    discount_amount = round_money(discount_amount)
    tax_percent = round_money(tax_percent)
    tax_amount = round_money(tax_amount)

    taxable_amount = round_money(subtotal - discount_amount)
    total = round_money(total or (taxable_amount + tax_amount))
    notes = notes or ""

    # ستايل عربي موحد
    arabic_style = ParagraphStyle(
        name='Arabic',
        fontName='Arabic',
        fontSize=12,
        alignment=2  # يمين
    )

    header_style = ParagraphStyle(
        name='ArabicHeader',
        fontName='Arabic',
        fontSize=11,
        alignment=2
    )

    cell_style = ParagraphStyle(
        name='ArabicCell',
        fontName='Arabic',
        fontSize=10,
        leading=14,
        alignment=2
    )

    title_style = ParagraphStyle(
        name='TitleArabic',
        fontName='Arabic',
        fontSize=18,
        alignment=2
    )


    # ===== شعار =====
    try:
        logo = Image("assets/logo.png", width=120, height=60)
        elements.append(logo)
    except:
        pass


    # ===== عنوان =====
    elements.append(Paragraph(fix_arabic("فاتورة"), title_style))
    elements.append(Spacer(1, 10))


    # ===== معلومات =====
    elements.append(Paragraph(fix_arabic(f"رقم الفاتورة: {invoice_number}"), arabic_style))
    elements.append(Paragraph(fix_arabic(f"العميل: {client}"), arabic_style))
    elements.append(Paragraph(fix_arabic(f"التاريخ: {invoice_date}"), arabic_style))
    elements.append(Spacer(1, 15))


    # ===== جدول الأصناف =====
    # الترتيب من اليسار لليمين معكوس ليظهر "الصنف" أقصى اليمين (اتجاه عربي)
    header = [
        Paragraph(fix_arabic("الإجمالي"), header_style),
        Paragraph(fix_arabic("الكمية"), header_style),
        Paragraph(fix_arabic("السعر"), header_style),
        Paragraph(fix_arabic("الوصف"), header_style),
        Paragraph(fix_arabic("الصنف"), header_style),
    ]
    data = [header]

    for item in items:
        name, desc, qty, price, item_total = item

        data.append([
            Paragraph(format_money(item_total, symbol=False), cell_style),
            Paragraph(_format_qty(qty), cell_style),
            Paragraph(format_money(price, symbol=False), cell_style),
            Paragraph(fix_arabic(desc or ""), cell_style),
            Paragraph(fix_arabic(name or ""), cell_style),
        ])

    # عرض الصفحة المتاح (A4 ناقص الهوامش الافتراضية)
    col_widths = [70, 55, 60, 140, 126]

    table = Table(data, colWidths=col_widths, repeatRows=1)

    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Arabic"),
        ("GRID", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # ✅ هذا هو الإصلاح: إضافة جدول الأصناف إلى محتوى الفاتورة
    elements.append(table)

    # ملخص الفاتورة
    summary_data = [
        [
            Paragraph(fix_arabic("المجموع الفرعي"), arabic_style),
            Paragraph(format_money(subtotal), arabic_style),
        ],
        [
            Paragraph(
                fix_arabic(f"الخصم ({discount_percent:g}%)"),
                arabic_style
            ),
            Paragraph(format_money(discount_amount), arabic_style),
        ],
        [
            Paragraph(
                fix_arabic(f"الضريبة ({tax_percent:g}%)"),
                arabic_style
            ),
            Paragraph(format_money(tax_amount), arabic_style),
        ],
        [
            Paragraph(fix_arabic("الإجمالي النهائي"), arabic_style),
            Paragraph(format_money(total), arabic_style),
        ],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[260, 180]
    )

    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Arabic"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
    ]))

    elements.append(Spacer(1, 12))
    elements.append(KeepTogether([summary_table]))

    # الملاحظات
    if notes.strip():
        elements.append(Spacer(1, 12))

        elements.append(
            Paragraph(
                fix_arabic("📝 الملاحظات"),
                title_style
            )
        )

        elements.append(
            Paragraph(
                fix_arabic(notes),
                arabic_style
            )
        )

    # QR Code
    # ======================
    qr_data = f"""
    Invoice: {invoice_number}
    Client: {client}
    Date: {invoice_date}
    Subtotal: {subtotal}
    Discount: {discount_amount}
    Tax: {tax_amount}
    Total: {total}
    """

    qr = qrcode.make(qr_data)

    temp_qr = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".png"
    )

    qr_path = temp_qr.name

    qr.save(qr_path)

    temp_qr.close()

    qr_image = Image(
        qr_path,
        width=100,
        height=100
    )

    elements.append(Spacer(1, 20))

    elements.append(qr_image)

    doc.build(elements)

    if os.path.exists(qr_path):
        os.remove(qr_path)

    return file_name

# ======================
# إنشاء PDF مؤقت للمعاينة والطباعة
# ======================
def generate_temp_pdf(client_name, items, summary=None, notes=""):
    summary = summary or {}
    notes = notes or summary.get("notes", "")

    # إنشاء ملف مؤقت
    temp_dir = tempfile.gettempdir()

    pdf_path = os.path.join(
        temp_dir,
        "invoice_preview.pdf"
    )

    # إنشاء ملف PDF
    doc = SimpleDocTemplate(pdf_path)

    elements = []

    styles = getSampleStyleSheet()

    title = Paragraph(
        "Invoice Preview",
        styles['Title']
    )

    elements.append(title)

    elements.append(Spacer(1, 20))

    client = Paragraph(
        f"Client: {client_name}",
        styles['Heading2']
    )

    elements.append(client)

    elements.append(Spacer(1, 10))
    subtotal = round_money(summary.get("subtotal", 0))
    discount_percent = round_money(summary.get("discount_percent", 0))
    discount_amount = round_money(summary.get("discount_amount", 0))
    tax_percent = round_money(summary.get("tax_percent", 0))
    tax_amount = round_money(summary.get("tax_amount", 0))
    total = round_money(summary.get("total", 0))

    summary_text = Paragraph(
        f"""
        Subtotal: {format_money(subtotal)}<br/>
        Discount ({discount_percent:g}%): {format_money(discount_amount)}<br/>
        Tax ({tax_percent:g}%): {format_money(tax_amount)}<br/>
        <b>Final Total: {format_money(total)}</b>
        """,
        styles["Normal"]
    )

    elements.append(summary_text)

    if notes.strip():
        elements.append(Spacer(1, 10))

        elements.append(
            Paragraph(
                f"Notes: {notes}",
                styles["Normal"]
            )
        )

    # بيانات الجدول
    data = [[
        "Item",
        "Description",
        "Qty",
        "Price",
        "Total"
    ]]
    
    for item in items:

        data.append([
            item["name"],
            item.get("desc", ""),
            str(item["qty"]),
            str(item["price"]),
            str(item["total"])
        ])

    data.append([
        "",
        "",
        "",
        "Final Total",
        str(total)
    ])

    table = Table(data)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),

        ('GRID', (0, 0), (-1, -1), 1, colors.black),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))

    elements.append(table)

    doc.build(elements)

    return pdf_path


