# ui/finance_dashboard_page.py
"""لوحة التحكم المالية: مؤشرات، رسم شهري، توزيع المصروفات، المدينون، آخر الحركات."""

import math
import tkinter as tk
from datetime import date

import customtkinter as ctk

from database import (
    get_expense_by_category,
    get_finance_summary,
    get_monthly_series,
    get_recent_transactions,
    get_top_debtors,
)
from ui.components.buttons import make_button
from ui.components.cards import StatCard
from ui.components.invoice_utils import format_money
from ui.components.period import PERIODS, period_range, year_choices

GREEN = "#15803d"
RED = "#b91c1c"
BLUE = "#2563eb"
GRID = "#e5e7eb"
MUTED = "#6b7280"

CHART_SERIES = [
    ("sales", "المبيعات", BLUE),
    ("receipts", "المقبوضات", "#16a34a"),
    ("expenses", "المصروفات", "#dc2626"),
]


def nice_scale(max_value, ticks=4):
    """أعلى قيمة «جميلة» للمحور وخطوة التدرّج: (maximum, step)."""
    if max_value <= 0:
        return float(ticks), 1.0

    raw = max_value / ticks
    magnitude = 10 ** math.floor(math.log10(raw))

    for factor in (1, 2, 2.5, 5, 10):
        step = factor * magnitude

        if step * ticks >= max_value:
            return step * ticks, step

    step = 10 * magnitude
    return step * ticks, step


# =====================================================
# رسم الأعمدة الشهري
# =====================================================
class MonthlyChart(tk.Canvas):

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, bg="white", highlightthickness=0, height=260, **kwargs
        )
        self.series = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, series):
        self.series = series
        self.redraw()

    def redraw(self):
        self.delete("all")

        width = self.winfo_width()
        height = self.winfo_height()

        if width < 120 or height < 100:
            return

        left, right, top, bottom = 78, 12, 14, 42
        plot_w = width - left - right
        plot_h = height - top - bottom

        peak = max(
            (m[key] for m in self.series for key, _n, _c in CHART_SERIES),
            default=0,
        )
        maximum, step = nice_scale(peak)

        # خطوط الشبكة وقيم المحور
        for i in range(5):
            value = step * i
            y = top + plot_h - plot_h * value / maximum
            self.create_line(left, y, width - right, y, fill=GRID)
            self.create_text(
                left - 8, y, text=f"{value:,.0f}", anchor="e",
                fill=MUTED, font=("Cairo", 9),
            )

        group_w = plot_w / 12
        bar_w = max(min(group_w * 0.7 / len(CHART_SERIES), 16), 3)
        used = bar_w * len(CHART_SERIES)

        for index, month in enumerate(self.series):
            x0 = left + index * group_w + (group_w - used) / 2

            for n, (key, _name, color) in enumerate(CHART_SERIES):
                value = month[key]

                if value > 0:
                    bar_h = plot_h * value / maximum
                    self.create_rectangle(
                        x0 + n * bar_w, top + plot_h - bar_h,
                        x0 + (n + 1) * bar_w - 1, top + plot_h,
                        fill=color, outline="",
                    )

            self.create_text(
                left + index * group_w + group_w / 2, top + plot_h + 12,
                text=str(index + 1), fill=MUTED, font=("Cairo", 9),
            )

        # مفتاح الألوان
        x = width - right
        for key, name, color in CHART_SERIES:
            self.create_text(
                x, height - 10, text=name, anchor="e",
                fill="#374151", font=("Cairo", 10),
            )
            x -= 8 + len(name) * 7
            self.create_rectangle(x - 10, height - 16, x, height - 6,
                                  fill=color, outline="")
            x -= 24


# =====================================================
# رسم أشرطة أفقية (توزيع المصروفات)
# =====================================================
class CategoryChart(tk.Canvas):

    ROW_H = 34

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, bg="white", highlightthickness=0, height=260, **kwargs
        )
        self.rows = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, rows):
        self.rows = rows
        self.redraw()

    def redraw(self):
        self.delete("all")

        width = self.winfo_width()

        if width < 120:
            return

        if not self.rows:
            self.create_text(
                width / 2, 60, text="لا توجد مصروفات في هذه الفترة",
                fill=MUTED, font=("Cairo", 12),
            )
            return

        peak = max(value for _n, value in self.rows) or 1
        label_w = 120
        bar_area = max(width - label_w - 110, 40)

        for index, (name, value) in enumerate(self.rows):
            y = 20 + index * self.ROW_H
            bar = max(bar_area * value / peak, 2)

            self.create_text(
                width - 8, y, text=name, anchor="e",
                fill="#374151", font=("Cairo", 11),
            )
            self.create_rectangle(
                10, y - 9, 10 + bar, y + 9, fill="#f97316", outline=""
            )
            self.create_text(
                10 + bar + 6, y, text=format_money(value, symbol=False),
                anchor="w", fill="#111827", font=("Cairo", 10, "bold"),
            )


# =====================================================
# الصفحة
# =====================================================
class FinanceDashboardPage(ctk.CTkFrame):

    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app
        self.cards = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.scroll.grid_columnconfigure(0, weight=1)

        self._build_cards()
        self._build_panels()

        self.refresh()

    # ---- بناء الواجهة ----
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="📈 لوحة التحكم المالية",
            font=("Cairo", 24, "bold"), text_color="#111827",
        ).grid(row=0, column=0, sticky="w")

        self.period_note = ctk.CTkLabel(
            header, text="", font=("Cairo", 13), text_color=MUTED
        )
        self.period_note.grid(row=1, column=0, sticky="w")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=1, rowspan=2, sticky="e")

        self.period_var = ctk.StringVar(value="سنة")

        ctk.CTkSegmentedButton(
            controls, values=PERIODS, variable=self.period_var,
            command=lambda v: self.refresh(),
        ).grid(row=0, column=0, padx=6)

        self.year_menu = ctk.CTkOptionMenu(
            controls, values=year_choices(), width=90,
            command=lambda v: self.refresh(),
        )
        self.year_menu.grid(row=0, column=1, padx=6)

        make_button(
            controls, "🔄", self.refresh, "navy", width=44
        ).grid(row=0, column=2, padx=(6, 0))

    def _build_cards(self):
        specs = [
            [
                ("sales", "💰 المبيعات", BLUE),
                ("receipts", "🧾 المقبوضات", "#16a34a"),
                ("expenses", "📉 المصروفات", RED),
                ("profit", "📈 صافي الربح", GREEN),
            ],
            [
                ("payments", "💸 المدفوعات", "#c2410c"),
                ("cash", "🏦 صافي النقدية", GREEN),
                ("receivables", "👥 ذمم العملاء", "#7c3aed"),
                ("payables", "⏳ مستحقات غير مسددة", "#b45309"),
            ],
        ]

        for row_index, row in enumerate(specs):
            frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
            frame.grid(row=row_index, column=0, sticky="ew", pady=(0, 8))

            for col, (key, title, color) in enumerate(row):
                frame.grid_columnconfigure(col, weight=1, uniform=f"k{row_index}")

                card = StatCard(frame, title, "0.00 ₪", color)
                card.grid(row=0, column=col, padx=5, sticky="ew")
                self.cards[key] = card

    def _panel(self, parent, title, row, column, weight=1):
        panel = ctk.CTkFrame(
            parent, fg_color="white", corner_radius=12,
            border_width=1, border_color=GRID,
        )
        panel.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel, text=title, font=("Cairo", 15, "bold"),
            text_color="#111827",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        parent.grid_columnconfigure(column, weight=weight)
        return panel

    def _build_panels(self):
        top = ctk.CTkFrame(self.scroll, fg_color="transparent")
        top.grid(row=2, column=0, sticky="ew")

        chart_panel = self._panel(top, "📊 الأداء الشهري", 0, 0, weight=3)
        self.monthly_chart = MonthlyChart(chart_panel)
        self.monthly_chart.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.chart_title = chart_panel.winfo_children()[0]

        cat_panel = self._panel(top, "🏷 المصروفات حسب التصنيف", 0, 1, weight=2)
        self.category_chart = CategoryChart(cat_panel)
        self.category_chart.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        bottom = ctk.CTkFrame(self.scroll, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew")

        self.debtors_panel = self._panel(bottom, "👥 أكبر العملاء مديونية", 0, 0)
        self.recent_panel = self._panel(bottom, "🕒 آخر الحركات النقدية", 0, 1)

    # ---- البيانات ----
    def refresh(self):
        label = self.period_var.get()
        year = self.year_menu.get()
        start, end = period_range(label, year)

        summary = get_finance_summary(start, end)

        self.period_note.configure(
            text=(
                f"الفترة: {start} ← {end}" if start
                else "الفترة: كل البيانات"
            ) + "   |   الذمم والمستحقات تُحسب على كل الفترات"
        )

        def money(v):
            return format_money(v)

        self.cards["sales"].set(
            money(summary["sales"]), f"{summary['invoices_count']} فاتورة"
        )
        self.cards["receipts"].set(
            money(summary["receipts"]), f"{summary['receipts_count']} سند قبض"
        )
        self.cards["expenses"].set(
            money(summary["expenses"]), f"{summary['expenses_count']} مصروف"
        )
        self.cards["profit"].set(
            money(summary["net_profit"]), "المبيعات − المصروفات",
            GREEN if summary["net_profit"] >= 0 else RED,
        )
        self.cards["payments"].set(
            money(summary["payments"]),
            f"{summary['payments_count']} سند صرف "
            f"(مستقل: {money(summary['other_payments'])})",
        )
        self.cards["cash"].set(
            money(summary["net_cash"]), "المقبوضات − المدفوعات",
            GREEN if summary["net_cash"] >= 0 else RED,
        )
        self.cards["receivables"].set(
            money(summary["receivables"]),
            f"{summary['receivables_count']} فاتورة غير مسددة",
        )
        self.cards["payables"].set(
            money(summary["payables"]),
            f"{summary['payables_count']} مصروف غير مسدد",
        )

        self.chart_title.configure(text=f"📊 الأداء الشهري — {year}")
        self.monthly_chart.set_data(get_monthly_series(year))

        self.category_chart.set_data(get_expense_by_category(start, end)[:6])

        self._fill_debtors()
        self._fill_recent()

    def _clear(self, panel):
        for widget in panel.winfo_children()[1:]:
            widget.destroy()

    def _row(self, panel, index, left_text, right_text, color="#111827"):
        row = ctk.CTkFrame(panel, fg_color="#f8fafc" if index % 2 else "white")
        row.grid(row=index + 1, column=0, sticky="ew", padx=10, pady=1)
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            row, text=left_text, font=("Cairo", 12), anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=4)

        ctk.CTkLabel(
            row, text=right_text, font=("Cairo", 12, "bold"),
            text_color=color, anchor="e",
        ).grid(row=0, column=1, padx=8, pady=4)

    def _empty(self, panel, text):
        ctk.CTkLabel(
            panel, text=text, font=("Cairo", 12), text_color=MUTED
        ).grid(row=1, column=0, padx=14, pady=(10, 18))

    def _fill_debtors(self):
        self._clear(self.debtors_panel)
        debtors = get_top_debtors(5)

        if not debtors:
            self._empty(self.debtors_panel, "لا توجد ذمم مستحقة 🎉")
            return

        for i, d in enumerate(debtors):
            self._row(
                self.debtors_panel, i,
                f"{d['client']}  ({d['count']} فاتورة)",
                format_money(d["remaining"]), "#7c3aed",
            )

        ctk.CTkFrame(self.debtors_panel, height=8, fg_color="white").grid(
            row=len(debtors) + 1, column=0
        )

    def _fill_recent(self):
        self._clear(self.recent_panel)
        items = get_recent_transactions(8)

        if not items:
            self._empty(self.recent_panel, "لا توجد حركات بعد")
            return

        for i, t in enumerate(items):
            receipt = t["kind"] == "receipt"
            sign = "+" if receipt else "−"

            self._row(
                self.recent_panel, i,
                f"{'🟢' if receipt else '🔴'} {t['number']} — "
                f"{t['party']}  ({t['date']})",
                f"{sign} {format_money(t['amount'])}",
                GREEN if receipt else RED,
            )

        ctk.CTkFrame(self.recent_panel, height=8, fg_color="white").grid(
            row=len(items) + 1, column=0
        )
