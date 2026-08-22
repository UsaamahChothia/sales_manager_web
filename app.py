from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import csv
import os
from datetime import datetime
import json
import traceback

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Needed for flash messages

# File paths - use relative paths for PythonAnywhere
PRODUCTS_FILE = 'products.csv'
SALES_FILE = 'sales.csv'
CUSTOMERS_FILE = 'customers.csv'

# Updated field definitions with payment types
PRODUCT_FIELDS = ['product_id', 'product_name', 'stock_qty', 'cost_price', 'selling_price', 'date_added']
SALE_FIELDS = ['sale_id', 'product_id', 'customer_id', 'quantity_sold', 'sale_price', 'sale_date', 'payment_type', 'payment_status', 'deposit_amount', 'balance_amount', 'completion_date', 'installment_plan']
CUSTOMER_FIELDS = ['customer_id', 'name', 'cellphone', 'date_added']

print("🚀 Starting Furniture Management System...")
print(f"📁 Current directory: {os.getcwd()}")
print(f"📁 Files in directory: {os.listdir('.')}")

# Ensure data files exist
def initialize_files():
    print("📂 Initializing files...")
    try:
        for filename, fields in [
            (PRODUCTS_FILE, PRODUCT_FIELDS),
            (SALES_FILE, SALE_FIELDS),
            (CUSTOMERS_FILE, CUSTOMER_FIELDS)
        ]:
            print(f"Checking {filename}...")
            if not os.path.exists(filename):
                print(f"Creating {filename}...")
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()
                print(f"✅ Created {filename}")
            else:
                print(f"✅ {filename} exists")
        
        # Check templates folder
        if os.path.exists('templates'):
            print("✅ Templates folder exists")
            print(f"📁 Templates: {os.listdir('templates')}")
        else:
            print("❌ Templates folder missing!")
            
        # Upgrade existing sales file if it has old structure
        upgrade_sales_structure()
        
    except Exception as e:
        print(f"❌ Error in initialize_files: {e}")
        traceback.print_exc()

def upgrade_sales_structure():
    """Upgrade existing sales file to new structure with payment fields"""
    try:
        if os.path.exists(SALES_FILE):
            print("🔄 Checking sales file structure...")
            # Read existing sales
            existing_sales = []
            with open(SALES_FILE, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if any(row.values()):
                        existing_sales.append(row)
            
            # Check if already has new structure
            if existing_sales and 'payment_type' in existing_sales[0]:
                print("✅ Sales file already upgraded")
                return  # Already upgraded
            
            print("🔄 Upgrading sales file structure...")
            # Add new fields to existing sales
            upgraded_sales = []
            for sale in existing_sales:
                upgraded_sale = {
                    'sale_id': sale.get('sale_id', ''),
                    'product_id': sale.get('product_id', ''),
                    'customer_id': sale.get('customer_id', ''),
                    'quantity_sold': sale.get('quantity_sold', ''),
                    'sale_price': sale.get('sale_price', ''),
                    'sale_date': sale.get('sale_date', ''),
                    'payment_type': sale.get('payment_type', 'cash'),
                    'payment_status': sale.get('payment_status', 'paid'),
                    'deposit_amount': sale.get('deposit_amount', sale.get('sale_price', '0')),
                    'balance_amount': sale.get('balance_amount', '0'),
                    'completion_date': sale.get('completion_date', ''),
                    'installment_plan': sale.get('installment_plan', '')
                }
                upgraded_sales.append(upgraded_sale)
            
            # Save with new structure
            with open(SALES_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=SALE_FIELDS)
                writer.writeheader()
                for sale in upgraded_sales:
                    writer.writerow(sale)
            
            print("✅ Sales file upgraded successfully!")
    except Exception as e:
        print(f"❌ Error upgrading sales file: {e}")
        traceback.print_exc()

# --- Data Functions ---

def load_csv(filename, fieldnames):
    try:
        data = []
        if os.path.exists(filename):
            with open(filename, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f, fieldnames=fieldnames)
                next(reader)  # Skip header
                for row in reader:
                    if any(row.values()):
                        data.append(row)
        return data
    except Exception as e:
        print(f"❌ Error loading {filename}: {e}")
        return []

def save_csv(filename, fieldnames, data):
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
    except Exception as e:
        print(f"❌ Error saving {filename}: {e}")

def generate_id(prefix, existing_ids):
    num = 1
    while True:
        candidate = f"{prefix}{num:04d}"
        if candidate not in existing_ids:
            return candidate
        num += 1

# Products functions
def load_products():
    return load_csv(PRODUCTS_FILE, PRODUCT_FIELDS)

def save_products(products):
    save_csv(PRODUCTS_FILE, PRODUCT_FIELDS, products)

def add_product(product_data):
    products = load_products()
    if any(p['product_id'] == product_data['product_id'] for p in products):
        return False, "Product ID already exists"
    
    try:
        int(product_data['stock_qty'])
        float(product_data['cost_price'])
        float(product_data['selling_price'])
    except ValueError:
        return False, "Stock must be integer, prices must be numbers"
    
    products.append(product_data)
    save_products(products)
    return True, "Product added successfully"

def update_product(product_data):
    products = load_products()
    for i, p in enumerate(products):
        if p['product_id'] == product_data['product_id']:
            try:
                int(product_data['stock_qty'])
                float(product_data['cost_price'])
                float(product_data['selling_price'])
            except ValueError:
                return False, "Stock must be integer, prices must be numbers"
            
            products[i] = product_data
            save_products(products)
            return True, "Product updated successfully"
    return False, "Product not found"

def delete_product(product_id):
    products = load_products()
    new_products = [p for p in products if p['product_id'] != product_id]
    if len(new_products) == len(products):
        return False, "Product not found"
    save_products(new_products)
    return True, "Product deleted successfully"

# Enhanced Sales functions with payment types
def load_sales():
    return load_csv(SALES_FILE, SALE_FIELDS)

def save_sales(sales):
    save_csv(SALES_FILE, SALE_FIELDS, sales)

def add_sale_with_payment(sale_data):
    sales = load_sales()
    
    if any(s['sale_id'] == sale_data['sale_id'] for s in sales):
        return False, "Sale ID already exists"
    
    # Validate product and stock
    products = load_products()
    product = next((p for p in products if p['product_id'] == sale_data['product_id']), None)
    if not product:
        return False, "Product not found"
    
    # Handle different payment types
    payment_type = sale_data['payment_type']
    
    if payment_type == 'layby':
        # For layby, only reserve stock, don't reduce it completely
        try:
            deposit_amount = float(sale_data['deposit_amount'])
            sale_price = float(sale_data['sale_price'])
            if deposit_amount <= 0:
                return False, "Deposit must be positive"
            if deposit_amount >= sale_price:
                return False, "For layby, deposit must be less than total price"
        except ValueError:
            return False, "Invalid deposit amount"
        
        # Set initial layby status
        sale_data['payment_status'] = 'in_progress'
        sale_data['balance_amount'] = str(sale_price - deposit_amount)
        
    elif payment_type in ['cash', 'card']:
        # For immediate payments, reduce stock
        try:
            quantity_sold = int(sale_data['quantity_sold'])
            current_stock = int(product['stock_qty'])
            if quantity_sold > current_stock:
                return False, f"Not enough stock. Current: {current_stock}"
            product['stock_qty'] = str(current_stock - quantity_sold)
        except ValueError:
            return False, "Quantity must be integer"
        
        sale_data['payment_status'] = 'paid'
        sale_data['deposit_amount'] = sale_data['sale_price']
        sale_data['balance_amount'] = '0'
    
    # Save updated product stock
    save_products(products)
    
    sales.append(sale_data)
    save_sales(sales)
    return True, "Sale added successfully"

def process_layby_payment(sale_id, payment_amount):
    sales = load_sales()
    for sale in sales:
        if sale['sale_id'] == sale_id and sale['payment_type'] == 'layby':
            try:
                current_balance = float(sale['balance_amount'])
                payment = float(payment_amount)
                
                if payment <= 0:
                    return False, "Payment amount must be positive"
                
                new_balance = current_balance - payment
                sale['balance_amount'] = str(new_balance)
                
                if new_balance <= 0:
                    sale['payment_status'] = 'completed'
                    sale['completion_date'] = datetime.today().strftime('%Y-%m-%d')
                    # Now reduce the stock since layby is complete
                    products = load_products()
                    for product in products:
                        if product['product_id'] == sale['product_id']:
                            current_stock = int(product['stock_qty'])
                            quantity_sold = int(sale['quantity_sold'])
                            product['stock_qty'] = str(current_stock - quantity_sold)
                    save_products(products)
                
                save_sales(sales)
                return True, f"Payment processed. New balance: ${new_balance:.2f}"
                
            except ValueError:
                return False, "Invalid payment amount"
    
    return False, "Sale not found or not a layby"

def delete_sale(sale_id):
    sales = load_sales()
    new_sales = [s for s in sales if s['sale_id'] != sale_id]
    if len(new_sales) == len(sales):
        return False, "Sale not found"
    save_sales(new_sales)
    return True, "Sale deleted successfully"

# Customers functions
def load_customers():
    return load_csv(CUSTOMERS_FILE, CUSTOMER_FIELDS)

def save_customers(customers):
    save_csv(CUSTOMERS_FILE, CUSTOMER_FIELDS, customers)

def add_customer(customer_data):
    customers = load_customers()
    if any(c['customer_id'] == customer_data['customer_id'] for c in customers):
        return False, "Customer ID already exists"
    
    customers.append(customer_data)
    save_customers(customers)
    return True, "Customer added successfully"

def update_customer(customer_data):
    customers = load_customers()
    for i, c in enumerate(customers):
        if c['customer_id'] == customer_data['customer_id']:
            customers[i] = customer_data
            save_customers(customers)
            return True, "Customer updated successfully"
    return False, "Customer not found"

def delete_customer(customer_id):
    customers = load_customers()
    new_customers = [c for c in customers if c['customer_id'] != customer_id]
    if len(new_customers) == len(customers):
        return False, "Customer not found"
    save_customers(new_customers)
    return True, "Customer deleted successfully"

def get_customer_purchase_history(customer_id):
    sales = load_sales()
    return [s for s in sales if s['customer_id'] == customer_id]

# Enhanced Analytics functions for furniture business
def get_sales_summary():
    sales = load_sales()
    products = load_products()
    
    total_sales = len(sales)
    total_revenue = sum(float(s.get('sale_price', 0)) for s in sales)
    total_products = len(products)
    
    low_stock = sum(1 for p in products if int(p.get('stock_qty', 0)) < 10)
    
    return {
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'total_products': total_products,
        'low_stock': low_stock
    }

def get_furniture_business_metrics():
    sales = load_sales()
    products = load_products()
    
    metrics = {
        'total_cash_sales': 0,
        'total_card_sales': 0,
        'total_layby_sales': 0,
        'active_laybys': 0,
        'layby_balance_outstanding': 0,
        'average_sale_value': 0
    }
    
    total_revenue = 0
    total_sales_count = len(sales)
    
    for sale in sales:
        sale_price = float(sale.get('sale_price', 0))
        payment_type = sale.get('payment_type', '')
        
        if payment_type == 'cash':
            metrics['total_cash_sales'] += sale_price
        elif payment_type == 'card':
            metrics['total_card_sales'] += sale_price
        elif payment_type == 'layby':
            metrics['total_layby_sales'] += sale_price
            if sale.get('payment_status') == 'in_progress':
                metrics['active_laybys'] += 1
                metrics['layby_balance_outstanding'] += float(sale.get('balance_amount', 0))
        
        total_revenue += sale_price
    
    metrics['average_sale_value'] = total_revenue / total_sales_count if total_sales_count > 0 else 0
    
    return metrics

def get_top_products():
    sales = load_sales()
    products = load_products()
    
    product_sales = {}
    for sale in sales:
        product_id = sale['product_id']
        try:
            quantity = int(sale.get('quantity_sold', 0))
            product_sales[product_id] = product_sales.get(product_id, 0) + quantity
        except ValueError:
            continue
    
    top_products = []
    for product_id, quantity in sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]:
        product = next((p for p in products if p['product_id'] == product_id), None)
        if product:
            top_products.append({'name': product['product_name'], 'quantity': quantity})
    
    return top_products

# --- Web Routes ---

@app.route('/')
def dashboard():
    try:
        print("📊 Loading dashboard...")
        summary = get_sales_summary()
        top_products = get_top_products()
        business_metrics = get_furniture_business_metrics()
        print("✅ Dashboard data loaded successfully")
        return render_template('dashboard.html', summary=summary, top_products=top_products, metrics=business_metrics)
    except Exception as e:
        print(f"❌ Error in dashboard route: {e}")
        traceback.print_exc()
        return f"Error loading dashboard: {str(e)}", 500

# Products routes
@app.route('/products')
def products_page():
    try:
        print("📦 Loading products page...")
        products = load_products()
        print(f"✅ Loaded {len(products)} products")
        return render_template('products.html', products=products)
    except Exception as e:
        print(f"❌ Error in products route: {e}")
        traceback.print_exc()
        return f"Error loading products: {str(e)}", 500

@app.route('/api/products/add', methods=['POST'])
def api_add_product():
    try:
        data = request.json
        product_id = data.get('product_id', '').strip()
        
        if not product_id:
            existing_ids = [p['product_id'] for p in load_products()]
            product_id = generate_id("P", existing_ids)
        
        product_data = {
            'product_id': product_id,
            'product_name': data['product_name'],
            'stock_qty': data['stock_qty'],
            'cost_price': data['cost_price'],
            'selling_price': data['selling_price'],
            'date_added': datetime.today().strftime('%Y-%m-%d')
        }
        
        success, message = add_product(product_data)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        print(f"❌ Error in api_add_product: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/products/update', methods=['POST'])
def api_update_product():
    data = request.json
    product_data = {
        'product_id': data['product_id'],
        'product_name': data['product_name'],
        'stock_qty': data['stock_qty'],
        'cost_price': data['cost_price'],
        'selling_price': data['selling_price'],
        'date_added': datetime.today().strftime('%Y-%m-%d')
    }
    
    success, message = update_product(product_data)
    return jsonify({'success': success, 'message': message})

@app.route('/api/products/delete/<product_id>', methods=['DELETE'])
def api_delete_product(product_id):
    success, message = delete_product(product_id)
    return jsonify({'success': success, 'message': message})

# Enhanced Sales routes with payment types
@app.route('/sales')
def sales_page():
    try:
        print("💰 Loading sales page...")
        sales = load_sales()
        products = load_products()
        customers = load_customers()
        print(f"✅ Loaded {len(sales)} sales, {len(products)} products, {len(customers)} customers")
        return render_template('sales.html', sales=sales, products=products, customers=customers)
    except Exception as e:
        print(f"❌ Error in sales route: {e}")
        traceback.print_exc()
        return f"Error loading sales: {str(e)}", 500

@app.route('/api/sales/add', methods=['POST'])
def api_add_sale():
    data = request.json
    sale_id = data.get('sale_id', '').strip()
    
    if not sale_id:
        existing_ids = [s['sale_id'] for s in load_sales()]
        sale_id = generate_id("S", existing_ids)
    
    sale_data = {
        'sale_id': sale_id,
        'product_id': data['product_id'],
        'customer_id': data['customer_id'],
        'quantity_sold': data['quantity_sold'],
        'sale_price': data['sale_price'],
        'sale_date': data.get('sale_date') or datetime.today().strftime('%Y-%m-%d'),
        'payment_type': data['payment_type'],
        'payment_status': 'paid',  # Will be updated in add_sale_with_payment
        'deposit_amount': data.get('deposit_amount', data['sale_price']),
        'balance_amount': '0',  # Will be updated in add_sale_with_payment
        'completion_date': '',
        'installment_plan': data.get('installment_plan', '')
    }
    
    success, message = add_sale_with_payment(sale_data)
    return jsonify({'success': success, 'message': message})

@app.route('/api/sales/delete/<sale_id>', methods=['DELETE'])
def api_delete_sale(sale_id):
    success, message = delete_sale(sale_id)
    return jsonify({'success': success, 'message': message})

# Layby management routes
@app.route('/api/layby/payment', methods=['POST'])
def api_process_layby_payment():
    data = request.json
    success, message = process_layby_payment(data['sale_id'], data['payment_amount'])
    return jsonify({'success': success, 'message': message})

@app.route('/api/layby/overdue')
def api_get_overdue_laybys():
    sales = load_sales()
    overdue_laybys = []
    
    for sale in sales:
        if sale['payment_type'] == 'layby' and sale['payment_status'] == 'in_progress':
            overdue_laybys.append(sale)
    
    return jsonify(overdue_laybys)

# Customers routes
@app.route('/customers')
def customers_page():
    try:
        print("👥 Loading customers page...")
        customers = load_customers()
        print(f"✅ Loaded {len(customers)} customers")
        return render_template('customers.html', customers=customers)
    except Exception as e:
        print(f"❌ Error in customers route: {e}")
        traceback.print_exc()
        return f"Error loading customers: {str(e)}", 500

@app.route('/api/customers/add', methods=['POST'])
def api_add_customer():
    data = request.json
    customer_id = data.get('customer_id', '').strip()
    
    if not customer_id:
        existing_ids = [c['customer_id'] for c in load_customers()]
        customer_id = generate_id("C", existing_ids)
    
    customer_data = {
        'customer_id': customer_id,
        'name': data['name'],
        'cellphone': data['cellphone'],
        'date_added': datetime.today().strftime('%Y-%m-%d')
    }
    
    success, message = add_customer(customer_data)
    return jsonify({'success': success, 'message': message})

@app.route('/api/customers/update', methods=['POST'])
def api_update_customer():
    data = request.json
    customer_data = {
        'customer_id': data['customer_id'],
        'name': data['name'],
        'cellphone': data['cellphone'],
        'date_added': datetime.today().strftime('%Y-%m-%d')
    }
    
    success, message = update_customer(customer_data)
    return jsonify({'success': success, 'message': message})

@app.route('/api/customers/delete/<customer_id>', methods=['DELETE'])
def api_delete_customer(customer_id):
    success, message = delete_customer(customer_id)
    return jsonify({'success': success, 'message': message})

@app.route('/api/customers/<customer_id>/history')
def api_customer_history(customer_id):
    history = get_customer_purchase_history(customer_id)
    return jsonify(history)

@app.route('/api/admin/clear-data', methods=['POST'])
def clear_all_data():
    """Wipes all CSV data files and re-initializes headers"""
    try:
        print("⚠️ Admin: Clearing all data files...")
        files_to_reset = [
            (PRODUCTS_FILE, PRODUCT_FIELDS),
            (SALES_FILE, SALE_FIELDS),
            (CUSTOMERS_FILE, CUSTOMER_FIELDS)
        ]
        
        for filename, fields in files_to_reset:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
            print(f"✅ Reset {filename}")
        
        flash("All system data has been cleared successfully!", "warning")
    except Exception as e:
        print(f"❌ Error clearing data: {e}")
        flash(f"Error clearing data: {str(e)}", "danger")
        
    return redirect(url_for('dashboard'))      

if __name__ == '__main__':
    try:
        print("🚀 Starting Furniture Management System...")
        initialize_files()
        
        port = int(os.environ.get('PORT', 5000))
        print(f"🌐 Starting server on port {port}...")
        
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=True  # Kept on True for your local development setup
        )
    except Exception as e:
        print(f"❌ Fatal error starting app: {e}")
        traceback.print_exc()
