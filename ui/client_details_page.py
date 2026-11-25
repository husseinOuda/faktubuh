# ui/client_details_page.py
"""
صفحة تفاصيل العميل (0.1.8)

  رأس الصفحة: الاسم وبيانات التواصل + أزرار سريعة (فاتورة جديدة، سند قبض، تعديل)
  بطاقات: عدد الفواتير · إجمالي المشتريات · المحصّل · المتبقي · دفعات على الحساب · الرصيد

  التبويبات:
    📄 سجل الفواتير      فواتير العميل النشطة (معاينة، طباعة، تعديل، سند قبض، أرشفة)
    🗄 أرشيف الفواتير    فواتيره المؤرشفة (إلغاء الأرشفة)
    🧾 سندات القبض       مقبوضاته (إصدار، معاينة، طباعة)
    📒 كشف الحساب        حركات مرتّبة زمنياً برصيد تراكمي + PDF + Excel
    👤 بيانات العميل     الهاتف والبريد والعنوان والملاحظات
"""

import re
from datetime import date, datetime
from tkinter import messagebox

import customtkinter as ctk

from database import (
    BALANCE_LABELS,
    BALANCE_ZERO,
    INVOICE_STATUSES,
    STATUS_CANCELLED,
    STATUS_PAID,
    STATUS_UNPAID,
    VOUCHER_ACTIVE,
    VOUCHER_CANCELLED,
    get_client,
    get_client_receipts,
    get_client_invoices,
    get_client_statement,
    get_receipt,
    get_receipt_invoice_summary,
    payment_method_label,
    set_invoice_archived,
    status_label,
    voucher_status_label,
)
from statement_pdf import generate_statement_pdf
from theme import STATUS_COLORS
from ui.components.buttons import make_button
from ui.components.cards import StatCard
from ui.components.client_dialogs import ClientFormDialog
from ui.components.data_table import DataTable
from ui.components.files import export_rows_excel, open_file
from ui.components.invoice_pdf import build_invoice_pdf
from ui.components.invoice_utils import format_money
from ui.components.list_page import ListPageBase
from ui.components.pdf_preview import PDFPreviewWindow
from ui.components.period import period_range, year_choices
from ui.receipts_page import ReceiptDialog
from voucher_pdf import generate_receipt_pdf

_RED = "#b91c1c"
_GREEN = "#15803d"
_NAVY = "#0f2a5c"
_PURPLE = "#7c3aed"
_GREY = "#9ca3af"

_STATE_COLORS = {"debit": _RED, "credit": _GREEN, "zero": _NAVY}


def _signed_text(amount, state=None):
    """«150.00 ₪ عليه» / «20.00 ₪ له» / «مسدّد»."""
    if state is None:
        state = "debit" if amount > 0.005 else "credit" if amount < -0.005 else "zero"

    if state == "zero":
        return BALANCE_LABELS[BALANCE_ZERO]

    return f"{format_money(abs(amount))} {BALANCE_LABELS[state]}"


def _safe_filename(text):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(text or "")).strip("_") or "client"


# =====================================================
# تبويب: سجل / أرشيف الفواتير
# =====================================================
class _InvoicesTab(ListPageBase):

    TITLE = ""
    SEARCH_HINT = "🔍 ابحث برقم الفاتورة أو الملاحظات..."

    COLUMNS = [
        ("number", "رقم الفاتورة", 130, "center"),
        ("date", "التاريخ", 100, "center"),
        ("total", "الإجمالي", 115, "e"),
        ("collected", "المحصّل", 115, "e"),
        ("remaining", "المتبقي", 115, "e"),
        ("status", "الحالة", 100, "center"),
    ]

    STAT_CARDS = [
        ("count", "📄 عدد الفواتير", "#2563eb"),
        ("total", "💰 إجمالي الفواتير", _NAVY),
        ("remaining", "📌 المتبقي للتحصيل", _RED),
    ]

    FILTER_OPTIONS = [
        ("كل الحالات", None),
        ("مدفوعة", STATUS_PAID),
        ("غير مدفوعة", STATUS_UNPAID),
        ("ملغاة", STATUS_CANCELLED),
    ]

    TAG_COLORS = {f"status_{k}": v for k, v in STATUS_COLORS.items()}

    EXPORT_HEADERS = [
        "رقم الفاتورة", "التاريخ", "الإجمالي", "المحصّل", "المتبقي",
        "الحالة", "ملاحظات",
    ]

    def __init__(self, parent, app, client_id, on_changed, archived=False):
        self.client_id = client_id
        self.on_changed = on_changed
        self.archived = archived
        self.EXPORT_NAME = "client_archive" if archived else "client_invoices"

        super().__init__(parent, app)

    # ---- البيانات ----
    def fetch_records(self):
        return get_client_invoices(self.client_id, archived=self.archived)

    def row_values(self, inv):
        return {
            "number": inv["invoice_number"],
            "date": inv["date"],
            "total": format_money(inv["total"]),
            "collected": format_money(inv["collected"]),
            "remaining": format_money(inv["remaining"]),
            "status": status_label(inv["status"]),
        }

    def row_tags(self, inv):
        return (f"status_{inv['status']}",)

    def row_sort_values(self, inv):
        return {
            "total": inv["total"],
            "collected": inv["collected"],
            "remaining": inv["remaining"],
        }

    def search_blob(self, inv):
        return f"{inv['invoice_number']} {inv['notes']} {inv['date']}"

    def export_row(self, inv):
        return [
            inv["invoice_number"], inv["date"], inv["total"],
            inv["collected"], inv["remaining"],
            status_label(inv["status"]), inv["notes"],
        ]

    def update_cards(self, filtered, everything):
        live = [i for i in filtered if i["status"] != STATUS_CANCELLED]

        self.set_card("count", str(len(filtered)))
        self.set_card("total", format_money(sum(i["total"] for i in live)))
        self.set_card("remaining",
                      format_money(sum(i["remaining"] for i in live)))

    # ---- الأزرار ----
    def build_actions(self):
        self.add_action("👁 معاينة", self.preview_selected, "blue")
        self.add_action("📄 فتح PDF", self.open_selected_pdf, "blue")
        self.add_action("🖨 طباعة", self.print_selected, "blue")
        self.add_action("✏ تعديل الفاتورة", self.edit_selected, "orange")
        self.add_action("💰 سند قبض", self.receipt_for_selected, "green")

        if self.archived:
            self.add_action("📤 إلغاء الأرشفة", lambda: self.set_archived(False), "orange")
        else:
            self.add_action("🗄 أرشفة", lambda: self.set_archived(True), "gray")

        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def build_context_menu(self, menu):
        menu.add_command(label="👁 معاينة", command=self.preview_selected)
        menu.add_command(label="📄 فتح PDF", command=self.open_selected_pdf)
        menu.add_command(label="✏ تعديل الفاتورة", command=self.edit_selected)
        menu.add_command(label="💰 سند قبض", command=self.receipt_for_selected)
        menu.add_separator()

        if self.archived:
            menu.add_command(label="📤 إلغاء الأرشفة",
                             command=lambda: self.set_archived(False))
        else:
            menu.add_command(label="🗄 أرشفة",
                             command=lambda: self.set_archived(True))

    def on_open_record(self, iid):
        self.preview_selected()

    # ---- العمليات ----
    def _single(self):
        records = self.require_selection(single=True, what="فاتورة")
        return records[0] if records else None

    def preview_selected(self):
        invoice = self._single()

        if not invoice:
            return

        try:
            path = build_invoice_pdf(invoice["id"])
        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{error}", parent=self)
            return

        PDFPreviewWindow(self, path)

    def open_selected_pdf(self, print_it=False):
        invoice = self._single()

        if not invoice:
            return

        try:
            open_file(build_invoice_pdf(invoice["id"]), print_it=print_it)
        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{error}", parent=self)

    def print_selected(self):
        self.open_selected_pdf(print_it=True)

    def edit_selected(self):
        invoice = self._single()

        if not invoice:
            return

        self.app.show_invoices()
        self.app.pages["invoices"].edit_invoice(invoice["id"])

    def receipt_for_selected(self):
        invoice = self._single()

        if not invoice:
            return

        if invoice["status"] == STATUS_CANCELLED or invoice["remaining"] <= 0.005:
            messagebox.showinfo(
                "لا يوجد متبقٍ",
                f"الفاتورة {invoice['invoice_number']} لا يوجد عليها مبلغ "
                "متبقٍ للتحصيل (مدفوعة أو ملغاة).",
                parent=self,
            )
            return

        ReceiptDialog(self, lambda _r: self._changed(), invoice_id=invoice["id"])

    def set_archived(self, archived):
        records = self.require_selection(what="فاتورة")

        if not records:
            return

        set_invoice_archived([r["id"] for r in records], archived)
        self._changed()

    def _changed(self):
        self.refresh()
        self.on_changed()


# =====================================================
# تبويب: سندات القبض
# =====================================================
class _ReceiptsTab(ListPageBase):

    TITLE = ""
    SEARCH_HINT = "🔍 ابحث برقم السند أو الفاتورة أو المرجع..."

    COLUMNS = [
        ("number", "رقم السند", 120, "center"),
        ("date", "التاريخ", 100, "center"),
        ("invoice", "الفاتورة", 140, "center"),
        ("method", "طريقة الدفع", 110, "center"),
        ("amount", "المبلغ", 120, "e"),
        ("status", "الحالة", 90, "center"),
    ]

    STAT_CARDS = [
        ("total", "💰 إجمالي المقبوضات", _GREEN),
        ("count", "🧾 عدد السندات الفعّالة", "#2563eb"),
        ("advance", "📌 دفعات على الحساب", _PURPLE),
    ]

    FILTER_OPTIONS = [
        ("كل الحالات", None),
        ("فعّال", VOUCHER_ACTIVE),
        ("ملغى", VOUCHER_CANCELLED),
    ]

    TAG_COLORS = {"status_cancelled": _GREY}

    EXPORT_NAME = "client_receipts"
    EXPORT_HEADERS = [
        "رقم السند", "التاريخ", "الفاتورة", "طريقة الدفع", "المرجع",
        "المبلغ", "الحالة", "البيان",
    ]

    def __init__(self, parent, app, client_id, on_changed):
        self.client_id = client_id
        self.on_changed = on_changed

        super().__init__(parent, app)

    def fetch_records(self):
        return get_client_receipts(self.client_id)

    def row_values(self, r):
        return {
            "number": r["receipt_number"],
            "date": r["date"],
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
            r["receipt_number"], r["invoice_number"] or "",
            r["reference"], r["notes"],
        ))

    def export_row(self, r):
        return [
            r["receipt_number"], r["date"],
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

    def build_actions(self):
        self.add_action("➕ سند قبض جديد", self.new_receipt, "green")
        self.add_action("✏ تعديل", self.edit_selected, "orange")
        self.add_action("👁 معاينة", self.preview_selected, "blue")
        self.add_action("📄 فتح PDF", self.open_selected_pdf, "blue")
        self.add_action("🖨 طباعة", self.print_selected, "blue")
        self.add_action("📊 تصدير Excel", self.export_excel, "purple")
        self.add_action("🧾 إدارة كل السندات", self.open_finance, "navy")
        self.add_action("🔄 تحديث", self.refresh, "navy")

    def on_open_record(self, iid):
        self.preview_selected()

    # ---- العمليات ----
    def _changed(self, _result=None):
        self.refresh()
        self.on_changed()

    def new_receipt(self):
        client = get_client(self.client_id)

        if client:
            ReceiptDialog(self, self._changed, client_name=client["name"])

    def edit_selected(self):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        if records[0]["status"] == VOUCHER_CANCELLED:
            messagebox.showinfo(
                "سند ملغى",
                "لا يمكن تعديل سند ملغى. أعد تفعيله من صفحة السندات أولاً.",
                parent=self,
            )
            return

        ReceiptDialog(self, self._changed, receipt=records[0])

    def _pdf_path(self, receipt_id):
        return generate_receipt_pdf(
            get_receipt(receipt_id), get_receipt_invoice_summary(receipt_id)
        )

    def preview_selected(self):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        try:
            path = self._pdf_path(records[0]["id"])
        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{error}", parent=self)
            return

        PDFPreviewWindow(
            self, path,
            title="معاينة سند القبض",
            share_message="مرحباً، تم إصدار سند القبض الخاص بكم، "
                          "يرجى إرفاق ملف PDF المرفق وإرساله.",
            email_subject="سند قبض",
            email_body="مرفق لكم سند القبض.",
        )

    def open_selected_pdf(self, print_it=False):
        records = self.require_selection(single=True, what="سند")

        if not records:
            return

        try:
            open_file(self._pdf_path(records[0]["id"]), print_it=print_it)
        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{error}", parent=self)

    def print_selected(self):
        self.open_selected_pdf(print_it=True)

    def open_finance(self):
        self.app.show_finance("receipts")


# =====================================================
# تبويب: كشف الحساب
# =====================================================
class _StatementTab(ctk.CTkFrame):

    PERIOD_CHOICES = ["الكل", "الشهر", "سنة", "مخصص"]

    COLUMNS = [
        ("date", "التاريخ", 95, "center"),
        ("kind", "النوع", 85, "center"),
        ("ref", "المستند", 130, "center"),
        ("description", "البيان", 250, "e"),
        ("debit", "مدين", 105, "e"),
        ("credit", "دائن", 105, "e"),
        ("balance", "الرصيد", 130, "e"),
    ]

    KIND_TEXT = {"invoice": "فاتورة", "receipt": "سند قبض", "manual": "تسديد"}

    # بطاقات الملخص (يعيد تعريفها كشف حساب المورد)
    CARDS = [
        ("opening", "↩ الرصيد الافتتاحي", _NAVY),
        ("debit", "📄 إجمالي المدين (فواتير)", _RED),
        ("credit", "💰 إجمالي الدائن (مقبوضات)", _GREEN),
        ("closing", "📒 الرصيد الختامي", _NAVY),
    ]

    def __init__(self, parent, app, client_id):
        super().__init__(parent, fg_color="transparent")

        self.app = app
        self.client_id = client_id
        self.statement = None
        self.entries = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_controls()
        self._build_cards()

        self.table = DataTable(
            self,
            self.COLUMNS,
            tag_colors={"cancelled": _GREY, "opening": _NAVY},
            on_open=self.open_document,
        )
        self.table.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))

        self._build_actions()
        self.reload()

    # ---- الواجهة ----
    def _build_controls(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(4, 8))

        self.period_var = ctk.StringVar(value="الكل")

        ctk.CTkSegmentedButton(
            frame,
            values=self.PERIOD_CHOICES,
            variable=self.period_var,
            command=lambda _v: self._on_period_changed(),
        ).grid(row=0, column=0, padx=(10, 6), pady=10)

        self.year_menu = ctk.CTkOptionMenu(
            frame, values=year_choices(), width=90,
            command=lambda _v: self.reload(),
        )
        self.year_menu.grid(row=0, column=1, padx=6, pady=10)

        ctk.CTkLabel(frame, text="من", font=("Cairo", 13)).grid(
            row=0, column=2, padx=(14, 2))
        self.from_entry = ctk.CTkEntry(
            frame, width=110, height=34, placeholder_text="YYYY-MM-DD",
            justify="center")
        self.from_entry.grid(row=0, column=3, padx=2)

        ctk.CTkLabel(frame, text="إلى", font=("Cairo", 13)).grid(
            row=0, column=4, padx=(10, 2))
        self.to_entry = ctk.CTkEntry(
            frame, width=110, height=34, placeholder_text="YYYY-MM-DD",
            justify="center")
        self.to_entry.grid(row=0, column=5, padx=2)

        make_button(frame, "عرض", self.reload, "blue", width=70, height=34).grid(
            row=0, column=6, padx=8)

        self.cancelled_var = ctk.StringVar(value="on")
        ctk.CTkCheckBox(
            frame, text="إظهار الملغاة", variable=self.cancelled_var,
            onvalue="on", offvalue="off", command=self.reload,
            font=("Cairo", 13),
        ).grid(row=0, column=7, padx=14)

        frame.grid_columnconfigure(8, weight=1)

    def _build_cards(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 8))

        self.cards = {}

        for index, (key, title, color) in enumerate(self.CARDS):
            frame.grid_columnconfigure(index, weight=1, uniform="stcards")
            card = StatCard(frame, title, "0.00", color)
            card.grid(row=0, column=index, padx=5, sticky="ew")
            self.cards[key] = card

    def _build_actions(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        buttons = [
            ("👁 معاينة PDF", self.preview, "blue"),
            ("📄 فتح PDF", self.open_pdf, "blue"),
            ("🖨 طباعة", self.print_pdf, "blue"),
            ("📊 تصدير Excel", self.export_excel, "purple"),
            ("🔄 تحديث", self.reload, "navy"),
        ]

        for column, (text, command, color) in enumerate(buttons):
            frame.grid_columnconfigure(column, weight=1, uniform="stact")
            make_button(frame, text, command, color).grid(
                row=0, column=column, padx=5, pady=5, sticky="ew")

    # ---- الفترة ----
    def _on_period_changed(self):
        self.reload()

    def _range(self):
        label = self.period_var.get()

        if label != "مخصص":
            return period_range(label, self.year_menu.get())

        values = []

        for entry, name in ((self.from_entry, "من"), (self.to_entry, "إلى")):
            text = entry.get().strip()

            if text:
                try:
                    datetime.strptime(text, "%Y-%m-%d")
                except ValueError:
                    raise ValueError(
                        f"تاريخ «{name}» غير صحيح. الصيغة: YYYY-MM-DD"
                    ) from None

            values.append(text or None)

        if values[0] and values[1] and values[0] > values[1]:
            raise ValueError("تاريخ البداية بعد تاريخ النهاية")

        return values[0], values[1]

    # ---- البيانات ----
    def _fetch_statement(self, start, end, include_cancelled):
        return get_client_statement(
            self.client_id, start, end, include_cancelled=include_cancelled
        )

    def signed_text(self, amount, state=None):
        return _signed_text(amount, state)

    def reload(self):
        try:
            start, end = self._range()
        except ValueError as error:
            messagebox.showerror("فترة غير صحيحة", str(error), parent=self)
            return

        try:
            self.statement = self._fetch_statement(
                start, end, self.cancelled_var.get() == "on"
            )
        except ValueError as error:
            messagebox.showerror("خطأ", str(error), parent=self)
            return

        st = self.statement
        rows = []
        self.entries = {}

        if st["start"] or abs(st["opening"]) > 0.005:
            rows.append({
                "iid": "open",
                "values": {
                    "date": st["start"] or "",
                    "kind": "—",
                    "description": "رصيد افتتاحي (مُرحَّل)",
                    "balance": self.signed_text(st["opening"]),
                },
                "tags": ("opening",),
            })

        for index, entry in enumerate(st["rows"]):
            iid = str(index)
            self.entries[iid] = entry

            rows.append({
                "iid": iid,
                "values": {
                    "date": entry["date"],
                    "kind": self.KIND_TEXT.get(entry["kind"], ""),
                    "ref": entry["ref"] or "",
                    "description": entry["description"],
                    "debit": format_money(entry["debit"]) if entry["debit"] else "",
                    "credit": format_money(entry["credit"]) if entry["credit"] else "",
                    "balance": self.signed_text(entry["balance"]),
                },
                "tags": ("cancelled",) if entry["cancelled"] else (),
                "sort": {
                    "debit": entry["debit"],
                    "credit": entry["credit"],
                    "balance": entry["balance"],
                },
            })

        self.table.set_rows(rows)

        self.cards["opening"].set(
            self.signed_text(st["opening"]),
            color=_STATE_COLORS[self._state(st["opening"])],
        )
        self.cards["debit"].set(format_money(st["total_debit"]))
        self.cards["credit"].set(format_money(st["total_credit"]))
        self.cards["closing"].set(
            self.signed_text(st["closing"], st["state"]),
            f"{len(st['rows'])} حركة",
            color=_STATE_COLORS[st["state"]],
        )

    @staticmethod
    def _state(amount):
        return "debit" if amount > 0.005 else "credit" if amount < -0.005 else "zero"

    # ---- فتح المستند المرتبط بالحركة ----
    def open_document(self, iid):
        entry = self.entries.get(str(iid))

        if not entry:
            return

        try:
            if entry["invoice_id"]:
                path = build_invoice_pdf(entry["invoice_id"])
                PDFPreviewWindow(self, path)

            elif entry["receipt_id"]:
                path = generate_receipt_pdf(
                    get_receipt(entry["receipt_id"]),
                    get_receipt_invoice_summary(entry["receipt_id"]),
                )
                PDFPreviewWindow(self, path, title="معاينة سند القبض")

        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر فتح المستند:\n{error}", parent=self)

    # ---- PDF و Excel ----
    def _statement_path(self):
        if self.statement is None:
            self.reload()

        if self.statement is None:
            return None

        return generate_statement_pdf(self.statement)

    def preview(self):
        try:
            path = self._statement_path()
        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر إنشاء PDF:\n{error}", parent=self)
            return

        if path:
            PDFPreviewWindow(
                self, path,
                title="معاينة كشف الحساب",
                share_message="مرحباً، مرفق كشف حسابكم، "
                              "يرجى إرفاق ملف PDF المرفق وإرساله.",
                email_subject="كشف حساب",
                email_body="مرفق لكم كشف الحساب.",
            )

    def open_pdf(self, print_it=False):
        try:
            path = self._statement_path()

            if path:
                open_file(path, print_it=print_it)

        except Exception as error:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف:\n{error}", parent=self)

    def print_pdf(self):
        self.open_pdf(print_it=True)

    def export_excel(self):
        st = self.statement

        if not st:
            return

        headers = [column[1] for column in self.COLUMNS]
        rows = []

        if st["start"] or abs(st["opening"]) > 0.005:
            rows.append([st["start"] or "", "", "", "رصيد افتتاحي",
                         "", "", st["opening"]])

        for entry in st["rows"]:
            rows.append([
                entry["date"], self.KIND_TEXT.get(entry["kind"], ""),
                entry["ref"] or "", entry["description"],
                entry["debit"], entry["credit"], entry["balance"],
            ])

        rows.append(["", "", "", "الإجمالي / الرصيد الختامي",
                     st["total_debit"], st["total_credit"], st["closing"]])

        export_rows_excel(
            self, headers, rows,
            f"statement_{_safe_filename(st['client']['name'])}_{date.today()}.xlsx",
        )


# =====================================================
# تبويب: بيانات العميل
# =====================================================
class _InfoTab(ctk.CTkFrame):

    def __init__(self, parent, page):
        super().__init__(parent, fg_color="transparent")

        client = page.client
        self.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            self, fg_color="white", corner_radius=12,
            border_width=1, border_color="#e5e7eb",
        )
        card.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        card.grid_columnconfigure(0, weight=1)

        fields = [
            ("📞 الهاتف", client["phone"]),
            ("✉ البريد الإلكتروني", client["email"]),
            ("📍 العنوان", client["address"]),
            ("📅 آخر فاتورة", client["last_invoice_date"]),
            ("🧾 آخر دفعة", client["last_receipt_date"]),
        ]

        for row, (label, value) in enumerate(fields):
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.grid(row=row, column=0, sticky="ew", padx=16, pady=(10 if row == 0 else 2, 2))
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
        notes.grid(row=len(fields) + 1, column=0, sticky="ew", padx=16, pady=(0, 12))
        notes.insert("1.0", client["notes"] or "")
        notes.configure(state="disabled")

        make_button(
            card, "✏ تعديل البيانات والملاحظات", page.edit_client, "orange",
            width=240,
        ).grid(row=len(fields) + 2, column=0, sticky="w", padx=16, pady=(0, 16))


# =====================================================
# صفحة تفاصيل العميل
# =====================================================
class ClientDetailsPage(ctk.CTkFrame):

    TABS = [
        ("invoices", "📄 سجل الفواتير"),
        ("archive", "🗄 أرشيف الفواتير"),
        ("receipts", "🧾 سندات القبض"),
        ("statement", "📒 كشف الحساب"),
        ("info", "👤 بيانات العميل"),
    ]

    def __init__(self, parent, app, client_id, tab="invoices"):
        super().__init__(parent)

        self.app = app
        self.client_id = client_id
        self.client = get_client(client_id)
        self.current_key = None
        self.cards = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        if not self.client:
            ctk.CTkLabel(
                self, text="تعذّر العثور على العميل (ربما حُذف).",
                font=("Cairo", 16),
            ).grid(row=0, column=0, pady=40)
            make_button(self, "← العودة للعملاء", app.show_clients, "gray").grid(
                row=1, column=0)
            return

        self._build_header()
        self._build_cards()
        self._build_tabs()

        labels = dict(self.TABS)
        self.show_tab(tab if tab in labels else "invoices")

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
            ("← العملاء", self.app.show_clients, "gray"),
            ("✏ تعديل", self.edit_client, "orange"),
            ("🧾 فاتورة جديدة", self.new_invoice, "blue"),
            ("💰 سند قبض", self.new_receipt, "green"),
        ]):
            make_button(buttons, text, command, color, width=130).grid(
                row=0, column=column, padx=4)

    def _build_cards(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(4, 6))

        for index, (key, title, color) in enumerate([
            ("count", "📄 عدد الفواتير", "#2563eb"),
            ("purchases", "🛒 إجمالي المشتريات", _NAVY),
            ("collected", "💰 المحصّل", _GREEN),
            ("remaining", "📌 المتبقي على الفواتير", _RED),
            ("advance", "📥 دفعات على الحساب", _PURPLE),
            ("balance", "📒 رصيد العميل", _NAVY),
        ]):
            frame.grid_columnconfigure(index, weight=1, uniform="dcards")
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
            fresh = get_client(self.client_id)

            if fresh:
                self.client = fresh

        c = self.client
        state = c["balance_state"]

        self.title_label.configure(text=f"👤 {c['name']}")

        contact = "  ·  ".join(
            part for part in (
                f"📞 {c['phone']}" if c["phone"] else "",
                f"✉ {c['email']}" if c["email"] else "",
                f"📍 {c['address']}" if c["address"] else "",
            ) if part
        )
        self.contact_label.configure(text=contact or "لا توجد بيانات تواصل")

        self.cards["count"].set(str(c["invoices_count"]),
                                f"{c['archived_count']} مؤرشفة")
        self.cards["purchases"].set(format_money(c["purchases"]))
        self.cards["collected"].set(format_money(c["collected"]))
        self.cards["remaining"].set(format_money(c["remaining"]))
        self.cards["advance"].set(format_money(c["advance"]))
        self.cards["balance"].set(
            _signed_text(c["balance"], state),
            {"debit": "مستحق على العميل", "credit": "رصيد لصالح العميل",
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

        if key == "archive":
            return _InvoicesTab(parent, self.app, self.client_id,
                                self.refresh_summary, archived=True)

        if key == "receipts":
            return _ReceiptsTab(parent, self.app, self.client_id,
                                self.refresh_summary)

        if key == "statement":
            return _StatementTab(parent, self.app, self.client_id)

        if key == "info":
            return _InfoTab(parent, self)

        return _InvoicesTab(parent, self.app, self.client_id,
                            self.refresh_summary, archived=False)

    def show_tab(self, key):
        for widget in self.content.winfo_children():
            widget.destroy()

        self.current_key = key
        self.tab_var.set(dict(self.TABS)[key])

        tab = self._build_tab(key)
        tab.grid(row=0, column=0, sticky="nsew")

    # ---- الإجراءات ----
    def edit_client(self):
        ClientFormDialog(self, on_done=self._after_edit, client=self.client)

    def _after_edit(self, _client_id):
        self.refresh_summary()
        self.show_tab(self.current_key)

    def new_invoice(self):
        self.app.show_invoices()
        self.app.pages["invoices"].client_var.set(self.client["name"])

    def new_receipt(self):
        ReceiptDialog(
            self, self._after_receipt, client_name=self.client["name"]
        )

    def _after_receipt(self, _result):
        self.refresh_summary()
        self.show_tab(self.current_key)
