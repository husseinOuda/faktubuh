# arabic_words.py
"""تفقيط المبالغ بالعربية (مثال: 1250.50 → ألف ومائتان وخمسون شيكلاً وخمسون أغورة)."""

from decimal import Decimal, ROUND_HALF_UP

_ONES_M = [
    "", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية",
    "تسعة", "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر",
    "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر",
]

_ONES_F = [
    "", "واحدة", "اثنتان", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثمان",
    "تسع", "عشر", "إحدى عشرة", "اثنتا عشرة", "ثلاث عشرة", "أربع عشرة",
    "خمس عشرة", "ست عشرة", "سبع عشرة", "ثماني عشرة", "تسع عشرة",
]

_TENS = [
    "", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون",
    "ثمانون", "تسعون",
]

_HUNDREDS = [
    "", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة",
    "سبعمائة", "ثمانمائة", "تسعمائة",
]

# (اسم المفرد، المثنى، الجمع)
_SCALES = [
    None,
    ("ألف", "ألفان", "آلاف"),
    ("مليون", "مليونان", "ملايين"),
    ("مليار", "ملياران", "مليارات"),
]


def _below_100(n, feminine):
    ones = _ONES_F if feminine else _ONES_M

    if n < 20:
        return ones[n]

    tens, unit = divmod(n, 10)

    if unit == 0:
        return _TENS[tens]

    return f"{ones[unit]} و{_TENS[tens]}"


def _below_1000(n, feminine):
    hundreds, rest = divmod(n, 100)
    parts = []

    if hundreds:
        parts.append(_HUNDREDS[hundreds])

    if rest:
        parts.append(_below_100(rest, feminine))

    return " و".join(parts)


def number_to_words(n, feminine=False, tanween=True):
    """
    عدد صحيح موجب (حتى مئات المليارات) → كلمات عربية.
    tanween: تنوين ألفاً/مليوناً عندما تكون آخر كلمة في العدد (11..99).
    """

    n = int(n)

    if n == 0:
        return "صفر"

    if n >= 10 ** 12:
        raise ValueError("الرقم أكبر من الحد المدعوم")

    groups = []

    while n:
        n, group = divmod(n, 1000)
        groups.append(group)

    parts = []
    last_index = min(i for i, g in enumerate(groups) if g)

    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]

        if not group:
            continue

        if index == 0:
            parts.append(_below_1000(group, feminine))
            continue

        single, dual, plural = _SCALES[index]

        if group == 1:
            parts.append(single)
        elif group == 2:
            parts.append(dual)
        elif group <= 10:
            parts.append(f"{_below_1000(group, False)} {plural}")
        else:
            rest = group % 100
            words = _below_1000(group, False)

            # مائتا ألف / ثلاثمائة ألف ... (إضافة)
            if group == 200:
                words = "مائتا"

            # 11..99 تمييزها منصوب: خمسة وعشرون ألفاً (إن كانت آخر كلمة)
            tail = single

            if tanween and index == last_index and 11 <= rest <= 99:
                tail = f"{single}اً"

            parts.append(f"{words} {tail}")

    return " و".join(parts)


def _shekel_phrase(n):
    if n == 1:
        return "شيكل واحد"
    if n == 2:
        return "شيكلان"

    rest = n % 100

    # 3..10 بعد المئات/الآلاف تأخذ الجمع، و11..99 التمييز منصوب
    if 3 <= rest <= 10:
        return f"{number_to_words(n, tanween=False)} شواكل"
    if 11 <= rest <= 99:
        return f"{number_to_words(n, tanween=False)} شيكلاً"
    return f"{number_to_words(n, tanween=False)} شيكل"


def _agora_phrase(n):
    if n == 1:
        return "أغورة واحدة"
    if n == 2:
        return "أغورتان"
    if 3 <= n <= 10:
        return f"{number_to_words(n, feminine=True)} أغورات"
    return f"{number_to_words(n, feminine=True)} أغورة"


def amount_to_words(amount, prefix="فقط", suffix="لا غير"):
    """
    1250.50 → «فقط ألف ومائتان وخمسون شيكلاً وخمسون أغورة لا غير».
    المبلغ صفر/غير صالح يرجع نصاً فارغاً.
    """
    try:
        value = Decimal(str(amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return ""

    if value <= 0:
        return ""

    whole = int(value)
    cents = int((value - whole) * 100)

    parts = []

    if whole:
        parts.append(_shekel_phrase(whole))

    if cents:
        parts.append(_agora_phrase(cents))

    text = " و".join(parts)

    return " ".join(p for p in (prefix, text, suffix) if p)
