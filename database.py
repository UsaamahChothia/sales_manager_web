import sqlite3
import os

# Path to our SQLite database file
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

def get_db_connection():
    """Establishes a connection to the database and returns it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Creates the necessary tables if they don't exist yet."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Products Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            stock_qty INTEGER NOT NULL DEFAULT 0,
            cost_price REAL NOT NULL,
            selling_price REAL NOT NULL,
            date_added TEXT NOT NULL
        )
    ''')
    
    # 2. Customers Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cellphone TEXT NOT NULL,
            date_added TEXT NOT NULL
        )
    ''')
    
    # 3. Sales Table
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
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✨ Relational Database Engine Initialized Successfully!")
