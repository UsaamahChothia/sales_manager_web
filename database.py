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
    If tenant_db_name is not provided, resolves it from current_user.
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
    """Sets up master authentication database and handles schema migrations."""
    conn = get_master_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            db_name TEXT NOT NULL,
            business_type TEXT NOT NULL DEFAULT 'retail',
            created_at TEXT NOT NULL
        );
    ''')

    # Safe column migration if companies table existed previously without business_type
    cursor.execute("PRAGMA table_info(companies);")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'business_type' not in columns:
        cursor.execute("ALTER TABLE companies ADD COLUMN business_type TEXT NOT NULL DEFAULT 'retail';")

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

    # Restaurant raw inventory
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            ingredient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            unit TEXT NOT NULL,
            stock_qty REAL NOT NULL DEFAULT 0.0,
            cost_per_unit REAL NOT NULL DEFAULT 0.0,
            date_added TEXT NOT NULL
        );
    ''')

    # Restaurant recipe mapping (Bill of Materials)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            ingredient_id TEXT NOT NULL,
            qty_required REAL NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (product_id),
            FOREIGN KEY (ingredient_id) REFERENCES ingredients (ingredient_id)
        );
    ''')

    conn.commit()
    conn.close()

def seed_initial_tenants(bcrypt_instance):
    """Seeds default tenants if database is clean."""
    init_master_db()
    conn = get_master_connection()
    company_count = conn.execute("SELECT COUNT(*) as count FROM companies").fetchone()['count']

    if company_count == 0:
        tenants = [
            ("Store Alpha", "store_alpha", "store_alpha.db", "retail", "admin_alpha", "alpha123"),
            ("Store Beta", "store_beta", "store_beta.db", "retail", "admin_beta", "beta123")
        ]

        for company_name, slug, db_file, b_type, admin_user, admin_pass in tenants:
            init_tenant_db(db_file)
            today = datetime.today().strftime('%Y-%m-%d')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO companies (company_name, slug, db_name, business_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (company_name, slug, db_file, b_type, today))
            company_id = cursor.lastrowid

            pw_hash = bcrypt_instance.generate_password_hash(admin_pass).decode('utf-8')
            cursor.execute('''
                INSERT INTO users (company_id, username, password_hash, role, date_created)
                VALUES (?, ?, ?, 'admin', ?)
            ''', (company_id, admin_user, pw_hash, today))

        conn.commit()
        print(" Successfully seeded master and default tenant databases.")

    conn.close()

def register_new_company(company_name, admin_username, admin_password, business_type, bcrypt_instance):
    """
    Provisions a new tenant database:
    1. Creates a clean slug for filenames.
    2. Provisions isolated tenant DB with both retail & recipe tables.
    3. Records company, business_type, and hashed admin user in master.db.
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
    b_type = 'restaurant' if business_type == 'restaurant' else 'retail'

    try:
        init_tenant_db(db_filename)

        cursor.execute('''
            INSERT INTO companies (company_name, slug, db_name, business_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (company_name, slug, db_filename, b_type, today))
        new_company_id = cursor.lastrowid

        pw_hash = bcrypt_instance.generate_password_hash(admin_password).decode('utf-8')
        cursor.execute('''
            INSERT INTO users (company_id, username, password_hash, role, date_created)
            VALUES (?, ?, ?, 'admin', ?)
        ''', (new_company_id, admin_username, pw_hash, today))

        conn.commit()
        return True, "Company provisioned successfully!"
    except Exception as e:
        conn.rollback()
        return False, f"Provisioning failed: {str(e)}"
    finally:
        conn.close()

def delete_company_by_id(company_id):
    """
    Purges a tenant:
    1. Removes all linked users in master.db
    2. Deletes the company record from master.db
    3. Deletes the tenant's isolated .db file from tenants/
    """
    init_master_db()
    conn = get_master_connection()
    cursor = conn.cursor()

    company = cursor.execute("SELECT db_name FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        conn.close()
        return False, "Company record not found."

    db_filename = company['db_name']
    db_path = os.path.join(TENANTS_DIR, db_filename)

    try:
        cursor.execute("DELETE FROM users WHERE company_id = ?", (company_id,))
        cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        conn.commit()

        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError as err:
                print(f"Warning: Could not remove file {db_path}: {err}")

        return True, "Business and associated database successfully deleted."
    except Exception as e:
        conn.rollback()
        return False, f"Failed to delete company: {str(e)}"
    finally:
        conn.close()