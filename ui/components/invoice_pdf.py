# ui/components/invoice_pdf.py
"""إنشاء ملف PDF لفاتورة محفوظة (مشترك بين الصفحات التي تعرض فواتير)."""

from database import get_invoice_info, get_invoice_items
from pdf_generator import generate_pdf


def build_invoice_pdf(invoice_id):
    """يولّد PDF للفاتورة ويرجع مساره. يرفع ValueError إن لم تكن موجودة."""
    info = get_invoice_info(invoice_id)

    if not info:
        raise ValueError("تعذّر العثور على الفاتورة")

    return generate_pdf(
        invoice_id,
        info["invoice_number"],
        get_invoice_items(invoice_id),
        info["client"],
        invoice_date=info["date"],
        subtotal=info["subtotal"],
        discount_percent=info["discount_percent"],
        discount_amount=info["discount_amount"],
        tax_percent=info["tax_percent"],
        tax_amount=info["tax_amount"],
        total=info["total"],
        notes=info["notes"],
        status=info["status"],
    )
