# ui/components/period.py
"""فلاتر الفترات الزمنية المشتركة (اليوم / الأسبوع / الشهر / سنة)."""

import calendar
from datetime import date, datetime, timedelta

PERIODS = ["الكل", "اليوم", "الأسبوع", "الشهر", "سنة"]


def year_choices(count=10):
    """قائمة سنوات من الحالية إلى الوراء (نصوص)."""
    current = date.today().year
    return [str(y) for y in range(current, current - count, -1)]


def period_range(label, year=None, today=None):
    """
    يحوّل اسم الفترة إلى (بداية، نهاية) بصيغة YYYY-MM-DD.
    «الكل» أو أي اسم غير معروف → (None, None).
    """
    today = today or date.today()

    if label == "اليوم":
        return today.isoformat(), today.isoformat()

    if label == "الأسبوع":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()

    if label == "الشهر":
        last_day = calendar.monthrange(today.year, today.month)[1]
        return (
            date(today.year, today.month, 1).isoformat(),
            date(today.year, today.month, last_day).isoformat(),
        )

    if label == "سنة":
        chosen = int(year or today.year)
        return f"{chosen}-01-01", f"{chosen}-12-31"

    return None, None


def in_period(value, start, end):
    """هل التاريخ ضمن الفترة؟ (بدون فترة → دائماً صحيح)."""
    if not start and not end:
        return True

    text = str(value or "")

    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False

    return (not start or text >= start) and (not end or text <= end)
