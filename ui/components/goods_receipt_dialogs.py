# ui/components/goods_receipt_dialogs.py
"""
نافذة استلام بضاعة:

  ReceiveGoodsDialog(parent, on_done=callback(receipt_id),
                     purchase_order_id=None, supplier_id=None)

  تختار أمر شراء (أو يأتي محدداً)، فتظهر أصنافه مع المطلوب والمستلم سابقاً
  والمتبقي، وتُدخل الكمية المستلمة الآن لكل صنف (الافتراضي = المتبقي).
  يمكن الاستلام على دفعات (استلام جزئي) حتى يكتمل الأمر.

  الاستلام بالباركود: امسح الصنف بقارئ USB (في حقل الباركود ثم Enter) أو
  بالكاميرا «📷 مسح بالكاميرا»؛ كل مسح يزيد الكمية المستلمة للصنف 1، ولا
  يتجاوز المتبقي. عند أول مسح تُصفَّر الكميات الافتراضية لتبدأ العدّ من صفر.
"""

from datetime import date

import customtkinter as ctk

from ui.components.barcode_dialog import open_barcode_scanner
from purchases_db import (
    add_goods_receipt,
    get_po_receivable_items,
    get_receivable_orders,
)
from ui.components.dialogs import ENTRY_FONT, FormDialog
from tkinter import messagebox

from ui.components.invoice_utils import parse_number

NO_ORDER = "— لا توجد أوامر شراء بانتظار الاستلام —"


def _qty(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:g}"


class ReceiveGoodsDialog(FormDialog):

    def __init__(self, parent, on_done=None, purchase_order_id=None,
                 supplier_id=None):
        super().__init__(
            parent, "📦 استلام بضاعة", width=640,
            save_text="📦 تسجيل الاستلام", on_done=on_done,
        )

        self._order_map = {}
        self._qty_entries = []      # [{id, name, remaining, barcode, entry}]
        self._scan_mode = False     # بدأ العدّ بالمسح (الكميات من الصفر)

        orders = get_receivable_orders(supplier_id)

        labels = []
        selected = None

        for order in orders:
            label = (
                f"{order['po_number']}  |  {order['supplier']}"
                f"  |  مستلم {_qty(order['received_qty'])} "
                f"من {_qty(order['ordered_qty'])}"
            )
            self._order_map[label] = order
            labels.append(label)

            if order["id"] == purchase_order_id:
                selected = label

        self.add_menu(
            "order", "أمر الشراء", labels or [NO_ORDER],
            initial=selected, command=self._on_order_changed,
        )

        self.add_entry(
            "date", "تاريخ الاستلام (YYYY-MM-DD)",
            initial=date.today().isoformat(),
        )

        self.barcode_entry = self.add_entry(
            "barcode", "الباركود (قارئ USB ثم Enter، أو الكاميرا)",
            placeholder="🔎 امسح باركود الصنف المستلم",
        )
        self.barcode_entry.bind("<Return>", self._on_barcode_enter)
        self.barcode_entry.bind("<KP_Enter>", self._on_barcode_enter)

        ctk.CTkButton(
            self.body, text="📷 مسح بالكاميرا",
            command=self._scan_with_camera,
            fg_color="#2563eb", hover_color="#1d4ed8", height=36,
            corner_radius=10, font=("Cairo", 13, "bold"),
        ).grid(row=self._row, column=0, sticky="ew", pady=(6, 0))
        self._row += 1

        self.scan_status = ctk.CTkLabel(
            self.body, text="", font=("Cairo", 12, "bold"),
            text_color="#0f2a5c", anchor="e", justify="right",
            wraplength=self._width - 60,
        )
        self.scan_status.grid(row=self._row, column=0, sticky="ew")
        self._row += 1

        self._add_label("الأصناف — أدخل الكمية المستلمة الآن لكل صنف")

        self.items_frame = ctk.CTkScrollableFrame(
            self.body, height=230, fg_color="#ffffff",
            border_width=1, border_color="#d1d5db",
        )
        self.items_frame.grid(row=self._row, column=0, sticky="ew")
        self.items_frame.grid_columnconfigure(0, weight=1)
        self._row += 1

        self.add_textbox("notes", "ملاحظات (اختياري)", height=60)

        self._load_items()
        self.finish_layout()

    # ---- الأصناف ----
    def _selected_order(self):
        return self._order_map.get(self.value("order"))

    def _on_order_changed(self, _value=None):
        self._load_items()

    def _load_items(self):
        for widget in self.items_frame.winfo_children():
            widget.destroy()

        self._qty_entries = []
        self._scan_mode = False
        order = self._selected_order()

        if not order:
            ctk.CTkLabel(
                self.items_frame,
                text="لا توجد أصناف للاستلام",
                font=("Cairo", 13), text_color="#6b7280",
            ).grid(row=0, column=0, pady=20)
            return

        header = ctk.CTkFrame(self.items_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="المستلم الآن", width=90,
            font=("Cairo", 12, "bold"), text_color="#374151",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="الصنف  (المتبقي من المطلوب)",
            font=("Cairo", 12, "bold"), text_color="#374151", anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        row = 1

        for item in get_po_receivable_items(order["id"]):
            line = ctk.CTkFrame(self.items_frame, fg_color="transparent")
            line.grid(row=row, column=0, sticky="ew", padx=6, pady=2)
            line.grid_columnconfigure(1, weight=1)

            entry = ctk.CTkEntry(
                line, width=90, height=34, corner_radius=8,
                font=ENTRY_FONT, justify="center",
            )
            entry.grid(row=0, column=0, sticky="w")

            remaining = item["remaining"]

            if remaining > 0:
                entry.insert(0, _qty(remaining))
            else:
                entry.insert(0, "0")
                entry.configure(state="disabled")

            text = f"{item['name']}   ({_qty(remaining)} من {_qty(item['ordered'])})"

            ctk.CTkLabel(
                line, text=text, font=("Cairo", 13), anchor="e",
                text_color="#111827" if remaining > 0 else "#9ca3af",
            ).grid(row=0, column=1, sticky="ew", padx=(10, 0))

            self._qty_entries.append({
                "id": item["po_item_id"],
                "name": item["name"],
                "remaining": remaining,
                "barcode": item.get("barcode", ""),
                "entry": entry,
            })
            row += 1

    # ---- الباركود ----
    def _set_status(self, text, ok=True):
        self.scan_status.configure(
            text=text, text_color="#15803d" if ok else "#b91c1c"
        )

    def _on_barcode_enter(self, _event=None):
        code = self.barcode_entry.get().strip()
        self.barcode_entry.delete(0, "end")

        if code:
            self.handle_barcode(code)

        return "break"

    def _scan_with_camera(self):
        if not self._selected_order():
            messagebox.showinfo(
                "اختر أمر شراء", "اختر أمر الشراء أولاً.", parent=self
            )
            return

        open_barcode_scanner(self, self.handle_barcode, continuous=True)

    def handle_barcode(self, code):
        """كل مسح يزيد كمية الصنف المطابق 1 (ضمن المتبقي). يرجع رسالة الحالة."""
        code = str(code or "").strip()

        if not code:
            return ""

        match = next(
            (e for e in self._qty_entries
             if e["barcode"] and e["barcode"] == code),
            None,
        )

        if match is None:
            message = f"❌ الباركود {code} غير موجود في أصناف هذا الأمر"
            self._set_status(message, ok=False)
            self.bell()
            return message

        if not self._scan_mode:
            # أول مسح: ابدأ العدّ من صفر بدل الكميات الافتراضية (= المتبقي)
            self._scan_mode = True

            for entry_info in self._qty_entries:
                if entry_info["remaining"] > 0:
                    entry_info["entry"].delete(0, "end")
                    entry_info["entry"].insert(0, "0")

        entry = match["entry"]

        try:
            current = float(entry.get().strip() or 0)
        except ValueError:
            current = 0.0

        if current + 1 > match["remaining"] + 1e-9:
            message = (
                f"⚠ «{match['name']}»: بلغت الكمية المتبقية للاستلام "
                f"({_qty(match['remaining'])})"
            )
            self._set_status(message, ok=False)
            self.bell()
            return message

        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, _qty(current + 1))

        message = (
            f"✔ {match['name']} — {_qty(current + 1)} "
            f"من {_qty(match['remaining'])}"
        )
        self._set_status(message)
        return message

    # ---- الحفظ ----
    def save(self):
        order = self._selected_order()

        if not order:
            raise ValueError("اختر أمر شراء بانتظار الاستلام")

        lines = []

        for info in self._qty_entries:
            text = info["entry"].get().strip()

            if not text:
                continue

            qty = parse_number(text, f"كمية «{info['name']}»")
            lines.append({"po_item_id": info["id"], "qty": qty})

        return add_goods_receipt(
            order["id"], self.value("date"), lines, self.value("notes")
        )
