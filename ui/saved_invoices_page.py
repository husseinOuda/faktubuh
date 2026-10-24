# ui/saved_invoices_page.py

import os
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta

from pdf_generator import (
    generate_pdf
)

from database import (
    get_invoices as db_get_invoices,
    delete_invoice as db_delete_invoice,
    get_invoice_items,
    set_invoice_status,
    set_invoice_archived,
    status_label,
    STATUS_PAID,
    STATUS_UNPAID,
    STATUS_CANCELLED
)

from ui.reports_page import export_invoices_excel
from ui.components.pdf_preview import PDFPreviewWindow 
from ui.components.invoice_utils import (
    NumberParseError,
    format_money,
    parse_number
)
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
        self.grid_rowconfigure(5, weight=0)  # status / archive filter
        self.grid_rowconfigure(6, weight=1)  # table
        self.grid_rowconfigure(7, weight=0)  # buttons

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

        # إحصائيات الحالات (الفواتير الملغاة لا تدخل في إجمالي المبيعات)
        self.paid_label = ctk.CTkLabel(
            self.stats_frame,
            text="✅ المدفوعة: 0",
            font=("Cairo", 14, "bold"),
            text_color="#15803d"
        )
        self.paid_label.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        self.unpaid_label = ctk.CTkLabel(
            self.stats_frame,
            text="⏳ غير المدفوعة: 0",
            font=("Cairo", 14, "bold"),
            text_color="#c2410c"
        )
        self.unpaid_label.grid(row=1, column=1, padx=15, pady=(0, 10), sticky="e")

        self.cancelled_label = ctk.CTkLabel(
            self.stats_frame,
            text="🚫 الملغاة: 0",
            font=("Cairo", 14, "bold"),
            text_color="#b91c1c"
        )
        self.cancelled_label.grid(row=1, column=2, padx=15, pady=(0, 10), sticky="ew")

        self.archived_label = ctk.CTkLabel(
            self.stats_frame,
            text="🗄 المؤرشفة: 0",
            font=("Cairo", 14, "bold"),
            text_color="#4b5563"
        )
        self.archived_label.grid(row=1, column=3, padx=15, pady=(0, 10), sticky="ew")

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

        # عدد الفواتير المعروضة بعد التصفية
        self.result_count_label = ctk.CTkLabel(
            self.filter_frame,
            text="",
            font=("Cairo", 14, "bold"),
            text_color="#2563eb"
        )
        self.result_count_label.pack(
            side="right",
            padx=15
        )

        # ======================
        # فلتر الحالة + عرض الأرشيف
        # ======================
        self.status_filter_frame = ctk.CTkFrame(self)
        self.status_filter_frame.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=15,
            pady=(0, 10)
        )

        self.status_filter_var = ctk.StringVar(value="كل الحالات")

        self._status_filter_map = {
            "مدفوعة": STATUS_PAID,
            "غير مدفوعة": STATUS_UNPAID,
            "ملغاة": STATUS_CANCELLED,
        }

        ctk.CTkSegmentedButton(
            self.status_filter_frame,
            values=["كل الحالات", "مدفوعة", "غير مدفوعة", "ملغاة"],
            variable=self.status_filter_var,
            command=self.apply_filters
        ).pack(side="left", padx=10, pady=10)

        self.archive_view_var = ctk.StringVar(value="النشطة")

        ctk.CTkSegmentedButton(
            self.status_filter_frame,
            values=["النشطة", "المؤرشفة", "الكل"],
            variable=self.archive_view_var,
            command=self.on_archive_view_changed
        ).pack(side="right", padx=10, pady=10)

        # ======================
        # إنشاء جدول الفواتير 
        # ======================
        self.invoices_frame = ctk.CTkFrame(self)
        self.invoices_frame.grid(row=6, column=0, sticky="nsew", padx=10, pady=10)
        self.invoices_frame.grid_rowconfigure(0, weight=1)
        self.invoices_frame.grid_columnconfigure(0, weight=1)

        self.sort_reverse = False

        self.invoice_table = ttk.Treeview(
            self.invoices_frame,
            columns=(
                "number",
                "client",
                "date",
                "total",
                "status",
                "no"
            ),
            displaycolumns=(
                "no",
                "number",
                "client",
                "date",
                "total",
                "status"
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

        self.invoice_table.heading(
            "status",
            text="الحالة",
            command=lambda: self.sort_table("status")
        )

        # عرض الأعمدة 
        # ======================
        self.invoice_table.column(
            "status",
            width=110,
            anchor="center"
        )

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

        # عمود الترقيم التلقائي
        self.invoice_table.heading("no", text="#")

        self.invoice_table.column(
            "no",
            width=60,
            anchor="center",
            stretch=False
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

        # تمييز الصف عند مرور الفأرة
        # ======================
        self._hover_row = None
        self._row_status_tag = {}  # iid -> وسم الحالة (يُستعاد بعد إزالة التمييز)

        # ألوان الحالات
        self.invoice_table.tag_configure("status_paid", foreground="#15803d")
        self.invoice_table.tag_configure("status_unpaid", foreground="#c2410c")
        self.invoice_table.tag_configure(
            "status_cancelled",
            foreground="#9ca3af"
        )
        self.invoice_table.tag_configure("archived", background="#f3f4f6")
        self.invoice_table.tag_configure("hover", background="#e0e7ff")

        self.invoice_table.bind("<Motion>", self.on_table_hover)
        self.invoice_table.bind("<Leave>", self.on_table_leave)
        self.invoice_table.bind("<<TreeviewSelect>>", self.on_table_select)

        # اختصارات لوحة المفاتيح
        # ======================
        self.invoice_table.bind("<Return>", self.on_enter_key)
        self.invoice_table.bind("<KP_Enter>", self.on_enter_key)
        self.invoice_table.bind("<Delete>", self.on_delete_key)
        self.invoice_table.bind("<Double-1>", self.on_double_click)

        # قائمة بزر الفأرة الأيمن
        self.invoice_table.bind("<Button-3>", self.on_right_click)

        # ======================
        # أزرار الإدارة
        # ======================
        self.actions_frame = ctk.CTkFrame(self)
        self.actions_frame.grid(
            row=7,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0,10)
        )
        self.actions_frame.grid_columnconfigure((0,1,2,3,4,5,6), weight=1)

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
        
        self.copy_btn = ctk.CTkButton(
            self.actions_frame,
            text="📋 نسخ الفاتورة",
            command=self.copy_selected_invoice
        )
        self.copy_btn.grid(row=0, column=6, padx=5, pady=5, sticky="ew")

        # ----- الصف الثاني: الحالات والأرشفة -----
        self.paid_btn = ctk.CTkButton(
            self.actions_frame,
            text="✅ تحديد كمدفوعة",
            fg_color="#16a34a",
            hover_color="#15803d",
            command=lambda: self.change_selected_status(STATUS_PAID)
        )
        self.paid_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        self.unpaid_btn = ctk.CTkButton(
            self.actions_frame,
            text="⏳ تحديد كغير مدفوعة",
            fg_color="#ea580c",
            hover_color="#c2410c",
            command=lambda: self.change_selected_status(STATUS_UNPAID)
        )
        self.unpaid_btn.grid(row=1, column=2, columnspan=2, padx=5, pady=5, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            self.actions_frame,
            text="🚫 إلغاء الفاتورة",
            fg_color="#6b7280",
            hover_color="#4b5563",
            command=lambda: self.change_selected_status(STATUS_CANCELLED)
        )
        self.cancel_btn.grid(row=1, column=4, columnspan=2, padx=5, pady=5, sticky="ew")

        self.archive_btn = ctk.CTkButton(
            self.actions_frame,
            text="🗄 أرشفة",
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self.toggle_archive_selected
        )
        self.archive_btn.grid(row=1, column=6, padx=5, pady=5, sticky="ew")

        # قائمة الفأرة اليمنى
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="👁 معاينة", command=self.preview_selected_invoice)
        self.context_menu.add_command(label="📄 فتح PDF", command=self.open_selected_invoice)
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="✅ تحديد كمدفوعة",
            command=lambda: self.change_selected_status(STATUS_PAID)
        )
        self.context_menu.add_command(
            label="⏳ تحديد كغير مدفوعة",
            command=lambda: self.change_selected_status(STATUS_UNPAID)
        )
        self.context_menu.add_command(
            label="🚫 إلغاء الفاتورة",
            command=lambda: self.change_selected_status(STATUS_CANCELLED)
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗄 أرشفة / إلغاء الأرشفة", command=self.toggle_archive_selected)

        self.load_invoices()


    # ======================
    # تحميل الفواتير
    # ======================
    def load_invoices(self):
        """تحميل الفواتير وتحديث الجدول والإحصائيات."""
        self.apply_filters()

    # ======================
    # تحديث الإحصائيات
    # ======================
    def update_stats(self, invoices, archived_count=0):

        invoice_count = len(invoices)

        def _sum(status):
            return sum(
                float(invoice.get("total") or 0)
                for invoice in invoices
                if invoice.get("status") == status
            )

        paid_total = _sum(STATUS_PAID)
        unpaid_total = _sum(STATUS_UNPAID)
        cancelled_count = sum(
            1 for invoice in invoices
            if invoice.get("status") == STATUS_CANCELLED
        )

        # إجمالي المبيعات لا يشمل الفواتير الملغاة
        total_sales = paid_total + unpaid_total

        clients_count = len(
            set(
                invoice["client"]
                for invoice in invoices
            )
        )

        if invoices:

            last_invoice = max(
                invoices,
                key=lambda invoice: invoice["id"]
            )["invoice_number"]

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

        self.paid_label.configure(
            text=f"✅ المدفوعة: {paid_total:,.2f} ₪"
        )
        self.unpaid_label.configure(
            text=f"⏳ غير المدفوعة: {unpaid_total:,.2f} ₪"
        )
        self.cancelled_label.configure(
            text=f"🚫 الملغاة: {cancelled_count}"
        )
        self.archived_label.configure(
            text=f"🗄 المؤرشفة: {archived_count}"
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
    # نسخ الفاتورة المحددة
    # ======================
    def copy_selected_invoice(self):
        data = self.get_selected_invoice()

        if not data:
            return

        invoice_id, _ = data

        self.app.show_invoices()
        invoices_page = self.app.pages["invoices"]
        invoices_page.copy_invoice(invoice_id)

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

        all_invoices = db_get_invoices()

        archived_count = sum(1 for inv in all_invoices if inv["archived"])

        # عرض النشطة (الافتراضي) أو المؤرشفة أو الكل
        archive_view = self.archive_view_var.get()

        if archive_view == "النشطة":
            invoices = [inv for inv in all_invoices if not inv["archived"]]
        elif archive_view == "المؤرشفة":
            invoices = [inv for inv in all_invoices if inv["archived"]]
        else:
            invoices = all_invoices

        status_filter = self._status_filter_map.get(
            self.status_filter_var.get()
        )

        filtered_invoices = []

        for item in self.invoice_table.get_children():
            self.invoice_table.delete(item)

        self._row_status_tag = {}
        self._hover_row = None

        for invoice in invoices:

            # فلتر الحالة
            if status_filter and invoice["status"] != status_filter:
                continue

            # التاريخ مطلوب فقط مع الفلاتر الزمنية؛ في حالة "الكل" تظهر
            # كل الفواتير حتى التي تاريخها غير صالح
            invoice_date = None

            if selected_filter in ("اليوم", "الأسبوع", "الشهر", "سنة"):
                try:
                    invoice_date = datetime.strptime(
                        invoice["date"],
                        "%Y-%m-%d"
                    )
                except (ValueError, TypeError):
                    # لا يمكن مطابقة فاتورة بلا تاريخ صالح مع فلتر زمني
                    continue

            # البحث
            if search_text:

                if (
                    search_text not in str(invoice["invoice_number"]).lower()
                    and
                    search_text not in str(invoice["client"]).lower()
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
            filtered_invoices.append(invoice)

            iid = str(invoice["id"])

            tags = [f"status_{invoice['status']}"]

            if invoice["archived"]:
                tags.append("archived")

            self._row_status_tag[iid] = tuple(tags)

            self.invoice_table.insert(
                "",
                "end",
                iid=iid,
                values=(
                    invoice["invoice_number"],
                    invoice["client"],
                    invoice["date"],
                    format_money(invoice["total"]),
                    status_label(invoice["status"]) + (
                        " 🗄" if invoice["archived"] else ""
                    )
                ),
                tags=self._row_status_tag[iid]
            )
        self.renumber_rows()
        self.update_count_label(len(filtered_invoices), len(invoices))
        self.update_stats(filtered_invoices, archived_count)
        self.update_archive_button()
    
    # ======================
    # إعادة ترقيم الصفوف تلقائياً
    # ======================
    def renumber_rows(self):

        for number, item in enumerate(
            self.invoice_table.get_children(),
            start=1
        ):
            self.invoice_table.set(item, "no", number)

    # ======================
    # تمييز الصف عند مرور الفأرة
    # ======================
    def on_table_hover(self, event):

        row = self.invoice_table.identify_row(event.y)

        # نفس الصف ومميّز بالفعل → لا حاجة لأي تغيير
        if (
            row
            and row == self._hover_row
            and "hover" in self.invoice_table.item(row, "tags")
        ):
            return

        self._clear_hover()

        # لا نميّز الصف المحدد حتى يبقى لون التحديد ظاهراً
        if row and row not in self.invoice_table.selection():
            self.invoice_table.item(
                row,
                tags=self._row_status_tag.get(row, ()) + ("hover",)
            )
            self._hover_row = row

    def on_table_leave(self, event):
        self._clear_hover()

    def on_table_select(self, event):
        self._clear_hover()

    def _clear_hover(self):

        if (
            self._hover_row is not None
            and self.invoice_table.exists(self._hover_row)
        ):
            self.invoice_table.item(
                self._hover_row,
                tags=self._row_status_tag.get(self._hover_row, ())
            )

        self._hover_row = None

    # ======================
    # Enter → فتح التعديل / Delete → حذف الفاتورة
    # ======================
    def on_enter_key(self, event=None):

        if self.invoice_table.selection():
            self.edit_selected_invoice()

        return "break"

    def on_delete_key(self, event=None):

        if self.invoice_table.selection():
            self.delete_selected_invoice()

        return "break"

    # ======================
    # نقر مزدوج → فتح التعديل مباشرة
    # ======================
    def on_double_click(self, event):

        # تجاهل النقر على رؤوس الأعمدة أو المساحة الفارغة
        if self.invoice_table.identify_region(event.x, event.y) != "cell":
            return

        row = self.invoice_table.identify_row(event.y)

        if not row:
            return

        self.invoice_table.selection_set(row)
        self.edit_selected_invoice()

        return "break"
    
    # ======================
    # عدد الفواتير المعروضة
    # ======================
    def update_count_label(self, shown, total):

        self.result_count_label.configure(
            text=f"📋 المعروض: {shown} من {total} فاتورة"
        )

    # ======================
    # فرز الجدول
    # ======================
    def sort_table(self, column):

        column_index = {
            "number": 0,
            "client": 1,
            "date": 2,
            "total": 3,
            "status": 4,
        }[column]

        def sort_key(value):
            # الأعمدة الرقمية تُرتب كأرقام، والبقية كنص
            try:
                return (0, parse_number(value, "قيمة الفرز"), "")
            except NumberParseError:
                return (1, 0.0, str(value).lower())

        data = [
            (
                self.invoice_table.item(item, "values")[column_index],
                item
            )
            for item in self.invoice_table.get_children()
        ]

        data.sort(
            key=lambda x: sort_key(x[0]),
            reverse=self.sort_reverse
        )

        for index, (_, item) in enumerate(data):
            self.invoice_table.move(item, "", index)

        self.renumber_rows()
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
    # الفواتير المحددة (واحدة أو أكثر)
    # ======================
    def _selected_ids(self):

        selected = self.invoice_table.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "يرجى اختيار فاتورة أولاً"
            )
            return []

        return [int(iid) for iid in selected]

    # ======================
    # تغيير حالة الفواتير المحددة
    # ======================
    def change_selected_status(self, status):

        ids = self._selected_ids()

        if not ids:
            return

        label = status_label(status)

        # الإلغاء يحتاج تأكيداً لأنه يستبعد الفاتورة من إجمالي المبيعات
        if status == STATUS_CANCELLED:
            confirm = messagebox.askyesno(
                "تأكيد الإلغاء",
                f"هل تريد إلغاء {len(ids)} فاتورة؟\n"
                "الفواتير الملغاة لا تدخل في إجمالي المبيعات.\n"
                "(يمكنك إعادة حالتها لاحقاً)"
            )

            if not confirm:
                return

        try:
            set_invoice_status(ids, status)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر تغيير الحالة:\n{e}")
            return

        self.load_invoices()

        # إعادة تحديد الصفوف التي ما زالت ظاهرة بعد التحديث
        still_visible = [
            str(i) for i in ids
            if self.invoice_table.exists(str(i))
        ]

        if still_visible:
            self.invoice_table.selection_set(still_visible)

    # ======================
    # أرشفة / إلغاء أرشفة المحدد
    # ======================
    def toggle_archive_selected(self):

        ids = self._selected_ids()

        if not ids:
            return

        # في عرض المؤرشفة يكون الإجراء "إلغاء الأرشفة"، وغير ذلك "أرشفة"
        archive = self.archive_view_var.get() != "المؤرشفة"

        if self.archive_view_var.get() == "الكل":
            # في عرض "الكل": إن كانت كل المحددة مؤرشفة نلغي الأرشفة
            archived_ids = {
                inv["id"] for inv in db_get_invoices() if inv["archived"]
            }
            archive = not all(i in archived_ids for i in ids)

        try:
            set_invoice_archived(ids, archive)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر تنفيذ العملية:\n{e}")
            return

        self.load_invoices()

    def update_archive_button(self):

        if self.archive_view_var.get() == "المؤرشفة":
            self.archive_btn.configure(text="♻ إلغاء الأرشفة")
        else:
            self.archive_btn.configure(text="🗄 أرشفة")

    def on_archive_view_changed(self, *args):
        self.apply_filters()

    # ======================
    # قائمة الفأرة اليمنى
    # ======================
    def on_right_click(self, event):

        row = self.invoice_table.identify_row(event.y)

        if not row:
            return

        # إن كان الصف خارج التحديد الحالي نحدده وحده
        if row not in self.invoice_table.selection():
            self.invoice_table.selection_set(row)

        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

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

            if inv["id"] == invoice_id:
                target = inv
                break

        if not target:
            return

        invoice_number = target["invoice_number"]
        client_name = target["client"]

        items = get_invoice_items(invoice_id)

        file_name = generate_pdf(
            invoice_id,
            invoice_number,
            items,
            client_name,
            invoice_date=target["date"],
            subtotal=target["subtotal"],
            discount_percent=target["discount_percent"],
            discount_amount=target["discount_amount"],
            tax_percent=target["tax_percent"],
            tax_amount=target["tax_amount"],
            total=target["total"],
            notes=target["notes"],
            status=target["status"]
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

            if inv["id"] == invoice_id:
                target = inv
                break

        if not target:
            return

        invoice_number = target["invoice_number"]
        client_name = target["client"]

        items = get_invoice_items(invoice_id)

        file_name = generate_pdf(
            invoice_id,
            invoice_number,
            items,
            client_name,
            invoice_date=target["date"],
            subtotal=target["subtotal"],
            discount_percent=target["discount_percent"],
            discount_amount=target["discount_amount"],
            tax_percent=target["tax_percent"],
            tax_amount=target["tax_amount"],
            total=target["total"],
            notes=target["notes"],
            status=target["status"]
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

        selected = self.invoice_table.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "يرجى اختيار فاتورة أولاً"
            )
            return

        # فاتورة واحدة → نفس السلوك السابق
        if len(selected) == 1:

            data = self.get_selected_invoice()

            if data:
                invoice_id, invoice_number = data

                self.delete_invoice(
                    invoice_id,
                    invoice_number
                )

            return

        # عدة فواتير → تأكيد واحد ثم حذف الكل
        count = len(selected)

        confirm = messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف {count} فاتورة محددة؟\n"
            "لا يمكن التراجع عن هذه العملية."
        )

        if not confirm:
            return

        deleted = 0

        try:
            for iid in selected:
                db_delete_invoice(int(iid))
                deleted += 1

        except Exception as e:
            self.load_invoices()

            messagebox.showerror(
                "خطأ",
                f"تم حذف {deleted} من {count} فاتورة فقط:\n{e}"
            )
            return

        self.load_invoices()

        messagebox.showinfo(
            "تم",
            f"تم حذف {count} فاتورة بنجاح"
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

        invoices_by_id = {
            invoice["id"]: invoice
            for invoice in db_get_invoices()
        }

        selected_invoices = [
            invoices_by_id[int(item)]
            for item in selected
            if int(item) in invoices_by_id
        ]

        export_invoices_excel(selected_invoices)

        