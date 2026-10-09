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
    Image, Paragraph, Spacer
)

from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# تسجيل الخط
pdfmetrics.registerFont(TTFont('Arabic', 'assets/Cairo-Regular.ttf'))


def fix_arabic(text):
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def generate_pdf(invoice_id, invoice_number, items, client="غير محدد"):
    file_name = f"invoice_{invoice_id}.pdf"
    doc = SimpleDocTemplate(file_name)

    elements = []

    # ستايل عربي موحد
    arabic_style = ParagraphStyle(
        name='Arabic',
        fontName='Arabic',
        fontSize=12,
        alignment=2  # يمين
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
    elements.append(Paragraph(fix_arabic(f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}"), arabic_style))
    elements.append(Spacer(1, 15))


    # ===== Table =====
    data = [
        [
            Paragraph(fix_arabic("الصنف"), arabic_style),
            Paragraph(fix_arabic("الوصف"), arabic_style),
            Paragraph(fix_arabic("السعر"), arabic_style),
            Paragraph(fix_arabic("الكمية"), arabic_style),
            Paragraph(fix_arabic("الإجمالي"), arabic_style),
        ]
    ]

    total = 0


    for item in items:
        name, desc, qty, price, t = item

        data.append([
            Paragraph(fix_arabic(name), arabic_style),
            Paragraph(fix_arabic(desc), arabic_style),
            Paragraph(str(price), arabic_style),
            Paragraph(str(qty), arabic_style),
            Paragraph(str(t), arabic_style),
        ])

        total += t


    # الإجمالي
    data.append([
        "",
        "",
        "",
        Paragraph(fix_arabic("الإجمالي"), arabic_style),
        Paragraph(str(total), arabic_style),
    ])

    table = Table(data)

    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Arabic"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
    ]))

    elements.append(table)

    # QR Code
    # ======================
    qr_data = f"""
    Invoice: {invoice_number}
    Client: {client}
    Date: {datetime.now().strftime('%Y-%m-%d')}
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
def generate_temp_pdf(client_name, items, total):

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


