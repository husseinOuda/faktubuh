# ui/purchase_order_form_page.py
"""
إنشاء / تعديل أمر شراء — بنفس تخطيط صفحة إنشاء الفاتورة:

  يمين الشاشة (اللوحة اليسرى برمجياً): المورد، رقم أمر الشراء ورقم فاتورة
  المورد والتاريخ، إدخال الأصناف، الخصم والضريبة والملاحظات، والدفعة.
  اللوحة الكبيرة: جدول الأصناف (نقر مزدوج أو F2 للتعديل · Delete للحذف)
  وتحته الإجمالي والمدفوع والمتبقي.

  - رقم أمر الشراء تلقائي: PO-2026-0001 (يبدأ كل سنة من 0001).
  - رقم فاتورة المورد يُعبَّأ تلقائياً (1، 2، 3 ...) ويمكن تعديله.
  - «المدفوع الآن» ينشئ سند صرف PV مرتبطاً بالأمر والمورد.
  - الباركود: اكتب/امسح الباركود في حقله (قارئ USB ثم Enter) أو اضغط
    «📷 مسح بالكاميرا». الصنف المعروف يُضاف بكمية 1 وآخر سعر شراء، ومسح الصنف
    نفسه مجدداً يزيد كميته 1؛ والباركود الجديد يُكمل بإدخال اسم الصنف وسعره
    ويُحفظ للمرات القادمة.
"""

from datetime import date as _date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from database import PAYMENT_METHODS
from purchase_pdf import generate_temp_purchase_pdf
from purchases_db import (
    SUPPLIER_BALANCE_LABELS,
    get_product_by_barcode,
    get_purchase_order,
    get_purchase_order_items,
    get_suppliers_full,
    next_supplier_invoice_number,
    preview_po_number,
    save_purchase_order,
    update_purchase_order,
)
from theme import BRAND_LIGHT, BRAND_NAVY, ENTRY_STYLE, PRIMARY_BTN
from ui.components.barcode_dialog import open_barcode_scanner
from ui.components.dialogs import FormDialog
from ui.components.files import open_file
from ui.components.invoice_utils import (
    NumberParseError,
    calculate_invoice_totals,
    format_money,
    parse_number,
    round_money,
)
from ui.components.pdf_preview import PDFPreviewWindow
from ui.components.supplier_dialogs import SupplierFormDialog, SupplierPicker
from ui.components.tables import (
    STYLE_NAME,
    configure_zebra,
    rtl_columns,
    setup_table_style,
    zebra_tag,
)

_METHOD_BY_LABEL = {label: code for code, label in PAYMENT_METHODS.items()}

_SECONDARY_BTN = {
    "fg_color": "#f3f4f6",
    "hover_color": "#e5e7eb",
    "height": 45,
    "corner_radius": 10,
    "font": ("Cairo", 14, "bold"),
    "text_color": "#111827",
}


# =====================================================
# نافذة تعديل صنف
# =====================================================
class PurchaseItemDialog(FormDialog):

    def __init__(self, parent, item, on_done):
        self.item = item

        super().__init__(parent, "✏ تعديل الصنف", width=480, on_done=on_done)

        self.add_entry("name", "اسم الصنف *", initial=item["name"])
        self.add_entry("barcode", "الباركود", initial=item.get("barcode", ""))
        self.add_entry("desc", "الوصف", initial=item.get("desc", ""))
        self.add_entry(
            "qty", "الكمية",
            initial=format_money(item["qty"], symbol=False),
        )
        self.add_entry(
            "price", "سعر الشراء",
            initial=format_money(item["price"], symbol=False),
        )

        self.finish_layout()
        self._fields["name"][1].focus_set()

    def save(self):
        name = self.value("name")

        if not name:
            raise ValueError("اسم الصنف مطلوب")

        qty = parse_number(self.value("qty"), "الكمية", positive=True)
        price = parse_number(self.value("price"), "السعر")

        return {
            "name": name,
            "barcode": self.value("barcode"),
            "desc": self.value("desc"),
            "qty": qty,
            "price": price,
            "total": round_money(qty * price),
        }


# =====================================================
# صفحة أمر الشراء
# =====================================================
class PurchaseOrderFormPage(ctk.CTkFrame):

    def __init__(self, parent, app, po_id=None, supplier_id=None):
        super().__init__(parent)

        self.app = app
        self.items = []

        self.po = get_purchase_order(po_id) if po_id else None
        self.edit_mode = self.po is not None
        self.po_id = self.po["id"] if self.po else None
        self.pending_barcode = ""      # باركود جديد بانتظار اسم الصنف

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.discount_var = ctk.StringVar(value="0")
        self.tax_var = ctk.StringVar(value="0")
        self.paid_var = ctk.StringVar(value="")
        self.supplier_var = ctk.StringVar()
        self.method_var = ctk.StringVar(value=PAYMENT_METHODS["cash"])

        self._build_header()
        self._build_body()
        self._build_actions()

        if self.edit_mode:
            self._load_existing()
        elif supplier_id:
            self._preselect_supplier(supplier_id)

        self.discount_var.trace_add("write", lambda *a: self._refresh_summary())
        self.tax_var.trace_add("write", lambda *a: self._refresh_summary())
        self.paid_var.trace_add("write", lambda *a: self._refresh_summary())

        self.after_idle(self._refresh_summary)

    # ======================
    # بناء الواجهة
    # ======================
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))

        title = (
            f"✏ تعديل أمر الشراء {self.po['po_number']}"
            if self.edit_mode else "🛒 أمر شراء جديد"
        )

        ctk.CTkLabel(
            header, text=title,
            font=("Cairo", 26, "bold"), text_color="#111827",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="تسجيل مشتريات من مورد: الأصناف، الخصم والضريبة، والمبلغ المدفوع",
            font=("Cairo", 14), text_color="#6b7280",
        ).pack(anchor="w")

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew")

        self._build_supplier_card(left)
        self._build_info_card(left)
        self._build_item_form(left)
        self._build_settings_card(left)
        self._build_payment_card(left)
        self._build_items_table(right)

    # ---- المورد ----
    def _build_supplier_card(self, parent):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(
            card, text="🏭 المورد", font=("Cairo", 14, "bold")
        ).pack(anchor="w", padx=10, pady=(8, 0))

        self.supplier_picker = SupplierPicker(
            card,
            textvariable=self.supplier_var,
            on_change=self._on_supplier_changed,
            on_add_new=self._open_add_supplier,
            width=300,
            height=40,
        )
        self.supplier_picker.set_clients(get_suppliers_full())
        self.supplier_picker.pack(padx=10, pady=5, fill="x")

        self.supplier_balance_label = ctk.CTkLabel(
            card, text="", font=("Cairo", 12, "bold"), text_color="#6b7280"
        )
        self.supplier_balance_label.pack(padx=10)

        ctk.CTkButton(
            card, text="➕ مورد جديد",
            command=self._open_add_supplier, **PRIMARY_BTN,
        ).pack(pady=8)

    # ---- أرقام وتاريخ ----
    def _build_info_card(self, parent):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=10, pady=6)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="📄 بيانات أمر الشراء", font=("Cairo", 14, "bold")
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        number_text = (
            self.po["po_number"] if self.edit_mode
            else f"{preview_po_number()}  (تلقائي)"
        )

        ctk.CTkLabel(
            card, text=f"رقم أمر الشراء:  {number_text}",
            font=("Cairo", 13, "bold"), text_color=BRAND_NAVY,
        ).grid(row=1, column=0, sticky="w", padx=10, pady=2)

        ctk.CTkLabel(
            card, text="رقم فاتورة المورد", font=("Cairo", 12),
            text_color="#374151",
        ).grid(row=2, column=0, sticky="w", padx=10, pady=(6, 0))

        self.invoice_no_entry = ctk.CTkEntry(
            card, placeholder_text="رقم فاتورة المورد", **ENTRY_STYLE
        )
        self.invoice_no_entry.grid(
            row=3, column=0, sticky="ew", padx=10, pady=(0, 4)
        )

        if not self.edit_mode:
            self.invoice_no_entry.insert(0, next_supplier_invoice_number())

        ctk.CTkLabel(
            card, text="التاريخ (YYYY-MM-DD)", font=("Cairo", 12),
            text_color="#374151",
        ).grid(row=4, column=0, sticky="w", padx=10, pady=(6, 0))

        self.date_entry = ctk.CTkEntry(card, **ENTRY_STYLE)
        self.date_entry.grid(
            row=5, column=0, sticky="ew", padx=10, pady=(0, 10)
        )
        self.date_entry.insert(0, _date.today().isoformat())

    # ---- إدخال صنف ----
    def _build_item_form(self, parent):
        form = ctk.CTkFrame(parent)
        form.pack(fill="x", padx=10, pady=6)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self.barcode_entry = ctk.CTkEntry(
            form, placeholder_text="🔎 الباركود (قارئ USB ثم Enter)",
            **ENTRY_STYLE,
        )
        self.barcode_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.barcode_entry.bind("<Return>", self._on_barcode_enter)
        self.barcode_entry.bind("<KP_Enter>", self._on_barcode_enter)

        ctk.CTkButton(
            form, text="📷 مسح بالكاميرا", command=self.scan_with_camera,
            **_SECONDARY_BTN,
        ).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.scan_status = ctk.CTkLabel(
            form, text="", font=("Cairo", 12, "bold"), text_color="#0f2a5c",
            wraplength=300, justify="right",
        )
        self.scan_status.grid(
            row=1, column=0, columnspan=2, padx=8, pady=(0, 2), sticky="ew"
        )

        self.item_name = ctk.CTkEntry(
            form, placeholder_text="اسم الصنف", **ENTRY_STYLE
        )
        self.item_name.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

        self.item_desc = ctk.CTkEntry(
            form, placeholder_text="الوصف", **ENTRY_STYLE
        )
        self.item_desc.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.qty = ctk.CTkEntry(
            form, placeholder_text="الكمية", **ENTRY_STYLE
        )
        self.qty.grid(row=3, column=0, padx=5, pady=5, sticky="ew")

        self.price = ctk.CTkEntry(
            form, placeholder_text="سعر الشراء", **ENTRY_STYLE
        )
        self.price.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        entries = (self.item_name, self.item_desc, self.qty, self.price)

        for index, entry in enumerate(entries):
            entry.bind("<Return>", lambda e, i=index: self._on_item_enter(i))
            entry.bind("<KP_Enter>", lambda e, i=index: self._on_item_enter(i))

        self._item_entries = entries

        ctk.CTkButton(
            form, text="➕ إضافة صنف", command=self.add_item, **PRIMARY_BTN
        ).grid(row=4, column=0, columnspan=2, pady=12)

    # ---- الخصم والضريبة والملاحظات ----
    def _build_settings_card(self, parent):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=10, pady=6)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="💰 الخصم والضريبة والملاحظات",
            font=("Cairo", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))

        ctk.CTkEntry(
            card, textvariable=self.discount_var,
            placeholder_text="الخصم %", **ENTRY_STYLE,
        ).grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        ctk.CTkEntry(
            card, textvariable=self.tax_var,
            placeholder_text="الضريبة %", **ENTRY_STYLE,
        ).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.notes_entry = ctk.CTkEntry(
            card, placeholder_text="📝 ملاحظات أمر الشراء - اختياري",
            **ENTRY_STYLE,
        )
        self.notes_entry.grid(
            row=2, column=0, columnspan=2, padx=5, pady=(5, 10), sticky="ew"
        )

    # ---- الدفعة ----
    def _build_payment_card(self, parent):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", padx=10, pady=(6, 14))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="💸 الدفع", font=("Cairo", 14, "bold")
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        if self.edit_mode:
            ctk.CTkLabel(
                card,
                text=(
                    f"المدفوع حتى الآن:  {format_money(self.po['paid'])}\n"
                    "لتسجيل دفعة جديدة استخدم «سند صرف» من قائمة أوامر الشراء."
                ),
                font=("Cairo", 12), text_color="#374151", justify="right",
                wraplength=300,
            ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
            return

        ctk.CTkEntry(
            card, textvariable=self.paid_var,
            placeholder_text="المبلغ المدفوع الآن (اختياري)", **ENTRY_STYLE,
        ).grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkOptionMenu(
            card, values=list(PAYMENT_METHODS.values()),
            variable=self.method_var, height=38,
            font=("Cairo", 13), dropdown_font=("Cairo", 13),
        ).grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.reference_entry = ctk.CTkEntry(
            card, placeholder_text="رقم الشيك / المرجع (اختياري)",
            **ENTRY_STYLE,
        )
        self.reference_entry.grid(
            row=3, column=0, padx=10, pady=(5, 10), sticky="ew"
        )

    # ---- جدول الأصناف ----
    def _build_items_table(self, parent):
        ctk.CTkLabel(
            parent, text="📋 الأصناف المضافة", font=("Cairo", 18, "bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(
            toolbar, text="Double Click أو F2 للتعديل",
            font=("Cairo", 12), text_color="#6b7280",
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            toolbar, text="✏️ تعديل", width=85, height=32, corner_radius=8,
            font=("Cairo", 12, "bold"), fg_color="#2563eb",
            hover_color="#1d4ed8", command=self.edit_selected_item,
        ).pack(side="right", padx=3)

        ctk.CTkButton(
            toolbar, text="🗑 حذف", width=85, height=32, corner_radius=8,
            font=("Cairo", 12, "bold"), fg_color="#dc2626",
            hover_color="#b91c1c", command=self.delete_selected_items,
        ).pack(side="right", padx=3)

        # ---- الإجماليات (أسفل اللوحة) ----
        totals = ctk.CTkFrame(parent, fg_color="transparent")
        totals.pack(side="bottom", fill="x", padx=10, pady=(5, 10))

        for column in range(6):
            totals.grid_columnconfigure(column, weight=1)

        def make_label(column, text, size=13, color=None):
            label = ctk.CTkLabel(
                totals, text=text, font=("Cairo", size, "bold"),
                **({"text_color": color} if color else {}),
            )
            label.grid(row=0, column=column, padx=4, pady=5, sticky="ew")
            return label

        self.subtotal_label = make_label(0, "المجموع: 0.00 ₪")
        self.discount_label = make_label(1, "الخصم: 0.00 ₪")
        self.tax_label = make_label(2, "الضريبة: 0.00 ₪")
        self.total_label = make_label(3, "الإجمالي: 0.00 ₪", 15, "#2563eb")
        self.paid_label = make_label(4, "المدفوع: 0.00 ₪", 13, "#15803d")
        self.remaining_label = make_label(
            5, "المتبقي: 0.00 ₪", 15, "#b91c1c"
        )

        # ---- شريط معلومات ----
        footer = ctk.CTkFrame(
            parent, fg_color=BRAND_LIGHT, corner_radius=8, height=34
        )
        footer.pack(side="bottom", fill="x", padx=10, pady=(0, 6))

        self.items_footer_label = ctk.CTkLabel(
            footer, text="عدد الأصناف: 0   |   مجموع الكميات: 0",
            font=("Cairo", 13, "bold"), text_color=BRAND_NAVY,
        )
        self.items_footer_label.pack(side="right", padx=15, pady=4)

        # ---- الجدول ----
        setup_table_style(self)

        container = ctk.CTkFrame(parent)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.items_table = ttk.Treeview(
            container,
            style=STYLE_NAME,
            columns=("name", "barcode", "desc", "qty", "price", "total", "no"),
            displaycolumns=rtl_columns(
                "no", "name", "barcode", "desc", "qty", "price", "total"
            ),
            show="headings",
            height=10,
            selectmode="extended",
        )
        configure_zebra(self.items_table)
        self.items_table.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            container, orient="vertical",
            style="Invoice.Vertical.TScrollbar",
            command=self.items_table.yview,
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.items_table.configure(yscrollcommand=scroll.set)

        for column_id, title, width, anchor, stretch in (
            ("no", "#", 50, "center", False),
            ("name", "الصنف", 170, "e", True),
            ("barcode", "الباركود", 120, "center", False),
            ("desc", "الوصف", 170, "e", True),
            ("qty", "الكمية", 85, "center", False),
            ("price", "سعر الشراء", 110, "e", False),
            ("total", "الإجمالي", 130, "e", False),
        ):
            self.items_table.heading(
                column_id, text=title,
                anchor=anchor if anchor != "e" else "center",
            )
            self.items_table.column(
                column_id, width=width, minwidth=50,
                anchor=anchor, stretch=stretch,
            )

        self.items_table.bind("<Double-1>", self._on_item_double_click)
        self.items_table.bind("<F2>", lambda e: self.edit_selected_item())
        self.items_table.bind("<Delete>", lambda e: self.delete_selected_items())

    # ---- الشريط السفلي ----
    def _build_actions(self):
        bar = ctk.CTkFrame(
            self, fg_color="#ffffff", corner_radius=0,
            border_width=1, border_color="#e5e7eb", height=76,
        )
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(side="right", padx=15, pady=15)

        self.save_btn = ctk.CTkButton(
            inner,
            text="💾 حفظ التعديلات" if self.edit_mode else "💾 حفظ أمر الشراء",
            width=175, command=self.save_order, **PRIMARY_BTN,
        )
        self.save_btn.pack(side="right", padx=5)

        ctk.CTkButton(
            inner, text="👁️ معاينة", width=135,
            command=self.preview_order, **_SECONDARY_BTN,
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            inner, text="🖨️ طباعة", width=135,
            command=lambda: self.preview_order(print_it=True),
            **_SECONDARY_BTN,
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            inner, text="⬅ رجوع للقائمة", width=150, height=45,
            corner_radius=10, font=("Cairo", 14, "bold"),
            fg_color="#6b7280", hover_color="#4b5563",
            command=self.go_back,
        ).pack(side="left", padx=5)

    # ======================
    # تحميل أمر موجود / مورد مبدئي
    # ======================
    def _load_existing(self):
        po = self.po

        self.supplier_var.set(po["supplier"])

        self.invoice_no_entry.delete(0, "end")
        self.invoice_no_entry.insert(0, po["supplier_invoice_no"])

        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, po["date"])

        self.discount_var.set(f"{po['discount_percent']:g}")
        self.tax_var.set(f"{po['tax_percent']:g}")

        self.notes_entry.insert(0, po["notes"])

        self.items = get_purchase_order_items(self.po_id)
        self.refresh_items()

    def _preselect_supplier(self, supplier_id):
        for supplier in get_suppliers_full():
            if supplier["id"] == supplier_id:
                self.supplier_var.set(supplier["name"])
                break

    # ======================
    # المورد
    # ======================
    def _on_supplier_changed(self, supplier):
        if not supplier:
            self.supplier_balance_label.configure(text="")
            return

        state = supplier.get("balance_state")
        balance = supplier.get("balance") or 0

        if state in ("debit", "credit") and balance:
            self.supplier_balance_label.configure(
                text=(
                    f"{SUPPLIER_BALANCE_LABELS[state]}: "
                    f"{format_money(abs(balance))}"
                ),
                text_color="#b91c1c" if state == "debit" else "#15803d",
            )
        else:
            self.supplier_balance_label.configure(
                text=SUPPLIER_BALANCE_LABELS["zero"], text_color="#6b7280"
            )

    def _open_add_supplier(self, name=""):
        SupplierFormDialog(
            self, on_done=self._after_supplier_added, name=name
        )

    def _after_supplier_added(self, supplier_id):
        suppliers = get_suppliers_full()
        self.supplier_picker.set_clients(suppliers)

        for supplier in suppliers:
            if supplier["id"] == supplier_id:
                self.supplier_var.set(supplier["name"])
                break

    # ======================
    # الأصناف
    # ======================
    def _on_item_enter(self, index):
        if index < len(self._item_entries) - 1:
            self._item_entries[index + 1].focus_set()
        else:
            self.add_item()

    def add_item(self):
        name = self.item_name.get().strip()

        if not name:
            messagebox.showwarning("تنبيه", "يرجى إدخال اسم الصنف", parent=self)
            self.item_name.focus_set()
            return

        try:
            qty = parse_number(self.qty.get(), "الكمية", positive=True)
            price = parse_number(self.price.get(), "سعر الشراء")
        except NumberParseError as error:
            messagebox.showerror("خطأ", str(error), parent=self)
            return

        self.items.append({
            "name": name,
            "barcode": self.pending_barcode or self.barcode_entry.get().strip(),
            "desc": self.item_desc.get().strip(),
            "qty": qty,
            "price": price,
            "total": round_money(qty * price),
        })

        for entry in self._item_entries:
            entry.delete(0, "end")

        self.barcode_entry.delete(0, "end")
        self.pending_barcode = ""
        self._set_scan_status("")

        self.item_name.focus_set()
        self.refresh_items()

    # ======================
    # الباركود
    # ======================
    def _set_scan_status(self, text, ok=True):
        self.scan_status.configure(
            text=text, text_color="#15803d" if ok else "#b91c1c"
        )

    def _on_barcode_enter(self, _event=None):
        code = self.barcode_entry.get().strip()
        self.barcode_entry.delete(0, "end")

        if code:
            self.handle_barcode(code)

        return "break"

    def scan_with_camera(self):
        open_barcode_scanner(self, self.handle_barcode, continuous=True)

    def handle_barcode(self, code):
        """
        يعالج باركوداً (من القارئ أو الكاميرا) ويرجع رسالة الحالة:
          - صنف موجود في الأمر → كميته + 1
          - صنف معروف سابقاً   → يُضاف بكمية 1 وآخر سعر شراء
          - باركود جديد        → يُنتظر اسم الصنف وسعره ثم «إضافة صنف»
        """
        code = str(code or "").strip()

        if not code:
            return ""

        for item in self.items:
            if item.get("barcode") == code:
                item["qty"] = float(item["qty"]) + 1
                item["total"] = round_money(item["qty"] * item["price"])
                self.refresh_items()

                message = (
                    f"✔ {item['name']} — الكمية "
                    f"{format_money(item['qty'], symbol=False)}"
                )
                self._set_scan_status(message)
                return message

        product = get_product_by_barcode(code)

        if product:
            price = float(product["price"] or 0)

            self.items.append({
                "name": product["name"],
                "barcode": code,
                "desc": product["desc"],
                "qty": 1.0,
                "price": price,
                "total": round_money(price),
            })
            self.refresh_items()

            message = f"✔ أُضيف: {product['name']} — {format_money(price)}"
            self._set_scan_status(message)
            return message

        # باركود جديد: ينتظر المستخدم لإكمال البيانات
        self.pending_barcode = code
        self.barcode_entry.delete(0, "end")
        self.barcode_entry.insert(0, code)
        self.item_name.focus_set()

        message = f"🆕 باركود جديد {code} — أدخل اسم الصنف وسعره ثم «إضافة صنف»"
        self._set_scan_status(message, ok=True)
        return message

    def refresh_items(self):
        for row in self.items_table.get_children():
            self.items_table.delete(row)

        for index, item in enumerate(self.items):
            self.items_table.insert(
                "", "end", iid=str(index),
                values=(
                    item["name"],
                    item.get("barcode", ""),
                    item.get("desc", ""),
                    format_money(item["qty"], symbol=False),
                    format_money(item["price"], symbol=False),
                    format_money(item["total"], symbol=False),
                    index + 1,
                ),
                tags=(zebra_tag(index),),
            )

        total_qty = sum(float(item["qty"]) for item in self.items)
        qty_text = (
            str(int(total_qty)) if total_qty.is_integer() else f"{total_qty:g}"
        )
        self.items_footer_label.configure(
            text=f"عدد الأصناف: {len(self.items)}   |   مجموع الكميات: {qty_text}"
        )

        self._refresh_summary()

    def _selected_indexes(self):
        return sorted(int(iid) for iid in self.items_table.selection())

    def _on_item_double_click(self, event):
        row = self.items_table.identify_row(event.y)

        if row:
            self.items_table.selection_set(row)
            self.edit_selected_item()

    def edit_selected_item(self):
        indexes = self._selected_indexes()

        if len(indexes) != 1:
            messagebox.showwarning(
                "تنبيه", "يرجى اختيار صنف واحد للتعديل", parent=self
            )
            return

        index = indexes[0]

        def done(updated):
            self.items[index] = updated
            self.refresh_items()

        PurchaseItemDialog(self, self.items[index], done)

    def delete_selected_items(self):
        indexes = self._selected_indexes()

        if not indexes:
            messagebox.showwarning(
                "تنبيه", "يرجى اختيار صنف للحذف", parent=self
            )
            return

        if not messagebox.askyesno(
            "تأكيد الحذف", f"هل تريد حذف {len(indexes)} صنف؟", parent=self
        ):
            return

        for index in reversed(indexes):
            del self.items[index]

        self.refresh_items()

    # ======================
    # الملخص
    # ======================
    def _summary(self, show_errors=False):
        try:
            return calculate_invoice_totals(
                self.items,
                self.discount_var.get().strip() or "0",
                self.tax_var.get().strip() or "0",
            )
        except NumberParseError as error:
            if show_errors:
                messagebox.showerror("خطأ", str(error), parent=self)

            return None

    def _paid_amount(self, show_errors=False):
        """المدفوع: من الأمر المحفوظ عند التعديل، أو من الحقل عند الإنشاء."""
        if self.edit_mode:
            return self.po["paid"]

        text = self.paid_var.get().strip()

        if not text:
            return 0.0

        try:
            return parse_number(text, "المبلغ المدفوع")
        except NumberParseError as error:
            if show_errors:
                messagebox.showerror("خطأ", str(error), parent=self)
                return None

            return 0.0

    def _refresh_summary(self):
        summary = self._summary()

        if summary is None:
            return

        paid = self._paid_amount()
        remaining = max(round_money(summary["total"] - paid), 0.0)

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
        self.paid_label.configure(text=f"المدفوع: {format_money(paid)}")
        self.remaining_label.configure(
            text=f"المتبقي: {format_money(remaining)}"
        )

    # ======================
    # الحفظ والمعاينة
    # ======================
    def _read_date(self):
        text = self.date_entry.get().strip()

        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                "صيغة التاريخ غير صحيحة. استخدم YYYY-MM-DD مثل 2026-10-29"
            ) from None

        return text

    def save_order(self):
        if not self.items:
            messagebox.showwarning(
                "تنبيه", "لا توجد أصناف في أمر الشراء", parent=self
            )
            return

        supplier_id = self.supplier_picker.client_id()

        if not supplier_id:
            messagebox.showerror(
                "خطأ", "يرجى اختيار مورد صحيح من القائمة", parent=self
            )
            return

        summary = self._summary(show_errors=True)

        if summary is None:
            return

        paid_now = self._paid_amount(show_errors=True)

        if paid_now is None:
            return

        try:
            order_date = self._read_date()
            common = dict(
                supplier_invoice_no=self.invoice_no_entry.get().strip(),
                tax_percent=summary["tax_percent"],
                discount_percent=summary["discount_percent"],
                notes=self.notes_entry.get().strip(),
            )

            if self.edit_mode:
                update_purchase_order(
                    self.po_id, supplier_id, order_date, self.items, **common
                )
                message = "تم حفظ تعديلات أمر الشراء بنجاح"
            else:
                po_id, voucher_id = save_purchase_order(
                    supplier_id, order_date, self.items,
                    paid_now=paid_now,
                    payment_method=_METHOD_BY_LABEL.get(
                        self.method_var.get(), "cash"
                    ),
                    reference=self.reference_entry.get().strip(),
                    **common,
                )
                message = "تم حفظ أمر الشراء بنجاح"

                if voucher_id:
                    message += "\nوتم إصدار سند صرف بالمبلغ المدفوع."

        except ValueError as error:
            messagebox.showerror("خطأ", str(error), parent=self)
            return

        except Exception as error:
            messagebox.showerror(
                "خطأ", f"حدث خطأ غير متوقع:\n{error}", parent=self
            )
            return

        messagebox.showinfo("تم", message, parent=self)
        self.go_back()

    def _temp_pdf(self):
        if not self.items:
            messagebox.showwarning("تنبيه", "لا توجد أصناف", parent=self)
            return None

        summary = self._summary(show_errors=True)

        if summary is None:
            return None

        paid = self._paid_amount(show_errors=True)

        if paid is None:
            return None

        try:
            order_date = self._read_date()
        except ValueError as error:
            messagebox.showerror("خطأ", str(error), parent=self)
            return None

        supplier = self.supplier_picker.client() or {
            "name": self.supplier_var.get().strip()
        }

        try:
            return generate_temp_purchase_pdf(
                supplier,
                self.items,
                summary,
                notes=self.notes_entry.get().strip(),
                invoice_no=self.invoice_no_entry.get().strip(),
                date=order_date,
                paid=paid,
            )
        except Exception as error:
            messagebox.showerror(
                "خطأ", f"تعذّر إنشاء PDF:\n{error}", parent=self
            )
            return None

    def preview_order(self, print_it=False):
        path = self._temp_pdf()

        if not path:
            return

        if print_it:
            try:
                open_file(path, print_it=True)
            except Exception as error:
                messagebox.showerror(
                    "خطأ", f"تعذّرت الطباعة:\n{error}", parent=self
                )
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة أمر الشراء",
            share_message="مرحباً، مرفق أمر الشراء، يرجى إرفاق ملف PDF "
                          "المرفق وإرساله.",
            email_subject="أمر شراء",
            email_body="مرفق لكم أمر الشراء.",
        )

    def go_back(self):
        self.app.show_purchases("orders")
