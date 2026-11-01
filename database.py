# database.py

import sqlite3
import json
import hashlib
from contextlib import contextmanager
from datetime import datetime

DB_NAME = "invoices.db"

# ======================
# حالات الفواتير
# ======================
STATUS_PAID = "paid"
STATUS_UNPAID = "unpaid"
STATUS_CANCELLED = "cancelled"

INVOICE_STATUSES = {
    STATUS_PAID: "مدفوعة",
    STATUS_UNPAID: "غير مدفوعة",
    STATUS_CANCELLED: "ملغاة",
}


def status_label(status):
    """الاسم العربي للحالة (أي قيمة غير معروفة تعتبر غير مدفوعة)."""
    return INVOICE_STATUSES.get(status, INVOICE_STATUSES[STATUS_UNPAID])


# ======================
# الاتصال بقاعدة البيانات
# ======================
def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# اتصال آمن: commit عند النجاح، rollback عند الخطأ، وإغلاق الاتصال دائماً
@contextmanager
def db_connection():
    conn = connect()

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

# ======================
# التشفير
# ======================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# تقريب قيم مالية محفوظة في قاعدة البيانات.
# ======================
def _money(value):
    return round(float(value or 0), 2)

# حساب إجمالي الفاتورة بعد الخصم والضريبة
# ======================
def _calculate_invoice_totals(items, discount_percent=0, tax_percent=0):

    subtotal = _money(
        sum(float(item.get("total", 0)) for item in items)
    )

    discount_percent = _money(discount_percent)
    tax_percent = _money(tax_percent)

    discount_amount = _money(
        subtotal * discount_percent / 100
    )

    taxable_amount = _money(
        subtotal - discount_amount
    )

    tax_amount = _money(
        taxable_amount * tax_percent / 100
    )

    total = _money(
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

# ======================
# إنشاء الجداول
# ======================
def create_tables():
    conn = connect()
    cursor = conn.cursor()

    # المستخدمين
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user'
    )
    """)

    # العملاء
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        phone TEXT
    )
    """)

    # الفواتير
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        items TEXT,
        subtotal REAL DEFAULT 0,
        discount_percent REAL DEFAULT 0,
        discount_amount REAL DEFAULT 0,
        tax_percent REAL DEFAULT 0,
        tax_amount REAL DEFAULT 0,
        total REAL DEFAULT 0,
        date TEXT,
        invoice_number TEXT,
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'unpaid',
        archived INTEGER DEFAULT 0,
        paid_by_receipts INTEGER DEFAULT 0,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )
    """)

    # أصناف الفاتورة
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        item_name TEXT,
        quantity REAL,
        price REAL,
        total REAL,
        description TEXT,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    """)
    
    _create_finance_tables(cursor)

    conn.commit()
    conn.close()


# ======================
# المستخدمين
# ======================
def create_user(username, password, role="user"):
    conn = connect()
    cursor = conn.cursor()

    hashed = hash_password(password)

    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
        conn.commit()
    except Exception as e:
        print("خطأ في إنشاء المستخدم:", e)

    conn.close()


def login(username, password):
    conn = connect()
    cursor = conn.cursor()

    hashed = hash_password(password)

    cursor.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, hashed)
    )
    user = cursor.fetchone()

    # دعم كلمات المرور القديمة
    if not user:
        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = cursor.fetchone()

        if user:
            cursor.execute(
                "UPDATE users SET password=? WHERE username=?",
                (hashed, username)
            )
            conn.commit()

    conn.close()
    return user


# ======================
# العملاء
# ======================

# ➕ إضافة عميل
# ======================
def add_client(name, phone, address=""):
    try:
        with db_connection() as conn:
            conn.execute(
                "INSERT INTO clients (name, phone) VALUES (?, ?)",
                (name, phone)
            )

    except sqlite3.IntegrityError:
        raise ValueError("اسم العميل موجود مسبقاً") from None


# 📋 جلب العملاء
# ======================
def get_clients():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, phone
        FROM clients
        ORDER BY id DESC
        """
    )

    data = cursor.fetchall()

    conn.close()
    return data


def get_invoice_info(invoice_id):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            invoices.id,
            invoices.invoice_number,
            clients.name,
            invoices.date,
            invoices.subtotal,
            invoices.discount_percent,
            invoices.discount_amount,
            invoices.tax_percent,
            invoices.tax_amount,
            invoices.total,
            invoices.notes,
            invoices.status,
            invoices.archived

        FROM invoices

        LEFT JOIN clients
        ON invoices.client_id = clients.id

        WHERE invoices.id = ?
    """, (invoice_id,))

    data = cursor.fetchone()
    conn.close()

    if not data:
        return None

    keys = (
        "id",
        "invoice_number",
        "client",
        "date",
        "subtotal",
        "discount_percent",
        "discount_amount",
        "tax_percent",
        "tax_amount",
        "total",
        "notes",
        "status",
        "archived",
    )

    return dict(zip(keys, data))

# 🔍 البحث عن العملاء
# ======================
def search_clients(keyword):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, phone
        FROM clients
        WHERE name LIKE ?
        OR phone LIKE ?
        ORDER BY id DESC
        """,
        (f"%{keyword}%", f"%{keyword}%")
    )

    data = cursor.fetchall()

    conn.close()
    return data


# ✏️ تعديل عميل
# ======================
def update_client(client_id, name, phone):
    try:
        with db_connection() as conn:
            conn.execute(
                """
                UPDATE clients
                SET name=?, phone=?
                WHERE id=?
                """,
                (name, phone, client_id)
            )

    except sqlite3.IntegrityError:
        raise ValueError("اسم العميل موجود مسبقاً") from None


# ❌ حذف عميل
# ======================
def delete_client(client_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM invoices WHERE client_id=?",
            (client_id,)
        )

        count = cursor.fetchone()[0]

        if count:
            raise ValueError(
                f"لا يمكن حذف عميل لديه فواتير (عدد الفواتير: {count}).\n"
                "احذف فواتيره أولاً."
            )

        cursor.execute(
            "SELECT COUNT(*) FROM receipts WHERE client_id=?",
            (client_id,)
        )

        receipts_count = cursor.fetchone()[0]

        if receipts_count:
            raise ValueError(
                f"لا يمكن حذف عميل لديه سندات قبض (عددها: {receipts_count}).\n"
                "احذف سنداته أولاً."
            )

        cursor.execute(
            "DELETE FROM clients WHERE id=?",
            (client_id,)
        )


# ======================
# الفواتير
# ======================

# ➕ إضافة فاتورة
def save_invoice(client_id, date, items, tax_percent=0, discount_percent=0, notes=""):
    totals = _calculate_invoice_totals(
        items,
        discount_percent=discount_percent,
        tax_percent=tax_percent
    )

    invoice_number = generate_invoice_number()

    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO invoices (
                client_id,
                subtotal,
                discount_percent,
                discount_amount,
                tax_percent,
                tax_amount,
                total,
                date,
                invoice_number,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                totals["subtotal"],
                totals["discount_percent"],
                totals["discount_amount"],
                totals["tax_percent"],
                totals["tax_amount"],
                totals["total"],
                date,
                invoice_number,
                notes or ""
            )
        )

        invoice_id = cursor.lastrowid

        for item in items:
            cursor.execute("""
                INSERT INTO invoice_items
                (invoice_id, item_name, description, quantity, price, total)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                item["name"],
                item.get("desc", ""),
                item["qty"],
                item["price"],
                item["total"]
            ))

    return invoice_id

# ======================
# 📋 جلب الفواتير
# ======================
def get_invoices():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            invoices.id,
            invoices.invoice_number,
            clients.name,
            invoices.date,
            invoices.subtotal,
            invoices.discount_percent,
            invoices.discount_amount,
            invoices.tax_percent,
            invoices.tax_amount,
            invoices.total,
            invoices.notes,
            invoices.status,
            invoices.archived

        FROM invoices

        JOIN clients
        ON invoices.client_id = clients.id

        ORDER BY invoices.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    keys = (
        "id",
        "invoice_number",
        "client",
        "date",
        "subtotal",
        "discount_percent",
        "discount_amount",
        "tax_percent",
        "tax_amount",
        "total",
        "notes",
        "status",
        "archived",
    )

    invoices = [dict(zip(keys, row)) for row in rows]

    collected_map = get_collected_by_invoice()

    for invoice in invoices:
        invoice["status"] = invoice["status"] or STATUS_UNPAID
        invoice["archived"] = int(invoice["archived"] or 0)

        collected, remaining = _collected_and_remaining(
            invoice["total"], invoice["status"],
            collected_map.get(invoice["id"], 0)
        )
        invoice["collected"] = collected
        invoice["remaining"] = remaining

    return invoices

# جلب الفاتورة حسب الرقم 
# ======================
def get_invoice_by_id(invoice_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM invoices
        WHERE id = ?
    """, (invoice_id,))

    invoice = cursor.fetchone()

    conn.close()

    return invoice

# جلب عناصر الفاتورة 
# ======================
def get_invoice_items(invoice_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            item_name,
            description,
            quantity,
            price,
            total
        FROM invoice_items
        WHERE invoice_id = ?
    """, (invoice_id,))

    items = cursor.fetchall()
    conn.close()

    return items

# ❌ حذف فاتورة
# ======================
def delete_invoice(invoice_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM receipts WHERE invoice_id=?",
            (invoice_id,)
        )

        linked = cursor.fetchone()[0]

        if linked:
            raise ValueError(
                f"لا يمكن حذف فاتورة مرتبطة بسندات قبض (عددها: {linked}).\n"
                "احذف السندات المرتبطة بها أولاً، أو ألغِ الفاتورة بدلاً من حذفها."
            )

        cursor.execute(
            "DELETE FROM invoice_items WHERE invoice_id=?",
            (invoice_id,)
        )

        cursor.execute(
            "DELETE FROM invoices WHERE id=?",
            (invoice_id,)
        )

# ✏️ تعديل فاتورة
# ======================
def update_invoice(invoice_id, client_id, items, tax_percent=0, discount_percent=0, notes=""):
    totals = _calculate_invoice_totals(
        items,
        discount_percent=discount_percent,
        tax_percent=tax_percent
    )

    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE invoices
            SET
                client_id=?,
                subtotal=?,
                discount_percent=?,
                discount_amount=?,
                tax_percent=?,
                tax_amount=?,
                total=?,
                notes=?
            WHERE id=?
            """,
            (
                client_id,
                totals["subtotal"],
                totals["discount_percent"],
                totals["discount_amount"],
                totals["tax_percent"],
                totals["tax_amount"],
                totals["total"],
                notes or "",
                invoice_id
            )
        )

        cursor.execute(
            "DELETE FROM invoice_items WHERE invoice_id=?",
            (invoice_id,)
        )

        for item in items:
            cursor.execute(
                """
                INSERT INTO invoice_items
                (invoice_id, item_name, description, quantity, price, total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    item["name"],
                    item.get("desc", ""),
                    item["qty"],
                    item["price"],
                    item["total"]
                )
            )

        # المجموع قد تغيّر → أعد مطابقة حالة الدفع مع سندات القبض
        _sync_invoice_payment(conn, invoice_id)


# ======================
# 🏷️ حالة الفاتورة (مدفوعة / غير مدفوعة / ملغاة)
# ======================
def _as_id_list(invoice_ids):
    if isinstance(invoice_ids, (list, tuple, set)):
        return [int(i) for i in invoice_ids]
    return [int(invoice_ids)]


def set_invoice_status(invoice_ids, status):
    """تغيير حالة فاتورة واحدة أو عدة فواتير. يرجع عدد الفواتير المعدّلة."""

    if status not in INVOICE_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(invoice_ids)

    if not ids:
        return 0

    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.executemany(
            "UPDATE invoices SET status=?, paid_by_receipts=0 WHERE id=?",
            [(status, invoice_id) for invoice_id in ids]
        )

        return cursor.rowcount


# ======================
# 🗄️ أرشفة الفواتير
# ======================
def set_invoice_archived(invoice_ids, archived=True):
    """أرشفة فاتورة/عدة فواتير أو إلغاء أرشفتها (بدون حذف أي بيانات)."""

    ids = _as_id_list(invoice_ids)

    if not ids:
        return 0

    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.executemany(
            "UPDATE invoices SET archived=? WHERE id=?",
            [(1 if archived else 0, invoice_id) for invoice_id in ids]
        )

        return cursor.rowcount


# ======================
# إنشاء رقم فاتورة احترافي
# ======================
def generate_invoice_number():

    conn = connect()

    cursor = conn.cursor()

    year = datetime.now().year

    # أرقام هذه السنة فقط (كل سنة تبدأ من 0001)
    cursor.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?",
        (f"INV-{year}-%",)
    )

    # أكبر رقم تسلسلي مستخدم (الجزء الأخير من INV-2026-0014)
    last = 0

    for (number,) in cursor.fetchall():
        try:
            last = max(last, int(str(number).split("-")[-1]))
        except ValueError:
            continue

    count = last + 1

    invoice_number = f"INV-{year}-{count:04d}"

    conn.close()

    return invoice_number

def get_total_profit():
    conn = connect()
    cursor = conn.cursor()

    # الفواتير الملغاة لا تدخل في الإجمالي
    cursor.execute(
        "SELECT SUM(total) FROM invoices "
        "WHERE COALESCE(status, 'unpaid') != 'cancelled'"
    )
    result = cursor.fetchone()[0]

    conn.close()
    return result if result else 0


def get_profit_by_date(start, end):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT SUM(total) FROM invoices
    WHERE date BETWEEN ? AND ?
    AND COALESCE(status, 'unpaid') != 'cancelled'
    """, (start, end))

    result = cursor.fetchone()[0]

    conn.close()
    return result if result else 0

# ======================
# ترقية قاعدة البيانات
# ======================
def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")

    if not any(row[1] == column for row in cursor.fetchall()):
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def _clients_name_is_unique(cursor):
    cursor.execute("PRAGMA index_list(clients)")

    for row in cursor.fetchall():
        index_name, is_unique = row[1], row[2]

        if not is_unique:
            continue

        cursor.execute(f"PRAGMA index_info('{index_name}')")

        if [col[2] for col in cursor.fetchall()] == ["name"]:
            return True

    return False


def migrate_database():
    """يجعل أي قاعدة قديمة مطابقة للمخطط الكامل في create_tables."""

    with db_connection() as conn:
        cursor = conn.cursor()

        _add_column_if_missing(cursor, "clients", "phone", "TEXT")
        _add_column_if_missing(cursor, "invoices", "items", "TEXT")
        _add_column_if_missing(cursor, "invoices", "invoice_number", "TEXT")
        _add_column_if_missing(cursor, "invoices", "subtotal", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "invoices", "discount_percent", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "invoices", "discount_amount", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "invoices", "tax_percent", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "invoices", "tax_amount", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "invoices", "notes", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "invoices", "status", "TEXT DEFAULT 'unpaid'")
        _add_column_if_missing(cursor, "invoices", "archived", "INTEGER DEFAULT 0")
        _add_column_if_missing(cursor, "invoice_items", "description", "TEXT")
        _add_column_if_missing(
            cursor, "invoices", "paid_by_receipts", "INTEGER DEFAULT 0"
        )

        # جداول السندات والمصروفات (0.1.6) — آمنة على القواعد القديمة
        _create_finance_tables(cursor)

        # تحديث الفواتير القديمة
        cursor.execute("""
            UPDATE invoices
            SET
                subtotal = COALESCE(subtotal, total),
                discount_percent = COALESCE(discount_percent, 0),
                discount_amount = COALESCE(discount_amount, 0),
                tax_percent = COALESCE(tax_percent, 0),
                tax_amount = COALESCE(tax_amount, 0),
                notes = COALESCE(notes, ''),
                status = COALESCE(status, 'unpaid'),
                archived = COALESCE(archived, 0)
        """)

        # منع تكرار أسماء العملاء في القواعد القديمة
        if not _clients_name_is_unique(cursor):
            try:
                cursor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name "
                    "ON clients(name)"
                )
            except sqlite3.IntegrityError:
                print(
                    "تنبيه: توجد أسماء عملاء مكررة، لم يُفرض منع التكرار. "
                    "عدّل الأسماء المكررة ثم أعد تشغيل البرنامج."
                )


# ======================================================================
# 0.1.6 — سندات القبض / سندات الصرف / المصروفات / المالية
# ======================================================================

# حالة السند (قبض أو صرف)
VOUCHER_ACTIVE = "active"
VOUCHER_CANCELLED = "cancelled"

VOUCHER_STATUSES = {
    VOUCHER_ACTIVE: "فعّال",
    VOUCHER_CANCELLED: "ملغى",
}

# طرق الدفع
PAYMENT_METHODS = {
    "cash": "نقداً",
    "bank": "تحويل بنكي",
    "cheque": "شيك",
    "card": "بطاقة",
    "other": "أخرى",
}

# حالة تسديد المصروف (تُحسب من سندات الصرف المرتبطة)
EXPENSE_UNPAID = "unpaid"
EXPENSE_PARTIAL = "partial"
EXPENSE_PAID = "paid"

EXPENSE_PAY_STATUSES = {
    EXPENSE_UNPAID: "غير مسدد",
    EXPENSE_PARTIAL: "مسدد جزئياً",
    EXPENSE_PAID: "مسدد",
}

DEFAULT_EXPENSE_CATEGORIES = [
    "رواتب وأجور",
    "إيجار",
    "كهرباء ومياه",
    "اتصالات وإنترنت",
    "مواصلات ومحروقات",
    "مشتريات ومواد",
    "صيانة",
    "تسويق وإعلان",
    "ضرائب ورسوم",
    "أخرى",
]

# هامش تقريب عند مقارنة المبالغ
_EPS = 0.005


def voucher_status_label(status):
    return VOUCHER_STATUSES.get(status, VOUCHER_STATUSES[VOUCHER_ACTIVE])


def payment_method_label(code):
    return PAYMENT_METHODS.get(code, PAYMENT_METHODS["other"])


def expense_pay_status_label(status):
    return EXPENSE_PAY_STATUSES.get(status, EXPENSE_PAY_STATUSES[EXPENSE_UNPAID])


# ======================
# تنظيف وفحص المدخلات
# ======================
def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _clean_date(value):
    text = str(value or "").strip() or _today()

    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            "صيغة التاريخ غير صحيحة. استخدم YYYY-MM-DD مثل 2026-10-29"
        ) from None

    return text


def _clean_amount(value, field="المبلغ"):
    try:
        amount = _money(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} غير صالح") from None

    if amount != amount or amount <= 0:
        raise ValueError(f"{field} يجب أن يكون أكبر من صفر")

    return amount


def _clean_method(value):
    method = value or "cash"

    if method not in PAYMENT_METHODS:
        raise ValueError("طريقة الدفع غير صالحة")

    return method


def _fmt(value):
    return f"{_money(value):,.2f}"


# ======================
# الترقيم التلقائي (RC / PV / EX)
# ======================
def _next_number(cursor, table, column, prefix):
    """رقم تسلسلي لكل سنة، يُحسب داخل نفس المعاملة التي تُدرج السند."""

    year = datetime.now().year

    cursor.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE ?",
        (f"{prefix}-{year}-%",)
    )

    last = 0

    for (number,) in cursor.fetchall():
        try:
            last = max(last, int(str(number).split("-")[-1]))
        except ValueError:
            continue

    return f"{prefix}-{year}-{last + 1:04d}"


# ======================
# إنشاء جداول المالية
# ======================
def _create_finance_tables(cursor):

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_number TEXT,
        title TEXT NOT NULL,
        category_id INTEGER,
        supplier TEXT DEFAULT '',
        amount REAL DEFAULT 0,
        date TEXT,
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        FOREIGN KEY(category_id) REFERENCES expense_categories(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_number TEXT,
        client_id INTEGER NOT NULL,
        invoice_id INTEGER,
        amount REAL DEFAULT 0,
        date TEXT,
        payment_method TEXT DEFAULT 'cash',
        reference TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_number TEXT,
        payee TEXT NOT NULL,
        expense_id INTEGER,
        category_id INTEGER,
        amount REAL DEFAULT 0,
        date TEXT,
        payment_method TEXT DEFAULT 'cash',
        reference TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        FOREIGN KEY(expense_id) REFERENCES expenses(id),
        FOREIGN KEY(category_id) REFERENCES expense_categories(id)
    )
    """)

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_receipts_invoice ON receipts(invoice_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_receipts_client ON receipts(client_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_vouchers_expense "
        "ON payment_vouchers(expense_id)"
    )

    # تصنيفات افتراضية عند أول تشغيل فقط
    cursor.execute("SELECT COUNT(*) FROM expense_categories")

    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT OR IGNORE INTO expense_categories (name) VALUES (?)",
            [(name,) for name in DEFAULT_EXPENSE_CATEGORIES]
        )


# ======================
# المحصّل والمتبقي على الفواتير
# ======================
def _invoice_remaining(total, status, paid_by_receipts, collected):
    """
    المتبقي القابل للتحصيل على الفاتورة:
      - الملغاة: صفر
      - المدفوعة يدوياً (بدون سندات): صفر
      - غير ذلك: الإجمالي − المحصّل بسندات فعّالة
    """
    if status == STATUS_CANCELLED:
        return 0.0

    if status == STATUS_PAID and not paid_by_receipts:
        return 0.0

    return max(_money(total) - _money(collected), 0.0)


def _collected_and_remaining(total, status, collected):
    """(المحصّل، المتبقي) للعرض في جدول الفواتير."""

    total = _money(total)
    collected = _money(collected)

    if status == STATUS_CANCELLED:
        return collected, 0.0

    if status == STATUS_PAID:
        # المدفوعة تُعتبر محصّلة بالكامل (حتى لو دُفعت يدوياً)
        return max(collected, total), 0.0

    return collected, max(_money(total - collected), 0.0)


def get_collected_by_invoice():
    """{invoice_id: مجموع سندات القبض الفعّالة}"""

    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT invoice_id, SUM(amount)
            FROM receipts
            WHERE invoice_id IS NOT NULL
              AND COALESCE(status, 'active') = 'active'
            GROUP BY invoice_id
            """
        ).fetchall()
    finally:
        conn.close()

    return {invoice_id: _money(total) for invoice_id, total in rows}


def _active_collected(conn, invoice_id, exclude_receipt_id=None):
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM receipts
        WHERE invoice_id = ?
          AND COALESCE(status, 'active') = 'active'
          AND (? IS NULL OR id != ?)
        """,
        (invoice_id, exclude_receipt_id, exclude_receipt_id)
    ).fetchone()

    return _money(row[0])


def _sync_invoice_payment(conn, invoice_id):
    """
    يطابق حالة الفاتورة مع سندات القبض:
      - غير مدفوعة + المحصّل ≥ الإجمالي  → مدفوعة (مع علامة paid_by_receipts)
      - مدفوعة بالسندات + نقص المحصّل    → غير مدفوعة
    الفواتير التي حُدّدت مدفوعة يدوياً لا تُمَس أبداً.
    """
    if not invoice_id:
        return

    row = conn.execute(
        "SELECT total, COALESCE(status, 'unpaid'), "
        "COALESCE(paid_by_receipts, 0) FROM invoices WHERE id = ?",
        (invoice_id,)
    ).fetchone()

    if not row:
        return

    total, status, flag = row
    collected = _active_collected(conn, invoice_id)
    covered = collected > 0 and collected >= _money(total) - _EPS

    if status == STATUS_UNPAID and covered:
        conn.execute(
            "UPDATE invoices SET status = ?, paid_by_receipts = 1 WHERE id = ?",
            (STATUS_PAID, invoice_id)
        )

    elif status == STATUS_PAID and flag and not covered:
        conn.execute(
            "UPDATE invoices SET status = ?, paid_by_receipts = 0 WHERE id = ?",
            (STATUS_UNPAID, invoice_id)
        )


# ======================================================================
# سندات القبض
# ======================================================================
_RECEIPT_SELECT = """
    SELECT
        r.id, r.receipt_number, r.client_id, c.name,
        r.invoice_id, i.invoice_number,
        r.amount, r.date, r.payment_method, r.reference, r.notes, r.status
    FROM receipts r
    LEFT JOIN clients c ON c.id = r.client_id
    LEFT JOIN invoices i ON i.id = r.invoice_id
"""

_RECEIPT_KEYS = (
    "id", "receipt_number", "client_id", "client",
    "invoice_id", "invoice_number",
    "amount", "date", "payment_method", "reference", "notes", "status",
)


def _receipt_dict(row):
    data = dict(zip(_RECEIPT_KEYS, row))
    data["status"] = data["status"] or VOUCHER_ACTIVE
    data["payment_method"] = data["payment_method"] or "cash"
    data["client"] = data["client"] or "-"
    data["reference"] = data["reference"] or ""
    data["notes"] = data["notes"] or ""
    return data


def get_receipts():
    conn = connect()

    try:
        rows = conn.execute(
            _RECEIPT_SELECT + " ORDER BY r.date DESC, r.id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [_receipt_dict(row) for row in rows]


def get_receipt(receipt_id):
    conn = connect()

    try:
        row = conn.execute(
            _RECEIPT_SELECT + " WHERE r.id = ?", (receipt_id,)
        ).fetchone()
    finally:
        conn.close()

    return _receipt_dict(row) if row else None


def get_receipt_invoice_summary(receipt_id):
    """ملخص الفاتورة المرتبطة بالسند (للطباعة): الإجمالي/المحصّل/المتبقي."""

    receipt = get_receipt(receipt_id)

    if not receipt or not receipt["invoice_id"]:
        return None

    conn = connect()

    try:
        row = conn.execute(
            "SELECT total, COALESCE(status, 'unpaid'), "
            "COALESCE(paid_by_receipts, 0) FROM invoices WHERE id = ?",
            (receipt["invoice_id"],)
        ).fetchone()

        if not row:
            return None

        total, status, flag = row
        collected = _active_collected(conn, receipt["invoice_id"])
    finally:
        conn.close()

    # المتبقي بعد جميع السندات الفعّالة
    remaining = max(_money(total) - collected, 0.0)

    if status == STATUS_PAID and not flag:
        remaining = 0.0

    return {
        "total": _money(total),
        "collected": collected,
        "remaining": _money(remaining),
    }


def get_client_open_invoices(client_id, exclude_receipt_id=None):
    """
    فواتير العميل التي ما زال عليها متبقٍ، مع المحصّل والمتبقي.
    exclude_receipt_id: عند تعديل سند، لا يُحتسب مبلغه ضمن المحصّل.
    """
    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT
                i.id, i.invoice_number, i.date, i.total,
                COALESCE(i.status, 'unpaid'),
                COALESCE(i.paid_by_receipts, 0),
                COALESCE((
                    SELECT SUM(r.amount) FROM receipts r
                    WHERE r.invoice_id = i.id
                      AND COALESCE(r.status, 'active') = 'active'
                      AND (? IS NULL OR r.id != ?)
                ), 0)
            FROM invoices i
            WHERE i.client_id = ?
              AND COALESCE(i.status, 'unpaid') != 'cancelled'
            ORDER BY i.date, i.id
            """,
            (exclude_receipt_id, exclude_receipt_id, client_id)
        ).fetchall()
    finally:
        conn.close()

    result = []

    for inv_id, number, date, total, status, flag, collected in rows:
        remaining = _invoice_remaining(total, status, flag, collected)

        if remaining > _EPS:
            result.append({
                "id": inv_id,
                "invoice_number": number,
                "date": date,
                "total": _money(total),
                "collected": _money(collected),
                "remaining": _money(remaining),
            })

    return result


def _validate_receipt(conn, client_id, invoice_id, amount,
                      exclude_receipt_id=None):
    """يفحص العميل والفاتورة المرتبطة وأن المبلغ لا يتجاوز المتبقي."""

    if not client_id:
        raise ValueError("يرجى اختيار العميل")

    if not conn.execute(
        "SELECT 1 FROM clients WHERE id = ?", (client_id,)
    ).fetchone():
        raise ValueError("العميل غير موجود")

    if not invoice_id:
        return  # دفعة على الحساب بدون فاتورة

    row = conn.execute(
        "SELECT client_id, total, COALESCE(status, 'unpaid'), "
        "COALESCE(paid_by_receipts, 0), invoice_number "
        "FROM invoices WHERE id = ?",
        (invoice_id,)
    ).fetchone()

    if not row:
        raise ValueError("الفاتورة المرتبطة غير موجودة")

    inv_client, total, status, flag, number = row

    if inv_client != client_id:
        raise ValueError("الفاتورة المختارة لا تخص هذا العميل")

    if status == STATUS_CANCELLED:
        raise ValueError(f"الفاتورة {number} ملغاة ولا يمكن التحصيل عليها")

    collected = _active_collected(conn, invoice_id, exclude_receipt_id)
    remaining = _invoice_remaining(total, status, flag, collected)

    if remaining <= _EPS:
        raise ValueError(f"الفاتورة {number} مسددة بالكامل")

    if amount > remaining + _EPS:
        raise ValueError(
            f"المبلغ ({_fmt(amount)}) أكبر من المتبقي على الفاتورة "
            f"{number} ({_fmt(remaining)}).\n"
            "خفّض المبلغ، أو اجعل السند دفعة على الحساب بدون فاتورة."
        )


def add_receipt(client_id, amount, date=None, payment_method="cash",
                reference="", notes="", invoice_id=None):
    """إنشاء سند قبض. يرجع رقم السند (id)."""

    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)

    with db_connection() as conn:
        _validate_receipt(conn, client_id, invoice_id, amount)

        cursor = conn.cursor()
        number = _next_number(cursor, "receipts", "receipt_number", "RC")

        cursor.execute(
            """
            INSERT INTO receipts (
                receipt_number, client_id, invoice_id, amount, date,
                payment_method, reference, notes, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                number, client_id, invoice_id or None, amount, date,
                method, (reference or "").strip(), (notes or "").strip()
            )
        )

        receipt_id = cursor.lastrowid
        _sync_invoice_payment(conn, invoice_id)

    return receipt_id


def update_receipt(receipt_id, client_id, amount, date=None,
                   payment_method="cash", reference="", notes="",
                   invoice_id=None):

    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)

    with db_connection() as conn:
        row = conn.execute(
            "SELECT invoice_id, COALESCE(status, 'active') "
            "FROM receipts WHERE id = ?",
            (receipt_id,)
        ).fetchone()

        if not row:
            raise ValueError("السند غير موجود")

        old_invoice_id, status = row

        if status == VOUCHER_CANCELLED:
            raise ValueError("لا يمكن تعديل سند ملغى. أعد تفعيله أولاً.")

        _validate_receipt(
            conn, client_id, invoice_id, amount,
            exclude_receipt_id=receipt_id
        )

        conn.execute(
            """
            UPDATE receipts
            SET client_id=?, invoice_id=?, amount=?, date=?,
                payment_method=?, reference=?, notes=?
            WHERE id=?
            """,
            (
                client_id, invoice_id or None, amount, date,
                method, (reference or "").strip(), (notes or "").strip(),
                receipt_id
            )
        )

        for inv in {old_invoice_id, invoice_id}:
            _sync_invoice_payment(conn, inv)


def set_receipts_status(receipt_ids, status):
    """إلغاء سندات القبض أو إعادة تفعيلها. يرجع عدد السندات المتغيّرة."""

    if status not in VOUCHER_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(receipt_ids)
    changed = 0

    with db_connection() as conn:
        for receipt_id in ids:
            row = conn.execute(
                "SELECT client_id, invoice_id, amount, receipt_number, "
                "COALESCE(status, 'active') FROM receipts WHERE id = ?",
                (receipt_id,)
            ).fetchone()

            if not row or row[4] == status:
                continue

            client_id, invoice_id, amount, number, _old = row

            if status == VOUCHER_ACTIVE:
                try:
                    _validate_receipt(
                        conn, client_id, invoice_id, amount,
                        exclude_receipt_id=receipt_id
                    )
                except ValueError as e:
                    raise ValueError(
                        f"تعذّرت إعادة تفعيل السند {number}:\n{e}"
                    ) from None

            conn.execute(
                "UPDATE receipts SET status = ? WHERE id = ?",
                (status, receipt_id)
            )
            _sync_invoice_payment(conn, invoice_id)
            changed += 1

    return changed


def delete_receipts(receipt_ids):
    """حذف نهائي لسندات القبض. يرجع عدد المحذوف."""

    ids = _as_id_list(receipt_ids)
    deleted = 0

    with db_connection() as conn:
        for receipt_id in ids:
            row = conn.execute(
                "SELECT invoice_id FROM receipts WHERE id = ?", (receipt_id,)
            ).fetchone()

            if not row:
                continue

            conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
            _sync_invoice_payment(conn, row[0])
            deleted += 1

    return deleted


# ======================================================================
# تصنيفات المصروفات
# ======================================================================
def get_expense_categories():
    """[(id, name)]"""

    conn = connect()

    try:
        return conn.execute(
            "SELECT id, name FROM expense_categories ORDER BY name"
        ).fetchall()
    finally:
        conn.close()


def add_expense_category(name):
    name = (name or "").strip()

    if not name:
        raise ValueError("اسم التصنيف مطلوب")

    try:
        with db_connection() as conn:
            return conn.execute(
                "INSERT INTO expense_categories (name) VALUES (?)", (name,)
            ).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("هذا التصنيف موجود مسبقاً") from None


def rename_expense_category(category_id, name):
    name = (name or "").strip()

    if not name:
        raise ValueError("اسم التصنيف مطلوب")

    try:
        with db_connection() as conn:
            conn.execute(
                "UPDATE expense_categories SET name = ? WHERE id = ?",
                (name, category_id)
            )
    except sqlite3.IntegrityError:
        raise ValueError("هذا التصنيف موجود مسبقاً") from None


def delete_expense_category(category_id):
    with db_connection() as conn:
        used = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM expenses WHERE category_id = ?) +
                (SELECT COUNT(*) FROM payment_vouchers WHERE category_id = ?)
            """,
            (category_id, category_id)
        ).fetchone()[0]

        if used:
            raise ValueError(
                f"لا يمكن حذف تصنيف مستخدم ({used} عملية مرتبطة به)."
            )

        conn.execute(
            "DELETE FROM expense_categories WHERE id = ?", (category_id,)
        )


# ======================================================================
# المصروفات
# ======================================================================
_EXPENSE_KEYS = (
    "id", "expense_number", "title", "category_id", "category",
    "supplier", "amount", "date", "notes", "status", "paid",
)

_EXPENSE_SELECT = """
    SELECT
        e.id, e.expense_number, e.title, e.category_id, c.name,
        e.supplier, e.amount, e.date, e.notes,
        COALESCE(e.status, 'active'),
        COALESCE((
            SELECT SUM(v.amount) FROM payment_vouchers v
            WHERE v.expense_id = e.id
              AND COALESCE(v.status, 'active') = 'active'
        ), 0)
    FROM expenses e
    LEFT JOIN expense_categories c ON c.id = e.category_id
"""


def _expense_pay_status(amount, paid):
    amount, paid = _money(amount), _money(paid)

    if paid <= _EPS:
        return EXPENSE_UNPAID

    if paid >= amount - _EPS:
        return EXPENSE_PAID

    return EXPENSE_PARTIAL


def _expense_dict(row):
    data = dict(zip(_EXPENSE_KEYS, row))
    data["category"] = data["category"] or "غير مصنف"
    data["supplier"] = data["supplier"] or ""
    data["notes"] = data["notes"] or ""
    data["amount"] = _money(data["amount"])
    data["paid"] = _money(data["paid"])
    data["remaining"] = (
        0.0 if data["status"] == VOUCHER_CANCELLED
        else max(_money(data["amount"] - data["paid"]), 0.0)
    )
    data["pay_status"] = _expense_pay_status(data["amount"], data["paid"])
    return data


def get_expenses():
    conn = connect()

    try:
        rows = conn.execute(
            _EXPENSE_SELECT + " ORDER BY e.date DESC, e.id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [_expense_dict(row) for row in rows]


def get_expense(expense_id):
    conn = connect()

    try:
        row = conn.execute(
            _EXPENSE_SELECT + " WHERE e.id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()

    return _expense_dict(row) if row else None


def get_unpaid_expenses(exclude_voucher_id=None):
    """
    المصروفات الفعّالة التي ما زال عليها متبقٍ للسداد.
    exclude_voucher_id: عند تعديل سند صرف لا يُحتسب مبلغه ضمن المدفوع.
    """
    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT
                e.id, e.expense_number, e.title, e.supplier, e.amount,
                COALESCE(c.name, 'غير مصنف'),
                COALESCE((
                    SELECT SUM(v.amount) FROM payment_vouchers v
                    WHERE v.expense_id = e.id
                      AND COALESCE(v.status, 'active') = 'active'
                      AND (? IS NULL OR v.id != ?)
                ), 0)
            FROM expenses e
            LEFT JOIN expense_categories c ON c.id = e.category_id
            WHERE COALESCE(e.status, 'active') = 'active'
            ORDER BY e.date, e.id
            """,
            (exclude_voucher_id, exclude_voucher_id)
        ).fetchall()
    finally:
        conn.close()

    result = []

    for exp_id, number, title, supplier, amount, category, paid in rows:
        remaining = _money(amount) - _money(paid)

        if remaining > _EPS:
            result.append({
                "id": exp_id,
                "expense_number": number,
                "title": title,
                "supplier": supplier or "",
                "category": category,
                "amount": _money(amount),
                "paid": _money(paid),
                "remaining": _money(remaining),
            })

    return result


def _check_category(conn, category_id):
    if category_id and not conn.execute(
        "SELECT 1 FROM expense_categories WHERE id = ?", (category_id,)
    ).fetchone():
        raise ValueError("تصنيف المصروف غير موجود")


def add_expense(title, amount, date=None, category_id=None, supplier="",
                notes="", pay_now=False, payment_method="cash", reference=""):
    """
    إضافة مصروف. مع pay_now=True يُنشأ معه سند صرف بكامل المبلغ في نفس
    المعاملة. يرجع (expense_id, voucher_id أو None).
    """
    title = (title or "").strip()

    if not title:
        raise ValueError("وصف المصروف مطلوب")

    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)
    supplier = (supplier or "").strip()

    with db_connection() as conn:
        _check_category(conn, category_id)

        cursor = conn.cursor()
        number = _next_number(cursor, "expenses", "expense_number", "EX")

        cursor.execute(
            """
            INSERT INTO expenses (
                expense_number, title, category_id, supplier,
                amount, date, notes, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                number, title, category_id or None, supplier,
                amount, date, (notes or "").strip()
            )
        )

        expense_id = cursor.lastrowid
        voucher_id = None

        if pay_now:
            voucher_id = _insert_payment_voucher(
                cursor,
                payee=supplier or title,
                amount=amount,
                date=date,
                method=method,
                reference=reference,
                notes=title,
                expense_id=expense_id,
                category_id=None,
            )

    return expense_id, voucher_id


def update_expense(expense_id, title, amount, date=None, category_id=None,
                   supplier="", notes=""):

    title = (title or "").strip()

    if not title:
        raise ValueError("وصف المصروف مطلوب")

    amount = _clean_amount(amount)
    date = _clean_date(date)

    with db_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(status, 'active') FROM expenses WHERE id = ?",
            (expense_id,)
        ).fetchone()

        if not row:
            raise ValueError("المصروف غير موجود")

        if row[0] == VOUCHER_CANCELLED:
            raise ValueError("لا يمكن تعديل مصروف ملغى. أعد تفعيله أولاً.")

        _check_category(conn, category_id)

        paid = _money(conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payment_vouchers "
            "WHERE expense_id = ? AND COALESCE(status, 'active') = 'active'",
            (expense_id,)
        ).fetchone()[0])

        if amount < paid - _EPS:
            raise ValueError(
                f"لا يمكن تخفيض المبلغ إلى {_fmt(amount)} "
                f"لأن المدفوع فعلاً {_fmt(paid)}.\n"
                "عدّل أو ألغِ سندات الصرف المرتبطة أولاً."
            )

        conn.execute(
            """
            UPDATE expenses
            SET title=?, category_id=?, supplier=?, amount=?, date=?, notes=?
            WHERE id=?
            """,
            (
                title, category_id or None, (supplier or "").strip(),
                amount, date, (notes or "").strip(), expense_id
            )
        )


def set_expenses_status(expense_ids, status):
    """إلغاء مصروفات أو إعادة تفعيلها (الإلغاء يتطلب عدم وجود سندات فعّالة)."""

    if status not in VOUCHER_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(expense_ids)
    changed = 0

    with db_connection() as conn:
        for expense_id in ids:
            row = conn.execute(
                "SELECT expense_number, COALESCE(status, 'active') "
                "FROM expenses WHERE id = ?",
                (expense_id,)
            ).fetchone()

            if not row or row[1] == status:
                continue

            if status == VOUCHER_CANCELLED:
                active = conn.execute(
                    "SELECT COUNT(*) FROM payment_vouchers "
                    "WHERE expense_id = ? "
                    "AND COALESCE(status, 'active') = 'active'",
                    (expense_id,)
                ).fetchone()[0]

                if active:
                    raise ValueError(
                        f"المصروف {row[0]} له {active} سند صرف فعّال.\n"
                        "ألغِ سندات الصرف المرتبطة به أولاً."
                    )

            conn.execute(
                "UPDATE expenses SET status = ? WHERE id = ?",
                (status, expense_id)
            )
            changed += 1

    return changed


def delete_expenses(expense_ids):
    """حذف نهائي للمصروفات التي ليس لها أي سند صرف."""

    ids = _as_id_list(expense_ids)
    deleted = 0

    with db_connection() as conn:
        for expense_id in ids:
            row = conn.execute(
                "SELECT expense_number FROM expenses WHERE id = ?",
                (expense_id,)
            ).fetchone()

            if not row:
                continue

            linked = conn.execute(
                "SELECT COUNT(*) FROM payment_vouchers WHERE expense_id = ?",
                (expense_id,)
            ).fetchone()[0]

            if linked:
                raise ValueError(
                    f"المصروف {row[0]} مرتبط بـ {linked} سند صرف.\n"
                    "احذف السندات أولاً، أو ألغِ المصروف بدلاً من حذفه."
                )

            conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            deleted += 1

    return deleted


# ======================================================================
# سندات الصرف
# ======================================================================
_VOUCHER_KEYS = (
    "id", "voucher_number", "payee", "expense_id", "expense_number",
    "expense_title", "category_id", "category",
    "amount", "date", "payment_method", "reference", "notes", "status",
)

_VOUCHER_SELECT = """
    SELECT
        v.id, v.voucher_number, v.payee, v.expense_id,
        e.expense_number, e.title,
        COALESCE(e.category_id, v.category_id), c.name,
        v.amount, v.date, v.payment_method, v.reference, v.notes,
        COALESCE(v.status, 'active')
    FROM payment_vouchers v
    LEFT JOIN expenses e ON e.id = v.expense_id
    LEFT JOIN expense_categories c
        ON c.id = COALESCE(e.category_id, v.category_id)
"""


def _voucher_dict(row):
    data = dict(zip(_VOUCHER_KEYS, row))
    data["payment_method"] = data["payment_method"] or "cash"
    data["category"] = data["category"] or "غير مصنف"
    data["reference"] = data["reference"] or ""
    data["notes"] = data["notes"] or ""
    return data


def get_payment_vouchers():
    conn = connect()

    try:
        rows = conn.execute(
            _VOUCHER_SELECT + " ORDER BY v.date DESC, v.id DESC"
        ).fetchall()
    finally:
        conn.close()

    return [_voucher_dict(row) for row in rows]


def get_payment_voucher(voucher_id):
    conn = connect()

    try:
        row = conn.execute(
            _VOUCHER_SELECT + " WHERE v.id = ?", (voucher_id,)
        ).fetchone()
    finally:
        conn.close()

    return _voucher_dict(row) if row else None


def get_voucher_expense_summary(voucher_id):
    """ملخص المصروف المرتبط بالسند (للطباعة): الإجمالي/المدفوع/المتبقي."""

    voucher = get_payment_voucher(voucher_id)

    if not voucher or not voucher["expense_id"]:
        return None

    expense = get_expense(voucher["expense_id"])

    if not expense:
        return None

    return {
        "total": expense["amount"],
        "paid": expense["paid"],
        "remaining": expense["remaining"],
    }


def _validate_voucher(conn, expense_id, amount, category_id,
                      exclude_voucher_id=None):

    _check_category(conn, category_id)

    if not expense_id:
        return  # دفعة مستقلة غير مرتبطة بمصروف

    row = conn.execute(
        "SELECT amount, COALESCE(status, 'active'), expense_number "
        "FROM expenses WHERE id = ?",
        (expense_id,)
    ).fetchone()

    if not row:
        raise ValueError("المصروف المرتبط غير موجود")

    expense_amount, status, number = row

    if status == VOUCHER_CANCELLED:
        raise ValueError(f"المصروف {number} ملغى ولا يمكن الصرف عليه")

    paid = _money(conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) FROM payment_vouchers
        WHERE expense_id = ?
          AND COALESCE(status, 'active') = 'active'
          AND (? IS NULL OR id != ?)
        """,
        (expense_id, exclude_voucher_id, exclude_voucher_id)
    ).fetchone()[0])

    remaining = _money(expense_amount) - paid

    if remaining <= _EPS:
        raise ValueError(f"المصروف {number} مسدد بالكامل")

    if amount > remaining + _EPS:
        raise ValueError(
            f"المبلغ ({_fmt(amount)}) أكبر من المتبقي على المصروف "
            f"{number} ({_fmt(remaining)})."
        )


def _insert_payment_voucher(cursor, payee, amount, date, method, reference,
                            notes, expense_id, category_id):

    number = _next_number(
        cursor, "payment_vouchers", "voucher_number", "PV"
    )

    cursor.execute(
        """
        INSERT INTO payment_vouchers (
            voucher_number, payee, expense_id, category_id, amount, date,
            payment_method, reference, notes, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            number, payee, expense_id or None, category_id or None,
            amount, date, method, (reference or "").strip(),
            (notes or "").strip()
        )
    )

    return cursor.lastrowid


def _resolve_payee(conn, payee, expense_id):
    payee = (payee or "").strip()

    if not payee and expense_id:
        row = conn.execute(
            "SELECT supplier, title FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()

        if row:
            payee = (row[0] or row[1] or "").strip()

    if not payee:
        raise ValueError("اسم المستفيد مطلوب")

    return payee


def add_payment_voucher(payee, amount, date=None, payment_method="cash",
                        reference="", notes="", expense_id=None,
                        category_id=None):
    """إنشاء سند صرف. يرجع رقم السند (id)."""

    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)

    with db_connection() as conn:
        _validate_voucher(conn, expense_id, amount, category_id)
        payee = _resolve_payee(conn, payee, expense_id)

        return _insert_payment_voucher(
            conn.cursor(), payee, amount, date, method, reference, notes,
            expense_id, None if expense_id else category_id
        )


def update_payment_voucher(voucher_id, payee, amount, date=None,
                           payment_method="cash", reference="", notes="",
                           expense_id=None, category_id=None):

    amount = _clean_amount(amount)
    date = _clean_date(date)
    method = _clean_method(payment_method)

    with db_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(status, 'active') FROM payment_vouchers "
            "WHERE id = ?",
            (voucher_id,)
        ).fetchone()

        if not row:
            raise ValueError("السند غير موجود")

        if row[0] == VOUCHER_CANCELLED:
            raise ValueError("لا يمكن تعديل سند ملغى. أعد تفعيله أولاً.")

        _validate_voucher(
            conn, expense_id, amount, category_id,
            exclude_voucher_id=voucher_id
        )
        payee = _resolve_payee(conn, payee, expense_id)

        conn.execute(
            """
            UPDATE payment_vouchers
            SET payee=?, expense_id=?, category_id=?, amount=?, date=?,
                payment_method=?, reference=?, notes=?
            WHERE id=?
            """,
            (
                payee, expense_id or None,
                None if expense_id else (category_id or None),
                amount, date, method, (reference or "").strip(),
                (notes or "").strip(), voucher_id
            )
        )


def set_vouchers_status(voucher_ids, status):
    """إلغاء سندات الصرف أو إعادة تفعيلها."""

    if status not in VOUCHER_STATUSES:
        raise ValueError(f"حالة غير صالحة: {status}")

    ids = _as_id_list(voucher_ids)
    changed = 0

    with db_connection() as conn:
        for voucher_id in ids:
            row = conn.execute(
                "SELECT expense_id, category_id, amount, voucher_number, "
                "COALESCE(status, 'active') FROM payment_vouchers "
                "WHERE id = ?",
                (voucher_id,)
            ).fetchone()

            if not row or row[4] == status:
                continue

            expense_id, category_id, amount, number, _old = row

            if status == VOUCHER_ACTIVE:
                try:
                    _validate_voucher(
                        conn, expense_id, amount, category_id,
                        exclude_voucher_id=voucher_id
                    )
                except ValueError as e:
                    raise ValueError(
                        f"تعذّرت إعادة تفعيل السند {number}:\n{e}"
                    ) from None

            conn.execute(
                "UPDATE payment_vouchers SET status = ? WHERE id = ?",
                (status, voucher_id)
            )
            changed += 1

    return changed


def delete_payment_vouchers(voucher_ids):
    ids = _as_id_list(voucher_ids)

    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.executemany(
            "DELETE FROM payment_vouchers WHERE id = ?",
            [(voucher_id,) for voucher_id in ids]
        )

        return cursor.rowcount


# ======================================================================
# اللوحة المالية
# ======================================================================
def _period_clause(column, start, end):
    clauses, params = [], []

    if start:
        clauses.append(f"{column} >= ?")
        params.append(start)

    if end:
        clauses.append(f"{column} <= ?")
        params.append(end)

    sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def _scalar(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else 0


def get_finance_summary(start=None, end=None):
    """
    ملخص مالي للفترة [start, end] (نصوص YYYY-MM-DD، وأي طرف اختياري):

      sales          إجمالي المبيعات (الفواتير غير الملغاة)
      receipts       المقبوضات (سندات القبض الفعّالة)
      expenses       المصروفات (غير الملغاة)
      payments       المدفوعات (سندات الصرف الفعّالة)
      other_payments مدفوعات غير مرتبطة بمصروف
      net_profit     صافي الربح = المبيعات − المصروفات
      net_cash       صافي النقدية = المقبوضات − المدفوعات
      receivables    ذمم العملاء المستحقة (كل الفترات)
      payables       مصروفات مستحقة لم تُسدَّد (كل الفترات)
    """
    conn = connect()

    try:
        sql, params = _period_clause("date", start, end)

        sales = _money(_scalar(
            conn,
            "SELECT SUM(total) FROM invoices "
            "WHERE COALESCE(status, 'unpaid') != 'cancelled'" + sql,
            params
        ))
        invoices_count = int(_scalar(
            conn,
            "SELECT COUNT(*) FROM invoices "
            "WHERE COALESCE(status, 'unpaid') != 'cancelled'" + sql,
            params
        ))

        receipts = _money(_scalar(
            conn,
            "SELECT SUM(amount) FROM receipts "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))
        receipts_count = int(_scalar(
            conn,
            "SELECT COUNT(*) FROM receipts "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))

        expenses = _money(_scalar(
            conn,
            "SELECT SUM(amount) FROM expenses "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))
        expenses_count = int(_scalar(
            conn,
            "SELECT COUNT(*) FROM expenses "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))

        payments = _money(_scalar(
            conn,
            "SELECT SUM(amount) FROM payment_vouchers "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))
        payments_count = int(_scalar(
            conn,
            "SELECT COUNT(*) FROM payment_vouchers "
            "WHERE COALESCE(status, 'active') = 'active'" + sql,
            params
        ))
        other_payments = _money(_scalar(
            conn,
            "SELECT SUM(amount) FROM payment_vouchers "
            "WHERE COALESCE(status, 'active') = 'active' "
            "AND expense_id IS NULL" + sql,
            params
        ))

        # ذمم العملاء (كل الفواتير غير المسدّدة بغض النظر عن الفترة)
        receivables, receivables_count = 0.0, 0

        for total, status, flag, collected in conn.execute(
            """
            SELECT
                i.total, COALESCE(i.status, 'unpaid'),
                COALESCE(i.paid_by_receipts, 0),
                COALESCE((
                    SELECT SUM(r.amount) FROM receipts r
                    WHERE r.invoice_id = i.id
                      AND COALESCE(r.status, 'active') = 'active'
                ), 0)
            FROM invoices i
            """
        ).fetchall():
            remaining = _invoice_remaining(total, status, flag, collected)

            if remaining > _EPS:
                receivables += remaining
                receivables_count += 1

        # مستحقات الموردين (مصروفات لم تُسدَّد بعد)
        payables, payables_count = 0.0, 0

        for amount, paid in conn.execute(
            """
            SELECT
                e.amount,
                COALESCE((
                    SELECT SUM(v.amount) FROM payment_vouchers v
                    WHERE v.expense_id = e.id
                      AND COALESCE(v.status, 'active') = 'active'
                ), 0)
            FROM expenses e
            WHERE COALESCE(e.status, 'active') = 'active'
            """
        ).fetchall():
            remaining = _money(amount) - _money(paid)

            if remaining > _EPS:
                payables += remaining
                payables_count += 1
    finally:
        conn.close()

    return {
        "sales": sales,
        "invoices_count": invoices_count,
        "receipts": receipts,
        "receipts_count": receipts_count,
        "expenses": expenses,
        "expenses_count": expenses_count,
        "payments": payments,
        "payments_count": payments_count,
        "other_payments": other_payments,
        "net_profit": _money(sales - expenses),
        "net_cash": _money(receipts - payments),
        "receivables": _money(receivables),
        "receivables_count": receivables_count,
        "payables": _money(payables),
        "payables_count": payables_count,
    }


def get_monthly_series(year):
    """12 عنصراً (شهر 1..12): المبيعات والمقبوضات والمصروفات والمدفوعات."""

    year = str(int(year))

    series = [
        {
            "month": m, "sales": 0.0, "receipts": 0.0,
            "expenses": 0.0, "payments": 0.0,
        }
        for m in range(1, 13)
    ]

    queries = {
        "sales": (
            "SELECT CAST(substr(date, 6, 2) AS INTEGER), SUM(total) "
            "FROM invoices WHERE COALESCE(status, 'unpaid') != 'cancelled' "
            "AND substr(date, 1, 4) = ? GROUP BY 1"
        ),
        "receipts": (
            "SELECT CAST(substr(date, 6, 2) AS INTEGER), SUM(amount) "
            "FROM receipts WHERE COALESCE(status, 'active') = 'active' "
            "AND substr(date, 1, 4) = ? GROUP BY 1"
        ),
        "expenses": (
            "SELECT CAST(substr(date, 6, 2) AS INTEGER), SUM(amount) "
            "FROM expenses WHERE COALESCE(status, 'active') = 'active' "
            "AND substr(date, 1, 4) = ? GROUP BY 1"
        ),
        "payments": (
            "SELECT CAST(substr(date, 6, 2) AS INTEGER), SUM(amount) "
            "FROM payment_vouchers WHERE COALESCE(status, 'active') = 'active' "
            "AND substr(date, 1, 4) = ? GROUP BY 1"
        ),
    }

    conn = connect()

    try:
        for key, sql in queries.items():
            for month, total in conn.execute(sql, (year,)).fetchall():
                if month and 1 <= month <= 12:
                    series[month - 1][key] = _money(total)
    finally:
        conn.close()

    return series


def get_expense_by_category(start=None, end=None):
    """[(اسم التصنيف, المجموع)] مرتبة تنازلياً."""

    sql, params = _period_clause("e.date", start, end)

    conn = connect()

    try:
        rows = conn.execute(
            "SELECT COALESCE(c.name, 'غير مصنف'), SUM(e.amount) "
            "FROM expenses e "
            "LEFT JOIN expense_categories c ON c.id = e.category_id "
            "WHERE COALESCE(e.status, 'active') = 'active'" + sql +
            " GROUP BY 1 ORDER BY 2 DESC",
            params
        ).fetchall()
    finally:
        conn.close()

    return [(name, _money(total)) for name, total in rows]


def get_top_debtors(limit=5):
    """العملاء الأكثر مديونية: [{client, count, remaining}]"""

    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT
                c.name, i.total, COALESCE(i.status, 'unpaid'),
                COALESCE(i.paid_by_receipts, 0),
                COALESCE((
                    SELECT SUM(r.amount) FROM receipts r
                    WHERE r.invoice_id = i.id
                      AND COALESCE(r.status, 'active') = 'active'
                ), 0)
            FROM invoices i
            JOIN clients c ON c.id = i.client_id
            """
        ).fetchall()
    finally:
        conn.close()

    debtors = {}

    for name, total, status, flag, collected in rows:
        remaining = _invoice_remaining(total, status, flag, collected)

        if remaining > _EPS:
            entry = debtors.setdefault(
                name, {"client": name, "count": 0, "remaining": 0.0}
            )
            entry["count"] += 1
            entry["remaining"] += remaining

    result = sorted(
        debtors.values(), key=lambda d: d["remaining"], reverse=True
    )

    for entry in result:
        entry["remaining"] = _money(entry["remaining"])

    return result[:limit]


def get_recent_transactions(limit=8):
    """آخر الحركات النقدية (قبض/صرف): [{kind, number, party, amount, date}]"""

    conn = connect()

    try:
        rows = conn.execute(
            """
            SELECT 'receipt', r.receipt_number, c.name, r.amount, r.date, r.id
            FROM receipts r
            LEFT JOIN clients c ON c.id = r.client_id
            WHERE COALESCE(r.status, 'active') = 'active'
            UNION ALL
            SELECT 'payment', v.voucher_number, v.payee, v.amount, v.date, v.id
            FROM payment_vouchers v
            WHERE COALESCE(v.status, 'active') = 'active'
            ORDER BY 5 DESC, 6 DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "kind": kind, "number": number, "party": party or "-",
            "amount": _money(amount), "date": date,
        }
        for kind, number, party, amount, date, _id in rows
    ]
