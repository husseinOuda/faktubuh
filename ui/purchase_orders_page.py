# ui/purchase_orders_page.py
"""
أوامر الشراء (تبويب «أوامر الشراء» في صفحة الموردون والمشتريات):

  جدول بأوامر الشراء: الرقم، رقم فاتورة المورد، التاريخ، المورد، الإجمالي،
  المدفوع، المتبقي، الحالة — مع بحث وفلتر فترة وفلتر حالة السداد،
  وإنشاء/تعديل (صفحة مثل الفاتورة)، معاينة PDF، طباعة، سند صرف، إلغاء،
  حذف، وتصدير Excel.
"""

from tkinter import messagebox

from database import VOUCHER_ACTIVE, VOUCHER_CANCELLED
from purchase_pdf import generate_purchase_order_pdf
from purchases_db import (
    PO_PAID,
    PO_PARTIAL,
    PO_UNPAID,
    delete_purchase_orders,
    get_purchase_order,
    get_purchase_order_items,
    get_purchase_orders,
    get_supplier,
    po_pay_status_label,
    receive_status_label,
    set_purchase_orders_status,
)
from ui.components.files import open_file
from ui.components.goods_receipt_dialogs import ReceiveGoodsDialog
from ui.components.invoice_utils import format_money
from ui.components.list_page import ListPageBase
from ui.components.pdf_preview import PDFPreviewWindow
from ui.components.supplier_dialogs import SupplierPaymentDialog

VIEW_CANCELLED = "cancelled"


def build_po_pdf(po_id):
    """يولّد PDF لأمر شراء محفوظ ويرجع مساره (يرفع ValueError إن لم يوجد)."""
    po = get_purchase_order(po_id)

    if not po:
        raise ValueError("تعذّر العثور على أمر الشراء")

    return generate_purchase_order_pdf(
        po,
        get_purchase_order_items(po_id),
        get_supplier(po["supplier_id"]),
    )


class PurchaseOrdersPage(ListPageBase):

    TITLE = ""      # العنوان تعرضه صفحة التبويبات
    SEARCH_HINT = (
        "🔍 ابحث برقم أمر الشراء أو رقم فاتورة المورد أو اسم المورد "
        "أو الملاحظات..."
    )

    COLUMNS = [
        ("number", "رقم أمر الشراء", 115, "center"),
        ("invoice_no", "فاتورة المورد", 95, "center"),
        ("date", "التاريخ", 95, "center"),
        ("supplier", "المورد", 180, "e"),
        ("total", "الإجمالي", 115, "e"),
        ("paid", "المدفوع", 110, "e"),
        ("remaining", "المتبقي", 110, "e"),
        ("status", "الحالة", 100, "center"),
        ("receive", "الاستلام", 105, "center"),
    ]

    STAT_CARDS = [
        ("total", "🛒 إجمالي المشتريات", "#0f2a5c"),
        ("paid", "💸 المدفوع", "#15803d"),
        ("remaining", "📌 المتبقي للموردين", "#b91c1c"),
        ("count", "🧾 عدد الأوامر الفعّالة", "#2563eb"),
        ("cancelled", "🚫 الأوامر الملغاة", "#6b7280"),
    ]

    FILTER_OPTIONS = [
        ("الكل", None),
        ("غير مسدد", PO_UNPAID),
        ("جزئي", PO_PARTIAL),
        ("مسدد", PO_PAID),
        ("ملغى", VIEW_CANCELLED),
    ]
    FILTER_FIELD = "view_status"

    TAG_COLORS = {
        "view_cancelled": "#9ca3af",
        "view_unpaid": "#c2410c",
        "view_partial": "#b45309",
        "view_paid": "#15803d",
    }

    EXPORT_NAME = "purchase_orders"
    EXPORT_HEADERS = [
        "رقم أمر الشراء", "رقم فاتورة المورد", "التاريخ", "المورد",
        "المجموع الفرعي", "الخصم", "الضريبة", "الإجمالي", "المدفوع",
        "المتبقي", "الحالة", "حالة الاستلام", "ملاحظات",
    ]

    # يُستدعى بعد أي تغيير (تستعمله صفحة حساب المورد لتحديث بطاقاتها)
    on_data_changed = None

    # ---- البيانات ----
    def fetch_records(self):
        records = get_purchase_orders()

        for r in records:
            r["view_status"] = (
                VIEW_CANCELLED if r["status"] == VOUCHER_CANCELLED
                else r["pay_status"]
            )

        return records

    def _status_text(self, r):
        if r["view_status"] == VIEW_CANCELLED:
            return "ملغى"

        return po_pay_status_label(r["pay_status"])

    def row_values(self, r):
        cancelled = r["view_status"] == VIEW_CANCELLED

        return {
            "number": r["po_number"],
            "invoice_no": r["supplier_invoice_no"] or "—",
            "date": r["date"],
            "supplier": r["supplier"],
            "total": format_money(r["total"]),
            "paid": format_money(r["paid"]),
            "remaining": "—" if cancelled else format_money(r["remaining"]),
            "status": self._status_text(r),
            "receive": (
                "—" if cancelled else receive_status_label(r["receive_status"])
            ),
        }

    def row_tags(self, r):
        return (f"view_{r['view_status']}",)

    def row_sort_values(self, r):
        return {
            "total": r["total"],
            "paid": r["paid"],
            "remaining": r["remaining"],
        }

    def search_blob(self, r):
        return " ".join(str(x) for x in (
            r["po_number"], r["supplier_invoice_no"], r["supplier"],
            r["notes"], r["date"],
        ))

    def export_row(self, r):
        return [
            r["po_number"], r["supplier_invoice_no"], r["date"],
            r["supplier"], r["subtotal"], r["discount_amount"],
            r["tax_amount"], r["total"], r["paid"], r["remaining"],
            self._status_text(r), receive_status_label(r["receive_status"]),
            r["notes"],
        ]

    def update_cards(self, filtered, everything):
        active = [r for r in filtered if r["status"] == VOUCHER_ACTIVE]

        self.set_card("total", format_money(sum(r["total"] for r in active)))
        self.set_card("paid", format_money(sum(
            min(r["paid"], r["total"]) for r in active)))
        self.set_card("remaining", format_money(
            sum(r["remaining"] for r in active)))
        self.set_card("count", str(len(active)))
        self.set_card("cancelled", str(sum(
            1 for r in filtered if r["status"] == VOUCHER_CANCELLED)))

    # ---- الأزرار ----
    def build_actions(self):
        self.add_action("➕ أمر شراء جديد", self.new_order, "green")
        self.add_action("✏ تعديل", self.edit_selected, "blue")
        self.add_action("👁 معاينة", self.preview_selected, "blue")
        self.add_action("📄 فتح PDF", self.open_selected_pdf, "blue")
        self.add_action("🖨 طباعة", self.print_selected, "blue")
        self.add_action("💸 سند صرف", self.new_payment, "green")
        self.add_action("📦 استلام بضاعة", self.receive_goods, "green")
        self.add_action("📒 حساب المورد", self.open_supplier_account, "purple")
        self.add_action(
            "🚫 إلغاء الأمر", lambda: self.change_status(VOUCHER_CANCELLED),
            "gray",
        )
        self.add_action(
            "♻ إعادة تفعيل", lambda: self.change_status(VOUCHER_ACTIVE),
            "orange",
        )
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="👁 معاينة", command=self.preview_selected)
        menu.add_command(label="📄 فتح PDF", command=self.open_selected_pdf)
        menu.add_command(label="✏ تعديل", command=self.edit_selected)
        menu.add_command(label="💸 سند صرف", command=self.new_payment)
        menu.add_command(label="📦 استلام بضاعة", command=self.receive_goods)
        menu.add_command(
            label="📒 حساب المورد", command=self.open_supplier_account
        )
        menu.add_separator()
        menu.add_command(
            label="🚫 إلغاء الأمر",
            command=lambda: self.change_status(VOUCHER_CANCELLED),
        )
        menu.add_command(
            label="♻ إعادة تفعيل",
            command=lambda: self.change_status(VOUCHER_ACTIVE),
        )
        menu.add_separator()
        menu.add_command(label="🗑 حذف", command=self.delete_selected)

    def on_open_record(self, iid):
        self.edit_selected()

    def apply_launch_options(self, search=None, **_ignored):
        """يُستدعى من صفحة الموردين لعرض أوامر مورد محدد."""
        if search:
            self.search_var.set(search)

    # ---- العمليات ----
    def new_order(self):
        self.app.show_purchase_order_form()

    def edit_selected(self):
        records = self.require_selection(single=True, what="أمر شراء")

        if not records:
            return

        if records[0]["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "أمر ملغى",
                "لا يمكن تعديل أمر شراء ملغى. أعد تفعيله أولاً ثم عدّله.",
                parent=self,
            )
            return

        self.app.show_purchase_order_form(po_id=records[0]["id"])

    def new_payment(self):
        records = self.require_selection(single=True, what="أمر شراء")

        if not records:
            return

        order = records[0]

        if order["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "أمر ملغى", "لا يمكن الصرف على أمر شراء ملغى.", parent=self
            )
            return

        if order["remaining"] <= 0.005:
            messagebox.showinfo(
                "لا يوجد متبقٍ",
                "هذا الأمر مسدد بالكامل. لتسجيل دفعة على حساب المورد "
                "استخدم «سند صرف للمورد» من تبويب الموردون.",
                parent=self,
            )
            return

        def done(_voucher_id):
            self._changed()
            self.table.select([str(order["id"])])

        SupplierPaymentDialog(
            self, on_done=done, purchase_order_id=order["id"]
        )

    def _changed(self):
        self.refresh()

        if self.on_data_changed:
            self.on_data_changed()

    def receive_goods(self):
        records = self.require_selection(single=True, what="أمر شراء")

        if not records:
            return

        order = records[0]

        if order["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "أمر ملغى", "لا يمكن استلام بضاعة أمر شراء ملغى.", parent=self
            )
            return

        if order["receive_status"] == "full":
            messagebox.showinfo(
                "تم الاستلام",
                "بضاعة هذا الأمر مستلمة بالكامل.",
                parent=self,
            )
            return

        def done(_receipt_id):
            self._changed()
            self.table.select([str(order["id"])])

        ReceiveGoodsDialog(self, on_done=done, purchase_order_id=order["id"])

    def open_supplier_account(self):
        records = self.require_selection(single=True, what="أمر شراء")

        if records:
            self.app.show_supplier_account(records[0]["supplier_id"])

    def _preview(self, po_id):
        try:
            path = build_po_pdf(po_id)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{e}", parent=self)
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة أمر الشراء",
            share_message="مرحباً، مرفق أمر الشراء، يرجى إرفاق ملف PDF "
                          "المرفق وإرساله.",
            email_subject="أمر شراء",
            email_body="مرفق لكم أمر الشراء.",
        )

    def preview_selected(self):
        records = self.require_selection(single=True, what="أمر شراء")

        if records:
            self._preview(records[0]["id"])

    def open_selected_pdf(self, print_it=False):
        records = self.require_selection(single=True, what="أمر شراء")

        if not records:
            return

        try:
            open_file(build_po_pdf(records[0]["id"]), print_it=print_it)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{e}", parent=self)

    def print_selected(self):
        self.open_selected_pdf(print_it=True)

    def change_status(self, status):
        records = self.require_selection(what="أمر شراء")

        if not records:
            return

        ids = [r["id"] for r in records]

        if status == VOUCHER_CANCELLED and not messagebox.askyesno(
            "تأكيد الإلغاء",
            f"هل تريد إلغاء {len(ids)} أمر شراء؟\n"
            "الأوامر الملغاة لا تدخل في المشتريات ولا في رصيد المورد، "
            "وما دُفع عليها يتحوّل إلى دفعة مقدّمة عند المورد.",
            parent=self,
        ):
            return

        ok, _ = self.run_action(set_purchase_orders_status, ids, status)

        if ok:
            self._changed()
            self.table.select([str(i) for i in ids])

    def delete_selected(self):
        records = self.require_selection(what="أمر شراء")

        if not records:
            return

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف {len(records)} أمر شراء نهائياً؟\n"
            "لا يمكن التراجع. (يمكنك إلغاء الأمر بدلاً من حذفه).",
            parent=self,
        ):
            return

        ok, _ = self.run_action(
            delete_purchase_orders, [r["id"] for r in records]
        )

        if ok:
            self._changed()
