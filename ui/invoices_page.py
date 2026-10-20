# ui/invoices_page.py

import os
import math
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date

from pdf_generator import (
    generate_pdf,
    generate_temp_pdf
)

from database import (
    get_clients,
    save_invoice,
    get_invoices,
    delete_invoice,
    get_invoice_by_id,
    get_invoice_items,
    get_invoice_info,
    add_client,
    update_invoice
)

from theme import ENTRY_STYLE, PRIMARY_BTN

from ui.components.invoice_utils import (
    NumberParseError,
    calculate_invoice_totals,
    format_money,
    parse_number,
    round_money
)

class InvoicesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        
        self.app = app

        # توزيع الشاشة: Header + المحتوى + شريط الإجراءات السفلي
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0, minsize=76)

        self.items = []
        self.edit_mode = False
        self.edit_invoice_id = None

        self.tax_percent_var = ctk.StringVar(value="0")
        self.discount_percent_var = ctk.StringVar(value="0")

        # محرر الخلية داخل جدول الأصناف
        self._cell_editor = None
        self._cell_editor_state = None

        # =========================
        # HEADER
        # =========================
        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="🧾 إنشاء الفواتير",
            font=("Cairo", 28, "bold"),
            text_color="#111827"
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="إنشاء الفواتير للعملاء بسهولة",
            font=("Cairo", 14),
            text_color="#6b7280"
        ).pack(anchor="w")

        # إطار المحتوى 
        # ======================
        content_frame = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        content_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=15,
            pady=(0, 10)
        )

        content_frame.grid_columnconfigure(0, weight=1)

        content_frame.grid_columnconfigure(1, weight=2)

        content_frame.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkScrollableFrame(content_frame)
        left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0,10)
        )

        right_panel = ctk.CTkFrame(
            content_frame
        )
        right_panel.grid(
            row=0,
            column=1,
            sticky="nsew"
        )

        # ======================
        # العملاء
        # ======================
        clients_frame = ctk.CTkFrame(left_panel)
        clients_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            clients_frame,
            text="👤 العميل"
        ).pack(anchor="w", padx=10)

        self.client_var = ctk.StringVar()

        clients = get_clients()

        self.client_map = {
            name: cid for cid, name, phone in clients
        }

        client_names = list(self.client_map.keys())

        self.client_combo = ctk.CTkComboBox(
            clients_frame,
            values=client_names,
            variable=self.client_var,
            width=350,
            height=40
        )

        self.client_combo.pack(padx=10, pady=5)

        ctk.CTkButton(
            clients_frame,
            text="➕ عميل جديد",
            command=self.open_add_client_window,
            **PRIMARY_BTN
        ).pack(pady=5)

        # =========================
        # TREEVIEW STYLE
        # =========================
        style = ttk.Style()

        style.theme_use("default")
        
        style.configure(
            "Treeview",
            rowheight=35,
            font=("Cairo", 12)
        )

        style.map(
            "Treeview",
            background=[("selected", "#2563eb")]
        )

        style.configure(
            "Treeview.Heading",
            font=("Cairo", 13, "bold")
        )

        form_frame = ctk.CTkFrame(left_panel)
        form_frame.pack(
            fill="x",
            padx=15,
            pady=10
        )

        form_frame.grid_columnconfigure(0, weight=1)
        form_frame.grid_columnconfigure(1, weight=1)

        # ======================
        # الخصم والضريبة والملاحظات
        # ======================
        settings_frame = ctk.CTkFrame(left_panel)
        settings_frame.pack(
            fill="x",
            padx=10,
            pady=(0, 10)
        )

        settings_frame.grid_columnconfigure(0, weight=1)
        settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            settings_frame,
            text="💰 الخصم والضريبة والملاحظات",
            font=("Cairo", 15, "bold")
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=10,
            pady=(10, 5)
        )

        self.discount_entry = ctk.CTkEntry(
            settings_frame,
            textvariable=self.discount_percent_var,
            placeholder_text="الخصم %",
            **ENTRY_STYLE
        )
        self.discount_entry.grid(
            row=1,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.tax_entry = ctk.CTkEntry(
            settings_frame,
            textvariable=self.tax_percent_var,
            placeholder_text="الضريبة %",
            **ENTRY_STYLE
        )
        self.tax_entry.grid(
            row=1,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.notes_entry = ctk.CTkEntry(
            settings_frame,
            placeholder_text="📝 ملاحظات الفاتورة - اختياري",
            height=45,
            corner_radius=10,
            font=("Cairo", 14)
        )
        self.notes_entry.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.discount_percent_var.trace_add(
            "write",
            lambda *args: self.refresh_invoice_summary()
        )

        self.tax_percent_var.trace_add(
            "write",
            lambda *args: self.refresh_invoice_summary()
        )

        # ======================
        # إدخال صنف
        # ======================
        self.item_name = ctk.CTkEntry(
            form_frame,
            placeholder_text="اسم الصنف",
            **ENTRY_STYLE
        )
        self.item_name.grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.item_desc = ctk.CTkEntry(
            form_frame,
            placeholder_text="الوصف",
            **ENTRY_STYLE
        )
        self.item_desc.grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.qty = ctk.CTkEntry(
            form_frame,
            placeholder_text="الكمية",
            **ENTRY_STYLE
        )
        self.qty.grid(
            row=1,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.price = ctk.CTkEntry(
            form_frame,
            placeholder_text="السعر",
            **ENTRY_STYLE
        )
        self.price.grid(
            row=1,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        # Enter في أي حقل: ينتقل للحقل التالي، وعند اكتمال البيانات يضيف الصنف
        for index, entry in enumerate(
            (self.item_name, self.item_desc, self.qty, self.price)
        ):
            entry.bind(
                "<Return>",
                lambda e, i=index: self.on_item_form_enter(i)
            )
            entry.bind(
                "<KP_Enter>",
                lambda e, i=index: self.on_item_form_enter(i)
            )

        ctk.CTkButton(
            form_frame,
            text="➕ إضافة صنف",
            command=self.add_item,
            **PRIMARY_BTN
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            pady=15
        )

        # ======================
        # جدول الأصناف
        # ======================
        ctk.CTkLabel(
            right_panel,
            text="📋 الأصناف المضافة",
            font=("Cairo", 18, "bold")
        ).pack(
            anchor="w",
            padx=15, 
            pady=(10,5)
        )

        table_frame = ctk.CTkFrame(
            right_panel,
            fg_color="transparent"
        )
        table_frame.pack(
            fill="x",
            padx=10,
            pady=10
        )

        # شريط أدوات الأصناف
        items_toolbar = ctk.CTkFrame(
            right_panel,
            fg_color="transparent"
        )
        items_toolbar.pack(
            fill="x",
            padx=10,
            pady=(0, 5)
        )

        ctk.CTkLabel(
            items_toolbar,
            text="Double Click أو F2 للتعديل",
            font=("Cairo", 12),
            text_color="#6b7280"
        ).pack(
            side="left",
            padx=5
        )

        ctk.CTkButton(
            items_toolbar,
            text="✏️ تعديل",
            width=85,
            height=32,
            corner_radius=8,
            font=("Cairo", 12, "bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self.edit_selected_item
        ).pack(
            side="right",
            padx=3
        )

        ctk.CTkButton(
            items_toolbar,
            text="🗑 حذف",
            width=85,
            height=32,
            corner_radius=8,
            font=("Cairo", 12, "bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.delete_selected_item
        ).pack(
            side="right",
            padx=3
        )

        # حاوية الجدول مع Scrollbar
        items_container = ctk.CTkFrame(right_panel)
        items_container.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 5)
        )

        items_container.grid_rowconfigure(0, weight=1)
        items_container.grid_columnconfigure(0, weight=1)

        self.items_table = ttk.Treeview(
            items_container,
            columns=(
                "name",
                "desc",
                "qty",
                "price",
                "total"
            ),
            show="headings",
            height=10,
            selectmode="extended"
        )

        self.items_table.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        self.items_scroll = ttk.Scrollbar(
            items_container,
            orient="vertical",
            command=self.items_table.yview
        )
        self.items_scroll.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        self.items_table.configure(
            yscrollcommand=self.items_scroll.set
        )

        self.items_table.heading(
            "name",
            text="الصنف"
        )

        self.items_table.heading(
            "desc",
            text="الوصف"
        )

        self.items_table.heading(
            "qty",
            text="الكمية"
        )

        self.items_table.heading(
            "price",
            text="السعر"
        )

        self.items_table.heading(
            "total",
            text="الإجمالي"
        )

        # شريط التمرير
        items_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self._on_items_scroll
        )
        self.items_table.configure(yscrollcommand=items_scroll.set)

        items_scroll.pack(side="right", fill="y")
        

        # تعديل الصنف مباشرة داخل الجدول
        # ======================
        self.items_table.bind("<Double-1>", self.on_item_double_click)
        self.items_table.bind("<F2>", self.on_item_f2)
        self.items_table.bind("<Delete>", self.delete_selected_item)
        self.items_table.bind("<MouseWheel>", self.on_items_table_scroll, add="+")

        # ======================
        # ملخص الفاتورة 
        # ======================
        totals_frame = ctk.CTkFrame(
            right_panel,
            fg_color="transparent"
        )
        totals_frame.pack(
            fill="x",
            padx=10,
            pady=(5, 10)
        )

        for column in range(4):
            totals_frame.grid_columnconfigure(
                column,
                weight=1
            )

        self.subtotal_label = ctk.CTkLabel(
            totals_frame,
            text="المجموع: 0.00 ₪",
            font=("Cairo", 13, "bold"),
            justify="right"
        )
        self.subtotal_label.grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.discount_label = ctk.CTkLabel(
            totals_frame,
            text="الخصم: 0.00 ₪",
            font=("Cairo", 13, "bold"),
            justify="right"
        )
        self.discount_label.grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.tax_label = ctk.CTkLabel(
            totals_frame,
            text="الضريبة: 0.00 ₪",
            font=("Cairo", 13, "bold"),
            justify="right"
        )
        self.tax_label.grid(
            row=0,
            column=2,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.total_label = ctk.CTkLabel(
            totals_frame,
            text="الإجمالي: 0.00 ₪",
            font=("Cairo", 16, "bold"),
            text_color="#2563eb",
            justify="right"
        )
        self.total_label.grid(
            row=0,
            column=3,
            padx=5,
            pady=5,
            sticky="ew"
        )

        # ======================
        # تحسين عرض الجدول 
        # ======================
        self.items_table.column(
            "name",
            width=180,
            anchor="center"
        )

        self.items_table.column(
            "desc",
            width=220,
            anchor="center"
        )

        self.items_table.column(
            "qty",
            width=80,
            anchor="center"
        )

        self.items_table.column(
            "price",
            width=100,
            anchor="center"
        )

        self.items_table.column(
            "total",
            width=120,
            anchor="center"
        )

        # ======================
        # شريط الأزرار السفلي الثابت
        # ======================
        SECONDARY_BTN = {
            "fg_color": "#f3f4f6",
            "hover_color": "#e5e7eb",
            "height": 45,
            "corner_radius": 10,
            "font": ("Cairo", 14, "bold"),
            "text_color": "#111827"
        }

        actions_bar = ctk.CTkFrame(
            self,
            fg_color="#ffffff",
            corner_radius=0,
            border_width=1,
            border_color="#e5e7eb",
            height=76
        )
        actions_bar.grid(
            row=2,
            column=0,
            sticky="ew"
        )
        actions_bar.grid_propagate(False)

        actions_inner = ctk.CTkFrame(
            actions_bar,
            fg_color="transparent"
        )
        actions_inner.pack(
            side="right",
            padx=15,
            pady=15
        )

        self.save_btn = ctk.CTkButton(
            actions_inner,
            text="💾 حفظ الفاتورة",
            width=165,
            command=self.save_invoice,
            **PRIMARY_BTN
        )
        self.save_btn.pack(
            side="right",
            padx=5
        )

        ctk.CTkButton(
            actions_inner,
            text="👁️ معاينة",
            width=135,
            command=self.preview_invoice,
            **SECONDARY_BTN
        ).pack(
            side="right",
            padx=5
        )

        self.print_btn = ctk.CTkButton(
            actions_inner,
            text="🖨️ طباعة",
            width=135,
            command=self.preview_and_print,
            **SECONDARY_BTN
        )
        self.print_btn.pack(
            side="right",
            padx=5
        )

        self.cancel_edit_btn = ctk.CTkButton(
            actions_inner,
            text="✖ إلغاء التعديل",
            width=150,
            height=45,
            corner_radius=10,
            font=("Cairo", 14, "bold"),
            fg_color="#6b7280",
            hover_color="#4b5563",
            command=self.cancel_edit
        )
        self.cancel_edit_btn.pack(
            side="left",
            padx=5
        )

        # زر إلغاء التعديل مخفي افتراضياً
        self.cancel_edit_btn.pack_forget()

    # ======================
    # Enter داخل حقول إدخال الصنف
    # ======================
    def on_item_form_enter(self, index):

        fields = [self.item_name, self.item_desc, self.qty, self.price]
        required = [self.item_name, self.qty, self.price]

        # الحقول الإلزامية (الاسم والكمية والسعر) معبأة → أضف الصنف
        if all(field.get().strip() for field in required):

            count_before = len(self.items)

            self.add_item()

            # بعد نجاح الإضافة نعود لحقل الاسم لإدخال الصنف التالي
            if len(self.items) > count_before:
                self.item_name.focus_set()

            return "break"

        # وإلا ننتقل إلى الحقل التالي (ومن السعر إلى أول حقل إلزامي فارغ)
        if index < len(fields) - 1:
            target = fields[index + 1]
        else:
            target = next(
                field for field in required
                if not field.get().strip()
            )

        target.focus_set()

        return "break"
    
    # ======================
    # إضافة صنف
    # ======================
    def add_item(self):
        try:
            name = self.item_name.get().strip()
            desc = self.item_desc.get().strip()

            if not name:
                raise NumberParseError("يرجى إدخال اسم الصنف")

            qty = parse_number(
                self.qty.get(),
                "الكمية",
                positive=True
            )

            price = parse_number(
                self.price.get(),
                "السعر",
                allow_zero=True
            )

            total = round_money(qty * price)

            self.items.append({
                "name": name,
                "desc": desc,
                "qty": qty,
                "price": price,
                "total": total
            })

            self.clear_inputs()
            self.refresh_items()

        except NumberParseError as error:
            messagebox.showerror("خطأ", str(error))

    # ======================
    # تحديث جدول الأصناف
    # ======================
    def refresh_items(self):
        # إغلاق محرر الخلية إن كان مفتوحاً
        self._destroy_cell_editor()

        # تنظيف الجدول 
        for row in self.items_table.get_children():
            self.items_table.delete(row)

        total = 0

        for index, item in enumerate(self.items):

            # iid = موضع الصنف في القائمة self.items
            self.items_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item["name"],
                    item["desc"],
                    format_money(item["qty"], symbol=False),
                    format_money(item["price"], symbol=False),
                    format_money(item["total"], symbol=False)
                )
            )
            total += item["total"]

        self.refresh_invoice_summary()

    # ======================
    # قراءة الخصم والضريبة والملاحظات وحساب الإجمالي النهائي
    # ======================
    def get_invoice_summary(self, show_errors=False):

        try:
            discount_text = self.discount_percent_var.get().strip()
            tax_text = self.tax_percent_var.get().strip()

            discount_percent = (
                0 if not discount_text
                else parse_number(discount_text, "نسبة الخصم")
            )

            tax_percent = (
                0 if not tax_text
                else parse_number(tax_text, "نسبة الضريبة")
            )

            notes = self.notes_entry.get().strip()

            return calculate_invoice_totals(
                self.items,
                discount_percent=discount_percent,
                tax_percent=tax_percent
            ) | {"notes": notes}

        except NumberParseError as error:
            if show_errors:
                messagebox.showerror("خطأ", str(error))
            return None


    # ======================
    # تحديث ملخص الفاتورة عند تغيير الأصناف أو الخصم أو الضريبة.
    # ======================
    def refresh_invoice_summary(self):

        if not hasattr(self, "total_label"):
            return

        summary = self.get_invoice_summary()

        if summary is None:
            self.subtotal_label.configure(text="المجموع: —")
            self.discount_label.configure(text="الخصم: —")
            self.tax_label.configure(text="الضريبة: —")
            self.total_label.configure(text="الإجمالي: —")
            return

        self.subtotal_label.configure(
            text=f"المجموع: {format_money(summary['subtotal'])}"
        )

        self.discount_label.configure(
            text=f"الخصم: {format_money(summary['discount_amount'])}"
        )

        self.tax_label.configure(
            text=f"الضريبة: {format_money(summary['tax_amount'])}"
        )

        self.total_label.configure(
            text=f"الإجمالي: {format_money(summary['total'])}"
        )


    # ======================
    # تفريغ الخصم والضريبة والملاحظات.
    # ======================
    def reset_invoice_extras(self):

        self.discount_percent_var.set("0")
        self.tax_percent_var.set("0")

        self.notes_entry.delete(0, "end")
        self.refresh_invoice_summary()


    # ======================
    # تعديل الأصناف داخل الجدول (Inline Edit)
    # ======================
    # الأعمدة القابلة للتعديل بالترتيب (الإجمالي يُحسب تلقائياً)
    EDITABLE_COLUMNS = ("name", "desc", "qty", "price")
    ALL_COLUMNS = ("name", "desc", "qty", "price", "total")

    def on_item_double_click(self, event):
        """نقر مزدوج على خلية → فتح محرر فوقها."""
        if self.items_table.identify_region(event.x, event.y) != "cell":
            return

        row_id = self.items_table.identify_row(event.y)
        col_index = int(self.items_table.identify_column(event.x)[1:]) - 1

        if not row_id or col_index < 0:
            return

        column = self.ALL_COLUMNS[col_index]

        # عمود الإجمالي للقراءة فقط
        if column not in self.EDITABLE_COLUMNS:
            return "break"

        self._start_cell_edit(row_id, column)
        return "break"

    def on_item_f2(self, event=None):
        """F2 → تعديل أول خلية في الصنف المحدد."""
        selected = self.items_table.selection()

        if selected:
            self._start_cell_edit(selected[0], self.EDITABLE_COLUMNS[0])

        return "break"

    def _on_items_scroll(self, *args):
        # حفظ التعديل المفتوح قبل تحريك الجدول بشريط التمرير
        self._finish_cell_edit(commit=True)
        self.items_table.yview(*args)

    def on_items_table_scroll(self, event=None):
        # عند التمرير يتغير موضع الصفوف، فنحفظ التعديل ونغلق المحرر
        self._finish_cell_edit(commit=True)

    def _start_cell_edit(self, row_id, column):
        # حفظ أي تعديل مفتوح قبل فتح خلية جديدة
        if not self._finish_cell_edit(commit=True):
            return

        # تأكد أن الصف ظاهر في الجدول (عند وجود تمرير)
        self.items_table.see(row_id)
        self.items_table.update_idletasks()

        bbox = self.items_table.bbox(row_id, column)

        if not bbox:
            return

        x, y, width, height = bbox
        index = int(row_id)
        current_value = self.items[index].get(column, "")

        if current_value is None:
            current_value = ""

        self.items_table.selection_set(row_id)
        self.items_table.focus(row_id)

        editor = tk.Entry(
            self.items_table,
            font=("Cairo", 12),
            justify="center",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#2563eb",
            highlightbackground="#2563eb"
        )
        editor.insert(0, str(current_value))
        editor.select_range(0, "end")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()

        self._cell_editor = editor
        self._cell_editor_state = {"index": index, "column": column}

        editor.bind("<Return>", lambda e: self._on_editor_enter())
        editor.bind("<KP_Enter>", lambda e: self._on_editor_enter())
        editor.bind("<Escape>", lambda e: self._on_editor_escape())
        editor.bind("<Tab>", lambda e: self._on_editor_tab(forward=True))
        editor.bind("<ISO_Left_Tab>", lambda e: self._on_editor_tab(forward=False))
        editor.bind("<Shift-Tab>", lambda e: self._on_editor_tab(forward=False))
        editor.bind("<FocusOut>", lambda e: self._on_editor_focus_out())

    def _on_editor_enter(self):
        self._finish_cell_edit(commit=True, show_error=True)
        return "break"

    def _on_editor_escape(self):
        self._finish_cell_edit(commit=False)
        return "break"

    def _on_editor_focus_out(self):
        # عند فقدان التركيز: نحفظ إن كانت القيمة صحيحة، وإلا نتراجع بصمت
        if self._cell_editor is not None:
            self._finish_cell_edit(commit=True)

    def _on_editor_tab(self, forward=True):
        """Tab / Shift+Tab → الانتقال للخلية القابلة للتعديل التالية/السابقة."""
        state = self._cell_editor_state

        if not state:
            return "break"

        index = state["index"]
        pos = self.EDITABLE_COLUMNS.index(state["column"])
        pos += 1 if forward else -1

        if not self._finish_cell_edit(commit=True, show_error=True):
            return "break"

        if 0 <= pos < len(self.EDITABLE_COLUMNS):
            self._start_cell_edit(str(index), self.EDITABLE_COLUMNS[pos])

        return "break"

    def _validate_cell_value(self, column, text):
        """يرجع (القيمة المحوّلة، رسالة الخطأ). رسالة الخطأ None إن كانت القيمة صحيحة."""
        text = text.strip()

        if column == "name":
            if not text:
                return None, "اسم الصنف لا يمكن أن يكون فارغاً"
            return text, None

        if column == "desc":
            return text, None

        if column == "qty":
            try:
                return parse_number(text, "الكمية", positive=True), None
            except NumberParseError as error:
                return None, str(error)

        if column == "price":
            try:
                return parse_number(text, "السعر"), None
            except NumberParseError as error:
                return None, str(error)

        return None, "عمود غير قابل للتعديل"

    def _finish_cell_edit(self, commit=True, show_error=False):
        """
        إنهاء التعديل الجاري.
        يرجع True إذا أُغلق المحرر (أو لم يكن مفتوحاً)،
        و False إذا بقي مفتوحاً بسبب قيمة غير صحيحة.
        """
        editor = self._cell_editor
        state = self._cell_editor_state

        if editor is None or state is None:
            return True

        if not commit:
            self._destroy_cell_editor()
            return True

        index = state["index"]
        column = state["column"]

        value, error = self._validate_cell_value(column, editor.get())

        if error:
            if show_error:
                # نُبقي المحرر مفتوحاً ونلوّنه بالأحمر ليصحح المستخدم القيمة
                editor.configure(
                    bg="#fee2e2",
                    highlightcolor="#dc2626",
                    highlightbackground="#dc2626"
                )
                self.bell()
                return False

            # فقدان تركيز مع قيمة غير صحيحة → تراجع عن التعديل
            self._destroy_cell_editor()
            return True

        # تطبيق القيمة وإعادة حساب إجمالي الصنف
        item = self.items[index]
        item[column] = value
        item["total"] = round_money(item["qty"] * item["price"])

        self._destroy_cell_editor()
        self.refresh_items()

        # إبقاء الصف محدداً بعد التحديث
        row_id = str(index)
        if self.items_table.exists(row_id):
            self.items_table.selection_set(row_id)
            self.items_table.focus(row_id)

        return True

    def _destroy_cell_editor(self):
        editor = self._cell_editor

        # نصفّر الحالة أولاً حتى لا يعيد FocusOut استدعاء الإنهاء
        self._cell_editor = None
        self._cell_editor_state = None

        if editor is not None:
            try:
                editor.destroy()
            except tk.TclError:
                pass

    def remove_item(self, index):
        self.items.pop(index)
        self.refresh_items()

    # ======================
    # فتح تعديل أول خلية في الصنف المحدد
    # ======================
    def edit_selected_item(self, event=None):

        selected = self.items_table.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "يرجى تحديد صنف أولاً"
            )
            return "break"

        # حفظ أي محرر مفتوح قبل فتح محرر جديد
        if not self._finish_cell_edit(
            commit=True,
            show_error=True
        ):
            return "break"

        row_id = selected[0]

        if self.items_table.exists(row_id):
            self._start_cell_edit(
                row_id,
                self.EDITABLE_COLUMNS[0]
            )

        return "break"

    # ======================
    # حذف الأصناف المحددة من الجدول
    # ======================
    def delete_selected_item(self, event=None):
        selected = self.items_table.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "يرجى تحديد صنف أولاً"
            )
            return "break"

        count = len(selected)

        if count == 1:
            index = int(selected[0])
            name = self.items[index]["name"]
            question = f"هل تريد حذف الصنف \"{name}\"؟"
        else:
            question = f"هل تريد حذف {count} أصناف محددة؟"

        if not messagebox.askyesno("تأكيد الحذف", question):
            return "break"

        # الحذف من الأكبر إلى الأصغر حتى لا تتغير مواضع الأصناف المتبقية
        for iid in sorted(selected, key=int, reverse=True):
            self.remove_item(int(iid))

        return "break"
    
    # ======================
    # معاينة الفاتورة
    # ======================
    def preview_invoice(self):

        if not self.items:
            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف للمعاينة"
            )
            return

        client_name = self.client_var.get()

        # إنشاء نافذة
        preview = ctk.CTkToplevel(self)

        preview.title("معاينة الفاتورة")

        preview.geometry("700x500")

        # عنوان
        # ======================
        ctk.CTkLabel(
            preview,
            text="🧾 معاينة الفاتورة",
            font=("Cairo", 24, "bold")
        ).pack(pady=10)

        # بيانات العميل
        ctk.CTkLabel(
            preview,
            text=f"العميل: {client_name}",
            font=("Cairo", 18)
        ).pack()

        ctk.CTkLabel(
            preview,
            text=f"التاريخ: {date.today()}",
            font=("Cairo", 16)
        ).pack(pady=5)

        # جدول الأصناف
        # ======================
        frame = ctk.CTkFrame(preview)

        frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        # رؤوس الجدول
        headers = [
            "الصنف",
            "الوصف",
            "الكمية",
            "السعر",
            "الإجمالي"
        ]

        for col, header in enumerate(headers):

            ctk.CTkLabel(
                frame,
                text=header,
                font=("Cairo", 14, "bold")
            ).grid(
                row=0,
                column=col,
                padx=10,
                pady=10
            )

        # الأصناف
        total = 0

        for row, item in enumerate(self.items, start=1):

            values = [
                item["name"],
                item.get("desc", ""),
                item["qty"],
                item["price"],
                item["total"]
            ]

            total += item["total"]

            for col, value in enumerate(values):

                ctk.CTkLabel(
                    frame,
                    text=str(value)
                ).grid(
                    row=row,
                    column=col,
                    padx=10,
                    pady=5
                )

        # الإجمالي
        # ======================
        summary = self.get_invoice_summary(show_errors=True)

        if summary is None:
            return

        ctk.CTkLabel(
            preview,
            text=f"المجموع الفرعي: {format_money(summary['subtotal'])}",
            font=("Cairo", 15)
        ).pack()

        ctk.CTkLabel(
            preview,
            text=(
                f"الخصم ({summary['discount_percent']:g}%): "
                f"{format_money(summary['discount_amount'])}"
            ),
            font=("Cairo", 15)
        ).pack()

        ctk.CTkLabel(
            preview,
            text=(
                f"الضريبة ({summary['tax_percent']:g}%): "
                f"{format_money(summary['tax_amount'])}"
            ),
            font=("Cairo", 15)
        ).pack()

        ctk.CTkLabel(
            preview,
            text=f"الإجمالي النهائي: {format_money(summary['total'])}",
            font=("Cairo", 18, "bold"),
            text_color="#2563eb"
        ).pack(pady=10)

        if summary["notes"]:
            ctk.CTkLabel(
                preview,
                text="📝 الملاحظات:",
                font=("Cairo", 15, "bold")
            ).pack()

            ctk.CTkLabel(
                preview,
                text=summary["notes"],
                font=("Cairo", 14),
                wraplength=650,
                justify="right"
            ).pack(pady=5)

    
    # ======================
    # حفظ فاتورة جديدة أو تحديث فاتورة
    # ======================
    def save_invoice(self):

        if not self.items:
            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف في الفاتورة"
            )
            return

        client_name = self.client_var.get().strip()
        client_id = self.client_map.get(client_name)

        if not client_id:
            messagebox.showerror(
                "خطأ",
                "يرجى اختيار عميل صحيح"
            )
            return

        summary = self.get_invoice_summary(show_errors=True)

        if summary is None:
            return

        try:
            # تعديل فاتورة موجودة
            if self.edit_invoice_id is not None:

                update_invoice(
                    self.edit_invoice_id,
                    client_id,
                    self.items,
                    tax_percent=summary["tax_percent"],
                    discount_percent=summary["discount_percent"],
                    notes=summary["notes"]
                )

                message = "تم تعديل الفاتورة بنجاح"

            # إنشاء فاتورة جديدة
            else:

                save_invoice(
                    client_id,
                    str(date.today()),
                    self.items,
                    tax_percent=summary["tax_percent"],
                    discount_percent=summary["discount_percent"],
                    notes=summary["notes"]
                )

                message = "تم حفظ الفاتورة بنجاح"

        except Exception as e:
            messagebox.showerror(
                "خطأ",
                f"تعذر حفظ الفاتورة:\n{e}"
            )
            return

        # إعادة الصفحة إلى وضع الإنشاء الطبيعي
        self.items = []
        self.edit_mode = False
        self.edit_invoice_id = None

        self.save_btn.configure(
            text="💾 حفظ الفاتورة"
        )

        self.set_cancel_button_visible(False)
        self.refresh_items()
        self.clear_inputs()
        self.client_var.set("")
        self.reset_invoice_extras()

        messagebox.showinfo("تم", message)

        # تحديث صفحة الفواتير المحفوظة إن كانت موجودة
        saved_page = self.app.pages.get("saved_invoices")

        if saved_page and saved_page.winfo_exists():
            saved_page.load_invoices()
    
    # ======================
    # تعديل فاتورة محفوظة
    # ======================
    def edit_invoice(self, invoice_id):

        # جلب بيانات الفاتورة
        invoice_info = get_invoice_info(invoice_id)

        if not invoice_info:
            messagebox.showerror(
                "خطأ",
                "تعذر العثور على الفاتورة"
            )
            return

        # جلب الأصناف
        items = get_invoice_items(invoice_id)

        invoice_number = invoice_info["invoice_number"]
        client_name = invoice_info["client"]

        # تفعيل وضع التعديل
        self.edit_mode = True
        self.edit_invoice_id = invoice_id

        # تحديد العميل
        self.client_var.set(client_name)
        self.discount_percent_var.set(
            str(invoice_info.get("discount_percent") or 0)
        )

        self.tax_percent_var.set(
            str(invoice_info.get("tax_percent") or 0)
        )

        self.notes_entry.delete(0, "end")
        self.notes_entry.insert(
            0,
            invoice_info.get("notes") or ""
        )

        self.refresh_invoice_summary()

        # تحديث قائمة الأصناف في الذاكرة
        self.items = []

        for item in items:
            self.items.append({
                "name": item[0],
                "desc": item[1] or "",
                "qty": item[2],
                "price": item[3],
                "total": item[4]
            })

        # عرض الأصناف وتحديث الإجمالي
        self.refresh_items()

        # تغيير نص زر الحفظ
        self.save_btn.configure(
            text="💾 حفظ التعديلات"
        )
        
        messagebox.showinfo(
            "تعديل",
            f"أنت الآن تعدل الفاتورة رقم {invoice_number}"
        )

        self.set_cancel_button_visible(True)

    # ======================
    # نسخ فاتورة محفوظة كفاتورة جديدة
    # ======================
    def copy_invoice(self, invoice_id):

        invoice_info = get_invoice_info(invoice_id)

        if not invoice_info:
            messagebox.showerror(
                "خطأ",
                "تعذر العثور على الفاتورة"
            )
            return

        items = get_invoice_items(invoice_id)

        invoice_number = invoice_info["invoice_number"]
        client_name = invoice_info["client"] or ""

        self.discount_percent_var.set(
            str(invoice_info.get("discount_percent") or 0)
        )

        self.tax_percent_var.set(
            str(invoice_info.get("tax_percent") or 0)
        )

        self.notes_entry.delete(0, "end")
        self.notes_entry.insert(
            0,
            invoice_info.get("notes") or ""
        )

        self.refresh_invoice_summary()

        # وضع الإنشاء (فاتورة جديدة وليس تعديلاً)
        self.edit_mode = False
        self.edit_invoice_id = None

        self.save_btn.configure(
            text="💾 حفظ الفاتورة"
        )

        self.set_cancel_button_visible(False)
        
        # نسخ العميل والأصناف
        self.client_var.set(client_name)

        self.items = []

        for item in items:
            self.items.append({
                "name": item[0],
                "desc": item[1] or "",
                "qty": item[2],
                "price": item[3],
                "total": item[4]
            })

        self.refresh_items()
        self.clear_inputs()

        messagebox.showinfo(
            "نسخ",
            f"تم نسخ بيانات الفاتورة رقم {invoice_number}\n"
            "عدّل ما تريد ثم اضغط \"حفظ الفاتورة\" لإنشاء فاتورة جديدة"
        )

    # ======================
    # إظهار أو إخفاء زر إلغاء التعديل في الشريط السفلي
    # ======================
    def set_cancel_button_visible(self, visible):

        if visible:
            self.cancel_edit_btn.pack(
                side="left",
                padx=5
            )
        else:
            self.cancel_edit_btn.pack_forget()

    # ======================
    # إلغاء تعديل الفاتورة والعودة للقائمة
    # ======================
    def cancel_edit(self):

        if not self.edit_mode:
            return

        confirm = messagebox.askyesno(
            "إلغاء التعديل",
            "هل تريد إلغاء تعديل الفاتورة؟\n"
            "لن تُحفظ أي تغييرات أجريتها."
        )

        if not confirm:
            return

        # العودة لصفحة الفواتير المحفوظة (تُبنى الصفحة من جديد)
        self.app.show_saved_invoices()

    # ======================
    # معاينة قبل حفظ الفاتورة الحالية
    # ======================
    def preview_and_print(self):

        if not self.items:

            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف"
            )

            return

        client_name = self.client_var.get()

        summary = self.get_invoice_summary(show_errors=True)

        if summary is None:
            return

        pdf_path = generate_temp_pdf(
            client_name,
            self.items,
            summary
        )

        # فتح الملف
        os.startfile(pdf_path)
    
    
    # ======================
    # طباعة مباشرة
    # ======================
    def print_invoice(self, invoice_id):

        invoices = get_invoices()

        target = None

        for inv in invoices:

            if inv[0] == invoice_id:
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
            notes=target["notes"]
        )

        try:

            os.startfile(file_name, "print")

        except:

            messagebox.showerror(
                "خطأ",
                "تعذر بدء الطباعة"
            )

    # ======================
    # نافذة إضافة عميل
    # ======================
    def open_add_client_window(self):

        window = ctk.CTkToplevel(self)
        window.title("إضافة عميل")
        window.geometry("400x250")

        # الاسم
        name_entry = ctk.CTkEntry(
            window,
            placeholder_text="اسم العميل",
            width=300,
            **ENTRY_STYLE
        )
        name_entry.pack(pady=20)

        # الهاتف
        phone_entry = ctk.CTkEntry(
            window,
            placeholder_text="رقم الهاتف",
            width=300,
            **ENTRY_STYLE
        )
        phone_entry.pack(pady=10)

        # زر الحفظ
        ctk.CTkButton(
            window,
            text="💾 حفظ العميل",
            command=lambda: self.save_new_client(
                window,
                name_entry.get(),
                phone_entry.get()
            ),
            **PRIMARY_BTN
        ).pack(pady=20)
                

    # ======================
    # حفظ العميل الجديد
    # ======================
    def save_new_client(self, window, name, phone):

        name = name.strip()
        phone = phone.strip()

        if not name:
            messagebox.showerror(
                "خطأ",
                "يرجى إدخال اسم العميل"
            )
            return

        # حفظ العميل
        try:
            add_client(name, phone)
        except ValueError as e:
            messagebox.showerror("خطأ", str(e))
            return

        # تحديث العملاء
        self.refresh_clients_list()

        # اختيار العميل الجديد تلقائياً
        self.client_var.set(name)

        messagebox.showinfo(
            "تم",
            "تم إضافة العميل بنجاح"
        )

        window.destroy()

    # ======================
    # تحديث قائمة العملاء
    # ======================
    def refresh_clients_list(self):

        clients = get_clients()

        self.client_map = {
            name: cid for cid, name, phone in clients
        }

        client_names = list(self.client_map.keys())

        self.client_combo.configure(
            values=client_names
        )        

    # ======================
    # تنظيف الحقول
    # ======================
    def clear_inputs(self):
        self.item_name.delete(0, "end")
        self.item_desc.delete(0, "end")
        self.qty.delete(0, "end")
        self.price.delete(0, "end")
        
