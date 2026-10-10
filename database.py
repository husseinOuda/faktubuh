# database.py

import sqlite3
import json
import hashlib
from datetime import datetime

DB_NAME = "invoices.db"


# ======================
# الاتصال بقاعدة البيانات
# ======================
def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ======================
# التشفير
# ======================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


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
        name TEXT,
        phone TEXT
    )
    """)

    # الفواتير
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        total REAL,
        date TEXT,
        invoice_number,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )
    """)

    # أصناف الفاتورة
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        item_name TEXT,
        quantity INTEGER,
        price REAL,
        total REAL,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    """)
    
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
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO clients (name, phone) VALUES (?, ?)",
        (name, phone)
    )

    conn.commit()
    conn.close()


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
            clients.name

        FROM invoices

        LEFT JOIN clients
        ON invoices.client_id = clients.id

        WHERE invoices.id=?
    """, (invoice_id,))

    data = cursor.fetchone()

    conn.close()

    return data

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
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE clients
        SET name=?, phone=?
        WHERE id=?
        """,
        (name, phone, client_id)
    )

    conn.commit()
    conn.close()


# ❌ حذف عميل
# ======================
def delete_client(client_id):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM clients WHERE id=?",
        (client_id,)
    )

    conn.commit()
    conn.close()


# ======================
# الفواتير
# ======================

# ➕ إضافة فاتورة
def save_invoice(client_id, date, items):
    conn = connect()
    cursor = conn.cursor()

    total = sum(item['total'] for item in items)

    # إنشاء رقم فاتورة
    invoice_number = generate_invoice_number()

    cursor.execute(
        """
        INSERT INTO invoices
        (client_id, total, date, invoice_number)
        VALUES (?, ?, ?, ?)
        """,
        (
            client_id,
            total,
            date,
            invoice_number
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
            item['name'],
            item.get('desc', ''),
            item['qty'],
            item['price'],
            item['total']
        ))

    conn.commit()
    conn.close()

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
            invoices.total

        FROM invoices

        JOIN clients
        ON invoices.client_id = clients.id

        ORDER BY invoices.id DESC
    """)

    data = cursor.fetchall()

    conn.close()

    return data

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
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM invoice_items WHERE invoice_id=?",
        (invoice_id,)
    )

    cursor.execute(
        "DELETE FROM invoices WHERE id=?",
        (invoice_id,)
    )

    conn.commit()
    conn.close()

# ✏️ تعديل فاتورة
# ======================
def update_invoice(invoice_id, client_id, items):
    conn = connect()
    cursor = conn.cursor()

    total = sum(item['total'] for item in items)

    cursor.execute(
        """
        UPDATE invoices
        SET client_id=?, total=?
        WHERE id=?
        """,
        (client_id, total, invoice_id)
    )

    # حذف الأصناف القديمة
    cursor.execute(
        "DELETE FROM invoice_items WHERE invoice_id=?",
        (invoice_id,)
    )

    # إعادة إدخال الأصناف الجديدة
    for item in items:
        cursor.execute(
            """
            INSERT INTO invoice_items
            (invoice_id, item_name, description, quantity, price, total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                item['name'],
                item.get('desc', ''),
                item['qty'],
                item['price'],
                item['total']
            )
        )

    conn.commit()
    conn.close()

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

    cursor.execute("SELECT SUM(total) FROM invoices")
    result = cursor.fetchone()[0]

    conn.close()
    return result if result else 0


def get_profit_by_date(start, end):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT SUM(total) FROM invoices
    WHERE date BETWEEN ? AND ?
    """, (start, end))

    result = cursor.fetchone()[0]

    conn.close()
    return result if result else 0

# ======================
# ترقية قاعدة البيانات
# ======================
def migrate_database():
    conn = connect()
    cursor = conn.cursor()

    # إضافة description إذا غير موجود
    try:
        cursor.execute("ALTER TABLE invoice_items ADD COLUMN description TEXT")
    except:
        pass  # العمود موجود مسبقًا

    conn.commit()
    conn.close()



