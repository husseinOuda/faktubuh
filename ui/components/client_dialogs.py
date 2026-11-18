# ui/components/client_dialogs.py
"""
نافذة إضافة / تعديل عميل — مشتركة بين صفحة العملاء وصفحة الفواتير
وصفحة تفاصيل العميل.

  ClientFormDialog(parent, on_done=callback(client_id), client=None, name="")

  - client: قاموس عميل (من database.get_client / get_clients_full) لوضع التعديل.
  - name:   اسم مبدئي عند الإضافة (من خيار «إضافة عميل جديد» في البحث الذكي).
"""

from database import add_client, update_client
from ui.components.dialogs import FormDialog


class ClientFormDialog(FormDialog):

    def __init__(self, parent, on_done=None, client=None, name=""):
        self.client = client

        super().__init__(
            parent,
            "✏ تعديل بيانات العميل" if client else "➕ عميل جديد",
            width=520,
            on_done=on_done,
        )

        data = client or {}

        self.add_entry(
            "name", "اسم العميل *",
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

        if self.client:
            update_client(self.client["id"], **values)
            return self.client["id"]

        return add_client(**values)
