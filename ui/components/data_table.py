# ui/components/data_table.py
"""
جدول موحّد لصفحات المالية (سندات القبض/الصرف/المصروفات):
رأس بلون الهوية، صفوف متناوبة، تمييز عند مرور الفأرة، فرز بالنقر على الرأس،
ترقيم تلقائي (#)، أعمدة من اليمين لليسار، واختصارات لوحة المفاتيح.
"""

import customtkinter as ctk
from tkinter import ttk

from theme import TABLE_HOVER
from ui.components.tables import (
    ROW_EVEN_TAG,
    ROW_ODD_TAG,
    STYLE_NAME,
    configure_zebra,
    rtl_columns,
    setup_table_style,
    zebra_tag,
)


def _sort_key(value):
    """الأرقام تُرتَّب كأرقام والنصوص كنصوص (بدون خلط الأنواع)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, float(value), "")

    return (1, 0.0, str(value).lower())


class DataTable(ctk.CTkFrame):
    """
    columns: قائمة (key, عنوان, عرض, محاذاة) بالترتيب المنطقي
             (الأول = الأقرب لليمين). عمود «#» يُضاف تلقائياً.
    tag_colors: {وسم: لون الخط} لتلوين الصفوف حسب الحالة.
    """

    def __init__(self, parent, columns, tag_colors=None, height=12,
                 on_open=None, on_delete=None, on_select=None):
        super().__init__(parent)

        self.columns = list(columns)
        self.on_open = on_open
        self.on_delete = on_delete
        self.on_select = on_select
        self.context_menu = None

        self._row_tags = {}
        self._sort_values = {}
        self._hover_row = None
        self._sort_reverse = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        setup_table_style(self)

        keys = ["no"] + [column[0] for column in self.columns]

        self.tree = ttk.Treeview(
            self,
            style=STYLE_NAME,
            columns=tuple(keys),
            displaycolumns=rtl_columns(*keys),
            show="headings",
            height=height,
            selectmode="extended",
        )

        # وسوم الصفوف المتناوبة تُعرَّف أولاً لتتغلب عليها الوسوم اللاحقة
        configure_zebra(self.tree)

        self.tree.heading("no", text="#")
        self.tree.column("no", width=50, anchor="center", stretch=False)

        for key, title, width, anchor in self.columns:
            self.tree.heading(
                key, text=title,
                command=lambda k=key: self.sort_by(k)
            )
            self.tree.column(key, width=width, anchor=anchor)

        for tag, color in (tag_colors or {}).items():
            self.tree.tag_configure(tag, foreground=color)

        self.tree.tag_configure("hover", background=TABLE_HOVER)

        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            style="Invoice.Vertical.TScrollbar",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=10)

        self.tree.bind("<Motion>", self._on_hover)
        self.tree.bind("<Leave>", lambda e: self._clear_hover())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._on_enter)
        self.tree.bind("<KP_Enter>", self._on_enter)
        self.tree.bind("<Delete>", self._on_delete)
        self.tree.bind("<Button-3>", self._on_right_click)

    # ======================
    # البيانات
    # ======================
    def set_rows(self, rows):
        """
        rows: قائمة قواميس:
          iid:    معرّف الصف
          values: {key: نص}
          tags:   وسوم الحالة (اختياري)
          sort:   {key: قيمة للفرز} (اختياري)
        """
        self._hover_row = None
        self._row_tags = {}
        self._sort_values = {}

        for item in self.tree.get_children():
            self.tree.delete(item)

        keys = [column[0] for column in self.columns]

        for row in rows:
            iid = str(row["iid"])
            values = ("",) + tuple(row["values"].get(k, "") for k in keys)

            self._row_tags[iid] = tuple(row.get("tags", ()))
            self._sort_values[iid] = row.get("sort", {})

            self.tree.insert("", "end", iid=iid, values=values,
                             tags=self._row_tags[iid])

        self.renumber()

    def renumber(self):
        for number, item in enumerate(self.tree.get_children(), start=1):
            self.tree.set(item, "no", number)

            base = tuple(
                tag for tag in self._row_tags.get(item, ())
                if tag not in (ROW_EVEN_TAG, ROW_ODD_TAG)
            )
            tags = base + (zebra_tag(number - 1),)

            self._row_tags[item] = tags
            self.tree.item(item, tags=tags)

    # ======================
    # التحديد
    # ======================
    def selected_ids(self):
        return list(self.tree.selection())

    def select(self, ids):
        existing = [str(i) for i in ids if self.tree.exists(str(i))]

        if existing:
            self.tree.selection_set(existing)

    # ======================
    # الفرز
    # ======================
    def sort_by(self, key):
        def value_of(item):
            stored = self._sort_values.get(item, {})

            if key in stored:
                return _sort_key(stored[key])

            return _sort_key(self.tree.set(item, key))

        items = sorted(
            self.tree.get_children(),
            key=value_of,
            reverse=self._sort_reverse,
        )

        for index, item in enumerate(items):
            self.tree.move(item, "", index)

        self.renumber()
        self._sort_reverse = not self._sort_reverse

    # ======================
    # قائمة الفأرة اليمنى
    # ======================
    def set_context_menu(self, menu):
        self.context_menu = menu

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)

        if not row or self.context_menu is None:
            return

        if row not in self.tree.selection():
            self.tree.selection_set(row)

        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    # ======================
    # التمييز عند مرور الفأرة
    # ======================
    def _on_hover(self, event):
        row = self.tree.identify_row(event.y)

        if (
            row
            and row == self._hover_row
            and "hover" in self.tree.item(row, "tags")
        ):
            return

        self._clear_hover()

        if row and row not in self.tree.selection():
            self.tree.item(
                row, tags=self._row_tags.get(row, ()) + ("hover",)
            )
            self._hover_row = row

    def _clear_hover(self):
        if self._hover_row is not None and self.tree.exists(self._hover_row):
            self.tree.item(
                self._hover_row,
                tags=self._row_tags.get(self._hover_row, ())
            )

        self._hover_row = None

    # ======================
    # الأحداث
    # ======================
    def _on_select(self, event):
        self._clear_hover()

        if self.on_select:
            self.on_select(self.selected_ids())

    def _on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return

        row = self.tree.identify_row(event.y)

        if not row:
            return

        self.tree.selection_set(row)

        if self.on_open:
            self.on_open(row)

        return "break"

    def _on_enter(self, event=None):
        selected = self.tree.selection()

        if selected and self.on_open:
            self.on_open(selected[0])

        return "break"

    def _on_delete(self, event=None):
        if self.tree.selection() and self.on_delete:
            self.on_delete()

        return "break"
