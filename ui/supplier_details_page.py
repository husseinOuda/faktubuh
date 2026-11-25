# ui/supplier_details_page.py
"""
حساب المورد (0.1.9) — بنفس أسلوب صفحة تفاصيل العميل:

  رأس الصفحة: الاسم وبيانات التواصل + أزرار سريعة (أمر شراء، سند صرف،
              استلام بضاعة، تعديل).
  بطاقات: عدد الأوامر · إجمالي المشتريات · المدفوع · المتبقي على الأوامر ·
          دفعات مقدّمة · رصيد المورد.

  التبويبات:
    📒 كشف الحساب      أوامر الشراء وسندات الصرف مرتّبة زمنياً برصيد تراكمي
                       + معاينة/طباعة PDF + تصدير Excel
    🛒 أوامر المورد    أوامره (معاينة، تعديل، سند صرف، استلام، إلغاء ...)
    📦 الاستلامات      مستندات استلام بضاعته
    🏭 بيانات المورد   الهاتف والبريد والعنوان والملاحظات

  رصيد المورد: موجب = مستحق للمورد علينا · سالب = دفعة مقدّمة لنا.
"""

from tkinter import messagebox

import customtkinter as ctk

from database import get_payment_voucher, get_voucher_expense_summary
from purchases_db import (
    SUPPLIER_BALANCE_LABELS,
    get_receivable_orders,
    get_supplier,
    get_supplier_statement,
)
from ui.client_details_page import (
    _GREEN,
    _GREY,
    _NAVY,
    _PURPLE,
    _RED,
    _STATE_COLORS,
    _StatementTab,
)
from ui.components.buttons import make_button
from ui.components.cards import StatCard
from ui.components.goods_receipt_dialogs import ReceiveGoodsDialog
from ui.components.invoice_utils import format_money
from ui.components.pdf_preview import PDFPreviewWindow
from ui.components.supplier_dialogs import (
    SupplierFormDialog,
    SupplierPaymentDialog,
)
from ui.goods_receipts_page import GoodsReceiptsPage
from ui.purchase_orders_page import PurchaseOrdersPage, build_po_pdf
from voucher_pdf import generate_payment_voucher_pdf


def _signed_text(amount, state=None):
    """«150.00 ₪ مستحق للمورد» / «20.00 ₪ دفعة مقدّمة» / «مسدّد»."""
    if state is None:
        state = (
            "debit" if amount > 0.005
            else "credit" if amount < -0.005 else "zero"
        )

    if state == "zero":
        return SUPPLIER_BALANCE_LABELS["zero"]

    return f"{format_money(abs(amount))} {SUPPLIER_BALANCE_LABELS[state]}"


# =====================================================
# تبويب: كشف حساب المورد
# =====================================================
class _SupplierStatementTab(_StatementTab):

    COLUMNS = [
        ("date", "التاريخ", 95, "center"),
        ("kind", "النوع", 85, "center"),
        ("ref", "المستند", 130, "center"),
        ("description", "البيان", 250, "e"),
        ("debit", "مشتريات", 105, "e"),
        ("credit", "مدفوعات", 105, "e"),
        ("balance", "الرصيد", 140, "e"),
    ]

    KIND_TEXT = {"purchase": "أمر شراء", "payment": "سند صرف"}

    CARDS = [
        ("opening", "↩ الرصيد الافتتاحي", _NAVY),
        ("debit", "🛒 إجمالي المشتريات", _RED),
        ("credit", "💸 إجمالي المدفوعات", _GREEN),
        ("closing", "📒 الرصيد الختامي", _NAVY),
    ]

    def _fetch_statement(self, start, end, include_cancelled):
        return get_supplier_statement(
            self.client_id, start, end, include_cancelled=include_cancelled
        )

    def signed_text(self, amount, state=None):
        return _signed_text(amount, state)

    def open_document(self, iid):
        entry = self.entries.get(str(iid))

        if not entry:
            return

        try:
            if entry["purchase_order_id"]:
                PDFPreviewWindow(
                    self, build_po_pdf(entry["purchase_order_id"]),
                    title="معاينة أمر الشراء",
                )

            elif entry["voucher_id"]:
                PDFPreviewWindow(
                    self,
                    generate_payment_voucher_pdf(
                        get_payment_voucher(entry["voucher_id"]),
                        get_voucher_expense_summary(entry["voucher_id"]),
                    ),
                    title="معاينة سند الصرف",
                )

        except Exception as error:
            messagebox.showerror(
                "خطأ", f"تعذّر فتح المستند:\n{error}", parent=self
            )


# =====================================================
# تبويبا الأوامر والاستلامات (مفلتران على المورد)
# =====================================================
class _SupplierOrdersTab(PurchaseOrdersPage):

    EXPORT_NAME = "supplier_orders"

    def __init__(self, parent, app, supplier_id, on_changed):
        self.supplier_id = supplier_id
        self.on_data_changed = on_changed

        super().__init__(parent, app)

    def fetch_records(self):
        return [
            r for r in super().fetch_records()
            if r["supplier_id"] == self.supplier_id
        ]

    def new_order(self):
        self.app.show_purchase_order_form(supplier_id=self.supplier_id)


class _SupplierReceiptsTab(GoodsReceiptsPage):

    EXPORT_NAME = "supplier_receipts"

    def __init__(self, parent, app, supplier_id, on_changed):
        self.supplier_id = supplier_id
        self.on_data_changed = on_changed

        super().__init__(parent, app)

    def fetch_records(self):
        return [
            r for r in super().fetch_records()
            if r["supplier_id"] == self.supplier_id
        ]

    def _dialog_defaults(self):
        return {"supplier_id": self.supplier_id}


# =====================================================
# تبويب: بيانات المورد
# =====================================================
class _InfoTab(ctk.CTkFrame):

    def __init__(self, parent, page):
        super().__init__(parent, fg_color="transparent")

        supplier = page.supplier
        self.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            self, fg_color="white", corner_radius=12,
            border_width=1, border_color="#e5e7eb",
        )
        card.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        card.grid_columnconfigure(0, weight=1)

        fields = [
            ("📞 الهاتف", supplier["phone"]),
            ("✉ البريد الإلكتروني", supplier["email"]),
            ("📍 العنوان", supplier["address"]),
            ("🛒 آخر عملية شراء", supplier["last_purchase_date"]),
            ("💸 آخر دفعة", supplier["last_payment_date"]),
        ]

        for row, (label, value) in enumerate(fields):
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.grid(
                row=row, column=0, sticky="ew", padx=16,
                pady=(10 if row == 0 else 2, 2),
            )
            line.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                line, text=label, font=("Cairo", 13, "bold"),
                text_color="#374151", width=170, anchor="w",
            ).grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(
                line, text=value or "—", font=("Cairo", 14),
                text_color="#111827" if value else _GREY, anchor="w",
            ).grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            card, text="📝 ملاحظات", font=("Cairo", 13, "bold"),
            text_color="#374151", anchor="w",
        ).grid(row=len(fields), column=0, sticky="w", padx=16, pady=(12, 2))

        notes = ctk.CTkTextbox(
            card, height=130, font=("Cairo", 13),
            corner_radius=10, border_width=1, border_color="#d1d5db",
        )
        notes.grid(
            row=len(fields) + 1, column=0, sticky="ew", padx=16, pady=(0, 12)
        )
        notes.insert("1.0", supplier["notes"] or "")
        notes.configure(state="disabled")

        make_button(
            card, "✏ تعديل البيانات والملاحظات", page.edit_supplier, "orange",
            width=240,
        ).grid(row=len(fields) + 2, column=0, sticky="w", padx=16, pady=(0, 16))


# =====================================================
# صفحة حساب المورد
# =====================================================
class SupplierAccountPage(ctk.CTkFrame):

    TABS = [
        ("statement", "📒 كشف الحساب"),
        ("orders", "🛒 أوامر المورد"),
        ("receipts", "📦 الاستلامات"),
        ("info", "🏭 بيانات المورد"),
    ]

    def __init__(self, parent, app, supplier_id, tab="statement"):
        super().__init__(parent)

        self.app = app
        self.supplier_id = supplier_id
        self.supplier = get_supplier(supplier_id)
        self.current_key = None
        self.cards = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        if not self.supplier:
            ctk.CTkLabel(
                self, text="تعذّر العثور على المورد (ربما حُذف).",
                font=("Cairo", 16),
            ).grid(row=0, column=0, pady=40)
            make_button(
                self, "← العودة للموردين",
                lambda: app.show_purchases("suppliers"), "gray",
            ).grid(row=1, column=0)
            return

        self._build_header()
        self._build_cards()
        self._build_tabs()

        labels = dict(self.TABS)
        self.show_tab(tab if tab in labels else "statement")

    # ---- الرأس ----
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 4))
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            header, text="", font=("Cairo", 24, "bold"), text_color="#111827",
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.contact_label = ctk.CTkLabel(
            header, text="", font=("Cairo", 13), text_color="#6b7280",
        )
        self.contact_label.grid(row=1, column=0, sticky="w")

        buttons = ctk.CTkFrame(header, fg_color="transparent")
        buttons.grid(row=0, column=1, rowspan=2, sticky="e")

        for column, (text, command, color) in enumerate([
            ("← الموردون", lambda: self.app.show_purchases("suppliers"), "gray"),
            ("✏ تعديل", self.edit_supplier, "orange"),
            ("🛒 أمر شراء", self.new_order, "blue"),
            ("💸 سند صرف", self.new_payment, "green"),
            ("📦 استلام", self.receive_goods, "green"),
        ]):
            make_button(buttons, text, command, color, width=120).grid(
                row=0, column=column, padx=4)

    def _build_cards(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(4, 6))

        for index, (key, title, color) in enumerate([
            ("count", "🛒 عدد الأوامر", "#2563eb"),
            ("purchases", "🧾 إجمالي المشتريات", _NAVY),
            ("paid", "💸 المدفوع", _GREEN),
            ("remaining", "📌 المتبقي على الأوامر", _RED),
            ("advance", "📥 دفعات مقدّمة", _PURPLE),
            ("balance", "📒 رصيد المورد", _NAVY),
        ]):
            frame.grid_columnconfigure(index, weight=1, uniform="sdcards")
            card = StatCard(frame, title, "0.00", color)
            card.grid(row=0, column=index, padx=4, sticky="ew")
            self.cards[key] = card

        self.refresh_summary(reload=False)

    def _build_tabs(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 0))
        bar.grid_columnconfigure(0, weight=1)

        self.tab_var = ctk.StringVar()

        ctk.CTkSegmentedButton(
            bar,
            values=[label for _key, label in self.TABS],
            variable=self.tab_var,
            command=self._on_tab_clicked,
            height=38,
            font=("Cairo", 14, "bold"),
        ).grid(row=0, column=0, sticky="ew")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=3, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    # ---- الملخص ----
    def refresh_summary(self, reload=True):
        if reload:
            fresh = get_supplier(self.supplier_id)

            if fresh:
                self.supplier = fresh

        s = self.supplier
        state = s["balance_state"]

        self.title_label.configure(text=f"🏭 {s['name']}")

        contact = "  ·  ".join(
            part for part in (
                f"📞 {s['phone']}" if s["phone"] else "",
                f"✉ {s['email']}" if s["email"] else "",
                f"📍 {s['address']}" if s["address"] else "",
            ) if part
        )
        self.contact_label.configure(text=contact or "لا توجد بيانات تواصل")

        self.cards["count"].set(
            str(s["orders_count"]), f"{s['cancelled_count']} ملغى"
        )
        self.cards["purchases"].set(format_money(s["purchases"]))
        self.cards["paid"].set(format_money(s["paid"]))
        self.cards["remaining"].set(format_money(s["remaining"]))
        self.cards["advance"].set(format_money(s["advance"]))
        self.cards["balance"].set(
            _signed_text(s["balance"], state),
            {"debit": "مستحق للمورد علينا",
             "credit": "دفعة مقدّمة لدى المورد",
             "zero": "لا توجد مبالغ مستحقة"}[state],
            color=_STATE_COLORS[state],
        )

    # ---- التبويبات ----
    def _on_tab_clicked(self, label):
        for key, text in self.TABS:
            if text == label:
                self.show_tab(key)
                return

    def _build_tab(self, key):
        parent = self.content

        if key == "orders":
            return _SupplierOrdersTab(
                parent, self.app, self.supplier_id, self.refresh_summary
            )

        if key == "receipts":
            return _SupplierReceiptsTab(
                parent, self.app, self.supplier_id, self.refresh_summary
            )

        if key == "info":
            return _InfoTab(parent, self)

        return _SupplierStatementTab(parent, self.app, self.supplier_id)

    def show_tab(self, key):
        for widget in self.content.winfo_children():
            widget.destroy()

        self.current_key = key
        self.tab_var.set(dict(self.TABS)[key])

        tab = self._build_tab(key)
        tab.grid(row=0, column=0, sticky="nsew")

    # ---- الإجراءات ----
    def _refresh_all(self):
        self.refresh_summary()
        self.show_tab(self.current_key)

    def edit_supplier(self):
        SupplierFormDialog(
            self, on_done=lambda _id: self._refresh_all(),
            supplier=self.supplier,
        )

    def new_order(self):
        self.app.show_purchase_order_form(supplier_id=self.supplier_id)

    def new_payment(self):
        SupplierPaymentDialog(
            self, on_done=lambda _id: self._refresh_all(),
            supplier_id=self.supplier_id,
        )

    def receive_goods(self):
        if not get_receivable_orders(self.supplier_id):
            messagebox.showinfo(
                "لا توجد أوامر",
                "لا توجد أوامر شراء فعّالة لهذا المورد بانتظار الاستلام.",
                parent=self,
            )
            return

        ReceiveGoodsDialog(
            self, on_done=lambda _id: self._refresh_all(),
            supplier_id=self.supplier_id,
        )
