import sqlite3
import os
import re
from datetime import datetime
from flask_login import current_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TENANTS_DIR = os.path.join(BASE_DIR, 'tenants')
MASTER_DB = os.path.join(BASE_DIR, 'master.db')

# Ensure directory exists for tenant DB files
os.makedirs(TENANTS_DIR, exist_ok=True)

def get_master_connection():
    """Connection to the master authentication and company registry database."""
    conn = sqlite3.connect(MASTER_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection(tenant_db_name=None):
    """
    Dynamically connects to the tenant's SQLite database file.
    If tenant_db_name is not provided, it resolves it from current_user.
    """
    if not tenant_db_name:
        if current_user.is_authenticated and hasattr(current_user, 'db_name'):
            tenant_db_name = current_user.db_name
        else:
            tenant_db_name = 'default_tenant.db'

    db_path = os.path.join(TENANTS_DIR, tenant_db_name)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_master_db():
    """Sets up the master database for tenant companies and logins."""
    conn = get_master_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            db_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            date_created TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        );
    ''')
    conn.commit()
    conn.close()

def init_tenant_db(db_name):
    """Initializes tables inside an isolated tenant database."""
    db_path = os.path.join(TENANTS_DIR, db_name)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            stock_qty INTEGER NOT NULL DEFAULT 0,
            cost_price REAL NOT NULL DEFAULT 0.0,
            selling_price REAL NOT NULL DEFAULT 0.0,
            date_added TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cellphone TEXT NOT NULL,
            email TEXT,
            date_added TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            sale_id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            quantity_sold INTEGER NOT NULL,
            sale_price REAL NOT NULL,
            sale_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            deposit_amount REAL DEFAULT 0.0,
            balance_amount REAL DEFAULT 0.0,
            completion_date TEXT,
            installment_plan TEXT,
            FOREIGN KEY (product_id) REFERENCES products (product_id),
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        );
    ''')

    conn.commit()
    conn.close()

def seed_initial_tenants(bcrypt_instance):
    """Seeds two default company tenants with their own credentials and databases."""
    init_master_db()
    conn = get_master_connection()
    company_count = conn.execute("SELECT COUNT(*) as count FROM companies").fetchone()['count']

    if company_count == 0:
        tenants = [
            ("Store Alpha", "store_alpha", "store_alpha.db", "admin_alpha", "alpha123"),
            ("Store Beta", "store_beta", "store_beta.db", "admin_beta", "beta123")
        ]

        for company_name, slug, db_file, admin_user, admin_pass in tenants:
            init_tenant_db(db_file)
            today = datetime.today().strftime('%Y-%m-%d')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO companies (company_name, slug, db_name, created_at)
                VALUES (?, ?, ?, ?)
            ''', (company_name, slug, db_file, today))
            company_id = cursor.lastrowid

            pw_hash = bcrypt_instance.generate_password_hash(admin_pass).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (company_id, username, password_hash, role, date_created)
                VALUES (?, ?, ?, 'admin', ?)
            ''', (company_id, admin_user, pw_hash, today))

        conn.commit()
        print(" Successfully initialized Master DB and seeded two isolated tenant databases.")

    conn.close()

def register_new_company(company_name, admin_username, admin_password, bcrypt_instance):
    """
    Provisions a new company and its isolated SQLite database:
    1. Creates a clean slug for filenames.
    2. Initializes an isolated tenant database file inside tenants/.
    3. Saves company & admin user credentials into master.db.
    """
    init_master_db()
    conn = get_master_connection()
    cursor = conn.cursor()

    base_slug = re.sub(r'[^a-zA-Z0-9]', '_', company_name.strip().lower())
    base_slug = re.sub(r'_+', '_', base_slug).strip('_')
    if not base_slug:
        base_slug = "company"

    slug = base_slug
    counter = 1
    while cursor.execute("SELECT 1 FROM companies WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}_{counter}"
        counter += 1

    db_filename = f"{slug}.db"

    existing_user = cursor.execute("SELECT 1 FROM users WHERE username = ?", (admin_username,)).fetchone()
    if existing_user:
        conn.close()
        return False, "This username is already taken. Please choose another."

    today = datetime.today().strftime('%Y-%m-%d')

    try:
        init_tenant_db(db_filename)

        cursor.execute('''
            INSERT INTO companies (company_name, slug, db_name, created_at)
            VALUES (?, ?, ?, ?)
        ''', (company_name, slug, db_filename, today))
        new_company_id = cursor.lastrowid

        pw_hash = bcrypt_instance.generate_password_hash(admin_password).decode('utf-8')
        cursor.execute('''
            INSERT INTO users (company_id, username, password_hash, role, date_created)
            VALUES (?, ?, ?, 'admin', ?)
        ''', (new_company_id, admin_username, pw_hash, today))

        conn.commit()
        return True, "Company and administrator registered successfully!"
    except Exception as e:
        conn.rollback()
        return False, f"Failed to provision company: {str(e)}"
    finally:
        conn.close()