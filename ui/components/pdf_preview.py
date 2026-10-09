# ui/components/pdf_preview.py

import os
import fitz
import webbrowser
import urllib.parse
import tkinter as tk
import customtkinter as ctk
import tkinter.messagebox as mb
from tkinter import filedialog
from PIL import Image, ImageTk


class PDFPreviewWindow(ctk.CTkToplevel):

    # =========================
    # إنشاء نافذة المعاينة 
    # =========================
    def __init__(self, parent, pdf_path):
        super().__init__(parent)

        self.pdf_path = pdf_path

        self.title("معاينة الفاتورة")
        self.geometry("820x650")

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        window_width = int(screen_width * 0.65)
        window_height = int(screen_height * 0.80)

        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.geometry(
            f"{window_width}x{window_height}+{x}+{y}"
        )

        self.minsize(700, 500)

        self.transient(parent)
        self.grab_set()
        self.focus_force()

        self.page_index = 0

        self.zoom = 1.0
        self.fit_width_mode = True

        self.doc = fitz.open(pdf_path)

        # تحرير PDF عند إغلاق النافذة
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # شريط الأدوات الاحترافي
        # =========================
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        toolbar_frame = ctk.CTkFrame(self)
        toolbar_frame.grid(row=0, column=0, sticky="ew")

        navigation_toolbar = ctk.CTkFrame(
            toolbar_frame,
            fg_color="transparent"
        )
        navigation_toolbar.grid(row=0, column=0, sticky="ew")

        # عمود فارغ للتمدد
        navigation_toolbar.grid_columnconfigure(12, weight=1)

        # أزرار الصفحات 
        self.prev_btn = ctk.CTkButton(
            navigation_toolbar,
            text="◀",
            width=45,
            command=self.prev_page
        )
        self.prev_btn.grid(row=0, column=0, padx=(5, 2), pady=5)

        self.next_btn = ctk.CTkButton(
            navigation_toolbar,
            text="▶",
            width=45,
            command=self.next_page
        )
        self.next_btn.grid(row=0, column=1, padx=(2, 10), pady=5)

        # التكبير والتصغير 
        ctk.CTkButton(
            navigation_toolbar,
            text="🔍+",
            width=45,
            command=self.zoom_in
        ).grid(row=0, column=2, padx=2)

        ctk.CTkButton(
            navigation_toolbar,
            text="🔍-",
            width=45,
            command=self.zoom_out
        ).grid(row=0, column=3, padx=2)

        # Fit Width 
        ctk.CTkButton(
            navigation_toolbar,
            text="Fit",
            width=55,
            command=self.fit_width
        ).grid(row=0, column=4, padx=(10, 2))

        # Actual Size 
        ctk.CTkButton(
            navigation_toolbar,
            text="100%",
            width=55,
            command=self.actual_size
        ).grid(row=0, column=5, padx=2)

        # مؤشر الصفحات 
        self.page_label = ctk.CTkLabel(
            navigation_toolbar,
            text=""
        )
        self.page_label.grid(row=0, column=6, padx=(15, 5))

        # إنشاء حقل رقم الصفحة / مربع الانتقال 
        self.page_entry = ctk.CTkEntry(
            navigation_toolbar,
            width=60
        )
        self.page_entry.grid(row=0, column=7, padx=2)

        self.page_entry.bind("<Return>", self.go_to_page)

        # زر الانتقال 
        ctk.CTkButton(
            navigation_toolbar,
            text="انتقال",
            width=70,
            command=self.go_to_page
        ).grid(row=0, column=8, padx=(2, 15))

        actions_toolbar = ctk.CTkFrame(
            toolbar_frame,
            fg_color="transparent"
        )
        actions_toolbar.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        # العمود المرن: يدفع الأزرار الأخيرة إلى اليمين 
        actions_toolbar.grid_columnconfigure(9, weight=1)

        # فتح PDF 
        ctk.CTkButton(
            actions_toolbar,
            text="📄 pdf فتح",
            width=80,
            command=self.open_pdf
        ).grid(row=0, column=10, padx=5, sticky="e")

        # حفظ باسم 
        ctk.CTkButton(
            actions_toolbar,
            text="💾 حفظ باسم",
            width=90,
            command=self.save_as
        ).grid(row=0, column=11, padx=5, sticky="e")

        # واتساب
        ctk.CTkButton(
            actions_toolbar,
            text="💬 واتساب",
            width=90,
            command=self.send_whatsapp
        ).grid(row=0, column=12, padx=5, sticky="e")

        # البريد
        ctk.CTkButton(
            actions_toolbar,
            text="📧 بريد",
            width=90,
            command=self.send_email
        ).grid(row=0, column=13, padx=5, sticky="e")

        # الطباعة 
        ctk.CTkButton(
            actions_toolbar,
            text="🖨 طباعة",
            width=80,
            command=self.print_pdf
        ).grid(row=0, column=14, padx=(5, 10), sticky="e")

        # Scrollbar container
        # =========================
        container = ctk.CTkFrame(self)
        container.grid(row=1, column=0, sticky="nsew")

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(container)
        
        # Ctrl + عجلة الماوس للتكبير 
        self.canvas.bind("<Control-MouseWheel>", self.ctrl_mouse_zoom)

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=self.canvas.yview
        )

        self.canvas.configure(
            yscrollcommand=scrollbar.set
        )
        scrollbar.grid(row=0, column=1, sticky="ns")

        x_scrollbar = tk.Scrollbar(
            container,
            orient="horizontal",
            command=self.canvas.xview
        )

        self.canvas.configure(
            xscrollcommand=x_scrollbar.set
        )
        x_scrollbar.grid(row=1, column=0, sticky="ew")

        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # =========================
        # شريط الحالة
        # =========================
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            height=28
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))

        # =========================
        # اختصارات لوحة المفاتيح
        # =========================
        self.bind("<Left>", lambda e: self.prev_page())
        self.bind("<Right>", lambda e: self.next_page())

        self.page_entry.bind("<Left>", lambda e: self.prev_page())
        self.page_entry.bind("<Right>", lambda e: self.next_page())

        self.bind("<Control-plus>", lambda e: self.zoom_in())
        self.bind("<Control-equal>", lambda e: self.zoom_in())
        self.bind("<Control-KP_Add>", lambda e: self.zoom_in())

        self.bind("<Control-minus>", lambda e: self.zoom_out())
        self.bind("<Control-KP_Subtract>", lambda e: self.zoom_out())

        self.bind("<Control-p>", lambda e: self.print_pdf())
        self.bind("<Control-P>", lambda e: self.print_pdf())

        self.bind("<Control-s>", lambda e: self.save_as())
        self.bind("<Control-S>", lambda e: self.save_as())

        self.bind("<Control-w>", lambda e: self.send_whatsapp())
        self.bind("<Control-e>", lambda e: self.send_email())

        self.show_page()

    # =========================
    # عرض الصفحة المعاينة 
    # =========================
    def show_page(self):
        page = self.doc.load_page(
            self.page_index
        )

        pix = page.get_pixmap(
            matrix=fitz.Matrix(
                self.zoom, 
                self.zoom
            )
        )

        image = Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples
        )

        if self.fit_width_mode:
            canvas_width = self.canvas.winfo_width()
            if canvas_width > 1:
                ratio = canvas_width / image.width
                image = image.resize(
                    (
                        int(image.width * ratio),
                        int(image.height * ratio)
                    ),
                    Image.LANCZOS
                )

        self.tk_image = ImageTk.PhotoImage(
            image
        )

        self.canvas.delete("all")

        self.canvas.create_image(
            0,
            0,
            anchor="nw",
            image=self.tk_image
        )

        self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        )

        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

        self.update_navigation_buttons()
        
        # تحديث مربع رقم الصفحة 
        self.page_entry.delete(0, "end")

        self.page_entry.insert(
            0,
            str(self.page_index + 1)
        )

        # تحديث شريط الحالة 
        self.update_status_bar()

    # =========================
    # التنقل بين الصفحات 
    # =========================
    def next_page(self):
        if self.page_index < len(self.doc) - 1:
            self.page_index += 1
            self.show_page()
        
    def prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self.show_page()

    def update_navigation_buttons(self):
        if not hasattr(self, "prev_btn"):
            return
        
        if self.page_index <= 0:
            self.prev_btn.configure(
                state="disabled"
            )
        else:
            self.prev_btn.configure(
                state="normal"
            )

        if self.page_index >= len(self.doc) - 1:

            self.next_btn.configure(
                state="disabled"
            )
        else:
            self.next_btn.configure(
                state="normal"
            )
        self.page_label.configure(
            text=f"صفحة {self.page_index + 1} من {len(self.doc)}"
        )
        
    # =========================
    # الانتقال إلى صفحة
    # =========================
    def go_to_page(self, event=None):
        try:
            page = int(
                self.page_entry.get()
            )
        except ValueError:
            mb.showwarning(
                "تنبيه",
                "أدخل رقم صفحة صحيح"
            )
            return
        if page < 1 or page > len(self.doc):
            mb.showwarning(
                "تنبيه",
                f"رقم الصفحة يجب أن يكون بين 1 و {len(self.doc)}"
            )
            return

        self.page_index = page - 1
        self.show_page()

    # =========================
    # تحديث شريط الحالة
    # =========================
    def update_status_bar(self):

        zoom_percent = int(self.zoom * 100)

        if self.fit_width_mode:
            zoom_text = "Fit Width"
        else:
            zoom_text = f"{zoom_percent}%"

        self.status_label.configure(
            text=(
                f"صفحة {self.page_index + 1} من {len(self.doc)}"
                f"    |    "
                f"التكبير: {zoom_text}"
            )
        )

    # =========================
    # التكبير 
    # =========================
    def zoom_in(self):
        self.fit_width_mode = False
        self.zoom *= 1.2
        self.show_page()
    
    def zoom_out(self):
        self.fit_width_mode = False
        self.zoom /= 1.2
        self.show_page()

    # =========================
    # Ctrl + Wheel Zoom
    # =========================
    def ctrl_mouse_zoom(self, event):
        if event.delta > 0:

            self.zoom_in()
        else:

            self.zoom_out()

    # =========================
    # الحجم الحقيقي 
    # =========================
    def actual_size(self):
        self.fit_width_mode = False
        self.zoom = 1
        self.show_page()

    # =========================
    # Fit Width 
    # =========================
    def fit_width(self):
        self.fit_width_mode = True
        self.show_page()

    # =========================
    # فتح PDF 
    # =========================
    def open_pdf(self):
        if os.path.exists(self.pdf_path):
            os.startfile(self.pdf_path)
        else:
            mb.showerror(
                "خطأ",
                "ملف PDF غير موجود"
            )

    # =========================
    # مشاركة عبر واتساب
    # =========================
    def send_whatsapp(self):
        message = (
            "مرحباً، "
            "تم إصدار فاتورتكم، "
            "يرجى إرفاق ملف PDF المرفق وإرساله."
        )
        url = (
            "https://wa.me/?text="
            + urllib.parse.quote(message)
        )
        webbrowser.open(url)

    # =========================
    # مشاركة عبر البريد
    # =========================
    def send_email(self):
        subject = urllib.parse.quote(
            "فاتورة"
        )
        body = urllib.parse.quote(
            "مرفق لكم الفاتورة."
        )
        url = (
            f"mailto:?subject={subject}&body={body}"
        )
        webbrowser.open(url)

    # =========================
    # الطباعة 
    # =========================
    def print_pdf(self):
        os.startfile(
            self.pdf_path,
            "print"
        )

    # =========================
    # حفظ باسم
    # =========================
    def save_as(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[
                ("PDF Files", "*.pdf")
            ],
            initialfile=os.path.basename(
                self.pdf_path
            )
        )

        if not file_path:
            return

        try:

            with open(self.pdf_path, "rb") as source:

                with open(file_path, "wb") as target:

                    target.write(
                        source.read()
                    )
            mb.showinfo(
                "تم",
                "تم حفظ الملف بنجاح"
            )
        except Exception as e:
            mb.showerror(
                "خطأ",
                str(e)
            )

    # =========================
    # إغلاق النافذة
    # =========================
    def on_close(self):
        try:
            if self.doc:
                self.doc.close()
        except Exception:
            pass
        self.destroy()


        
