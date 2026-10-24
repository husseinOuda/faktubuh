# ui/reports_page.py

import customtkinter as ctk
import pandas as pd
from tkinter import messagebox
from database import get_total_profit, get_profit_by_date, get_invoices, status_label
from datetime import date


# ======================
# تصدير Excel
# ======================
def export_invoices_excel(invoices=None):

    try:

        if invoices is None:
            invoices = get_invoices()

        rows = [
            {
                "ID": invoice["id"],
                "رقم الفاتورة": invoice["invoice_number"],
                "العميل": invoice["client"],
                "التاريخ": invoice["date"],
                "المجموع الفرعي": invoice["subtotal"],
                "نسبة الخصم": invoice["discount_percent"],
                "قيمة الخصم": invoice["discount_amount"],
                "نسبة الضريبة": invoice["tax_percent"],
                "قيمة الضريبة": invoice["tax_amount"],
                "الإجمالي النهائي": invoice["total"],
                "الملاحظات": invoice["notes"],
                "الحالة": status_label(invoice.get("status")),
                "مؤرشفة": "نعم" if invoice.get("archived") else "لا",
            }
            for invoice in invoices
        ]

        df = pd.DataFrame(
            rows,
            columns=[
                "ID",
                "رقم الفاتورة",
                "العميل",
                "التاريخ",
                "المجموع الفرعي",
                "نسبة الخصم",
                "قيمة الخصم",
                "نسبة الضريبة",
                "قيمة الضريبة",
                "الإجمالي النهائي",
                "الملاحظات",
                "الحالة",
                "مؤرشفة",
            ]
        )

        df.to_excel(
            f"selected_invoices_{date.today()}.xlsx",
            index=False
        )

        messagebox.showinfo(
            "نجاح",
            "تم تصدير ملف Excel بنجاح"
        )

    except Exception as e:

        messagebox.showerror(
            "خطأ",
            str(e)
        )

# ======================
# واجهة التقارير
# ======================
class ReportsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app

        self.build_ui()

        # حاوية البطاقات
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=20)

        # البطاقة الأولى
        card1 = ctk.CTkFrame(
            cards_frame,
            fg_color="white",
            corner_radius=15
        )
        card1.pack(side="left", padx=10, fill="both", expand=True)

        ctk.CTkLabel(
            card1,
            text="إجمالي الفواتير",
            font=("Cairo", 14)
        ).pack(pady=(15,5))

        ctk.CTkLabel(
            card1,
            text=str(len(get_invoices())),
            font=("Cairo", 24, "bold")
        ).pack(pady=(0,15))

    def build_ui(self):
        ctk.CTkLabel(self, text="📊 التقارير", font=("Arial", 20)).pack(pady=20)

        ctk.CTkButton(self, text="إجمالي الأرباح", command=self.show_total).pack(pady=10)

        self.start = ctk.CTkEntry(self, placeholder_text="من تاريخ YYYY-MM-DD")
        self.start.pack(pady=5)

        self.end = ctk.CTkEntry(self, placeholder_text="إلى تاريخ YYYY-MM-DD")
        self.end.pack(pady=5)

        ctk.CTkButton(self, text="فلترة", command=self.filter).pack(pady=10)

    def show_total(self):
        try:
            total = get_total_profit()
            messagebox.showinfo("الأرباح", f"{total} ₪")
        except Exception as e:
            messagebox.showerror("خطأ", str(e))



    def filter(self):
        start = self.start.get()
        end = self.end.get()

        if not start or not end:
            messagebox.showerror("خطأ", "أدخل التاريخ")
            return

        try:
            total = get_profit_by_date(start, end)
            messagebox.showinfo("النتيجة", f"{total} ₪")
        except Exception as e:
            messagebox.showerror("خطأ", str(e))


