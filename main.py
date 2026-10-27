# main.py

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from database import (
    create_tables,
    create_user,
    login,
    migrate_database
)

from pdf_generator import generate_pdf
from theme import BTN_STYLE

from ui.saved_invoices_page import SavedInvoicesPage
from ui.invoices_page import InvoicesPage
from ui.clients_page import ClientsPage
from ui.reports_page import ReportsPage

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


# ======================
# شاشة تسجيل الدخول
# ======================
class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("تسجيل الدخول")
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        main_frame = ctk.CTkFrame(root)
        main_frame.pack(fill="both", expand=True)

        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        main_frame.grid_rowconfigure(0, weight=1)

        left_frame = ctk.CTkFrame(
            main_frame,
            fg_color="#2563eb"
        )

        left_frame.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        right_frame = ctk.CTkFrame(
            main_frame,
            fg_color="#f8fafc"
        )

        right_frame.grid(
            row=0,
            column=1,
            sticky="nsew"
        )

        left_content = ctk.CTkFrame(
            left_frame,
            fg_color="transparent"
        )

        left_content.place(
            relx=0.5,
            rely=0.5,
            anchor="center"
        )

        ctk.CTkLabel(
            left_content,
            text="🧾",
            font=("Cairo", 80)
        ).pack(pady=(120,20))
        
        ctk.CTkLabel(
            left_content,
            text="فاكتبوه",
            font=("Cairo", 28, "bold"),
            text_color="white"
        ).pack()
        
        ctk.CTkLabel(
            left_content,
            text="نظام متكامل لإدارة الفواتير والعملاء والتقارير",
            font=("Cairo", 14),
            text_color="white"
        ).pack(pady=10)
        
        ctk.CTkLabel(
            left_content,
            text="V: 0.1.5",
            font=("Cairo", 13),
            text_color="#dbeafe"
        ).pack(pady=(20,0))
        
        ctk.CTkLabel(
            right_frame,
            text="تسجيل الدخول", 
            font=("Cairo", 28, "bold")
        ).pack(pady=(100,30))

        self.username = ctk.CTkEntry(
            right_frame,
            placeholder_text="اسم المستخدم",
            width=300,
            height=45,
            corner_radius=10
        )
        self.username.pack(pady=10)

        # إطار يحتوي الحقل + الزر
        self.password_frame = ctk.CTkFrame(
            right_frame,
            fg_color="transparent"
        )
        self.password_frame.pack(pady=10)

        self.password = ctk.CTkEntry(
            self.password_frame,
            placeholder_text="كلمة المرور",
            show="*",
            width=300,
            height=45,
            corner_radius=10
        )
        self.password.grid(row=0, column=0, padx=5)

        # زر إظهار/إخفاء
        self.show_password = False

        self.toggle_btn = ctk.CTkButton(
            self.password_frame,
            text="👁️",
            width=45,
            height=45,
            command=self.toggle_password
        )
        self.toggle_btn.grid(row=0, column=1)
        self.toggle_btn.configure(fg_color="transparent", text_color="black")

        self.btn = ctk.CTkButton(
            right_frame,
            text="تسجيل الدخول", 
            command=self.check_login,
            width=300,
            **BTN_STYLE
            
        )
        self.btn.pack(pady=20)

        self.username.bind('<Return>', lambda e: self.check_login())
        self.password.bind('<Return>', lambda e: self.check_login())

    def toggle_password(self):
        if self.show_password:
            self.password.configure(show="*")
            self.toggle_btn.configure(text="👁️")
            self.show_password = False
        else:
            self.password.configure(show="")
            self.toggle_btn.configure(text="🙈")
            self.show_password = True

    def check_login(self):
        user = login(self.username.get(), self.password.get())

        if user:
            role = user[3] if len(user) > 3 else "admin"
            self.root.destroy()
            open_main_app(role)
        else:
            messagebox.showerror("خطأ", "بيانات غير صحيحة")


# ======================
# التطبيق الرئيسي
# ======================
class App:
    def __init__(self, root, role):
        self.root = root
        self.root.title("نظام الفواتير")
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)
        
        self.role = role

        # ====== Layout رئيسي ======
        self.container = ctk.CTkFrame(root)
        self.container.pack(fill="both", expand=True)

        self.container.grid_columnconfigure(1, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        # ====== Sidebar ======
        self.sidebar = ctk.CTkFrame(
            self.container,
            width=260,
            fg_color="#111827",
            corner_radius=0
        )
        self.sidebar.grid(row=0, column=0, sticky="ns")

        ctk.CTkLabel(
            self.sidebar,
            text="🧾 فاكتبوه",
            font=("Cairo", 26, "bold"),
            text_color="white"
        ).pack(pady=(40, 30))

        ctk.CTkButton(
            self.sidebar,
            text="🧾 إنشاء الفواتير",
            command=self.show_invoices,
            **BTN_STYLE
        ).pack(fill="x", padx=15, pady=8)

        ctk.CTkButton(
            self.sidebar,
            text="📂 إدارة الفواتير",
            command=self.show_saved_invoices,
            **BTN_STYLE
        ).pack(fill="x", padx=15, pady=8)
        
        ctk.CTkButton(
            self.sidebar, 
            text="👥 العملاء", 
            command=self.show_clients,
            **BTN_STYLE
        ).pack(fill="x", padx=15, pady=8)

        ctk.CTkButton(
            self.sidebar, 
            text="📊 التقارير", 
            command=self.show_reports,
            **BTN_STYLE
        ).pack(fill="x", padx=10, pady=5)
        
        # ====== Main Content ======
        self.main_frame = ctk.CTkFrame(self.container)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        self.current_page = None
        self.pages = {}
        self.show_invoices()

    # ======================
    # Page navigation
    # ======================
    def clear_main(self):
        for page in self.main_frame.winfo_children():
            page.destroy()
        self.current_page = None

    def show_invoices(self):
        self.clear_main()
        self.current_page = InvoicesPage(self.main_frame, self)
        self.pages["invoices"] = self.current_page
        self.current_page.pack(fill="both", expand=True)

    def show_saved_invoices(self):
        self.clear_main()
        self.current_page = SavedInvoicesPage(self.main_frame, self)
        self.pages["saved_invoices"] = self.current_page
        self.current_page.pack(fill="both", expand=True)

    def show_clients(self):
        self.clear_main()
        self.current_page = ClientsPage(self.main_frame, self)
        self.pages["clients"] = self.current_page
        self.current_page.pack(fill="both", expand=True)

    def show_reports(self):
        self.clear_main()
        self.current_page = ReportsPage(self.main_frame, self)
        self.pages["reports"] = self.current_page
        self.current_page.pack(fill="both", expand=True)

# ======================
def open_main_app(role):
    root = ctk.CTk()
    app = App(root, role)
    root.mainloop()


if __name__ == "__main__":
    create_tables()
    migrate_database()

    # إنشاء مستخدم افتراضي 
    user = login("admin", "1234")
    if not user:
        create_user("admin", "1234", "admin")

    root = ctk.CTk()
    LoginWindow(root)
    root.mainloop()


