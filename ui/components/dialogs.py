# ui/components/dialogs.py
"""نافذة نموذج إدخال عامة (حقول، قوائم، ملاحظات) تُبنى عليها نوافذ السندات."""

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from theme import PRIMARY_BTN

LABEL_FONT = ("Cairo", 13, "bold")
ENTRY_FONT = ("Cairo", 14)


class FormDialog(ctk.CTkToplevel):
    """
    استخدام: ورِّث الصنف، أضف الحقول في __init__ ثم استدعِ finish_layout()،
    وعرّف save() لتنفيذ الحفظ (ارفع ValueError لعرض رسالة الخطأ).
    ما يرجعه save() يُمرَّر إلى on_done بعد إغلاق النافذة.
    """

    def __init__(self, parent, title, width=560, save_text="💾 حفظ",
                 on_done=None):
        super().__init__(parent)

        self._parent = parent
        self._width = width
        self.on_done = on_done
        self.on_close = None
        self._fields = {}
        self._row = 0

        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color="#f8fafc")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(18, 8))
        self.body.grid_columnconfigure(0, weight=1)

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(fill="x", padx=24, pady=(4, 18))
        self.footer.grid_columnconfigure((0, 1), weight=1)

        column = 0

        if save_text:
            self.save_btn = ctk.CTkButton(
                self.footer,
                text=save_text,
                command=self._on_save_click,
                **PRIMARY_BTN,
            )
            self.save_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")
            column = 1

        self.cancel_btn = ctk.CTkButton(
            self.footer,
            text="إلغاء" if save_text else "إغلاق",
            command=self.close,
            fg_color="#6b7280",
            hover_color="#4b5563",
            height=45,
            corner_radius=10,
            font=("Cairo", 14, "bold"),
        )
        self.cancel_btn.grid(
            row=0, column=column, padx=(6 if save_text else 0, 0),
            sticky="ew", columnspan=1 if save_text else 2,
        )

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

    # ======================
    # حجم النافذة وجعلها نمطية (Modal)
    # ======================
    def finish_layout(self):
        self.update_idletasks()

        height = self.winfo_reqheight()

        try:
            top = self._parent.winfo_toplevel()
            x = top.winfo_rootx() + (top.winfo_width() - self._width) // 2
            y = top.winfo_rooty() + (top.winfo_height() - height) // 2
        except tk.TclError:
            x, y = 200, 100

        self.geometry(f"{self._width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.after(150, self._make_modal)

    def _make_modal(self):
        try:
            self.transient(self._parent.winfo_toplevel())
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def close(self):
        callback = self.on_close
        self.destroy()

        if callback:
            callback()

    # ======================
    # إضافة الحقول
    # ======================
    def _add_label(self, text):
        ctk.CTkLabel(
            self.body,
            text=text,
            font=LABEL_FONT,
            text_color="#374151",
            anchor="e",
        ).grid(row=self._row, column=0, sticky="ew", pady=(8, 2))
        self._row += 1

    def add_section(self, text):
        ctk.CTkLabel(
            self.body,
            text=text,
            font=("Cairo", 12),
            text_color="#6b7280",
            anchor="e",
            wraplength=self._width - 60,
            justify="right",
        ).grid(row=self._row, column=0, sticky="ew", pady=(0, 4))
        self._row += 1

    def add_entry(self, key, label, initial="", placeholder=""):
        self._add_label(label)

        entry = ctk.CTkEntry(
            self.body,
            height=40,
            corner_radius=10,
            font=ENTRY_FONT,
            justify="right",
            placeholder_text=placeholder,
        )
        entry.grid(row=self._row, column=0, sticky="ew")
        self._row += 1

        if initial not in (None, ""):
            entry.insert(0, str(initial))

        self._fields[key] = ("entry", entry, None)
        return entry

    def add_menu(self, key, label, values, initial=None, command=None):
        self._add_label(label)

        values = list(values) or [""]
        var = ctk.StringVar(value=initial if initial in values else values[0])

        menu = ctk.CTkOptionMenu(
            self.body,
            values=values,
            variable=var,
            command=command,
            height=38,
            font=("Cairo", 13),
            dropdown_font=("Cairo", 13),
        )
        menu.grid(row=self._row, column=0, sticky="ew")
        self._row += 1

        self._fields[key] = ("menu", menu, var)
        return menu

    def add_textbox(self, key, label, initial="", height=72):
        self._add_label(label)

        box = ctk.CTkTextbox(
            self.body,
            height=height,
            font=("Cairo", 13),
            corner_radius=10,
            border_width=1,
            border_color="#d1d5db",
        )
        box.grid(row=self._row, column=0, sticky="ew")
        self._row += 1

        if initial:
            box.insert("1.0", str(initial))

        self._fields[key] = ("text", box, None)
        return box

    def add_check(self, key, label, initial=False, command=None):
        var = ctk.StringVar(value="on" if initial else "off")

        check = ctk.CTkCheckBox(
            self.body,
            text=label,
            variable=var,
            onvalue="on",
            offvalue="off",
            command=command,
            font=("Cairo", 13, "bold"),
        )
        check.grid(row=self._row, column=0, sticky="e", pady=(14, 2))
        self._row += 1

        self._fields[key] = ("check", check, var)
        return check

    # ======================
    # قراءة وتعديل القيم
    # ======================
    def value(self, key):
        kind, widget, var = self._fields[key]

        if kind == "entry":
            return widget.get().strip()

        if kind == "text":
            return widget.get("1.0", "end").strip()

        return var.get()

    def checked(self, key):
        return self._fields[key][2].get() == "on"

    def set_entry(self, key, text):
        entry = self._fields[key][1]
        entry.delete(0, "end")
        entry.insert(0, str(text))

    def set_menu_values(self, key, values, selected=None):
        _kind, menu, var = self._fields[key]
        values = list(values) or [""]

        menu.configure(values=values)
        var.set(selected if selected in values else values[0])

    def set_menu(self, key, value):
        self._fields[key][2].set(value)

    def set_enabled(self, key, enabled):
        self._fields[key][1].configure(
            state="normal" if enabled else "disabled"
        )

    # ======================
    # الحفظ
    # ======================
    def save(self):
        raise NotImplementedError

    def _on_save_click(self):
        try:
            result = self.save()

        except ValueError as e:
            messagebox.showerror("خطأ", str(e), parent=self)
            return

        except Exception as e:
            messagebox.showerror(
                "خطأ", f"حدث خطأ غير متوقع:\n{e}", parent=self
            )
            return

        callback = self.on_done
        self.destroy()

        if callback:
            callback(result)
