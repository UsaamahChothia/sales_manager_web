import csv
import os
from database import init_db, get_db_connection

def migrate_csv_to_sqlite():
    print("🚀 Beginning system data migration...")
    
    # First, setup the empty tables
    init_db()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Migrate Products
    if os.path.exists('products.csv'):
        with open('products.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('product_id'):
                    cursor.execute('''
                        INSERT OR IGNORE INTO products (product_id, product_name, stock_qty, cost_price, selling_price, date_added)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (row['product_id'], row['product_name'], int(row['stock_qty']), 
                          float(row['cost_price']), float(row['selling_price']), row['date_added']))
        print("✅ Products migrated to database.")

    # 2. Migrate Customers
    if os.path.exists('customers.csv'):
        with open('customers.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('customer_id'):
                    cursor.execute('''
                        INSERT OR IGNORE INTO customers (customer_id, name, cellphone, date_added)
                        VALUES (?, ?, ?, ?)
                    ''', (row['customer_id'], row['name'], row['cellphone'], row['date_added']))
        print("✅ Customers migrated to database.")

    # 3. Migrate Sales
    if os.path.exists('sales.csv'):
        with open('sales.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('sale_id'):
                    cursor.execute('''
                        INSERT OR IGNORE INTO sales (sale_id, product_id, customer_id, quantity_sold, sale_price, sale_date, payment_type, payment_status, deposit_amount, balance_amount, completion_date, installment_plan)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row['sale_id'], row['product_id'], row['customer_id'], int(row['quantity_sold']),
                        float(row['sale_price']), row['sale_date'], row.get('payment_type', 'cash'),
                        row.get('payment_status', 'paid'), float(row.get('deposit_amount', 0)),
                        float(row.get('balance_amount', 0)), row.get('completion_date', ''), row.get('installment_plan', '')
                    ))
        print("✅ Sales records migrated to database.")

    conn.commit()
    conn.close()
    print("🎉 Migration complete! Your data is running on the SQL engine.")

if __name__ == '__main__':
    migrate_csv_to_sqlite()
