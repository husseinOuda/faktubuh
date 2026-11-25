# ui/components/supplier_dialogs.py
"""
نوافذ ومكوّنات الموردين (مشتركة بين صفحة الموردين وأوامر الشراء):

  SupplierFormDialog(parent, on_done=callback(supplier_id), supplier=None, name="")
      إضافة / تعديل مورد.

  SupplierPicker
      بحث ذكي لاختيار المورد (نفس ClientPicker بنصوص الموردين).

  SupplierPaymentDialog(parent, on_done=callback(voucher_id), supplier_id=None,
                        purchase_order_id=None)
      سند صرف لمورد: سداد أمر شراء محدد أو دفعة على حساب المورد.
"""

from datetime import date

from database import PAYMENT_METHODS, payment_method_label
from purchases_db import (
    add_supplier,
    get_supplier_open_orders,
    get_suppliers_full,
    add_supplier_payment,
    get_purchase_order,
    update_supplier,
)
from ui.components.client_picker import ClientPicker
from ui.components.dialogs import FormDialog
from ui.components.invoice_utils import format_money, parse_number

NO_ORDER = "— دفعة على حساب المورد (بدون أمر شراء) —"
_METHOD_BY_LABEL = {label: code for code, label in PAYMENT_METHODS.items()}


class SupplierPicker(ClientPicker):
    """اختيار المورد ببحث ذكي: يرث ClientPicker ويغيّر النصوص فقط."""

    ADD_LABEL = "➕ إضافة «{name}» كمورد جديد"
    DEBIT_LABEL = "مستحق"
    CREDIT_LABEL = "دفعة مقدّمة"

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("placeholder", "🔍 اكتب اسم المورد أو رقم هاتفه...")
        super().__init__(parent, **kwargs)

    def supplier(self):
        return self.client()

    def supplier_id(self):
        return self.client_id()


# =====================================================
# إضافة / تعديل مورد
# =====================================================
class SupplierFormDialog(FormDialog):

    def __init__(self, parent, on_done=None, supplier=None, name=""):
        self.supplier = supplier

        super().__init__(
            parent,
            "✏ تعديل بيانات المورد" if supplier else "➕ مورد جديد",
            width=520,
            on_done=on_done,
        )

        data = supplier or {}

        self.add_entry(
            "name", "اسم المورد *",
            initial=data.get("name", name),
        )
        self.add_entry(
            "phone", "رقم الهاتف",
            initial=data.get("phone", ""),
        )
        self.add_entry(
            "email", "البريد الإلكتروني",
            initial=data.get("email", ""),
            placeholder="name@example.com",
        )
        self.add_entry(
            "address", "العنوان",
            initial=data.get("address", ""),
        )
        self.add_textbox(
            "notes", "ملاحظات",
            initial=data.get("notes", ""),
            height=84,
        )

        self.finish_layout()
        self._fields["name"][1].focus_set()

    def save(self):
        values = dict(
            name=self.value("name"),
            phone=self.value("phone"),
            address=self.value("address"),
            email=self.value("email"),
            notes=self.value("notes"),
        )

        if self.supplier:
            update_supplier(self.supplier["id"], **values)
            return self.supplier["id"]

        return add_supplier(**values)


# =====================================================
# سند صرف لمورد
# =====================================================
class SupplierPaymentDialog(FormDialog):

    def __init__(self, parent, on_done=None, supplier_id=None,
                 purchase_order_id=None):
        super().__init__(parent, "💸 سند صرف لمورد", on_done=on_done)

        suppliers = get_suppliers_full()

        initial_name = ""
        initial_order_id = purchase_order_id

        if purchase_order_id:
            order = get_purchase_order(purchase_order_id)

            if order:
                supplier_id = order["supplier_id"]
                initial_name = order["supplier"]

        if not initial_name and supplier_id:
            for item in suppliers:
                if item["id"] == supplier_id:
                    initial_name = item["name"]
                    break

        self.add_client_picker(
            "supplier", "المورد", suppliers,
            initial=initial_name,
            on_change=self._on_supplier_changed,
            picker_class=SupplierPicker,
        )

        self._order_map = {}
        self.add_menu(
            "order", "أمر الشراء المراد سداده", [NO_ORDER],
            command=self._on_order_changed,
        )
        self.add_entry("amount", "المبلغ (₪)")
        self.add_entry(
            "date", "التاريخ (YYYY-MM-DD)",
            initial=date.today().isoformat(),
        )
        self.add_menu(
            "method", "طريقة الدفع", list(PAYMENT_METHODS.values()),
            initial=payment_method_label("cash"),
        )
        self.add_entry("reference", "رقم الشيك / المرجع (اختياري)")
        self.add_textbox("notes", "البيان / ملاحظات")

        self._load_orders(initial_order_id)

        if initial_order_id and self.value("order") != NO_ORDER:
            self._on_order_changed(self.value("order"))

        self.finish_layout()

    def _supplier_id(self):
        return self._fields["supplier"][1].client_id()

    def _on_supplier_changed(self, _value=None):
        self._load_orders(None)

    def _load_orders(self, select_id):
        supplier_id = self._supplier_id()
        orders = get_supplier_open_orders(supplier_id) if supplier_id else []

        self._order_map = {}
        selected = NO_ORDER

        for order in orders:
            invoice_no = order["supplier_invoice_no"]
            label = (
                f"{order['po_number']}"
                f"{'  |  فاتورة المورد ' + invoice_no if invoice_no else ''}"
                f"  |  المتبقي {format_money(order['remaining'])}"
            )
            self._order_map[label] = order

            if order["id"] == select_id:
                selected = label

        self.set_menu_values(
            "order", [NO_ORDER] + list(self._order_map), selected
        )

    def _on_order_changed(self, value):
        order = self._order_map.get(value)

        if order:
            self.set_entry("amount", f"{order['remaining']:.2f}")

    def save(self):
        supplier_id = self._supplier_id()

        if not supplier_id:
            raise ValueError("يرجى اختيار مورد من القائمة")

        order = self._order_map.get(self.value("order"))
        amount = parse_number(self.value("amount"), "المبلغ", positive=True)

        return add_supplier_payment(
            supplier_id,
            amount,
            date=self.value("date"),
            payment_method=_METHOD_BY_LABEL.get(self.value("method"), "cash"),
            reference=self.value("reference"),
            notes=self.value("notes"),
            purchase_order_id=order["id"] if order else None,
        )
