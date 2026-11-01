# ui/components/list_page.py
"""
قالب صفحات القوائم المالية (سندات القبض / سندات الصرف / المصروفات):

  عنوان + بطاقات إحصائية + بحث + فلتر زمني + فلتر حالة + جدول + أزرار

الصنف الأب يبني الواجهة ويطبّق الفلاتر والبحث والتحديد، والصنف الابن
يحدّد الأعمدة والبيانات والإجراءات فقط.
"""

import tkinter as tk
import customtkinter as ctk
from datetime import date
from tkinter import messagebox

from ui.components.buttons import make_button
from ui.components.cards import StatCard
from ui.components.data_table import DataTable
from ui.components.files import export_rows_excel
from ui.components.period import (
    PERIODS,
    in_period,
    period_range,
    year_choices,
)


class ListPageBase(ctk.CTkFrame):

    # ---- يضبطها الصنف الابن ----
    TITLE = ""
    SUBTITLE = ""
    SEARCH_HINT = "🔍 ابحث..."
    COLUMNS = []             # (key, عنوان, عرض, محاذاة) — الأول = الأقرب لليمين
    STAT_CARDS = []          # (key, عنوان, لون)
    FILTER_OPTIONS = []      # [(نص الزر, القيمة أو None)]
    FILTER_FIELD = "status"
    DATE_FIELD = "date"
    TAG_COLORS = {}
    EXPORT_NAME = "export"
    EXPORT_HEADERS = []
    ACTIONS_PER_ROW = 5

    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app
        self.records = {}
        self.cards = {}
        self._action_count = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_cards()
        self._build_filters()
        self._build_table()
        self._build_actions()

        self.context_menu = tk.Menu(self, tearoff=0)
        self.build_context_menu(self.context_menu)
        self.table.set_context_menu(self.context_menu)

        self.refresh()

    # ======================
    # بناء الواجهة
    # ======================
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=self.TITLE,
            font=("Cairo", 24, "bold"),
            text_color="#111827",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=self.SUBTITLE,
            font=("Cairo", 14),
            text_color="#6b7280",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    def _build_cards(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 8))

        for index, (key, title, color) in enumerate(self.STAT_CARDS):
            frame.grid_columnconfigure(index, weight=1, uniform="cards")

            card = StatCard(frame, title, "0.00", color)
            card.grid(row=0, column=index, padx=5, sticky="ew")
            self.cards[key] = card

    def set_card(self, key, value, subtitle=None, color=None):
        if key in self.cards:
            self.cards[key].set(value, subtitle, color)

    def _build_filters(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 8))
        frame.grid_columnconfigure(3, weight=1)

        # البحث
        self.search_var = ctk.StringVar()

        ctk.CTkEntry(
            frame,
            textvariable=self.search_var,
            placeholder_text=self.SEARCH_HINT,
            height=38,
            corner_radius=10,
            font=("Cairo", 13),
        ).grid(row=0, column=0, columnspan=5, sticky="ew", padx=10, pady=(10, 6))

        self.search_var.trace_add("write", lambda *args: self.refresh())

        # الفترة الزمنية
        self.period_var = ctk.StringVar(value="الكل")

        ctk.CTkSegmentedButton(
            frame,
            values=PERIODS,
            variable=self.period_var,
            command=lambda value: self.refresh(),
        ).grid(row=1, column=0, padx=(10, 6), pady=(0, 10))

        self.year_menu = ctk.CTkOptionMenu(
            frame,
            values=year_choices(),
            width=90,
            command=lambda value: self.refresh(),
        )
        self.year_menu.grid(row=1, column=1, padx=6, pady=(0, 10))

        # فلتر الحالة
        self._filter_map = dict(self.FILTER_OPTIONS)

        if self.FILTER_OPTIONS:
            self.filter_var = ctk.StringVar(value=self.FILTER_OPTIONS[0][0])

            ctk.CTkSegmentedButton(
                frame,
                values=[label for label, _ in self.FILTER_OPTIONS],
                variable=self.filter_var,
                command=lambda value: self.refresh(),
            ).grid(row=1, column=2, padx=6, pady=(0, 10))
        else:
            self.filter_var = ctk.StringVar(value="")

        self.count_label = ctk.CTkLabel(
            frame,
            text="",
            font=("Cairo", 13, "bold"),
            text_color="#2563eb",
        )
        self.count_label.grid(row=1, column=3, padx=12, pady=(0, 10), sticky="e")

    def _build_table(self):
        self.table = DataTable(
            self,
            self.COLUMNS,
            tag_colors=self.TAG_COLORS,
            on_open=self.on_open_record,
            on_delete=self.delete_selected,
        )
        self.table.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 8))

    def _build_actions(self):
        self.actions_frame = ctk.CTkFrame(self)
        self.actions_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

        for column in range(self.ACTIONS_PER_ROW):
            self.actions_frame.grid_columnconfigure(column, weight=1, uniform="act")

        self.build_actions()

    def add_action(self, text, command, color="blue"):
        """يضيف زراً في الشبكة (ينتقل لصف جديد بعد ACTIONS_PER_ROW)."""
        row, column = divmod(self._action_count, self.ACTIONS_PER_ROW)

        button = make_button(self.actions_frame, text, command, color)
        button.grid(row=row, column=column, padx=5, pady=5, sticky="ew")

        self._action_count += 1
        return button

    # ======================
    # يعرّفها الصنف الابن
    # ======================
    def fetch_records(self):
        raise NotImplementedError

    def row_values(self, record):
        raise NotImplementedError

    def row_tags(self, record):
        return ()

    def row_sort_values(self, record):
        return {}

    def search_blob(self, record):
        return " ".join(str(v) for v in self.row_values(record).values())

    def update_cards(self, filtered, everything):
        pass

    def build_actions(self):
        pass

    def build_context_menu(self, menu):
        pass

    def export_row(self, record):
        return list(self.row_values(record).values())

    def on_open_record(self, iid):
        pass

    def delete_selected(self):
        pass

    # ======================
    # التحديث والفلاتر
    # ======================
    def current_filter_value(self):
        return self._filter_map.get(self.filter_var.get())

    def filter_records(self, records):
        search = self.search_var.get().strip().lower()
        start, end = period_range(self.period_var.get(), self.year_menu.get())
        wanted = self.current_filter_value()

        result = []

        for record in records:
            if wanted is not None and record.get(self.FILTER_FIELD) != wanted:
                continue

            if not in_period(record.get(self.DATE_FIELD), start, end):
                continue

            if search and search not in self.search_blob(record).lower():
                continue

            result.append(record)

        return result

    def refresh(self):
        previous = self.table.selected_ids()

        everything = self.fetch_records()
        filtered = self.filter_records(everything)

        self.records = {str(r["id"]): r for r in filtered}

        self.table.set_rows([
            {
                "iid": str(r["id"]),
                "values": self.row_values(r),
                "tags": self.row_tags(r),
                "sort": self.row_sort_values(r),
            }
            for r in filtered
        ])

        self.table.select(previous)

        self.count_label.configure(
            text=f"📋 المعروض: {len(filtered)} من {len(everything)}"
        )
        self.update_cards(filtered, everything)

    # ======================
    # أدوات للأصناف الأبناء
    # ======================
    def selected_records(self):
        return [
            self.records[iid]
            for iid in self.table.selected_ids()
            if iid in self.records
        ]

    def require_selection(self, single=False, what="سجل"):
        records = self.selected_records()

        if not records:
            messagebox.showwarning(
                "تنبيه", f"يرجى اختيار {what} أولاً", parent=self
            )
            return []

        if single and len(records) > 1:
            messagebox.showwarning(
                "تنبيه", f"يرجى اختيار {what} واحد فقط", parent=self
            )
            return []

        return records

    def run_action(self, function, *args):
        """ينفّذ عملية قاعدة بيانات ويعرض رسالة الخطأ. يرجع (نجح، النتيجة)."""
        try:
            result = function(*args)

        except ValueError as e:
            messagebox.showerror("تعذّر التنفيذ", str(e), parent=self)
            return False, None

        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ غير متوقع:\n{e}", parent=self)
            return False, None

        return True, result

    def export_excel(self):
        records = self.selected_records() or list(self.records.values())

        if not records:
            messagebox.showwarning("تنبيه", "لا توجد بيانات للتصدير", parent=self)
            return

        export_rows_excel(
            self,
            self.EXPORT_HEADERS,
            [self.export_row(r) for r in records],
            f"{self.EXPORT_NAME}_{date.today()}.xlsx",
        )
