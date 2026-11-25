# purchases_db.py
"""
الموردون والمشتريات (0.1.9) — طبقة قاعدة البيانات.

  الموردون        : بيانات المورد + رصيده المستحق + إجمالي المشتريات + آخر شراء.
  أوامر الشراء    : مثل فاتورة العميل (أصناف، خصم، ضريبة، ملاحظات) مع
                    المدفوع والمتبقي، وترقيم PO-2026-0001 يبدأ كل سنة من 0001.
  دفعات الموردين  : سندات صرف (PV) تُربط بالمورد وبأمر الشراء، فتظهر أيضاً في
                    «سندات الصرف» وتدخل في المدفوعات والنقدية.
  استلام البضاعة : مستندات استلام GR-2026-0001 (جزئي أو كامل) مقابل أصناف أمر
                    الشراء؛ لا يُستلم أكثر من المطلوب، ولا أثر مالي لها.
  حساب المورد     : كشف حساب بالتسلسل الزمني (get_supplier_statement).
  الباركود        : لكل صنف في أمر الشراء باركود اختياري؛ يتذكّر البرنامج الأصناف
                    المعروفة (جدول products) ليُكمل المسح بياناتها، ويُستعمل
                    المسح أيضاً في الاستلام (get_product_by_barcode).

تعريف رصيد المورد (موجب = مستحق للمورد علينا · سالب = دفعة مقدّمة لنا):

    الرصيد = المتبقي على أوامر شرائه غير الملغاة
             − الدفعات غير المطبّقة على أمر نشط

  الدفعات غير المطبّقة = سندات صرف فعّالة للمورد بلا أمر شراء (دفعة على
  الحساب) + سندات مرتبطة بأمر شراء صار ملغى.  (نفس منطق رصيد العميل.)

الجداول تُنشأ في database._create_purchase_tables.
"""

import sqlite3

from database import (
    BALANCE_CREDIT,
    BALANCE_DEBIT,
    BALANCE_ZERO,
    VOUCHER_ACTIVE,
    VOUCHER_CANCELLED,
    _EMAIL_RE,
    _EPS,
    _as_id_list,
    _calculate_invoice_totals,
    _clean_amount,
    _clean_date,
    _clean_method,
    _fmt,
    _money,
    _next_number,
    _validate_po_payment,
    balance_state,
    connect,
    db_connection,
)

# ======================
# تسميات
# ======================
SUPPLIER_FIELDS = ("name", "phone", "address", "email", "notes")

SUPPLIER_BALANCE_LABELS = {
    BALANCE_DEBIT: "مستحق للمورد",
    BALANCE_CREDIT: "دفعة مقدّمة",
    BALANCE_ZERO: "مسدّد",
}

PO_UNPAID = "unpaid"
PO_PARTIAL = "partial"
PO_PAID = "paid"

PO_PAY_STATUSES = {
    PO_UNPAID: "غير مسدد",
    PO_PARTIAL: "مسدد جزئياً",
    PO_PAID: "مسدد",
}

RECEIVE_NONE = "none"
RECEIVE_PARTIAL = "partial"
RECEIVE_FULL = "full"

RECEIVE_STATUSES = {
    RECEIVE_NONE: "لم يُستلم",
    RECEIVE_PARTIAL: "استلام جزئي",
    RECEIVE_FULL: "مستلم بالكامل",
}


def receive_status_label(status):
    return RECEIVE_STATUSES.get(status, RECEIVE_STATUSES[RECEIVE_NONE])

PO_STATUSES = {
    VOUCHER_ACTIVE: "فعّال",
    VOUCHER_CANCELLED: "ملغى",
}


def po_pay_status_label(status):
    return PO_PAY_STATUSES.get(status, PO_PAY_STATUSES[PO_UNPAID])


def po_status_label(status):
    return PO_STATUSES.get(status, PO_STATUSES[VOUCHER_ACTIVE])


def supplier_balance_text(supplier, money_formatter):
    """«مستحق للمورد 150.00 ₪» / «دفعة مقدّمة 20.00 ₪» / «مسدّد»."""
    state = supplier["balance_state"]

    if state == BALANCE_ZERO:
        return SUPPLIER_BALANCE_LABELS[BALANCE_ZERO]

    return (
        f"{SUPPLIER_BALANCE_LABELS[state]} "
        f"{money_formatter(abs(supplier['balance']))}"
    )


# ======================================================================
# الموردون
# ======================================================================
def _clean_supplier_field(field, value):
    """يرجع القيمة المنظّفة أو يرفع ValueError برسالة عربية واضحة."""
    text = str(value or "").strip()

    if field == "name":
        if not text:
            raise ValueError("اسم المورد مطلوب")

    elif field == "email":
        if text and not _EMAIL_RE.match(text):
            raise ValueError(
                "صيغة البريد الإلكتروني غير صحيحة (مثال: name@example.com)"
            )

    elif field not in SUPPLIER_FIELDS:
        raise ValueError("حقل غير معروف")

    return text


def add_supplier(name, phone="", address="", email="", notes=""):
    """يضيف مورداً ويرجع رقمه. يرفع ValueError عند التكرار أو بيانات خاطئة."""
    values = (
        _clean_supplier_field("name", name),
        _clean_supplier_field("phone", phone),
        _clean_supplier_field("email", email),
        _clean_supplier_field("address", address),
        _clean_supplier_field("notes", notes),
    )

    try:
        with db_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO suppliers (name, phone, email, address, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                values
            )
            return cursor.lastrowid

    except sqlite3.IntegrityError:
        raise ValueError("اسم المورد موجود مسبقاً") from None


def update_supplier(supplier_id, name, phone="", address="", email="",
                    notes=""):
    values = (
        _clean_supplier_field("name", name),
        _clean_supplier_field("phone", phone),
        _clean_supplier_field("email", email),
        _clean_supplier_field("address", address),
        _clean_supplier_field("notes", notes),
        supplier_id,
    )

    try:
        with db_connection() as conn:
            conn.execute(
                "UPDATE suppliers SET name=?, phone=?, email=?, address=?, "
                "notes=? WHERE id=?",
                values
            )

    except sqlite3.IntegrityError:
        raise ValueError("اسم المورد موجود مسبقاً") from None


def update_supplier_field(supplier_id, field, value):
    """تعديل حقل واحد (للتعديل المباشر داخل الجدول). يرجع القيمة المنظّفة."""
    if field not in SUPPLIER_FIELDS:
        raise ValueError("هذا الحقل غير قابل للتعديل")

    cleaned = _clean_supplier_field(field, value)

    try:
        with db_connection() as conn:
            conn.execute(
                f"UPDATE suppliers SET {field}=? WHERE id=?",
                (cleaned, supplier_id)
            )

    except sqlite3.IntegrityError:
        raise ValueError("اسم المورد موجود مسبقاً") from None

    return cleaned


def delete_supplier(supplier_id):
    """لا يُحذف مورد لديه أوامر شراء أو سندات صرف (حماية الأثر المحاسبي)."""
    with db_connection() as conn:
        orders = conn.execute(
            "SELECT COUNT(*) FROM purchase_orders WHERE supplier_id=?",
            (supplier_id,)
        ).fetchone()[0]

        if orders:
            raise ValueError(
                f"لا يمكن حذف مورد لديه أوامر شراء (عددها: {orders}).\n"
                "احذف أوامره أولاً."
            )

        vouchers = conn.execute(
            "SELECT COUNT(*) FROM payment_vouchers WHERE supplier_id=?",
            (supplier_id,)
        ).fetchone()[0]

        if vouchers:
            raise ValueError(
                f"لا يمكن حذف مورد لديه سندات صرف (عددها: {vouchers}).\n"
                "احذف سنداته أولاً."
            )

        conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))


# ----------------------
# الملخص المالي للمورد
# ----------------------
def _empty_supplier_financials():
    return {
        "orders_count": 0,
        "cancelled_count": 0,
        "purchases": 0.0,
        "paid": 0.0,
        "remaining": 0.0,
        "advance": 0.0,
        "balance": 0.0,
        "balance_state": BALANCE_ZERO,
        "last_purchase_date": "",
        "last_payment_date": "",
    }


def _supplier_financials(conn, supplier_id=None):
    """
    {supplier_id: ملخّص مالي} لكل الموردين أو لمورد واحد
    (ثلاثة استعلامات فقط مهما كان عدد الموردين).
    """
    scope = "" if supplier_id is None else "AND po.supplier_id = ?"
    params = () if supplier_id is None else (supplier_id,)

    result = {}

    def entry_for(sid):
        return result.setdefault(sid, _empty_supplier_financials())

    # أوامر الشراء + المدفوع عليها
    for sid, total, status, date, paid in conn.execute(
        f"""
        SELECT
            po.supplier_id, po.total, COALESCE(po.status, 'active'),
            COALESCE(po.date, ''),
            COALESCE((
                SELECT SUM(v.amount) FROM payment_vouchers v
                WHERE v.purchase_order_id = po.id
                  AND COALESCE(v.status, 'active') = 'active'
            ), 0)
        FROM purchase_orders po
        WHERE 1 = 1 {scope}
        """,
        params
    ).fetchall():
        entry = entry_for(sid)

        if status == VOUCHER_CANCELLED:
            entry["cancelled_count"] += 1
            # ما دفعناه على أمر صار ملغى يبقى رصيداً لنا عند المورد
            entry["advance"] += _money(paid)
            continue

        entry["orders_count"] += 1
        entry["purchases"] += _money(total)
        entry["paid"] += min(_money(paid), _money(total))
        entry["remaining"] += max(_money(total) - _money(paid), 0.0)

        if date > entry["last_purchase_date"]:
            entry["last_purchase_date"] = date

    voucher_scope = "" if supplier_id is None else "AND v.supplier_id = ?"

    # دفعات على الحساب (بلا أمر شراء)
    for sid, amount in conn.execute(
        f"""
        SELECT v.supplier_id, SUM(v.amount)
        FROM payment_vouchers v
        WHERE v.supplier_id IS NOT NULL
          AND v.purchase_order_id IS NULL
          AND COALESCE(v.status, 'active') = 'active'
          {voucher_scope}
        GROUP BY v.supplier_id
        """,
        params
    ).fetchall():
        entry_for(sid)["advance"] += _money(amount)

    for sid, last_date in conn.execute(
        f"""
        SELECT v.supplier_id, MAX(COALESCE(v.date, ''))
        FROM payment_vouchers v
        WHERE v.supplier_id IS NOT NULL
          AND COALESCE(v.status, 'active') = 'active'
          {voucher_scope}
        GROUP BY v.supplier_id
        """,
        params
    ).fetchall():
        entry_for(sid)["last_payment_date"] = last_date

    for entry in result.values():
        entry["purchases"] = _money(entry["purchases"])
        entry["paid"] = _money(entry["paid"])
        entry["remaining"] = _money(entry["remaining"])
        entry["advance"] = _money(entry["advance"])
        entry["balance"] = _money(entry["remaining"] - entry["advance"])
        entry["balance_state"] = balance_state(entry["balance"])

    return result


_SUPPLIER_SELECT = (
    "SELECT id, name, COALESCE(phone, ''), COALESCE(email, ''), "
    "COALESCE(address, ''), COALESCE(notes, '') FROM suppliers"
)

_SUPPLIER_KEYS = ("id", "name", "phone", "email", "address", "notes")


def _supplier_dict(row, financials):
    data = dict(zip(_SUPPLIER_KEYS, row))
    data.update(financials.get(data["id"]) or _empty_supplier_financials())
    return data


def get_suppliers_full():
    """كل الموردين بكامل بياناتهم وملخصهم المالي (الأحدث أولاً)."""
    conn = connect()

    try:
        rows = conn.execute(_SUPPLIER_SELECT + " ORDER BY id DESC").fetchall()
        financials = _supplier_financials(conn)
    finally:
        conn.close()

    return [_supplier_dict(row, financials) for row in rows]


def get_supplier(supplier_id):
    """مورد واحد بكامل بياناته وملخصه المالي، أو None."""
    conn = connect()

    try:
        row = conn.execute(
            _SUPPLIER_SELECT + " WHERE id = ?", (supplier_id,)
        ).fetchone()

        if not row:
            return None

        financials = _supplier_financials(conn, supplier_id)
    finally:
        conn.close()

    return _supplier_dict(row, financials)


# ======================================================================
# أوامر الشراء
# ======================================================================
def next_supplier_invoice_number():
    """
    رقم فاتورة المورد المقترح: يبدأ من 1 ثم يتسلسل تصاعدياً
    (أكبر رقم صرف مستخدم + 1). الأرقام غير الرقمية التي يكتبها
    المستخدم يدوياً لا تؤثر على التسلسل.
    """
    conn = connect()

    try:
        rows = conn.execute(
            "SELECT supplier_invoice_no FROM purchase_orders"
        ).fetchall()
    finally:
        conn.close()

    last = 0

    for (number,) in rows:
        text = str(number or "").strip()

        if text.isdigit():
            last = max(last, int(text))

    return str(last + 1)


def preview_po_number():
    """رقم أمر الشراء التالي للعرض فقط (يُحجز فعلياً عند الحفظ)."""
    conn = connect()

    try:
        return _next_number(conn.cursor(), "purchase_orders", "po_number", "PO")
    finally:
        conn.close()


_PO_SELECT = """
    SELECT
        po.id, po.po_number, po.supplier_id, s.name,
        COALESCE(po.supplier_invoice_no, ''), po.date,
        po.subtotal, po.discount_percent, po.discount_amount,
        po.tax_percent, po.tax_amount, po.total,
        COALESCE(po.notes, ''), COALESCE(po.status, 'active'),
        COALESCE((
            SELECT SUM(v.amount) FROM payment_vouchers v
            WHERE v.purchase_order_id = po.id
              AND COALESCE(v.status, 'active') = 'active'
        ), 0),
        (SELECT COUNT(*) FROM purchase_order_items i
         WHERE i.purchase_order_id = po.id),
        COALESCE((SELECT SUM(i.quantity) FROM purchase_order_items i
                  WHERE i.purchase_order_id = po.id), 0),
        COALESCE((
            SELECT SUM(gi.quantity)
            FROM goods_receipt_items gi
            JOIN goods_receipts g ON g.id = gi.goods_receipt_id
            WHERE g.purchase_order_id = po.id
              AND COALESCE(g.status, 'active') = 'active'
        ), 0)
    FROM purchase_orders po
    LEFT JOIN suppliers s ON s.id = po.supplier_id
"""

_PO_KEYS = (
    "id", "po_number", "supplier_id", "supplier", "supplier_invoice_no",
    "date", "subtotal", "discount_percent", "discount_amount",
    "tax_percent", "tax_amount", "total", "notes", "status", "paid",
    "items_count", "ordered_qty", "received_qty",
)


def _po_pay_status(total, paid):
    total, paid = _money(total), _money(paid)

    if paid <= _EPS:
        return PO_UNPAID

    if paid >= total - _EPS:
        return PO_PAID

    return PO_PARTIAL


def _receive_status(ordered, received):
    ordered, received = float(ordered or 0), float(received or 0)

    if received <= _EPS:
        return RECEIVE_NONE

    if received >= ordered - _EPS:
        return RECEIVE_FULL

    return RECEIVE_PARTIAL


def _po_dict(row):
    data = dict(zip(_PO_KEYS, row))

    data["supplier"] = data["supplier"] or "-"
    data["date"] = data["date"] or ""
    data["total"] = _money(data["total"])
    data["paid"] = _money(data["paid"])
    data["remaining"] = (
        0.0 if data["status"] == VOUCHER_CANCELLED
        else max(_money(data["total"] - data["paid"]), 0.0)
    )
    data["pay_status"] = _po_pay_status(data["total"], data["paid"])
    data["receive_status"] = _receive_status(
        data["ordered_qty"], data["received_qty"]
    )
    return data


def get_purchase_orders():
    conn = connect()

    try:
        rows = conn.execute(
            _PO_SELECT + " ORDER BY po.date DESC, po.id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [_po_dict(row) for row in rows]


def get_purchase_order(po_id):
    conn = connect()

    try:
        row = conn.execute(
            _PO_SELECT + " WHERE po.id = ?", (po_id,)
        ).fetchone()
    finally:
        conn.close()

    return _po_dict(row) if row else None


def get_purchase_order_items(po_id):
    """أصناف أمر الشراء: [{name, desc, qty, price, total}]"""
    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT item_name, COALESCE(description, ''), quantity, price, total,
                   COALESCE(barcode, '')
            FROM purchase_order_items
            WHERE purchase_order_id = ?
            ORDER BY id
            """,
            (po_id,)
        ).fetchall()
    finally:
        conn.close()

    return [
        {"name": n, "desc": d, "qty": q, "price": p, "total": t, "barcode": b}
        for n, d, q, p, t, b in rows
    ]


def get_supplier_open_orders(supplier_id, exclude_voucher_id=None):
    """
    أوامر الشراء الفعّالة للمورد التي ما زال عليها متبقٍ للسداد.
    exclude_voucher_id: عند تعديل سند لا يُحتسب مبلغه ضمن المدفوع.
    """
    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT
                po.id, po.po_number, COALESCE(po.supplier_invoice_no, ''),
                po.date, po.total,
                COALESCE((
                    SELECT SUM(v.amount) FROM payment_vouchers v
                    WHERE v.purchase_order_id = po.id
                      AND COALESCE(v.status, 'active') = 'active'
                      AND (? IS NULL OR v.id != ?)
                ), 0)
            FROM purchase_orders po
            WHERE po.supplier_id = ?
              AND COALESCE(po.status, 'active') = 'active'
            ORDER BY po.date, po.id
            """,
            (exclude_voucher_id, exclude_voucher_id, supplier_id)
        ).fetchall()
    finally:
        conn.close()

    result = []

    for po_id, number, invoice_no, date, total, paid in rows:
        remaining = _money(total) - _money(paid)

        if remaining > _EPS:
            result.append({
                "id": po_id,
                "po_number": number,
                "supplier_invoice_no": invoice_no,
                "date": date or "",
                "total": _money(total),
                "paid": _money(paid),
                "remaining": _money(remaining),
            })

    return result


# ----------------------
# تنظيف الأصناف
# ----------------------
def _clean_items(items):
    """يتحقق من الأصناف ويعيد حساب إجمالي كل صنف (الكمية × السعر)."""
    cleaned = []

    for number, item in enumerate(items or [], start=1):
        name = str(item.get("name", "")).strip()

        if not name:
            raise ValueError(f"اسم الصنف مطلوب (الصنف رقم {number})")

        try:
            qty = float(item.get("qty", 0))
            price = float(item.get("price", 0))
        except (TypeError, ValueError):
            raise ValueError(
                f"الكمية أو السعر غير صالح (الصنف رقم {number})"
            ) from None

        if qty != qty or qty <= 0:
            raise ValueError(
                f"الكمية يجب أن تكون أكبر من صفر (الصنف رقم {number})"
            )

        if price != price or price < 0:
            raise ValueError(
                f"السعر لا يمكن أن يكون سالباً (الصنف رقم {number})"
            )

        cleaned.append({
            "name": name,
            "barcode": str(item.get("barcode", "") or "").strip(),
            "desc": str(item.get("desc", "") or "").strip(),
            "qty": qty,
            "price": _money(price),
            "total": _money(qty * price),
        })

    if not cleaned:
        raise ValueError("أضف صنفاً واحداً على الأقل إلى أمر الشراء")

    return cleaned


def _check_supplier_exists(conn, supplier_id):
    if not supplier_id or not conn.execute(
        "SELECT 1 FROM suppliers WHERE id = ?", (supplier_id,)
    ).fetchone():
        raise ValueError("يرجى اختيار مورد صحيح")


def _check_supplier_invoice_no(conn, supplier_id, number, exclude_po_id=None):
    """رقم فاتورة المورد لا يتكرر لنفس المورد (بين الأوامر غير الملغاة)."""
    if not number:
        return

    row = conn.execute(
        """
        SELECT po_number FROM purchase_orders
        WHERE supplier_id = ? AND supplier_invoice_no = ?
          AND COALESCE(status, 'active') = 'active'
          AND (? IS NULL OR id != ?)
        """,
        (supplier_id, number, exclude_po_id, exclude_po_id)
    ).fetchone()

    if row:
        raise ValueError(
            f"رقم فاتورة المورد ({number}) مستخدم مسبقاً لهذا المورد "
            f"في أمر الشراء {row[0]}"
        )


def _stored_items(conn, po_id):
    rows = conn.execute(
        "SELECT item_name, COALESCE(description, ''), quantity, price "
        "FROM purchase_order_items WHERE purchase_order_id = ? ORDER BY id",
        (po_id,)
    ).fetchall()

    return [
        {"name": n, "desc": d, "qty": q, "price": p} for n, d, q, p in rows
    ]


def _items_signature(items):
    return [
        (i["name"], i.get("desc", ""), round(float(i["qty"]), 6),
         round(float(i["price"]), 2))
        for i in items
    ]


def _remember_products(cursor, items):
    """يحفظ/يحدّث الأصناف ذات الباركود (الاسم والوصف وآخر سعر شراء)."""
    for item in items:
        barcode = item.get("barcode", "")

        if not barcode:
            continue

        cursor.execute(
            """
            INSERT INTO products (barcode, name, description, last_price,
                                  updated_at)
            VALUES (?, ?, ?, ?, date('now'))
            ON CONFLICT(barcode) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                last_price = excluded.last_price,
                updated_at = excluded.updated_at
            """,
            (barcode, item["name"], item.get("desc", ""), item["price"])
        )


def get_product_by_barcode(barcode):
    """
    الصنف المعروف لهذا الباركود (من أوامر الشراء السابقة):
    {barcode, name, desc, price} أو None.
    """
    barcode = str(barcode or "").strip()

    if not barcode:
        return None

    conn = connect()

    try:
        row = conn.execute(
            "SELECT barcode, name, COALESCE(description, ''), last_price "
            "FROM products WHERE barcode = ?",
            (barcode,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {
        "barcode": row[0], "name": row[1], "desc": row[2], "price": row[3],
    }


def _insert_items(cursor, po_id, items):
    cursor.executemany(
        """
        INSERT INTO purchase_order_items
        (purchase_order_id, item_name, description, quantity, price, total,
         barcode)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (po_id, i["name"], i["desc"], i["qty"], i["price"], i["total"],
             i.get("barcode", ""))
            for i in items
        ]
    )

    _remember_products(cursor, items)


def _insert_supplier_voucher(cursor, supplier_id, payee, amount, date, method,
                             reference, notes, purchase_order_id):
    number = _next_number(
        cursor, "payment_vouchers", "voucher_number", "PV"
    )

    cursor.execute(
        """
        INSERT INTO payment_vouchers (
            voucher_number, payee, expense_id, category_id, amount, date,
            payment_method, reference, notes, status,
            supplier_id, purchase_order_id
        )
        VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            number, payee, amount, date, method,
            (reference or "").strip(), (notes or "").strip(),
            supplier_id, purchase_order_id or None
        )
    )

    return cursor.lastrowid


# ----------------------
# إنشاء / تعديل أمر شراء
# ----------------------
def save_purchase_order(supplier_id, date, items, supplier_invoice_no="",
                        tax_percent=0, discount_percent=0, notes="",
                        paid_now=0, payment_method="cash", reference=""):
    """
    ينشئ أمر شراء. إن كان paid_now > 0 يُنشأ معه سند صرف بهذا المبلغ
    في نفس المعاملة. يرجع (po_id, voucher_id أو None).
    """
    date = _clean_date(date)
    items = _clean_items(items)
    invoice_no = str(supplier_invoice_no or "").strip()

    totals = _calculate_invoice_totals(
        items, discount_percent=discount_percent, tax_percent=tax_percent
    )

    try:
        paid_now = _money(paid_now or 0)
    except (TypeError, ValueError):
        raise ValueError("المبلغ المدفوع غير صالح") from None

    if paid_now < 0:
        raise ValueError("المبلغ المدفوع لا يمكن أن يكون سالباً")

    if paid_now > totals["total"] + _EPS:
        raise ValueError(
            f"المبلغ المدفوع ({_fmt(paid_now)}) أكبر من إجمالي أمر الشراء "
            f"({_fmt(totals['total'])})."
        )

    method = _clean_method(payment_method)

    with db_connection() as conn:
        _check_supplier_exists(conn, supplier_id)
        _check_supplier_invoice_no(conn, supplier_id, invoice_no)

        cursor = conn.cursor()
        number = _next_number(cursor, "purchase_orders", "po_number", "PO")

        cursor.execute(
            """
            INSERT INTO purchase_orders (
                po_number, supplier_id, supplier_invoice_no, date,
                subtotal, discount_percent, discount_amount,
                tax_percent, tax_amount, total, notes, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                number, supplier_id, invoice_no, date,
                totals["subtotal"], totals["discount_percent"],
                totals["discount_amount"], totals["tax_percent"],
                totals["tax_amount"], totals["total"], (notes or "").strip()
            )
        )

        po_id = cursor.lastrowid
        _insert_items(cursor, po_id, items)

        voucher_id = None

        if paid_now > _EPS:
            payee = conn.execute(
                "SELECT name FROM suppliers WHERE id = ?", (supplier_id,)
            ).fetchone()[0]

            voucher_id = _insert_supplier_voucher(
                cursor, supplier_id, payee, paid_now, date, method,
                reference, f"دفعة عند إنشاء أمر الشراء {number}", po_id
            )

    return po_id, voucher_id


def update_purchase_order(po_id, supplier_id, date, items,
                          supplier_invoice_no="", tax_percent=0,
                          discount_percent=0, notes=""):
    """
    تعديل أمر شراء فعّال. لا يجوز أن يقلّ الإجمالي الجديد عن المدفوع
    فعلاً، ولا تغيير المورد إذا كانت عليه سندات صرف.
    """
    date = _clean_date(date)
    items = _clean_items(items)
    invoice_no = str(supplier_invoice_no or "").strip()

    totals = _calculate_invoice_totals(
        items, discount_percent=discount_percent, tax_percent=tax_percent
    )

    with db_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(status, 'active'), supplier_id, po_number "
            "FROM purchase_orders WHERE id = ?",
            (po_id,)
        ).fetchone()

        if not row:
            raise ValueError("أمر الشراء غير موجود")

        status, old_supplier_id, number = row

        if status == VOUCHER_CANCELLED:
            raise ValueError(
                "لا يمكن تعديل أمر شراء ملغى. أعد تفعيله أولاً."
            )

        _check_supplier_exists(conn, supplier_id)
        _check_supplier_invoice_no(
            conn, supplier_id, invoice_no, exclude_po_id=po_id
        )

        voucher_count, paid = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(CASE
                WHEN COALESCE(status, 'active') = 'active' THEN amount
                ELSE 0 END), 0)
            FROM payment_vouchers WHERE purchase_order_id = ?
            """,
            (po_id,)
        ).fetchone()

        if supplier_id != old_supplier_id and voucher_count:
            raise ValueError(
                f"لا يمكن تغيير مورد أمر الشراء {number} لأن عليه سندات صرف."
            )

        paid = _money(paid)

        receipts_count = conn.execute(
            "SELECT COUNT(*) FROM goods_receipts WHERE purchase_order_id = ?",
            (po_id,)
        ).fetchone()[0]

        if receipts_count and _items_signature(items) != _items_signature(
            _stored_items(conn, po_id)
        ):
            raise ValueError(
                f"لا يمكن تعديل أصناف أمر الشراء {number} لأن له مستندات "
                f"استلام (عددها: {receipts_count}).\n"
                "يمكنك تعديل التاريخ والملاحظات والخصم والضريبة، أو احذف "
                "مستندات الاستلام أولاً."
            )

        if totals["total"] < paid - _EPS:
            raise ValueError(
                f"الإجمالي الجديد ({_fmt(totals['total'])}) أقل من المدفوع "
                f"فعلاً ({_fmt(paid)}).\n"
                "عدّل سندات الصرف أو ألغِها أولاً."
            )

        conn.execute(
            """
            UPDATE purchase_orders
            SET supplier_id=?, supplier_invoice_no=?, date=?,
                subtotal=?, discount_percent=?, discount_amount=?,
                tax_percent=?, tax_amount=?, total=?, notes=?
            WHERE id=?
            """,
            (
                supplier_id, invoice_no, date,
                totals["subtotal"], totals["discount_percent"],
                totals["discount_amount"], totals["tax_percent"],
                totals["tax_amount"], totals["total"], (notes or "").strip(),
                po_id
            )
        )

        if not receipts_count:
            # الأصناف تُستبدل فقط عند عدم وجود استلامات (حفظاً لمعرّفات الأصناف)
            conn.execute(
                "DELETE FROM purchase_order_items WHERE purchase_order_id = ?",
                (po_id,)
            )
            _insert_items(conn.cursor(), po_id, items)

    return po_id


def set_purchase_orders_status(po_ids, status):
    """
    إلغاء أوامر الشراء أو إعادة تفعيلها. الأمر الملغى يبقى للأثر ولا يدخل
    في الحسابات، وما دُفع عليه يتحوّل إلى دفعة مقدّمة عند المورد.
    """
    if status not in PO_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(po_ids)
    changed = 0

    with db_connection() as conn:
        for po_id in ids:
            row = conn.execute(
                "SELECT COALESCE(status, 'active'), supplier_id, "
                "supplier_invoice_no, po_number "
                "FROM purchase_orders WHERE id = ?",
                (po_id,)
            ).fetchone()

            if not row or row[0] == status:
                continue

            _old, supplier_id, invoice_no, number = row

            if status == VOUCHER_CANCELLED:
                active_receipts = conn.execute(
                    "SELECT COUNT(*) FROM goods_receipts "
                    "WHERE purchase_order_id = ? "
                    "AND COALESCE(status, 'active') = 'active'",
                    (po_id,)
                ).fetchone()[0]

                if active_receipts:
                    raise ValueError(
                        f"لا يمكن إلغاء أمر الشراء {number} لأن بضاعته "
                        f"مستلمة (مستندات استلام فعّالة: {active_receipts}).\n"
                        "ألغِ مستندات الاستلام أولاً."
                    )

            if status == VOUCHER_ACTIVE:
                try:
                    _check_supplier_invoice_no(
                        conn, supplier_id, invoice_no, exclude_po_id=po_id
                    )
                except ValueError as e:
                    raise ValueError(
                        f"تعذّرت إعادة تفعيل {number}:\n{e}"
                    ) from None

            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE id = ?",
                (status, po_id)
            )
            changed += 1

    return changed


def delete_purchase_orders(po_ids):
    """لا يُحذف أمر شراء له سندات صرف (يُلغى بدلاً من حذفه)."""
    ids = _as_id_list(po_ids)
    deleted = 0

    with db_connection() as conn:
        for po_id in ids:
            row = conn.execute(
                "SELECT po_number FROM purchase_orders WHERE id = ?",
                (po_id,)
            ).fetchone()

            if not row:
                continue

            vouchers = conn.execute(
                "SELECT COUNT(*) FROM payment_vouchers "
                "WHERE purchase_order_id = ?",
                (po_id,)
            ).fetchone()[0]

            if vouchers:
                raise ValueError(
                    f"لا يمكن حذف أمر الشراء {row[0]} لأن عليه سندات صرف "
                    f"(عددها: {vouchers}).\n"
                    "احذف سنداته أولاً، أو ألغِ الأمر بدلاً من حذفه."
                )

            receipts = conn.execute(
                "SELECT COUNT(*) FROM goods_receipts "
                "WHERE purchase_order_id = ?",
                (po_id,)
            ).fetchone()[0]

            if receipts:
                raise ValueError(
                    f"لا يمكن حذف أمر الشراء {row[0]} لأن له مستندات استلام "
                    f"(عددها: {receipts}).\n"
                    "احذف مستندات الاستلام أولاً."
                )

            conn.execute(
                "DELETE FROM purchase_order_items WHERE purchase_order_id = ?",
                (po_id,)
            )
            conn.execute("DELETE FROM purchase_orders WHERE id = ?", (po_id,))
            deleted += 1

    return deleted


# ======================================================================
# دفعات الموردين (سندات صرف)
# ======================================================================
def add_supplier_payment(supplier_id, amount, date=None,
                         payment_method="cash", reference="", notes="",
                         purchase_order_id=None):
    """
    سند صرف لمورد. مع purchase_order_id يُسدَّد من أمر شراء محدد
    (لا يتجاوز متبقيه)، وبدونه يُسجَّل دفعة على حساب المورد.
    يرجع رقم السند (id).
    """
    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)

    with db_connection() as conn:
        _check_supplier_exists(conn, supplier_id)

        if purchase_order_id:
            owner = conn.execute(
                "SELECT supplier_id FROM purchase_orders WHERE id = ?",
                (purchase_order_id,)
            ).fetchone()

            if not owner or owner[0] != supplier_id:
                raise ValueError("أمر الشراء لا يخص هذا المورد")

            _validate_po_payment(conn, purchase_order_id, amount)

        payee = conn.execute(
            "SELECT name FROM suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()[0]

        return _insert_supplier_voucher(
            conn.cursor(), supplier_id, payee, amount, date, method,
            reference, notes, purchase_order_id
        )


# ======================================================================
# استلام البضاعة
# ======================================================================
GR_ACTIVE = VOUCHER_ACTIVE
GR_CANCELLED = VOUCHER_CANCELLED


def _po_receivable(conn, po_id, exclude_receipt_id=None):
    """
    أصناف أمر الشراء مع المستلم سابقاً والمتبقي للاستلام
    (المستندات الملغاة لا تُحتسب، ويمكن استثناء مستند معيّن).
    """
    rows = conn.execute(
        """
        SELECT
            i.id, i.item_name, COALESCE(i.description, ''), i.quantity,
            COALESCE((
                SELECT SUM(gi.quantity)
                FROM goods_receipt_items gi
                JOIN goods_receipts g ON g.id = gi.goods_receipt_id
                WHERE gi.po_item_id = i.id
                  AND COALESCE(g.status, 'active') = 'active'
                  AND (? IS NULL OR g.id != ?)
            ), 0),
            COALESCE(i.barcode, '')
        FROM purchase_order_items i
        WHERE i.purchase_order_id = ?
        ORDER BY i.id
        """,
        (exclude_receipt_id, exclude_receipt_id, po_id)
    ).fetchall()

    return [
        {
            "po_item_id": item_id,
            "name": name,
            "desc": desc,
            "barcode": barcode,
            "ordered": float(ordered),
            "received": float(received),
            "remaining": max(float(ordered) - float(received), 0.0),
        }
        for item_id, name, desc, ordered, received, barcode in rows
    ]


def get_po_receivable_items(po_id):
    """أصناف أمر شراء مع الكمية المستلمة والمتبقية للاستلام."""
    conn = connect()

    try:
        return _po_receivable(conn, po_id)
    finally:
        conn.close()


def get_receivable_orders(supplier_id=None):
    """
    أوامر الشراء الفعّالة التي ما زال فيها كميات لم تُستلم
    (للمورد المحدد، أو لكل الموردين).
    """
    return [
        order for order in get_purchase_orders()
        if order["status"] == VOUCHER_ACTIVE
        and order["receive_status"] != RECEIVE_FULL
        and (supplier_id is None or order["supplier_id"] == supplier_id)
    ]


def add_goods_receipt(purchase_order_id, date, lines, notes=""):
    """
    ينشئ مستند استلام بضاعة (GR-2026-0001) مقابل أمر شراء فعّال.

    lines: [{"po_item_id": id, "qty": الكمية المستلمة الآن}]؛ الأسطر ذات
           الكمية صفر تُهمل. لا تتجاوز الكمية المتبقي للاستلام من الصنف.
    يرجع رقم المستند (id).
    """
    date = _clean_date(date)

    cleaned = []

    for line in lines or []:
        try:
            qty = float(line.get("qty") or 0)
        except (TypeError, ValueError):
            raise ValueError("كمية الاستلام غير صالحة") from None

        if qty != qty or qty < 0:
            raise ValueError("كمية الاستلام لا يمكن أن تكون سالبة")

        if qty > _EPS:
            cleaned.append((int(line["po_item_id"]), qty))

    if not cleaned:
        raise ValueError("أدخل كمية مستلمة لصنف واحد على الأقل")

    with db_connection() as conn:
        order = conn.execute(
            "SELECT supplier_id, COALESCE(status, 'active'), po_number "
            "FROM purchase_orders WHERE id = ?",
            (purchase_order_id,)
        ).fetchone()

        if not order:
            raise ValueError("أمر الشراء غير موجود")

        supplier_id, status, po_number = order

        if status == VOUCHER_CANCELLED:
            raise ValueError(
                f"أمر الشراء {po_number} ملغى ولا يمكن استلام بضاعته"
            )

        receivable = {
            r["po_item_id"]: r for r in _po_receivable(conn, purchase_order_id)
        }
        requested = {}

        for item_id, qty in cleaned:
            if item_id not in receivable:
                raise ValueError("صنف لا يتبع أمر الشراء المحدد")

            requested[item_id] = requested.get(item_id, 0.0) + qty

        for item_id, qty in requested.items():
            item = receivable[item_id]

            if qty > item["remaining"] + _EPS:
                raise ValueError(
                    f"كمية استلام «{item['name']}» ({qty:g}) أكبر من المتبقي "
                    f"للاستلام ({item['remaining']:g}) "
                    f"من أصل {item['ordered']:g}."
                )

        cursor = conn.cursor()
        number = _next_number(
            cursor, "goods_receipts", "receipt_number", "GR"
        )

        cursor.execute(
            """
            INSERT INTO goods_receipts
            (receipt_number, purchase_order_id, supplier_id, date, notes,
             status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (number, purchase_order_id, supplier_id, date,
             (notes or "").strip())
        )

        receipt_id = cursor.lastrowid

        cursor.executemany(
            "INSERT INTO goods_receipt_items "
            "(goods_receipt_id, po_item_id, quantity) VALUES (?, ?, ?)",
            [(receipt_id, item_id, qty) for item_id, qty in requested.items()]
        )

    return receipt_id


_GR_SELECT = """
    SELECT
        g.id, g.receipt_number, g.purchase_order_id, po.po_number,
        COALESCE(po.supplier_invoice_no, ''), g.supplier_id, s.name,
        g.date, COALESCE(g.notes, ''), COALESCE(g.status, 'active'),
        COALESCE((SELECT SUM(gi.quantity) FROM goods_receipt_items gi
                  WHERE gi.goods_receipt_id = g.id), 0),
        (SELECT COUNT(*) FROM goods_receipt_items gi
         WHERE gi.goods_receipt_id = g.id)
    FROM goods_receipts g
    LEFT JOIN purchase_orders po ON po.id = g.purchase_order_id
    LEFT JOIN suppliers s ON s.id = g.supplier_id
"""

_GR_KEYS = (
    "id", "receipt_number", "purchase_order_id", "po_number",
    "supplier_invoice_no", "supplier_id", "supplier", "date", "notes",
    "status", "total_qty", "lines_count",
)


def _gr_dict(row):
    data = dict(zip(_GR_KEYS, row))
    data["supplier"] = data["supplier"] or "-"
    data["date"] = data["date"] or ""
    return data


def get_goods_receipts():
    conn = connect()

    try:
        rows = conn.execute(
            _GR_SELECT + " ORDER BY g.date DESC, g.id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [_gr_dict(row) for row in rows]


def get_goods_receipt(receipt_id):
    conn = connect()

    try:
        row = conn.execute(
            _GR_SELECT + " WHERE g.id = ?", (receipt_id,)
        ).fetchone()
    finally:
        conn.close()

    return _gr_dict(row) if row else None


def get_goods_receipt_items(receipt_id):
    """
    أسطر مستند الاستلام: الصنف، المطلوب، المستلم سابقاً (قبل هذا المستند)،
    المستلم الآن، والمتبقي بعده.
    """
    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT i.id, i.item_name, COALESCE(i.description, ''),
                   i.quantity, gi.quantity, g.purchase_order_id
            FROM goods_receipt_items gi
            JOIN goods_receipts g ON g.id = gi.goods_receipt_id
            JOIN purchase_order_items i ON i.id = gi.po_item_id
            WHERE gi.goods_receipt_id = ?
            ORDER BY gi.id
            """,
            (receipt_id,)
        ).fetchall()

        result = []

        for item_id, name, desc, ordered, qty, _po in rows:
            before = conn.execute(
                """
                SELECT COALESCE(SUM(gi.quantity), 0)
                FROM goods_receipt_items gi
                JOIN goods_receipts g ON g.id = gi.goods_receipt_id
                WHERE gi.po_item_id = ?
                  AND COALESCE(g.status, 'active') = 'active'
                  AND g.id < ?
                """,
                (item_id, receipt_id)
            ).fetchone()[0]

            result.append({
                "name": name,
                "desc": desc,
                "ordered": float(ordered),
                "before": float(before),
                "qty": float(qty),
                "remaining": max(float(ordered) - float(before) - float(qty),
                                 0.0),
            })
    finally:
        conn.close()

    return result


def set_goods_receipts_status(receipt_ids, status):
    """
    إلغاء مستندات الاستلام أو إعادة تفعيلها. الإلغاء يُرجع الكميات إلى
    «المتبقي للاستلام». إعادة التفعيل تتحقق من أن أمر الشراء فعّال وأن
    الكميات لا تتجاوز المطلوب.
    """
    if status not in PO_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(receipt_ids)
    changed = 0

    with db_connection() as conn:
        for receipt_id in ids:
            row = conn.execute(
                "SELECT COALESCE(g.status, 'active'), g.purchase_order_id, "
                "g.receipt_number, COALESCE(po.status, 'active'), po.po_number "
                "FROM goods_receipts g "
                "LEFT JOIN purchase_orders po ON po.id = g.purchase_order_id "
                "WHERE g.id = ?",
                (receipt_id,)
            ).fetchone()

            if not row or row[0] == status:
                continue

            _old, po_id, number, po_status, po_number = row

            if status == VOUCHER_ACTIVE:
                if po_status == VOUCHER_CANCELLED:
                    raise ValueError(
                        f"تعذّرت إعادة تفعيل {number}: أمر الشراء "
                        f"{po_number} ملغى."
                    )

                receivable = {
                    r["po_item_id"]: r for r in _po_receivable(
                        conn, po_id, exclude_receipt_id=receipt_id
                    )
                }

                for item_id, qty in conn.execute(
                    "SELECT po_item_id, quantity FROM goods_receipt_items "
                    "WHERE goods_receipt_id = ?",
                    (receipt_id,)
                ).fetchall():
                    item = receivable.get(item_id)

                    if item is None or qty > item["remaining"] + _EPS:
                        raise ValueError(
                            f"تعذّرت إعادة تفعيل {number}: الكميات تتجاوز "
                            f"المتبقي للاستلام على أمر الشراء {po_number}."
                        )

            conn.execute(
                "UPDATE goods_receipts SET status = ? WHERE id = ?",
                (status, receipt_id)
            )
            changed += 1

    return changed


def delete_goods_receipts(receipt_ids):
    """يحذف مستندات استلام (لا أثر مالي لها)."""
    ids = _as_id_list(receipt_ids)
    deleted = 0

    with db_connection() as conn:
        for receipt_id in ids:
            exists = conn.execute(
                "SELECT 1 FROM goods_receipts WHERE id = ?", (receipt_id,)
            ).fetchone()

            if not exists:
                continue

            conn.execute(
                "DELETE FROM goods_receipt_items WHERE goods_receipt_id = ?",
                (receipt_id,)
            )
            conn.execute(
                "DELETE FROM goods_receipts WHERE id = ?", (receipt_id,)
            )
            deleted += 1

    return deleted


# ======================================================================
# حساب المورد (كشف الحساب)
# ======================================================================
_STATEMENT_KIND_ORDER = {"purchase": 0, "payment": 1}


def get_supplier_statement(supplier_id, start=None, end=None,
                           include_cancelled=True):
    """
    كشف حساب المورد بالتسلسل الزمني (نفس بنية كشف العميل ليُطبع بنفس الـ PDF).

    الأعمدة:  debit = مشتريات (أمر شراء فعّال: يزيد المستحق للمورد)
              credit = مدفوعات (سند صرف فعّال: ينقص المستحق)
    الرصيد:   موجب = مستحق للمورد علينا · سالب = دفعة مقدّمة لنا
    الأنواع:  purchase (أمر شراء) · payment (سند صرف)
    الأوامر والسندات الملغاة تظهر بقيمة صفر وعلامة cancelled.

    الرصيد الختامي لكشف «كل الفترات» يساوي get_supplier()["balance"].
    """
    supplier = get_supplier(supplier_id)

    if not supplier:
        raise ValueError("المورد غير موجود")

    conn = connect()

    try:
        orders = conn.execute(
            """
            SELECT id, po_number, COALESCE(date, ''), total,
                   COALESCE(status, 'active'),
                   COALESCE(supplier_invoice_no, '')
            FROM purchase_orders WHERE supplier_id = ?
            """,
            (supplier_id,)
        ).fetchall()

        vouchers = conn.execute(
            """
            SELECT v.id, v.voucher_number, COALESCE(v.date, ''), v.amount,
                   COALESCE(v.status, 'active'), po.po_number,
                   COALESCE(po.status, 'active')
            FROM payment_vouchers v
            LEFT JOIN purchase_orders po ON po.id = v.purchase_order_id
            WHERE v.supplier_id = ?
            """,
            (supplier_id,)
        ).fetchall()
    finally:
        conn.close()

    entries = []

    for po_id, number, date, total, status, invoice_no in orders:
        cancelled = status == VOUCHER_CANCELLED

        if cancelled and not include_cancelled:
            continue

        text = "أمر شراء ملغى" if cancelled else "أمر شراء"

        if invoice_no:
            text += f" — فاتورة المورد {invoice_no}"

        entries.append({
            "date": date, "kind": "purchase", "ref": number,
            "description": text,
            "debit": 0.0 if cancelled else _money(total),
            "credit": 0.0, "purchase_order_id": po_id, "voucher_id": None,
            "cancelled": cancelled, "_id": po_id,
        })

    for v_id, number, date, amount, status, po_number, po_status in vouchers:
        cancelled = status == VOUCHER_CANCELLED

        if cancelled and not include_cancelled:
            continue

        if po_number:
            text = f"سند صرف عن أمر الشراء {po_number}"

            if po_status == VOUCHER_CANCELLED and not cancelled:
                text += " (الأمر ملغى — دفعة مقدّمة)"
        else:
            text = "سند صرف — دفعة على الحساب"

        if cancelled:
            text = text.replace("سند صرف", "سند صرف ملغى", 1)

        entries.append({
            "date": date, "kind": "payment", "ref": number,
            "description": text, "debit": 0.0,
            "credit": 0.0 if cancelled else _money(amount),
            "purchase_order_id": None, "voucher_id": v_id,
            "cancelled": cancelled, "_id": v_id,
        })

    entries.sort(
        key=lambda e: (e["date"], _STATEMENT_KIND_ORDER[e["kind"]], e["_id"])
    )

    opening = 0.0
    rows = []

    for entry in entries:
        date = entry["date"]

        if start and date < start:
            opening += entry["debit"] - entry["credit"]
            continue

        if end and date > end:
            continue

        rows.append(entry)

    opening = _money(opening)
    running = opening
    total_debit = total_credit = 0.0

    for entry in rows:
        running = _money(running + entry["debit"] - entry["credit"])
        entry["balance"] = running
        entry.pop("_id", None)
        total_debit += entry["debit"]
        total_credit += entry["credit"]

    return {
        "party": "supplier",
        "client": supplier,         # مفتاح «client» ليعمل مع statement_pdf
        "supplier": supplier,
        "start": start,
        "end": end,
        "opening": opening,
        "rows": rows,
        "total_debit": _money(total_debit),
        "total_credit": _money(total_credit),
        "closing": running,
        "state": balance_state(running),
    }
