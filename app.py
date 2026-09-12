from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import os
import json
from datetime import datetime
import traceback
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import (
    get_master_connection,
    get_db_connection,
    seed_initial_tenants
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'furniture-secret-key-prod-99')

# --- SMTP Email Configuration ---
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
MAIL_SENDER = os.environ.get('MAIL_SENDER', SMTP_USER or 'noreply@business.co.za')

# --- Security & Authentication Setup ---
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please sign in to access your company portal.'
login_manager.login_message_category = 'warning'

class User(UserMixin):
    def __init__(self, id, username, role, company_id, company_name, db_name):
        self.id = id
        self.username = username
        self.role = role
        self.company_id = company_id
        self.company_name = company_name
        self.db_name = db_name

@login_manager.user_loader
def load_user(user_id):
    conn = get_master_connection()
    user_row = conn.execute('''
        SELECT u.id, u.username, u.role, u.company_id, c.company_name, c.db_name
        FROM users u
        JOIN companies c ON u.company_id = c.id
        WHERE u.id = ?
    ''', (user_id,)).fetchone()
    conn.close()

    if user_row:
        return User(
            id=user_row['id'],
            username=user_row['username'],
            role=user_row['role'],
            company_id=user_row['company_id'],
            company_name=user_row['company_name'],
            db_name=user_row['db_name']
        )
    return None

def get_request_data():
    """Extracts payload without throwing Flask 415 exceptions."""
    data = {}
    raw_body = request.get_data(as_text=True)
    if raw_body:
        try:
            data = json.loads(raw_body)
        except Exception:
            data = {}
    
    if not data and request.form:
        data = request.form.to_dict()
        
    return data

def generate_id(prefix, table, id_column):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {id_column} FROM {table}")
    existing_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    num = 1
    while True:
        candidate = f"{prefix}{num:04d}"
        if candidate not in existing_ids:
            return candidate
        num += 1

def send_receipt_email(recipient_email, sale, customer, product):
    """Dispatches a formatted receipt via standard SMTP."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "SMTP credentials are not configured on this server."

    subject = f"Your Receipt #{sale['sale_id']} - {current_user.company_name}"
    
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 25px; border-radius: 8px;">
        <h2 style="color: #2a5298; margin-top: 0;">{current_user.company_name}</h2>
        <p style="color: #555;">Hi {customer['name']},</p>
        <p style="color: #555;">Thank you for your transaction. Here is your official payment record:</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background: #f8f9fa;">
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Invoice ID</th>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{sale['sale_id']}</td>
            </tr>
            <tr>
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Date</th>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{sale['sale_date']}</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Item Purchased</th>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{product['product_name']} (Qty: {sale['quantity_sold']})</td>
            </tr>
            <tr>
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Total Price</th>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><strong>R {float(sale['sale_price']):.2f}</strong></td>
            </tr>
            <tr style="background: #f8f9fa;">
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Amount Paid</th>
                <td style="padding: 10px; border: 1px solid #dee2e6; color: green;"><strong>R {float(sale['deposit_amount']):.2f}</strong></td>
            </tr>
            <tr>
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Outstanding Balance</th>
                <td style="padding: 10px; border: 1px solid #dee2e6; color: {'red' if float(sale['balance_amount']) > 0 else 'black'};">
                    <strong>R {float(sale['balance_amount']):.2f}</strong>
                </td>
            </tr>
            <tr style="background: #f8f9fa;">
                <th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Payment Status</th>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{sale['payment_status'].replace('_', ' ').upper()}</td>
            </tr>
        </table>
        
        <p style="font-size: 0.85em; color: #888;">Thank you for shopping with {current_user.company_name}!</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = MAIL_SENDER
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_SENDER, recipient_email, msg.as_string())
        return True, f"Receipt successfully sent to {recipient_email}!"
    except Exception as e:
        return False, f"SMTP Error: {str(e)}"

# --- Authentication Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_master_connection()
        user_row = conn.execute('''
            SELECT u.*, c.company_name, c.db_name 
            FROM users u
            JOIN companies c ON u.company_id = c.id
            WHERE u.username = ?
        ''', (username,)).fetchone()
        conn.close()

        if user_row and bcrypt.check_password_hash(user_row['password_hash'], password):
            user = User(
                id=user_row['id'],
                username=user_row['username'],
                role=user_row['role'],
                company_id=user_row['company_id'],
                company_name=user_row['company_name'],
                db_name=user_row['db_name']
            )
            login_user(user)
            flash(f"Logged into {user.company_name} as {user.username}!", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Invalid username or password. Please try again.", "danger")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for('login'))

# --- Protected Web Page Routes ---

@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    try:
        sales = conn.execute("SELECT * FROM sales").fetchall()
        products = conn.execute("SELECT * FROM products").fetchall()
        
        total_sales = len(sales)
        total_revenue = sum(float(s['sale_price']) for s in sales if s['payment_status'] in ['paid', 'completed'])
        total_products = len(products)
        low_stock = sum(1 for p in products if int(p['stock_qty']) < 5)
        
        summary = {
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_products': total_products,
            'low_stock': low_stock
        }

        total_cash = sum(float(s['sale_price']) for s in sales if s['payment_type'] == 'cash')
        total_card = sum(float(s['sale_price']) for s in sales if s['payment_type'] == 'card')
        total_layby = sum(float(s['sale_price']) for s in sales if s['payment_type'] == 'layby')
        active_laybys = sum(1 for s in sales if s['payment_type'] == 'layby' and s['payment_status'] == 'in_progress')
        layby_balance_due = sum(float(s['balance_amount']) for s in sales if s['payment_status'] == 'in_progress')
        
        avg_sale = (total_revenue / total_sales) if total_sales > 0 else 0.0

        metrics = {
            'total_cash_sales': total_cash,
            'total_card_sales': total_card,
            'total_layby_sales': total_layby,
            'active_laybys': active_laybys,
            'layby_balance_outstanding': layby_balance_due,
            'average_sale_value': avg_sale
        }

        top_products_query = '''
            SELECT p.product_name, SUM(s.quantity_sold) as total_qty
            FROM sales s
            JOIN products p ON s.product_id = p.product_id
            GROUP BY s.product_id
            ORDER BY total_qty DESC
            LIMIT 5
        '''
        top_products = conn.execute(top_products_query).fetchall()

        return render_template('dashboard.html', summary=summary, top_products=top_products, metrics=metrics)
    except Exception as e:
        traceback.print_exc()
        return f"Error loading dashboard: {str(e)}", 500
    finally:
        conn.close()

@app.route('/products')
@login_required
def products_page():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products ORDER BY date_added DESC").fetchall()
    conn.close()
    return render_template('products.html', products=products)

@app.route('/sales')
@login_required
def sales_page():
    conn = get_db_connection()
    sales_query = '''
        SELECT s.*, p.product_name, c.name as customer_name, c.email as customer_email
        FROM sales s
        LEFT JOIN products p ON s.product_id = p.product_id
        LEFT JOIN customers c ON s.customer_id = c.customer_id
        ORDER BY s.sale_date DESC
    '''
    sales = conn.execute(sales_query).fetchall()
    products = conn.execute("SELECT * FROM products WHERE stock_qty > 0 ORDER BY product_name ASC").fetchall()
    customers = conn.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
    conn.close()
    return render_template('sales.html', sales=sales, products=products, customers=customers)

@app.route('/sales/<sale_id>/receipt')
@login_required
def view_receipt(sale_id):
    conn = get_db_connection()
    try:
        sale = conn.execute("SELECT * FROM sales WHERE sale_id = ?", (sale_id,)).fetchone()
        if not sale:
            flash("Sale record not found.", "danger")
            return redirect(url_for('sales_page'))

        customer = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (sale['customer_id'],)).fetchone()
        product = conn.execute("SELECT * FROM products WHERE product_id = ?", (sale['product_id'],)).fetchone()

        qty = max(1, int(sale['quantity_sold'] or 1))
        tot_price = float(sale['sale_price'] or 0.0)
        u_price = tot_price / qty
        dep = float(sale['deposit_amount'] or 0.0)
        bal = float(sale['balance_amount'] or 0.0)

        plan = str(sale['installment_plan'] or '').replace('_', ' ').title()
        status = str(sale['payment_status'] or 'COMPLETED').replace('_', ' ').upper()
        pay_type = str(sale['payment_type'] or 'CASH').upper()

        return render_template(
            'receipt.html',
            company_name=current_user.company_name,
            sale_id=sale['sale_id'],
            sale_date=sale['sale_date'],
            customer_name=customer['name'] if customer else 'Unknown Customer',
            customer_cell=customer['cellphone'] if customer else 'N/A',
            customer_email=customer['email'] if (customer and customer['email']) else '',
            product_name=product['product_name'] if product else 'Standard Item',
            quantity=qty,
            unit_price=f"{u_price:.2f}",
            total_price=f"{tot_price:.2f}",
            deposit_paid=f"{dep:.2f}",
            balance_due=f"{bal:.2f}",
            status_display=status,
            payment_type=pay_type,
            installment_plan=plan
        )
    except Exception as e:
        traceback.print_exc()
        return f"Error loading receipt: {str(e)}", 500
    finally:
        conn.close()

@app.route('/customers')
@login_required
def customers_page():
    conn = get_db_connection()
    customers = conn.execute("SELECT * FROM customers ORDER BY date_added DESC").fetchall()
    conn.close()
    return render_template('customers.html', customers=customers)

# --- Protected API Endpoints ---

@app.route('/api/sales/<sale_id>/email-receipt', methods=['POST'])
@login_required
def api_email_receipt(sale_id):
    conn = get_db_connection()
    sale = conn.execute("SELECT * FROM sales WHERE sale_id = ?", (sale_id,)).fetchone()
    if not sale:
        conn.close()
        return jsonify({'success': False, 'message': 'Sale not found.'}), 404

    customer = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (sale['customer_id'],)).fetchone()
    product = conn.execute("SELECT * FROM products WHERE product_id = ?", (sale['product_id'],)).fetchone()
    conn.close()

    if not customer or not customer['email']:
        return jsonify({'success': False, 'message': 'This customer does not have an email address on record.'}), 400

    cust_data = {
        'name': customer['name'],
        'cellphone': customer['cellphone'],
        'email': customer['email']
    }
    prod_data = {
        'product_name': product['product_name'] if product else 'Archived Item'
    }

    success, message = send_receipt_email(customer['email'], sale, cust_data, prod_data)
    return jsonify({'success': success, 'message': message})

# 1. Product APIs
@app.route('/api/products/add', methods=['POST'])
@login_required
def api_add_product():
    data = get_request_data()

    product_id = data.get('product_id', '').strip() if data.get('product_id') else ''
    name = data.get('product_name', '').strip() if data.get('product_name') else ''
    
    try:
        stock_qty = int(data.get('stock_qty', 0))
        cost_price = float(data.get('cost_price', 0))
        selling_price = float(data.get('selling_price', 0))
        
        if stock_qty < 0 or cost_price < 0 or selling_price < 0:
            return jsonify({'success': False, 'message': 'Stock and prices must be non-negative values.'}), 400
            
        if not product_id:
            product_id = generate_id("P", "products", "product_id")

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO products (product_id, product_name, stock_qty, cost_price, selling_price, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_id, name, stock_qty, cost_price, selling_price, datetime.today().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Product added successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Product ID already exists.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products/delete/<product_id>', methods=['DELETE'])
@login_required
def api_delete_product(product_id):
    conn = get_db_connection()
    try:
        sale_exists = conn.execute("SELECT 1 FROM sales WHERE product_id = ?", (product_id,)).fetchone()
        if sale_exists:
            return jsonify({'success': False, 'message': 'Cannot delete: this product has existing sales records.'}), 400

        cursor = conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Product not found.'}), 404
        return jsonify({'success': True, 'message': 'Product deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# 2. Sales & Layby APIs
@app.route('/api/sales/add', methods=['POST'])
@login_required
def api_add_sale():
    data = get_request_data()

    product_id = data.get('product_id')
    customer_id = data.get('customer_id')
    payment_type = data.get('payment_type')
    installment_plan = data.get('installment_plan', '')
    
    try:
        qty_sold = int(data.get('quantity_sold', 1))
        unit_price = float(data.get('sale_price', 0))
        total_sale_price = unit_price * qty_sold
        sale_id = data.get('sale_id', '').strip() or generate_id("S", "sales", "sale_id")
        sale_date = data.get('sale_date') or datetime.today().strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid numeric values for price or quantity.'}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        product = conn.execute("SELECT stock_qty FROM products WHERE product_id = ?", (product_id,)).fetchone()
        
        if not product:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Product not found.'}), 404
            
        if product['stock_qty'] < qty_sold:
            conn.rollback()
            return jsonify({'success': False, 'message': f"Insufficient stock. On hand: {product['stock_qty']}"}), 400

        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE product_id = ?", (qty_sold, product_id))

        if payment_type == 'layby':
            deposit = float(data.get('deposit_amount', 0))
            if deposit <= 0 or deposit >= total_sale_price:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Layby deposit must be greater than 0 and less than total price.'}), 400
                
            balance = total_sale_price - deposit
            status = 'in_progress'
            completion_date = None
        else:
            deposit = total_sale_price
            balance = 0.0
            status = 'paid'
            completion_date = sale_date

        conn.execute('''
            INSERT INTO sales (sale_id, product_id, customer_id, quantity_sold, sale_price, sale_date, 
                               payment_type, payment_status, deposit_amount, balance_amount, completion_date, installment_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sale_id, product_id, customer_id, qty_sold, total_sale_price, sale_date,
              payment_type, status, deposit, balance, completion_date, installment_plan))

        conn.commit()
        return jsonify({'success': True, 'sale_id': sale_id, 'message': 'Sale processed successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/layby/payment', methods=['POST'])
@login_required
def api_process_layby_payment():
    data = get_request_data()
    sale_id = data.get('sale_id')
    
    try:
        payment = float(data.get('payment_amount', 0))
        if payment <= 0:
            return jsonify({'success': False, 'message': 'Payment must be greater than 0.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid payment amount.'}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        sale = conn.execute("SELECT * FROM sales WHERE sale_id = ? AND payment_type = 'layby'", (sale_id,)).fetchone()
        
        if not sale:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Active layby record not found.'}), 404
            
        if sale['payment_status'] == 'completed':
            conn.rollback()
            return jsonify({'success': False, 'message': 'This layby agreement is already fully settled.'}), 400

        new_balance = max(0.0, float(sale['balance_amount']) - payment)
        new_deposit = float(sale['deposit_amount']) + payment
        
        if new_balance == 0:
            new_status = 'completed'
            completion_date = datetime.today().strftime('%Y-%m-%d')
        else:
            new_status = 'in_progress'
            completion_date = sale['completion_date']

        conn.execute('''
            UPDATE sales 
            SET balance_amount = ?, deposit_amount = ?, payment_status = ?, completion_date = ?
            WHERE sale_id = ?
        ''', (new_balance, new_deposit, new_status, completion_date, sale_id))

        conn.commit()
        return jsonify({
            'success': True, 
            'message': f"Payment of R{payment:.2f} logged. Remaining Balance: R{new_balance:.2f}"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/sales/delete/<sale_id>', methods=['DELETE'])
@login_required
def api_delete_sale(sale_id):
    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        sale = conn.execute("SELECT product_id, quantity_sold, payment_status FROM sales WHERE sale_id = ?", (sale_id,)).fetchone()
        if not sale:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Sale not found.'}), 404

        conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE product_id = ?", 
                     (sale['quantity_sold'], sale['product_id']))
        
        conn.execute("DELETE FROM sales WHERE sale_id = ?", (sale_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Sale reversed and stock returned to inventory.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# 3. Customer APIs
@app.route('/api/customers/add', methods=['POST'])
@login_required
def api_add_customer():
    data = get_request_data()

    customer_id = data.get('customer_id', '').strip() if data.get('customer_id') else generate_id("C", "customers", "customer_id")
    name = data.get('name', '').strip() if data.get('name') else ''
    cellphone = (data.get('cellphone') or data.get('phone') or '').strip()
    email = data.get('email', '').strip() if data.get('email') else ''

    is_ajax = bool(request.get_data(as_text=True)) and not bool(request.form)

    if not name or not cellphone:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Name and Cellphone are required.'}), 400
        flash('Name and Cellphone are required.', 'danger')
        return redirect(url_for('customers_page'))

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO customers (customer_id, name, cellphone, email, date_added)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer_id, name, cellphone, email, datetime.today().strftime('%Y-%m-%d')))
        conn.commit()

        if is_ajax:
            return jsonify({'success': True, 'message': 'Customer registered successfully!'})
        
        flash('Customer registered successfully!', 'success')
        return redirect(url_for('customers_page'))
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Error adding customer: {str(e)}', 'danger')
        return redirect(url_for('customers_page'))
    finally:
        conn.close()

@app.route('/api/customers/delete/<customer_id>', methods=['DELETE'])
@login_required
def api_delete_customer(customer_id):
    conn = get_db_connection()
    try:
        sale_exists = conn.execute("SELECT 1 FROM sales WHERE customer_id = ?", (customer_id,)).fetchone()
        if sale_exists:
            return jsonify({'success': False, 'message': 'Cannot delete: Customer has linked sales records.'}), 400
            
        cursor = conn.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Customer not found.'}), 404
        return jsonify({'success': True, 'message': 'Customer record deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    seed_initial_tenants(bcrypt)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False, threaded=True)