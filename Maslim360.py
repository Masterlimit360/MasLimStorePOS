import sqlite3
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
import os
import shutil
import threading
import json
import urllib.request
import urllib.parse
import urllib.error
import base64
import io

# ─── Try importing optional camera/barcode libraries ───────────────────────────
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ─── Color Palette ─────────────────────────────────────────────────────────────
C = {
    "bg":         "#F9FAFB",   # Very light grey background
    "surface":    "#FFFFFF",   # White Card / panel surface
    "surface2":   "#F3F4F6",   # Lighter grey surface
    "border":     "#E5E7EB",   # Subtle border
    "accent":     "#EAB308",   # Yellow accent (Main)
    "accent2":    "#9CA3AF",   # Grey accent
    "accent3":    "#FBBF24",   # Amber / gold
    "danger":     "#EF4444",   # Red
    "success":    "#10B981",   # Green
    "warning":    "#F59E0B",   # Darker Yellow
    "text":       "#111827",   # Primary text (Dark Grey)
    "text2":      "#4B5563",   # Secondary text (Medium Grey)
    "text3":      "#9CA3AF",   # Muted text
    "white":      "#FFFFFF",
    "hover":      "#FEF08A",   # Lighter hover
}

FONT_TITLE   = ("Segoe UI", 22, "bold")
FONT_HEAD    = ("Segoe UI", 14, "bold")
FONT_SUB     = ("Segoe UI", 11, "bold")
FONT_BODY    = ("Segoe UI", 10)
FONT_SMALL   = ("Segoe UI", 9)
FONT_MONO    = ("Consolas", 10)

PAYSTACK_SECRET_KEY = ""   # ← Replace with real key
PAYSTACK_PUBLIC_KEY = ""   # ← Replace with real key

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
class DatabaseManager:
    def __init__(self, db_name="maslim360.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.initialize_tables()
        self.seed_data()

    def initialize_tables(self):
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                role TEXT,
                full_name TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                price REAL,
                quantity INTEGER,
                barcode TEXT UNIQUE,
                supplier TEXT,
                cost_price REAL DEFAULT 0,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                loyalty_points INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sales (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                customer_id INTEGER,
                total_amount REAL,
                discount REAL DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                payment_method TEXT,
                paystack_reference TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            );
            CREATE TABLE IF NOT EXISTS sales_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER,
                product_id INTEGER,
                quantity INTEGER,
                price_at_sale REAL,
                FOREIGN KEY(sale_id) REFERENCES sales(sale_id),
                FOREIGN KEY(product_id) REFERENCES products(product_id)
            );
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER,
                amount REAL,
                method TEXT,
                paystack_ref TEXT,
                status TEXT DEFAULT 'completed',
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sale_id) REFERENCES sales(sale_id)
            );
        """)
        # Migration guards
        for col in [
            ("products", "cost_price", "REAL DEFAULT 0"),
            ("products", "image_path", "TEXT"),
            ("sales", "discount", "REAL DEFAULT 0"),
            ("sales", "paystack_reference", "TEXT"),
            ("payments", "paystack_ref", "TEXT"),
            ("payments", "status", "TEXT DEFAULT 'completed'"),
            ("users", "full_name", "TEXT"),
            ("users", "phone", "TEXT"),
            ("users", "created_at", "TIMESTAMP"),
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE {col[0]} ADD COLUMN {col[1]} {col[2]}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def seed_data(self):
        # Admin
        for uname, pwd, role, fname in [
            ('admin',   'admin123',   'Administrator', 'Admin User'),
            ('manager', 'manager123', 'Manager',       'Store Manager'),
            ('cashier', 'cashier123', 'Cashier',       'Front Cashier'),
        ]:
            self.cursor.execute("SELECT 1 FROM users WHERE username=?", (uname,))
            if not self.cursor.fetchone():
                ph = hashlib.sha256(pwd.encode()).hexdigest()
                self.cursor.execute(
                    "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
                    (uname, ph, role, fname))

        # Products
        self.cursor.execute("SELECT COUNT(*) FROM products")
        if self.cursor.fetchone()[0] == 0:
            cats = ['Electronics', 'Stationery', 'Furniture', 'Appliances',
                    'Accessories', 'Books', 'Food', 'Health', 'Clothing', 'Beverages']
            sups = ['Ultra Supply Co', 'Prime Distributors', 'Ace Imports',
                    'Top Wholesale', 'Global Traders', 'Tech Hub', 'Office Pro', 'Smart Goods']
            pnames = [
                "Samsung Phone", "Laptop Stand", "Wireless Mouse", "Keyboard", "USB-C Hub",
                "Notebook A4", "Pen Set", "Stapler", "Scissors", "Tape Roll",
                "Office Chair", "Standing Desk", "File Cabinet", "Shelf Unit", "Desk Lamp",
                "Iron Box", "Blender", "Water Dispenser", "Fan (Stand)", "Rice Cooker",
                "Phone Case", "Screen Protector", "Earbuds", "Watch Band", "Cable Clips",
                "Python Book", "Accounting Manual", "Management Guide", "Atlas Book", "Novel Set",
                "Rice 5kg", "Cooking Oil", "Sugar 2kg", "Salt 1kg", "Tomato Paste",
                "Paracetamol", "Vitamin C", "Hand Sanitizer", "Face Mask", "Thermometer",
                "T-Shirt XL", "Trousers", "Cap", "Socks (3pk)", "Belt",
                "Mineral Water", "Soft Drink", "Juice 1L", "Energy Drink", "Tea Bags",
            ]
            prods = []
            for i, pname in enumerate(pnames):
                cat = cats[i % len(cats)]
                price = round(5 + (i + 1) * 2.5, 2)
                cost  = round(price * 0.65, 2)
                qty   = 30 + (i * 3)
                bc    = f"ML{1000 + i + 1:04d}"
                sup   = sups[i % len(sups)]
                prods.append((pname, cat, price, qty, bc, sup, cost))
            self.cursor.executemany(
                "INSERT INTO products (name,category,price,quantity,barcode,supplier,cost_price) VALUES (?,?,?,?,?,?,?)",
                prods)

        # Customers
        self.cursor.execute("SELECT COUNT(*) FROM customers")
        if self.cursor.fetchone()[0] == 0:
            custs = [
                ('Kwame Mensah',    '0244123456', 'kwame@mail.com',   'Asante, Kumasi',    50),
                ('Abena Owusu',     '0554987654', 'abena@mail.com',   'Ahodwo, Kumasi',    25),
                ('Kofi Asante',     '0201234567', 'kofi@mail.com',    'Bantama, Kumasi',   75),
                ('Ama Darko',       '0277654321', 'ama@mail.com',     'Nhyiaeso, Kumasi',  10),
                ('Yaw Boateng',     '0501112233', 'yaw@mail.com',     'Suame, Kumasi',     30),
            ]
            self.cursor.executemany(
                "INSERT INTO customers (name,phone,email,address,loyalty_points) VALUES (?,?,?,?,?)",
                custs)
        self.conn.commit()

    def execute_query(self, query, params=()):
        self.cursor.execute(query, params)
        return self.cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# POS CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════
class POSController:
    def __init__(self, db_manager):
        self.db = db_manager
        self.current_user = None

    def login(self, username, password):
        ph = hashlib.sha256(password.encode()).hexdigest()
        row = self.db.execute_query(
            "SELECT user_id, role, full_name FROM users WHERE username=? AND password_hash=?",
            (username, ph)).fetchone()
        if row:
            self.current_user = {'id': row[0], 'username': username, 'role': row[1], 'full_name': row[2] or username}
            return True
        return False

    # ─── Products ──────────────────────────────────────────────────────────────
    def get_product_by_barcode(self, barcode):
        row = self.db.execute_query("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
        return self._row_to_product(row)

    def get_product_by_name(self, name):
        row = self.db.execute_query("SELECT * FROM products WHERE name=?", (name,)).fetchone()
        return self._row_to_product(row)

    def search_products(self, query):
        rows = self.db.execute_query(
            "SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? OR category LIKE ?",
            (f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
        return [self._row_to_product(r) for r in rows if r]

    def _row_to_product(self, row):
        if not row: return None
        cols = ['id','name','category','price','stock','barcode','supplier','cost_price','image_path','created_at']
        return dict(zip(cols, row))

    def get_all_products(self):
        return self.db.execute_query("SELECT * FROM products ORDER BY name").fetchall()

    def get_all_product_names(self):
        return [r[0] for r in self.db.execute_query("SELECT name FROM products ORDER BY name").fetchall()]

    def add_product(self, name, category, price, qty, barcode, supplier='', cost_price=0):
        try:
            self.db.execute_query(
                "INSERT INTO products (name,category,price,quantity,barcode,supplier,cost_price) VALUES (?,?,?,?,?,?,?)",
                (name, category, price, qty, barcode, supplier, cost_price))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_product(self, pid, name, category, price, qty, barcode, supplier='', cost_price=0):
        try:
            self.db.execute_query(
                "UPDATE products SET name=?,category=?,price=?,quantity=?,barcode=?,supplier=?,cost_price=? WHERE product_id=?",
                (name, category, price, qty, barcode, supplier, cost_price, pid))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_product(self, pid):
        self.db.execute_query("DELETE FROM products WHERE product_id=?", (pid,))
        self.db.commit()

    # ─── Customers ─────────────────────────────────────────────────────────────
    def get_all_customers(self):
        return self.db.execute_query("SELECT * FROM customers ORDER BY name").fetchall()

    def add_customer(self, name, phone, email, address):
        self.db.execute_query(
            "INSERT INTO customers (name,phone,email,address) VALUES (?,?,?,?)",
            (name, phone, email, address))
        self.db.commit()

    def update_customer(self, cid, name, phone, email, address):
        self.db.execute_query(
            "UPDATE customers SET name=?,phone=?,email=?,address=? WHERE customer_id=?",
            (name, phone, email, address, cid))
        self.db.commit()

    def delete_customer(self, cid):
        self.db.execute_query("DELETE FROM customers WHERE customer_id=?", (cid,))
        self.db.commit()

    def get_customer_by_id(self, cid):
        row = self.db.execute_query("SELECT * FROM customers WHERE customer_id=?", (cid,)).fetchone()
        if row:
            return {'id':row[0],'name':row[1],'phone':row[2],'email':row[3],'address':row[4],'loyalty_points':row[5]}
        return None

    def get_customer_purchase_history(self, cid):
        sales = self.db.execute_query(
            "SELECT s.sale_id, s.date, s.total_amount, s.payment_method FROM sales s WHERE s.customer_id=? ORDER BY s.date DESC",
            (cid,)).fetchall()
        history = []
        for sale in sales:
            items = self.db.execute_query(
                "SELECT p.name, si.quantity FROM sales_items si JOIN products p ON si.product_id=p.product_id WHERE si.sale_id=?",
                (sale[0],)).fetchall()
            items_str = ", ".join([f"{it[0]} (x{it[1]})" for it in items])
            history.append((sale[0], sale[1], sale[2], sale[3], items_str))
        return history

    def award_loyalty_points(self, cid, points):
        self.db.execute_query("UPDATE customers SET loyalty_points=loyalty_points+? WHERE customer_id=?", (points, cid))
        self.db.commit()

    def redeem_loyalty_points(self, cid, points):
        cust = self.get_customer_by_id(cid)
        if cust and cust['loyalty_points'] >= points:
            self.db.execute_query("UPDATE customers SET loyalty_points=loyalty_points-? WHERE customer_id=?", (points, cid))
            self.db.commit()
            return True
        return False

    # ─── Sales ─────────────────────────────────────────────────────────────────
    def generate_receipt(self, sale_id, cart_items, total_sale, payment_method, customer_id=None, discount=0):
        os.makedirs('receipts', exist_ok=True)
        path = os.path.join('receipts', f'receipt_{sale_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
        cname = 'Guest'
        if customer_id:
            c = self.get_customer_by_id(customer_id)
            cname = c['name'] if c else 'Unknown'
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n' + '━'*44 + '\n')
            f.write('        MasLim360 Store\n')
            f.write('      Point of Sale Receipt\n')
            f.write('━'*44 + '\n')
            f.write(f'Receipt #: {sale_id:06d}\n')
            f.write(f'Date:      {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Cashier:   {self.current_user["username"]}\n')
            f.write(f'Customer:  {cname}\n')
            f.write('─'*44 + '\n')
            for it in cart_items:
                f.write(f"  {it['name'][:22]:22} x{it['qty']:2}  GH₵{it['total']:8.2f}\n")
            f.write('─'*44 + '\n')
            subtotal = sum(it['total'] for it in cart_items)
            f.write(f'  Subtotal:                    GH₵{subtotal:8.2f}\n')
            if discount:
                f.write(f'  Discount:                   -GH₵{discount:8.2f}\n')
            f.write(f'  TOTAL:                       GH₵{total_sale:8.2f}\n')
            f.write(f'  Payment:  {payment_method}\n')
            f.write('━'*44 + '\n')
            f.write('    Thank you for shopping at MasLim360!\n')
            f.write('━'*44 + '\n\n')
        return path

    def process_sale(self, cart_items, payment_method, customer_id=None, discount=0, paystack_ref=None):
        if not cart_items or not self.current_user:
            return False, "Cart empty or not logged in"
        try:
            subtotal   = sum(it['total'] for it in cart_items)
            total_sale = max(subtotal - discount, 0)
            alerts     = []

            self.db.execute_query(
                "INSERT INTO sales (user_id,customer_id,total_amount,discount,payment_method,paystack_reference) VALUES (?,?,?,?,?,?)",
                (self.current_user['id'], customer_id, total_sale, discount, payment_method, paystack_ref))
            sale_id = self.db.cursor.lastrowid

            for it in cart_items:
                row = self.db.execute_query(
                    "SELECT quantity FROM products WHERE product_id=?", (it['id'],)).fetchone()
                if not row or row[0] < it['qty']:
                    raise Exception(f"Insufficient stock for {it['name']}")
                self.db.execute_query(
                    "INSERT INTO sales_items (sale_id,product_id,quantity,price_at_sale) VALUES (?,?,?,?)",
                    (sale_id, it['id'], it['qty'], it['price']))
                self.db.execute_query(
                    "UPDATE products SET quantity=quantity-? WHERE product_id=?",
                    (it['qty'], it['id']))
                new_stock = row[0] - it['qty']
                if new_stock <= 10:
                    alerts.append(f"⚠ {it['name']} — only {new_stock} left")

            self.db.execute_query(
                "INSERT INTO payments (sale_id,amount,method,paystack_ref) VALUES (?,?,?,?)",
                (sale_id, total_sale, payment_method, paystack_ref))

            if customer_id:
                pts = int(total_sale // 10)
                if pts: self.award_loyalty_points(customer_id, pts)

            self.db.commit()
            receipt = self.generate_receipt(sale_id, cart_items, total_sale, payment_method, customer_id, discount)
            msg = f"Sale #{sale_id:06d} completed!\nReceipt → {receipt}"
            if alerts:
                msg += "\n\nLOW STOCK ALERTS:\n" + "\n".join(alerts)
            return True, msg
        except Exception as e:
            self.db.conn.rollback()
            return False, str(e)

    def get_sales_report(self, start_date=None, end_date=None):
        q = """SELECT s.sale_id, s.date, s.total_amount, s.payment_method, u.username, COALESCE(c.name,'Guest')
               FROM sales s
               LEFT JOIN users u ON s.user_id=u.user_id
               LEFT JOIN customers c ON s.customer_id=c.customer_id"""
        p = ()
        if start_date and end_date:
            q += " WHERE s.date BETWEEN ? AND ?"
            p = (start_date, end_date)
        q += " ORDER BY s.date DESC"
        return self.db.execute_query(q, p).fetchall()

    def get_dashboard_stats(self):
        today = datetime.now().strftime('%Y-%m-%d')
        sales_today = self.db.execute_query(
            "SELECT COUNT(*), COALESCE(SUM(total_amount),0) FROM sales WHERE date(date)=?", (today,)).fetchone()
        total_products = self.db.execute_query("SELECT COUNT(*) FROM products").fetchone()[0]
        low_stock = self.db.execute_query("SELECT COUNT(*) FROM products WHERE quantity<=10").fetchone()[0]
        total_customers = self.db.execute_query("SELECT COUNT(*) FROM customers").fetchone()[0]
        monthly = self.db.execute_query(
            "SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE strftime('%Y-%m',date)=strftime('%Y-%m','now')").fetchone()[0]
        return {
            'sales_count': sales_today[0],
            'sales_total': sales_today[1],
            'total_products': total_products,
            'low_stock': low_stock,
            'total_customers': total_customers,
            'monthly_revenue': monthly,
        }

    def get_inventory_report(self):
        return self.db.execute_query(
            "SELECT product_id,name,category,price,quantity,barcode,supplier FROM products ORDER BY quantity ASC").fetchall()

    # ─── Paystack ──────────────────────────────────────────────────────────────
    def initiate_paystack_charge(self, phone, amount_ghs, email="customer@maslim360.com", provider="mtn"):
        """Initiate mobile money charge via Paystack (GHS)."""
        try:
            amount_pesewas = int(amount_ghs * 100)
            payload = json.dumps({
                "mobile_money": {"phone": phone, "provider": provider},
                "amount": amount_pesewas,
                "email": email,
                "currency": "GHS",
                "metadata": {"store": "MasLim360", "cashier": self.current_user['username']} if self.current_user else {"store": "MasLim360"},
            }).encode()
            req = urllib.request.Request(
                "https://api.paystack.co/charge",
                data=payload,
                headers={
                    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode())
                return {"status": False, "message": error_data.get("message", str(e))}
            except Exception:
                return {"status": False, "message": str(e)}
        except Exception as e:
            return {"status": False, "message": str(e)}

    def verify_paystack_transaction(self, reference):
        try:
            req = urllib.request.Request(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={
                    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                },
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode())
                return {"status": False, "message": error_data.get("message", str(e))}
            except Exception:
                return {"status": False, "message": str(e)}
        except Exception as e:
            return {"status": False, "message": str(e)}

    def submit_paystack_otp(self, otp, reference):
        try:
            payload = json.dumps({"otp": otp, "reference": reference}).encode()
            req = urllib.request.Request(
                "https://api.paystack.co/charge/submit_otp",
                data=payload,
                headers={
                    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode())
                return {"status": False, "message": error_data.get("message", str(e))}
            except Exception:
                return {"status": False, "message": str(e)}
        except Exception as e:
            return {"status": False, "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════
def styled_btn(parent, text, command, bg=None, fg=None, font=None, **kw):
    bg   = bg   or C["accent"]
    fg   = fg   or C["white"]
    font = font or FONT_SUB
    btn = tk.Button(parent, text=text, command=command,
                    bg=bg, fg=fg, font=font,
                    relief=tk.FLAT, cursor="hand2",
                    activebackground=C["accent2"], activeforeground=C["white"],
                    padx=kw.get("padx", 14), pady=kw.get("pady", 7),
                    bd=0)
    return btn

def card_frame(parent, **kw):
    return tk.Frame(parent, bg=C["surface"], relief=tk.FLAT,
                    highlightbackground=C["border"], highlightthickness=1, **kw)

def section_label(parent, text, color=None):
    return tk.Label(parent, text=text, font=FONT_HEAD,
                    bg=C["surface"], fg=color or C["accent"])

def body_label(parent, text, color=None, **kw):
    return tk.Label(parent, text=text, font=FONT_BODY,
                    bg=C["surface"], fg=color or C["text2"], **kw)


# ═══════════════════════════════════════════════════════════════════════════════
# BARCODE SCANNER WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class BarcodeScannerWindow(tk.Toplevel):
    """Live camera barcode scanner using OpenCV + pyzbar."""

    def __init__(self, parent, on_scan_callback):
        super().__init__(parent)
        self.on_scan = on_scan_callback
        self.title("📷  MasLim360 — Barcode Scanner")
        self.configure(bg=C["bg"])
        self.geometry("700x560")
        self.resizable(False, False)

        self.cap = None
        self.running = False
        self.last_barcode = None

        # Header
        tk.Label(self, text="📷  Camera Barcode Scanner",
                 font=FONT_TITLE, bg=C["bg"], fg=C["accent"]).pack(pady=(16, 4))
        tk.Label(self, text="Point camera at barcode — detected codes appear below",
                 font=FONT_SMALL, bg=C["bg"], fg=C["text2"]).pack(pady=(0, 8))

        # Canvas for camera feed
        self.canvas = tk.Canvas(self, width=640, height=400, bg="#000", highlightthickness=0)
        self.canvas.pack(pady=4)

        # Status / result row
        bot = tk.Frame(self, bg=C["bg"])
        bot.pack(fill=tk.X, padx=16, pady=8)

        self.status_var = tk.StringVar(value="Initializing camera…")
        tk.Label(bot, textvariable=self.status_var, font=FONT_BODY,
                 bg=C["bg"], fg=C["text2"]).pack(side=tk.LEFT)

        # Manual entry fallback
        mf = tk.Frame(self, bg=C["bg"])
        mf.pack(pady=4)
        tk.Label(mf, text="Or enter barcode manually:", font=FONT_BODY,
                 bg=C["bg"], fg=C["text2"]).pack(side=tk.LEFT, padx=4)
        self.manual_var = tk.StringVar()
        me = tk.Entry(mf, textvariable=self.manual_var, font=FONT_BODY,
                      bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                      relief=tk.FLAT, bd=6, width=20)
        me.pack(side=tk.LEFT, padx=4)
        me.bind("<Return>", self._manual_submit)
        styled_btn(mf, "Use", self._manual_submit, padx=8, pady=4).pack(side=tk.LEFT)

        styled_btn(self, "✖  Close Scanner", self._close, bg=C["danger"], fg=C["white"]).pack(pady=8)

        self._start_camera()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _start_camera(self):
        if not (CV2_AVAILABLE and PYZBAR_AVAILABLE and PIL_AVAILABLE):
            missing = []
            if not CV2_AVAILABLE:    missing.append("opencv-python")
            if not PYZBAR_AVAILABLE: missing.append("pyzbar")
            if not PIL_AVAILABLE:    missing.append("Pillow")
            self.status_var.set(f"Install: pip install {' '.join(missing)}")
            self.canvas.create_text(320, 200, text="Camera libraries not installed.\nUse manual entry below.",
                                    fill=C["text2"], font=FONT_HEAD, justify="center")
            return
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.status_var.set("No camera detected — use manual entry.")
                return
            self.running = True
            self.status_var.set("Camera active — scanning…")
            self._update_frame()
        except Exception as e:
            self.status_var.set(f"Camera error: {e}")

    def _update_frame(self):
        if not self.running or not self.cap:
            return
        ret, frame = self.cap.read()
        if ret:
            # Scan barcodes
            barcodes = pyzbar.decode(frame)
            for bc in barcodes:
                data = bc.data.decode('utf-8')
                # Draw rect
                (x, y, w, h) = bc.rect
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 212, 170), 3)
                cv2.putText(frame, data, (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 170), 2)
                if data != self.last_barcode:
                    self.last_barcode = data
                    self.status_var.set(f"✅  Detected: {data}")
                    self.after(200, lambda d=data: self._confirm_scan(d))
                    return

            # Display frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb).resize((640, 400))
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)
        self.after(30, self._update_frame)

    def _confirm_scan(self, barcode):
        self._close()
        self.on_scan(barcode)

    def _manual_submit(self, event=None):
        val = self.manual_var.get().strip()
        if val:
            self._close()
            self.on_scan(val)

    def _close(self):
        self.running = False
        if self.cap:
            self.cap.release()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# PAYSTACK MOBILE MONEY DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class MobileMoneyDialog(tk.Toplevel):
    def __init__(self, parent, controller, amount, on_success):
        super().__init__(parent)
        self.controller = controller
        self.amount     = amount
        self.on_success = on_success
        self.title("📱  Mobile Money Payment — MasLim360")
        self.configure(bg=C["bg"])
        self.geometry("460x620")
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        tk.Label(self, text="📱  Mobile Money", font=FONT_TITLE, bg=C["bg"], fg=C["accent"]).pack(pady=(20, 4))
        tk.Label(self, text="Powered by Paystack", font=FONT_SMALL, bg=C["bg"], fg=C["text3"]).pack()

        # Amount card
        ac = card_frame(self)
        ac.pack(fill=tk.X, padx=24, pady=(16, 4))
        tk.Label(ac, text="Amount to Pay", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(pady=(10, 2))
        tk.Label(ac, text=f"GH₵ {self.amount:,.2f}",
                 font=("Segoe UI", 28, "bold"), bg=C["surface"], fg=C["success"]).pack(pady=(0, 10))

        # Network selector
        nf = card_frame(self)
        nf.pack(fill=tk.X, padx=24, pady=4)
        tk.Label(nf, text="Mobile Network", font=FONT_SUB, bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 4))
        self.network_var = tk.StringVar(value="mtn")
        nets = [("MTN Mobile Money", "mtn"), ("Vodafone Cash", "vod"), ("AirtelTigo Money", "tgo")]
        nrow = tk.Frame(nf, bg=C["surface"])
        nrow.pack(padx=12, pady=(0, 10))
        for label, val in nets:
            tk.Radiobutton(nrow, text=label, variable=self.network_var, value=val,
                           bg=C["surface"], fg=C["text"], selectcolor=C["surface2"],
                           activebackground=C["surface"], font=FONT_BODY).pack(side=tk.LEFT, padx=6)

        # Phone entry
        pf = card_frame(self)
        pf.pack(fill=tk.X, padx=24, pady=4)
        tk.Label(pf, text="Phone Number", font=FONT_SUB, bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 2))
        self.phone_var = tk.StringVar(value="0244")
        pe = tk.Entry(pf, textvariable=self.phone_var, font=("Segoe UI", 14),
                      bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                      relief=tk.FLAT, bd=6, width=22)
        pe.pack(padx=12, pady=(0, 10), ipady=6)

        # Email entry
        ef = card_frame(self)
        ef.pack(fill=tk.X, padx=24, pady=4)
        tk.Label(ef, text="Customer Email (optional)", font=FONT_SUB, bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 2))
        self.email_var = tk.StringVar(value="customer@maslim360.com")
        ee = tk.Entry(ef, textvariable=self.email_var, font=FONT_BODY,
                      bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                      relief=tk.FLAT, bd=6, width=30)
        ee.pack(padx=12, pady=(0, 10), ipady=5)

        self.status_var = tk.StringVar()
        tk.Label(self, textvariable=self.status_var, font=FONT_SMALL,
                 bg=C["bg"], fg=C["warning"], wraplength=380).pack(pady=4)

        styled_btn(self, "💸  Send Payment Request", self._charge,
                   bg=C["success"], fg=C["white"], padx=20, pady=10).pack(pady=6)
        styled_btn(self, "Cancel", self.destroy,
                   bg=C["surface2"], fg=C["text2"], padx=16, pady=8).pack()

    def _charge(self):
        phone = self.phone_var.get().strip()
        email = self.email_var.get().strip() or "customer@maslim360.com"
        provider = self.network_var.get()
        if len(phone) < 10:
            self.status_var.set("⚠  Enter a valid 10-digit phone number")
            return
        self.status_var.set("⏳  Sending request to Paystack…")
        self.update()

        def _do():
            resp = self.controller.initiate_paystack_charge(phone, self.amount, email, provider)
            self.after(0, lambda: self._handle_response(resp))

        threading.Thread(target=_do, daemon=True).start()

    def _handle_response(self, resp):
        if resp.get("status") and resp.get("data"):
            data = resp["data"]
            ref  = data.get("reference", "N/A")
            st   = data.get("status", "")
            msg  = data.get("display_text") or data.get("message") or "Prompt sent to phone"
            if st == "send_otp":
                self.status_var.set(f"🔔  {msg}")
                # Ask user for OTP
                otp = simpledialog.askstring("OTP Required", msg, parent=self)
                if otp:
                    self.status_var.set("⏳  Submitting OTP to Paystack…")
                    self.update()
                    def _do_otp():
                        otp_resp = self.controller.submit_paystack_otp(otp, ref)
                        self.after(0, lambda: self._handle_response(otp_resp))
                    threading.Thread(target=_do_otp, daemon=True).start()
                else:
                    self.status_var.set("❌  OTP entry cancelled.")
            elif st in ("pending", "pay_offline"):
                self.status_var.set(f"✅  {msg}  (Ref: {ref})")
                self.after(4000, lambda: self._finalise(ref))
            elif st == "success":
                self._finalise(ref)
            else:
                self.status_var.set(f"⚠  {msg}  (Status: {st})")
        else:
            msg = resp.get("message", "Payment request failed")
            # For general exceptions or HTTPErrors where Paystack returns "message"
            self.status_var.set(f"❌  {msg}")

    def _finalise(self, ref):
        self.on_success(ref)
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT FORM DIALOG  (add / edit)
# ═══════════════════════════════════════════════════════════════════════════════
class ProductFormDialog(tk.Toplevel):
    def __init__(self, parent, controller, product=None, on_save=None, prefill_barcode=None):
        super().__init__(parent)
        self.controller = controller
        self.product    = product
        self.on_save    = on_save
        title = "Edit Product" if product else "Add New Product"
        self.title(f"📦  MasLim360 — {title}")
        self.configure(bg=C["bg"])
        self.geometry("520x620")
        self.resizable(False, False)
        self.grab_set()
        self.prefill_barcode = prefill_barcode
        self._build()

    def _build(self):
        tk.Label(self, text="📦  Product Details", font=FONT_TITLE,
                 bg=C["bg"], fg=C["accent"]).pack(pady=(20, 4))

        form = card_frame(self)
        form.pack(fill=tk.BOTH, padx=24, pady=12, expand=True)

        fields = [
            ("Product Name",   "name",       self.product['name']       if self.product else ""),
            ("Category",       "category",   self.product['category']   if self.product else ""),
            ("Selling Price",  "price",      self.product['price']      if self.product else ""),
            ("Cost Price",     "cost_price", self.product.get('cost_price', 0) if self.product else ""),
            ("Stock Qty",      "qty",        self.product['stock']      if self.product else ""),
            ("Barcode",        "barcode",    self.product['barcode']    if self.product else (self.prefill_barcode or "")),
            ("Supplier",       "supplier",   self.product.get('supplier', '') if self.product else ""),
        ]
        self._vars = {}
        for i, (label, key, default) in enumerate(fields):
            row = tk.Frame(form, bg=C["surface"])
            row.pack(fill=tk.X, padx=16, pady=4)
            tk.Label(row, text=label, font=FONT_SMALL, width=14, anchor="w",
                     bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
            v = tk.StringVar(value=str(default))
            self._vars[key] = v
            tk.Entry(row, textvariable=v, font=FONT_BODY,
                     bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                     relief=tk.FLAT, bd=6, width=26).pack(side=tk.LEFT, padx=6, ipady=5)

        # Scan barcode button inside form
        bf = tk.Frame(form, bg=C["surface"])
        bf.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(bf, text="", width=14, bg=C["surface"]).pack(side=tk.LEFT)
        styled_btn(bf, "📷  Scan Barcode", self._open_scanner,
                   bg=C["accent2"], fg=C["white"], padx=10, pady=4).pack(side=tk.LEFT)

        # Buttons
        bb = tk.Frame(self, bg=C["bg"])
        bb.pack(pady=10)
        styled_btn(bb, "💾  Save Product", self._save,
                   bg=C["success"], fg=C["white"], padx=20, pady=8).pack(side=tk.LEFT, padx=8)
        styled_btn(bb, "Cancel", self.destroy,
                   bg=C["surface2"], fg=C["text2"], padx=16, pady=8).pack(side=tk.LEFT)

    def _open_scanner(self):
        BarcodeScannerWindow(self, self._barcode_scanned)

    def _barcode_scanned(self, barcode):
        self._vars['barcode'].set(barcode)

    def _save(self):
        try:
            name     = self._vars['name'].get().strip()
            category = self._vars['category'].get().strip()
            price    = float(self._vars['price'].get())
            cost     = float(self._vars['cost_price'].get() or 0)
            qty      = int(self._vars['qty'].get())
            barcode  = self._vars['barcode'].get().strip()
            supplier = self._vars['supplier'].get().strip()
            if not name or not barcode:
                messagebox.showerror("Error", "Name and Barcode are required", parent=self)
                return
            if self.product:
                ok = self.controller.update_product(
                    self.product['id'], name, category, price, qty, barcode, supplier, cost)
            else:
                ok = self.controller.add_product(name, category, price, qty, barcode, supplier, cost)
            if ok:
                if self.on_save: self.on_save()
                self.destroy()
            else:
                messagebox.showerror("Error", "Barcode already exists", parent=self)
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric value", parent=self)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN POS APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class POSApp:
    def __init__(self, root, controller):
        self.root       = root
        self.controller = controller
        self.cart       = []
        self.current_customer_id = None

        self.root.title("MasLim360 Store — POS")
        self.root.geometry("1440x860")
        self.root.minsize(1280, 720)
        self.root.configure(bg=C["bg"])

        # ttk styling
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("Dark.TNotebook",
                      background=C["bg"], tabmargins=[4, 4, 0, 0])
        st.configure("Dark.TNotebook.Tab",
                      background=C["surface2"], foreground=C["text2"],
                      font=FONT_SUB, padding=[16, 8])
        st.map("Dark.TNotebook.Tab",
               background=[("selected", C["surface"])],
               foreground=[("selected", C["accent"])])
        st.configure("Tree.Treeview",
                      background=C["surface"], fieldbackground=C["surface"],
                      foreground=C["text"], font=FONT_BODY, rowheight=26)
        st.configure("Tree.Treeview.Heading",
                      background=C["surface2"], foreground=C["accent"],
                      font=FONT_SUB)
        st.map("Tree.Treeview",
               background=[("selected", C["accent2"])],
               foreground=[("selected", C["white"])])
        st.configure("TScrollbar", background=C["surface2"], troughcolor=C["bg"])

        self.show_login_screen()

    # ─── Navigation ────────────────────────────────────────────────────────────
    def clear_screen(self):
        for w in self.root.winfo_children():
            w.destroy()

    def show_login_screen(self):
        self.clear_screen()
        self.cart = []

        bg = tk.Canvas(self.root, bg=C["bg"], highlightthickness=0)
        bg.pack(fill=tk.BOTH, expand=True)

        # Decorative circles
        bg.create_oval(-100, -100, 400, 400, fill="#FEF08A", outline="")
        bg.create_oval(900, 500, 1500, 1100, fill="#E5E7EB", outline="")
        bg.create_oval(1100, -80, 1500, 300, fill="#FDE047", outline="")

        # Center card
        card = tk.Frame(bg, bg=C["surface"], padx=50, pady=50)
        bg.create_window(720, 430, window=card, width=480)

        # Logo / Title
        tk.Label(card, text="🏪", font=("Segoe UI Emoji", 40),
                 bg=C["surface"], fg=C["accent"]).pack()
        tk.Label(card, text="MasLim360 Store",
                 font=("Segoe UI", 26, "bold"), bg=C["surface"], fg=C["accent"]).pack()
        tk.Label(card, text="Point of Sale System",
                 font=FONT_BODY, bg=C["surface"], fg=C["text3"]).pack(pady=(0, 30))

        # Inputs
        for label, attr, show in [("Username", "login_user", ""), ("Password", "login_pass", "●")]:
            tk.Label(card, text=label, font=FONT_SMALL, anchor="w",
                     bg=C["surface"], fg=C["text2"]).pack(fill=tk.X)
            ef = tk.Frame(card, bg=C["border"], pady=1)
            ef.pack(fill=tk.X, pady=(2, 12))
            e = tk.Entry(ef, show=show, font=("Segoe UI", 13),
                         bg=C["surface2"], fg=C["text"], insertbackground=C["accent"],
                         relief=tk.FLAT, bd=6)
            e.pack(fill=tk.X)
            setattr(self, attr, e)
        self.login_pass.bind("<Return>", lambda _: self._do_login())

        styled_btn(card, "  Sign In  →", self._do_login,
                   bg=C["accent"], fg=C["white"],
                   font=("Segoe UI", 12, "bold"),
                   padx=30, pady=10).pack(pady=10, fill=tk.X)

        # Hint
        hint = tk.Frame(card, bg=C["surface2"])
        hint.pack(fill=tk.X, pady=(10, 0))
        tk.Label(hint, text="Default credentials",
                 font=FONT_SMALL, bg=C["surface2"], fg=C["text3"]).pack(pady=(6, 2))
        for row in [("admin / admin123", "Administrator"),
                    ("manager / manager123", "Manager"),
                    ("cashier / cashier123", "Cashier")]:
            tk.Label(hint, text=f"  {row[0]}   ({row[1]})",
                     font=FONT_SMALL, bg=C["surface2"], fg=C["text2"]).pack(anchor="w", padx=10)
        tk.Label(hint, text="", bg=C["surface2"]).pack(pady=4)

    def _do_login(self):
        if self.controller.login(self.login_user.get(), self.login_pass.get()):
            self.show_main()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")

    # ─── Main Interface ─────────────────────────────────────────────────────────
    def show_main(self):
        self.clear_screen()

        # Top bar
        topbar = tk.Frame(self.root, bg=C["surface"], height=56)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)

        tk.Label(topbar, text="🏪  MasLim360 Store",
                 font=("Segoe UI", 16, "bold"), bg=C["surface"], fg=C["accent"]).pack(side=tk.LEFT, padx=20)

        user = self.controller.current_user
        tk.Label(topbar, text=f"👤  {user['full_name']}  ·  {user['role']}",
                 font=FONT_BODY, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT, padx=16)

        # Clock
        self.clock_var = tk.StringVar()
        tk.Label(topbar, textvariable=self.clock_var, font=FONT_MONO,
                 bg=C["surface"], fg=C["text3"]).pack(side=tk.LEFT, padx=20)
        self._tick_clock()

        styled_btn(topbar, "⏻  Logout", self.show_login_screen,
                   bg=C["danger"], fg=C["white"], padx=12, pady=6).pack(side=tk.RIGHT, padx=20)

        # Notebook
        nb = ttk.Notebook(self.root, style="Dark.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tabs = [
            ("🛒  Sales",     self._build_sales_tab),
            ("📦  Products",  self._build_products_tab),
            ("👥  Customers", self._build_customers_tab),
            ("📊  Reports",   self._build_reports_tab),
            ("🏠  Dashboard", self._build_dashboard_tab),
        ]
        if user['role'] == 'Administrator':
            tabs.append(("⚙  Users", self._build_users_tab))

        for title, builder in tabs:
            frame = tk.Frame(nb, bg=C["bg"])
            nb.add(frame, text=title)
            builder(frame)

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("🕐  %H:%M:%S   %d %b %Y"))
        self.root.after(1000, self._tick_clock)

    # ─── DASHBOARD TAB ──────────────────────────────────────────────────────────
    def _build_dashboard_tab(self, parent):
        parent.configure(bg=C["bg"])
        tk.Label(parent, text="🏠  Store Dashboard",
                 font=FONT_TITLE, bg=C["bg"], fg=C["accent"]).pack(pady=(18, 6))
        tk.Label(parent, text="Live overview of MasLim360 operations",
                 font=FONT_BODY, bg=C["bg"], fg=C["text2"]).pack(pady=(0, 18))

        stats_row = tk.Frame(parent, bg=C["bg"])
        stats_row.pack(fill=tk.X, padx=24, pady=4)

        def stat_card(parent, icon, label, value, color):
            c = card_frame(parent)
            c.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=8, pady=4)
            tk.Label(c, text=icon, font=("Segoe UI Emoji", 28),
                     bg=C["surface"], fg=color).pack(pady=(16, 2))
            tk.Label(c, text=str(value), font=("Segoe UI", 20, "bold"),
                     bg=C["surface"], fg=color).pack()
            tk.Label(c, text=label, font=FONT_SMALL,
                     bg=C["surface"], fg=C["text2"]).pack(pady=(2, 16))

        s = self.controller.get_dashboard_stats()
        stat_card(stats_row, "🛒", "Today's Sales",      s['sales_count'],    C["accent"])
        stat_card(stats_row, "💵", "Today's Revenue",    f"GH₵{s['sales_total']:,.2f}", C["success"])
        stat_card(stats_row, "📦", "Total Products",     s['total_products'],  C["accent3"])
        stat_card(stats_row, "⚠",  "Low Stock Items",   s['low_stock'],       C["danger"])
        stat_card(stats_row, "👥", "Customers",          s['total_customers'], C["accent2"])
        stat_card(stats_row, "📅", "Monthly Revenue",   f"GH₵{s['monthly_revenue']:,.2f}", C["accent"])

        # Low stock table
        low_frame = card_frame(parent)
        low_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=16)
        tk.Label(low_frame, text="⚠  Low Stock Alert  (≤10 units)",
                 font=FONT_HEAD, bg=C["surface"], fg=C["danger"]).pack(pady=(12, 4))

        cols = ("Name", "Category", "Price", "Stock", "Barcode")
        tv = ttk.Treeview(low_frame, columns=cols, show="headings",
                          style="Tree.Treeview", height=8)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=160)
        tv.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        rows = self.controller.get_inventory_report()
        for r in rows:
            if r[4] <= 10:
                tag = "critical" if r[4] == 0 else "low"
                tv.insert("", tk.END, values=(r[1], r[2], f"GH₵{r[3]:.2f}", r[4], r[5]),
                          tags=(tag,))
        tv.tag_configure("critical", foreground=C["danger"])
        tv.tag_configure("low",      foreground=C["warning"])

        styled_btn(low_frame, "🔄  Refresh",
                   lambda: self._refresh_dashboard(parent),
                   bg=C["surface2"], fg=C["text2"], padx=12, pady=5).pack(pady=8)

    def _refresh_dashboard(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        self._build_dashboard_tab(parent)

    # ─── SALES TAB ──────────────────────────────────────────────────────────────
    def _build_sales_tab(self, parent):
        parent.configure(bg=C["bg"])

        # Layout: left panel + right cart
        left = tk.Frame(parent, bg=C["bg"], width=480)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(12, 4), pady=8)
        left.pack_propagate(False)

        right = tk.Frame(parent, bg=C["bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 12), pady=8)

        # ── LEFT PANEL ───────────────────────────────────────────────
        tk.Label(left, text="🛒  Point of Sale",
                 font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(anchor="w", pady=(0, 8))

        # Product search card
        sc = card_frame(left)
        sc.pack(fill=tk.X, pady=4)
        tk.Label(sc, text="Search / Add Product", font=FONT_SUB,
                 bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 4))

        search_row = tk.Frame(sc, bg=C["surface"])
        search_row.pack(fill=tk.X, padx=12)
        self.sale_search_var = tk.StringVar()
        se = tk.Entry(search_row, textvariable=self.sale_search_var,
                      font=FONT_BODY, bg=C["surface2"], fg=C["text"],
                      insertbackground=C["text"], relief=tk.FLAT, bd=6, width=28)
        se.pack(side=tk.LEFT, ipady=6, padx=(0, 4))
        se.bind("<Return>", lambda _: self._sale_add_by_search())
        styled_btn(search_row, "➕ Add", self._sale_add_by_search,
                   padx=8, pady=5).pack(side=tk.LEFT)

        # Barcode row
        br = tk.Frame(sc, bg=C["surface"])
        br.pack(fill=tk.X, padx=12, pady=(4, 4))
        tk.Label(br, text="Barcode:", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
        self.sale_bc_var = tk.StringVar()
        be = tk.Entry(br, textvariable=self.sale_bc_var,
                      font=FONT_MONO, bg=C["surface2"], fg=C["text"],
                      insertbackground=C["text"], relief=tk.FLAT, bd=6, width=18)
        be.pack(side=tk.LEFT, padx=4, ipady=5)
        be.bind("<Return>", lambda _: self._sale_add_by_barcode())
        styled_btn(br, "📷 Scan", lambda: BarcodeScannerWindow(self.root, self._sale_barcode_scanned),
                   bg=C["accent2"], fg=C["white"], padx=8, pady=4).pack(side=tk.LEFT, padx=4)

        # Suggestions dropdown
        self.sale_suggestions = tk.Listbox(sc, bg=C["surface2"], fg=C["text"],
                                            font=FONT_BODY, height=0, relief=tk.FLAT,
                                            selectbackground=C["accent"], bd=0)
        self.sale_suggestions.pack(fill=tk.X, padx=12)
        self.sale_suggestions.bind("<ButtonRelease-1>", self._sale_suggestion_select)
        self.sale_search_var.trace("w", self._sale_update_suggestions)
        tk.Label(sc, text="", bg=C["surface"]).pack(pady=4)

        # Qty row
        qf = tk.Frame(sc, bg=C["surface"])
        qf.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(qf, text="Qty:", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
        self.sale_qty_var = tk.StringVar(value="1")
        tk.Spinbox(qf, from_=1, to=999, textvariable=self.sale_qty_var,
                   width=5, font=FONT_BODY, bg=C["surface2"], fg=C["text"],
                   buttonbackground=C["surface"], relief=tk.FLAT, bd=6).pack(side=tk.LEFT, padx=6)

        # Customer card
        cc = card_frame(left)
        cc.pack(fill=tk.X, pady=4)
        tk.Label(cc, text="Customer (Optional)", font=FONT_SUB,
                 bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 4))
        self.cust_var = tk.StringVar()
        self.cust_combo = ttk.Combobox(cc, textvariable=self.cust_var, state="readonly",
                                       font=FONT_BODY, width=34)
        self._reload_customers()
        self.cust_combo.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Discount card
        dc = card_frame(left)
        dc.pack(fill=tk.X, pady=4)
        tk.Label(dc, text="Discount", font=FONT_SUB, bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 4))
        dr = tk.Frame(dc, bg=C["surface"])
        dr.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.discount_var = tk.StringVar(value="0")
        tk.Entry(dr, textvariable=self.discount_var, font=FONT_BODY,
                 bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                 relief=tk.FLAT, bd=6, width=12).pack(side=tk.LEFT, ipady=5)
        tk.Label(dr, text="GH₵", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT, padx=4)

        # Payment card
        pc = card_frame(left)
        pc.pack(fill=tk.X, pady=4)
        tk.Label(pc, text="Payment Method", font=FONT_SUB, bg=C["surface"], fg=C["text"]).pack(anchor="w", padx=12, pady=(10, 4))
        self.pay_var = tk.StringVar(value="Cash")
        methods = ["Cash", "Mobile Money (Paystack)", "Card", "Bank Transfer", "Split Payment"]
        self.pay_combo = ttk.Combobox(pc, textvariable=self.pay_var, values=methods,
                                      state="readonly", font=FONT_BODY, width=34)
        self.pay_combo.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Checkout button
        styled_btn(left, "💳  Process Sale", self._process_sale,
                   bg=C["success"], fg=C["white"],
                   font=("Segoe UI", 13, "bold"), padx=20, pady=12).pack(fill=tk.X, pady=8)

        # ── RIGHT PANEL (Cart) ────────────────────────────────────────
        cart_header = tk.Frame(right, bg=C["bg"])
        cart_header.pack(fill=tk.X)
        tk.Label(cart_header, text="🧾  Cart",
                 font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        styled_btn(cart_header, "🗑 Clear", self._clear_cart,
                   bg=C["danger"], fg=C["white"], padx=8, pady=4).pack(side=tk.RIGHT)

        # Cart treeview
        cart_card = card_frame(right)
        cart_card.pack(fill=tk.BOTH, expand=True, pady=(8, 4))
        cart_cols = ("Product", "Qty", "Unit Price", "Total")
        self.cart_tree = ttk.Treeview(cart_card, columns=cart_cols, show="headings",
                                      style="Tree.Treeview")
        for col, w in zip(cart_cols, [280, 60, 120, 120]):
            self.cart_tree.heading(col, text=col)
            self.cart_tree.column(col, width=w, anchor="center")
        self.cart_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(cart_card, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Remove selected btn
        styled_btn(cart_card, "✖  Remove Selected", self._remove_cart_item,
                   bg=C["surface2"], fg=C["text2"], padx=10, pady=4).pack(pady=4)

        # Total card
        tc = card_frame(right)
        tc.pack(fill=tk.X, pady=4)
        totrow = tk.Frame(tc, bg=C["surface"])
        totrow.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(totrow, text="Total:", font=("Segoe UI", 15, "bold"),
                 bg=C["surface"], fg=C["text"]).pack(side=tk.LEFT)
        self.total_var = tk.StringVar(value="GH₵ 0.00")
        tk.Label(totrow, textvariable=self.total_var,
                 font=("Segoe UI", 22, "bold"), bg=C["surface"], fg=C["success"]).pack(side=tk.RIGHT)

    def _sale_update_suggestions(self, *_):
        q = self.sale_search_var.get().strip()
        self.sale_suggestions.delete(0, tk.END)
        if len(q) < 2:
            self.sale_suggestions.config(height=0)
            return
        results = self.controller.search_products(q)
        if results:
            self.sale_suggestions.config(height=min(len(results), 6))
            for p in results:
                self.sale_suggestions.insert(tk.END, f"{p['name']}  |  {p['barcode']}  |  GH₵{p['price']:.2f}")
        else:
            self.sale_suggestions.config(height=0)

    def _sale_suggestion_select(self, _):
        sel = self.sale_suggestions.curselection()
        if not sel: return
        text = self.sale_suggestions.get(sel[0])
        name = text.split("|")[0].strip()
        self.sale_search_var.set(name)
        self.sale_suggestions.config(height=0)
        self._sale_add_by_search()

    def _sale_add_by_search(self):
        name = self.sale_search_var.get().strip()
        if not name: return
        p = self.controller.get_product_by_name(name)
        if not p:
            results = self.controller.search_products(name)
            p = results[0] if results else None
        if p:
            self._add_to_cart(p)
            self.sale_search_var.set("")
            self.sale_suggestions.config(height=0)
        else:
            messagebox.showwarning("Not Found", f"Product '{name}' not found")

    def _sale_add_by_barcode(self):
        bc = self.sale_bc_var.get().strip()
        if not bc: return
        p = self.controller.get_product_by_barcode(bc)
        if p:
            self._add_to_cart(p)
            self.sale_bc_var.set("")
        else:
            messagebox.showwarning("Not Found", f"Barcode '{bc}' not found")

    def _sale_barcode_scanned(self, barcode):
        p = self.controller.get_product_by_barcode(barcode)
        if p:
            self._add_to_cart(p)
        else:
            if messagebox.askyesno("New Barcode", f"Barcode '{barcode}' not found.\nAdd as new product?"):
                ProductFormDialog(self.root, self.controller,
                                  on_save=None, prefill_barcode=barcode)

    def _add_to_cart(self, product):
        try:
            qty = int(self.sale_qty_var.get())
        except ValueError:
            qty = 1
        if product['stock'] < qty:
            messagebox.showwarning("Low Stock", f"Only {product['stock']} units available")
            return
        for it in self.cart:
            if it['id'] == product['id']:
                it['qty'] += qty
                it['total'] = round(it['qty'] * it['price'], 2)
                self._refresh_cart()
                return
        self.cart.append({
            'id':    product['id'],
            'name':  product['name'],
            'price': product['price'],
            'qty':   qty,
            'total': round(product['price'] * qty, 2),
        })
        self._refresh_cart()

    def _refresh_cart(self):
        for row in self.cart_tree.get_children():
            self.cart_tree.delete(row)
        for it in self.cart:
            self.cart_tree.insert("", tk.END, values=(
                it['name'], it['qty'],
                f"GH₵{it['price']:.2f}", f"GH₵{it['total']:.2f}"))
        try:
            disc = float(self.discount_var.get() or 0)
        except ValueError:
            disc = 0
        subtotal = sum(it['total'] for it in self.cart)
        total    = max(subtotal - disc, 0)
        self.total_var.set(f"GH₵ {total:,.2f}")

    def _remove_cart_item(self):
        sel = self.cart_tree.selection()
        if not sel: return
        idx = self.cart_tree.index(sel[0])
        self.cart.pop(idx)
        self._refresh_cart()

    def _clear_cart(self):
        self.cart.clear()
        self._refresh_cart()

    def _reload_customers(self):
        custs = self.controller.get_all_customers()
        vals = ["— No Customer —"] + [f"{c[0]} — {c[1]}" for c in custs]
        self.cust_combo['values'] = vals
        self.cust_combo.set("— No Customer —")

    def _process_sale(self):
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Add items to the cart first")
            return

        try:
            disc = float(self.discount_var.get() or 0)
        except ValueError:
            disc = 0

        method = self.pay_var.get()
        cust_sel = self.cust_var.get()
        cid = None
        if cust_sel and "—" not in cust_sel:
            cid = int(cust_sel.split("—")[0].strip())

        subtotal = sum(it['total'] for it in self.cart)
        total    = max(subtotal - disc, 0)

        if method == "Mobile Money (Paystack)":
            MobileMoneyDialog(self.root, self.controller, total,
                              on_success=lambda ref: self._finish_sale(method, cid, disc, ref))
        else:
            self._finish_sale(method, cid, disc)

    def _finish_sale(self, method, cid, disc, paystack_ref=None):
        ok, msg = self.controller.process_sale(
            self.cart, method, cid, disc, paystack_ref)
        if ok:
            self.cart.clear()
            self._refresh_cart()
            self.discount_var.set("0")
            messagebox.showinfo("✅  Sale Complete", msg)
        else:
            messagebox.showerror("❌  Sale Failed", msg)

    # ─── PRODUCTS TAB ──────────────────────────────────────────────────────────
    def _build_products_tab(self, parent):
        parent.configure(bg=C["bg"])

        # Toolbar
        tb = tk.Frame(parent, bg=C["bg"])
        tb.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(tb, text="📦  Product Inventory", font=FONT_HEAD,
                 bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        styled_btn(tb, "🔄 Refresh", lambda: self._refresh_products_tab(parent),
                   bg=C["surface2"], fg=C["text2"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)
        styled_btn(tb, "📷 Scan & Add", self._scan_add_product,
                   bg=C["accent2"], fg=C["white"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)
        styled_btn(tb, "➕ New Product", lambda: ProductFormDialog(
                   self.root, self.controller, on_save=lambda: self._refresh_products_tab(parent)),
                   bg=C["accent"], fg=C["bg"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)

        # Search bar
        sf = tk.Frame(parent, bg=C["bg"])
        sf.pack(fill=tk.X, padx=12, pady=4)
        self.prod_search_var = tk.StringVar()
        se = tk.Entry(sf, textvariable=self.prod_search_var,
                      font=FONT_BODY, bg=C["surface2"], fg=C["text"],
                      insertbackground=C["text"], relief=tk.FLAT, bd=6, width=40)
        se.pack(side=tk.LEFT, ipady=6, padx=(0, 6))
        se.bind("<Return>", lambda _: self._filter_products())
        styled_btn(sf, "🔍 Search", self._filter_products,
                   bg=C["surface2"], fg=C["text2"], padx=8, pady=5).pack(side=tk.LEFT)
        styled_btn(sf, "✖ Clear", lambda: (self.prod_search_var.set(""), self._filter_products()),
                   bg=C["surface2"], fg=C["text3"], padx=8, pady=5).pack(side=tk.LEFT, padx=4)

        # Tree
        tc = card_frame(parent)
        tc.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        cols = ("ID","Name","Category","Price","Cost","Stock","Barcode","Supplier")
        self.prod_tree = ttk.Treeview(tc, columns=cols, show="headings",
                                      style="Tree.Treeview")
        widths = [40, 200, 120, 90, 90, 70, 120, 160]
        for col, w in zip(cols, widths):
            self.prod_tree.heading(col, text=col)
            self.prod_tree.column(col, width=w, anchor="center")
        self.prod_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(tc, orient="vertical", command=self.prod_tree.yview)
        self.prod_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Action buttons
        ab = tk.Frame(parent, bg=C["bg"])
        ab.pack(fill=tk.X, padx=12, pady=4)
        styled_btn(ab, "✏  Edit", self._edit_product,
                   bg=C["accent3"], fg=C["bg"], padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "🗑  Delete", self._delete_product,
                   bg=C["danger"], fg=C["white"], padx=10, pady=5).pack(side=tk.LEFT, padx=4)

        self._parent_products = parent
        self._load_products()

    def _load_products(self, query=""):
        for row in self.prod_tree.get_children():
            self.prod_tree.delete(row)
        if query:
            rows = self.controller.search_products(query)
            rows = [(r['id'],r['name'],r['category'],r['price'],
                     r.get('cost_price',0),r['stock'],r['barcode'],r.get('supplier','')) for r in rows]
        else:
            rows = self.controller.get_all_products()
        for r in rows:
            tag = "low" if r[4] <= 10 else ("medium" if r[4] <= 20 else "")
            self.prod_tree.insert("", tk.END, values=(
                r[0], r[1], r[2],
                f"GH₵{r[3]:.2f}", f"GH₵{r[7] if len(r)>7 else 0:.2f}",
                r[4], r[5], r[6] if len(r)>6 else ""), tags=(tag,))
        self.prod_tree.tag_configure("low",    foreground=C["danger"])
        self.prod_tree.tag_configure("medium", foreground=C["warning"])

    def _filter_products(self):
        self._load_products(self.prod_search_var.get().strip())

    def _refresh_products_tab(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        self._build_products_tab(parent)

    def _scan_add_product(self):
        BarcodeScannerWindow(self.root, self._scanned_for_product)

    def _scanned_for_product(self, barcode):
        p = self.controller.get_product_by_barcode(barcode)
        if p:
            messagebox.showinfo("Found", f"Product already exists:\n{p['name']}")
        else:
            ProductFormDialog(self.root, self.controller,
                              on_save=lambda: self._load_products(),
                              prefill_barcode=barcode)

    def _get_selected_product(self):
        sel = self.prod_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a product first")
            return None
        vals = self.prod_tree.item(sel[0])['values']
        return self.controller.get_product_by_barcode(str(vals[6]))

    def _edit_product(self):
        p = self._get_selected_product()
        if p:
            ProductFormDialog(self.root, self.controller, product=p,
                              on_save=lambda: self._load_products())

    def _delete_product(self):
        p = self._get_selected_product()
        if p and messagebox.askyesno("Confirm", f"Delete '{p['name']}'?"):
            self.controller.delete_product(p['id'])
            self._load_products()

    # ─── CUSTOMERS TAB ──────────────────────────────────────────────────────────
    def _build_customers_tab(self, parent):
        parent.configure(bg=C["bg"])

        tb = tk.Frame(parent, bg=C["bg"])
        tb.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(tb, text="👥  Customers", font=FONT_HEAD,
                 bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        styled_btn(tb, "➕ Add", self._add_customer,
                   bg=C["accent"], fg=C["bg"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)

        tc = card_frame(parent)
        tc.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        cols = ("ID","Name","Phone","Email","Address","Loyalty Pts")
        self.cust_tree = ttk.Treeview(tc, columns=cols, show="headings",
                                      style="Tree.Treeview")
        widths = [40, 180, 120, 200, 220, 90]
        for col, w in zip(cols, widths):
            self.cust_tree.heading(col, text=col)
            self.cust_tree.column(col, width=w)
        self.cust_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(tc, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        ab = tk.Frame(parent, bg=C["bg"])
        ab.pack(fill=tk.X, padx=12, pady=4)
        styled_btn(ab, "✏ Edit",    self._edit_customer,   bg=C["accent3"], fg=C["bg"],   padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "🗑 Delete", self._delete_customer, bg=C["danger"],  fg=C["white"],padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "📋 History",self._customer_history,bg=C["surface2"],fg=C["text2"],padx=10, pady=5).pack(side=tk.LEFT, padx=4)

        self._load_customers_tree()

    def _load_customers_tree(self):
        for row in self.cust_tree.get_children():
            self.cust_tree.delete(row)
        for c in self.controller.get_all_customers():
            self.cust_tree.insert("", tk.END, values=c[:6])

    def _cust_dialog(self, data=None):
        dlg = tk.Toplevel(self.root)
        dlg.title("Customer")
        dlg.configure(bg=C["bg"])
        dlg.geometry("440x400")
        dlg.grab_set()
        tk.Label(dlg, text="Customer Details", font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(pady=16)
        card = card_frame(dlg)
        card.pack(fill=tk.BOTH, padx=20, pady=4, expand=True)
        fields = [("Name","name"),("Phone","phone"),("Email","email"),("Address","address")]
        vars_ = {}
        for lbl, key in fields:
            row = tk.Frame(card, bg=C["surface"])
            row.pack(fill=tk.X, padx=12, pady=4)
            tk.Label(row, text=lbl, width=10, anchor="w", font=FONT_SMALL,
                     bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
            v = tk.StringVar(value=data.get(key,'') if data else "")
            vars_[key] = v
            tk.Entry(row, textvariable=v, font=FONT_BODY, width=28,
                     bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                     relief=tk.FLAT, bd=6).pack(side=tk.LEFT, padx=6, ipady=5)
        def _save():
            if data:
                self.controller.update_customer(data['id'], vars_['name'].get(),
                    vars_['phone'].get(), vars_['email'].get(), vars_['address'].get())
            else:
                self.controller.add_customer(vars_['name'].get(), vars_['phone'].get(),
                    vars_['email'].get(), vars_['address'].get())
            self._load_customers_tree()
            self._reload_customers()
            dlg.destroy()
        styled_btn(dlg, "💾 Save", _save, bg=C["success"], fg=C["white"], padx=18, pady=8).pack(pady=10)

    def _add_customer(self):    self._cust_dialog()
    def _edit_customer(self):
        sel = self.cust_tree.selection()
        if not sel: return
        cid = self.cust_tree.item(sel[0])['values'][0]
        self._cust_dialog(self.controller.get_customer_by_id(cid))
    def _delete_customer(self):
        sel = self.cust_tree.selection()
        if not sel: return
        cid = self.cust_tree.item(sel[0])['values'][0]
        if messagebox.askyesno("Confirm", "Delete this customer?"):
            self.controller.delete_customer(cid)
            self._load_customers_tree()
    def _customer_history(self):
        sel = self.cust_tree.selection()
        if not sel: return
        cid  = self.cust_tree.item(sel[0])['values'][0]
        name = self.cust_tree.item(sel[0])['values'][1]
        hist = self.controller.get_customer_purchase_history(cid)
        dlg = tk.Toplevel(self.root)
        dlg.title(f"History — {name}")
        dlg.configure(bg=C["bg"])
        dlg.geometry("700x440")
        tk.Label(dlg, text=f"Purchase History: {name}", font=FONT_HEAD,
                 bg=C["bg"], fg=C["accent"]).pack(pady=12)
        cols = ("Sale#","Date","Total","Payment","Items")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", style="Tree.Treeview")
        for c in cols: tv.heading(c, text=c)
        tv.column("Items", width=300)
        tv.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        for h in hist:
            tv.insert("", tk.END, values=(h[0], h[1], f"GH₵{h[2]:.2f}", h[3], h[4]))

    # ─── REPORTS TAB ───────────────────────────────────────────────────────────
    def _build_reports_tab(self, parent):
        parent.configure(bg=C["bg"])

        tb = tk.Frame(parent, bg=C["bg"])
        tb.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(tb, text="📊  Sales Reports", font=FONT_HEAD,
                 bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        styled_btn(tb, "📥 Export CSV", self._export_csv,
                   bg=C["accent3"], fg=C["bg"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)
        styled_btn(tb, "🔄 Refresh", self._load_sales_report,
                   bg=C["surface2"], fg=C["text2"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)

        # Date filter
        df = card_frame(parent)
        df.pack(fill=tk.X, padx=12, pady=4)
        dr = tk.Frame(df, bg=C["surface"])
        dr.pack(fill=tk.X, padx=12, pady=10)
        tk.Label(dr, text="From:", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
        self.rpt_from = tk.Entry(dr, font=FONT_BODY, bg=C["surface2"], fg=C["text"],
                                  insertbackground=C["text"], relief=tk.FLAT, bd=6, width=14)
        self.rpt_from.insert(0, datetime.now().strftime("%Y-%m-01"))
        self.rpt_from.pack(side=tk.LEFT, padx=6, ipady=5)
        tk.Label(dr, text="To:", font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT, padx=(12,0))
        self.rpt_to = tk.Entry(dr, font=FONT_BODY, bg=C["surface2"], fg=C["text"],
                                insertbackground=C["text"], relief=tk.FLAT, bd=6, width=14)
        self.rpt_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.rpt_to.pack(side=tk.LEFT, padx=6, ipady=5)
        styled_btn(dr, "🔍 Filter", self._load_sales_report,
                   bg=C["accent"], fg=C["bg"], padx=10, pady=5).pack(side=tk.LEFT, padx=8)

        # Table
        tc = card_frame(parent)
        tc.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        cols = ("Sale#","Date","Total","Payment","Cashier","Customer")
        self.report_tree = ttk.Treeview(tc, columns=cols, show="headings", style="Tree.Treeview")
        for col, w in zip(cols, [60,160,100,140,120,140]):
            self.report_tree.heading(col, text=col)
            self.report_tree.column(col, width=w)
        self.report_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(tc, orient="vertical", command=self.report_tree.yview)
        self.report_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Summary
        self.rpt_summary = tk.StringVar()
        tk.Label(parent, textvariable=self.rpt_summary, font=FONT_SUB,
                 bg=C["bg"], fg=C["success"]).pack(pady=4)

        self._load_sales_report()

    def _load_sales_report(self):
        for row in self.report_tree.get_children():
            self.report_tree.delete(row)
        start = self.rpt_from.get().strip() + " 00:00:00"
        end   = self.rpt_to.get().strip()   + " 23:59:59"
        rows  = self.controller.get_sales_report(start, end)
        total = 0
        for r in rows:
            self.report_tree.insert("", tk.END,
                values=(f"#{r[0]:06d}", r[1], f"GH₵{r[2]:.2f}", r[3], r[4], r[5]))
            total += r[2]
        self.rpt_summary.set(f"  {len(rows)} transactions  ·  Total: GH₵{total:,.2f}")

    def _export_csv(self):
        try:
            import csv
            fn = f"maslim360_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            rows = self.controller.get_sales_report(
                self.rpt_from.get() + " 00:00:00",
                self.rpt_to.get()   + " 23:59:59")
            with open(fn, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["Sale#","Date","Total","Payment","Cashier","Customer"])
                for r in rows:
                    w.writerow(r)
            messagebox.showinfo("Exported", f"Saved to {fn}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ─── USERS TAB ─────────────────────────────────────────────────────────────
    def _build_users_tab(self, parent):
        parent.configure(bg=C["bg"])

        tb = tk.Frame(parent, bg=C["bg"])
        tb.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(tb, text="⚙  User Management", font=FONT_HEAD,
                 bg=C["bg"], fg=C["accent"]).pack(side=tk.LEFT)
        styled_btn(tb, "➕ Add User", self._add_user,
                   bg=C["accent"], fg=C["bg"], padx=10, pady=4).pack(side=tk.RIGHT, padx=4)

        tc = card_frame(parent)
        tc.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        cols = ("ID","Username","Full Name","Role","Created")
        self.users_tree = ttk.Treeview(tc, columns=cols, show="headings", style="Tree.Treeview")
        for col, w in zip(cols, [40,140,180,130,160]):
            self.users_tree.heading(col, text=col)
            self.users_tree.column(col, width=w)
        self.users_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        ab = tk.Frame(parent, bg=C["bg"])
        ab.pack(fill=tk.X, padx=12, pady=4)
        styled_btn(ab, "✏ Edit Role",      self._edit_user_role,  bg=C["accent3"],  fg=C["bg"],    padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "🔑 Change Password",self._change_password, bg=C["accent2"],  fg=C["white"], padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "🗑 Delete",         self._delete_user,     bg=C["danger"],   fg=C["white"], padx=10, pady=5).pack(side=tk.LEFT, padx=4)
        styled_btn(ab, "🔄 Refresh",        self._load_users,      bg=C["surface2"], fg=C["text2"], padx=10, pady=5).pack(side=tk.RIGHT, padx=4)

        self._load_users()

    def _load_users(self):
        for row in self.users_tree.get_children():
            self.users_tree.delete(row)
        rows = self.controller.db.execute_query(
            "SELECT user_id, username, COALESCE(full_name,''), role, COALESCE(created_at,'') FROM users"
        ).fetchall()
        for r in rows:
            self.users_tree.insert("", tk.END, values=r)

    def _add_user(self):
        self._user_dialog()

    def _user_dialog(self, user=None):
        dlg = tk.Toplevel(self.root)
        dlg.title("User")
        dlg.configure(bg=C["bg"])
        dlg.geometry("440x420")
        dlg.grab_set()
        tk.Label(dlg, text="User Account", font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(pady=16)
        card = card_frame(dlg)
        card.pack(fill=tk.BOTH, padx=20, pady=4, expand=True)
        fields = [("Username","username"),("Full Name","full_name"),("Password","password"),("Role","role")]
        vars_ = {}
        for lbl, key in fields:
            row = tk.Frame(card, bg=C["surface"])
            row.pack(fill=tk.X, padx=12, pady=4)
            tk.Label(row, text=lbl, width=12, anchor="w", font=FONT_SMALL,
                     bg=C["surface"], fg=C["text2"]).pack(side=tk.LEFT)
            v = tk.StringVar(value=user.get(key,'') if user else "")
            vars_[key] = v
            show = "●" if key == "password" else ""
            tk.Entry(row, textvariable=v, show=show, font=FONT_BODY, width=26,
                     bg=C["surface2"], fg=C["text"], insertbackground=C["text"],
                     relief=tk.FLAT, bd=6).pack(side=tk.LEFT, padx=6, ipady=5)

        def _save():
            uname = vars_['username'].get().strip()
            fname = vars_['full_name'].get().strip()
            pwd   = vars_['password'].get()
            role  = vars_['role'].get().strip()
            if role not in ('Administrator','Manager','Cashier'):
                messagebox.showerror("Error","Role must be Administrator, Manager, or Cashier", parent=dlg)
                return
            try:
                ph = hashlib.sha256(pwd.encode()).hexdigest()
                self.controller.db.execute_query(
                    "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,?)",
                    (uname, fname, ph, role))
                self.controller.db.commit()
                self._load_users()
                dlg.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Error","Username already exists", parent=dlg)
        styled_btn(dlg, "💾 Save", _save, bg=C["success"], fg=C["white"], padx=18, pady=8).pack(pady=10)

    def _edit_user_role(self):
        sel = self.users_tree.selection()
        if not sel: return
        vals = self.users_tree.item(sel[0])['values']
        uid  = vals[0]
        role = simpledialog.askstring("Edit Role",
                "Role (Administrator / Manager / Cashier):", initialvalue=vals[3])
        if role not in ('Administrator','Manager','Cashier'):
            messagebox.showerror("Error","Invalid role")
            return
        self.controller.db.execute_query("UPDATE users SET role=? WHERE user_id=?", (role, uid))
        self.controller.db.commit()
        self._load_users()

    def _change_password(self):
        sel = self.users_tree.selection()
        if not sel: return
        uid  = self.users_tree.item(sel[0])['values'][0]
        pwd  = simpledialog.askstring("New Password","Enter new password:", show="*")
        if not pwd: return
        ph = hashlib.sha256(pwd.encode()).hexdigest()
        self.controller.db.execute_query("UPDATE users SET password_hash=? WHERE user_id=?", (ph, uid))
        self.controller.db.commit()
        messagebox.showinfo("Done","Password updated")

    def _delete_user(self):
        sel = self.users_tree.selection()
        if not sel: return
        vals = self.users_tree.item(sel[0])['values']
        if vals[1] == self.controller.current_user['username']:
            messagebox.showerror("Error","Cannot delete your own account")
            return
        if messagebox.askyesno("Confirm", f"Delete user '{vals[1]}'?"):
            self.controller.db.execute_query("DELETE FROM users WHERE user_id=?", (vals[0],))
            self.controller.db.commit()
            self._load_users()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    db         = DatabaseManager()
    controller = POSController(db)
    root       = tk.Tk()
    app        = POSApp(root, controller)
    root.mainloop()
    db.close()
