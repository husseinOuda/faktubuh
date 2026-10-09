# ui/clients_page.py

import customtkinter as ctk
from tkinter import ttk
from tkinter import messagebox

from database import (
    add_client,
    get_clients,
    delete_client,
    search_clients,
    update_client
)


class ClientsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)

        self.app = app

        self.selected_client_id = None

        self.client_map = {}

        self.build_ui()
        self.load_clients()

    # ======================
    # بناء الواجهة 
    # ======================
    def build_ui(self):

        # العنوان
        title = ctk.CTkLabel(
            self,
            text="👥 إدارة العملاء",
            font=("Arial", 28, "bold")
        )
        title.pack(pady=20)

        # ======================
        # النموذج
        # ======================
        form_frame = ctk.CTkFrame(self)
        form_frame.pack(fill="x", padx=20, pady=10)

        # اسم العميل
        self.name_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="اسم العميل",
            width=250,
            height=40
        )
        self.name_entry.grid(row=0, column=0, padx=10, pady=10)

        # رقم الهاتف 
        self.phone_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="رقم الهاتف",
            width=250,
            height=40
        )
        self.phone_entry.grid(row=0, column=1, padx=10, pady=10)

        # زر إضافة
        add_btn = ctk.CTkButton(
            form_frame,
            text="➕ إضافة عميل",
            command=self.add_client_action,
            height=40,
            width=150,
            fg_color="#16a34a",
            hover_color="#15803d"
        )
        add_btn.grid(row=0, column=2, padx=10)

        # زر تعديل
        update_btn = ctk.CTkButton(
            form_frame,
            text="✏️ تعديل",
            command=self.edit_client,
            height=40,
            width=120,
            fg_color="#f59e0b",
            hover_color="#d97706"
        )
        update_btn.grid(row=0, column=3, padx=10)

        # زر حذف
        delete_btn = ctk.CTkButton(
            form_frame,
            text="❌ حذف",
            command=self.delete_client_action,
            height=40,
            width=120,
            fg_color="#dc2626",
            hover_color="#b91c1c"
        )
        delete_btn.grid(row=0, column=4, padx=10)

        # ======================
        # البحث
        # ======================
        search_frame = ctk.CTkFrame(self)
        search_frame.pack(fill="x", padx=20, pady=10)

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 البحث باسم العميل أو رقم الهاتف",
            height=45,
            corner_radius=12,
            font=("Cairo", 14)
        )
        self.search_entry.pack(fill="x", padx=10, pady=10)

        self.search_entry.bind("<KeyRelease>", self.search_clients_action)

        # ======================
        # جدول العملاء
        # ======================
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=20, pady=10)

        columns = ("id", "name", "phone")

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=15
        )

        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="اسم العميل")
        self.tree.heading("phone", text="رقم الهاتف")

        self.tree.column("name", width=300, anchor="center")
        self.tree.column("phone", width=250, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        # عند اختيار صف
        self.tree.bind("<<TreeviewSelect>>", self.select_client)

    # ======================
    # تحميل العملاء 
    # ======================
    def load_clients(self):

        # حذف القديم
        for item in self.tree.get_children():
            self.tree.delete(item)

        clients = get_clients()

        for client in clients:
            self.tree.insert(
                "",
                "end",
                values=(
                    client[0],
                    client[1],
                    client[2]
                )
            )


    # ======================
    # إضافة عميل
    # ======================
    def add_client_action(self):

        name = self.name_entry.get().strip()
        phone = self.phone_entry.get().strip()

        if not name:
            messagebox.showerror("خطأ", "يرجى إدخال اسم العميل")
            return

        add_client(name, phone)

        self.clear_fields()
        self.load_clients()

        messagebox.showinfo("تم", "تم إضافة العميل بنجاح")

    # ======================
    # اختيار عميل
    # ======================
    def select_client(self, event):

        selected = self.tree.selection()

        if not selected:
            return

        values = self.tree.item(selected[0], "values")

        self.selected_client_id = values[0]

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, values[1])

        self.phone_entry.delete(0, "end")
        self.phone_entry.insert(0, values[2])


    # ======================
    # ✏️ تعديل عميل 
    # ======================
    def edit_client(self):

        if not self.selected_client_id:
            messagebox.showerror("خطأ", "اختر عميل أولاً")
            return

        name = self.name_entry.get().strip()
        phone = self.phone_entry.get().strip()

        if not name:
            messagebox.showerror("خطأ", "اسم العميل مطلوب")
            return

        update_client(
            self.selected_client_id,
            name,
            phone
        )

        self.load_clients()
        self.clear_fields()

        messagebox.showinfo("تم", "تم تعديل بيانات العميل")

    # ======================
    # حذف عميل
    # ======================
    def delete_client_action(self):

        if not self.selected_client_id:
            messagebox.showerror("خطأ", "اختر عميل أولاً")
            return

        confirm = messagebox.askyesno(
            "تأكيد",
            "هل أنت متأكد من حذف العميل؟"
        )

        if not confirm:
            return

        delete_client(self.selected_client_id)

        self.load_clients()
        self.clear_fields()

        messagebox.showinfo("تم", "تم حذف العميل")

    # ======================
    # 🔍 البحث عن عميل 
    # ======================
    def search_clients_action(self, event=None):

        keyword = self.search_entry.get().strip()

        if not keyword:
            self.load_clients()
            return

        results = search_clients(keyword)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for client in results:
            self.tree.insert(
                "",
                "end",
                values=(
                    client[0],
                    client[1],
                    client[2]
                )
            )

    # ======================
    # تنظيف الحقول
    # ======================
    def clear_fields(self):

        self.selected_client_id = None

        self.name_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
    

