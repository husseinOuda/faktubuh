# ui/components/client_picker.py
"""
اختيار العميل ببحث ذكي (Autocomplete) — بديل CTkComboBox.

  - تظهر قائمة اقتراحات أثناء الكتابة، والبحث في الاسم والهاتف والبريد
    ويتجاهل التشكيل واختلاف الهمزات (أ/إ/ا) و(ة/ه) و(ى/ي) والأرقام العربية.
  - الأسهم ↑↓ للتنقل، Enter للاختيار، Esc للإغلاق.
  - عند عدم وجود تطابق يُعرض خيار «➕ إضافة ... كعميل جديد».
  - زر ▾ يعرض القائمة كاملة (كالقائمة المنسدلة القديمة).
  - تظهر بجانب كل عميل حالة رصيده (عليه/له) إن توفّرت.

الاستخدام:

    picker = ClientPicker(parent, textvariable=self.client_var,
                          on_select=..., on_add_new=...)
    picker.set_clients(get_clients_full())     # أو get_clients() (id, name, phone)
    picker.client_id()                          # رقم العميل المطابق للنص أو None
"""

import tkinter as tk
import customtkinter as ctk

from ui.components.invoice_utils import format_money

PLACEHOLDER = "🔍 اكتب اسم العميل أو رقم هاتفه..."

_BG = "#ffffff"
_ACTIVE = "#dbeafe"
_BORDER = "#93c5fd"
_TEXT = "#111827"
_MUTED = "#6b7280"
_DEBIT = "#b91c1c"
_CREDIT = "#15803d"
_ADD = "#1d4ed8"

_TASHKEEL = dict.fromkeys(
    list(range(0x064B, 0x0653)) + [0x0670, 0x0640]
)
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ة": "ه",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def normalize_text(text):
    """نص للبحث: بلا تشكيل ولا تطويل، موحّد الهمزات والأرقام، أحرف صغيرة."""
    return str(text or "").translate(_TASHKEEL).translate(_FOLD).lower().strip()


def _as_client(item):
    """يقبل (id, name, phone) أو قاموساً كاملاً ويرجع قاموساً موحّداً."""
    if isinstance(item, dict):
        client = dict(item)
    else:
        cid, name, phone = item[0], item[1], item[2] if len(item) > 2 else ""
        client = {"id": cid, "name": name, "phone": phone}

    client.setdefault("phone", "")
    client.setdefault("email", "")
    client["_blob"] = normalize_text(
        f"{client.get('name', '')} {client.get('phone', '')} "
        f"{client.get('email', '')}"
    )
    client["_name"] = normalize_text(client.get("name", ""))
    return client


def search_clients_in_memory(clients, query, limit=None):
    """
    يفلتر قائمة العملاء (قواميس موحّدة) حسب الاستعلام ويرتّبها:
    يبدأ بالاسم ← يحتوي الاسم ← بقية الحقول.
    """
    tokens = normalize_text(query).split()

    if not tokens:
        found = list(clients)
    else:
        ranked = []

        for client in clients:
            if not all(token in client["_blob"] for token in tokens):
                continue

            name = client["_name"]

            if name.startswith(tokens[0]):
                rank = 0
            elif all(token in name for token in tokens):
                rank = 1
            else:
                rank = 2

            ranked.append((rank, name, client))

        ranked.sort(key=lambda entry: (entry[0], entry[1]))
        found = [client for _rank, _name, client in ranked]

    return found if limit is None else found[:limit]


class ClientPicker(ctk.CTkFrame):

    MAX_ROWS = 7
    ROW_HEIGHT = 34

    # نصوص قابلة للتخصيص (يرثها SupplierPicker في الموردين)
    ADD_LABEL = "➕ إضافة «{name}» كعميل جديد"
    DEBIT_LABEL = "عليه"
    CREDIT_LABEL = "له"

    def __init__(self, parent, textvariable=None, on_select=None,
                 on_add_new=None, on_change=None, width=350, height=40,
                 placeholder=PLACEHOLDER, font=("Cairo", 14)):
        """
        on_select(client):  عند اختيار عميل من القائمة.
        on_change(client|None): كلما تغيّر العميل المطابق للنص (كتابة، اختيار،
                            أو تعيين برمجي)، وclient=None إن لم يعد النص مطابقاً.
        on_add_new(name):   عند اختيار «إضافة عميل جديد».
        """
        super().__init__(parent, fg_color="transparent")

        self.var = textvariable or ctk.StringVar()
        self.on_select = on_select
        self.on_add_new = on_add_new
        self.on_change = on_change
        self._last_id = None
        self._trace_id = self.var.trace_add("write", self._on_var_changed)

        self._clients = []
        self._shown = []            # العناصر الظاهرة حالياً (client | "add" | "more")
        self._rows = []
        self._active = -1
        self._popup = None
        self._popup_pressed = False
        self._close_job = None
        self._outside_binding = None

        self.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            self,
            textvariable=self.var,
            placeholder_text=placeholder,
            width=width,
            height=height,
            font=font,
            justify="right",
        )
        self.entry.grid(row=0, column=0, sticky="ew")

        self.arrow = ctk.CTkButton(
            self,
            text="▾",
            width=36,
            height=height,
            fg_color="#e5e7eb",
            hover_color="#d1d5db",
            text_color="#374151",
            font=("Cairo", 14, "bold"),
            command=self._toggle_all,
        )
        self.arrow.grid(row=0, column=1, padx=(6, 0))

        inner = self.entry._entry     # حقل tk الداخلي لـ CTkEntry
        inner.bind("<KeyRelease>", self._on_key_release, add="+")
        inner.bind("<Down>", self._on_down, add="+")
        inner.bind("<Up>", self._on_up, add="+")
        inner.bind("<Return>", self._on_return, add="+")
        inner.bind("<KP_Enter>", self._on_return, add="+")
        inner.bind("<Escape>", self._on_escape, add="+")
        inner.bind("<Tab>", lambda e: self._close(), add="+")
        inner.bind("<FocusOut>", self._on_focus_out, add="+")
        inner.bind("<Button-1>", self._on_click_entry, add="+")

    # ======================
    # البيانات
    # ======================
    def _on_var_changed(self, *_args):
        try:
            client = self.client()
        except tk.TclError:
            return

        client_id = client["id"] if client else None

        if client_id == self._last_id:
            return

        self._last_id = client_id

        if self.on_change:
            self.on_change(client)

    def set_clients(self, clients):
        self._clients = [_as_client(item) for item in clients]
        self._last_id = self.client_id()

        if self._popup is not None:
            self._refresh_popup(self.var.get())

    def refresh_clients(self, clients, select=None):
        """تحديث القائمة بعد إضافة عميل، مع اختيار عميل معيّن اختيارياً."""
        self.set_clients(clients)

        if select is not None:
            self.set(select)

    def get(self):
        return self.var.get().strip()

    def set(self, name):
        self.var.set(name or "")

    def client(self):
        """العميل المطابق للنص الحالي تماماً (قاموس) أو None."""
        wanted = normalize_text(self.var.get())

        if not wanted:
            return None

        for client in self._clients:
            if client["_name"] == wanted:
                return client

        return None

    def client_id(self):
        client = self.client()
        return client["id"] if client else None

    def focus_entry(self):
        self.entry.focus_set()

    # ======================
    # فتح/إغلاق القائمة
    # ======================
    def _on_click_entry(self, _event=None):
        # عند النقر على حقل فارغ نعرض آخر العملاء
        if self._popup is None and not self.var.get().strip():
            self.after(10, lambda: self._open(""))

    def _toggle_all(self):
        if self._popup is not None:
            self._close()
        else:
            self.entry.focus_set()
            self._open("")

    def _open(self, query):
        if not self._clients and not self.on_add_new:
            return

        if self._popup is None:
            top = self.winfo_toplevel()

            self._popup = tk.Frame(
                top,
                bg=_BG,
                highlightthickness=1,
                highlightbackground=_BORDER,
                highlightcolor=_BORDER,
                bd=0,
            )
            self._popup.bind(
                "<ButtonPress-1>", lambda e: self._mark_popup_press()
            )

            if self._outside_binding is None:
                self._outside_binding = (
                    top,
                    top.bind("<Button-1>", self._on_outside_click, add="+"),
                )

        self._refresh_popup(query)

    def _mark_popup_press(self):
        self._popup_pressed = True
        self.after(300, self._reset_popup_press)

    def _reset_popup_press(self):
        self._popup_pressed = False

    def _close(self, _event=None):
        if self._close_job is not None:
            try:
                self.after_cancel(self._close_job)
            except (tk.TclError, ValueError):
                pass
            self._close_job = None

        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass

        self._popup = None
        self._rows = []
        self._shown = []
        self._active = -1

    def _on_focus_out(self, _event=None):
        # تأخير بسيط كي لا يُغلق قبل أن يصل النقر لصف القائمة
        self._close_job = self.after(180, self._close_if_idle)

    def _close_if_idle(self):
        self._close_job = None

        if self._popup_pressed:
            return

        self._close()

    def _on_outside_click(self, event):
        if self._popup is None:
            return

        widget = str(event.widget)

        if widget.startswith(str(self._popup)):
            return

        if widget.startswith(str(self.entry)) or widget.startswith(str(self.arrow)):
            return

        self._close()

    def destroy(self):
        self._close()

        try:
            self.var.trace_remove("write", self._trace_id)
        except (tk.TclError, ValueError):
            pass

        if self._outside_binding is not None:
            top, binding_id = self._outside_binding
            self._outside_binding = None

            try:
                top.unbind("<Button-1>", binding_id)
            except (tk.TclError, ValueError):
                pass

        super().destroy()

    # ======================
    # بناء قائمة الاقتراحات
    # ======================
    def _refresh_popup(self, query):
        if self._popup is None:
            return

        for child in self._popup.winfo_children():
            child.destroy()

        query = (query or "").strip()
        matches = search_clients_in_memory(self._clients, query)

        shown = list(matches[:self.MAX_ROWS])
        hidden = len(matches) - len(shown)

        if hidden > 0:
            shown.append(("more", hidden))

        exact = self.client()

        if query and exact is None and self.on_add_new:
            shown.append(("add", query))

        if not shown:
            self._close()
            return

        self._shown = shown
        self._rows = []
        self._active = 0 if (query and matches) else -1

        for index, item in enumerate(shown):
            self._rows.append(self._build_row(index, item))

        self._paint_rows()
        self._place_popup(len(shown))

    def _build_row(self, index, item):
        row = tk.Frame(self._popup, bg=_BG, height=self.ROW_HEIGHT)
        row.pack(fill="x")
        row.pack_propagate(False)

        widgets = [row]

        if isinstance(item, tuple) and item[0] == "more":
            label = tk.Label(
                row, text=f"… و{item[1]} نتيجة أخرى — تابع الكتابة للتضييق",
                bg=_BG, fg=_MUTED, font=("Cairo", 10), anchor="e",
            )
            label.pack(side="right", fill="x", expand=True, padx=10)
            return {"frame": row, "widgets": widgets, "selectable": False}

        if isinstance(item, tuple) and item[0] == "add":
            label = tk.Label(
                row, text=self.ADD_LABEL.format(name=item[1]),
                bg=_BG, fg=_ADD, font=("Cairo", 12, "bold"), anchor="e",
            )
            label.pack(side="right", fill="x", expand=True, padx=10)
            widgets.append(label)
            self._bind_row(widgets, index)
            return {"frame": row, "widgets": widgets, "selectable": True}

        name = tk.Label(
            row, text=item.get("name", ""), bg=_BG, fg=_TEXT,
            font=("Cairo", 12, "bold"), anchor="e",
        )
        name.pack(side="right", padx=(4, 10))
        widgets.append(name)

        phone = item.get("phone") or ""

        if phone:
            phone_label = tk.Label(
                row, text=f"📞 {phone}", bg=_BG, fg=_MUTED,
                font=("Cairo", 10), anchor="e",
            )
            phone_label.pack(side="right", padx=(0, 6))
            widgets.append(phone_label)

        state = item.get("balance_state")
        balance = item.get("balance") or 0

        if state in ("debit", "credit") and balance:
            text = (
                f"{self.DEBIT_LABEL} {format_money(abs(balance))}"
                if state == "debit"
                else f"{self.CREDIT_LABEL} {format_money(abs(balance))}"
            )
            balance_label = tk.Label(
                row, text=text, bg=_BG,
                fg=_DEBIT if state == "debit" else _CREDIT,
                font=("Cairo", 10, "bold"),
            )
            balance_label.pack(side="left", padx=10)
            widgets.append(balance_label)

        self._bind_row(widgets, index)
        return {"frame": row, "widgets": widgets, "selectable": True}

    def _bind_row(self, widgets, index):
        for widget in widgets:
            widget.bind("<Enter>", lambda e, i=index: self._set_active(i))
            widget.bind("<ButtonPress-1>", lambda e: self._mark_popup_press())
            widget.bind(
                "<ButtonRelease-1>", lambda e, i=index: self._choose(i)
            )
            widget.configure(cursor="hand2")

    def _paint_rows(self):
        for index, row in enumerate(self._rows):
            color = _ACTIVE if index == self._active else _BG

            for widget in row["widgets"]:
                try:
                    widget.configure(bg=color)
                except tk.TclError:
                    pass

    def _set_active(self, index):
        if 0 <= index < len(self._rows) and self._rows[index]["selectable"]:
            self._active = index
            self._paint_rows()

    def _place_popup(self, row_count):
        top = self.winfo_toplevel()
        self.update_idletasks()

        x = self.entry.winfo_rootx() - top.winfo_rootx()
        y = (
            self.entry.winfo_rooty() - top.winfo_rooty()
            + self.entry.winfo_height() + 2
        )
        width = max(self.entry.winfo_width() + self.arrow.winfo_width() + 6, 240)

        self._popup.place(
            x=x, y=y, width=width, height=row_count * self.ROW_HEIGHT + 2
        )
        self._popup.lift()

    # ======================
    # اختيار عنصر
    # ======================
    def _choose(self, index):
        self._popup_pressed = False

        if not (0 <= index < len(self._shown)):
            return

        item = self._shown[index]

        if isinstance(item, tuple):
            if item[0] == "add":
                typed = item[1]
                self._close()

                if self.on_add_new:
                    self.on_add_new(typed)

            return

        self.var.set(item["name"])
        self._close()
        self.entry.focus_set()

        try:
            self.entry.icursor("end")
        except (AttributeError, tk.TclError):
            pass

        if self.on_select:
            self.on_select(item)

    # ======================
    # لوحة المفاتيح
    # ======================
    def _on_key_release(self, event):
        if event.keysym in (
            "Down", "Up", "Return", "KP_Enter", "Escape", "Tab",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Left", "Right", "Home", "End",
        ):
            return

        text = self.var.get()

        if not text.strip():
            self._close()
            return

        self._open(text)

    def _move(self, step):
        if self._popup is None:
            self._open(self.var.get())
            return

        count = len(self._rows)

        if not count:
            return

        index = self._active

        for _ in range(count):
            index = (index + step) % count

            if self._rows[index]["selectable"]:
                self._active = index
                break

        self._paint_rows()

    def _on_down(self, _event=None):
        self._move(1)
        return "break"

    def _on_up(self, _event=None):
        self._move(-1)
        return "break"

    def _on_return(self, _event=None):
        if self._popup is not None and self._active >= 0:
            self._choose(self._active)
            return "break"

        return None

    def _on_escape(self, _event=None):
        if self._popup is not None:
            self._close()
            return "break"

        return None
