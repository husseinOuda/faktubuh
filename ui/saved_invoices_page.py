# ui/saved_invoices_page.py

import os
import customtkinter as ctk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta

from pdf_generator import (
    generate_pdf
)

from database import (
    get_invoices as db_get_invoices,
    delete_invoice as db_delete_invoice,
    get_invoice_items
)

from ui.reports_page import export_invoices_excel
from ui.components.pdf_preview import PDFPreviewWindow 
# from theme import ENTRY_STYLE, PRIMARY_BTN, DANGER_BTN


class SavedInvoicesPage(ctk.CTkFrame):

    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app
        
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # stats
        self.grid_rowconfigure(2, weight=0)  # title
        self.grid_rowconfigure(3, weight=0)  # search
        self.grid_rowconfigure(4, weight=0)  # filter
        self.grid_rowconfigure(5, weight=1)  # table
        self.grid_rowconfigure(6, weight=0)  # buttons

        self.grid_columnconfigure(0, weight=1)

        # =========================
        # HEADER
        # =========================
        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="📂 إدارة الفواتير",
            font=("Cairo", 24, "bold"),
            text_color="#111827"
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="إدارة الفواتير المحفوظة بسهولة",
            font=("Cairo", 14),
            text_color="#6b7280"
        ).grid(row=1, column=0, sticky="w", pady=(5,0))

        # ======================
        # الإحصائيات السريعة
        # ======================
        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=15,
            pady=(0,10)
        )

        for i in range(4):
            self.stats_frame.grid_columnconfigure(
                i,
                weight=1
            )

        self.invoice_count_label = ctk.CTkLabel(
            self.stats_frame,
            text="عدد الفواتير: 0",
            font=("Cairo", 16, "bold")
        )
        self.invoice_count_label.grid(
            row=0,
            column=0,
            padx=15,
            pady=10,
            sticky="w"
        )

        self.sales_total_label = ctk.CTkLabel(
            self.stats_frame,
            text="إجمالي المبيعات: 0 ₪",
            font=("Cairo", 16, "bold")
        )
        self.sales_total_label.grid(
            row=0,
            column=1,
            padx=15,
            pady=10,
            sticky="e"
        )

        self.clients_count_label = ctk.CTkLabel(
            self.stats_frame,
            text="عدد العملاء: 0",
            font=("Cairo", 16, "bold")
        )
        self.clients_count_label.grid(
            row=0,
            column=2,
            padx=15,
            pady=10,
            sticky="ew"
        )

        self.last_invoice_label = ctk.CTkLabel(
            self.stats_frame,
            text="آخر فاتورة: -",
            font=("Cairo", 16, "bold")
        )
        self.last_invoice_label.grid(
            row=0,
            column=3,
            padx=15,
            pady=10,
            sticky="ew"
        )

        # ======================
        # البحث
        # ======================
        self.search_var = ctk.StringVar()

        self.search_entry = ctk.CTkEntry(
            self,
            textvariable=self.search_var,
            placeholder_text="🔍 ابحث برقم الفاتورة أو اسم العميل..."
        )
        self.search_entry.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=15,
            pady=(0,10)
        )

        self.search_var.trace_add(
            "write",
            self.on_search
        )

        # ======================
        # الفلاتر الزمنية
        # ======================
        self.filter_frame = ctk.CTkFrame(self)
        self.filter_frame.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=15,
            pady=(0,10)
        )

        self.filter_var = ctk.StringVar(value="الكل")

        ctk.CTkSegmentedButton(
            self.filter_frame,
            values=[
                "الكل",
                "اليوم",
                "الأسبوع",
                "الشهر",
                "سنة"
            ],
            variable=self.filter_var,
            command=self.apply_filters
        ).pack(fill="x", padx=10, pady=10)

        current_year = datetime.now().year

        years = [
            str(y)
            for y in range(
                current_year,
                current_year - 10,
                -1
            )
        ]

        self.year_menu = ctk.CTkOptionMenu(
            self.filter_frame,
            values=years,
            command=lambda x: self.apply_filters()
        )

        self.year_menu.pack(
            side="left",
            padx=10
        )

        # ======================
        # إنشاء جدول الفواتير 
        # ======================
        self.invoices_frame = ctk.CTkFrame(self)
        self.invoices_frame.grid(row=5, column=0, sticky="nsew", padx=10, pady=10)
        self.invoices_frame.grid_rowconfigure(0, weight=1)
        self.invoices_frame.grid_columnconfigure(0, weight=1)

        self.sort_reverse = False

        self.invoice_table = ttk.Treeview(
            self.invoices_frame,
            columns=(
                "number",
                "client",
                "date",
                "total"
            ),
            show="headings",
            height=20,
            selectmode="extended"
        )

        # رؤوس الأعمدة 
        # ======================
        self.invoice_table.heading(
            "number",
            text="رقم الفاتورة",
            command=lambda: self.sort_table("number")
        )

        self.invoice_table.heading(
            "client",
            text="العميل",
            command=lambda: self.sort_table("client")
        )

        self.invoice_table.heading(
            "date",
            text="التاريخ",
            command=lambda: self.sort_table("date")
        )

        self.invoice_table.heading(
            "total",
            text="الإجمالي",
            command=lambda: self.sort_table("total")
        )

        # عرض الأعمدة 
        # ======================
        self.invoice_table.column(
            "number",
            width=120,
            anchor="center"
        )

        self.invoice_table.column(
            "client",
            width=220,
            anchor="center"
        )

        self.invoice_table.column(
            "date",
            width=140,
            anchor="center"
        )

        self.invoice_table.column(
            "total",
            width=120,
            anchor="center"
        )

        # شريط تمرير للجداول Scrollbar 
        # ======================
        self.v_scroll = ttk.Scrollbar(
            self.invoices_frame,
            orient="vertical",
            command=self.invoice_table.yview
        )
        self.invoice_table.grid(row=0, column=0, sticky="nsew", padx=(10,0), pady=10)

        self.invoice_table.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.grid(row=0, column=1, sticky="ns", pady=10)

        # ======================
        # أزرار الإدارة
        # ======================
        self.actions_frame = ctk.CTkFrame(self)
        self.actions_frame.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0,10)
        )
        self.actions_frame.grid_columnconfigure((0,1,2,3,4,5), weight=1)

        self.preview_btn = ctk.CTkButton(
            self.actions_frame,
            text="👁 معاينة",
            command=self.preview_selected_invoice
        )
        self.preview_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.open_btn = ctk.CTkButton(
            self.actions_frame,
            text="📄 فتح PDF",
            command=self.open_selected_invoice
        )
        self.open_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.edit_btn = ctk.CTkButton(
            self.actions_frame,
            text="✏ تعديل",
            command=self.edit_selected_invoice
        )
        self.edit_btn.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.delete_btn = ctk.CTkButton(
            self.actions_frame,
            text="🗑 حذف",
            fg_color="#d9534f",
            hover_color="#c9302c",
            command=self.delete_selected_invoice
        )
        self.delete_btn.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        self.refresh_btn = ctk.CTkButton(
            self.actions_frame,
            text="🔄 تحديث",
            command=self.apply_filters
        )
        self.refresh_btn.grid(row=0, column=4, padx=5, pady=5, sticky="ew")

        self.export_btn = ctk.CTkButton(
            self.actions_frame,
            text="📊 تصدير Excel",
            command=self.export_selected_invoices
        )
        self.export_btn.grid(row=0, column=5, padx=5, pady=5, sticky="ew")
        
        self.load_invoices()


    # ======================
    # تحميل الفواتير
    # ======================
    def load_invoices(self):

        invoices = db_get_invoices()

        for item in self.invoice_table.get_children():
            self.invoice_table.delete(item)

        for inv_id, invoice_number, client, date_, total in invoices:

            self.invoice_table.insert(
                "",
                "end",
                iid=str(inv_id),
                values=(
                    invoice_number,
                    client,
                    date_,
                    total
                )
            )

        self.update_stats(invoices)

    # ======================
    # تحديث الإحصائيات
    # ======================
    def update_stats(self, invoices):

        invoice_count = len(invoices)

        total_sales = sum(
            float(inv[4] or 0)
            for inv in invoices
        )

        clients_count = len(
            set(
                inv[2]
                for inv in invoices
            )
        )

        if invoices:

            last_invoice = max(
                invoices,
                key=lambda inv: inv[0]
            )[1]

        else:

            last_invoice = "-"

        self.invoice_count_label.configure(
            text=f"📄 عدد الفواتير: {invoice_count}"
        )

        self.sales_total_label.configure(
            text=f"💰 إجمالي المبيعات: {total_sales:,.2f} ₪"
        )

        self.clients_count_label.configure(
            text=f"👥 عدد العملاء: {clients_count}"
        )

        self.last_invoice_label.configure(
            text=f"🧾 آخر فاتورة: {last_invoice}"
        )

    # ======================
    # تنفيذ التعديل
    # ======================
    def edit_selected_invoice(self):
        data = self.get_selected_invoice()

        if not data:
            return

        invoice_id, _ = data

        self.app.show_invoices()
        invoices_page = self.app.pages["invoices"]
        invoices_page.edit_invoice(invoice_id)


    # ======================
    # البحث الفوري
    # ======================
    def on_search(self, *args):
        self.apply_filters()

    # ======================
    # الفلاتر والتصفية 
    # ======================
    def apply_filters(self, *args):

        search_text = self.search_var.get().strip().lower()

        selected_filter = self.filter_var.get()

        today = datetime.today()

        invoices = db_get_invoices()

        filtered_invoices = []

        for item in self.invoice_table.get_children():
            self.invoice_table.delete(item)

        for inv_id, invoice_number, client, date_, total in invoices:

            try:
                invoice_date = datetime.strptime(
                    date_,
                    "%Y-%m-%d"
                )
            except ValueError:
                continue

            # البحث
            if search_text:

                if (
                    search_text not in str(invoice_number).lower()
                    and
                    search_text not in str(client).lower()
                ):
                    continue

            # الفلاتر
            if selected_filter == "اليوم":

                if invoice_date.date() != today.date():
                    continue

            elif selected_filter == "الأسبوع":

                start_week = today - timedelta(
                    days=today.weekday()
                )

                end_week = start_week + timedelta(days=6)

                if not (
                    start_week.date()
                    <= invoice_date.date()
                    <= end_week.date()
                ):
                    continue

            elif selected_filter == "الشهر":

                if (
                    invoice_date.month != today.month
                    or
                    invoice_date.year != today.year
                ):
                    continue

            elif selected_filter == "سنة":

                selected_year = int(
                    self.year_menu.get()
                )

                if invoice_date.year != selected_year:
                    continue
            
            # إضافة النتائج المطابقة 
            filtered_invoices.append(
                (
                    inv_id,
                    invoice_number,
                    client,
                    date_,
                    total
                )
            )

            self.invoice_table.insert(
                "",
                "end",
                iid=str(inv_id),
                values=(
                    invoice_number,
                    client,
                    date_,
                    total
                )
            )

        self.update_stats(filtered_invoices)

    # ======================
    # فرز الجدول
    # ======================
    def sort_table(self, column):

        data = []

        for item in self.invoice_table.get_children():

            values = self.invoice_table.item(
                item,
                "values"
            )

            columns = {
                "number": values[0],
                "client": values[1],
                "date": values[2],
                "total": values[3]
            }

            data.append(
                (
                    columns[column],
                    item
                )
            )

        try:
            data.sort(
                key=lambda x: float(x[0]),
                reverse=self.sort_reverse
            )

        except ValueError:

            data.sort(
                key=lambda x: str(x[0]).lower(),
                reverse=self.sort_reverse
            )

        for index, (_, item) in enumerate(data):

            self.invoice_table.move(
                item,
                "",
                index
            )

        self.sort_reverse = not self.sort_reverse

    # ======================
    # حدد الفاتورة 
    # ======================
    def get_selected_invoice(self):

        selected = self.invoice_table.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "يرجى اختيار فاتورة أولاً"
            )
            return None

        invoice_id = int(selected[0])

        values = self.invoice_table.item(
            selected[0],
            "values"
        )

        invoice_number = values[0]

        return invoice_id, invoice_number

    # ======================
    # حذف فاتورة
    # ======================
    def delete_invoice(self, invoice_id, invoice_number):

        confirm = messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف الفاتورة رقم {invoice_number}؟"
        )

        if not confirm:
            return

        db_delete_invoice(invoice_id)

        self.load_invoices()

        messagebox.showinfo(
            "تم",
            "تم حذف الفاتورة بنجاح"
        )
    
    # ======================
    # PDF
    # ======================
    def open_pdf(self, invoice_id):

        invoices = db_get_invoices()

        target = None

        for inv in invoices:

            if inv[0] == invoice_id:
                target = inv
                break

        if not target:
            return

        invoice_number = target[1]
        client_name = target[2]

        items = get_invoice_items(invoice_id)

        file_name = generate_pdf(
            invoice_id,
            invoice_number,
            items,
            client_name
        )

        os.startfile(file_name)

    # ======================
    # فتح PDF 
    # ======================
    def open_selected_invoice(self):

        data = self.get_selected_invoice()

        if not data:
            return

        invoice_id, _ = data

        self.open_pdf(invoice_id)

    # ======================
    # معاينة لفاتورة محفوظة مسبقاً
    # ======================
    def preview_invoice_pdf(self, invoice_id):

        invoices = db_get_invoices()

        target = None

        for inv in invoices:

            if inv[0] == invoice_id:
                target = inv
                break

        if not target:
            return

        invoice_number = target[1]
        client_name = target[2]

        items = get_invoice_items(invoice_id)

        file_name = generate_pdf(
            invoice_id,
            invoice_number,
            items,
            client_name
        )

        PDFPreviewWindow(self, file_name)

    # ======================
    # معاينة الفاتورة المحددة
    # ======================
    def preview_selected_invoice(self):

        data = self.get_selected_invoice()

        if not data:
            return

        invoice_id, _ = data

        self.preview_invoice_pdf(invoice_id)
    
    # ======================
    # حذف الفاتورة المحددة
    # ======================
    def delete_selected_invoice(self):

        data = self.get_selected_invoice()

        if not data:
            return

        invoice_id, invoice_number = data

        self.delete_invoice(
            invoice_id,
            invoice_number
        )

    # ======================
    # تصدير المحدد إلى Excel
    # ======================
    def export_selected_invoices(self):

        selected = self.invoice_table.selection()

        if not selected:

            messagebox.showwarning(
                "تنبيه",
                "يرجى تحديد فاتورة واحدة على الأقل"
            )

            return

        invoices = []

        for item in selected:

            values = self.invoice_table.item(
                item,
                "values"
            )

            invoices.append(
                (
                    int(item),      # ID
                    values[0],      # رقم الفاتورة
                    values[1],      # العميل
                    values[2],      # التاريخ
                    values[3]       # الإجمالي
                )
            )

        export_invoices_excel(invoices)

        