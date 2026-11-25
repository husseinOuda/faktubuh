# ui/suppliers_page.py
"""
إدارة الموردين (تبويب «الموردون» في صفحة الموردون والمشتريات):

  - جدول: الاسم، الهاتف، البريد، العنوان، الملاحظات، الرصيد المستحق،
    إجمالي المشتريات، آخر عملية شراء.
  - تعديل مباشر داخل الجدول: نقر مزدوج على الخلية (أو F2) ثم Enter للحفظ
    · Esc للتراجع · Tab للخلية التالية.
  - بحث فوري (يتجاهل التشكيل والهمزات) وفلتر حسب حالة الرصيد.
  - إجراءات سريعة: حساب المورد (كشف الحساب)، أمر شراء جديد، سند صرف للمورد،
    عرض أوامر المورد. Enter أو النقر المزدوج على خلية غير قابلة للتعديل يفتح
    حساب المورد.
"""

from tkinter import messagebox

from database import BALANCE_CREDIT, BALANCE_DEBIT, BALANCE_ZERO
from purchases_db import (
    SUPPLIER_BALANCE_LABELS,
    delete_supplier,
    get_suppliers_full,
    supplier_balance_text,
    update_supplier_field,
)
from ui.components.client_picker import normalize_text
from ui.components.invoice_utils import format_money
from ui.components.list_page import ListPageBase
from ui.components.supplier_dialogs import (
    SupplierFormDialog,
    SupplierPaymentDialog,
)


class SuppliersPage(ListPageBase):

    TITLE = ""      # العنوان تعرضه صفحة التبويبات
    SEARCH_HINT = "🔍 ابحث بالاسم أو الهاتف أو البريد أو العنوان أو الملاحظات..."

    SHOW_PERIOD = False
    EDITABLE_COLUMNS = ("name", "phone", "email", "address", "notes")

    COLUMNS = [
        ("name", "اسم المورد", 170, "e"),
        ("phone", "الهاتف", 100, "center"),
        ("email", "البريد الإلكتروني", 145, "center"),
        ("address", "العنوان", 120, "e"),
        ("notes", "الملاحظات", 120, "e"),
        ("balance", "الرصيد المستحق", 135, "e"),
        ("purchases", "إجمالي المشتريات", 115, "e"),
        ("last", "آخر عملية شراء", 100, "center"),
    ]

    STAT_CARDS = [
        ("count", "🏭 عدد الموردين", "#2563eb"),
        ("purchases", "🛒 إجمالي المشتريات", "#0f2a5c"),
        ("paid", "💸 إجمالي المدفوع", "#15803d"),
        ("debit", "📌 مستحق للموردين", "#b91c1c"),
        ("credit", "🟣 دفعات مقدّمة لدى الموردين", "#7c3aed"),
    ]

    FILTER_OPTIONS = [
        ("كل الموردين", None),
        ("مستحق لهم", BALANCE_DEBIT),
        ("دفعة مقدّمة", BALANCE_CREDIT),
        ("مسدّدون", BALANCE_ZERO),
    ]
    FILTER_FIELD = "balance_state"
    DATE_FIELD = "last_purchase_date"

    EXPORT_NAME = "suppliers"
    EXPORT_HEADERS = [
        "اسم المورد", "الهاتف", "البريد الإلكتروني", "العنوان", "ملاحظات",
        "عدد أوامر الشراء", "إجمالي المشتريات", "المدفوع على الأوامر",
        "المتبقي على الأوامر", "دفعات على الحساب", "الرصيد المستحق",
        "حالة الرصيد", "آخر عملية شراء",
    ]

    # ======================
    # البيانات
    # ======================
    def fetch_records(self):
        return get_suppliers_full()

    def row_values(self, s):
        return {
            "name": s["name"],
            "phone": s["phone"],
            "email": s["email"],
            "address": s["address"],
            "notes": s["notes"].replace("\n", " "),
            "balance": supplier_balance_text(s, format_money),
            "purchases": format_money(s["purchases"]),
            "last": s["last_purchase_date"] or "—",
        }

    def row_sort_values(self, s):
        return {
            "balance": s["balance"],
            "purchases": s["purchases"],
            "last": s["last_purchase_date"],
        }

    def search_blob(self, s):
        return normalize_text(" ".join(
            str(s[key])
            for key in ("name", "phone", "email", "address", "notes")
        ))

    def filter_records(self, records):
        tokens = normalize_text(self.search_var.get()).split()
        wanted = self.current_filter_value()
        result = []

        for record in records:
            if wanted is not None and record["balance_state"] != wanted:
                continue

            if tokens:
                blob = self.search_blob(record)

                if not all(token in blob for token in tokens):
                    continue

            result.append(record)

        return result

    def export_row(self, s):
        return [
            s["name"], s["phone"], s["email"], s["address"], s["notes"],
            s["orders_count"], s["purchases"], s["paid"], s["remaining"],
            s["advance"], s["balance"],
            SUPPLIER_BALANCE_LABELS[s["balance_state"]],
            s["last_purchase_date"],
        ]

    def update_cards(self, filtered, everything):
        self.set_card("count", str(len(filtered)),
                      f"من أصل {len(everything)}")
        self.set_card("purchases", format_money(
            sum(s["purchases"] for s in filtered)))
        self.set_card("paid", format_money(
            sum(s["paid"] for s in filtered)))
        self.set_card("debit", format_money(sum(
            s["balance"] for s in filtered if s["balance"] > 0)))
        self.set_card("credit", format_money(sum(
            -s["balance"] for s in filtered if s["balance"] < 0)))

    # ======================
    # التعديل المباشر داخل الجدول
    # ======================
    def on_cell_edit(self, record, key, text):
        cleaned = update_supplier_field(record["id"], key, text)
        record[key] = cleaned
        return cleaned.replace("\n", " ")

    # ======================
    # الأزرار
    # ======================
    def build_actions(self):
        self.add_action("➕ مورد جديد", self.new_supplier, "green")
        self.add_action("📒 حساب المورد", self.open_account, "purple")
        self.add_action("🛒 أمر شراء جديد", self.new_order, "blue")
        self.add_action("💸 سند صرف للمورد", self.new_payment, "green")
        self.add_action("📋 أوامر المورد", self.show_orders, "blue")
        self.add_action("✏ تعديل (نافذة)", self.edit_selected, "orange")
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="📒 حساب المورد", command=self.open_account)
        menu.add_command(label="🛒 أمر شراء جديد", command=self.new_order)
        menu.add_command(label="💸 سند صرف للمورد", command=self.new_payment)
        menu.add_command(label="📋 أوامر المورد", command=self.show_orders)
        menu.add_separator()
        menu.add_command(label="✏ تعديل (نافذة)", command=self.edit_selected)
        menu.add_command(label="🗑 حذف", command=self.delete_selected)

    def on_open_record(self, iid):
        # Enter على الصف: حساب المورد (كشف الحساب)
        self.app.show_supplier_account(int(iid))

    # ======================
    # العمليات
    # ======================
    def _after_save(self, supplier_id):
        self.refresh()
        self.table.select([str(supplier_id)])

    def new_supplier(self):
        SupplierFormDialog(self, on_done=self._after_save)

    def edit_selected(self):
        records = self.require_selection(single=True, what="مورد")

        if records:
            SupplierFormDialog(
                self, on_done=self._after_save, supplier=records[0]
            )

    def new_order(self):
        records = self.require_selection(single=True, what="مورد")

        if records:
            self.app.show_purchase_order_form(supplier_id=records[0]["id"])

    def new_payment(self):
        records = self.require_selection(single=True, what="مورد")

        if not records:
            return

        supplier_id = records[0]["id"]

        SupplierPaymentDialog(
            self,
            on_done=lambda _voucher_id: self._after_save(supplier_id),
            supplier_id=supplier_id,
        )

    def open_account(self):
        records = self.require_selection(single=True, what="مورد")

        if records:
            self.app.show_supplier_account(records[0]["id"])

    def show_orders(self):
        records = self.require_selection(single=True, what="مورد")

        if records:
            self.app.show_purchases(
                "orders", search=records[0]["name"]
            )

    def delete_selected(self):
        records = self.require_selection(what="مورد")

        if not records:
            return

        names = "، ".join(r["name"] for r in records[:3])

        if len(records) > 3:
            names += f" و{len(records) - 3} آخرين"

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل أنت متأكد من حذف {len(records)} مورد؟\n{names}",
            parent=self,
        ):
            return

        failures = []

        for record in records:
            try:
                delete_supplier(record["id"])
            except ValueError as error:
                failures.append(f"• {record['name']}: {error}")

        self.refresh()

        if failures:
            messagebox.showerror(
                "لا يمكن حذف بعض الموردين", "\n\n".join(failures),
                parent=self,
            )
