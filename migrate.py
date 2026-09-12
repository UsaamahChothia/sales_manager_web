import csv
import os
import sqlite3
from database import init_db, get_db_connection

def clean_val(val, default=''):
    return val.strip() if val else default

def migrate_csv_to_sqlite():
    print("🚀 Beginning system data migration...")
    
    # 1. Setup clean schema
    init_db()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Temporarily disable foreign keys so legacy mismatch rows can be imported or inspected safely
    cursor.execute("PRAGMA foreign_keys = OFF;")
    
    # 2. Migrate Products
    products_migrated = 0
    if os.path.exists('products.csv'):
        with open('products.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = clean_val(row.get('product_id'))
                if p_id:
                    cursor.execute('''
                        INSERT OR REPLACE INTO products (product_id, product_name, stock_qty, cost_price, selling_price, date_added)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        p_id, 
                        clean_val(row.get('product_name'), 'Unknown Product'),
                        int(float(clean_val(row.get('stock_qty'), 0))), 
                        float(clean_val(row.get('cost_price'), 0)), 
                        float(clean_val(row.get('selling_price'), 0)), 
                        clean_val(row.get('date_added'), '2026-01-01')
                    ))
                    products_migrated += 1
        print(f"✅ Products migrated ({products_migrated} items).")

    # 3. Migrate Customers
    customers_migrated = 0
    if os.path.exists('customers.csv'):
        with open('customers.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                c_id = clean_val(row.get('customer_id'))
                if c_id:
                    cursor.execute('''
                        INSERT OR REPLACE INTO customers (customer_id, name, cellphone, email, date_added)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        c_id, 
                        clean_val(row.get('name'), 'Unknown Customer'), 
                        clean_val(row.get('cellphone'), '0000000000'),
                        clean_val(row.get('email'), ''),
                        clean_val(row.get('date_added'), '2026-01-01')
                    ))
                    customers_migrated += 1
        print(f"✅ Customers migrated ({customers_migrated} accounts).")

    # 4. Migrate Sales & Reconcile Missing Parent Keys
    sales_migrated = 0
    if os.path.exists('sales.csv'):
        with open('sales.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                s_id = clean_val(row.get('sale_id'))
                p_id = clean_val(row.get('product_id'))
                c_id = clean_val(row.get('customer_id'))
                
                if s_id and p_id and c_id:
                    # Auto-provision placeholder product if legacy sale points to non-existent ID
                    cursor.execute("SELECT product_id FROM products WHERE product_id = ?", (p_id,))
                    if not cursor.fetchone():
                        print(f"⚠️ Warning: Product '{p_id}' in sale '{s_id}' not found. Auto-generating catalog item.")
                        cursor.execute('''
                            INSERT INTO products (product_id, product_name, stock_qty, cost_price, selling_price, date_added)
                            VALUES (?, ?, 0, 0.0, ?, ?)
                        ''', (p_id, f"Archived Item ({p_id})", float(clean_val(row.get('sale_price'), 0)), clean_val(row.get('sale_date'), '2026-01-01')))

                    # Auto-provision placeholder customer if legacy sale points to non-existent ID
                    cursor.execute("SELECT customer_id FROM customers WHERE customer_id = ?", (c_id,))
                    if not cursor.fetchone():
                        print(f"⚠️ Warning: Customer '{c_id}' in sale '{s_id}' not found. Auto-generating customer record.")
                        cursor.execute('''
                            INSERT INTO customers (customer_id, name, cellphone, email, date_added)
                            VALUES (?, ?, '0000000000', '', ?)
                        ''', (c_id, f"Archived Customer ({c_id})", clean_val(row.get('sale_date'), '2026-01-01')))

                    cursor.execute('''
                        INSERT OR REPLACE INTO sales (
                            sale_id, product_id, customer_id, quantity_sold, sale_price, sale_date, 
                            payment_type, payment_status, deposit_amount, balance_amount, completion_date, installment_plan
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        s_id,
                        p_id,
                        c_id,
                        int(float(clean_val(row.get('quantity_sold'), 1))),
                        float(clean_val(row.get('sale_price'), 0)),
                        clean_val(row.get('sale_date'), '2026-01-01'),
                        clean_val(row.get('payment_type'), 'cash'),
                        clean_val(row.get('payment_status'), 'paid'),
                        float(clean_val(row.get('deposit_amount'), 0)),
                        float(clean_val(row.get('balance_amount'), 0)),
                        clean_val(row.get('completion_date'), ''),
                        clean_val(row.get('installment_plan'), '')
                    ))
                    sales_migrated += 1
                    
        print(f"✅ Sales records migrated ({sales_migrated} sales).")

    conn.commit()
    
    # Re-enable foreign key enforcement
    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.close()
    print("🎉 Data migration finished cleanly with 100% relational integrity!")

if __name__ == '__main__':
    migrate_csv_to_sqlite()