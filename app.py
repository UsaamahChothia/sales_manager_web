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
    seed_initial_tenants,
    register_new_company,
    init_master_db,
    delete_company_by_id
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'furniture-restaurant-pos-secret-99')

# --- SMTP Email Configuration ---
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
MAIL_SENDER = os.environ.get('MAIL_SENDER', SMTP_USER or 'noreply@pos.co.za')

# --- Security & Authentication Setup ---
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please sign in to access your business portal.'
login_manager.login_message_category = 'warning'

class User(UserMixin):
    def __init__(self, id, username, role, company_id, company_name, db_name, business_type):
        self.id = id
        self.username = username
        self.role = role
        self.company_id = company_id
        self.company_name = company_name
        self.db_name = db_name
        self.business_type = business_type or 'retail'

@login_manager.user_loader
def load_user(user_id):
    conn = get_master_connection()
    user_row = conn.execute('''
        SELECT u.id, u.username, u.role, u.company_id, c.company_name, c.db_name, c.business_type
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
            db_name=user_row['db_name'],
            business_type=user_row['business_type']
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

    subject = f"Receipt #{sale['sale_id']} - {current_user.company_name}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 25px; border-radius: 8px;">
        <h2 style="color: #2a5298; margin-top: 0;">{current_user.company_name}</h2>
        <p style="color: #555;">Hi {customer['name']},</p>
        <p style="color: #555;">Thank you for your order. Here is your payment receipt:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background: #f8f9fa;"><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Invoice ID</th><td style="padding: 10px; border: 1px solid #dee2e6;">{sale['sale_id']}</td></tr>
            <tr><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Date</th><td style="padding: 10px; border: 1px solid #dee2e6;">{sale['sale_date']}</td></tr>
            <tr style="background: #f8f9fa;"><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Item</th><td style="padding: 10px; border: 1px solid #dee2e6;">{product['product_name']} (Qty: {sale['quantity_sold']})</td></tr>
            <tr><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Total</th><td style="padding: 10px; border: 1px solid #dee2e6;"><strong>R {float(sale['sale_price']):.2f}</strong></td></tr>
            <tr style="background: #f8f9fa;"><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Amount Paid</th><td style="padding: 10px; border: 1px solid #dee2e6; color: green;"><strong>R {float(sale['deposit_amount']):.2f}</strong></td></tr>
            <tr><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Balance</th><td style="padding: 10px; border: 1px solid #dee2e6; color: {'red' if float(sale['balance_amount']) > 0 else 'black'};"><strong>R {float(sale['balance_amount']):.2f}</strong></td></tr>
            <tr style="background: #f8f9fa;"><th style="padding: 10px; border: 1px solid #dee2e6; text-align: left;">Payment Method</th><td style="padding: 10px; border: 1px solid #dee2e6;">{sale['payment_type'].upper()}</td></tr>
        </table>
        <p style="font-size: 0.85em; color: #888;">Thank you for your patronage with {current_user.company_name}!</p>
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
        return True, f"Receipt sent to {recipient_email}!"
    except Exception as e:
        return False, f"SMTP Error: {str(e)}"

# --- Auth Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_master_connection()
        user_row = conn.execute('''
            SELECT u.*, c.company_name, c.db_name, c.business_type 
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
                db_name=user_row['db_name'],
                business_type=user_row['business_type']
            )
            login_user(user)
            flash(f"Welcome back! Logged into {user.company_name}.", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Invalid username or password.", "danger")

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        business_type = request.form.get('business_type', 'retail').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not company_name or not username or not password:
            flash("All fields are required.", "danger")
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('register.html')

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_template('register.html')

        success, message = register_new_company(company_name, username, password, business_type, bcrypt)
        if success:
            flash(f"Account for {company_name} provisioned! You may now sign in.", "success")
            return redirect(url_for('login'))
        else:
            flash(message, "danger")

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

@app.route('/company/delete', methods=['POST'])
@login_required
def delete_current_company():
    company_id = current_user.company_id
    company_name = current_user.company_name

    logout_user()
    success, message = delete_company_by_id(company_id)

    if success:
        flash(f"Company '{company_name}' and all associated records have been permanently deleted.", "info")
    else:
        flash(f"Error deleting company: {message}", "danger")

    return redirect(url_for('register'))

# --- Main Views ---

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

        top_products = conn.execute('''
            SELECT p.product_name, SUM(s.quantity_sold) as total_qty
            FROM sales s
            JOIN products p ON s.product_id = p.product_id
            GROUP BY s.product_id
            ORDER BY total_qty DESC
            LIMIT 5
        ''').fetchall()

        # Low stock ingredients for restaurant (<500g, <500ml, or <5 units)
        low_ingredients = []
        if current_user.business_type == 'restaurant':
            low_ingredients = conn.execute('''
                SELECT * FROM ingredients 
                WHERE (unit IN ('g', 'ml') AND stock_qty < 500) 
                   OR (unit = 'units' AND stock_qty < 5) 
                ORDER BY stock_qty ASC
            ''').fetchall()

        return render_template('dashboard.html', summary=summary, top_products=top_products, metrics=metrics, low_ingredients=low_ingredients)
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
    ingredients = []
    if current_user.business_type == 'restaurant':
        ingredients = conn.execute("SELECT * FROM ingredients ORDER BY name ASC").fetchall()
    conn.close()
    return render_template('products.html', products=products, ingredients=ingredients)

@app.route('/ingredients')
@login_required
def ingredients_page():
    if current_user.business_type != 'restaurant':
        flash("Ingredients portal is only active for restaurant accounts.", "info")
        return redirect(url_for('products_page'))
    conn = get_db_connection()
    ingredients = conn.execute("SELECT * FROM ingredients ORDER BY name ASC").fetchall()
    conn.close()
    return render_template('ingredients.html', ingredients=ingredients)

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
    
    if current_user.business_type == 'restaurant':
        products = conn.execute("SELECT * FROM products ORDER BY product_name ASC").fetchall()
    else:
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
            customer_name=customer['name'] if customer else 'Counter Customer',
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

# --- API Endpoints ---

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
        return jsonify({'success': False, 'message': 'Customer does not have an email on file.'}), 400

    cust_data = {'name': customer['name'], 'cellphone': customer['cellphone'], 'email': customer['email']}
    prod_data = {'product_name': product['product_name'] if product else 'Archived Item'}

    success, message = send_receipt_email(customer['email'], sale, cust_data, prod_data)
    return jsonify({'success': success, 'message': message})

# 1. Product & Recipe APIs
@app.route('/api/products/add', methods=['POST'])
@login_required
def api_add_product():
    data = get_request_data()
    product_id = data.get('product_id', '').strip() if data.get('product_id') else ''
    name = data.get('product_name', '').strip() if data.get('product_name') else ''
    
    try:
        stock_qty = int(data.get('stock_qty', 0)) if current_user.business_type == 'retail' else 0
        cost_price = float(data.get('cost_price', 0))
        selling_price = float(data.get('selling_price', 0))
        
        if cost_price < 0 or selling_price < 0:
            return jsonify({'success': False, 'message': 'Prices must be non-negative.'}), 400
            
        if not product_id:
            product_id = generate_id("P", "products", "product_id")

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO products (product_id, product_name, stock_qty, cost_price, selling_price, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_id, name, stock_qty, cost_price, selling_price, datetime.today().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Menu item/Product registered!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Item ID already exists.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products/delete/<product_id>', methods=['DELETE'])
@login_required
def api_delete_product(product_id):
    conn = get_db_connection()
    try:
        sale_exists = conn.execute("SELECT 1 FROM sales WHERE product_id = ?", (product_id,)).fetchone()
        if sale_exists:
            return jsonify({'success': False, 'message': 'Cannot delete: Item has linked transactions.'}), 400

        conn.execute("DELETE FROM product_recipes WHERE product_id = ?", (product_id,))
        cursor = conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Product not found.'}), 404
        return jsonify({'success': True, 'message': 'Product deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# Recipe Management (Restaurant Mode)
@app.route('/api/products/<product_id>/recipe', methods=['GET', 'POST'])
@login_required
def api_product_recipe(product_id):
    conn = get_db_connection()
    if request.method == 'GET':
        recipe = conn.execute('''
            SELECT pr.id, pr.ingredient_id, i.name as ingredient_name, i.unit, pr.qty_required, i.cost_per_unit
            FROM product_recipes pr
            JOIN ingredients i ON pr.ingredient_id = i.ingredient_id
            WHERE pr.product_id = ?
        ''', (product_id,)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in recipe])

    if request.method == 'POST':
        data = get_request_data()
        items = data.get('recipe', [])
        try:
            conn.execute("BEGIN TRANSACTION;")
            conn.execute("DELETE FROM product_recipes WHERE product_id = ?", (product_id,))
            calculated_cost = 0.0
            
            for item in items:
                ing_id = item.get('ingredient_id')
                qty = float(item.get('qty_required', 0))
                if qty > 0 and ing_id:
                    conn.execute('''
                        INSERT INTO product_recipes (product_id, ingredient_id, qty_required)
                        VALUES (?, ?, ?)
                    ''', (product_id, ing_id, qty))
                    ing = conn.execute("SELECT cost_per_unit FROM ingredients WHERE ingredient_id = ?", (ing_id,)).fetchone()
                    if ing:
                        calculated_cost += (float(ing['cost_per_unit']) * qty)

            conn.execute("UPDATE products SET cost_price = ? WHERE product_id = ?", (calculated_cost, product_id))
            conn.commit()
            return jsonify({'success': True, 'message': 'Recipe updated and dish cost calculated!', 'cost': calculated_cost})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conn.close()

# 2. Dual-Unit Ingredient APIs (Pantry Conversion Engine)
@app.route('/api/ingredients/add', methods=['POST'])
@login_required
def api_add_ingredient():
    data = get_request_data()
    ing_id = data.get('ingredient_id', '').strip() or generate_id("ING", "ingredients", "ingredient_id")
    name = data.get('name', '').strip()
    purchased_unit = data.get('unit', 'units').strip().lower()
    
    try:
        raw_qty = float(data.get('stock_qty', 0))
        total_cost = float(data.get('total_cost', 0))
        
        if raw_qty <= 0 or total_cost < 0:
            return jsonify({'success': False, 'message': 'Quantity must be positive and cost non-negative.'}), 400

        # Normalization to base units (g, ml, units)
        if purchased_unit == 'kg':
            base_qty = raw_qty * 1000.0
            base_unit = 'g'
        elif purchased_unit == 'l':
            base_qty = raw_qty * 1000.0
            base_unit = 'ml'
        elif purchased_unit == 'g':
            base_qty = raw_qty
            base_unit = 'g'
        elif purchased_unit == 'ml':
            base_qty = raw_qty
            base_unit = 'ml'
        else:
            base_qty = raw_qty
            base_unit = 'units'

        cost_per_base_unit = total_cost / base_qty

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO ingredients (ingredient_id, name, unit, stock_qty, cost_per_unit, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ing_id, name, base_unit, base_qty, cost_per_base_unit, datetime.today().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f"Added {name} ({base_qty:.1f} {base_unit} at R{cost_per_base_unit:.4f}/{base_unit})"})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Ingredient ID already registered.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/ingredients/adjust', methods=['POST'])
@login_required
def api_adjust_ingredient_stock():
    data = get_request_data()
    ingredient_id = data.get('ingredient_id')
    reason = data.get('reason', 'manual_adjustment')
    
    try:
        qty_change = float(data.get('quantity_change', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid adjustment quantity.'}), 400

    if qty_change == 0:
        return jsonify({'success': False, 'message': 'Adjustment quantity cannot be zero.'}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        item = conn.execute("SELECT stock_qty, name, unit FROM ingredients WHERE ingredient_id = ?", (ingredient_id,)).fetchone()
        if not item:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Ingredient not found.'}), 404

        new_stock = item['stock_qty'] + qty_change
        if new_stock < 0:
            conn.rollback()
            return jsonify({'success': False, 'message': f"Cannot adjust below zero. Current: {item['stock_qty']:.2f} {item['unit']}"}), 400

        conn.execute("UPDATE ingredients SET stock_qty = ? WHERE ingredient_id = ?", (new_stock, ingredient_id))
        conn.commit()
        return jsonify({
            'success': True,
            'message': f"Updated {item['name']}. Current stock: {new_stock:.2f} {item['unit']} ({reason.replace('_', ' ').title()})"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/ingredients/delete/<ingredient_id>', methods=['DELETE'])
@login_required
def api_delete_ingredient(ingredient_id):
    conn = get_db_connection()
    try:
        in_use = conn.execute("SELECT 1 FROM product_recipes WHERE ingredient_id = ?", (ingredient_id,)).fetchone()
        if in_use:
            return jsonify({'success': False, 'message': 'Cannot delete: Ingredient is active in menu item recipes.'}), 400

        cursor = conn.execute("DELETE FROM ingredients WHERE ingredient_id = ?", (ingredient_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Ingredient not found.'}), 404
        return jsonify({'success': True, 'message': 'Ingredient purged.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# 3. Dynamic POS Sale API (Portion Depletion vs Retail Depletion)
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
        return jsonify({'success': False, 'message': 'Invalid numeric price or quantity.'}), 400

    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION;")
        product = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        if not product:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Product/Dish not found.'}), 404

        # Depletion Logic
        if current_user.business_type == 'restaurant':
            recipe_items = conn.execute('''
                SELECT pr.ingredient_id, pr.qty_required, i.name, i.stock_qty, i.unit
                FROM product_recipes pr
                JOIN ingredients i ON pr.ingredient_id = i.ingredient_id
                WHERE pr.product_id = ?
            ''', (product_id,)).fetchall()

            for item in recipe_items:
                needed = item['qty_required'] * qty_sold
                if item['stock_qty'] < needed:
                    conn.rollback()
                    return jsonify({
                        'success': False, 
                        'message': f"Insufficient ingredient: '{item['name']}'. Needed: {needed:.1f} {item['unit']}, In stock: {item['stock_qty']:.1f} {item['unit']}"
                    }), 400
                conn.execute("UPDATE ingredients SET stock_qty = stock_qty - ? WHERE ingredient_id = ?", 
                             (needed, item['ingredient_id']))
        else:
            if product['stock_qty'] < qty_sold:
                conn.rollback()
                return jsonify({'success': False, 'message': f"Insufficient stock. Available: {product['stock_qty']}"}), 400
            conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE product_id = ?", (qty_sold, product_id))

        # Payment / Layby Handling
        if payment_type == 'layby' and current_user.business_type != 'restaurant':
            deposit = float(data.get('deposit_amount', 0))
            if deposit <= 0 or deposit >= total_sale_price:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Deposit must be > 0 and < total price.'}), 400
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
        return jsonify({'success': True, 'sale_id': sale_id, 'message': 'Transaction completed successfully!'})
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
        if not sale or sale['payment_status'] == 'completed':
            conn.rollback()
            return jsonify({'success': False, 'message': 'Active layby not found or already settled.'}), 400

        new_balance = max(0.0, float(sale['balance_amount']) - payment)
        new_deposit = float(sale['deposit_amount']) + payment
        new_status = 'completed' if new_balance == 0 else 'in_progress'
        comp_date = datetime.today().strftime('%Y-%m-%d') if new_balance == 0 else sale['completion_date']

        conn.execute('''
            UPDATE sales SET balance_amount = ?, deposit_amount = ?, payment_status = ?, completion_date = ?
            WHERE sale_id = ?
        ''', (new_balance, new_deposit, new_status, comp_date, sale_id))
        conn.commit()
        return jsonify({'success': True, 'message': f"Payment of R{payment:.2f} logged. Balance: R{new_balance:.2f}"})
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
        sale = conn.execute("SELECT product_id, quantity_sold FROM sales WHERE sale_id = ?", (sale_id,)).fetchone()
        if not sale:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Sale not found.'}), 404

        if current_user.business_type == 'restaurant':
            recipes = conn.execute("SELECT ingredient_id, qty_required FROM product_recipes WHERE product_id = ?", 
                                   (sale['product_id'],)).fetchall()
            for r in recipes:
                conn.execute("UPDATE ingredients SET stock_qty = stock_qty + ? WHERE ingredient_id = ?", 
                             (r['qty_required'] * sale['quantity_sold'], r['ingredient_id']))
        else:
            conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE product_id = ?", 
                         (sale['quantity_sold'], sale['product_id']))

        conn.execute("DELETE FROM sales WHERE sale_id = ?", (sale_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Sale reversed and stock returned.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# 4. Customer APIs
@app.route('/api/customers/add', methods=['POST'])
@login_required
def api_add_customer():
    data = get_request_data()
    customer_id = data.get('customer_id', '').strip() or generate_id("C", "customers", "customer_id")
    name = data.get('name', '').strip()
    cellphone = (data.get('cellphone') or data.get('phone') or '').strip()
    email = data.get('email', '').strip()

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
            return jsonify({'success': True, 'message': 'Customer registered!'})
        flash('Customer registered!', 'success')
        return redirect(url_for('customers_page'))
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
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
        return jsonify({'success': True, 'message': 'Customer deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    seed_initial_tenants(bcrypt)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False, threaded=True)