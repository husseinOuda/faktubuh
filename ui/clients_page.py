# ui/clients_page.py
"""
إدارة العملاء (0.1.8):

  - جدول بكل بيانات العميل: الاسم، الهاتف، البريد، العنوان، الملاحظات
    + عدد الفواتير + إجمالي المشتريات + الرصيد (عليه / له / مسدّد).
  - تعديل مباشر داخل الجدول: نقر مزدوج على الخلية (أو F2) ثم Enter للحفظ
    · Esc للتراجع · Tab للخلية التالية.
  - بحث فوري وفلتر حسب حالة الرصيد.
  - فتح صفحة تفاصيل العميل (فواتير، أرشيف، سندات، كشف حساب).
  - إجراءات سريعة: فاتورة جديدة، سند قبض، كشف حساب.
"""

from tkinter import messagebox

from database import (
    BALANCE_CREDIT,
    BALANCE_DEBIT,
    BALANCE_LABELS,
    BALANCE_ZERO,
    delete_client,
    get_clients_full,
    update_client_field,
)
from ui.components.client_dialogs import ClientFormDialog
from ui.components.client_picker import normalize_text
from ui.components.invoice_utils import format_money
from ui.components.list_page import ListPageBase


def balance_text(client):
    """نص الرصيد للعرض: «عليه 150.00 ₪» / «له 20.00 ₪» / «مسدّد»."""
    state = client["balance_state"]

    if state == BALANCE_ZERO:
        return BALANCE_LABELS[BALANCE_ZERO]

    return f"{BALANCE_LABELS[state]} {format_money(abs(client['balance']))}"


class ClientsPage(ListPageBase):

    TITLE = "👥 إدارة العملاء"
    SUBTITLE = "بيانات العملاء وأرصدتهم وسجل فواتيرهم وكشوف حساباتهم"
    HINT = (
        "💡 انقر نقراً مزدوجاً على الاسم أو الهاتف أو البريد أو العنوان "
        "أو الملاحظات لتعديلها مباشرة  ·  Enter لفتح صفحة العميل"
    )
    SEARCH_HINT = "🔍 ابحث بالاسم أو الهاتف أو البريد أو العنوان أو الملاحظات..."

    SHOW_PERIOD = False
    EDITABLE_COLUMNS = ("name", "phone", "email", "address", "notes")

    COLUMNS = [
        ("name", "اسم العميل", 180, "e"),
        ("phone", "الهاتف", 105, "center"),
        ("email", "البريد الإلكتروني", 150, "center"),
        ("address", "العنوان", 130, "e"),
        ("notes", "ملاحظات", 130, "e"),
        ("invoices", "الفواتير", 62, "center"),
        ("purchases", "إجمالي المشتريات", 115, "e"),
        ("balance", "الرصيد", 120, "e"),
    ]

    STAT_CARDS = [
        ("count", "👥 عدد العملاء", "#2563eb"),
        ("purchases", "🛒 إجمالي المشتريات", "#0f2a5c"),
        ("collected", "💰 إجمالي المحصّل", "#15803d"),
        ("debit", "📌 مستحق على العملاء", "#b91c1c"),
        ("credit", "🟣 أرصدة لصالح العملاء", "#7c3aed"),
    ]

    FILTER_OPTIONS = [
        ("كل العملاء", None),
        ("عليهم رصيد", BALANCE_DEBIT),
        ("لهم رصيد", BALANCE_CREDIT),
        ("مسدّدون", BALANCE_ZERO),
    ]
    FILTER_FIELD = "balance_state"
    DATE_FIELD = "last_invoice_date"

    EXPORT_NAME = "clients"
    EXPORT_HEADERS = [
        "الاسم", "الهاتف", "البريد الإلكتروني", "العنوان", "ملاحظات",
        "عدد الفواتير", "إجمالي المشتريات", "المحصّل على الفواتير",
        "المتبقي على الفواتير", "دفعات على الحساب", "الرصيد", "حالة الرصيد",
    ]

    # ======================
    # البيانات
    # ======================
    def fetch_records(self):
        return get_clients_full()

    def row_values(self, c):
        return {
            "name": c["name"],
            "phone": c["phone"],
            "email": c["email"],
            "address": c["address"],
            "notes": c["notes"].replace("\n", " "),
            "invoices": str(c["invoices_count"]),
            "purchases": format_money(c["purchases"]),
            "balance": balance_text(c),
        }

    def row_sort_values(self, c):
        return {
            "invoices": c["invoices_count"],
            "purchases": c["purchases"],
            "balance": c["balance"],
        }

    def search_blob(self, c):
        return normalize_text(" ".join(
            str(c[key])
            for key in ("name", "phone", "email", "address", "notes")
        ))

    def filter_records(self, records):
        # البحث يتجاهل التشكيل واختلاف الهمزات (مثل البحث الذكي)
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

    def export_row(self, c):
        return [
            c["name"], c["phone"], c["email"], c["address"], c["notes"],
            c["invoices_count"], c["purchases"], c["collected"],
            c["remaining"], c["advance"], c["balance"],
            BALANCE_LABELS[c["balance_state"]],
        ]

    def update_cards(self, filtered, everything):
        self.set_card("count", str(len(filtered)),
                      f"من أصل {len(everything)}")
        self.set_card("purchases", format_money(
            sum(c["purchases"] for c in filtered)))
        self.set_card("collected", format_money(
            sum(c["collected"] for c in filtered)))
        self.set_card("debit", format_money(sum(
            c["balance"] for c in filtered if c["balance"] > 0)))
        self.set_card("credit", format_money(sum(
            -c["balance"] for c in filtered if c["balance"] < 0)))

    # ======================
    # التعديل المباشر داخل الجدول
    # ======================
    def on_cell_edit(self, record, key, text):
        cleaned = update_client_field(record["id"], key, text)
        record[key] = cleaned
        return cleaned.replace("\n", " ")

    # ======================
    # الأزرار
    # ======================
    def build_actions(self):
        self.add_action("➕ عميل جديد", self.new_client, "green")
        self.add_action("👤 تفاصيل العميل", self.open_details, "blue")
        self.add_action("📒 كشف حساب", self.open_statement, "purple")
        self.add_action("🧾 فاتورة جديدة", self.new_invoice, "blue")
        self.add_action("💰 سند قبض", self.new_receipt, "green")
        self.add_action("✏ تعديل (نافذة)", self.edit_selected, "orange")
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="👤 تفاصيل العميل", command=self.open_details)
        menu.add_command(label="📒 كشف حساب", command=self.open_statement)
        menu.add_separator()
        menu.add_command(label="🧾 فاتورة جديدة", command=self.new_invoice)
        menu.add_command(label="💰 سند قبض", command=self.new_receipt)
        menu.add_separator()
        menu.add_command(label="✏ تعديل (نافذة)", command=self.edit_selected)
        menu.add_command(label="🗑 حذف", command=self.delete_selected)

    def on_open_record(self, iid):
        self.app.show_client_details(int(iid))

    # ======================
    # العمليات
    # ======================
    def _after_save(self, client_id):
        self.refresh()
        self.table.select([str(client_id)])

    def new_client(self):
        ClientFormDialog(self, on_done=self._after_save)

    def edit_selected(self):
        records = self.require_selection(single=True, what="عميل")

        if records:
            ClientFormDialog(
                self, on_done=self._after_save, client=records[0]
            )

    def open_details(self, tab="invoices"):
        records = self.require_selection(single=True, what="عميل")

        if records:
            self.app.show_client_details(records[0]["id"], tab=tab)

    def open_statement(self):
        self.open_details(tab="statement")

    def new_invoice(self):
        records = self.require_selection(single=True, what="عميل")

        if not records:
            return

        name = records[0]["name"]

        self.app.show_invoices()
        self.app.pages["invoices"].client_var.set(name)

    def new_receipt(self):
        records = self.require_selection(single=True, what="عميل")

        if not records:
            return

        from ui.receipts_page import ReceiptDialog

        client_id = records[0]["id"]
        ReceiptDialog(
            self,
            lambda _result: self._after_save(client_id),
            client_name=records[0]["name"],
        )

    def delete_selected(self):
        records = self.require_selection(what="عميل")

        if not records:
            return

        names = "، ".join(r["name"] for r in records[:3])

        if len(records) > 3:
            names += f" و{len(records) - 3} آخرين"

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل أنت متأكد من حذف {len(records)} عميل؟\n{names}",
            parent=self,
        ):
            return

        failures = []

        for record in records:
            try:
                delete_client(record["id"])
            except ValueError as error:
                failures.append(f"• {record['name']}: {error}")

        self.refresh()

        if failures:
            messagebox.showerror(
                "لا يمكن حذف بعض العملاء", "\n\n".join(failures), parent=self
            )
