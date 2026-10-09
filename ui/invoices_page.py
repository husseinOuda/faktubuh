# ui/invoices_page.py

import os
import customtkinter as ctk
from tkinter import messagebox, ttk
from datetime import date

from pdf_generator import (
    generate_pdf,
    generate_temp_pdf
)

from database import (
    get_clients,
    save_invoice,
    get_invoices,
    delete_invoice,
    get_invoice_by_id,
    get_invoice_items,
    get_invoice_info,
    add_client,
    update_invoice
)

from theme import ENTRY_STYLE, PRIMARY_BTN, DANGER_BTN

from ui.reports_page import export_invoices_excel

class InvoicesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        
        self.app = app

        self.items = []
        self.edit_mode = False
        self.edit_invoice_id = None

        # =========================
        # HEADER
        # =========================
        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text="🧾 إنشاء الفواتير",
            font=("Cairo", 28, "bold"),
            text_color="#111827"
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="إنشاء الفواتير للعملاء بسهولة",
            font=("Cairo", 14),
            text_color="#6b7280"
        ).pack(anchor="w")

        # إطار المحتوى 
        # ======================
        content_frame = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )
        content_frame.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=10
        )

        content_frame.grid_columnconfigure(
            0,
            weight=1
        )

        content_frame.grid_columnconfigure(
            1,
            weight=2
        )

        left_panel = ctk.CTkFrame(
            content_frame
        )
        left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0,10)
        )

        right_panel = ctk.CTkFrame(
            content_frame
        )
        right_panel.grid(
            row=0,
            column=1,
            sticky="nsew"
        )

        left_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)

        # ======================
        # العملاء
        # ======================
        clients_frame = ctk.CTkFrame(left_panel)
        clients_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            clients_frame,
            text="👤 العميل"
        ).pack(anchor="w", padx=10)

        self.client_var = ctk.StringVar()

        clients = get_clients()

        self.client_map = {
            name: cid for cid, name, phone in clients
        }

        client_names = list(self.client_map.keys())

        self.client_combo = ctk.CTkComboBox(
            clients_frame,
            values=client_names,
            variable=self.client_var,
            width=350,
            height=40
        )

        self.client_combo.pack(padx=10, pady=5)

        ctk.CTkButton(
            clients_frame,
            text="➕ عميل جديد",
            command=self.open_add_client_window,
            **PRIMARY_BTN
        ).pack(pady=5)

        # =========================
        # TREEVIEW STYLE
        # =========================
        style = ttk.Style()

        style.theme_use("default")
        
        style.configure(
            "Treeview",
            rowheight=35,
            font=("Cairo", 12)
        )

        style.map(
            "Treeview",
            background=[("selected", "#2563eb")]
        )

        style.configure(
            "Treeview.Heading",
            font=("Cairo", 13, "bold")
        )

        form_frame = ctk.CTkFrame(left_panel)
        form_frame.pack(
            fill="x",
            padx=15,
            pady=10
        )

        form_frame.grid_columnconfigure(0, weight=1)
        form_frame.grid_columnconfigure(1, weight=1)

        # ======================
        # إدخال صنف
        # ======================
        self.item_name = ctk.CTkEntry(
            form_frame,
            placeholder_text="اسم الصنف",
            **ENTRY_STYLE
        )
        self.item_name.grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.item_desc = ctk.CTkEntry(
            form_frame,
            placeholder_text="الوصف",
            **ENTRY_STYLE
        )
        self.item_desc.grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.qty = ctk.CTkEntry(
            form_frame,
            placeholder_text="الكمية",
            **ENTRY_STYLE
        )
        self.qty.grid(
            row=1,
            column=0,
            padx=5,
            pady=5,
            sticky="ew"
        )

        self.price = ctk.CTkEntry(
            form_frame,
            placeholder_text="السعر",
            **ENTRY_STYLE
        )
        self.price.grid(
            row=1,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        ctk.CTkButton(
            form_frame,
            text="➕ إضافة صنف",
            command=self.add_item,
            **PRIMARY_BTN
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            pady=15
        )

        # ======================
        # جدول الأصناف
        # ======================
        ctk.CTkLabel(
            right_panel,
            text="📋 الأصناف المضافة",
            font=("Cairo", 18, "bold")
        ).pack(
            anchor="w",
            padx=15, 
            pady=(10,5)
        )

        self.items_table = ttk.Treeview(
            right_panel,
            columns=(
                "name",
                "desc",
                "qty",
                "price",
                "total"
            ),
            show="headings",
            height=8
        )

        self.items_table.heading(
            "name",
            text="الصنف"
        )

        self.items_table.heading(
            "desc",
            text="الوصف"
        )

        self.items_table.heading(
            "qty",
            text="الكمية"
        )

        self.items_table.heading(
            "price",
            text="السعر"
        )

        self.items_table.heading(
            "total",
            text="الإجمالي"
        )

        self.items_table.pack(
            fill="x",
            padx=10,
            pady=10
        )

        # ======================
        # الإجمالي
        # ======================
        self.total_label = ctk.CTkLabel(
            right_panel,
            text="الإجمالي: 0 ₪",
            font=("Cairo", 18, "bold"),
            text_color="#2563eb"
        )
        self.total_label.pack(pady=10)

        # ======================
        # تحسين عرض الجدول 
        # ======================
        self.items_table.column(
            "name",
            width=180,
            anchor="center"
        )

        self.items_table.column(
            "desc",
            width=220,
            anchor="center"
        )

        self.items_table.column(
            "qty",
            width=80,
            anchor="center"
        )

        self.items_table.column(
            "price",
            width=100,
            anchor="center"
        )

        self.items_table.column(
            "total",
            width=120,
            anchor="center"
        )

        # ======================
        # أزرار
        # ======================
        buttons_frame = ctk.CTkFrame(
            left_panel,
            fg_color="transparent"
        )
        buttons_frame.pack(
            fill="x",
            padx=10,
            pady=15
        )
        buttons_frame.grid_columnconfigure(0, weight=1)
        buttons_frame.grid_columnconfigure(1, weight=1)

        self.save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 حفظ الفاتورة",
            command=self.save_invoice,
            **PRIMARY_BTN
        )
        self.save_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        ctk.CTkButton(
            buttons_frame,
            text="🖨️ معاينة وطباعة",
            command=self.preview_and_print,
            **PRIMARY_BTN
        ).grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        ctk.CTkButton(
            buttons_frame,
            text="👁️ معاينة الفاتورة",
            command=self.preview_invoice,
            **PRIMARY_BTN
        ).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkButton(
            buttons_frame, 
            text="📊 تصدير Excel", 
            command=export_invoices_excel, 
            **PRIMARY_BTN
        ).grid(row=1, column=1, padx=5, pady=5, sticky="ew")


    # ======================
    # إضافة صنف
    # ======================
    def add_item(self):
        try:
            name = self.item_name.get()
            desc = self.item_desc.get()
            qty = int(self.qty.get())
            price = float(self.price.get())
            
            total = qty * price

            self.items.append({
                "name": name,
                "desc": desc,
                "qty": qty,
                "price": price,
                "total": total
            })
            self.clear_inputs()
            self.refresh_items()
        except:
            messagebox.showerror("خطأ", "تحقق من البيانات")

    # ======================
    # تحديث جدول الأصناف
    # ======================
    def refresh_items(self):
        # تنظيف الجدول 
        for item in self.items_table.get_children():
            self.items_table.delete(item)

        total = 0

        for item in self.items:

            self.items_table.insert(
                "",
                "end",
                values=(
                    item["name"],
                    item["desc"],
                    item["qty"],
                    item["price"],
                    item["total"]
                )
            )
            total += item["total"]

        self.total_label.configure(text=f"الإجمالي: {total}")

    def remove_item(self, index):
        self.items.pop(index)
        self.refresh_items()

    # ======================
    # معاينة الفاتورة
    # ======================
    def preview_invoice(self):

        if not self.items:
            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف للمعاينة"
            )
            return

        client_name = self.client_var.get()

        # إنشاء نافذة
        preview = ctk.CTkToplevel(self)

        preview.title("معاينة الفاتورة")

        preview.geometry("700x500")

        # عنوان
        # ======================
        ctk.CTkLabel(
            preview,
            text="🧾 معاينة الفاتورة",
            font=("Cairo", 24, "bold")
        ).pack(pady=10)

        # بيانات العميل
        ctk.CTkLabel(
            preview,
            text=f"العميل: {client_name}",
            font=("Cairo", 18)
        ).pack()

        ctk.CTkLabel(
            preview,
            text=f"التاريخ: {date.today()}",
            font=("Cairo", 16)
        ).pack(pady=5)

        # جدول الأصناف
        # ======================
        frame = ctk.CTkFrame(preview)

        frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        # رؤوس الجدول
        headers = [
            "الصنف",
            "الوصف",
            "الكمية",
            "السعر",
            "الإجمالي"
        ]

        for col, header in enumerate(headers):

            ctk.CTkLabel(
                frame,
                text=header,
                font=("Cairo", 14, "bold")
            ).grid(
                row=0,
                column=col,
                padx=10,
                pady=10
            )

        # الأصناف
        total = 0

        for row, item in enumerate(self.items, start=1):

            values = [
                item["name"],
                item.get("desc", ""),
                item["qty"],
                item["price"],
                item["total"]
            ]

            total += item["total"]

            for col, value in enumerate(values):

                ctk.CTkLabel(
                    frame,
                    text=str(value)
                ).grid(
                    row=row,
                    column=col,
                    padx=10,
                    pady=5
                )

        # الإجمالي
        # ======================
        ctk.CTkLabel(
            preview,
            text=f"الإجمالي النهائي: {total} ₪",
            font=("Cairo", 18, "bold")
        ).pack(pady=10)

    
    # ======================
    # حفظ فاتورة جديدة أو تحديث فاتورة
    # ======================
    def save_invoice(self):

        if not self.items:
            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف في الفاتورة"
            )
            return

        client_name = self.client_var.get().strip()
        client_id = self.client_map.get(client_name)

        if not client_id:
            messagebox.showerror(
                "خطأ",
                "يرجى اختيار عميل صحيح"
            )
            return

        try:
            # تعديل فاتورة موجودة
            if self.edit_invoice_id is not None:

                update_invoice(
                    self.edit_invoice_id,
                    client_id,
                    str(date.today()),
                    self.items
                )

                message = "تم تعديل الفاتورة بنجاح"

            # إنشاء فاتورة جديدة
            else:

                save_invoice(
                    client_id,
                    str(date.today()),
                    self.items
                )

                message = "تم حفظ الفاتورة بنجاح"

        except Exception as e:
            messagebox.showerror(
                "خطأ",
                f"تعذر حفظ الفاتورة:\n{e}"
            )
            return

        # إعادة الصفحة إلى وضع الإنشاء الطبيعي
        self.items = []
        self.edit_mode = False
        self.edit_invoice_id = None

        self.save_btn.configure(
            text="💾 حفظ الفاتورة"
        )

        self.refresh_items()
        self.clear_inputs()
        self.client_var.set("")

        messagebox.showinfo("تم", message)

        # تحديث صفحة الفواتير المحفوظة إن كانت موجودة
        saved_page = self.app.pages.get("saved_invoices")

        if saved_page and saved_page.winfo_exists():
            saved_page.load_invoices()
    
    # ======================
    # تعديل فاتورة محفوظة
    # ======================
    def edit_invoice(self, invoice_id):

        # جلب بيانات الفاتورة
        invoice_info = get_invoice_info(invoice_id)

        if not invoice_info:
            messagebox.showerror(
                "خطأ",
                "تعذر العثور على الفاتورة"
            )
            return

        # جلب الأصناف
        items = get_invoice_items(invoice_id)

        invoice_number = invoice_info[1]
        client_name = invoice_info[2]

        # تفعيل وضع التعديل
        self.edit_mode = True
        self.edit_invoice_id = invoice_id

        # تحديد العميل
        self.client_var.set(client_name)

        # تحديث قائمة الأصناف في الذاكرة
        self.items = []

        for item in items:
            self.items.append({
                "name": item[0],
                "desc": item[1],
                "qty": item[2],
                "price": item[3],
                "total": item[4]
            })

        # عرض الأصناف وتحديث الإجمالي
        self.refresh_items()

        # تغيير نص زر الحفظ
        self.save_btn.configure(
            text="💾 حفظ التعديلات"
        )

        messagebox.showinfo(
            "تعديل",
            f"أنت الآن تعدل الفاتورة رقم {invoice_number}"
        )

    # ======================
    # معاينة قبل حفظ الفاتورة الحالية
    # ======================
    def preview_and_print(self):

        if not self.items:

            messagebox.showwarning(
                "تنبيه",
                "لا توجد أصناف"
            )

            return

        client_name = self.client_var.get()

        total = sum(
            item["total"]
            for item in self.items
        )

        # إنشاء PDF مؤقت
        pdf_path = generate_temp_pdf(
            client_name,
            self.items,
            total
        )

        # فتح الملف
        os.startfile(pdf_path)
    
    
    # ======================
    # طباعة مباشرة
    # ======================
    def print_invoice(self, invoice_id):

        invoices = get_invoices()

        target = None

        for inv in invoices:

            if inv[0] == invoice_id:
                target = inv
                break

        if not target:
            return

        invoice_number = target[1]
        client_name = target[2]

        items = get_invoice_items(invoice_id)

        file_name = generate_pdf(
            invoice_id,
            invoice_number,
            items,
            client_name
        )

        try:

            os.startfile(file_name, "print")

        except:

            messagebox.showerror(
                "خطأ",
                "تعذر بدء الطباعة"
            )

    # ======================
    # نافذة إضافة عميل
    # ======================
    def open_add_client_window(self):

        window = ctk.CTkToplevel(self)
        window.title("إضافة عميل")
        window.geometry("400x250")

        # الاسم
        name_entry = ctk.CTkEntry(
            window,
            placeholder_text="اسم العميل",
            width=300,
            **ENTRY_STYLE
        )
        name_entry.pack(pady=20)

        # الهاتف
        phone_entry = ctk.CTkEntry(
            window,
            placeholder_text="رقم الهاتف",
            width=300,
            **ENTRY_STYLE
        )
        phone_entry.pack(pady=10)

        # زر الحفظ
        ctk.CTkButton(
            window,
            text="💾 حفظ العميل",
            command=lambda: self.save_new_client(
                window,
                name_entry.get(),
                phone_entry.get()
            ),
            **PRIMARY_BTN
        ).pack(pady=20)
                

    # ======================
    # حفظ العميل الجديد
    # ======================
    def save_new_client(self, window, name, phone):

        name = name.strip()
        phone = phone.strip()

        if not name:
            messagebox.showerror(
                "خطأ",
                "يرجى إدخال اسم العميل"
            )
            return

        # حفظ العميل
        add_client(name, phone)

        # تحديث العملاء
        self.refresh_clients_list()

        # اختيار العميل الجديد تلقائياً
        self.client_var.set(name)

        messagebox.showinfo(
            "تم",
            "تم إضافة العميل بنجاح"
        )

        window.destroy()

    # ======================
    # تحديث قائمة العملاء
    # ======================
    def refresh_clients_list(self):

        clients = get_clients()

        self.client_map = {
            name: cid for cid, name, phone in clients
        }

        client_names = list(self.client_map.keys())

        self.client_combo.configure(
            values=client_names
        )        

    # ======================
    # تنظيف الحقول
    # ======================
    def clear_inputs(self):
        self.item_name.delete(0, "end")
        self.item_desc.delete(0, "end")
        self.qty.delete(0, "end")
        self.price.delete(0, "end")
        
