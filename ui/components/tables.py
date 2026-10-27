# ui/components/tables.py
"""
أدوات مشتركة لجعل جداول Treeview تبدو كجداول برامج المحاسبة:
  - رأس بلون الهوية البصرية
  - صفوف متناوبة الألوان (Zebra)
  - خطوط فاصلة هادئة وتحديد واضح
  - ترتيب أعمدة من اليمين لليسار (عربي)
"""

from tkinter import ttk

from theme import (
    BRAND_NAVY,
    TABLE_GRID,
    TABLE_SELECT,
    TABLE_ZEBRA,
)

# اسم النمط الموحد لجداول الفواتير
STYLE_NAME = "Invoice.Treeview"

ROW_EVEN_TAG = "row_even"
ROW_ODD_TAG = "row_odd"


def setup_table_style(master=None, row_height=38):
    """يهيّئ نمط الجدول مرة واحدة (آمن للاستدعاء المتكرر)."""
    style = ttk.Style(master)

    # لا نغيّر الثيم إذا كان مضبوطاً مسبقاً على default
    if style.theme_use() != "default":
        style.theme_use("default")

    style.configure(
        STYLE_NAME,
        rowheight=row_height,
        font=("Cairo", 12),
        background="#ffffff",
        fieldbackground="#ffffff",
        foreground="#111827",
        bordercolor=TABLE_GRID,
        borderwidth=1,
        relief="flat",
    )

    style.configure(
        f"{STYLE_NAME}.Heading",
        font=("Cairo", 12, "bold"),
        background=BRAND_NAVY,
        foreground="#ffffff",
        relief="flat",
        borderwidth=1,
        padding=(8, 9),
    )

    style.map(
        STYLE_NAME,
        background=[("selected", TABLE_SELECT)],
        foreground=[("selected", "#ffffff")],
    )

    style.map(
        f"{STYLE_NAME}.Heading",
        background=[("active", "#1b3a7a")],
    )

    # شريط تمرير أنحف وأهدأ
    style.configure(
        "Invoice.Vertical.TScrollbar",
        troughcolor="#f1f5f9",
        background="#cbd5e1",
        bordercolor="#f1f5f9",
        arrowcolor="#64748b",
        relief="flat",
    )

    return STYLE_NAME


def configure_zebra(table):
    """يعرّف وسوم تلوين الصفوف المتناوبة على الجدول."""
    table.tag_configure(ROW_EVEN_TAG, background="#ffffff")
    table.tag_configure(ROW_ODD_TAG, background=TABLE_ZEBRA)


def zebra_tag(position):
    """وسم الصف حسب ترتيبه (يبدأ من 0)."""
    return ROW_ODD_TAG if position % 2 else ROW_EVEN_TAG


def rtl_columns(*logical_order):
    """
    يحوّل ترتيب الأعمدة المنطقي (الأول = الأقرب لليمين) إلى ترتيب العرض
    في Treeview الذي يرسم من اليسار لليمين.
    مثال: rtl_columns("no", "name", "total") -> ("total", "name", "no")
    """
    return tuple(reversed(logical_order))
