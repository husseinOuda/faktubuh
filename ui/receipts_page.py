# ui/receipts_page.py
"""سندات القبض: إصدار، تعديل، معاينة PDF، إلغاء، حذف، تصدير."""

from datetime import date
from tkinter import messagebox

from database import (
    PAYMENT_METHODS,
    VOUCHER_ACTIVE,
    VOUCHER_CANCELLED,
    add_receipt,
    delete_receipts,
    get_client_open_invoices,
    get_clients,
    get_invoice_info,
    get_receipt,
    get_receipt_invoice_summary,
    get_receipts,
    payment_method_label,
    set_receipts_status,
    update_receipt,
    voucher_status_label,
)
from ui.components.dialogs import FormDialog
from ui.components.files import open_file
from ui.components.invoice_utils import format_money, parse_number
from ui.components.list_page import ListPageBase
from ui.components.pdf_preview import PDFPreviewWindow
from voucher_pdf import generate_receipt_pdf

NO_INVOICE = "— دفعة على الحساب (بدون فاتورة) —"
_METHOD_BY_LABEL = {label: code for code, label in PAYMENT_METHODS.items()}


# =====================================================
# نافذة إصدار / تعديل سند قبض
# =====================================================
class ReceiptDialog(FormDialog):

    def __init__(self, parent, on_done, receipt=None, invoice_id=None):
        self.receipt = receipt

        super().__init__(
            parent,
            "✏ تعديل سند قبض" if receipt else "🧾 سند قبض جديد",
            on_done=on_done,
        )

        clients = get_clients()
        self.client_ids = {name: cid for cid, name, _phone in clients}

        # العميل المبدئي: من السند عند التعديل، أو من الفاتورة المحددة
        initial_client = None
        initial_invoice_id = None

        if receipt:
            initial_client = receipt["client"]
            initial_invoice_id = receipt["invoice_id"]

        elif invoice_id:
            info = get_invoice_info(invoice_id)

            if info:
                initial_client = info["client"]
                initial_invoice_id = invoice_id

        self.add_menu(
            "client", "العميل", list(self.client_ids),
            initial=initial_client, command=self._on_client_changed,
        )

        self._invoice_map = {}
        self.add_menu(
            "invoice", "الفاتورة المرتبطة", [NO_INVOICE],
            command=self._on_invoice_changed,
        )

        self.add_entry(
            "amount", "المبلغ (₪)",
            initial=f"{receipt['amount']:.2f}" if receipt else "",
        )
        self.add_entry(
            "date", "التاريخ (YYYY-MM-DD)",
            initial=receipt["date"] if receipt else date.today().isoformat(),
        )
        self.add_menu(
            "method", "طريقة الدفع", list(PAYMENT_METHODS.values()),
            initial=payment_method_label(receipt["payment_method"])
            if receipt else None,
        )
        self.add_entry(
            "reference", "رقم الشيك / المرجع (اختياري)",
            initial=receipt["reference"] if receipt else "",
        )
        self.add_textbox(
            "notes", "البيان / ملاحظات",
            initial=receipt["notes"] if receipt else "",
        )

        self._load_invoices(initial_invoice_id)

        # مبلغ مقترح عند الإصدار من فاتورة محددة (المتبقي عليها)
        if invoice_id and not receipt and initial_invoice_id in {
            inv["id"] for inv in self._invoice_map.values()
        }:
            self._on_invoice_changed(self.value("invoice"))

        self.finish_layout()

    # ---- العميل والفواتير ----
    def _on_client_changed(self, _value=None):
        self._load_invoices(None)

    def _load_invoices(self, select_id):
        client_id = self.client_ids.get(self.value("client"))

        invoices = get_client_open_invoices(
            client_id,
            exclude_receipt_id=self.receipt["id"] if self.receipt else None,
        ) if client_id else []

        self._invoice_map = {}
        selected = NO_INVOICE

        for inv in invoices:
            label = (
                f"{inv['invoice_number']}  |  المتبقي "
                f"{format_money(inv['remaining'])}  |  {inv['date']}"
            )
            self._invoice_map[label] = inv

            if inv["id"] == select_id:
                selected = label

        self.set_menu_values(
            "invoice", [NO_INVOICE] + list(self._invoice_map), selected
        )

    def _on_invoice_changed(self, value):
        invoice = self._invoice_map.get(value)

        if invoice:
            self.set_entry("amount", f"{invoice['remaining']:.2f}")

    # ---- الحفظ ----
    def save(self):
        client_id = self.client_ids.get(self.value("client"))

        if not client_id:
            raise ValueError("يرجى اختيار العميل")

        invoice = self._invoice_map.get(self.value("invoice"))
        invoice_id = invoice["id"] if invoice else None

        amount = parse_number(
            self.value("amount"), "المبلغ", positive=True
        )

        data = dict(
            client_id=client_id,
            amount=amount,
            date=self.value("date"),
            payment_method=_METHOD_BY_LABEL.get(self.value("method"), "cash"),
            reference=self.value("reference"),
            notes=self.value("notes"),
            invoice_id=invoice_id,
        )

        if self.receipt:
            update_receipt(self.receipt["id"], **data)
            return self.receipt["id"], False

        return add_receipt(**data), True


# =====================================================
# صفحة سندات القبض
# =====================================================
class ReceiptsPage(ListPageBase):

    TITLE = "🧾 سندات القبض"
    SUBTITLE = "إصدار سندات استلام الدفعات من العملاء وربطها بالفواتير"
    SEARCH_HINT = "🔍 ابحث برقم السند أو اسم العميل أو رقم الفاتورة أو المرجع..."

    COLUMNS = [
        ("number", "رقم السند", 110, "center"),
        ("date", "التاريخ", 100, "center"),
        ("client", "العميل", 210, "e"),
        ("invoice", "الفاتورة", 130, "center"),
        ("method", "طريقة الدفع", 110, "center"),
        ("amount", "المبلغ", 120, "e"),
        ("status", "الحالة", 90, "center"),
    ]

    STAT_CARDS = [
        ("total", "💰 إجمالي المقبوضات", "#15803d"),
        ("count", "🧾 عدد السندات الفعّالة", "#2563eb"),
        ("advance", "📌 دفعات على الحساب", "#7c3aed"),
        ("cancelled", "🚫 السندات الملغاة", "#b91c1c"),
    ]

    FILTER_OPTIONS = [
        ("كل الحالات", None),
        ("فعّال", VOUCHER_ACTIVE),
        ("ملغى", VOUCHER_CANCELLED),
    ]

    TAG_COLORS = {"status_cancelled": "#9ca3af"}

    EXPORT_NAME = "receipts"
    EXPORT_HEADERS = [
        "رقم السند", "التاريخ", "العميل", "الفاتورة", "طريقة الدفع",
        "رقم الشيك / المرجع", "المبلغ", "الحالة", "البيان",
    ]

    # ---- البيانات ----
    def fetch_records(self):
        return get_receipts()

    def row_values(self, r):
        return {
            "number": r["receipt_number"],
            "date": r["date"],
            "client": r["client"],
            "invoice": r["invoice_number"] or "دفعة على الحساب",
            "method": payment_method_label(r["payment_method"]),
            "amount": format_money(r["amount"]),
            "status": voucher_status_label(r["status"]),
        }

    def row_tags(self, r):
        return (f"status_{r['status']}",)

    def row_sort_values(self, r):
        return {"amount": r["amount"]}

    def search_blob(self, r):
        return " ".join(str(x) for x in (
            r["receipt_number"], r["client"], r["invoice_number"] or "",
            r["reference"], r["notes"],
        ))

    def export_row(self, r):
        return [
            r["receipt_number"], r["date"], r["client"],
            r["invoice_number"] or "دفعة على الحساب",
            payment_method_label(r["payment_method"]), r["reference"],
            r["amount"], voucher_status_label(r["status"]), r["notes"],
        ]

    def update_cards(self, filtered, everything):
        active = [r for r in filtered if r["status"] == VOUCHER_ACTIVE]

        self.set_card("total", format_money(sum(r["amount"] for r in active)))
        self.set_card("count", str(len(active)))
        self.set_card("advance", format_money(sum(
            r["amount"] for r in active if not r["invoice_id"]
        )))
        self.set_card("cancelled", str(sum(
            1 for r in filtered if r["status"] == VOUCHER_CANCELLED
        )))

    # ---- الأزرار ----
    def build_actions(self):
        self.add_action("➕ سند قبض جديد", self.new_receipt, "green")
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

    def apply_launch_options(self, new_receipt_invoice_id=None, **_ignored):
        """يُستدعى من صفحة الفواتير لفتح نافذة سند قبض لفاتورة محددة."""
        if new_receipt_invoice_id:
            self.new_receipt(invoice_id=new_receipt_invoice_id)

    # ---- العمليات ----
    def _after_save(self, result):
        receipt_id, is_new = result
        self.refresh()
        self.table.select([str(receipt_id)])

        if is_new:
            receipt = get_receipt(receipt_id)

            if messagebox.askyesno(
                "تم",
                f"تم إصدار سند القبض {receipt['receipt_number']} بنجاح.\n"
                "هل تريد معاينة السند؟",
                parent=self,
            ):
                self._preview(receipt_id)

    def new_receipt(self, invoice_id=None):
        if not get_clients():
            messagebox.showwarning(
                "تنبيه", "أضف عميلاً أولاً من صفحة العملاء.", parent=self
            )
            return

        if invoice_id:
            info = get_invoice_info(invoice_id)

            if not info:
                return

            open_ids = {
                inv["id"]
                for cid, name, _p in get_clients() if name == info["client"]
                for inv in get_client_open_invoices(cid)
            }

            if invoice_id not in open_ids:
                messagebox.showinfo(
                    "لا يوجد متبقٍ",
                    f"الفاتورة {info['invoice_number']} لا يوجد عليها مبلغ "
                    "متبقٍ للتحصيل (مدفوعة أو ملغاة).",
                    parent=self,
                )
                invoice_id = None

        ReceiptDialog(self, self._after_save, invoice_id=invoice_id)

    def edit_selected(self):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        record = records[0]

        if record["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "سند ملغى",
                "لا يمكن تعديل سند ملغى. أعد تفعيله أولاً ثم عدّله.",
                parent=self,
            )
            return

        ReceiptDialog(self, self._after_save, receipt=record)

    def _pdf_path(self, receipt_id):
        receipt = get_receipt(receipt_id)
        summary = get_receipt_invoice_summary(receipt_id)
        return generate_receipt_pdf(receipt, summary)

    def _preview(self, receipt_id):
        try:
            path = self._pdf_path(receipt_id)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{e}", parent=self)
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة سند القبض",
            share_message="مرحباً، تم إصدار سند القبض الخاص بكم، "
                          "يرجى إرفاق ملف PDF المرفق وإرساله.",
            email_subject="سند قبض",
            email_body="مرفق لكم سند القبض.",
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

        if status == VOUCHER_CANCELLED:
            if not messagebox.askyesno(
                "تأكيد الإلغاء",
                f"هل تريد إلغاء {len(ids)} سند؟\n"
                "السندات الملغاة لا تدخل في المقبوضات، وتعود الفاتورة "
                "غير مدفوعة إن نقص المحصّل عليها.",
                parent=self,
            ):
                return

        ok, changed = self.run_action(set_receipts_status, ids, status)

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
            "لا يمكن التراجع. (يمكنك إلغاء السند بدلاً من حذفه للاحتفاظ بالأثر).",
            parent=self,
        ):
            return

        ok, _ = self.run_action(delete_receipts, [r["id"] for r in records])

        if ok:
            self.refresh()
