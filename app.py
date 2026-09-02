from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response
import sqlite3, os, csv, io, json, urllib.parse, urllib.request
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# DIGITAL SHOP MANAGEMENT SYSTEM
# Simple Flask + SQLite project.
# ============================================================

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data.db")
UPLOADS = os.path.join(BASE, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)
app.secret_key = "dims_final_v2_fixed_secret_key_2026"
app.permanent_session_lifetime = 60 * 60 * 24 * 3650  # About 10 years.

UNITS = ["Piece", "Kg", "Gram", "Milligram", "Litre", "ML", "Packet", "Box", "Dozen", "Meter", "Custom"]


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def local_now():
    """Server fallback time. Forms normally send phone/browser local time."""
    d = datetime.now()
    return d.strftime("%Y-%m-%d"), d.strftime("%I:%M %p")


def form_datetime(form):
    """Use device/browser local date and time when supplied."""
    date = (form.get("device_date") or "").strip()
    time = (form.get("device_time") or "").strip()
    if date and time:
        return date, time
    return local_now()


def uid():
    return session.get("uid")


def logged_in():
    """Return True only when the session belongs to a real user."""
    user_id = uid()
    if not user_id:
        return False
    conn = db()
    exists = conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not exists:
        session.clear()
        return False
    return True


def get_user():
    if not uid():
        return None
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
    conn.close()
    return row


def valid_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def next_bill_number(conn, user_id, date):
    row = conn.execute(
        "SELECT COALESCE(MAX(bill_no), 0) + 1 AS n FROM sales WHERE user_id=? AND date=?",
        (user_id, date),
    ).fetchone()
    return int(row["n"])


def csv_response(rows, headers, filename):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[h] for h in headers])
    data = io.BytesIO(text.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name=filename)


def init_db():
    # Create the main tables.
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            contact TEXT DEFAULT '',
            address TEXT DEFAULT '',
            logo TEXT DEFAULT '',
            theme TEXT DEFAULT 'dark',
            theme_color TEXT DEFAULT 'red',
            language TEXT DEFAULT 'en'
        );

        CREATE TABLE IF NOT EXISTS stock(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            supplier TEXT DEFAULT '',
            item TEXT NOT NULL,
            qty REAL NOT NULL,
            unit TEXT NOT NULL,
            buy_price REAL DEFAULT 0,
            sell_price REAL DEFAULT 0,
            low_limit REAL DEFAULT 0,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS stock_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stock_id INTEGER,
            supplier TEXT DEFAULT '',
            item TEXT NOT NULL,
            qty REAL NOT NULL,
            unit TEXT NOT NULL,
            buy_price REAL DEFAULT 0,
            sell_price REAL DEFAULT 0,
            low_limit REAL DEFAULT 0,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(stock_id) REFERENCES stock(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bill_no INTEGER NOT NULL,
            customer TEXT NOT NULL,
            contact TEXT DEFAULT '',
            item TEXT NOT NULL,
            unit TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            cost_price REAL DEFAULT 0,
            total REAL NOT NULL,
            paid REAL DEFAULT 0,
            remaining REAL DEFAULT 0,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sale_id INTEGER NOT NULL,
            customer TEXT NOT NULL,
            contact TEXT DEFAULT '',
            amount REAL NOT NULL,
            remaining REAL NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS ix_stock_user ON stock(user_id);
        CREATE INDEX IF NOT EXISTS ix_stock_history_user ON stock_history(user_id);
        CREATE INDEX IF NOT EXISTS ix_sales_user ON sales(user_id);
        CREATE INDEX IF NOT EXISTS ix_pay_user ON payments(user_id);
        """
    )

    # Simple migration for databases made by an earlier version.
    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "theme_color" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN theme_color TEXT DEFAULT 'red'")
    if "language" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(sales)").fetchall()}
    if "cost_price" not in columns:
        conn.execute("ALTER TABLE sales ADD COLUMN cost_price REAL DEFAULT 0")
    # Final-version migrations.
    stock_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stock)").fetchall()}
    if "supplier_contact" not in stock_cols:
        conn.execute("ALTER TABLE stock ADD COLUMN supplier_contact TEXT DEFAULT ''")
    hist_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stock_history)").fetchall()}
    if "supplier_contact" not in hist_cols:
        conn.execute("ALTER TABLE stock_history ADD COLUMN supplier_contact TEXT DEFAULT ''")
    conn.execute("UPDATE stock_history SET supplier_contact=COALESCE((SELECT supplier_contact FROM stock WHERE stock.id=stock_history.stock_id), '') WHERE supplier_contact IS NULL OR supplier_contact=''" )
    # Same paid/remaining values are stored on every line of a bill so old and new data remain compatible.

    # Old stock rows may exist without history. Copy them once so reports can still show additions.
    history_count = conn.execute("SELECT COUNT(*) AS n FROM stock_history").fetchone()["n"]
    stock_count = conn.execute("SELECT COUNT(*) AS n FROM stock").fetchone()["n"]
    if history_count == 0 and stock_count > 0:
        rows = conn.execute("SELECT * FROM stock").fetchall()
        for r in rows:
            conn.execute(
                """INSERT INTO stock_history
                (user_id,stock_id,supplier,item,qty,unit,buy_price,sell_price,low_limit,date,time)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (r["user_id"], r["id"], r["supplier"], r["item"], r["qty"], r["unit"],
                 r["buy_price"], r["sell_price"], r["low_limit"], r["date"], r["time"]),
            )
    conn.commit()
    conn.close()


init_db()


THEME_COLORS = {
    "blue": "Blue", "red": "Red", "green": "Green", "orange": "Orange",
    "gold": "Gold", "pink": "Pink", "brown": "Brown", "maroon": "Maroon",
    "olive": "Olive", "teal": "Teal", "navy": "Navy", "black": "Black",
    "silver": "Silver", "coral": "Coral", "peach": "Peach", "forest": "Forest",
    "mint": "Mint", "magenta": "Magenta"
}

THEME_COLOR_HEX = {
    "blue": "#2563EB", "red": "#EF4444", "green": "#16A34A", "orange": "#F97316",
    "gold": "#D4A017", "pink": "#EC4899", "brown": "#92400E", "maroon": "#9F1239",
    "olive": "#687F24", "teal": "#0F766E", "navy": "#1E3A8A", "black": "#111827",
    "silver": "#6B7280", "coral": "#F05A47", "peach": "#F28C5B", "forest": "#166534",
    "mint": "#10B981", "magenta": "#C026D3"
}

LANGUAGES = {
    "en": "English", "hinglish": "Hinglish",
    "as": "অসমীয়া (Assamese)", "bn": "বাংলা (Bengali)", "brx": "बड़ो (Bodo)",
    "doi": "डोगरी (Dogri)", "gu": "ગુજરાતી (Gujarati)", "hi": "हिन्दी (Hindi)",
    "kn": "ಕನ್ನಡ (Kannada)", "ks": "کٲشُر (Kashmiri)", "kok": "कोंकणी (Konkani)",
    "mai": "मैथिली (Maithili)", "ml": "മലയാളം (Malayalam)", "mni": "মৈতৈলোন্ (Manipuri)",
    "mr": "मराठी (Marathi)", "ne": "नेपाली (Nepali)", "or": "ଓଡ଼ିଆ (Odia)",
    "pa": "ਪੰਜਾਬੀ (Punjabi)", "sa": "संस्कृतम् (Sanskrit)", "sat": "ᱥᱟᱱᱛᱟᱲᱤ (Santali)",
    "sd": "سنڌي (Sindhi)", "ta": "தமிழ் (Tamil)", "te": "తెలుగు (Telugu)", "ur": "اردو (Urdu)"
}

# Google Translate uses slightly different language codes for a few Indian languages.
TRANSLATE_CODES = {
    "brx": "hi", "doi": "hi", "kok": "hi", "mai": "hi", "mni": "bn",
    "sat": "hi", "ks": "ur"
}


@app.context_processor
def common_values():
    return {"units": UNITS, "user": get_user(), "theme_colors": THEME_COLORS, "theme_color_hex": THEME_COLOR_HEX, "languages": LANGUAGES}


# ============================================================
# AUTHENTICATION
# ============================================================

@app.route("/")
def home():
    """Opening page: always show the Account screen first."""
    return render_template("profile.html", profile=None)


@app.route("/dashboard")
def dashboard():
    conn = db()
    today = local_now()[0]
    sales_today = conn.execute(
        "SELECT COALESCE(SUM(total),0) AS n FROM sales WHERE user_id=? AND date=?",
        (uid(), today),
    ).fetchone()["n"]
    pending_total = conn.execute(
        "SELECT COALESCE(SUM(remaining),0) AS n FROM (SELECT bill_no,MAX(remaining) remaining FROM sales WHERE user_id=? GROUP BY bill_no)",
        (uid(),),
    ).fetchone()["n"]
    low = conn.execute(
        """SELECT item,unit,SUM(qty) AS qty,MAX(low_limit) AS low_limit
           FROM stock WHERE user_id=? GROUP BY item,unit
           HAVING SUM(qty) < MAX(low_limit)""",
        (uid(),),
    ).fetchall()
    conn.close()
    return render_template("index.html", sales=sales_today, pending=pending_total, low=low)


@app.route("/login", methods=["GET", "POST"])
def login():
    if logged_in():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth.html", mode="login", next_page=request.args.get("next", ""))
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["uid"] = user["id"]
            session.permanent = True
            if request.form.get("next") == "profile" or request.args.get("next") == "profile":
                return redirect(url_for("profile"))
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")

    return render_template("auth.html", mode=request.args.get("mode") or "login", next_page=request.args.get("next", ""))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if logged_in():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        shop = request.form.get("shop_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not shop or not username or not password:
            flash("Please fill all required fields.", "error")
            return render_template("auth.html", mode="signup", next_page=request.args.get("next", ""))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth.html", mode="signup", next_page=request.args.get("next", ""))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth.html", mode="signup", next_page=request.args.get("next", ""))
        try:
            conn = db()
            cur = conn.execute(
                "INSERT INTO users(shop_name,username,password,language) VALUES(?,?,?,?)",
                (shop, username, generate_password_hash(password), request.cookies.get("dims_language", "en")),
            )
            conn.commit()
            new_id = cur.lastrowid
            conn.close()
            session.clear()
            session["uid"] = new_id
            session.permanent = True
            if request.form.get("next") == "profile" or request.args.get("next") == "profile":
                return redirect(url_for("profile"))
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")

    return render_template("auth.html", mode=request.args.get("mode") or "signup", next_page=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    response = make_response(redirect(url_for("home")))
    return response


@app.route("/delete-account", methods=["POST"])
def delete_account():
    if logged_in():
        conn = db()
        conn.execute("DELETE FROM users WHERE id=?", (uid(),))
        conn.commit()
        conn.close()
        session.clear()
    return redirect(url_for("home"))


# ============================================================
# PROFILE / SETTINGS / THEME
# ============================================================

@app.route("/profile")
def profile():
    if not logged_in():
        return render_template("profile.html", profile=None)
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
    conn.close()
    return render_template("profile.html", profile=row)


@app.route("/profile/edit", methods=["GET", "POST"])
def profile_edit():
    if not logged_in():
        return redirect(url_for("profile"))
    conn = db()
    current = conn.execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
    if request.method == "POST":
        shop = request.form.get("shop_name", "").strip()
        contact = request.form.get("contact", "").strip()
        address = request.form.get("address", "").strip()
        logo = current["logo"]
        image = request.files.get("logo")
        if not shop:
            conn.close()
            flash("Shop name is required.", "error")
            return redirect(url_for("profile_edit"))
        if image and image.filename:
            safe = secure_filename(image.filename)
            ext = os.path.splitext(safe)[1].lower()
            if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
                conn.close()
                flash("Please select PNG, JPG, JPEG or WEBP image.", "error")
                return redirect(url_for("profile_edit"))
            filename = f"logo_{uid()}{ext}"
            image.save(os.path.join(UPLOADS, filename))
            logo = filename
        conn.execute("UPDATE users SET shop_name=?, contact=?, address=?, logo=? WHERE id=?", (shop, contact, address, logo, uid()))
        conn.commit()
        conn.close()
        flash("Shop details saved successfully.", "ok")
        return redirect(url_for("profile"))
    conn.close()
    return render_template("profile_edit.html", profile=current)


@app.route("/password", methods=["POST"])
def change_password():
    if not logged_in():
        return redirect(url_for("login", mode="login", next="profile"))
    old = request.form.get("old", "")
    new = request.form.get("new", "")
    confirm = request.form.get("confirm_new", "")
    user = get_user()
    if not check_password_hash(user["password"], old):
        flash("Current password is incorrect.", "error")
    elif len(new) < 6:
        flash("Password must be at least 6 characters.", "error")
    elif new != confirm:
        flash("New passwords do not match.", "error")
    else:
        conn = db()
        conn.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), uid()))
        conn.commit()
        conn.close()
        flash("Password changed successfully.", "ok")
    return redirect(url_for("profile"))


@app.route("/theme/<name>")
def theme(name):
    if logged_in() and name in ("dark", "light"):
        conn = db()
        conn.execute("UPDATE users SET theme=? WHERE id=?", (name, uid()))
        conn.commit()
        conn.close()
    response = make_response(redirect(request.referrer or url_for("dashboard")))
    if name in ("dark", "light"):
        response.set_cookie("dims_theme", name, max_age=60 * 60 * 24 * 3650)
    return response


@app.route("/color/<name>", methods=["GET", "POST"])
def color(name):
    if name not in THEME_COLORS:
        return redirect(request.referrer or url_for("dashboard"))
    response = make_response(redirect(request.referrer or url_for("dashboard")))
    response.set_cookie("dims_color", name, max_age=60 * 60 * 24 * 3650)
    if logged_in():
        conn = db()
        conn.execute("UPDATE users SET theme_color=? WHERE id=?", (name, uid()))
        conn.commit()
        conn.close()
    return response

@app.route("/language/<code>")
def language(code):
    if code not in LANGUAGES:
        code = "en"
    if logged_in():
        conn = db()
        conn.execute("UPDATE users SET language=? WHERE id=?", (code, uid()))
        conn.commit()
        conn.close()
    next_page = request.referrer or url_for("home")
    response = make_response(redirect(next_page))
    response.set_cookie("dims_language", code, max_age=60*60*24*3650, samesite="Lax")
    return response

@app.route("/translate-ui", methods=["POST"])
def translate_ui():
    # UI-only translator. Bills are never sent by the browser script.
    payload = request.get_json(silent=True) or {}
    code = payload.get("language", "en")
    texts = payload.get("texts", [])
    if code not in LANGUAGES or code in ("en", "hinglish"):
        return {"translations": texts}
    target = TRANSLATE_CODES.get(code, code)
    translations = []
    for value in texts[:180]:
        value = str(value or "").strip()
        if not value:
            translations.append(value)
            continue
        try:
            params = urllib.parse.urlencode({"client":"gtx", "sl":"en", "tl":target, "dt":"t", "q":value})
            with urllib.request.urlopen("https://translate.googleapis.com/translate_a/single?" + params, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            translated = "".join(part[0] for part in data[0] if part and part[0])
            translations.append(translated or value)
        except Exception:
            translations.append(value)
    return {"translations": translations}


@app.route("/uploads/<path:name>")
def uploads(name):
    return send_file(os.path.join(UPLOADS, name))


# ============================================================
# STOCK
# ============================================================

@app.route("/stock/add", methods=["GET", "POST"])
def add_stock():
    if not logged_in(): return redirect(url_for("login"))
    if request.method == "POST":
        form=request.form; date,time=form_datetime(form); item=form.get("item","").strip(); qty=valid_number(form.get("qty")); unit=form.get("unit","Piece")
        if unit=="Custom": unit=form.get("custom_unit","").strip() or "Custom"
        if not item or qty<=0:
            flash("Enter a valid item name and quantity.","error"); return render_template("form.html",page="add_stock")
        supplier=form.get("supplier","").strip(); supplier_contact=form.get("supplier_contact","").strip(); buy=valid_number(form.get("buy_price")); sell=valid_number(form.get("sell_price")); low=valid_number(form.get("low_limit"))
        conn=db(); cur=conn.execute("INSERT INTO stock(user_id,supplier,supplier_contact,item,qty,unit,buy_price,sell_price,low_limit,date,time) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uid(),supplier,supplier_contact,item,qty,unit,buy,sell,low,date,time)); stock_id=cur.lastrowid
        conn.execute("INSERT INTO stock_history(user_id,stock_id,supplier,supplier_contact,item,qty,unit,buy_price,sell_price,low_limit,date,time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uid(),stock_id,supplier,supplier_contact,item,qty,unit,buy,sell,low,date,time)); conn.commit(); conn.close(); flash("Stock saved successfully.","ok"); return redirect(url_for("add_stock"))
    return render_template("form.html",page="add_stock")


@app.route("/stock")
def stock():
    if not logged_in(): return redirect(url_for("login"))
    q=request.args.get("q","").strip(); conn=db(); sql="SELECT MAX(id) id,MAX(supplier) supplier,MAX(supplier_contact) supplier_contact,item,SUM(qty) qty,unit,MAX(buy_price) buy_price,MAX(sell_price) sell_price,MAX(low_limit) low_limit,MAX(date) date,MAX(time) time FROM stock WHERE user_id=?"; args=[uid()]
    if q:
        like=f"%{q}%"; sql+=" AND (item LIKE ? OR supplier LIKE ? OR supplier_contact LIKE ?)"; args += [like,like,like]
    sql+=" GROUP BY item,unit ORDER BY item"; rows=conn.execute(sql,args).fetchall(); conn.close(); return render_template("table.html",page="stock",rows=rows,q=q)


@app.route("/stock/edit/<int:id>", methods=["GET", "POST"])
def edit_stock(id):
    if not logged_in(): return redirect(url_for("login"))
    conn=db(); history=conn.execute("SELECT * FROM stock_history WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if not history: conn.close(); return redirect(url_for("purchase_history"))
    if request.method=="POST":
        f=request.form; item=f.get("item","").strip(); qty=valid_number(f.get("qty")); unit=f.get("unit","Piece"); unit=f.get("custom_unit","").strip() if unit=="Custom" else unit
        if not item or qty<=0: conn.close(); flash("Enter a valid item and quantity.","error"); return redirect(url_for("edit_stock",id=id))
        old_qty=history["qty"]; diff=qty-old_qty; sid=history["stock_id"]; supplier=f.get("supplier","").strip(); sc=f.get("supplier_contact","").strip(); buy=valid_number(f.get("buy_price")); sell=valid_number(f.get("sell_price")); low=valid_number(f.get("low_limit"))
        if sid: conn.execute("UPDATE stock SET supplier=?,supplier_contact=?,item=?,qty=qty+?,unit=?,buy_price=?,sell_price=?,low_limit=? WHERE id=? AND user_id=?",(supplier,sc,item,diff,unit,buy,sell,low,sid,uid()))
        conn.execute("UPDATE stock_history SET supplier=?,supplier_contact=?,item=?,qty=?,unit=?,buy_price=?,sell_price=?,low_limit=? WHERE id=? AND user_id=?",(supplier,sc,item,qty,unit,buy,sell,low,id,uid())); conn.commit(); conn.close(); flash("Purchase/stock entry updated.","ok"); return redirect(url_for("purchase_history"))
    conn.close(); return render_template("form.html",page="edit_stock",record=history)

@app.route("/stock/delete/<int:id>", methods=["POST"])
def delete_stock(id):
    if not logged_in(): return redirect(url_for("purchase_history"))
    conn=db(); h=conn.execute("SELECT stock_id,qty FROM stock_history WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if h:
        if h["stock_id"]:
            conn.execute("DELETE FROM stock WHERE id=? AND user_id=?",(h["stock_id"],uid()))
        conn.execute("DELETE FROM stock_history WHERE id=? AND user_id=?",(id,uid())); conn.commit()
    conn.close(); flash("Purchase entry deleted.","ok"); return redirect(url_for("purchase_history"))


@app.route("/stock/current-edit/<int:id>", methods=["GET", "POST"])
def current_stock_edit(id):
    if not logged_in():
        return redirect(url_for("stock"))
    conn = db()
    row = conn.execute("SELECT * FROM stock WHERE id=? AND user_id=?", (id, uid())).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("stock"))
    if request.method == "POST":
        f = request.form
        item = f.get("item", "").strip()
        qty = valid_number(f.get("qty"))
        unit = f.get("unit", "Piece")
        if unit == "Custom":
            unit = f.get("custom_unit", "").strip() or "Custom"
        if not item or qty < 0:
            conn.close()
            flash("Enter valid stock details.", "error")
            return redirect(url_for("current_stock_edit", id=id))
        conn.execute(
            "UPDATE stock SET supplier=?,supplier_contact=?,item=?,qty=?,unit=?,buy_price=?,sell_price=?,low_limit=? WHERE id=? AND user_id=?",
            (f.get("supplier","").strip(), f.get("supplier_contact","").strip(), item, qty, unit,
             valid_number(f.get("buy_price")), valid_number(f.get("sell_price")),
             valid_number(f.get("low_limit")), id, uid())
        )
        conn.commit()
        conn.close()
        flash("Current stock updated successfully.", "ok")
        return redirect(url_for("stock"))
    conn.close()
    return render_template("form.html", page="edit_current_stock", record=row)

@app.route("/stock/current-delete/<int:id>", methods=["POST"])
def current_stock_delete(id):
    if not logged_in():
        return redirect(url_for("stock"))
    conn = db()
    row = conn.execute("SELECT id FROM stock WHERE id=? AND user_id=?", (id, uid())).fetchone()
    if row:
        conn.execute("DELETE FROM stock WHERE id=? AND user_id=?", (id, uid()))
        conn.commit()
        flash("Current stock entry deleted. Purchase history is kept.", "ok")
    conn.close()
    return redirect(url_for("stock"))


# ============================================================
# SALES + BILL
# ============================================================

def _sale_items(conn):
    return conn.execute("SELECT item,unit,SUM(qty) AS qty,MAX(sell_price) AS price FROM stock WHERE user_id=? AND qty>0 GROUP BY item,unit ORDER BY item",(uid(),)).fetchall()

def _bill(conn,bill_no):
    rows=conn.execute("SELECT * FROM sales WHERE user_id=? AND bill_no=? ORDER BY id",(uid(),bill_no)).fetchall()
    if not rows: return None,[]
    total=sum(r["total"] for r in rows); paid=max(r["paid"] for r in rows); remaining=max(total-paid,0)
    return {"bill_no":bill_no,"customer":rows[0]["customer"],"contact":rows[0]["contact"],"date":rows[0]["date"],"time":rows[0]["time"],"total":total,"paid":paid,"remaining":remaining},rows

@app.route("/sale/add", methods=["GET", "POST"])
def add_sale():
    if not logged_in(): return redirect(url_for("login"))
    conn=db(); items=_sale_items(conn)
    if request.method=="POST":
        f=request.form; customer=f.get("customer","").strip(); contact=f.get("contact","").strip(); names=f.getlist("item[]"); units=f.getlist("unit[]"); qtys=f.getlist("qty[]"); prices=f.getlist("price[]"); paid=max(valid_number(f.get("paid")),0); date,time=form_datetime(f)
        lines=[]; grand=0
        for name,unit,q,p in zip(names,units,qtys,prices):
            name=name.strip(); q=valid_number(q); p=valid_number(p)
            if not name or q<=0: continue
            available=conn.execute("SELECT COALESCE(SUM(qty),0) q FROM stock WHERE user_id=? AND item=? AND unit=? AND qty>0",(uid(),name,unit)).fetchone()["q"]
            if q>available: conn.close(); flash(f"Not enough stock for {name}. Available: {available:g} {unit}.","error"); return render_template("form.html",page="add_sale",items=items)
            cost=conn.execute("SELECT COALESCE(SUM(qty*buy_price),0) value,COALESCE(SUM(qty),0) qty FROM stock WHERE user_id=? AND item=? AND unit=? AND qty>0",(uid(),name,unit)).fetchone(); cost_price=(cost["value"]/cost["qty"]) if cost["qty"] else 0
            total=round(q*p,2); grand+=total; lines.append((name,unit,q,p,cost_price,total))
        if not lines or not customer: conn.close(); flash("Enter customer and at least one valid item.","error"); return render_template("form.html",page="add_sale",items=items)
        paid=min(paid,round(grand,2)); remaining=round(grand-paid,2); bill_no=next_bill_number(conn,uid(),date); first_id=None
        for name,unit,q,p,cost,total in lines:
            cur=conn.execute("INSERT INTO sales(user_id,bill_no,customer,contact,item,unit,qty,price,cost_price,total,paid,remaining,date,time) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uid(),bill_no,customer,contact,name,unit,q,p,cost,total,paid,remaining,date,time)); first_id=first_id or cur.lastrowid
            left=q
            lots=conn.execute("SELECT id,qty FROM stock WHERE user_id=? AND item=? AND unit=? AND qty>0 ORDER BY id",(uid(),name,unit)).fetchall()
            for lot in lots:
                take=min(left,lot["qty"]); conn.execute("UPDATE stock SET qty=qty-? WHERE id=?",(take,lot["id"])); left-=take
                if left<=0: break
        if paid>0: conn.execute("INSERT INTO payments(user_id,sale_id,customer,contact,amount,remaining,date,time) VALUES(?,?,?,?,?,?,?,?)",(uid(),first_id,customer,contact,paid,remaining,date,time))
        conn.commit(); bill,rows=_bill(conn,bill_no); conn.close(); return render_template("bill.html",bill=bill,items=rows)
    conn.close(); return render_template("form.html",page="add_sale",items=items)

@app.route("/sales")
def sales():
    if not logged_in(): return redirect(url_for("login"))
    q=request.args.get("q","").strip(); conn=db(); like=f"%{q}%"
    sql="SELECT MIN(id) id,bill_no,MAX(customer) customer,MAX(contact) contact,GROUP_CONCAT(item || ' (' || qty || ' ' || unit || ')', ', ') items,SUM(total) total,MAX(paid) paid,MAX(remaining) remaining,MAX(date) date,MAX(time) time FROM sales WHERE user_id=?"
    args=[uid()]
    if q: sql+=" AND (customer LIKE ? OR contact LIKE ? OR item LIKE ? OR CAST(bill_no AS TEXT) LIKE ?)"; args += [like,like,like,like]
    sql+=" GROUP BY bill_no ORDER BY MAX(id) DESC"; rows=conn.execute(sql,args).fetchall(); conn.close(); return render_template("table.html",page="sales",rows=rows,q=q)

@app.route("/bill/<int:bill_no>")
def bill_view(bill_no):
    if not logged_in(): return redirect(url_for("login"))
    conn=db(); bill,rows=_bill(conn,bill_no); conn.close()
    if not bill: return redirect(url_for("sales"))
    return render_template("bill.html",bill=bill,items=rows)

@app.route("/sale/pay/<int:id>", methods=["GET", "POST"])
def pay(id):
    if not logged_in(): return redirect(url_for("sales"))
    conn=db(); row=conn.execute("SELECT * FROM sales WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if not row: conn.close(); return redirect(url_for("sales"))
    bill,rows=_bill(conn,row["bill_no"])
    if request.method=="POST":
        amount=min(max(valid_number(request.form.get("amount")),0),bill["remaining"])
        if amount<=0: conn.close(); flash("Enter a valid payment amount.","error"); return redirect(url_for("pay",id=id))
        d,t=form_datetime(request.form); new_paid=round(bill["paid"]+amount,2); new_rem=round(bill["total"]-new_paid,2)
        conn.execute("UPDATE sales SET paid=?,remaining=? WHERE user_id=? AND bill_no=?",(new_paid,new_rem,uid(),row["bill_no"]))
        conn.execute("INSERT INTO payments(user_id,sale_id,customer,contact,amount,remaining,date,time) VALUES(?,?,?,?,?,?,?,?)",(uid(),row["id"],bill["customer"],bill["contact"],amount,new_rem,d,t)); conn.commit(); conn.close(); flash("Payment saved successfully.","ok"); return redirect(url_for("sales"))
    conn.close(); return render_template("pay.html",sale=row)

@app.route("/sale/edit/<int:id>", methods=["GET", "POST"])
def edit_sale(id):
    # Editing individual lines is intentionally kept simple. Use delete/return for bill-level corrections.
    if not logged_in(): return redirect(url_for("sales"))
    conn=db(); old=conn.execute("SELECT * FROM sales WHERE id=? AND user_id=?",(id,uid())).fetchone(); items=_sale_items(conn); conn.close()
    if not old: return redirect(url_for("sales"))
    flash("For multi-item bills, use Bill and Return actions to correct individual items.","error"); return redirect(url_for("sales"))

@app.route("/sale/delete/<int:id>", methods=["POST"])
def delete_sale(id):
    if not logged_in(): return redirect(url_for("sales"))
    conn=db(); row=conn.execute("SELECT * FROM sales WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if row:
        rows=conn.execute("SELECT * FROM sales WHERE user_id=? AND bill_no=?",(uid(),row["bill_no"])).fetchall()
        for sale in rows:
            lots=conn.execute("SELECT id FROM stock WHERE user_id=? AND item=? AND unit=? ORDER BY id LIMIT 1",(uid(),sale["item"],sale["unit"])).fetchone()
            if lots: conn.execute("UPDATE stock SET qty=qty+? WHERE id=?",(sale["qty"],lots["id"]))
            else:
                d,t=local_now(); conn.execute("INSERT INTO stock(user_id,supplier,item,qty,unit,buy_price,sell_price,low_limit,date,time) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),"Restored from deleted sale",sale["item"],sale["qty"],sale["unit"],sale["cost_price"],sale["price"],0,d,t))
        conn.execute("DELETE FROM payments WHERE user_id=? AND sale_id IN (SELECT id FROM sales WHERE user_id=? AND bill_no=?)",(uid(),uid(),row["bill_no"])); conn.execute("DELETE FROM sales WHERE user_id=? AND bill_no=?",(uid(),row["bill_no"])); conn.commit()
    conn.close(); flash("Bill deleted and stock restored.","ok"); return redirect(url_for("sales"))

@app.route("/sale/return/<int:id>", methods=["GET", "POST"])
def return_sale(id):
    if not logged_in(): return redirect(url_for("sales"))
    conn=db(); sale=conn.execute("SELECT * FROM sales WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if not sale: conn.close(); return redirect(url_for("sales"))
    if request.method=="POST":
        qty=min(max(valid_number(request.form.get("qty")),0),sale["qty"])
        if qty<=0: conn.close(); flash("Enter a valid return quantity.","error"); return redirect(url_for("return_sale",id=id))
        # Refund/credit adjustment is based on the line's sale rate.
        amount=round(qty*sale["price"],2); new_total=round(sale["total"]-amount,2); new_paid=min(sale["paid"],new_total); new_rem=round(new_total-new_paid,2)
        lots=conn.execute("SELECT id FROM stock WHERE user_id=? AND item=? AND unit=? ORDER BY id LIMIT 1",(uid(),sale["item"],sale["unit"])).fetchone()
        if lots: conn.execute("UPDATE stock SET qty=qty+? WHERE id=?",(qty,lots["id"]))
        else:
            d,t=local_now(); conn.execute("INSERT INTO stock(user_id,supplier,item,qty,unit,buy_price,sell_price,low_limit,date,time) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),"Returned Sale",sale["item"],qty,sale["unit"],sale["cost_price"],sale["price"],0,d,t))
        if qty==sale["qty"]: conn.execute("DELETE FROM sales WHERE id=? AND user_id=?",(id,uid()))
        else: conn.execute("UPDATE sales SET qty=?,total=? WHERE id=? AND user_id=?",(sale["qty"]-qty,new_total,id,uid()))
        bill_rows=conn.execute("SELECT * FROM sales WHERE user_id=? AND bill_no=?",(uid(),sale["bill_no"])).fetchall()
        if bill_rows:
            bill_total=sum(r["total"] for r in bill_rows); paid=min(sale["paid"],bill_total); rem=round(bill_total-paid,2); conn.execute("UPDATE sales SET paid=?,remaining=? WHERE user_id=? AND bill_no=?",(paid,rem,uid(),sale["bill_no"]))
        conn.commit(); conn.close(); flash("Sale return processed and stock restored.","ok"); return redirect(url_for("sales"))
    conn.close(); return render_template("return.html",sale=sale)


# ============================================================
# PAYMENT HISTORY
# ============================================================

@app.route("/payments")
def payments():
    if not logged_in():
        return redirect(url_for("login"))
    q = request.args.get("q", "").strip()
    conn = db()
    if q:
        rows = conn.execute(
            """SELECT * FROM payments WHERE user_id=?
               AND (customer LIKE ? OR contact LIKE ? OR CAST(amount AS TEXT) LIKE ? OR CAST(remaining AS TEXT) LIKE ?)
               ORDER BY id DESC""",
            (uid(), f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
    conn.close()
    return render_template("table.html", page="payments", rows=rows, q=q)


@app.route("/payment/delete/<int:id>", methods=["POST"])
def delete_payment(id):
    if not logged_in(): return redirect(url_for("payments"))
    conn=db(); payment=conn.execute("SELECT * FROM payments WHERE id=? AND user_id=?",(id,uid())).fetchone()
    if payment:
        sale=conn.execute("SELECT * FROM sales WHERE id=? AND user_id=?",(payment["sale_id"],uid())).fetchone()
        if sale:
            bill,rows=_bill(conn,sale["bill_no"]); new_paid=max(0,round(bill["paid"]-payment["amount"],2)); new_remaining=round(bill["total"]-new_paid,2)
            conn.execute("UPDATE sales SET paid=?,remaining=? WHERE user_id=? AND bill_no=?",(new_paid,new_remaining,uid(),sale["bill_no"]))
        conn.execute("DELETE FROM payments WHERE id=? AND user_id=?",(id,uid())); conn.commit()
    conn.close(); flash("Payment history entry deleted.","ok"); return redirect(url_for("payments"))


# ============================================================
# PENDING PAYMENTS
# ============================================================

@app.route("/reports/pending")
def pending():
    if not logged_in(): return redirect(url_for("login"))
    q=request.args.get("q","").strip(); conn=db(); like=f"%{q}%"; sql="SELECT MIN(id) id,bill_no,MAX(customer) customer,MAX(contact) contact,MAX(remaining) remaining,MAX(date) date,MAX(time) time FROM sales WHERE user_id=? AND remaining>0"; args=[uid()]
    if q: sql+=" AND (customer LIKE ? OR contact LIKE ? OR CAST(remaining AS TEXT) LIKE ?)"; args += [like,like,like]
    sql+=" GROUP BY bill_no ORDER BY MAX(id) DESC"; rows=conn.execute(sql,args).fetchall(); conn.close(); return render_template("table.html",page="pending",rows=rows,q=q)


# ============================================================
# PURCHASE HISTORY / CUSTOMER HISTORY / BACKUP
# ============================================================
@app.route("/purchases")
def purchase_history():
    if not logged_in(): return redirect(url_for("login"))
    q=request.args.get("q","").strip(); conn=db(); sql="SELECT id,supplier,supplier_contact,item,qty,unit,(qty*buy_price) AS total_price,date,time FROM stock_history WHERE user_id=?"; args=[uid()]
    if q:
        like=f"%{q}%"; sql+=" AND (supplier LIKE ? OR supplier_contact LIKE ? OR item LIKE ?)"; args += [like,like,like]
    sql+=" ORDER BY id DESC"; rows=conn.execute(sql,args).fetchall(); conn.close(); return render_template("table.html",page="purchase",rows=rows,q=q)

@app.route("/customers")
def customer_history():
    if not logged_in(): return redirect(url_for("login"))
    q=request.args.get("q","").strip(); conn=db()
    if not q:
        conn.close(); return render_template("customer.html",customer=None,rows=[],q=q,summary={"items":0,"total":0,"paid":0,"remaining":0})
    like=f"%{q}%"; rows=conn.execute("SELECT * FROM sales WHERE user_id=? AND (customer LIKE ? OR contact LIKE ?) ORDER BY date DESC, bill_no DESC, id DESC",(uid(),like,like)).fetchall();
    if not rows: conn.close(); return render_template("customer.html",customer=q,rows=[],q=q,summary={"items":0,"total":0,"paid":0,"remaining":0})
    customer=rows[0]["customer"]; total=sum(r["total"] for r in rows); items=sum(r["qty"] for r in rows)
    bills={r["bill_no"]:r for r in rows}; paid=sum(max(r["paid"] for r in rows if r["bill_no"]==b) for b in bills); remaining=sum(max(r["remaining"] for r in rows if r["bill_no"]==b) for b in bills)
    conn.close(); return render_template("customer.html",customer=customer,rows=rows,q=q,summary={"items":items,"total":total,"paid":paid,"remaining":remaining})

# ============================================================
# REPORT DATE HELPERS
# ============================================================

def selected_dates():
    """Return dates for the single Choose Date selector."""
    today = datetime.now().date()
    option = request.args.get("range", "today")

    if option == "yesterday":
        return [(today - timedelta(days=1)).strftime("%Y-%m-%d")]
    if option == "week":
        start = today - timedelta(days=today.weekday())
        return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    if option == "month":
        first = today.replace(day=1)
        next_first = today.replace(year=today.year + 1, month=1, day=1) if today.month == 12 else today.replace(month=today.month + 1, day=1)
        return [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((next_first-first).days)]
    if option == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        first_last = last_month_end.replace(day=1)
        return [(first_last + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((last_month_end-first_last).days + 1)]
    if option == "year":
        first = today.replace(month=1, day=1)
        return [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((today-first).days+1)]
    if option == "custom_week":
        week = request.args.get("week", "1")
        start_day = {"1":1,"2":8,"3":15,"4":22}.get(week,1)
        first = today.replace(day=1)
        if today.month == 12:
            next_first = today.replace(year=today.year+1, month=1, day=1)
        else:
            next_first = today.replace(month=today.month+1, day=1)
        last = (next_first-timedelta(days=1)).day
        start = today.replace(day=min(start_day,last))
        end = today.replace(day=min(start_day+6,last))
        return [(start+timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end-start).days+1)]
    if option == "custom_month":
        month = max(1,min(12,int(request.args.get("month",today.month))))
        first = today.replace(month=month,day=1)
        if month == 12:
            next_first = today.replace(year=today.year+1,month=1,day=1)
        else:
            next_first = today.replace(month=month+1,day=1)
        return [(first+timedelta(days=i)).strftime("%Y-%m-%d") for i in range((next_first-first).days)]
    date = request.args.get("date","")
    return [date if date else today.strftime("%Y-%m-%d")]


@app.route("/reports/stock")
def stock_report():
    if not logged_in():
        return redirect(url_for("login"))
    dates = selected_dates()
    placeholders = ",".join("?" for _ in dates)
    conn = db()
    sold = conn.execute(
        f"""SELECT item, unit, SUM(qty) AS sold
            FROM sales WHERE user_id=? AND date IN ({placeholders})
            GROUP BY item, unit HAVING SUM(qty) > 0 ORDER BY item""",
        [uid(), *dates],
    ).fetchall()

    rows = []
    for item in sold:
        current = conn.execute(
            """SELECT COALESCE(SUM(qty),0) AS available, MAX(sell_price) AS price,
                      MAX(low_limit) AS limit_qty
               FROM stock WHERE user_id=? AND item=? AND unit=?""",
            (uid(), item["item"], item["unit"]),
        ).fetchone()
        available = current["available"] or 0
        limit_qty = current["limit_qty"] or 0
        if available <= 0:
            status = "Out of Stock"
        elif limit_qty > 0 and available <= limit_qty:
            status = "Low Stock"
        else:
            status = "In Stock"
        rows.append({
            "item": item["item"], "unit": item["unit"],
            "price": current["price"] or 0, "available": available,
            "limit_qty": limit_qty, "status": status,
        })

    low = [r for r in rows if r["status"] == "Low Stock"]
    conn.close()
    return render_template(
        "report.html", kind="stock", rows=rows, low=low,
        total_items=len(rows), rng=request.args.get("range", "today"),
        week=request.args.get("week", "1"), month=request.args.get("month", str(datetime.now().month)),
        date=request.args.get("date", ""),
    )


@app.route("/reports/sales")
def sales_report():
    if not logged_in():
        return redirect(url_for("login"))
    dates = selected_dates()
    placeholders = ",".join("?" for _ in dates)
    conn = db()
    sold_rows = conn.execute(
        f"""SELECT item, unit, SUM(qty) AS qty, SUM(total) AS total,
                  SUM((price-cost_price)*qty) AS profit
           FROM sales WHERE user_id=? AND date IN ({placeholders})
           GROUP BY item, unit HAVING SUM(qty) > 0 ORDER BY item""",
        [uid(), *dates],
    ).fetchall()

    rows = []
    total = 0
    profit = 0
    for r in sold_rows:
        unit_price = (r["total"] / r["qty"]) if r["qty"] else 0
        rows.append({
            "item": r["item"], "unit": r["unit"], "price": unit_price,
            "total": r["total"] or 0, "profit": r["profit"] or 0,
        })
        total += r["total"] or 0
        profit += r["profit"] or 0

    conn.close()
    return render_template(
        "report.html", kind="sales", rows=rows, total=total, profit=profit,
        total_items=len(rows), rng=request.args.get("range", "today"),
        week=request.args.get("week", "1"), month=request.args.get("month", str(datetime.now().month)),
        date=request.args.get("date", ""),
    )


# ============================================================
# EXPORT / PRINT
# ============================================================

@app.route("/export/<kind>")
def export(kind):
    if not logged_in():
        return redirect(url_for("login"))
    conn = db()
    if kind == "stock":
        dates = selected_dates()
        ph = ",".join("?" for _ in dates)
        rows = conn.execute(
            f"""SELECT item, unit, SUM(qty) AS sold FROM sales
                WHERE user_id=? AND date IN ({ph}) GROUP BY item, unit
                HAVING SUM(qty)>0 ORDER BY item""",
            [uid(), *dates],
        ).fetchall()
        export_rows=[]
        for r in rows:
            current=conn.execute("SELECT COALESCE(SUM(qty),0) available, MAX(sell_price) price, MAX(low_limit) limit_qty FROM stock WHERE user_id=? AND item=? AND unit=?",(uid(),r["item"],r["unit"])).fetchone()
            available=current["available"] or 0; limit_qty=current["limit_qty"] or 0
            status="Out of Stock" if available<=0 else ("Low Stock" if limit_qty>0 and available<=limit_qty else "In Stock")
            export_rows.append({"item":r["item"],"unit":r["unit"],"price":current["price"] or 0,"available":available,"limit":limit_qty,"status":status})
        conn.close()
        return csv_response(export_rows, ["item","unit","price","available","limit","status"], "stock_report.csv")
    if kind == "sales":
        dates = selected_dates()
        ph = ",".join("?" for _ in dates)
        rows = conn.execute(
            f"""SELECT item, unit, SUM(qty) qty, SUM(total) total,
                       SUM((price-cost_price)*qty) profit
                FROM sales WHERE user_id=? AND date IN ({ph})
                GROUP BY item, unit HAVING SUM(qty)>0 ORDER BY item""",
            [uid(), *dates],
        ).fetchall()
        export_rows=[{"item":r["item"],"unit":r["unit"],"price":(r["total"]/r["qty"]) if r["qty"] else 0,"total":r["total"] or 0,"profit":r["profit"] or 0} for r in rows]
        conn.close()
        return csv_response(export_rows, ["item","unit","price","total","profit"], "sales_report.csv")
    if kind == "purchase":
        rows = conn.execute("SELECT supplier,supplier_contact,item,qty,unit,(qty*buy_price) AS total_price,date,time FROM stock_history WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
        conn.close()
        return csv_response(rows, ["supplier","supplier_contact","item","qty","unit","total_price","date","time"], "purchase_history.csv")
    if kind == "payments":
        rows = conn.execute(
            "SELECT customer,contact,amount,date,time FROM payments WHERE user_id=? ORDER BY id DESC",
            (uid(),),
        ).fetchall()
        conn.close()
        return csv_response(rows, ["customer", "contact", "amount", "date", "time"], "payment_history.csv")
    rows = conn.execute(
        "SELECT customer,contact,remaining,date,time FROM sales WHERE user_id=? AND remaining>0 ORDER BY id DESC",
        (uid(),),
    ).fetchall()
    conn.close()
    return csv_response(rows, ["customer", "contact", "remaining", "date", "time"], "pending_payments.csv")


@app.route("/print/<kind>")
def print_page(kind):
    if not logged_in():
        return redirect(url_for("login"))
    conn = db()
    if kind == "stock":
        rows = conn.execute("SELECT * FROM stock_history WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
        title = "Stock Report"
    elif kind == "sales":
        rows = conn.execute("SELECT * FROM sales WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
        title = "Sales Report"
    elif kind == "purchase":
        rows = conn.execute("SELECT * FROM stock_history WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
        title = "Purchase History"
    elif kind == "payments":
        rows = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC", (uid(),)).fetchall()
        title = "Payment History"
    else:
        rows = conn.execute("SELECT customer,contact,remaining,date,time FROM sales WHERE user_id=? AND remaining>0 ORDER BY id DESC", (uid(),)).fetchall()
        title = "Pending Payments"
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
    conn.close()
    return render_template("print.html", rows=rows, title=title, kind=kind, user=user)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
