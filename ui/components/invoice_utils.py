# ui/components/invoice_utils.py

"""أدوات مساعدة لحساب الفواتير ودعم أرقام الفاصلة العربية."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CURRENCY = "₪"

_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789"
)


class NumberParseError(ValueError):
    """خطأ مخصص عندما تكون قيمة رقمية غير صالحة."""


def round_money(value):
    """تقريب مالي إلى خانتين عشريتين."""
    return float(
        Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )


def parse_number(value, field_name="القيمة", allow_zero=True, positive=False):
    """
    دعم:
    - الفاصلة العشرية العربية: ,
    - النقطة: .
    - الفاصلة المنقوطة: ،
    - الأرقام العربية والهندية
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        text = str(value).strip()

        if not text:
            raise NumberParseError(f"يرجى إدخال {field_name}")

        text = text.translate(_DIGIT_TRANSLATION)
        text = (
            text.replace("٪", "")
                .replace("%", "")
                .replace(CURRENCY, "")
                .replace(" ", "")
                .replace("٬", "")
        )

        text = text.replace("،", ",")

        # إذا وُجدت الفاصلة والنقطة معاً، آخر فاصلة تعتبر عشرية
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "")
            else:
                text = text.replace(",", "")

        if text.count(",") > 1 or text.count(".") > 1:
            raise NumberParseError(
                f"صيغة {field_name} غير صحيحة. مثال: 12,50 أو 12.50"
            )

        text = text.replace(",", ".")

        try:
            number = float(text)
        except (TypeError, ValueError):
            raise NumberParseError(
                f"{field_name} يجب أن يكون رقماً صحيحاً أو عشرياً"
            ) from None

    if number != number:
        raise NumberParseError(f"{field_name} غير صالح")

    if positive and number <= 0:
        raise NumberParseError(f"{field_name} يجب أن يكون أكبر من صفر")

    if not allow_zero and number == 0:
        raise NumberParseError(f"{field_name} لا يمكن أن يكون صفراً")

    if number < 0:
        raise NumberParseError(f"{field_name} لا يمكن أن يكون سالباً")

    return number


def calculate_invoice_totals(items, discount_percent=0, tax_percent=0):
    """حساب الإجمالي بعد الخصم والضريبة."""

    subtotal = round_money(
        sum(
            parse_number(item.get("total", 0), "إجمالي الصنف")
            for item in items
        )
    )

    discount_percent = round_money(
        parse_number(discount_percent, "نسبة الخصم")
    )

    tax_percent = round_money(
        parse_number(tax_percent, "نسبة الضريبة")
    )

    discount_amount = round_money(
        subtotal * discount_percent / 100
    )

    taxable_amount = round_money(
        subtotal - discount_amount
    )

    tax_amount = round_money(
        taxable_amount * tax_percent / 100
    )

    total = round_money(
        taxable_amount + tax_amount
    )

    return {
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "tax_percent": tax_percent,
        "tax_amount": tax_amount,
        "total": total,
    }


def format_money(value, symbol=True):
    """تنسيق مبلغ بخانتين عشريتين."""
    value = round_money(value)
    text = f"{value:,.2f}"

    if symbol:
        return f"{text} {CURRENCY}"

    return text


def shorten_text(text, max_length=45):
    """اختصار الملاحظات عند عرضها في الجداول."""
    text = str(text or "").strip()

    if len(text) <= max_length:
        return text

    return text[: max_length - 1].rstrip() + "…"