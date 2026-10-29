from datetime import date, timedelta
from pathlib import Path
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, url_for
from datetime import datetime
import json
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "smartsupply.db"
app = Flask(__name__)
app.secret_key = "smartsupply-local-development"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def configured_openai_key():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key if key and key != "your_openai_api_key_here" else ""


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            contact TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Active'
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT '',
            supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            stock INTEGER NOT NULL DEFAULT 0, reorder_level INTEGER NOT NULL DEFAULT 10,
            unit_price REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
            quantity INTEGER NOT NULL, unit_price REAL NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
            order_date TEXT NOT NULL, expected_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
            carrier TEXT NOT NULL DEFAULT '', tracking_number TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Preparing', eta TEXT NOT NULL DEFAULT ''
        );
    """)
    if db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
        db.executemany("INSERT INTO suppliers(name,contact,email,category,status) VALUES(?,?,?,?,?)", [
            ("Northstar Components", "Maya Chen", "maya@northstar.example", "Electronics", "Active"),
            ("Evergreen Packaging", "Omar Patel", "omar@evergreen.example", "Packaging", "Active"),
            ("Atlas Industrial", "Nina Brooks", "nina@atlas.example", "Hardware", "Active"),
            ("Summit Office Supply", "Leo Martin", "leo@summit.example", "Office", "Active"),
        ])
        db.executemany("INSERT INTO products(name,sku,category,supplier_id,stock,reorder_level,unit_price) VALUES(?,?,?,?,?,?,?)", [
            ("Wireless sensor module", "EL-2041", "Electronics", 1, 42, 25, 18.50),
            ("Protective mailer, medium", "PK-1088", "Packaging", 2, 18, 30, 0.85),
            ("Steel mounting bracket", "HW-3320", "Hardware", 3, 126, 40, 4.20),
            ("Thermal label roll", "PK-2214", "Packaging", 2, 9, 20, 6.75),
            ("USB-C power adapter", "EL-1672", "Electronics", 1, 67, 30, 12.00),
        ])
        today = date.today()
        db.executemany("INSERT INTO purchase_orders(supplier_id,product_id,quantity,unit_price,status,order_date,expected_date) VALUES(?,?,?,?,?,?,?)", [
            (1, 1, 80, 17.90, "In transit", (today-timedelta(days=4)).isoformat(), (today+timedelta(days=2)).isoformat()),
            (2, 2, 200, 0.82, "Pending", (today-timedelta(days=1)).isoformat(), (today+timedelta(days=7)).isoformat()),
            (3, 3, 60, 4.00, "Delivered", (today-timedelta(days=12)).isoformat(), (today-timedelta(days=5)).isoformat()),
        ])
        db.executemany("INSERT INTO deliveries(order_id,carrier,tracking_number,status,eta) VALUES(?,?,?,?,?)", [
            (1, "DHL Express", "DHL-78429310", "In transit", (today+timedelta(days=2)).isoformat()),
            (2, "Awaiting dispatch", "—", "Preparing", (today+timedelta(days=7)).isoformat()),
        ])
    db.commit()
    db.close()


@app.context_processor
def inject_counts():
    db = get_db()
    low = db.execute("SELECT COUNT(*) FROM products WHERE stock <= reorder_level").fetchone()[0]
    return {"low_stock_count": low, "year": date.today().year, "now_label": datetime.now().strftime("%A, %B %-d") if os.name != "nt" else datetime.now().strftime("%A, %B %#d"), "ai_enabled": bool(configured_openai_key())}


def build_restock_recommendations(db):
    rows = db.execute("""SELECT p.id,p.name,p.sku,p.stock,p.reorder_level,p.unit_price,s.name supplier,
        COALESCE(SUM(CASE WHEN po.status IN ('Pending','In transit') THEN po.quantity ELSE 0 END),0) incoming
        FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id
        LEFT JOIN purchase_orders po ON po.product_id=p.id
        GROUP BY p.id ORDER BY (p.stock <= p.reorder_level) DESC,p.stock ASC""").fetchall()
    recommendations = []
    for row in rows:
        available = row["stock"] + row["incoming"]
        target = max(row["reorder_level"] * 2, row["reorder_level"] + 1)
        if row["stock"] <= row["reorder_level"] and available < target:
            gap = target - available
            urgency = "Urgent" if row["stock"] == 0 else "High" if row["stock"] <= row["reorder_level"] / 2 else "Review"
            recommendations.append({**dict(row), "available": available, "target": target, "suggested_qty": gap, "estimated_cost": gap * row["unit_price"], "urgency": urgency})
    return recommendations


def supply_chain_snapshot(db):
    products = db.execute("""SELECT p.name,p.sku,p.category,p.stock,p.reorder_level,p.unit_price,s.name supplier,
        COALESCE(SUM(CASE WHEN po.status IN ('Pending','In transit') THEN po.quantity ELSE 0 END),0) incoming
        FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id LEFT JOIN purchase_orders po ON po.product_id=p.id
        GROUP BY p.id ORDER BY p.name""").fetchall()
    orders = db.execute("""SELECT po.id,po.status,po.quantity,po.unit_price,po.expected_date,p.name product,s.name supplier
        FROM purchase_orders po LEFT JOIN products p ON p.id=po.product_id LEFT JOIN suppliers s ON s.id=po.supplier_id
        ORDER BY po.id DESC LIMIT 30""").fetchall()
    deliveries = db.execute("""SELECT d.status,d.carrier,d.eta,p.name product,s.name supplier
        FROM deliveries d JOIN purchase_orders po ON po.id=d.order_id LEFT JOIN products p ON p.id=po.product_id
        LEFT JOIN suppliers s ON s.id=po.supplier_id ORDER BY d.id DESC LIMIT 20""").fetchall()
    return {"products": [dict(r) for r in products], "recent_purchase_orders": [dict(r) for r in orders], "deliveries": [dict(r) for r in deliveries]}


@app.route("/")
def dashboard():
    db = get_db()
    metrics = {
        "suppliers": db.execute("SELECT COUNT(*) FROM suppliers WHERE status='Active'").fetchone()[0],
        "orders": db.execute("SELECT COUNT(*) FROM purchase_orders WHERE status IN ('Pending','In transit')").fetchone()[0],
        "inventory": db.execute("SELECT COALESCE(SUM(stock * unit_price),0) FROM products").fetchone()[0],
        "low_stock": db.execute("SELECT COUNT(*) FROM products WHERE stock <= reorder_level").fetchone()[0],
        "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
    }
    orders = db.execute("""SELECT po.*, s.name supplier, p.name product, p.sku FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN products p ON p.id=po.product_id
        ORDER BY po.id DESC LIMIT 5""").fetchall()
    products = db.execute("SELECT * FROM products ORDER BY (stock <= reorder_level) DESC, stock ASC LIMIT 5").fetchall()
    return render_template("dashboard.html", metrics=metrics, orders=orders, products=products, today=date.today().strftime("%A, %B %-d") if __import__("os").name != "nt" else date.today().strftime("%A, %B %#d"))


@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Supplier name is required.", "error")
        else:
            db.execute("INSERT INTO suppliers(name,contact,email,category) VALUES(?,?,?,?)", (name, request.form.get("contact", "").strip(), request.form.get("email", "").strip(), request.form.get("category", "").strip()))
            db.commit()
            flash("Supplier added.", "success")
        return redirect(url_for("suppliers"))
    rows = db.execute("SELECT s.*, COUNT(p.id) product_count FROM suppliers s LEFT JOIN products p ON p.supplier_id=s.id GROUP BY s.id ORDER BY s.name").fetchall()
    return render_template("suppliers.html", suppliers=rows)


@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    db = get_db()
    if request.method == "POST":
        name, sku = request.form.get("name", "").strip(), request.form.get("sku", "").strip()
        try:
            if not name or not sku:
                raise ValueError("Product name and SKU are required.")
            db.execute("INSERT INTO products(name,sku,category,supplier_id,stock,reorder_level,unit_price) VALUES(?,?,?,?,?,?,?)", (name, sku, request.form.get("category", "").strip(), request.form.get("supplier_id") or None, int(request.form.get("stock", 0)), int(request.form.get("reorder_level", 10)), float(request.form.get("unit_price", 0))))
            db.commit()
            flash("Product added to inventory.", "success")
        except (ValueError, sqlite3.IntegrityError):
            flash("Check the product details. SKUs must be unique and quantities must be valid.", "error")
        return redirect(url_for("inventory"))
    products = db.execute("SELECT p.*, s.name supplier FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.name").fetchall()
    supplier_rows = db.execute("SELECT id,name FROM suppliers WHERE status='Active' ORDER BY name").fetchall()
    low_stock = sum(1 for p in products if p["stock"] <= p["reorder_level"])
    stock_value = sum(p["stock"] * p["unit_price"] for p in products)
    return render_template("inventory.html", products=products, suppliers=supplier_rows, low_stock=low_stock, stock_value=stock_value)


@app.route("/procurement", methods=["GET", "POST"])
def procurement():
    db = get_db()
    if request.method == "POST":
        try:
            product_id = int(request.form["product_id"])
            supplier_id = int(request.form["supplier_id"])
            quantity, price = int(request.form["quantity"]), float(request.form["unit_price"])
            if quantity < 1 or price < 0:
                raise ValueError
            today = date.today()
            expected = request.form.get("expected_date") or (today + timedelta(days=7)).isoformat()
            db.execute("INSERT INTO purchase_orders(supplier_id,product_id,quantity,unit_price,status,order_date,expected_date) VALUES(?,?,?,?,?,?,?)", (supplier_id, product_id, quantity, price, "Pending", today.isoformat(), expected))
            db.commit()
            flash("Purchase order created.", "success")
        except (ValueError, KeyError, sqlite3.IntegrityError):
            flash("Enter a valid supplier, product, quantity, and unit price.", "error")
        return redirect(url_for("procurement"))
    orders = db.execute("SELECT po.*,s.name supplier,p.name product,p.sku FROM purchase_orders po LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN products p ON p.id=po.product_id ORDER BY po.id DESC").fetchall()
    suppliers = db.execute("SELECT id,name FROM suppliers WHERE status='Active' ORDER BY name").fetchall()
    products = db.execute("SELECT id,name,sku,unit_price,supplier_id FROM products ORDER BY name").fetchall()
    return render_template("procurement.html", orders=orders, suppliers=suppliers, products=products)


@app.route("/orders/<int:order_id>/status", methods=["POST"])
def update_order_status(order_id):
    status = request.form.get("status", "")
    if status not in {"Pending", "In transit", "Delivered", "Cancelled"}:
        flash("Invalid order status.", "error")
    else:
        db = get_db()
        order = db.execute("SELECT * FROM purchase_orders WHERE id=?", (order_id,)).fetchone()
        if order:
            db.execute("UPDATE purchase_orders SET status=? WHERE id=?", (status, order_id))
            if status == "Delivered" and order["status"] != "Delivered" and order["product_id"]:
                db.execute("UPDATE products SET stock=stock+? WHERE id=?", (order["quantity"], order["product_id"]))
            db.commit()
            flash("Order status updated.", "success")
    return redirect(request.referrer or url_for("procurement"))


@app.route("/deliveries", methods=["GET", "POST"])
def deliveries():
    db = get_db()
    if request.method == "POST":
        try:
            order_id = int(request.form["order_id"])
            carrier = request.form.get("carrier", "").strip()
            tracking = request.form.get("tracking_number", "").strip()
            eta = request.form.get("eta", "").strip()
            if not carrier:
                raise ValueError
            db.execute("INSERT INTO deliveries(order_id,carrier,tracking_number,status,eta) VALUES(?,?,?,?,?)", (order_id, carrier, tracking or "—", "Preparing", eta))
            db.commit()
            flash("Delivery tracking added.", "success")
        except (ValueError, KeyError, sqlite3.IntegrityError):
            flash("Choose an order and enter a carrier.", "error")
        return redirect(url_for("deliveries"))
    rows = db.execute("SELECT d.*,po.quantity,po.status order_status,s.name supplier,p.name product FROM deliveries d JOIN purchase_orders po ON po.id=d.order_id LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN products p ON p.id=po.product_id ORDER BY d.id DESC").fetchall()
    available = db.execute("SELECT po.id,po.expected_date,s.name supplier,p.name product FROM purchase_orders po LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN products p ON p.id=po.product_id WHERE NOT EXISTS(SELECT 1 FROM deliveries d WHERE d.order_id=po.id) AND po.status!='Cancelled' ORDER BY po.id DESC").fetchall()
    return render_template("deliveries.html", deliveries=rows, available_orders=available)


@app.route("/deliveries/<int:delivery_id>/status", methods=["POST"])
def update_delivery_status(delivery_id):
    status = request.form.get("status", "")
    if status not in {"Preparing", "In transit", "Delivered", "Delayed"}:
        flash("Invalid delivery status.", "error")
    else:
        db = get_db()
        delivery = db.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if delivery:
            db.execute("UPDATE deliveries SET status=? WHERE id=?", (status, delivery_id))
            if status == "Delivered":
                order = db.execute("SELECT * FROM purchase_orders WHERE id=?", (delivery["order_id"],)).fetchone()
                if order and order["status"] != "Delivered":
                    db.execute("UPDATE purchase_orders SET status='Delivered' WHERE id=?", (order["id"],))
                    if order["product_id"]:
                        db.execute("UPDATE products SET stock=stock+? WHERE id=?", (order["quantity"], order["product_id"]))
            db.commit()
            flash("Delivery status updated.", "success")
    return redirect(url_for("deliveries"))


@app.route("/reports")
def reports():
    db = get_db()
    spend = db.execute("SELECT COALESCE(SUM(quantity*unit_price),0) FROM purchase_orders WHERE status!='Cancelled'").fetchone()[0]
    total_units = db.execute("SELECT COALESCE(SUM(stock),0) FROM products").fetchone()[0]
    supplier_stats = db.execute("SELECT s.name,COUNT(po.id) orders,COALESCE(SUM(po.quantity*po.unit_price),0) spend,COALESCE(AVG(CASE WHEN po.status='Delivered' THEN 100 ELSE 65 END),0) performance FROM suppliers s LEFT JOIN purchase_orders po ON po.supplier_id=s.id GROUP BY s.id ORDER BY spend DESC").fetchall()
    category_stats = db.execute("SELECT category,COUNT(*) products,SUM(stock) units,SUM(stock*unit_price) value FROM products GROUP BY category ORDER BY value DESC").fetchall()
    return render_template("reports.html", spend=spend, total_units=total_units, supplier_stats=supplier_stats, category_stats=category_stats)


@app.route("/assistant")
def assistant():
    db = get_db()
    recommendations = build_restock_recommendations(db)
    return render_template("assistant.html", recommendations=recommendations, total_products=db.execute("SELECT COUNT(*) FROM products").fetchone()[0])


@app.route("/api/assistant", methods=["POST"])
def ask_assistant():
    api_key = configured_openai_key()
    if not api_key:
        return {"error": "AI chat is not configured yet. Set OPENAI_API_KEY in PowerShell, restart SmartSupply, and try again."}, 503
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("message", "")).strip()
    if not question or len(question) > 2000:
        return {"error": "Enter a question of 1 to 2,000 characters."}, 400
    try:
        from openai import OpenAI
        context = supply_chain_snapshot(get_db())
        client = OpenAI(api_key=api_key, timeout=30.0, max_retries=1)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            instructions=("You are SmartSupply's procurement and supply chain assistant. Use only the supplied current database snapshot for company-specific facts. "
                          "Do not invent stock, supplier, order, date, or cost data. If the snapshot lacks the information, say so. "
                          "Give concise, practical recommendations. Clearly distinguish observed facts from estimates. Never claim to create or update an order; this assistant is read-only."),
            input="Current SmartSupply data (JSON):\n" + json.dumps(context, ensure_ascii=False) + "\n\nUser question:\n" + question,
            store=False,
        )
        answer = response.output_text.strip()
        if not answer:
            return {"error": "The AI assistant returned an empty response. Please try again."}, 502
        return {"answer": answer}
    except ImportError:
        return {"error": "Install the AI package with: pip install -r requirements.txt, then restart SmartSupply."}, 503
    except Exception:
        app.logger.exception("AI assistant request failed")
        return {"error": "Could not reach the AI service. Check your API key, internet connection, and model access, then try again."}, 502


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
