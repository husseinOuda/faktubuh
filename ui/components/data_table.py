# ui/components/data_table.py
"""
جدول موحّد لصفحات المالية (سندات القبض/الصرف/المصروفات):
رأس بلون الهوية، صفوف متناوبة، تمييز عند مرور الفأرة، فرز بالنقر على الرأس،
ترقيم تلقائي (#)، أعمدة من اليمين لليسار، واختصارات لوحة المفاتيح.
"""

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox, ttk

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

    التعديل المباشر (0.1.8):
      editable_columns: مفاتيح الأعمدة القابلة للتعديل بالنقر المزدوج أو F2.
      on_edit(iid, key, text): تُستدعى عند تثبيت القيمة. ارفع ValueError لرفضها
        (يبقى المحرر مفتوحاً مع الرسالة)، أو أرجع نصاً ليُعرض في الخلية بدل ما
        كُتب (تنسيق/تنظيف).
    """

    def __init__(self, parent, columns, tag_colors=None, height=12,
                 on_open=None, on_delete=None, on_select=None,
                 editable_columns=(), on_edit=None):
        super().__init__(parent)

        self.columns = list(columns)
        self.on_open = on_open
        self.on_delete = on_delete
        self.on_select = on_select
        self.editable_columns = tuple(editable_columns)
        self.on_edit = on_edit
        self.context_menu = None

        self._editor = None
        self._editor_state = None

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
            command=self._yview,
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
        self.tree.bind("<F2>", self._on_f2)
        self.tree.bind("<MouseWheel>", lambda e: self.cancel_edit(), add="+")

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
        self.cancel_edit()

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
        self.cancel_edit()

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

        key = self._column_key_at(event.x)

        if self.on_edit and key in self.editable_columns:
            self.start_edit(row, key)
            return "break"

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

    # ======================
    # التعديل المباشر داخل الخلية (0.1.8)
    # ======================
    def _yview(self, *args):
        self.cancel_edit()
        self.tree.yview(*args)

    def _column_key_at(self, x):
        """مفتاح العمود تحت الإحداثي x (يراعي ترتيب العرض من اليمين)."""
        try:
            index = int(self.tree.identify_column(x).lstrip("#")) - 1
        except ValueError:
            return None

        display = [str(c) for c in self.tree.cget("displaycolumns")]

        if 0 <= index < len(display):
            return display[index]

        return None

    def _on_f2(self, event=None):
        selected = self.tree.selection()

        if selected and self.on_edit and self.editable_columns:
            self.start_edit(selected[0], self.editable_columns[0])

        return "break"

    def start_edit(self, iid, key):
        """يفتح محرراً فوق الخلية. يرجع True عند النجاح."""
        iid = str(iid)

        if (
            not self.on_edit
            or key not in self.editable_columns
            or not self.tree.exists(iid)
        ):
            return False

        if not self.commit_edit():
            return False

        self.tree.see(iid)
        self.tree.update_idletasks()

        bbox = self.tree.bbox(iid, key)

        if not bbox:
            return False

        x, y, width, height = bbox
        original = str(self.tree.set(iid, key))

        self.tree.selection_set(iid)
        self.tree.focus(iid)

        editor = tk.Entry(
            self.tree,
            font=("Cairo", 12),
            justify="right",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#2563eb",
            highlightbackground="#2563eb",
        )
        editor.insert(0, original)
        editor.select_range(0, "end")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()

        self._editor = editor
        self._editor_state = {
            "iid": iid, "key": key, "original": original, "busy": False,
        }

        editor.bind("<Return>", lambda e: self._editor_enter())
        editor.bind("<KP_Enter>", lambda e: self._editor_enter())
        editor.bind("<Escape>", lambda e: self._editor_escape())
        editor.bind("<Tab>", lambda e: self._editor_tab(True))
        editor.bind("<ISO_Left_Tab>", lambda e: self._editor_tab(False))
        editor.bind("<Shift-Tab>", lambda e: self._editor_tab(False))
        editor.bind("<FocusOut>", lambda e: self._editor_focus_out())
        return True

    def commit_edit(self, show_error=False):
        """
        يثبّت التعديل الجاري. يرجع True إذا أُغلق المحرر (أو لم يكن مفتوحاً)،
        و False إن بقي مفتوحاً بسبب قيمة مرفوضة.
        """
        editor, state = self._editor, self._editor_state

        if editor is None or state is None:
            return True

        text = editor.get().strip()

        if text == state["original"].strip():
            self._destroy_editor()
            return True

        try:
            result = self.on_edit(state["iid"], state["key"], text)

        except ValueError as error:
            if not show_error:
                # فقدان تركيز مع قيمة مرفوضة → تراجع بصمت
                self._destroy_editor()
                return True

            editor.configure(
                bg="#fee2e2",
                highlightcolor="#dc2626",
                highlightbackground="#dc2626",
            )
            self.bell()

            state["busy"] = True
            messagebox.showerror("قيمة غير صالحة", str(error),
                                 parent=self.winfo_toplevel())

            if self._editor is editor:
                state["busy"] = False
                editor.focus_set()

            return False

        shown = text if result is None or result is True else str(result)

        iid, key = state["iid"], state["key"]
        self._destroy_editor()

        if self.tree.exists(iid):
            self.tree.set(iid, key, shown)

        return True

    def cancel_edit(self):
        self._destroy_editor()

    def _destroy_editor(self):
        editor = self._editor

        # نصفّر الحالة أولاً حتى لا يعيد FocusOut استدعاء الإنهاء
        self._editor = None
        self._editor_state = None

        if editor is not None:
            try:
                editor.destroy()
            except tk.TclError:
                pass

    def _editor_enter(self):
        iid = self._editor_state["iid"] if self._editor_state else None

        if self.commit_edit(show_error=True) and iid and self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus_set()

        return "break"

    def _editor_escape(self):
        self.cancel_edit()
        self.tree.focus_set()
        return "break"

    def _editor_focus_out(self):
        state = self._editor_state

        if state is None or state["busy"]:
            return

        self.commit_edit()

    def _editor_tab(self, forward):
        state = self._editor_state

        if not state or not self.editable_columns:
            return "break"

        iid, key = state["iid"], state["key"]
        columns = list(self.editable_columns)
        rows = list(self.tree.get_children())

        if not self.commit_edit(show_error=True):
            return "break"

        position = columns.index(key) + (1 if forward else -1)
        row_index = rows.index(iid) if iid in rows else 0

        if position >= len(columns):
            position, row_index = 0, row_index + 1
        elif position < 0:
            position, row_index = len(columns) - 1, row_index - 1

        if 0 <= row_index < len(rows):
            self.start_edit(rows[row_index], columns[position])

        return "break"
