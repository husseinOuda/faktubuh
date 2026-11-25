# ui/goods_receipts_page.py
"""
استلام البضاعة (تبويب «📦 استلام البضاعة» في صفحة الموردون والمشتريات):

  جدول بمستندات الاستلام GR-2026-0001: الرقم، التاريخ، أمر الشراء، المورد،
  فاتورة المورد، الكمية المستلمة، الحالة — مع بحث وفلتر فترة وفلتر حالة،
  وتسجيل استلام جديد (كامل أو جزئي)، معاينة PDF، طباعة، إلغاء/إعادة تفعيل،
  حذف، وتصدير Excel.
"""

from tkinter import messagebox

from database import VOUCHER_ACTIVE, VOUCHER_CANCELLED
from goods_receipt_pdf import generate_goods_receipt_pdf
from purchases_db import (
    delete_goods_receipts,
    get_goods_receipt,
    get_goods_receipt_items,
    get_goods_receipts,
    get_purchase_order,
    get_receivable_orders,
    get_supplier,
    set_goods_receipts_status,
)
from ui.components.files import open_file
from ui.components.goods_receipt_dialogs import ReceiveGoodsDialog
from ui.components.list_page import ListPageBase
from ui.components.pdf_preview import PDFPreviewWindow


def _qty(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def build_receipt_pdf(receipt_id):
    """يولّد PDF لمستند استلام ويرجع مساره."""
    receipt = get_goods_receipt(receipt_id)

    if not receipt:
        raise ValueError("تعذّر العثور على مستند الاستلام")

    return generate_goods_receipt_pdf(
        receipt,
        get_goods_receipt_items(receipt_id),
        po=get_purchase_order(receipt["purchase_order_id"]),
        supplier=get_supplier(receipt["supplier_id"]),
    )


class GoodsReceiptsPage(ListPageBase):

    TITLE = ""      # العنوان تعرضه صفحة التبويبات
    SEARCH_HINT = (
        "🔍 ابحث برقم الاستلام أو أمر الشراء أو فاتورة المورد "
        "أو اسم المورد أو الملاحظات..."
    )

    COLUMNS = [
        ("number", "رقم الاستلام", 115, "center"),
        ("date", "التاريخ", 95, "center"),
        ("po", "أمر الشراء", 115, "center"),
        ("supplier", "المورد", 190, "e"),
        ("invoice_no", "فاتورة المورد", 95, "center"),
        ("qty", "الكمية المستلمة", 115, "center"),
        ("status", "الحالة", 90, "center"),
        ("notes", "ملاحظات", 170, "e"),
    ]

    STAT_CARDS = [
        ("count", "📦 عدد مستندات الاستلام", "#2563eb"),
        ("qty", "🔢 إجمالي الكميات المستلمة", "#15803d"),
        ("pending", "⏳ أوامر بانتظار الاستلام", "#c2410c"),
        ("cancelled", "🚫 الملغاة", "#6b7280"),
    ]

    FILTER_OPTIONS = [
        ("الكل", None),
        ("فعّالة", VOUCHER_ACTIVE),
        ("ملغاة", VOUCHER_CANCELLED),
    ]
    FILTER_FIELD = "status"

    TAG_COLORS = {"status_cancelled": "#9ca3af"}

    EXPORT_NAME = "goods_receipts"
    EXPORT_HEADERS = [
        "رقم الاستلام", "التاريخ", "أمر الشراء", "المورد",
        "رقم فاتورة المورد", "عدد الأصناف", "الكمية المستلمة", "الحالة",
        "ملاحظات",
    ]

    # يُستدعى بعد أي تغيير (تستعمله صفحة حساب المورد لتحديث بطاقاتها)
    on_data_changed = None

    # ---- البيانات ----
    def fetch_records(self):
        return get_goods_receipts()

    def row_values(self, r):
        cancelled = r["status"] == VOUCHER_CANCELLED

        return {
            "number": r["receipt_number"],
            "date": r["date"],
            "po": r["po_number"] or "—",
            "supplier": r["supplier"],
            "invoice_no": r["supplier_invoice_no"] or "—",
            "qty": _qty(r["total_qty"]),
            "status": "ملغى" if cancelled else "فعّال",
            "notes": r["notes"].replace("\n", " "),
        }

    def row_tags(self, r):
        return (f"status_{r['status']}",)

    def row_sort_values(self, r):
        return {"qty": r["total_qty"]}

    def search_blob(self, r):
        return " ".join(str(x) for x in (
            r["receipt_number"], r["po_number"], r["supplier_invoice_no"],
            r["supplier"], r["notes"], r["date"],
        ))

    def export_row(self, r):
        return [
            r["receipt_number"], r["date"], r["po_number"], r["supplier"],
            r["supplier_invoice_no"], r["lines_count"], r["total_qty"],
            "ملغى" if r["status"] == VOUCHER_CANCELLED else "فعّال",
            r["notes"],
        ]

    def update_cards(self, filtered, everything):
        active = [r for r in filtered if r["status"] == VOUCHER_ACTIVE]

        self.set_card("count", str(len(active)))
        self.set_card("qty", _qty(sum(r["total_qty"] for r in active)))
        self.set_card("pending", str(len(get_receivable_orders())))
        self.set_card("cancelled", str(sum(
            1 for r in filtered if r["status"] == VOUCHER_CANCELLED)))

    # ---- الأزرار ----
    def build_actions(self):
        self.add_action("➕ استلام بضاعة", self.new_receipt, "green")
        self.add_action("👁 معاينة", self.preview_selected, "blue")
        self.add_action("📄 فتح PDF", self.open_selected_pdf, "blue")
        self.add_action("🖨 طباعة", self.print_selected, "blue")
        self.add_action(
            "🚫 إلغاء المستند",
            lambda: self.change_status(VOUCHER_CANCELLED), "gray",
        )
        self.add_action(
            "♻ إعادة تفعيل",
            lambda: self.change_status(VOUCHER_ACTIVE), "orange",
        )
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="👁 معاينة", command=self.preview_selected)
        menu.add_command(label="📄 فتح PDF", command=self.open_selected_pdf)
        menu.add_separator()
        menu.add_command(
            label="🚫 إلغاء المستند",
            command=lambda: self.change_status(VOUCHER_CANCELLED),
        )
        menu.add_command(
            label="♻ إعادة تفعيل",
            command=lambda: self.change_status(VOUCHER_ACTIVE),
        )
        menu.add_separator()
        menu.add_command(label="🗑 حذف", command=self.delete_selected)

    def on_open_record(self, iid):
        self.preview_selected()

    def apply_launch_options(self, search=None, **_ignored):
        if search:
            self.search_var.set(search)

    def _changed(self):
        self.refresh()

        if self.on_data_changed:
            self.on_data_changed()

    # ---- العمليات ----
    def _dialog_defaults(self):
        """مورد مبدئي لنافذة الاستلام (يعيد تعريفه تبويب حساب المورد)."""
        return {}

    def new_receipt(self):
        if not get_receivable_orders(self._dialog_defaults().get("supplier_id")):
            messagebox.showinfo(
                "لا توجد أوامر",
                "لا توجد أوامر شراء فعّالة بانتظار الاستلام.",
                parent=self,
            )
            return

        def done(receipt_id):
            self._changed()
            self.table.select([str(receipt_id)])

        ReceiveGoodsDialog(self, on_done=done, **self._dialog_defaults())

    def _preview(self, receipt_id):
        try:
            path = build_receipt_pdf(receipt_id)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{e}", parent=self)
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة مستند الاستلام",
            share_message="مرحباً، مرفق مستند استلام البضاعة، يرجى إرفاق "
                          "ملف PDF المرفق وإرساله.",
            email_subject="استلام بضاعة",
            email_body="مرفق لكم مستند استلام البضاعة.",
        )

    def preview_selected(self):
        records = self.require_selection(single=True, what="مستند استلام")

        if records:
            self._preview(records[0]["id"])

    def open_selected_pdf(self, print_it=False):
        records = self.require_selection(single=True, what="مستند استلام")

        if not records:
            return

        try:
            open_file(build_receipt_pdf(records[0]["id"]), print_it=print_it)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{e}", parent=self)

    def print_selected(self):
        self.open_selected_pdf(print_it=True)

    def change_status(self, status):
        records = self.require_selection(what="مستند استلام")

        if not records:
            return

        ids = [r["id"] for r in records]

        if status == VOUCHER_CANCELLED and not messagebox.askyesno(
            "تأكيد الإلغاء",
            f"هل تريد إلغاء {len(ids)} مستند استلام؟\n"
            "ستعود الكميات إلى «المتبقي للاستلام» في أمر الشراء.",
            parent=self,
        ):
            return

        ok, _ = self.run_action(set_goods_receipts_status, ids, status)

        if ok:
            self._changed()
            self.table.select([str(i) for i in ids])

    def delete_selected(self):
        records = self.require_selection(what="مستند استلام")

        if not records:
            return

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف {len(records)} مستند استلام نهائياً؟\n"
            "لا يمكن التراجع. (يمكنك إلغاء المستند بدلاً من حذفه).",
            parent=self,
        ):
            return

        ok, _ = self.run_action(
            delete_goods_receipts, [r["id"] for r in records]
        )

        if ok:
            self._changed()
