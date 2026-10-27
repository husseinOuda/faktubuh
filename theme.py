# STYLES 

PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
SUCCESS = "#16a34a"
WARNING = "#f59e0b"
DANGER = "#dc2626"

BACKGROUND = "#f5f7fb"
CARD = "#ffffff"
TEXT = "#111827"
MUTED = "#6b7280"

FONT = "Cairo"

# =========================
# BTN STYLE
# =========================
BTN_STYLE = {
    "height": 50,
    "corner_radius": 12,
    "anchor": "w",
    "font": ("Cairo", 16, "bold"),
    "fg_color": "#1f2937",
    "hover_color": "#374151"
}

# =========================
# ENTRY STYLE
# =========================
ENTRY_STYLE = {
    "height": 45,
    "corner_radius": 10,
    "font": ("Cairo", 14)
}

# =========================
# PRIMARY BTN
# =========================
PRIMARY_BTN = {
    "fg_color": "#2563eb",
    "hover_color": "#1d4ed8",
    "height": 45,
    "corner_radius": 10,
    "font": ("Cairo", 14, "bold")
}

DANGER_BTN = {
    "fg_color": "#dc2626",
    "hover_color": "#b91c1c",
    "height": 45,
    "corner_radius": 10,
    "font": ("Cairo", 14, "bold")
}



# =========================
# الهوية البصرية للفواتير (0.1.5)
# =========================
# ألوان مأخوذة من الشعار (أزرق/كحلي) وتُستخدم في الجداول والـ PDF
BRAND_NAVY = "#0f2a5c"       # الترويسة ورؤوس الجداول
BRAND_BLUE = "#2563eb"       # اللون الأساسي (نفس PRIMARY)
BRAND_LIGHT = "#eef4ff"      # خلفيات فاتحة (تسميات، ملخصات)
TABLE_GRID = "#d6deeb"       # خطوط الجدول
TABLE_ZEBRA = "#f6f9fe"      # تلوين الصفوف المتناوب
TABLE_HOVER = "#e0e7ff"      # تمييز الصف عند مرور الفأرة
TABLE_SELECT = "#2563eb"     # لون الصف المحدد

# ألوان حالات الفاتورة
STATUS_COLORS = {
    "paid": "#15803d",
    "unpaid": "#c2410c",
    "cancelled": "#b91c1c",
}

# =========================
# بيانات الجهة المُصدِرة (تظهر في ترويسة وتذييل الفاتورة PDF)
# عدّل القيم هنا فقط، والحقول الفارغة لا تُطبع.
# =========================
COMPANY = {
    "name": "Tech Makers",
    "tagline": "",                     # مثال: حلول وخدمات تقنية
    "phone": "",                       # مثال: 0599-000000
    "email": "",
    "address": "",                     # مثال: نابلس - فلسطين
    "tax_no": "",                      # الرقم الضريبي إن وُجد
    "footer_note": "شكراً لتعاملكم معنا",
    "signatory": "",                   # اسم المُصدِر تحت التوقيع (اختياري)
}
