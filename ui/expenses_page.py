# ui/expenses_page.py
"""إدارة المصروفات: تسجيل، تصنيف، متابعة السداد، وإصدار سندات الصرف."""

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from database import (
    EXPENSE_PAID,
    EXPENSE_PARTIAL,
    EXPENSE_UNPAID,
    PAYMENT_METHODS,
    VOUCHER_ACTIVE,
    VOUCHER_CANCELLED,
    add_expense,
    add_expense_category,
    delete_expense_category,
    delete_expenses,
    expense_pay_status_label,
    get_expense_categories,
    get_expenses,
    rename_expense_category,
    set_expenses_status,
    update_expense,
)
from ui.components.buttons import make_button
from ui.components.dialogs import FormDialog
from ui.components.invoice_utils import format_money, parse_number
from ui.components.list_page import ListPageBase

NEW_CATEGORY = "➕ إضافة تصنيف جديد..."
NO_CATEGORY = "— بدون تصنيف —"
_METHOD_BY_LABEL = {label: code for code, label in PAYMENT_METHODS.items()}

# حالة العرض: الملغى يغلب حالة السداد
VIEW_CANCELLED = "cancelled"


# =====================================================
# نافذة إدارة التصنيفات
# =====================================================
class CategoriesDialog(FormDialog):

    def __init__(self, parent, on_close):
        super().__init__(parent, "🏷 تصنيفات المصروفات", width=480,
                         save_text=None)
        self.on_close = on_close

        self.add_section("أضف تصنيفاً جديداً أو عدّل/احذف تصنيفاً غير مستخدم.")

        new_row = ctk.CTkFrame(self.body, fg_color="transparent")
        new_row.grid(row=self._row, column=0, sticky="ew", pady=(0, 8))
        new_row.grid_columnconfigure(0, weight=1)
        self._row += 1

        self.new_entry = ctk.CTkEntry(
            new_row, height=38, corner_radius=10, font=("Cairo", 13),
            justify="right", placeholder_text="اسم التصنيف الجديد",
        )
        self.new_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        make_button(
            new_row, "➕ إضافة", self._add, "green", width=90
        ).grid(row=0, column=1)

        self.list_frame = ctk.CTkScrollableFrame(self.body, height=260)
        self.list_frame.grid(row=self._row, column=0, sticky="ew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self._row += 1

        self._reload()
        self.finish_layout()

    def _reload(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        for index, (cid, name) in enumerate(get_expense_categories()):
            ctk.CTkLabel(
                self.list_frame, text=name, font=("Cairo", 13), anchor="e"
            ).grid(row=index, column=0, sticky="ew", padx=6, pady=3)

            make_button(
                self.list_frame, "✏", lambda c=cid, n=name: self._rename(c, n),
                "blue", width=40, height=30,
            ).grid(row=index, column=1, padx=3)

            make_button(
                self.list_frame, "🗑", lambda c=cid: self._delete(c),
                "red", width=40, height=30,
            ).grid(row=index, column=2, padx=3)

    def _add(self):
        try:
            add_expense_category(self.new_entry.get())
        except ValueError as e:
            messagebox.showerror("خطأ", str(e), parent=self)
            return

        self.new_entry.delete(0, "end")
        self._reload()

    def _rename(self, category_id, old_name):
        new_name = ctk.CTkInputDialog(
            text=f"الاسم الجديد للتصنيف «{old_name}»:", title="تعديل تصنيف"
        ).get_input()

        if not new_name:
            return

        try:
            rename_expense_category(category_id, new_name)
        except ValueError as e:
            messagebox.showerror("خطأ", str(e), parent=self)
            return

        self._reload()

    def _delete(self, category_id):
        if not messagebox.askyesno("تأكيد", "حذف هذا التصنيف؟", parent=self):
            return

        try:
            delete_expense_category(category_id)
        except ValueError as e:
            messagebox.showerror("لا يمكن الحذف", str(e), parent=self)
            return

        self._reload()


# =====================================================
# نافذة إضافة / تعديل مصروف
# =====================================================
class ExpenseDialog(FormDialog):

    def __init__(self, parent, on_done, expense=None):
        self.expense = expense

        super().__init__(
            parent,
            "✏ تعديل مصروف" if expense else "📉 مصروف جديد",
            on_done=on_done,
        )

        self._load_categories()
        self._last_category = NO_CATEGORY

        self.add_entry(
            "title", "وصف المصروف",
            initial=expense["title"] if expense else "",
            placeholder="مثال: إيجار المكتب لشهر تشرين الأول",
        )
        self.add_entry(
            "amount", "المبلغ (₪)",
            initial=f"{expense['amount']:.2f}" if expense else "",
        )
        self.add_entry(
            "date", "التاريخ (YYYY-MM-DD)",
            initial=expense["date"] if expense else date.today().isoformat(),
        )

        initial_category = (
            expense["category"] if expense and expense["category_id"] else None
        )
        self.add_menu(
            "category", "التصنيف", self._category_values(),
            initial=initial_category, command=self._on_category_changed,
        )
        self._last_category = self.value("category")

        self.add_entry(
            "supplier", "المورد / الجهة (اختياري)",
            initial=expense["supplier"] if expense else "",
        )
        self.add_textbox(
            "notes", "ملاحظات", initial=expense["notes"] if expense else ""
        )

        if not expense:
            self.add_check(
                "pay_now", "تم دفعه الآن (إصدار سند صرف تلقائياً)",
                command=self._on_pay_now_toggled,
            )
            self.add_menu(
                "method", "طريقة الدفع", list(PAYMENT_METHODS.values())
            )
            self.add_entry("reference", "رقم الشيك / المرجع (اختياري)")
            self._on_pay_now_toggled()

        self.finish_layout()

    # ---- التصنيفات ----
    def _load_categories(self):
        self.category_ids = {
            name: cid for cid, name in get_expense_categories()
        }

    def _category_values(self):
        return [NO_CATEGORY] + list(self.category_ids) + [NEW_CATEGORY]

    def _on_category_changed(self, value):
        if value != NEW_CATEGORY:
            self._last_category = value
            return

        name = ctk.CTkInputDialog(
            text="اسم التصنيف الجديد:", title="تصنيف جديد"
        ).get_input()

        if name and name.strip():
            try:
                add_expense_category(name)
            except ValueError as e:
                messagebox.showerror("خطأ", str(e), parent=self)
                name = None
        else:
            name = None

        self._load_categories()
        selected = name.strip() if name else self._last_category
        self.set_menu_values("category", self._category_values(), selected)
        self._last_category = self.value("category")

    def _on_pay_now_toggled(self):
        enabled = self.checked("pay_now")
        self.set_enabled("method", enabled)
        self.set_enabled("reference", enabled)

    # ---- الحفظ ----
    def save(self):
        amount = parse_number(self.value("amount"), "المبلغ", positive=True)
        category_id = self.category_ids.get(self.value("category"))

        data = dict(
            title=self.value("title"),
            amount=amount,
            date=self.value("date"),
            category_id=category_id,
            supplier=self.value("supplier"),
            notes=self.value("notes"),
        )

        if self.expense:
            update_expense(self.expense["id"], **data)
            return self.expense["id"]

        expense_id, _voucher_id = add_expense(
            pay_now=self.checked("pay_now"),
            payment_method=_METHOD_BY_LABEL.get(self.value("method"), "cash"),
            reference=self.value("reference"),
            **data,
        )
        return expense_id


# =====================================================
# صفحة المصروفات
# =====================================================
class ExpensesPage(ListPageBase):

    TITLE = "📉 إدارة المصروفات"
    SUBTITLE = "تسجيل المصروفات وتصنيفها ومتابعة المسدد والمتبقي منها"
    SEARCH_HINT = "🔍 ابحث بالوصف أو المورد أو التصنيف أو رقم المصروف..."
    FILTER_FIELD = "view_status"

    COLUMNS = [
        ("number", "رقم المصروف", 105, "center"),
        ("date", "التاريخ", 95, "center"),
        ("title", "الوصف", 200, "e"),
        ("category", "التصنيف", 110, "center"),
        ("supplier", "المورد", 110, "e"),
        ("amount", "المبلغ", 100, "e"),
        ("paid", "المدفوع", 100, "e"),
        ("remaining", "المتبقي", 100, "e"),
        ("status", "حالة السداد", 100, "center"),
    ]

    STAT_CARDS = [
        ("total", "📉 إجمالي المصروفات", "#b91c1c"),
        ("paid", "✅ المسدد", "#15803d"),
        ("due", "⏳ المستحق (غير مسدد)", "#c2410c"),
        ("count", "🧾 عدد المصروفات", "#2563eb"),
    ]

    FILTER_OPTIONS = [
        ("الكل", None),
        ("غير مسدد", EXPENSE_UNPAID),
        ("جزئي", EXPENSE_PARTIAL),
        ("مسدد", EXPENSE_PAID),
        ("ملغى", VIEW_CANCELLED),
    ]

    TAG_COLORS = {
        "view_cancelled": "#9ca3af",
        "view_unpaid": "#c2410c",
        "view_partial": "#b45309",
        "view_paid": "#15803d",
    }

    EXPORT_NAME = "expenses"
    EXPORT_HEADERS = [
        "رقم المصروف", "التاريخ", "الوصف", "التصنيف", "المورد", "المبلغ",
        "المدفوع", "المتبقي", "حالة السداد", "ملاحظات",
    ]

    ACTIONS_PER_ROW = 5

    # ---- البيانات ----
    def fetch_records(self):
        records = get_expenses()

        for r in records:
            r["view_status"] = (
                VIEW_CANCELLED if r["status"] == VOUCHER_CANCELLED
                else r["pay_status"]
            )

        return records

    def _status_text(self, r):
        if r["view_status"] == VIEW_CANCELLED:
            return "ملغى"

        return expense_pay_status_label(r["pay_status"])

    def row_values(self, r):
        cancelled = r["view_status"] == VIEW_CANCELLED

        return {
            "number": r["expense_number"],
            "date": r["date"],
            "title": r["title"],
            "category": r["category"],
            "supplier": r["supplier"] or "—",
            "amount": format_money(r["amount"]),
            "paid": format_money(r["paid"]),
            "remaining": "—" if cancelled else format_money(r["remaining"]),
            "status": self._status_text(r),
        }

    def row_tags(self, r):
        return (f"view_{r['view_status']}",)

    def row_sort_values(self, r):
        return {
            "amount": r["amount"],
            "paid": r["paid"],
            "remaining": r["remaining"],
        }

    def search_blob(self, r):
        return " ".join(str(x) for x in (
            r["expense_number"], r["title"], r["category"], r["supplier"],
            r["notes"],
        ))

    def export_row(self, r):
        return [
            r["expense_number"], r["date"], r["title"], r["category"],
            r["supplier"], r["amount"], r["paid"], r["remaining"],
            self._status_text(r), r["notes"],
        ]

    def update_cards(self, filtered, everything):
        active = [r for r in filtered if r["status"] != VOUCHER_CANCELLED]

        self.set_card("total", format_money(sum(r["amount"] for r in active)))
        self.set_card("paid", format_money(sum(r["paid"] for r in active)))
        self.set_card("due", format_money(sum(r["remaining"] for r in active)))
        self.set_card("count", str(len(active)))

    # ---- الأزرار ----
    def build_actions(self):
        self.add_action("➕ مصروف جديد", self.new_expense, "green")
        self.add_action("✏ تعديل", self.edit_selected, "blue")
        self.add_action("💸 إصدار سند صرف", self.issue_voucher, "orange")
        self.add_action("🏷 التصنيفات", self.manage_categories, "purple")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🚫 إلغاء المصروف", lambda: self.change_status(VOUCHER_CANCELLED), "gray")
        self.add_action("♻ إعادة تفعيل", lambda: self.change_status(VOUCHER_ACTIVE), "orange")
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="✏ تعديل", command=self.edit_selected)
        menu.add_command(label="💸 إصدار سند صرف", command=self.issue_voucher)
        menu.add_separator()
        menu.add_command(
            label="🚫 إلغاء المصروف",
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

    # ---- العمليات ----
    def _after_save(self, expense_id):
        self.refresh()
        self.table.select([str(expense_id)])

    def new_expense(self):
        ExpenseDialog(self, self._after_save)

    def edit_selected(self):
        records = self.require_selection(single=True, what="مصروف")

        if not records:
            return

        if records[0]["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "مصروف ملغى",
                "لا يمكن تعديل مصروف ملغى. أعد تفعيله أولاً ثم عدّله.",
                parent=self,
            )
            return

        ExpenseDialog(self, self._after_save, expense=records[0])

    def issue_voucher(self):
        records = self.require_selection(single=True, what="مصروف")

        if not records:
            return

        record = records[0]

        if record["status"] == VOUCHER_CANCELLED or record["remaining"] <= 0.005:
            messagebox.showinfo(
                "لا يوجد متبقٍ",
                "هذا المصروف مسدد بالكامل أو ملغى.",
                parent=self,
            )
            return

        self.app.show_finance("payments", new_voucher_expense_id=record["id"])

    def manage_categories(self):
        CategoriesDialog(self, self.refresh)

    def change_status(self, status):
        records = self.require_selection(what="مصروف")

        if not records:
            return

        ids = [r["id"] for r in records]

        if status == VOUCHER_CANCELLED and not messagebox.askyesno(
            "تأكيد الإلغاء",
            f"هل تريد إلغاء {len(ids)} مصروف؟\n"
            "المصروفات الملغاة لا تدخل في الحسابات.",
            parent=self,
        ):
            return

        ok, _ = self.run_action(set_expenses_status, ids, status)

        if ok:
            self.refresh()
            self.table.select([str(i) for i in ids])

    def delete_selected(self):
        records = self.require_selection(what="مصروف")

        if not records:
            return

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف {len(records)} مصروف نهائياً؟\n"
            "لا يمكن التراجع.",
            parent=self,
        ):
            return

        ok, _ = self.run_action(delete_expenses, [r["id"] for r in records])

        if ok:
            self.refresh()
