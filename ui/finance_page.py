# ui/finance_page.py
"""
المركز المالي: صفحة «إدارة الفواتير» بتبويبات

  الفواتير المحفوظة | سندات القبض | سندات الصرف | المصروفات | لوحة التحكم المالية

كل تبويب يُبنى عند فتحه (فتظهر بياناته محدّثة دائماً).
"""

import customtkinter as ctk

TABS = [
    ("invoices", "📂 الفواتير المحفوظة"),
    ("receipts", "🧾 سندات القبض"),
    ("payments", "💸 سندات الصرف"),
    ("expenses", "📉 المصروفات"),
    ("dashboard", "📈 لوحة التحكم المالية"),
]

_LABEL_BY_KEY = dict(TABS)
_KEY_BY_LABEL = {label: key for key, label in TABS}


class FinancePage(ctk.CTkFrame):

    def __init__(self, parent, app, tab="invoices", **options):
        super().__init__(parent)

        self.app = app
        self.current_key = None
        self.page = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 0))
        bar.grid_columnconfigure(0, weight=1)

        self.tab_var = ctk.StringVar(value=_LABEL_BY_KEY.get(tab, TABS[0][1]))

        ctk.CTkSegmentedButton(
            bar,
            values=[label for _key, label in TABS],
            variable=self.tab_var,
            command=self._on_tab_clicked,
            height=40,
            font=("Cairo", 14, "bold"),
        ).grid(row=0, column=0, sticky="ew")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.show_tab(tab, **options)

    def _on_tab_clicked(self, label):
        self.show_tab(_KEY_BY_LABEL[label])

    def _build_page(self, key):
        # استيراد متأخر لتجنب الاستيراد الدائري وتسريع التشغيل
        if key == "receipts":
            from ui.receipts_page import ReceiptsPage as Page
        elif key == "payments":
            from ui.payments_page import PaymentsPage as Page
        elif key == "expenses":
            from ui.expenses_page import ExpensesPage as Page
        elif key == "dashboard":
            from ui.finance_dashboard_page import FinanceDashboardPage as Page
        else:
            from ui.saved_invoices_page import SavedInvoicesPage as Page

        return Page(self.content, self.app)

    def show_tab(self, key, **options):
        if key not in _LABEL_BY_KEY:
            key = "invoices"

        for widget in self.content.winfo_children():
            widget.destroy()

        self.current_key = key
        self.tab_var.set(_LABEL_BY_KEY[key])

        self.page = self._build_page(key)
        self.page.grid(row=0, column=0, sticky="nsew")

        if key == "invoices":
            # تبقى متاحة لباقي الصفحات (تحديث القائمة بعد حفظ فاتورة)
            self.app.pages["saved_invoices"] = self.page

        launch = getattr(self.page, "apply_launch_options", None)

        if options and launch:
            self.after(150, lambda: launch(**options))
