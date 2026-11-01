# ui/payments_page.py
"""سندات الصرف: إصدار، ربط بمصروف، معاينة PDF، إلغاء، حذف، تصدير."""

from datetime import date
from tkinter import messagebox

from database import (
    PAYMENT_METHODS,
    VOUCHER_ACTIVE,
    VOUCHER_CANCELLED,
    add_payment_voucher,
    delete_payment_vouchers,
    get_expense,
    get_expense_categories,
    get_payment_voucher,
    get_payment_vouchers,
    get_unpaid_expenses,
    get_voucher_expense_summary,
    payment_method_label,
    set_vouchers_status,
    update_payment_voucher,
    voucher_status_label,
)
from ui.components.dialogs import FormDialog
from ui.components.files import open_file
from ui.components.invoice_utils import format_money, parse_number
from ui.components.list_page import ListPageBase
from ui.components.pdf_preview import PDFPreviewWindow
from voucher_pdf import generate_payment_voucher_pdf

NO_EXPENSE = "— دفعة مستقلة (بدون مصروف) —"
NO_CATEGORY = "— بدون تصنيف —"
_METHOD_BY_LABEL = {label: code for code, label in PAYMENT_METHODS.items()}


# =====================================================
# نافذة إصدار / تعديل سند صرف
# =====================================================
class PaymentDialog(FormDialog):

    def __init__(self, parent, on_done, voucher=None, expense_id=None):
        self.voucher = voucher

        super().__init__(
            parent,
            "✏ تعديل سند صرف" if voucher else "💸 سند صرف جديد",
            on_done=on_done,
        )

        categories = get_expense_categories()
        self.category_ids = {name: cid for cid, name in categories}

        initial_expense_id = expense_id

        if voucher:
            initial_expense_id = voucher["expense_id"]

        self._expense_map = {}
        self.add_menu(
            "expense", "المصروف المرتبط", [NO_EXPENSE],
            command=self._on_expense_changed,
        )
        self.add_entry(
            "payee", "المستفيد (المدفوع له)",
            initial=voucher["payee"] if voucher else "",
        )
        self.add_entry(
            "amount", "المبلغ (₪)",
            initial=f"{voucher['amount']:.2f}" if voucher else "",
        )
        self.add_entry(
            "date", "التاريخ (YYYY-MM-DD)",
            initial=voucher["date"] if voucher else date.today().isoformat(),
        )
        self.add_menu(
            "category", "التصنيف (للدفعات المستقلة)",
            [NO_CATEGORY] + list(self.category_ids),
            initial=voucher["category"] if voucher else None,
        )
        self.add_menu(
            "method", "طريقة الدفع", list(PAYMENT_METHODS.values()),
            initial=payment_method_label(voucher["payment_method"])
            if voucher else None,
        )
        self.add_entry(
            "reference", "رقم الشيك / المرجع (اختياري)",
            initial=voucher["reference"] if voucher else "",
        )
        self.add_textbox(
            "notes", "البيان / ملاحظات",
            initial=voucher["notes"] if voucher else "",
        )

        self._load_expenses(initial_expense_id)

        # مبلغ والمستفيد مقترحان عند الإصدار من مصروف محدد
        if expense_id and not voucher and self.value("expense") != NO_EXPENSE:
            self._on_expense_changed(self.value("expense"))

        self.finish_layout()

    def _load_expenses(self, select_id):
        expenses = get_unpaid_expenses(
            exclude_voucher_id=self.voucher["id"] if self.voucher else None
        )

        self._expense_map = {}
        selected = NO_EXPENSE

        for exp in expenses:
            label = (
                f"{exp['expense_number']}  |  {exp['title']}  |  المتبقي "
                f"{format_money(exp['remaining'])}"
            )
            self._expense_map[label] = exp

            if exp["id"] == select_id:
                selected = label

        self.set_menu_values(
            "expense", [NO_EXPENSE] + list(self._expense_map), selected
        )
        self._update_category_state()

    def _update_category_state(self):
        # التصنيف يؤخذ من المصروف عند الربط
        linked = self.value("expense") != NO_EXPENSE
        self._fields["category"][1].configure(
            state="disabled" if linked else "normal"
        )

    def _on_expense_changed(self, value):
        expense = self._expense_map.get(value)
        self._update_category_state()

        if expense:
            self.set_entry("amount", f"{expense['remaining']:.2f}")

            if not self.value("payee"):
                self.set_entry("payee", expense["supplier"] or expense["title"])

    def save(self):
        expense = self._expense_map.get(self.value("expense"))
        expense_id = expense["id"] if expense else None

        amount = parse_number(self.value("amount"), "المبلغ", positive=True)

        data = dict(
            payee=self.value("payee"),
            amount=amount,
            date=self.value("date"),
            payment_method=_METHOD_BY_LABEL.get(self.value("method"), "cash"),
            reference=self.value("reference"),
            notes=self.value("notes"),
            expense_id=expense_id,
            category_id=self.category_ids.get(self.value("category")),
        )

        if self.voucher:
            update_payment_voucher(self.voucher["id"], **data)
            return self.voucher["id"], False

        return add_payment_voucher(**data), True


# =====================================================
# صفحة سندات الصرف
# =====================================================
class PaymentsPage(ListPageBase):

    TITLE = "💸 سندات الصرف"
    SUBTITLE = "إصدار سندات دفع المصروفات والمستحقات وربطها بالمصروفات"
    SEARCH_HINT = "🔍 ابحث برقم السند أو المستفيد أو المصروف أو المرجع..."

    COLUMNS = [
        ("number", "رقم السند", 110, "center"),
        ("date", "التاريخ", 100, "center"),
        ("payee", "المستفيد", 190, "e"),
        ("expense", "المصروف", 110, "center"),
        ("category", "التصنيف", 120, "center"),
        ("method", "طريقة الدفع", 105, "center"),
        ("amount", "المبلغ", 115, "e"),
        ("status", "الحالة", 85, "center"),
    ]

    STAT_CARDS = [
        ("total", "💸 إجمالي المدفوعات", "#b91c1c"),
        ("count", "🧾 عدد السندات الفعّالة", "#2563eb"),
        ("other", "📌 دفعات مستقلة", "#7c3aed"),
        ("cancelled", "🚫 السندات الملغاة", "#6b7280"),
    ]

    FILTER_OPTIONS = [
        ("كل الحالات", None),
        ("فعّال", VOUCHER_ACTIVE),
        ("ملغى", VOUCHER_CANCELLED),
    ]

    TAG_COLORS = {"status_cancelled": "#9ca3af"}

    EXPORT_NAME = "payment_vouchers"
    EXPORT_HEADERS = [
        "رقم السند", "التاريخ", "المستفيد", "المصروف", "التصنيف",
        "طريقة الدفع", "رقم الشيك / المرجع", "المبلغ", "الحالة", "البيان",
    ]

    def fetch_records(self):
        return get_payment_vouchers()

    def row_values(self, v):
        return {
            "number": v["voucher_number"],
            "date": v["date"],
            "payee": v["payee"],
            "expense": v["expense_number"] or "مستقلة",
            "category": v["category"],
            "method": payment_method_label(v["payment_method"]),
            "amount": format_money(v["amount"]),
            "status": voucher_status_label(v["status"]),
        }

    def row_tags(self, v):
        return (f"status_{v['status']}",)

    def row_sort_values(self, v):
        return {"amount": v["amount"]}

    def search_blob(self, v):
        return " ".join(str(x) for x in (
            v["voucher_number"], v["payee"], v["expense_number"] or "",
            v["expense_title"] or "", v["category"], v["reference"],
            v["notes"],
        ))

    def export_row(self, v):
        return [
            v["voucher_number"], v["date"], v["payee"],
            v["expense_number"] or "مستقلة", v["category"],
            payment_method_label(v["payment_method"]), v["reference"],
            v["amount"], voucher_status_label(v["status"]), v["notes"],
        ]

    def update_cards(self, filtered, everything):
        active = [v for v in filtered if v["status"] == VOUCHER_ACTIVE]

        self.set_card("total", format_money(sum(v["amount"] for v in active)))
        self.set_card("count", str(len(active)))
        self.set_card("other", format_money(sum(
            v["amount"] for v in active if not v["expense_id"]
        )))
        self.set_card("cancelled", str(sum(
            1 for v in filtered if v["status"] == VOUCHER_CANCELLED
        )))

    def build_actions(self):
        self.add_action("➕ سند صرف جديد", self.new_voucher, "green")
        self.add_action("✏ تعديل", self.edit_selected, "blue")
        self.add_action("👁 معاينة", self.preview_selected, "blue")
        self.add_action("📄 فتح PDF", self.open_selected_pdf, "blue")
        self.add_action("🖨 طباعة", self.print_selected, "blue")
        self.add_action("🚫 إلغاء السند", lambda: self.change_status(VOUCHER_CANCELLED), "gray")
        self.add_action("♻ إعادة تفعيل", lambda: self.change_status(VOUCHER_ACTIVE), "orange")
        self.add_action("🗑 حذف", self.delete_selected, "red")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="👁 معاينة", command=self.preview_selected)
        menu.add_command(label="📄 فتح PDF", command=self.open_selected_pdf)
        menu.add_command(label="✏ تعديل", command=self.edit_selected)
        menu.add_separator()
        menu.add_command(
            label="🚫 إلغاء السند",
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

    def apply_launch_options(self, new_voucher_expense_id=None, **_ignored):
        """يُستدعى من صفحة المصروفات لإصدار سند صرف لمصروف محدد."""
        if new_voucher_expense_id:
            self.new_voucher(expense_id=new_voucher_expense_id)

    # ---- العمليات ----
    def _after_save(self, result):
        voucher_id, is_new = result
        self.refresh()
        self.table.select([str(voucher_id)])

        if is_new:
            voucher = get_payment_voucher(voucher_id)

            if messagebox.askyesno(
                "تم",
                f"تم إصدار سند الصرف {voucher['voucher_number']} بنجاح.\n"
                "هل تريد معاينة السند؟",
                parent=self,
            ):
                self._preview(voucher_id)

    def new_voucher(self, expense_id=None):
        if expense_id:
            expense = get_expense(expense_id)

            if not expense or expense["remaining"] <= 0.005:
                messagebox.showinfo(
                    "لا يوجد متبقٍ",
                    "هذا المصروف لا يوجد عليه مبلغ متبقٍ للسداد "
                    "(مسدد أو ملغى).",
                    parent=self,
                )
                expense_id = None

        PaymentDialog(self, self._after_save, expense_id=expense_id)

    def edit_selected(self):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        if records[0]["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "سند ملغى",
                "لا يمكن تعديل سند ملغى. أعد تفعيله أولاً ثم عدّله.",
                parent=self,
            )
            return

        PaymentDialog(self, self._after_save, voucher=records[0])

    def _pdf_path(self, voucher_id):
        voucher = get_payment_voucher(voucher_id)
        summary = get_voucher_expense_summary(voucher_id)
        return generate_payment_voucher_pdf(voucher, summary)

    def _preview(self, voucher_id):
        try:
            path = self._pdf_path(voucher_id)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{e}", parent=self)
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة سند الصرف",
            share_message="مرحباً، تم إصدار سند الصرف الخاص بكم، "
                          "يرجى إرفاق ملف PDF المرفق وإرساله.",
            email_subject="سند صرف",
            email_body="مرفق لكم سند الصرف.",
        )

    def preview_selected(self):
        records = self.require_selection(single=True, what="سند")

        if records:
            self._preview(records[0]["id"])

    def open_selected_pdf(self, print_it=False):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        try:
            open_file(self._pdf_path(records[0]["id"]), print_it=print_it)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{e}", parent=self)

    def print_selected(self):
        self.open_selected_pdf(print_it=True)

    def change_status(self, status):
        records = self.require_selection(what="سند")

        if not records:
            return

        ids = [r["id"] for r in records]

        if status == VOUCHER_CANCELLED and not messagebox.askyesno(
            "تأكيد الإلغاء",
            f"هل تريد إلغاء {len(ids)} سند؟\n"
            "السندات الملغاة لا تدخل في المدفوعات، ويعود المصروف المرتبط "
            "غير مسدد بقدرها.",
            parent=self,
        ):
            return

        ok, _ = self.run_action(set_vouchers_status, ids, status)

        if ok:
            self.refresh()
            self.table.select([str(i) for i in ids])

    def delete_selected(self):
        records = self.require_selection(what="سند")

        if not records:
            return

        if not messagebox.askyesno(
            "تأكيد الحذف",
            f"هل تريد حذف {len(records)} سند نهائياً؟\n"
            "لا يمكن التراجع. (يمكنك إلغاء السند بدلاً من حذفه).",
            parent=self,
        ):
            return

        ok, _ = self.run_action(
            delete_payment_vouchers, [r["id"] for r in records]
        )

        if ok:
            self.refresh()
