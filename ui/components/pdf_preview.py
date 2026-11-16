# ui/components/pdf_preview.py
"""
نافذة معاينة PDF (0.1.7)

الجديد في هذا الإصدار:
  • البحث داخل PDF مع تمييز النتائج (Ctrl+F / F3 / Shift+F3)
  • لوحة الصور المصغرة للصفحات (Thumbnails)
  • أداة اليد (Hand Tool) لسحب الصفحة بالماوس (والزر الأوسط دائماً)
  • وضع ملء الشاشة (F11 / Esc)
  • شريط تقدم أثناء تحميل/فهرسة/بحث ملفات PDF الكبيرة
  • حفظ آخر مستوى تكبير وطريقة العرض واسترجاعهما في المرة القادمة
  • طباعة مباشرة (نافذة اختيار الطابعة والصفحات) بلا حاجة لبرنامج PDF مرتبط
  • عرض متواصل لكل الصفحات برسم الصفحات الظاهرة فقط (سريع مع الملفات الكبيرة)
"""

import math
import os
import urllib.parse
import webbrowser
from bisect import bisect_right
from tkinter import filedialog
import tkinter as tk
import tkinter.messagebox as mb

import customtkinter as ctk
import fitz
from PIL import Image, ImageDraw, ImageTk

from ui.components.print_utils import (
    iter_print_pdf,
    list_printers,
    open_pdf_safely,
    parse_page_range,
)

try:
    from database import get_setting, set_setting
except Exception:  # يعمل المكوّن حتى لو تعذّر الوصول لقاعدة البيانات
    def get_setting(key, default=None):
        return default

    def set_setting(key, value):
        return False


# =========================
# ثوابت
# =========================
GAP = 14                    # المسافة بين الصفحات
MARGIN = 14                 # هامش حول الصفحات
ZOOM_MIN = 0.2
ZOOM_MAX = 4.0
ZOOM_STEP = 1.2

THUMB_W = 120               # عرض الصورة المصغرة
THUMB_PANEL_W = 160         # عرض اللوحة
THUMB_LABEL_H = 22          # مساحة رقم الصفحة تحت المصغرة
THUMB_BATCH = 3             # عدد المصغرات لكل دفعة

SYNC_SCAN_LIMIT = 80        # أكثر من هذا نفهرس الصفحات على دفعات مع شريط تقدم
SCAN_CHUNK = 40
SEARCH_CHUNK = 15
PROGRESS_MIN_PAGES = 12     # لا نُظهر شريط التقدم للملفات الصغيرة

VIEW_BG = "#cbd5e1"
SHADOW = "#94a3b8"
BTN_OFF = "#64748b"         # لون أزرار التبديل (غير مفعّلة)
BTN_ON = "#2563eb"          # لون أزرار التبديل (مفعّلة)

HIT_COLOR = (250, 204, 21, 110)       # أصفر شفاف: نتائج البحث
HIT_CUR_COLOR = (249, 115, 22, 150)   # برتقالي: النتيجة الحالية

SETTING_ZOOM = "preview.zoom"
SETTING_MODE = "preview.zoom_mode"
SETTING_THUMBS = "preview.thumbs"
SETTING_PRINTER = "preview.printer"


# =========================
# نافذة الطباعة
# =========================
class PrintDialog(ctk.CTkToplevel):
    """يسأل عن الطابعة والصفحات وعدد النسخ. النتيجة في self.result."""

    def __init__(self, parent, page_count, current_page, last_printer=""):
        super().__init__(parent)

        self.result = None
        self.page_count = page_count
        self.current_page = current_page

        self.title("طباعة")
        self.resizable(False, False)
        self.transient(parent)

        printers, default = list_printers()
        self.printers = printers

        body = ctk.CTkFrame(self)
        body.pack(fill="both", expand=True, padx=15, pady=15)

        # الطابعة
        ctk.CTkLabel(body, text="الطابعة:", anchor="e").grid(
            row=0, column=1, sticky="e", padx=8, pady=8
        )

        if printers:
            chosen = last_printer if last_printer in printers else (
                default if default in printers else printers[0]
            )
            self.printer_var = tk.StringVar(value=chosen)
            ctk.CTkComboBox(
                body, values=printers, variable=self.printer_var,
                state="readonly", width=300
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
        else:
            self.printer_var = tk.StringVar(value="")
            ctk.CTkLabel(body, text="الطابعة الافتراضية للنظام").grid(
                row=0, column=0, sticky="w", padx=8, pady=8
            )

        # النسخ
        ctk.CTkLabel(body, text="عدد النسخ:", anchor="e").grid(
            row=1, column=1, sticky="e", padx=8, pady=8
        )
        self.copies_entry = ctk.CTkEntry(body, width=70)
        self.copies_entry.insert(0, "1")
        self.copies_entry.grid(row=1, column=0, sticky="w", padx=8, pady=8)

        # الصفحات
        ctk.CTkLabel(body, text="الصفحات:", anchor="ne").grid(
            row=2, column=1, sticky="ne", padx=8, pady=8
        )

        pages_box = ctk.CTkFrame(body, fg_color="transparent")
        pages_box.grid(row=2, column=0, sticky="w", padx=8, pady=8)

        self.mode_var = tk.StringVar(value="all")

        ctk.CTkRadioButton(
            pages_box, text=f"كل الصفحات ({page_count})",
            variable=self.mode_var, value="all"
        ).pack(anchor="w", pady=3)

        ctk.CTkRadioButton(
            pages_box, text=f"الصفحة الحالية ({current_page + 1})",
            variable=self.mode_var, value="current"
        ).pack(anchor="w", pady=3)

        range_row = ctk.CTkFrame(pages_box, fg_color="transparent")
        range_row.pack(anchor="w", pady=3)

        ctk.CTkRadioButton(
            range_row, text="مدى:", variable=self.mode_var,
            value="range", width=60
        ).pack(side="left")

        self.range_entry = ctk.CTkEntry(
            range_row, width=170, placeholder_text="مثال: 1-3, 5"
        )
        self.range_entry.pack(side="left", padx=(5, 0))
        self.range_entry.bind(
            "<FocusIn>", lambda e: self.mode_var.set("range")
        )

        # الأزرار
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=3, column=0, columnspan=2, pady=(12, 0))

        ctk.CTkButton(
            buttons, text="🖨 طباعة", width=110, command=self._ok
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            buttons, text="إلغاء", width=90, fg_color="#64748b",
            hover_color="#475569", command=self.destroy
        ).pack(side="left", padx=6)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        self.after(100, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _ok(self):
        try:
            copies = int(self.copies_entry.get().strip() or "1")
        except ValueError:
            copies = 0

        if copies < 1 or copies > 99:
            mb.showwarning("تنبيه", "عدد النسخ يجب أن يكون بين 1 و 99", parent=self)
            return

        mode = self.mode_var.get()

        if mode == "all":
            pages = list(range(self.page_count))
        elif mode == "current":
            pages = [self.current_page]
        else:
            try:
                pages = parse_page_range(self.range_entry.get(), self.page_count)
            except ValueError as e:
                mb.showwarning("تنبيه", str(e), parent=self)
                return

        self.result = {
            "printer": self.printer_var.get(),
            "pages": pages,
            "copies": copies,
        }
        self.destroy()


# =========================
# نافذة المعاينة
# =========================
class PDFPreviewWindow(ctk.CTkToplevel):

    # =========================
    # إنشاء نافذة المعاينة
    # =========================
    def __init__(
        self,
        parent,
        pdf_path,
        title="معاينة الفاتورة",
        share_message="مرحباً، تم إصدار فاتورتكم، يرجى إرفاق ملف PDF المرفق وإرساله.",
        email_subject="فاتورة",
        email_body="مرفق لكم الفاتورة.",
    ):
        super().__init__(parent)

        self._parent = parent
        self.pdf_path = os.path.abspath(pdf_path)
        self.share_message = share_message
        self.email_subject = email_subject
        self.email_body = email_body

        # حالة المستند
        self.doc = None
        self.page_count = 0
        self.page_sizes = []           # (عرض، ارتفاع) بالنقاط
        self.page_index = 0
        self._alive = True
        self._ready = False

        # التكبير (يُسترجع من الإعدادات)
        self.zoom = 1.0
        self.zoom_mode = "width"       # width | page | custom
        self._load_prefs()

        # التخطيط
        self.page_tops = []
        self.page_xs = []
        self.page_pxs = []
        self.total_h = 1
        self.view_w = 1
        self._page_imgs = {}           # index -> (PhotoImage, item_id, key)
        self._hl_ver = {}              # index -> رقم نسخة التمييز

        # المصغرات
        self._thumb_tops = []
        self._thumb_imgs = {}
        self._thumb_sel = {}
        self._thumb_pending = set()
        self._thumb_job = None
        self._thumb_built = False
        self._thumb_current = None
        self._thumbs_on = False

        # البحث
        self.hits = {}                 # page -> [Rect]
        self.hit_order = []            # [(page, k)]
        self.hit_pos = -1
        self._search_token = 0
        self._search_pos = 0
        self._search_query = ""
        self._search_variants = []

        # أدوات
        self.hand_tool = False
        self._middle_drag = False
        self._fullscreen = False
        self._prev_geometry = None
        self._tasks = {}
        self._print_gen = None
        self._print_total = 0
        self._print_printer = ""
        self._flash = ""

        self._view_job = None
        self._cfg_job = None
        self._save_job = None
        self._last_canvas_size = (0, 0)

        self.title(title)
        self._setup_geometry()

        self.minsize(760, 520)
        self.transient(parent)

        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbars()
        self._build_search_bar()
        self._build_body()
        self._build_status_bar()
        self._bind_keys()

        # نفتح الملف بعد ظهور النافذة ليظهر شريط التقدم أثناء الفتح
        self._task("open", None, "جارٍ فتح الملف")
        self._after(60, self._open_document)

    def _setup_geometry(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        window_width = int(screen_width * 0.65)
        window_height = int(screen_height * 0.80)

        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.geometry(f"{window_width}x{window_height}+{x}+{y}")

    def _after(self, ms, fn):
        """after آمن: لا يُنفَّذ بعد إغلاق النافذة."""
        def run():
            if self._alive:
                fn()
        return self.after(ms, run)

    # =========================
    # الإعدادات المحفوظة
    # =========================
    def _load_prefs(self):
        try:
            zoom = float(get_setting(SETTING_ZOOM, "1.0"))
            self.zoom = min(max(zoom, ZOOM_MIN), ZOOM_MAX)
        except (TypeError, ValueError):
            self.zoom = 1.0

        mode = get_setting(SETTING_MODE, "width")
        self.zoom_mode = mode if mode in ("width", "page", "custom") else "width"

        self._thumbs_pref = get_setting(SETTING_THUMBS, None)

    def _save_prefs(self):
        set_setting(SETTING_ZOOM, f"{self.zoom:.4f}")
        set_setting(SETTING_MODE, self.zoom_mode)
        set_setting(
            SETTING_THUMBS, "1" if self._thumbs_visible() else "0"
        )

    def _schedule_save(self):
        if self._save_job:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self._after(600, self._save_prefs)

    # =========================
    # بناء الواجهة
    # =========================
    def _tool_btn(self, parent, text, command, width=45, toggle=False):
        kwargs = {}
        if toggle:
            kwargs["fg_color"] = BTN_OFF
            kwargs["hover_color"] = "#475569"

        return ctk.CTkButton(
            parent, text=text, width=width, command=command, **kwargs
        )

    def _build_toolbars(self):
        toolbar_frame = ctk.CTkFrame(self)
        toolbar_frame.grid(row=0, column=0, sticky="ew")

        # ---- الصف الأول: التنقل والعرض ----
        view_bar = ctk.CTkFrame(toolbar_frame, fg_color="transparent")
        view_bar.pack(fill="x", pady=(5, 0))

        self.thumbs_btn = self._tool_btn(
            view_bar, "🗂 مصغرات", self.toggle_thumbs, 90, toggle=True
        )
        self.thumbs_btn.pack(side="left", padx=(8, 8))

        self.prev_btn = self._tool_btn(view_bar, "◀", self.prev_page)
        self.prev_btn.pack(side="left", padx=(0, 2))

        self.next_btn = self._tool_btn(view_bar, "▶", self.next_page)
        self.next_btn.pack(side="left", padx=(2, 8))

        self.page_entry = ctk.CTkEntry(view_bar, width=55, justify="center")
        self.page_entry.pack(side="left", padx=2)
        self.page_entry.bind("<Return>", self.go_to_page)

        self.page_label = ctk.CTkLabel(view_bar, text="/ 0")
        self.page_label.pack(side="left", padx=(2, 12))

        self._tool_btn(view_bar, "🔍-", self.zoom_out).pack(side="left", padx=2)

        self.zoom_label = ctk.CTkLabel(view_bar, text="100%", width=55)
        self.zoom_label.pack(side="left")

        self._tool_btn(view_bar, "🔍+", self.zoom_in).pack(side="left", padx=2)

        self.fit_btn = self._tool_btn(
            view_bar, "عرض الصفحة", self.fit_width, 95, toggle=True
        )
        self.fit_btn.pack(side="left", padx=(10, 2))

        self.fitpage_btn = self._tool_btn(
            view_bar, "صفحة كاملة", self.fit_page, 95, toggle=True
        )
        self.fitpage_btn.pack(side="left", padx=2)

        self._tool_btn(view_bar, "100%", self.actual_size, 55).pack(
            side="left", padx=2
        )

        # أدوات في أقصى اليمين
        self.fullscreen_btn = self._tool_btn(
            view_bar, "⛶ ملء الشاشة", self.toggle_fullscreen, 115
        )
        self.fullscreen_btn.pack(side="right", padx=(4, 8))

        self.search_btn = self._tool_btn(
            view_bar, "🔎 بحث", self.toggle_search, 80, toggle=True
        )
        self.search_btn.pack(side="right", padx=4)

        self.hand_btn = self._tool_btn(
            view_bar, "✋ سحب", self.toggle_hand, 80, toggle=True
        )
        self.hand_btn.pack(side="right", padx=4)

        # ---- الصف الثاني: الإجراءات ----
        actions = ctk.CTkFrame(toolbar_frame, fg_color="transparent")
        actions.pack(fill="x", pady=(5, 5))

        self.print_btn = self._tool_btn(
            actions, "🖨 طباعة", self.print_pdf, 90
        )
        self.print_btn.pack(side="right", padx=(5, 10))

        self._tool_btn(actions, "📧 بريد", self.send_email, 90).pack(
            side="right", padx=5
        )
        self._tool_btn(actions, "💬 واتساب", self.send_whatsapp, 90).pack(
            side="right", padx=5
        )
        self._tool_btn(actions, "💾 حفظ باسم", self.save_as, 100).pack(
            side="right", padx=5
        )
        self._tool_btn(actions, "📄 فتح PDF", self.open_pdf, 90).pack(
            side="right", padx=5
        )

        self.toolbar_frame = toolbar_frame

    def _build_search_bar(self):
        self.search_bar = ctk.CTkFrame(self)
        self.search_bar.grid(row=1, column=0, sticky="ew")
        self.search_bar.grid_remove()

        inner = ctk.CTkFrame(self.search_bar, fg_color="transparent")
        inner.pack(fill="x", pady=5)

        ctk.CTkButton(
            inner, text="✕", width=34, fg_color="#64748b",
            hover_color="#475569", command=self.close_search
        ).pack(side="right", padx=(4, 10))

        self.search_count = ctk.CTkLabel(inner, text="", width=130, anchor="e")
        self.search_count.pack(side="right", padx=6)

        ctk.CTkButton(
            inner, text="▼", width=36,
            command=lambda: self.next_hit(1)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            inner, text="▲", width=36,
            command=lambda: self.next_hit(-1)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            inner, text="بحث", width=70, command=self.run_search
        ).pack(side="right", padx=4)

        self.search_entry = ctk.CTkEntry(
            inner, width=300, placeholder_text="ابحث داخل المستند…"
        )
        self.search_entry.pack(side="right", padx=4)
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_entry.bind(
            "<Shift-Return>", lambda e: self.next_hit(-1)
        )

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        # ---- منطقة العرض ----
        viewer = ctk.CTkFrame(body)
        viewer.grid(row=0, column=0, sticky="nsew")
        viewer.grid_rowconfigure(0, weight=1)
        viewer.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            viewer, bg=VIEW_BG, highlightthickness=0,
            yscrollincrement=30, xscrollincrement=30
        )

        self.y_scrollbar = tk.Scrollbar(
            viewer, orient="vertical", command=self.canvas.yview
        )
        self.x_scrollbar = tk.Scrollbar(
            viewer, orient="horizontal", command=self.canvas.xview
        )

        self.canvas.configure(
            yscrollcommand=self._on_yscroll,
            xscrollcommand=self.x_scrollbar.set,
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.y_scrollbar.grid(row=0, column=1, sticky="ns")
        self.x_scrollbar.grid(row=1, column=0, sticky="ew")

        # ---- لوحة المصغرات (على اليمين) ----
        self.thumb_frame = ctk.CTkFrame(body, width=THUMB_PANEL_W + 18)
        self.thumb_frame.grid(row=0, column=1, sticky="ns")
        self.thumb_frame.grid_propagate(False)
        self.thumb_frame.grid_rowconfigure(0, weight=1)
        self.thumb_frame.grid_columnconfigure(0, weight=1)

        self.thumb_canvas = tk.Canvas(
            self.thumb_frame, bg="#e2e8f0", highlightthickness=0,
            width=THUMB_PANEL_W, yscrollincrement=30
        )
        self.thumb_scroll = tk.Scrollbar(
            self.thumb_frame, orient="vertical",
            command=self.thumb_canvas.yview
        )
        self.thumb_canvas.configure(yscrollcommand=self._on_thumb_yscroll)

        self.thumb_canvas.grid(row=0, column=0, sticky="nsew")
        self.thumb_scroll.grid(row=0, column=1, sticky="ns")
        self.thumb_frame.grid_remove()

        # ---- أحداث الماوس ----
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        self.canvas.bind("<Control-MouseWheel>", self.ctrl_mouse_zoom)
        self.canvas.bind("<Button-4>", lambda e: self._wheel_units(-3))
        self.canvas.bind("<Button-5>", lambda e: self._wheel_units(3))

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-2>", self._on_press_middle)
        self.canvas.bind("<B2-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_release)

        self.thumb_canvas.bind("<MouseWheel>", self._on_thumb_wheel)
        self.thumb_canvas.bind(
            "<Button-4>", lambda e: self.thumb_canvas.yview_scroll(-3, "units")
        )
        self.thumb_canvas.bind(
            "<Button-5>", lambda e: self.thumb_canvas.yview_scroll(3, "units")
        )
        self.thumb_canvas.bind("<Button-1>", self._on_thumb_click)

    def _build_status_bar(self):
        status = ctk.CTkFrame(self, fg_color="transparent")
        status.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 5))
        status.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(status, text="", anchor="w", height=28)
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.progress_label = ctk.CTkLabel(status, text="", anchor="e")
        self.progress_label.grid(row=0, column=1, padx=(10, 6))

        self.progress_bar = ctk.CTkProgressBar(status, width=190, height=10)
        self.progress_bar.grid(row=0, column=2, padx=(0, 4))
        self.progress_label.grid_remove()
        self.progress_bar.grid_remove()

    # =========================
    # اختصارات لوحة المفاتيح
    # =========================
    def _typing(self):
        try:
            widget = self.focus_get()
            return widget is not None and widget.winfo_class() in (
                "Entry", "Text", "TEntry"
            )
        except Exception:
            return False

    def _key(self, fn):
        def handler(event=None):
            if self._typing():
                return None
            fn()
            return "break"
        return handler

    def _bind_keys(self):
        self.bind("<Left>", self._key(self.prev_page))
        self.bind("<Right>", self._key(self.next_page))
        self.bind("<Up>", self._key(lambda: self._wheel_units(-3)))
        self.bind("<Down>", self._key(lambda: self._wheel_units(3)))
        self.bind("<Prior>", self._key(lambda: self.canvas.yview_scroll(-1, "pages")))
        self.bind("<Next>", self._key(lambda: self.canvas.yview_scroll(1, "pages")))
        self.bind("<Home>", self._key(lambda: self.go_to(0)))
        self.bind("<End>", self._key(lambda: self.go_to(self.page_count - 1)))

        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind(seq, lambda e: self.zoom_in())

        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind(seq, lambda e: self.zoom_out())

        self.bind("<Control-0>", lambda e: self.fit_width())
        self.bind("<Control-1>", lambda e: self.actual_size())

        for seq in ("<Control-p>", "<Control-P>"):
            self.bind(seq, lambda e: self.print_pdf())

        for seq in ("<Control-s>", "<Control-S>"):
            self.bind(seq, lambda e: self.save_as())

        for seq in ("<Control-f>", "<Control-F>"):
            self.bind(seq, lambda e: self.open_search())

        self.bind("<F3>", lambda e: self.next_hit(1))
        self.bind("<Shift-F3>", lambda e: self.next_hit(-1))
        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", self._on_escape)

        self.bind("<Control-w>", lambda e: self.send_whatsapp())
        self.bind("<Control-e>", lambda e: self.send_email())

    def _on_escape(self, event=None):
        if self._fullscreen:
            self.toggle_fullscreen()
        elif self.search_bar.winfo_ismapped():
            self.close_search()

    # =========================
    # شريط التقدم (مهام متعددة)
    # =========================
    def _task(self, name, frac=None, text=""):
        self._tasks[name] = (frac, text)
        self._refresh_progress()

    def _task_done(self, name):
        self._tasks.pop(name, None)
        self._refresh_progress()

    def _refresh_progress(self):
        if not self._alive:
            return

        if not self._tasks:
            try:
                self.progress_bar.stop()
            except Exception:
                pass
            self.progress_bar.grid_remove()
            self.progress_label.grid_remove()
            return

        _name, (frac, text) = list(self._tasks.items())[-1]

        self.progress_bar.grid()
        self.progress_label.grid()

        if frac is None:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self.progress_label.configure(text=text)
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(max(0.0, min(1.0, frac)))
            self.progress_label.configure(text=f"{text} {int(frac * 100)}%")

    # =========================
    # فتح المستند وفهرسة الصفحات
    # =========================
    def _open_document(self):
        self.update_idletasks()

        try:
            if not os.path.exists(self.pdf_path):
                raise FileNotFoundError("ملف PDF غير موجود")

            self.doc = fitz.open(self.pdf_path)
            self.page_count = len(self.doc)

            if self.page_count == 0:
                raise ValueError("الملف لا يحتوي على صفحات")

            first = self.doc.load_page(0).rect
            self.page_sizes = [(first.width, first.height)] * self.page_count

        except Exception as e:
            self._task_done("open")
            mb.showerror("خطأ", f"تعذّر فتح الملف:\n{e}", parent=self)
            self.on_close()
            return

        self._task_done("open")

        self.page_label.configure(text=f"/ {self.page_count}")
        self._ready = True

        # عرض فوري للصفحة الأولى بقياسها، ثم نفهرس الباقي
        self._apply_zoom_mode()
        self._layout(keep_anchor=False)
        self._set_current(0)

        if self.page_count <= SYNC_SCAN_LIMIT:
            self.page_sizes = [
                (r.width, r.height)
                for r in (self.doc.load_page(i).rect
                          for i in range(self.page_count))
            ]
            self._after_scan()
        else:
            self._scan_pos = 1
            self._after(5, self._scan_step)

    def _scan_step(self):
        if not self.doc:
            return

        end = min(self._scan_pos + SCAN_CHUNK, self.page_count)

        for i in range(self._scan_pos, end):
            rect = self.doc.load_page(i).rect
            self.page_sizes[i] = (rect.width, rect.height)

        self._scan_pos = end

        if end < self.page_count:
            self._task("scan", end / self.page_count, "تحليل الصفحات")
            self._after(1, self._scan_step)
        else:
            self._task_done("scan")
            self._after_scan()

    def _after_scan(self):
        """بعد معرفة أحجام كل الصفحات: تخطيط نهائي + المصغرات."""
        self._apply_zoom_mode()
        self._layout(keep_anchor=True)

        show = self._thumbs_pref
        if show is None:
            show = "1" if self.page_count > 1 else "0"

        if show == "1":
            self.toggle_thumbs(save=False)

        self.update_status_bar()

    # =========================
    # التخطيط والرسم
    # =========================
    def _page_px(self, index):
        width, height = self.page_sizes[index]
        return (
            max(1, math.ceil(width * self.zoom)),
            max(1, math.ceil(height * self.zoom)),
        )

    def _page_at(self, y):
        if not self.page_tops:
            return 0
        index = bisect_right(self.page_tops, y) - 1
        return min(max(index, 0), self.page_count - 1)

    def _anchor(self):
        """الصفحة وموضع أعلى نافذة العرض داخلها (لحفظ المكان عند التكبير)."""
        if not self.page_tops:
            return None

        y = self.canvas.canvasy(0)
        index = self._page_at(y)
        height = self.page_pxs[index][1]
        frac = (y - self.page_tops[index]) / height if height else 0

        return index, max(-0.2, min(frac, 1.0)), self.canvas.xview()[0]

    def _layout(self, keep_anchor=True):
        if not self._ready:
            return

        anchor = self._anchor() if keep_anchor else None

        canvas_w = max(self.canvas.winfo_width(), 1)

        self.page_pxs = [self._page_px(i) for i in range(self.page_count)]
        content_w = max(w for w, _ in self.page_pxs) + 2 * MARGIN
        self.view_w = max(content_w, canvas_w)

        y = MARGIN
        self.page_tops = []
        self.page_xs = []

        for width, height in self.page_pxs:
            self.page_tops.append(y)
            self.page_xs.append((self.view_w - width) // 2)
            y += height + GAP

        self.total_h = max(y - GAP + MARGIN, 1)

        self.canvas.delete("all")
        self._page_imgs.clear()

        for i, (width, height) in enumerate(self.page_pxs):
            x0 = self.page_xs[i]
            y0 = self.page_tops[i]

            self.canvas.create_rectangle(
                x0 + 4, y0 + 4, x0 + width + 4, y0 + height + 4,
                fill=SHADOW, outline=""
            )
            self.canvas.create_rectangle(
                x0, y0, x0 + width, y0 + height,
                fill="white", outline="#94a3b8"
            )

        self.canvas.configure(scrollregion=(0, 0, self.view_w, self.total_h))

        if anchor:
            index, frac, xfrac = anchor
            target = self.page_tops[index] + frac * self.page_pxs[index][1]
            self.canvas.yview_moveto(max(0, target) / self.total_h)
            self.canvas.xview_moveto(xfrac)

        self._schedule_view_update()
        self.update_status_bar()

    def _schedule_view_update(self):
        if self._view_job is None:
            self._view_job = self.after_idle(self._run_view_update)

    def _run_view_update(self):
        self._view_job = None

        if not self._alive or not self._ready:
            return

        self._render_visible()
        self._sync_current_page()

    def _render_visible(self):
        if not self.page_tops:
            return

        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()

        first = self._page_at(top)
        last = self._page_at(bottom)

        lo = max(0, first - 1)
        hi = min(self.page_count - 1, last + 1)

        # تحرير صور الصفحات البعيدة
        for index in list(self._page_imgs):
            if index < lo - 1 or index > hi + 1:
                _img, item, _key = self._page_imgs.pop(index)
                self.canvas.delete(item)

        order = list(range(first, last + 1)) + [
            i for i in range(lo, hi + 1) if i < first or i > last
        ]

        for index in order:
            self._ensure_page_image(index)

    def _ensure_page_image(self, index):
        # مفتاح الصورة: التكبير + نسخة التمييز (النتيجة الحالية تُدرج في النسخة)
        key = (round(self.zoom, 4), self._hl_ver.get(index, 0))

        cached = self._page_imgs.get(index)
        if cached and cached[2] == key:
            return

        if cached:
            self.canvas.delete(cached[1])

        try:
            image = self._render_page_image(index)
        except Exception:
            return

        photo = ImageTk.PhotoImage(image)

        x0 = (self.view_w - photo.width()) // 2
        item = self.canvas.create_image(
            x0, self.page_tops[index], anchor="nw", image=photo
        )

        self._page_imgs[index] = (photo, item, key)

    def _render_page_image(self, index):
        page = self.doc.load_page(index)

        pix = page.get_pixmap(
            matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False
        )
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        rects = self.hits.get(index)
        if rects:
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            current = (
                self.hit_order[self.hit_pos]
                if 0 <= self.hit_pos < len(self.hit_order) else None
            )

            for k, rect in enumerate(rects):
                color = HIT_CUR_COLOR if current == (index, k) else HIT_COLOR
                draw.rectangle(
                    [
                        rect.x0 * self.zoom, rect.y0 * self.zoom,
                        rect.x1 * self.zoom, rect.y1 * self.zoom,
                    ],
                    fill=color,
                )

            image = Image.alpha_composite(
                image.convert("RGBA"), overlay
            ).convert("RGB")

        return image

    def _invalidate_pages(self, pages):
        for index in pages:
            self._hl_ver[index] = self._hl_ver.get(index, 0) + 1

    # =========================
    # التمرير
    # =========================
    def _on_yscroll(self, first, last):
        self.y_scrollbar.set(first, last)
        self._schedule_view_update()

    def _wheel_units(self, units):
        self.canvas.yview_scroll(units, "units")

    def _on_wheel(self, event):
        self._wheel_units(-3 if event.delta > 0 else 3)

    def _on_shift_wheel(self, event):
        self.canvas.xview_scroll(-3 if event.delta > 0 else 3, "units")

    def _sync_current_page(self):
        first, last = self.canvas.yview()

        if first <= 0.001 and last >= 0.999:
            return  # المستند كله ظاهر: نُبقي الصفحة المختارة

        if last >= 0.999:
            index = self.page_count - 1
        elif first <= 0.001:
            index = 0
        else:
            probe = self.canvas.canvasy(0) + min(
                self.canvas.winfo_height() * 0.25, 140
            )
            index = self._page_at(probe)

        if index != self.page_index:
            self._set_current(index)

    def _set_current(self, index):
        self.page_index = index

        # لا نغيّر الرقم أثناء كتابة المستخدم فيه
        try:
            typing_in_entry = self.focus_get() is self.page_entry._entry
        except Exception:
            typing_in_entry = False

        if not typing_in_entry:
            self.page_entry.delete(0, "end")
            self.page_entry.insert(0, str(index + 1))

        self.prev_btn.configure(state="disabled" if index <= 0 else "normal")
        self.next_btn.configure(
            state="disabled" if index >= self.page_count - 1 else "normal"
        )

        self._highlight_thumb(index)
        self.update_status_bar()

    # =========================
    # أدوات الماوس: اليد
    # =========================
    def toggle_hand(self):
        self.hand_tool = not self.hand_tool
        self.hand_btn.configure(
            fg_color=BTN_ON if self.hand_tool else BTN_OFF
        )
        self.canvas.configure(cursor="hand2" if self.hand_tool else "")
        self.update_status_bar()

    def _on_press(self, event):
        self.canvas.focus_set()

        if self.hand_tool:
            self.canvas.scan_mark(event.x, event.y)
            self.canvas.configure(cursor="fleur")

    def _on_press_middle(self, event):
        self.canvas.focus_set()
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor="fleur")
        self._middle_drag = True

    def _on_drag(self, event):
        if self.hand_tool or self._middle_drag:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, event):
        self._middle_drag = False
        self.canvas.configure(cursor="hand2" if self.hand_tool else "")

    # =========================
    # التنقل بين الصفحات
    # =========================
    def go_to(self, index):
        if not self._ready:
            return

        index = min(max(index, 0), self.page_count - 1)

        target = max(0, self.page_tops[index] - MARGIN // 2)
        self.canvas.yview_moveto(target / self.total_h)

        self._set_current(index)
        self._schedule_view_update()

    def next_page(self):
        if self.page_index < self.page_count - 1:
            self.go_to(self.page_index + 1)

    def prev_page(self):
        if self.page_index > 0:
            self.go_to(self.page_index - 1)

    def go_to_page(self, event=None):
        try:
            page = int(self.page_entry.get())
        except ValueError:
            mb.showwarning("تنبيه", "أدخل رقم صفحة صحيح", parent=self)
            return

        if page < 1 or page > self.page_count:
            mb.showwarning(
                "تنبيه",
                f"رقم الصفحة يجب أن يكون بين 1 و {self.page_count}",
                parent=self,
            )
            return

        self.go_to(page - 1)
        self.canvas.focus_set()

    # =========================
    # التكبير
    # =========================
    def _fit_width_zoom(self):
        canvas_w = self.canvas.winfo_width()
        if canvas_w <= 1 or not self.page_sizes:
            return self.zoom

        max_w = max(w for w, _ in self.page_sizes)
        return (canvas_w - 2 * MARGIN) / max_w

    def _fit_page_zoom(self):
        canvas_h = self.canvas.winfo_height()
        if canvas_h <= 1 or not self.page_sizes:
            return self._fit_width_zoom()

        max_h = max(h for _, h in self.page_sizes)
        return min(
            self._fit_width_zoom(), (canvas_h - 2 * MARGIN) / max_h
        )

    def _apply_zoom_mode(self):
        if self.zoom_mode == "width":
            self.zoom = self._fit_width_zoom()
        elif self.zoom_mode == "page":
            self.zoom = self._fit_page_zoom()

        self.zoom = min(max(self.zoom, ZOOM_MIN), ZOOM_MAX)
        self._update_zoom_ui()

    def _update_zoom_ui(self):
        self.zoom_label.configure(text=f"{int(round(self.zoom * 100))}%")
        self.fit_btn.configure(
            fg_color=BTN_ON if self.zoom_mode == "width" else BTN_OFF
        )
        self.fitpage_btn.configure(
            fg_color=BTN_ON if self.zoom_mode == "page" else BTN_OFF
        )

    def set_zoom(self, zoom, mode="custom"):
        self.zoom = min(max(zoom, ZOOM_MIN), ZOOM_MAX)
        self.zoom_mode = mode

        if mode != "custom":
            self._apply_zoom_mode()
        else:
            self._update_zoom_ui()

        self._layout(keep_anchor=True)
        self._schedule_save()

    def zoom_in(self):
        self.set_zoom(self.zoom * ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self.zoom / ZOOM_STEP)

    def ctrl_mouse_zoom(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"

    def actual_size(self):
        self.set_zoom(1.0)

    def fit_width(self):
        self.set_zoom(self.zoom, mode="width")

    def fit_page(self):
        self.set_zoom(self.zoom, mode="page")

    def _on_canvas_configure(self, event):
        size = (event.width, event.height)
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size

        if not self._ready:
            return

        if self._cfg_job:
            try:
                self.after_cancel(self._cfg_job)
            except Exception:
                pass

        self._cfg_job = self._after(120, self._after_resize)

    def _after_resize(self):
        self._cfg_job = None

        if self.zoom_mode in ("width", "page"):
            self._apply_zoom_mode()
            self._schedule_save()

        self._layout(keep_anchor=True)

    # =========================
    # المصغرات (Thumbnails)
    # =========================
    def _thumbs_visible(self):
        return self._thumbs_on

    def toggle_thumbs(self, save=True):
        if self._thumbs_on:
            self._thumbs_on = False
            self.thumb_frame.grid_remove()
            self.thumbs_btn.configure(fg_color=BTN_OFF)
        else:
            self._thumbs_on = True
            self.thumb_frame.grid()
            self.thumbs_btn.configure(fg_color=BTN_ON)

            if self._ready:
                if not self._thumb_built:
                    self._build_thumbs()
                self._start_thumb_job()

        if save:
            self._schedule_save()

        # تغيّر عرض منطقة العرض => تُعاد الملاءمة تلقائياً عبر <Configure>

    def _build_thumbs(self):
        canvas = self.thumb_canvas
        canvas.delete("all")

        self._thumb_imgs.clear()
        self._thumb_sel.clear()
        self._thumb_tops = []
        self._thumb_pending = set(range(self.page_count))

        x0 = (THUMB_PANEL_W - THUMB_W) // 2
        y = 10

        for i in range(self.page_count):
            width, height = self.page_sizes[i]
            thumb_h = max(30, int(THUMB_W * height / width))

            self._thumb_tops.append((y, thumb_h))

            self._thumb_sel[i] = canvas.create_rectangle(
                x0 - 5, y - 5, x0 + THUMB_W + 5, y + thumb_h + 5,
                outline="", fill=""
            )
            canvas.create_rectangle(
                x0, y, x0 + THUMB_W, y + thumb_h,
                fill="white", outline="#cbd5e1"
            )
            canvas.create_text(
                THUMB_PANEL_W // 2, y + thumb_h + 12,
                text=str(i + 1), fill="#334155", font=("Cairo", 9)
            )

            y += thumb_h + THUMB_LABEL_H + 10

        canvas.configure(scrollregion=(0, 0, THUMB_PANEL_W, y))

        self._thumb_built = True
        self._thumb_current = None
        self._highlight_thumb(self.page_index)

    def _start_thumb_job(self):
        if self._thumb_job is None and self._thumb_pending:
            self._thumb_job = self._after(10, self._thumb_step)

    def _on_thumb_yscroll(self, first, last):
        self.thumb_scroll.set(first, last)
        self._start_thumb_job()

    def _thumb_step(self):
        self._thumb_job = None

        if (
            not self.doc or not self._thumb_built
            or not self._thumbs_visible()
        ):
            return

        canvas = self.thumb_canvas
        top = canvas.canvasy(0)
        bottom = top + canvas.winfo_height()

        # الظاهر أولاً ثم بقية الصفحات بالترتيب
        pending = sorted(self._thumb_pending)
        visible = [
            i for i in pending
            if self._thumb_tops[i][0] + self._thumb_tops[i][1] >= top
            and self._thumb_tops[i][0] <= bottom
        ]
        visible_set = set(visible)
        others = [i for i in pending if i not in visible_set]

        for index in (visible + others)[:THUMB_BATCH]:
            self._render_thumb(index)
            self._thumb_pending.discard(index)

        if self.page_count > PROGRESS_MIN_PAGES:
            done = self.page_count - len(self._thumb_pending)
            if self._thumb_pending:
                self._task("thumbs", done / self.page_count, "المصغرات")
            else:
                self._task_done("thumbs")

        if self._thumb_pending:
            self._thumb_job = self._after(8, self._thumb_step)

    def _render_thumb(self, index):
        page = self.doc.load_page(index)
        scale = THUMB_W / page.rect.width

        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        photo = ImageTk.PhotoImage(image)
        x0 = (THUMB_PANEL_W - photo.width()) // 2
        y0 = self._thumb_tops[index][0]

        self.thumb_canvas.create_image(x0, y0, anchor="nw", image=photo)
        self._thumb_imgs[index] = photo

    def _highlight_thumb(self, index):
        if not self._thumb_built:
            return

        previous = self._thumb_current
        if previous is not None and previous in self._thumb_sel:
            self.thumb_canvas.itemconfigure(
                self._thumb_sel[previous], outline="", fill=""
            )

        if index in self._thumb_sel:
            self.thumb_canvas.itemconfigure(
                self._thumb_sel[index], outline=BTN_ON, fill="#bfdbfe", width=2
            )

            # إبقاء المصغرة الحالية ظاهرة
            if self._thumbs_visible():
                y0, height = self._thumb_tops[index]
                top = self.thumb_canvas.canvasy(0)
                bottom = top + self.thumb_canvas.winfo_height()
                region = str(self.thumb_canvas.cget("scrollregion")).split()
                total = float(region[3]) if len(region) == 4 else 1

                if y0 < top or y0 + height > bottom:
                    self.thumb_canvas.yview_moveto(max(0, y0 - 20) / total)

        self._thumb_current = index

    def _on_thumb_click(self, event):
        y = self.thumb_canvas.canvasy(event.y)

        for index, (top, height) in enumerate(self._thumb_tops):
            if top - 8 <= y <= top + height + THUMB_LABEL_H:
                self.go_to(index)
                return

    def _on_thumb_wheel(self, event):
        self.thumb_canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")

    # =========================
    # البحث داخل PDF
    # =========================
    def toggle_search(self):
        if self.search_bar.winfo_ismapped():
            self.close_search()
        else:
            self.open_search()

    def open_search(self):
        self.search_bar.grid()
        self.search_btn.configure(fg_color=BTN_ON)
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def close_search(self):
        self._cancel_search()
        self._clear_hits()

        self.search_bar.grid_remove()
        self.search_btn.configure(fg_color=BTN_OFF)
        self.search_count.configure(text="")
        self.canvas.focus_set()

    def _cancel_search(self):
        self._search_token += 1
        self._task_done("search")

    def _clear_hits(self):
        pages = list(self.hits)

        self.hits = {}
        self.hit_order = []
        self.hit_pos = -1
        self._search_query = ""

        self._invalidate_pages(pages)
        self._schedule_view_update()

    @staticmethod
    def _query_variants(query):
        """
        نصوص PDF العربية في هذا النظام مخزّنة بعد تشكيل الحروف وعكس الاتجاه
        (انظر fix_arabic في pdf_generator)، لذلك نبحث بالنص كما كُتب وبصيغته
        المعروضة معاً.
        """
        variants = [query]

        try:
            import arabic_reshaper
            from bidi.algorithm import get_display

            visual = get_display(arabic_reshaper.reshape(query))
            if visual and visual not in variants:
                variants.append(visual)
        except Exception:
            pass

        return variants

    def _on_search_enter(self, event=None):
        query = self.search_entry.get().strip()

        if query and query == self._search_query and self.hit_order:
            self.next_hit(1)
        else:
            self.run_search()

        return "break"

    def run_search(self):
        query = self.search_entry.get().strip()

        self._cancel_search()
        self._clear_hits()

        if not query or not self.doc:
            self.search_count.configure(text="")
            return

        self._search_query = query
        self._search_variants = self._query_variants(query)
        self._search_pos = 0

        self.search_count.configure(text="جارٍ البحث…")
        self._search_step(self._search_token)

    def _search_step(self, token):
        if token != self._search_token or not self.doc:
            return

        end = min(self._search_pos + SEARCH_CHUNK, self.page_count)
        new_pages = []

        for index in range(self._search_pos, end):
            page = self.doc.load_page(index)
            found = []
            seen = set()

            for variant in self._search_variants:
                for rect in page.search_for(variant):
                    signature = tuple(round(v) for v in (
                        rect.x0, rect.y0, rect.x1, rect.y1
                    ))
                    if signature not in seen:
                        seen.add(signature)
                        found.append(rect)

            if found:
                found.sort(key=lambda r: (round(r.y0), r.x0))
                self.hits[index] = found
                new_pages.append(index)

                for k in range(len(found)):
                    self.hit_order.append((index, k))

        self._search_pos = end
        self._invalidate_pages(new_pages)

        finished = end >= self.page_count

        # اختيار أول نتيجة عند الصفحة الحالية أو بعدها فور ظهورها
        if self.hit_pos < 0 and self.hit_order:
            for pos, (page_no, _k) in enumerate(self.hit_order):
                if page_no >= self.page_index or finished:
                    self._select_hit(pos)
                    break
        else:
            self._schedule_view_update()

        self._update_search_label(finished)

        if finished:
            self._task_done("search")
            if not self.hit_order:
                self.search_count.configure(text="لا توجد نتائج")
        else:
            if self.page_count > PROGRESS_MIN_PAGES:
                self._task("search", end / self.page_count, "بحث")
            self._after(1, lambda: self._search_step(token))

    def _update_search_label(self, finished=True):
        total = len(self.hit_order)

        if total == 0:
            return

        current = self.hit_pos + 1 if self.hit_pos >= 0 else 0
        suffix = "" if finished else "…"
        self.search_count.configure(text=f"{current} من {total}{suffix}")

    def next_hit(self, step=1):
        if not self.search_bar.winfo_ismapped():
            self.open_search()
            return

        if not self.hit_order:
            if self.search_entry.get().strip():
                self.run_search()
            return

        pos = (self.hit_pos + step) % len(self.hit_order)
        self._select_hit(pos)

    def _select_hit(self, pos):
        if not (0 <= pos < len(self.hit_order)):
            return

        old = self.hit_order[self.hit_pos] if self.hit_pos >= 0 else None
        self.hit_pos = pos
        page_no, k = self.hit_order[pos]

        pages = {page_no}
        if old:
            pages.add(old[0])
        self._invalidate_pages(pages)

        rect = self.hits[page_no][k]

        # تمرير النتيجة إلى ثلث الشاشة تقريباً
        y = self.page_tops[page_no] + rect.y0 * self.zoom
        x = self.page_xs[page_no] + rect.x0 * self.zoom

        canvas_h = self.canvas.winfo_height()
        canvas_w = self.canvas.winfo_width()

        self.canvas.yview_moveto(max(0, y - canvas_h / 3) / self.total_h)

        if self.view_w > canvas_w:
            self.canvas.xview_moveto(
                max(0, x - canvas_w / 3) / self.view_w
            )

        self._set_current(page_no)
        self._schedule_view_update()
        self._update_search_label(self._search_pos >= self.page_count)

    # =========================
    # ملء الشاشة
    # =========================
    def toggle_fullscreen(self):
        try:
            if not self._fullscreen:
                self._prev_geometry = self.geometry()

                try:
                    self.transient("")      # النوافذ التابعة لا تدعم ملء الشاشة جيداً
                except tk.TclError:
                    pass

                self.attributes("-fullscreen", True)
                self._fullscreen = True
                self.fullscreen_btn.configure(text="🗗 خروج")
            else:
                self.attributes("-fullscreen", False)

                if self._prev_geometry:
                    self.geometry(self._prev_geometry)

                try:
                    self.transient(self._parent)
                except tk.TclError:
                    pass

                self._fullscreen = False
                self.fullscreen_btn.configure(text="⛶ ملء الشاشة")

            self.update_status_bar()
            self.focus_force()

            try:
                self.grab_set()
            except tk.TclError:
                pass

        except tk.TclError:
            # بعض أنظمة النوافذ: نستخدم التكبير الكامل بديلاً
            try:
                self.state("normal" if self._fullscreen else "zoomed")
                self._fullscreen = not self._fullscreen
            except tk.TclError:
                pass

    # =========================
    # شريط الحالة
    # =========================
    def update_status_bar(self):
        if not hasattr(self, "status_label") or not self._ready:
            return

        mode_names = {
            "width": "ملاءمة العرض",
            "page": "صفحة كاملة",
        }
        zoom_text = f"{int(round(self.zoom * 100))}%"
        if self.zoom_mode in mode_names:
            zoom_text += f" ({mode_names[self.zoom_mode]})"

        parts = [
            f"صفحة {self.page_index + 1} من {self.page_count}",
            f"التكبير: {zoom_text}",
        ]

        if self.hand_tool:
            parts.append("أداة اليد مفعّلة")

        if self._flash:
            parts = [self._flash]

        self.status_label.configure(text="    |    ".join(parts))

    def _flash_status(self, text, ms=5000):
        self._flash = text
        self.update_status_bar()

        def clear():
            self._flash = ""
            self.update_status_bar()

        self._after(ms, clear)

    # =========================
    # فتح PDF
    # =========================
    def open_pdf(self):
        if not os.path.exists(self.pdf_path):
            mb.showerror("خطأ", "ملف PDF غير موجود", parent=self)
            return

        try:
            open_pdf_safely(self.pdf_path)
        except Exception as e:
            mb.showerror("خطأ", str(e), parent=self)

    # =========================
    # مشاركة عبر واتساب
    # =========================
    def send_whatsapp(self):
        url = "https://wa.me/?text=" + urllib.parse.quote(self.share_message)
        webbrowser.open(url)

    # =========================
    # مشاركة عبر البريد
    # =========================
    def send_email(self):
        subject = urllib.parse.quote(self.email_subject)
        body = urllib.parse.quote(self.email_body)
        webbrowser.open(f"mailto:?subject={subject}&body={body}")

    # =========================
    # الطباعة المباشرة
    # =========================
    def print_pdf(self):
        if self._print_gen is not None:
            return  # طباعة جارية

        if not self.doc:
            return

        if not os.path.exists(self.pdf_path):
            mb.showerror("خطأ", "ملف PDF غير موجود", parent=self)
            return

        dialog = PrintDialog(
            self,
            self.page_count,
            self.page_index,
            last_printer=get_setting(SETTING_PRINTER, "") or "",
        )
        self.wait_window(dialog)

        try:
            self.grab_set()
        except tk.TclError:
            pass

        if not self._alive or not dialog.result:
            return

        result = dialog.result

        if result["printer"]:
            set_setting(SETTING_PRINTER, result["printer"])

        self._print_total = len(result["pages"]) * result["copies"]
        self._print_printer = result["printer"]

        self._print_gen = iter_print_pdf(
            self.pdf_path,
            printer_name=result["printer"],
            page_indexes=result["pages"],
            copies=result["copies"],
        )

        self.print_btn.configure(state="disabled")
        self._task("print", 0.0, "جارٍ الطباعة")
        self._after(30, self._print_step)

    def _print_step(self):
        gen = self._print_gen
        if gen is None:
            return

        try:
            event = next(gen)

        except StopIteration:
            self._finish_print(None, None)
            return

        except Exception as e:
            self._finish_print(None, str(e))
            return

        if event[0] == "progress":
            _kind, done, total = event
            self._task("print", done / max(total, 1), "جارٍ الطباعة")
            self._after(1, self._print_step)
        else:
            self._finish_print(event[1], None)

    def _finish_print(self, method, error):
        self._print_gen = None
        self._task_done("print")

        if self._alive:
            self.print_btn.configure(state="normal")

        if error:
            mb.showerror("خطأ في الطباعة", error, parent=self)
            return

        if method == "direct":
            target = f" ({self._print_printer})" if self._print_printer else ""
            self._flash_status(
                f"تم إرسال {self._print_total} صفحة إلى الطابعة{target}"
            )
        elif method:
            self._flash_status("تم إرسال المستند للطباعة")

    # =========================
    # حفظ باسم
    # =========================
    def save_as(self):
        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=os.path.basename(self.pdf_path),
        )

        if not file_path:
            return

        try:
            with open(self.pdf_path, "rb") as source:
                with open(file_path, "wb") as target:
                    target.write(source.read())

            mb.showinfo("تم", "تم حفظ الملف بنجاح", parent=self)
        except Exception as e:
            mb.showerror("خطأ", str(e), parent=self)

    # =========================
    # إغلاق النافذة
    # =========================
    def on_close(self):
        if not self._alive:
            return

        # حفظ آخر مستوى تكبير
        if self._ready:
            try:
                self._save_prefs()
            except Exception:
                pass

        self._alive = False

        # إيقاف الطباعة الجارية (يُجهض المهمة عبر GeneratorExit)
        if self._print_gen is not None:
            try:
                self._print_gen.close()
            except Exception:
                pass
            self._print_gen = None

        self._search_token += 1

        try:
            if self.doc:
                self.doc.close()
        except Exception:
            pass

        self.doc = None

        if self._fullscreen:
            try:
                self.attributes("-fullscreen", False)
            except tk.TclError:
                pass

        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()
