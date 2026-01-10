# imports
import sqlite3
import os
from functools import wraps
from flask import (
    Flask,
    render_template,
    session,
    redirect,
    url_for,
    request,
    flash
)

# --------------------------------------------------
# App & Config
# --------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_secret")

import secrets

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sports_store.db")

#--------------------------------------------------
# Database Helpers
#--------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
   
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            image TEXT NOT NULL
        )
""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

def get_products():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    conn.close()
    return products

def verify_csrf():
    session_token = session.get("_csrf_token")
    form_token = request.form.get("csrf_token")
    return bool(session_token and form_token and session_token == form_token)

from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password: str) -> str:
    return generate_password_hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)

with app.app_context():
    init_db()
    
# --------------------------------------------------
# Admin Decorator (DEFINE BEFORE ROUTES)
# --------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

def validate_product_form(name, price, category, image):
    if not name or not price or not category or not image:
        return "All fields are required."
    try:
        price=float(price)
        if price <= 0:
           return "Price must be greater than zero."
    except ValueError:
        return "Price must be a number."
    
    if not image.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "Invalid image format."
    
    return None

# --------------------------------------------------
# Public Routes
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/products")
def product_page():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    sql = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    
    if category:
        sql += " AND category = ?"
        params.append(category)
    
    cursor.execute(sql, params)
    products = cursor.fetchall()
    conn.close()

    return render_template("products.html", products=products, query=query, category=category)

@app.route("/contact")
def contact():
    return render_template("contact.html")

# --------------------------------------------------
# Cart Routes
# --------------------------------------------------

@app.route("/add_to_cart/<product_name>")
def add_to_cart(product_name):
    cart = session.get("cart")

    # SAFETY: migrate old list-based cart to dict
    if isinstance(cart, list):
        new_cart = {}
        for item in cart:
            new_cart[item] = new_cart.get(item, 0) + 1
        cart = new_cart

    if cart is None:
        cart = {}

    cart[product_name] = cart.get(product_name, 0) + 1

    session["cart"] = cart
    session.modified = True

    return redirect(url_for("product_page"))

@app.route("/remove_from_cart/<product_name>")
def remove_from_cart(product_name):
    cart = session.get("cart", {})

    if product_name in cart:
        del cart[product_name]

    session["cart"] = cart
    session.modified = True

    return redirect(url_for("cart"))

@app.route("/cart")
def cart():
    cart = session.get("cart", {})

    # SAFETY: migrate old list-based cart to dict
    if isinstance(cart, list):
        new_cart = {}
        for item in cart:
            new_cart[item] = new_cart.get(item, 0) + 1
        session["cart"] = new_cart
        cart = new_cart

    cart_products = []
    total = 0

    for name, qty in cart.items():
        for product in get_products():
            if product["name"] == name:
                product_copy = dict(product)
                product_copy["qty"] = qty
                product_copy["subtotal"] = qty * product["price"]
                total += product_copy["subtotal"]
                cart_products.append(product_copy)

    return render_template("cart.html", cart_products=cart_products, total=total)

# --------------------------------------------------
# Admin Routes
# --------------------------------------------------

@app.route("/admin")
@admin_required
def admin():
    
    products = get_products()
    return render_template("admin.html", products=products)

@app.route("/admin/add", methods=["POST"])
@admin_required
def admin_add():
    
    if not verify_csrf():
        flash("Invalid CSRF token", "danger")
        return redirect(url_for("admin"))
    
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "").strip()
    category = request.form.get("category", "").strip()
    image = request.form.get("image", "").strip()

    error = validate_product_form(name, price, category, image)
    if error:
        flash(error, "error")
        return redirect(url_for("admin"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, price, category, image) VALUES (?, ?, ?, ?)", 
        (name, price, category, image)
    )
    conn.commit()
    conn.close()
    
    flash("Product added successfully!", "success")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<int:product_id>")
@admin_required
def admin_delete(product_id):
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    
    flash("Product deleted", "warning")
    return redirect(url_for("admin"))

@app.route("/admin/edit/<int:product_id>")
@admin_required
def admin_edit(product_id):
    if not admin_required():
        return redirect(url_for("admin_login"))
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
   
    conn.close()
    
    return render_template("admin_edit.html", product=product)

@app.route("/admin/update/<int:product_id>", methods=["POST"])
def admin_update(product_id):
    
    if not verify_csrf():
        flash("Invalid CSRF token", "danger")
        return redirect(url_for("admin"))
    
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "").strip()
    category = request.form.get("category", "").strip()
    image = request.form.get("image", "").strip()
    
    if image:
        error = validate_product_form(name, price, category, image)
        if error:
            flash(error, "error")
            return redirect(url_for("admin"))

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 🔒 If image is empty, keep existing one
    if not image:
        cursor.execute("SELECT image FROM products WHERE id = ?", (product_id,))
        image = cursor.fetchone()["image"]

    sql = "UPDATE products SET name = ?, price = ?, category = ?, image = ? WHERE id = ?"
    cursor.execute(sql, (name, price, category, image, product_id))

    conn.commit()
    conn.close()

    flash("Product updated successfully!", "info")
    return redirect(url_for("admin"))

# --------------------------------------------------
# Auth Routes
# --------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Username and password are required", "danger")
            return redirect(url_for("admin_login"))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE username = ?", 
            (username,)
        )
        user = cursor.fetchone()
        conn.close()
        
        if not user or not verify_password(password, user["password_hash"]):
            flash("Invalid username or password", "danger")
            return redirect(url_for("admin_login"))
        
        session["admin_logged_in"] = True
        return redirect(url_for("admin"))
    
    return render_template("admin_login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("register"))
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            flash("Username already exists.", "danger")
            return redirect(url_for("register"))
        
        password_hash = hash_password(password)
        
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)", 
            (username, password_hash)
        )
        conn.commit()
        conn.close()
        
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("admin_login"))
    
    return render_template("register.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

# --------------------------------------------------
# Run (local only)
# --------------------------------------------------

if __name__ == "__main__":
    app.run()
