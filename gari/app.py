"""Gari - garage management SaaS (Nairobi). Flask + SQLite, multi-tenant."""
import os, re, time, sqlite3, secrets, hashlib, hmac, smtplib, threading, datetime as dt
from email.message import EmailMessage
from functools import wraps
import jwt
from flask import Flask, g, request, jsonify, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
VAT_RATE = 16  # percent, Kenya standard rate

def create_app(db_path=None, secret=None):
    app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")
    app.config["DB"] = db_path or os.environ.get("GARI_DB", os.path.join(BASE, "gari.db"))
    app.config["SECRET"] = secret or os.environ.get("GARI_SECRET") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    app.config["LOGIN_LIMIT"] = (8, 300)  # attempts, window seconds
    app.config["RESET_TTL_MIN"] = 30
    app.config["MAIL_SENDER"] = None  # callable(to, subject, body); tests inject one
    app.config["MAIL_SYNC"] = False
    attempts = {}

    def connect():
        c = sqlite3.connect(app.config["DB"], timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000"); c.execute("PRAGMA synchronous=NORMAL")
        return c

    with connect() as c:
        with open(os.path.join(BASE, "schema.sql")) as f: c.executescript(f.read())
        if "token_version" not in [r["name"] for r in c.execute("PRAGMA table_info(users)")]:
            c.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")

    # ---------- infrastructure ----------
    class ApiError(Exception):
        def __init__(self, msg, code=400, field=None): self.msg, self.code, self.field = msg, code, field

    @app.errorhandler(ApiError)
    def _api_err(e):
        return jsonify(error=e.msg, field=e.field), e.code

    @app.errorhandler(404)
    def _404(e): return jsonify(error="Not found"), 404
    @app.errorhandler(405)
    def _405(e): return jsonify(error="Method not allowed"), 405
    @app.errorhandler(413)
    def _413(e): return jsonify(error="Request too large"), 413
    @app.errorhandler(Exception)
    def _500(e):
        app.logger.exception(e)
        return jsonify(error="Something went wrong on our side. Try again."), 500

    @app.before_request
    def _open():
        g.db = connect()

    @app.teardown_request
    def _close(exc):
        db = g.pop("db", None)
        if db is not None:
            try:
                (db.rollback if exc else db.commit)()
            finally:
                db.close()

    @app.after_request
    def _headers(r):
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Frame-Options"] = "DENY"
        r.headers["Referrer-Policy"] = "no-referrer"
        r.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        if request.path.startswith("/api/"): r.headers["Cache-Control"] = "no-store"
        return r

    def q(sql, *a): return g.db.execute(sql, a).fetchall()
    def q1(sql, *a): return g.db.execute(sql, a).fetchone()
    def run(sql, *a): return g.db.execute(sql, a)
    def audit(action, detail=""):
        u = getattr(g, "user", None)
        run("INSERT INTO audit_log(garage_id,user_id,action,detail) VALUES(?,?,?,?)",
            u["garage_id"] if u else None, u["id"] if u else None, action, str(detail)[:500])

    # ---------- passwords / tokens ----------
    def hash_pw(pw):
        salt = secrets.token_bytes(16)
        h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return "scrypt$" + salt.hex() + "$" + h.hex()

    def check_pw(pw, stored):
        try:
            _, salt, h = stored.split("$")
            calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
            return hmac.compare_digest(calc.hex(), h)
        except Exception:
            return False

    def make_token(u):
        return jwt.encode({"uid": u["id"], "gid": u["garage_id"], "role": u["role"], "tv": u["token_version"],
                           "exp": int(time.time()) + 12 * 3600}, app.config["SECRET"], algorithm="HS256")

    def auth(*roles):
        def deco(fn):
            @wraps(fn)
            def inner(*a, **kw):
                h = request.headers.get("Authorization", "")
                if not h.startswith("Bearer "): raise ApiError("Sign in to continue", 401)
                try:
                    p = jwt.decode(h[7:], app.config["SECRET"], algorithms=["HS256"])
                except jwt.PyJWTError:
                    raise ApiError("Your session expired. Sign in again.", 401)
                u = q1("SELECT * FROM users WHERE id=? AND garage_id=? AND active=1", p["uid"], p["gid"])
                if not u: raise ApiError("Account disabled or not found", 401)
                if p.get("tv", 0) != u["token_version"]: raise ApiError("Your password changed. Sign in again.", 401)
                g.user = u
                if roles and u["role"] not in roles: raise ApiError("You don't have permission to do this", 403)
                return fn(*a, **kw)
            return inner
        return deco

    def gid(): return g.user["garage_id"]
    def is_staff(): return g.user["role"] in ("owner", "manager")

    # ---------- validation ----------
    def body():
        d = request.get_json(silent=True)
        if not isinstance(d, dict): raise ApiError("Send a JSON object")
        return d

    def s(d, k, req=True, mx=200, label=None):
        v = d.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            if req: raise ApiError(f"{label or k} is required", field=k)
            return None
        if not isinstance(v, str): v = str(v)
        v = v.strip()
        if len(v) > mx: raise ApiError(f"{label or k} is too long", field=k)
        return v

    def n(d, k, req=True, lo=0, hi=10**9, label=None):
        v = d.get(k)
        if v in (None, ""):
            if req: raise ApiError(f"{label or k} is required", field=k)
            return None
        try:
            if isinstance(v, bool): raise ValueError
            f = float(v)
            if f != int(f): raise ValueError
            v = int(f)
        except (ValueError, TypeError, OverflowError):
            raise ApiError(f"{label or k} must be a whole number", field=k)
        if v < lo or v > hi: raise ApiError(f"{label or k} must be between {lo} and {hi}", field=k)
        return v

    def phone(v):
        d = re.sub(r"[\s\-()]", "", v or "")
        if re.fullmatch(r"(?:\+?254|0)([17]\d{8})", d): return "+254" + re.fullmatch(r"(?:\+?254|0)([17]\d{8})", d).group(1)
        raise ApiError("Enter a valid Kenyan phone number, e.g. 0712 345 678", field="phone")

    def plate(v):
        p = re.sub(r"\s+", "", (v or "").upper())
        if not re.fullmatch(r"[A-Z0-9]{5,9}", p): raise ApiError("Enter a valid number plate, e.g. KDA 123A", field="plate")
        return p

    def email(v):
        v = (v or "").strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) or len(v) > 120: raise ApiError("Enter a valid email address", field="email")
        return v

    def password(v):
        if not isinstance(v, str) or len(v) < 8 or not re.search(r"\d", v) or not re.search(r"[A-Za-z]", v):
            raise ApiError("Password needs 8+ characters with letters and numbers", field="password")
        return v

    def rows(rs): return [dict(r) for r in rs]
    def now(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ---------- public / auth ----------
    @app.get("/")
    def index(): return send_from_directory(app.static_folder, "index.html")

    @app.get("/q/<token>")
    def quote_page(token): return send_from_directory(app.static_folder, "quote.html")

    @app.get("/api/health")
    def health():
        q1("SELECT 1"); return jsonify(status="ok", time=now())

    def throttle(key):
        lim, win = app.config["LOGIN_LIMIT"]; t = time.time()
        a = [x for x in attempts.get(key, []) if t - x < win]
        attempts[key] = a
        if len(a) >= lim: raise ApiError("Too many attempts. Wait a few minutes and try again.", 429)
        return a

    @app.post("/api/auth/register")
    def register():
        d = body()
        gname = s(d, "garage_name", label="Garage name", mx=80)
        pin = s(d, "kra_pin", req=False, mx=11)
        if pin and not re.fullmatch(r"[AP]\d{9}[A-Z]", pin.upper()): raise ApiError("KRA PIN looks like A123456789Z", field="kra_pin")
        name = s(d, "name", label="Your name", mx=80); em = email(d.get("email")); pw = password(d.get("password"))
        ph = phone(d.get("phone"))
        if q1("SELECT 1 FROM users WHERE email=?", em): raise ApiError("That email is already registered", 409, "email")
        gid_ = run("INSERT INTO garages(name,kra_pin,phone) VALUES(?,?,?)", gname, pin.upper() if pin else None, ph).lastrowid
        uid = run("INSERT INTO users(garage_id,name,phone,email,pw_hash,role) VALUES(?,?,?,?,?,'owner')",
                  gid_, name, ph, em, hash_pw(pw)).lastrowid
        u = q1("SELECT * FROM users WHERE id=?", uid); g.user = u; audit("garage.register", gname)
        return jsonify(token=make_token(u), user=pub_user(u)), 201

    def pub_user(u): return {k: u[k] for k in ("id", "name", "email", "phone", "role", "garage_id")}

    @app.post("/api/auth/login")
    def login():
        d = body(); em = (d.get("email") or "").strip().lower()
        key = (request.remote_addr or "") + "|" + em
        a = throttle(key)
        u = q1("SELECT * FROM users WHERE email=? AND active=1", em)
        ok = check_pw(d.get("password") or "", u["pw_hash"]) if u else (check_pw("x", "scrypt$00$00") and False)
        if not ok:
            a.append(time.time()); attempts[key] = a
            raise ApiError("Email or password is incorrect", 401)
        attempts.pop(key, None); g.user = u; audit("login")
        return jsonify(token=make_token(u), user=pub_user(u))

    @app.get("/api/me")
    @auth()
    def me():
        gr = q1("SELECT id,name,kra_pin,phone FROM garages WHERE id=?", gid())
        return jsonify(user=pub_user(g.user), garage=dict(gr), vat_rate=VAT_RATE)


    # ---------- password reset ----------
    def hit(key):
        a_ = throttle(key); a_.append(time.time()); attempts[key] = a_

    def deliver(to, subject, text):
        """Send mail via injected sender, SMTP if configured, otherwise write to the server log."""
        sender = app.config["MAIL_SENDER"]
        def smtp_send():
            host = os.environ.get("GARI_SMTP_HOST")
            if not host:
                app.logger.warning("MAIL (SMTP not configured) to=%s subject=%s\n%s", to, subject, text); return
            try:
                msg = EmailMessage(); msg["From"] = os.environ.get("GARI_MAIL_FROM", "Gari <no-reply@localhost>")
                msg["To"] = to; msg["Subject"] = subject; msg.set_content(text)
                with smtplib.SMTP(host, int(os.environ.get("GARI_SMTP_PORT", 587)), timeout=10) as s_:
                    if os.environ.get("GARI_SMTP_TLS", "1") == "1": s_.starttls()
                    if os.environ.get("GARI_SMTP_USER"): s_.login(os.environ["GARI_SMTP_USER"], os.environ.get("GARI_SMTP_PASSWORD", ""))
                    s_.send_message(msg)
            except Exception:
                app.logger.exception("Could not send email to %s", to)
        if sender: sender(to, subject, text)
        elif os.environ.get("GARI_SMTP_HOST") and not app.config["MAIL_SYNC"]: threading.Thread(target=smtp_send, daemon=True).start()
        else: smtp_send()

    @app.get("/reset/<token>")
    def reset_page(token): return send_from_directory(app.static_folder, "reset.html")

    @app.post("/api/auth/forgot")
    def forgot():
        d = body(); em = (d.get("email") or "").strip().lower() if isinstance(d.get("email"), str) else ""
        hit("forgot|" + (request.remote_addr or "")); 
        if em: hit("forgot|" + em)
        u = q1("SELECT * FROM users WHERE email=? AND active=1", em) if em else None
        if u:
            run("UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL", now(), u["id"])
            tok = secrets.token_urlsafe(32)
            exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=app.config["RESET_TTL_MIN"])).strftime("%Y-%m-%d %H:%M:%S")
            run("INSERT INTO password_resets(user_id,token_hash,expires_at) VALUES(?,?,?)", u["id"], hashlib.sha256(tok.encode()).hexdigest(), exp)
            g.user = u; audit("password.reset_requested")
            base = (os.environ.get("GARI_BASE_URL") or request.host_url).rstrip("/")
            g.db.commit()  # token must exist before the email goes out
            deliver(u["email"], "Reset your Gari password",
                    f"Hi {u['name']},\n\nUse this link to choose a new password:\n{base}/reset/{tok}\n\n"
                    f"It works once and expires in {app.config['RESET_TTL_MIN']} minutes. If you didn't ask for this, ignore this email and your password stays the same.\n\nGari")
        # identical answer whether or not the account exists, so emails can't be probed
        return jsonify(ok=True, message="If that email is registered, a reset link is on its way. It expires in %d minutes." % app.config["RESET_TTL_MIN"])

    @app.post("/api/auth/reset")
    def reset_password():
        d = body(); hit("reset|" + (request.remote_addr or ""))
        pw = password(d.get("password")); tok = d.get("token") if isinstance(d.get("token"), str) else ""
        r = q1("""SELECT r.id rid, u.* FROM password_resets r JOIN users u ON u.id=r.user_id
                  WHERE r.token_hash=? AND r.used_at IS NULL AND r.expires_at>? AND u.active=1""", hashlib.sha256(tok.encode()).hexdigest(), now())
        if not r: raise ApiError("This reset link is invalid or has expired. Request a new one.", 400, "token")
        run("UPDATE users SET pw_hash=?, token_version=token_version+1 WHERE id=?", hash_pw(pw), r["id"])
        run("UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL", now(), r["id"])
        g.user = q1("SELECT * FROM users WHERE id=?", r["id"]); audit("password.reset_done")
        attempts.pop("forgot|" + r["email"], None)
        return jsonify(ok=True)

    @app.post("/api/me/password")
    @auth()
    def change_password():
        d = body()
        if not check_pw(d.get("current") or "", g.user["pw_hash"]): raise ApiError("Current password is incorrect", 400, "current")
        pw = password(d.get("password"))
        if check_pw(pw, g.user["pw_hash"]): raise ApiError("Choose a password you haven't used just now", 400, "password")
        run("UPDATE users SET pw_hash=?, token_version=token_version+1 WHERE id=?", hash_pw(pw), g.user["id"]); audit("password.changed")
        return jsonify(token=make_token(q1("SELECT * FROM users WHERE id=?", g.user["id"])))

    # ---------- team ----------
    @app.get("/api/users")
    @auth("owner", "manager")
    def users():
        return jsonify(rows(q("SELECT id,name,email,phone,role,active FROM users WHERE garage_id=? ORDER BY role,name", gid())))

    @app.post("/api/users")
    @auth("owner", "manager")
    def add_user():
        d = body(); role = s(d, "role")
        if role not in ("manager", "mechanic"): raise ApiError("Role must be manager or mechanic", field="role")
        if role == "manager" and g.user["role"] != "owner": raise ApiError("Only the owner can add managers", 403)
        em = email(d.get("email"))
        if q1("SELECT 1 FROM users WHERE email=?", em): raise ApiError("That email is already registered", 409, "email")
        uid = run("INSERT INTO users(garage_id,name,phone,email,pw_hash,role) VALUES(?,?,?,?,?,?)",
                  gid(), s(d, "name", mx=80), phone(d.get("phone")), em, hash_pw(password(d.get("password"))), role).lastrowid
        audit("user.add", f"{em} as {role}")
        return jsonify(rows(q("SELECT id,name,email,phone,role,active FROM users WHERE id=?", uid))[0]), 201

    @app.patch("/api/users/<int:uid>")
    @auth("owner", "manager")
    def edit_user(uid):
        u = q1("SELECT * FROM users WHERE id=? AND garage_id=?", uid, gid())
        if not u: raise ApiError("Team member not found", 404)
        if u["role"] == "owner": raise ApiError("The owner account can't be changed here", 403)
        if u["role"] == "manager" and g.user["role"] != "owner": raise ApiError("Only the owner can change managers", 403)
        d = body()
        if "active" in d: run("UPDATE users SET active=? WHERE id=?", 1 if d["active"] else 0, uid)
        audit("user.edit", f"{uid} {d}")
        return jsonify(ok=True)

    @app.post("/api/users/<int:uid>/password")
    @auth("owner", "manager")
    def set_user_password(uid):
        u = q1("SELECT * FROM users WHERE id=? AND garage_id=?", uid, gid())
        if not u: raise ApiError("Team member not found", 404)
        if u["role"] == "owner" or u["id"] == g.user["id"]: raise ApiError("Use 'Change password' or 'Forgot password' for this account", 403)
        if u["role"] == "manager" and g.user["role"] != "owner": raise ApiError("Only the owner can reset a manager's password", 403)
        run("UPDATE users SET pw_hash=?, token_version=token_version+1 WHERE id=?", hash_pw(password(body().get("password"))), uid)
        audit("password.set_by_manager", u["email"])
        return jsonify(ok=True)

    # ---------- customers & vehicles ----------
    @app.get("/api/vehicles")
    @auth()
    def vehicles():
        term = "%" + (request.args.get("q") or "").strip().replace(" ", "").upper() + "%"
        tl = "%" + (request.args.get("q") or "").strip().lower() + "%"
        r = q("""SELECT v.id,v.plate,v.make,v.model,v.year,v.mileage,c.id customer_id,c.name customer,c.phone
                 FROM vehicles v JOIN customers c ON c.id=v.customer_id
                 WHERE v.garage_id=? AND (v.plate LIKE ? OR lower(c.name) LIKE ? OR c.phone LIKE ?)
                 ORDER BY v.created_at DESC LIMIT 50""", gid(), term, tl, tl)
        return jsonify(rows(r))

    @app.post("/api/vehicles")
    @auth("owner", "manager")
    def add_vehicle():
        d = body(); pl = plate(d.get("plate")); ph = phone(d.get("phone"))
        if q1("SELECT 1 FROM vehicles WHERE garage_id=? AND plate=?", gid(), pl): raise ApiError("This vehicle is already registered", 409, "plate")
        c = q1("SELECT id FROM customers WHERE garage_id=? AND phone=?", gid(), ph)
        if c: cid = c["id"]
        else:
            cid = run("INSERT INTO customers(garage_id,name,phone,email,consent_sms) VALUES(?,?,?,?,?)",
                      gid(), s(d, "customer_name", label="Customer name", mx=80), ph,
                      email(d["email"]) if d.get("email") else None, 1 if d.get("consent_sms") else 0).lastrowid
        year = n(d, "year", req=False, lo=1950, hi=dt.date.today().year + 1)
        vid = run("INSERT INTO vehicles(garage_id,customer_id,plate,make,model,year,mileage) VALUES(?,?,?,?,?,?,?)",
                  gid(), cid, pl, s(d, "make", req=False, mx=40), s(d, "model", req=False, mx=40), year,
                  n(d, "mileage", req=False, hi=2_000_000) or 0).lastrowid
        audit("vehicle.add", pl)
        return jsonify(id=vid, customer_id=cid, plate=pl), 201

    @app.get("/api/vehicles/<int:vid>")
    @auth()
    def vehicle(vid):
        v = q1("""SELECT v.*,c.name customer,c.phone FROM vehicles v JOIN customers c ON c.id=v.customer_id
                  WHERE v.id=? AND v.garage_id=?""", vid, gid())
        if not v: raise ApiError("Vehicle not found", 404)
        jobs = q("""SELECT id,number,status,complaint,mileage_in,created_at FROM jobs
                    WHERE vehicle_id=? AND garage_id=? ORDER BY created_at DESC""", vid, gid())
        return jsonify(vehicle=dict(v), jobs=rows(jobs))

    # ---------- parts / stock ----------
    PART_COLS = "id,sku,name,category,supplier,qty,reorder_level,sell_price" 

    def part_row(p):
        d = dict(p)
        if not is_staff(): d.pop("unit_cost", None)
        d["low"] = p["qty"] <= p["reorder_level"]
        return d

    @app.get("/api/parts")
    @auth()
    def parts():
        t = "%" + (request.args.get("q") or "").strip().lower() + "%"
        sql = "SELECT * FROM parts WHERE garage_id=? AND active=1 AND (lower(name) LIKE ? OR lower(sku) LIKE ? OR lower(IFNULL(category,'')) LIKE ?)"
        if request.args.get("low") == "1": sql += " AND qty<=reorder_level"
        return jsonify([part_row(p) for p in q(sql + " ORDER BY name LIMIT 300", gid(), t, t, t)])

    @app.post("/api/parts")
    @auth("owner", "manager")
    def add_part():
        d = body(); sku = s(d, "sku", label="SKU", mx=40).upper()
        if q1("SELECT 1 FROM parts WHERE garage_id=? AND sku=?", gid(), sku): raise ApiError("That SKU already exists", 409, "sku")
        cost, price = n(d, "unit_cost", lo=0, hi=10_000_000, label="Cost price"), n(d, "sell_price", lo=0, hi=10_000_000, label="Selling price")
        qty = n(d, "qty", req=False, hi=100000) or 0
        pid = run("INSERT INTO parts(garage_id,sku,name,category,supplier,unit_cost,sell_price,qty,reorder_level) VALUES(?,?,?,?,?,?,?,?,?)",
                  gid(), sku, s(d, "name", mx=100), s(d, "category", req=False, mx=40), s(d, "supplier", req=False, mx=80),
                  cost, price, qty, n(d, "reorder_level", req=False, hi=100000) or 0).lastrowid
        if qty: run("INSERT INTO stock_moves(garage_id,part_id,delta,reason,user_id) VALUES(?,?,?,?,?)", gid(), pid, qty, "opening stock", g.user["id"])
        audit("part.add", sku)
        return jsonify(part_row(q1("SELECT * FROM parts WHERE id=?", pid))), 201

    @app.patch("/api/parts/<int:pid>")
    @auth("owner", "manager")
    def edit_part(pid):
        p = q1("SELECT * FROM parts WHERE id=? AND garage_id=?", pid, gid())
        if not p: raise ApiError("Part not found", 404)
        d = body()
        for k, lab in (("unit_cost", "Cost price"), ("sell_price", "Selling price"), ("reorder_level", "Reorder level")):
            if k in d: run(f"UPDATE parts SET {k}=? WHERE id=?", n(d, k, hi=10_000_000, label=lab), pid)
        if "name" in d: run("UPDATE parts SET name=? WHERE id=?", s(d, "name", mx=100), pid)
        audit("part.edit", f"{p['sku']} {d}")
        return jsonify(part_row(q1("SELECT * FROM parts WHERE id=?", pid)))

    @app.post("/api/parts/<int:pid>/adjust")
    @auth("owner", "manager")
    def adjust(pid):
        p = q1("SELECT * FROM parts WHERE id=? AND garage_id=?", pid, gid())
        if not p: raise ApiError("Part not found", 404)
        d = body(); delta = n(d, "delta", lo=-100000, hi=100000, label="Quantity")
        if delta == 0: raise ApiError("Quantity can't be zero", field="delta")
        reason = s(d, "reason", label="Reason", mx=60)
        if reason not in ("received", "stocktake", "damaged", "returned to supplier"): raise ApiError("Pick a valid reason", field="reason")
        if delta < 0 and reason == "received": raise ApiError("Received stock must be positive", field="delta")
        if delta > 0 and reason in ("damaged", "returned to supplier"): raise ApiError(f"'{reason}' must reduce stock", field="delta")
        cur = run("UPDATE parts SET qty=qty+? WHERE id=? AND garage_id=? AND qty+?>=0", delta, pid, gid(), delta)
        if cur.rowcount == 0: raise ApiError(f"Only {p['qty']} in stock. You can't remove {-delta}.", 409, "delta")
        if "unit_cost" in d and d["unit_cost"] not in (None, "") and delta > 0:
            run("UPDATE parts SET unit_cost=? WHERE id=?", n(d, "unit_cost", hi=10_000_000), pid)
        run("INSERT INTO stock_moves(garage_id,part_id,delta,reason,ref,user_id) VALUES(?,?,?,?,?,?)",
            gid(), pid, delta, reason, s(d, "ref", req=False, mx=60), g.user["id"])
        audit("stock.adjust", f"{p['sku']} {delta:+d} {reason}")
        return jsonify(part_row(q1("SELECT * FROM parts WHERE id=?", pid)))

    @app.get("/api/parts/<int:pid>/moves")
    @auth("owner", "manager")
    def moves(pid):
        if not q1("SELECT 1 FROM parts WHERE id=? AND garage_id=?", pid, gid()): raise ApiError("Part not found", 404)
        return jsonify(rows(q("""SELECT m.id,m.delta,m.reason,m.ref,m.created_at,u.name user FROM stock_moves m
            LEFT JOIN users u ON u.id=m.user_id WHERE m.part_id=? ORDER BY m.id DESC LIMIT 100""", pid)))

    # ---------- jobs ----------
    FLOW = {"intake": {"diagnosing", "cancelled"}, "diagnosing": {"quoted", "cancelled"},
            "quoted": {"approved", "diagnosing", "cancelled"}, "approved": {"in_progress", "cancelled"},
            "in_progress": {"qa", "quoted"}, "qa": {"ready", "in_progress"}, "ready": {"in_progress"},
            "invoiced": set(), "cancelled": set()}
    MECH_CAN = {"diagnosing", "quoted", "in_progress", "qa"}
    EDITABLE = {"intake", "diagnosing", "quoted", "approved", "in_progress"}

    def job_or_404(jid):
        j = q1("SELECT * FROM jobs WHERE id=? AND garage_id=?", jid, gid())
        if not j: raise ApiError("Job not found", 404)
        if g.user["role"] == "mechanic" and j["mechanic_id"] != g.user["id"]: raise ApiError("This job is assigned to someone else", 403)
        return j

    def event(jid, text): run("INSERT INTO job_events(garage_id,job_id,user_id,text) VALUES(?,?,?,?)", gid(), jid, g.user["id"] if getattr(g, "user", None) else None, text)
    def touch(jid): run("UPDATE jobs SET updated_at=? WHERE id=?", now(), jid)

    def totals(jid):
        r = q1("SELECT IFNULL(SUM(qty*unit_price),0) sub FROM job_items WHERE job_id=?", jid)["sub"]
        vat = round(r * VAT_RATE / 100)
        return {"subtotal": r, "vat": vat, "total": r + vat}

    def job_dict(j, detail=False):
        d = {k: j[k] for k in ("id", "number", "status", "complaint", "mileage_in", "created_at", "updated_at", "promised_at", "mechanic_id", "vehicle_id", "customer_id", "approved_total", "approved_at")}
        v = q1("SELECT plate,make,model FROM vehicles WHERE id=?", j["vehicle_id"])
        c = q1("SELECT name,phone FROM customers WHERE id=?", j["customer_id"])
        m = q1("SELECT name FROM users WHERE id=?", j["mechanic_id"]) if j["mechanic_id"] else None
        d.update(plate=v["plate"], make=v["make"], model=v["model"], customer=c["name"], mechanic=m["name"] if m else None)
        t = totals(j["id"]); d["totals"] = t
        d["needs_reapproval"] = bool(j["approved_total"] is not None and t["total"] > j["approved_total"] and j["status"] in ("in_progress", "qa", "ready", "approved"))
        if detail:
            d.update(diagnosis=j["diagnosis"], fuel_level=j["fuel_level"], belongings=j["belongings"], phone=c["phone"],
                     approval_method=j["approval_method"])
            if j["status"] == "quoted": d["approval_token"] = j["approval_token"]
            items = rows(q("""SELECT i.id,i.kind,i.part_id,i.description,i.qty,i.unit_price,i.unit_cost,u.name added_by
                  FROM job_items i LEFT JOIN users u ON u.id=i.added_by WHERE i.job_id=? ORDER BY i.id""", j["id"]))
            if not is_staff():
                for i in items: i.pop("unit_cost")
                for k in ("totals",): d.pop(k)
                d["needs_reapproval"] = d["needs_reapproval"]
            d["items"] = items
            d["events"] = rows(q("""SELECT e.text,e.created_at,u.name user FROM job_events e LEFT JOIN users u ON u.id=e.user_id
                  WHERE e.job_id=? ORDER BY e.id DESC""", j["id"]))
            inv = q1("SELECT id,number,total,paid,status,etims_ref FROM invoices WHERE job_id=?", j["id"])
            d["invoice"] = dict(inv) if inv and is_staff() else None
        elif not is_staff():
            d.pop("totals")
        return d

    @app.get("/api/jobs")
    @auth()
    def jobs():
        sql, a = "SELECT * FROM jobs WHERE garage_id=?", [gid()]
        if g.user["role"] == "mechanic": sql += " AND mechanic_id=?"; a.append(g.user["id"])
        st = request.args.get("status")
        if st == "open": sql += " AND status NOT IN ('invoiced','cancelled')"
        elif st: sql += " AND status=?"; a.append(st)
        if request.args.get("mechanic") and is_staff(): sql += " AND mechanic_id=?"; a.append(int(request.args["mechanic"]) if request.args["mechanic"].isdigit() else 0)
        return jsonify([job_dict(j) for j in q(sql + " ORDER BY updated_at DESC LIMIT 300", *a)])

    @app.post("/api/jobs")
    @auth("owner", "manager")
    def create_job():
        d = body(); v = q1("SELECT * FROM vehicles WHERE id=? AND garage_id=?", n(d, "vehicle_id", label="Vehicle"), gid())
        if not v: raise ApiError("Vehicle not found", 404, "vehicle_id")
        if q1("SELECT 1 FROM jobs WHERE vehicle_id=? AND status NOT IN ('invoiced','cancelled')", v["id"]):
            raise ApiError("This vehicle already has an open job card", 409, "vehicle_id")
        mech = None
        if d.get("mechanic_id"):
            mech = q1("SELECT id FROM users WHERE id=? AND garage_id=? AND active=1 AND role='mechanic'", n(d, "mechanic_id"), gid())
            if not mech: raise ApiError("Mechanic not found", 404, "mechanic_id")
        mil = n(d, "mileage_in", req=False, hi=2_000_000)
        run("UPDATE garages SET job_seq=job_seq+1 WHERE id=?", gid())
        seq = q1("SELECT job_seq FROM garages WHERE id=?", gid())["job_seq"]
        number = f"JC-{seq:05d}"
        jid = run("""INSERT INTO jobs(garage_id,number,vehicle_id,customer_id,mechanic_id,complaint,mileage_in,fuel_level,belongings,promised_at,created_by)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", gid(), number, v["id"], v["customer_id"], mech["id"] if mech else None,
                  s(d, "complaint", label="Customer complaint", mx=1000), mil, s(d, "fuel_level", req=False, mx=20),
                  s(d, "belongings", req=False, mx=300), s(d, "promised_at", req=False, mx=30), g.user["id"]).lastrowid
        if mil: run("UPDATE vehicles SET mileage=? WHERE id=? AND mileage<?", mil, v["id"], mil)
        event(jid, f"Vehicle checked in. Job card {number} opened." + (f" Assigned to mechanic." if mech else ""))
        audit("job.create", number)
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True)), 201

    @app.get("/api/jobs/<int:jid>")
    @auth()
    def job(jid): return jsonify(job_dict(job_or_404(jid), True))

    @app.patch("/api/jobs/<int:jid>")
    @auth()
    def edit_job(jid):
        j = job_or_404(jid); d = body()
        if j["status"] in ("invoiced", "cancelled"): raise ApiError("This job is closed", 409)
        if "diagnosis" in d:
            run("UPDATE jobs SET diagnosis=? WHERE id=?", s(d, "diagnosis", req=False, mx=2000), jid); event(jid, "Diagnosis updated")
        if "mechanic_id" in d:
            if not is_staff(): raise ApiError("Only a manager can assign mechanics", 403)
            if d["mechanic_id"] in (None, ""): run("UPDATE jobs SET mechanic_id=NULL WHERE id=?", jid); event(jid, "Mechanic unassigned")
            else:
                m = q1("SELECT id,name FROM users WHERE id=? AND garage_id=? AND active=1 AND role='mechanic'", n(d, "mechanic_id"), gid())
                if not m: raise ApiError("Mechanic not found", 404, "mechanic_id")
                run("UPDATE jobs SET mechanic_id=? WHERE id=?", m["id"], jid); event(jid, f"Assigned to {m['name']}")
        if "promised_at" in d and is_staff(): run("UPDATE jobs SET promised_at=? WHERE id=?", s(d, "promised_at", req=False, mx=30), jid)
        touch(jid)
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True))

    @app.post("/api/jobs/<int:jid>/status")
    @auth()
    def set_status(jid):
        j = job_or_404(jid); to = s(body(), "status")
        if to not in FLOW[j["status"]]: raise ApiError(f"A job in '{j['status']}' can't move to '{to}'", 409)
        if g.user["role"] == "mechanic" and to not in MECH_CAN: raise ApiError("A manager needs to do this step", 403)
        if to == "approved": raise ApiError("Record customer approval instead", 409)
        if to in ("diagnosing", "in_progress") and not j["mechanic_id"] and j["status"] == "intake":
            raise ApiError("Assign a mechanic before starting", 409)
        if to == "quoted":
            if not q1("SELECT 1 FROM job_items WHERE job_id=?", jid): raise ApiError("Add at least one part or labour line before quoting", 409)
            run("UPDATE jobs SET approval_token=? WHERE id=?", secrets.token_urlsafe(24), jid)
        if to == "qa" and not j["diagnosis"]: raise ApiError("Add the diagnosis / work done notes before QA", 409)
        if to == "ready" and j["approved_total"] is not None and totals(jid)["total"] > j["approved_total"]:
            raise ApiError("Extra work isn't approved yet. Get customer approval first.", 409)
        if to == "cancelled":
            for it in q("SELECT * FROM job_items WHERE job_id=? AND kind='part'", jid): release(it, "job cancelled")
        run("UPDATE jobs SET status=? WHERE id=?", to, jid); touch(jid)
        event(jid, f"Status: {j['status'].replace('_',' ')} \u2192 {to.replace('_',' ')}"); audit("job.status", f"{j['number']} {to}")
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True))

    @app.post("/api/jobs/<int:jid>/approve")
    @auth("owner", "manager")
    def approve(jid):
        j = job_or_404(jid); d = body(); method = s(d, "method", label="Approval method")
        if method not in ("phone", "in_person", "whatsapp", "sms"): raise ApiError("Pick how the customer approved", field="method")
        if j["status"] not in ("quoted", "in_progress", "qa", "ready"): raise ApiError("There's nothing waiting for approval", 409)
        if j["status"] == "quoted":
            run("UPDATE jobs SET status='approved' WHERE id=?", jid)
        t = totals(jid)["total"]
        run("UPDATE jobs SET approved_total=?, approved_at=?, approval_method=?, approval_token=NULL WHERE id=?", t, now(), method, jid)
        touch(jid); event(jid, f"Customer approved KES {t:,} ({method.replace('_',' ')})"); audit("job.approve", f"{j['number']} {t}")
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True))

    def release(it, why):
        run("UPDATE parts SET qty=qty+? WHERE id=?", it["qty"], it["part_id"])
        run("INSERT INTO stock_moves(garage_id,part_id,delta,reason,ref,user_id) VALUES(?,?,?,?,?,?)",
            gid(), it["part_id"], it["qty"], "returned from job", why, g.user["id"])

    @app.post("/api/jobs/<int:jid>/items")
    @auth()
    def add_item(jid):
        j = job_or_404(jid); d = body()
        if j["status"] not in EDITABLE: raise ApiError("Lines can't be changed at this stage", 409)
        kind = s(d, "kind")
        qty = n(d, "qty", lo=1, hi=10000, label="Quantity")
        if kind == "part":
            p = q1("SELECT * FROM parts WHERE id=? AND garage_id=? AND active=1", n(d, "part_id", label="Part"), gid())
            if not p: raise ApiError("Part not found", 404, "part_id")
            price = p["sell_price"]
            if d.get("unit_price") not in (None, "") and is_staff(): price = n(d, "unit_price", hi=10_000_000, label="Price")
            cur = run("UPDATE parts SET qty=qty-? WHERE id=? AND qty>=?", qty, p["id"], qty)
            if cur.rowcount == 0: raise ApiError(f"Only {p['qty']} {p['name']} in stock", 409, "qty")
            run("INSERT INTO stock_moves(garage_id,part_id,delta,reason,ref,user_id) VALUES(?,?,?,?,?,?)", gid(), p["id"], -qty, "used on job", j["number"], g.user["id"])
            run("INSERT INTO job_items(garage_id,job_id,kind,part_id,description,qty,unit_price,unit_cost,added_by) VALUES(?,?,?,?,?,?,?,?,?)",
                gid(), jid, "part", p["id"], p["name"], qty, price, p["unit_cost"], g.user["id"])
            event(jid, f"Added {qty} \u00d7 {p['name']}")
        elif kind == "labour":
            if not is_staff(): raise ApiError("Labour is priced by the manager", 403)
            desc = s(d, "description", label="Description", mx=150)
            run("INSERT INTO job_items(garage_id,job_id,kind,description,qty,unit_price,added_by) VALUES(?,?,?,?,?,?,?)",
                gid(), jid, "labour", desc, qty, n(d, "unit_price", hi=10_000_000, label="Price"), g.user["id"])
            event(jid, f"Added labour: {desc}")
        else:
            raise ApiError("Kind must be part or labour", field="kind")
        if j["status"] == "quoted": run("UPDATE jobs SET approval_token=? WHERE id=?", secrets.token_urlsafe(24), jid)
        touch(jid)
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True)), 201

    @app.delete("/api/jobs/<int:jid>/items/<int:iid>")
    @auth()
    def del_item(jid, iid):
        j = job_or_404(jid)
        if j["status"] not in EDITABLE: raise ApiError("Lines can't be changed at this stage", 409)
        it = q1("SELECT * FROM job_items WHERE id=? AND job_id=?", iid, jid)
        if not it: raise ApiError("Line not found", 404)
        if not is_staff() and it["added_by"] != g.user["id"]: raise ApiError("You can only remove lines you added", 403)
        if it["kind"] == "part": release(it, j["number"])
        run("DELETE FROM job_items WHERE id=?", iid)
        if j["status"] == "quoted": run("UPDATE jobs SET approval_token=? WHERE id=?", secrets.token_urlsafe(24), jid)
        event(jid, f"Removed {it['description']}"); touch(jid)
        return jsonify(job_dict(q1("SELECT * FROM jobs WHERE id=?", jid), True))

    # ---------- customer quote link (public) ----------
    def quote_by_token(tok):
        j = q1("SELECT * FROM jobs WHERE approval_token=? AND status='quoted'", tok) if tok and len(tok) > 20 else None
        if not j: raise ApiError("This quote link has expired or was already used", 404)
        return j

    @app.get("/api/public/quote/<tok>")
    def pub_quote(tok):
        j = quote_by_token(tok)
        gr = q1("SELECT name,phone FROM garages WHERE id=?", j["garage_id"]); v = q1("SELECT plate,make,model FROM vehicles WHERE id=?", j["vehicle_id"])
        items = rows(q("SELECT kind,description,qty,unit_price FROM job_items WHERE job_id=?", j["id"]))
        sub = sum(i["qty"] * i["unit_price"] for i in items); vat = round(sub * VAT_RATE / 100)
        return jsonify(garage=gr["name"], garage_phone=gr["phone"], number=j["number"], vehicle=dict(v), diagnosis=j["diagnosis"],
                       items=items, subtotal=sub, vat=vat, total=sub + vat)

    @app.post("/api/public/quote/<tok>/approve")
    def pub_approve(tok):
        throttle("pub|" + (request.remote_addr or ""))
        j = quote_by_token(tok); t = q1("SELECT IFNULL(SUM(qty*unit_price),0) s FROM job_items WHERE job_id=?", j["id"])["s"]
        t += round(t * VAT_RATE / 100)
        run("UPDATE jobs SET status='approved',approved_total=?,approved_at=?,approval_method='link',approval_token=NULL,updated_at=? WHERE id=?", t, now(), now(), j["id"])
        run("INSERT INTO job_events(garage_id,job_id,text) VALUES(?,?,?)", j["garage_id"], j["id"], f"Customer approved KES {t:,} using the quote link")
        return jsonify(ok=True, total=t)

    # ---------- invoices & payments ----------
    @app.post("/api/jobs/<int:jid>/invoice")
    @auth("owner", "manager")
    def make_invoice(jid):
        j = job_or_404(jid)
        if j["status"] != "ready": raise ApiError("Only jobs marked ready can be invoiced", 409)
        t = totals(jid)
        if t["subtotal"] <= 0: raise ApiError("There's nothing to invoice", 409)
        if j["approved_total"] is not None and t["total"] > j["approved_total"]: raise ApiError("Extra work isn't approved yet", 409)
        run("UPDATE garages SET inv_seq=inv_seq+1 WHERE id=?", gid())
        seq = q1("SELECT inv_seq FROM garages WHERE id=?", gid())["inv_seq"]
        iid = run("INSERT INTO invoices(garage_id,job_id,number,subtotal,vat,total) VALUES(?,?,?,?,?,?)",
                  gid(), jid, f"INV-{seq:05d}", t["subtotal"], t["vat"], t["total"]).lastrowid
        run("UPDATE jobs SET status='invoiced' WHERE id=?", jid); touch(jid)
        event(jid, f"Invoice INV-{seq:05d} issued for KES {t['total']:,}"); audit("invoice.create", f"INV-{seq:05d}")
        return jsonify(invoice_dict(iid)), 201

    def invoice_dict(iid):
        i = q1("""SELECT i.*,j.number job_number,v.plate,c.name customer,c.phone FROM invoices i JOIN jobs j ON j.id=i.job_id
                  JOIN vehicles v ON v.id=j.vehicle_id JOIN customers c ON c.id=j.customer_id WHERE i.id=? AND i.garage_id=?""", iid, gid())
        if not i: raise ApiError("Invoice not found", 404)
        d = dict(i); d["balance"] = i["total"] - i["paid"]
        d["items"] = rows(q("SELECT kind,description,qty,unit_price FROM job_items WHERE job_id=?", i["job_id"]))
        d["payments"] = rows(q("SELECT method,amount,reference,created_at FROM payments WHERE invoice_id=? ORDER BY id", iid))
        return d

    @app.get("/api/invoices")
    @auth("owner", "manager")
    def invoices():
        r = q("""SELECT i.id,i.number,i.total,i.paid,i.status,i.created_at,v.plate,c.name customer FROM invoices i
                 JOIN jobs j ON j.id=i.job_id JOIN vehicles v ON v.id=j.vehicle_id JOIN customers c ON c.id=j.customer_id
                 WHERE i.garage_id=? ORDER BY i.id DESC LIMIT 200""", gid())
        return jsonify(rows(r))

    @app.get("/api/invoices/<int:iid>")
    @auth("owner", "manager")
    def invoice(iid): return jsonify(invoice_dict(iid))

    @app.patch("/api/invoices/<int:iid>")
    @auth("owner", "manager")
    def edit_invoice(iid):
        invoice_dict(iid); ref = s(body(), "etims_ref", label="eTIMS invoice number", mx=60)
        run("UPDATE invoices SET etims_ref=? WHERE id=?", ref, iid); audit("invoice.etims", f"{iid} {ref}")
        return jsonify(invoice_dict(iid))

    @app.post("/api/invoices/<int:iid>/pay")
    @auth("owner", "manager")
    def pay(iid):
        inv = invoice_dict(iid); d = body(); method = s(d, "method", label="Payment method")
        if method not in ("cash", "mpesa", "card", "bank"): raise ApiError("Pick a valid payment method", field="method")
        amt = n(d, "amount", lo=1, hi=10_000_000, label="Amount")
        if amt > inv["balance"]: raise ApiError(f"Balance is only KES {inv['balance']:,}", 409, "amount")
        ref = s(d, "reference", req=False, mx=40)
        if method == "mpesa":
            ref = (ref or "").upper()
            if not re.fullmatch(r"[A-Z0-9]{10}", ref): raise ApiError("M-Pesa code has 10 letters and numbers, e.g. SGH7K2L9QP", field="reference")
        try:
            run("INSERT INTO payments(garage_id,invoice_id,method,amount,reference,user_id) VALUES(?,?,?,?,?,?)", gid(), iid, method, amt, ref, g.user["id"])
        except sqlite3.IntegrityError:
            raise ApiError("This payment reference was already recorded", 409, "reference")
        paid = inv["paid"] + amt
        run("UPDATE invoices SET paid=?,status=? WHERE id=?", paid, "paid" if paid >= inv["total"] else "partial", iid)
        audit("invoice.pay", f"{inv['number']} {method} {amt}")
        return jsonify(invoice_dict(iid))

    # ---------- reports ----------
    @app.get("/api/reports/summary")
    @auth("owner", "manager")
    def report():
        days = min(max(int(request.args.get("days", 30)) if str(request.args.get("days", "30")).isdigit() else 30, 1), 365)
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"); G = gid()
        coll = q1("SELECT IFNULL(SUM(amount),0) s FROM payments WHERE garage_id=? AND created_at>=?", G, since)["s"]
        inv = q1("SELECT IFNULL(SUM(total),0) t, IFNULL(SUM(vat),0) v, COUNT(*) c FROM invoices WHERE garage_id=? AND created_at>=?", G, since)
        owed = q1("SELECT IFNULL(SUM(total-paid),0) s, COUNT(*) c FROM invoices WHERE garage_id=? AND status!='paid'", G)
        prof = q1("""SELECT IFNULL(SUM(it.qty*it.unit_price),0) rev, IFNULL(SUM(it.qty*it.unit_cost),0) cost,
                     IFNULL(SUM(CASE WHEN it.kind='labour' THEN it.qty*it.unit_price END),0) labour
                     FROM job_items it JOIN invoices i ON i.job_id=it.job_id WHERE i.garage_id=? AND i.created_at>=?""", G, since)
        by_status = {r["status"]: r["c"] for r in q("SELECT status,COUNT(*) c FROM jobs WHERE garage_id=? GROUP BY status", G)}
        tat = q1("""SELECT AVG((julianday(i.created_at)-julianday(j.created_at))*24) h FROM invoices i JOIN jobs j ON j.id=i.job_id
                    WHERE i.garage_id=? AND i.created_at>=?""", G, since)["h"]
        daily = rows(q("SELECT date(created_at) day, SUM(amount) amount FROM payments WHERE garage_id=? AND created_at>=? GROUP BY day ORDER BY day", G, since))
        by_method = rows(q("SELECT method, SUM(amount) amount FROM payments WHERE garage_id=? AND created_at>=? GROUP BY method", G, since))
        mech = rows(q("""SELECT u.id,u.name, COUNT(DISTINCT j.id) jobs,
                         IFNULL(SUM(CASE WHEN it.kind='labour' THEN it.qty*it.unit_price END),0) labour_revenue,
                         IFNULL(ROUND(AVG((julianday(i.created_at)-julianday(j.created_at))*24),1),0) avg_hours
                         FROM users u LEFT JOIN jobs j ON j.mechanic_id=u.id AND j.status='invoiced'
                         LEFT JOIN invoices i ON i.job_id=j.id AND i.created_at>=?
                         LEFT JOIN job_items it ON it.job_id=j.id AND i.id IS NOT NULL
                         WHERE u.garage_id=? AND u.role='mechanic' GROUP BY u.id ORDER BY labour_revenue DESC""", since, G))
        for m in mech:
            m["jobs"] = q1("SELECT COUNT(*) c FROM jobs j JOIN invoices i ON i.job_id=j.id WHERE j.mechanic_id=? AND i.created_at>=?", m["id"], since)["c"]
        top = rows(q("""SELECT it.description name, SUM(it.qty) qty, SUM(it.qty*(it.unit_price-it.unit_cost)) profit FROM job_items it
                        JOIN invoices i ON i.job_id=it.job_id WHERE it.kind='part' AND i.garage_id=? AND i.created_at>=?
                        GROUP BY it.description ORDER BY profit DESC LIMIT 5""", G, since))
        stock = q1("SELECT IFNULL(SUM(qty*unit_cost),0) value, SUM(CASE WHEN qty<=reorder_level THEN 1 ELSE 0 END) low FROM parts WHERE garage_id=? AND active=1", G)
        return jsonify(days=days, collected=coll, invoiced=inv["t"], vat_collected=inv["v"], invoice_count=inv["c"],
                       outstanding=owed["s"], outstanding_count=owed["c"], gross_profit=(prof["rev"] - prof["cost"]),
                       labour_revenue=prof["labour"], avg_turnaround_hours=round(tat, 1) if tat else None, jobs_by_status=by_status,
                       daily=daily, by_method=by_method, mechanics=mech, top_parts=top,
                       stock_value=stock["value"], low_stock=stock["low"] or 0)

    @app.get("/api/audit")
    @auth("owner")
    def audit_view():
        return jsonify(rows(q("""SELECT a.action,a.detail,a.created_at,u.name user FROM audit_log a LEFT JOIN users u ON u.id=a.user_id
                                 WHERE a.garage_id=? ORDER BY a.id DESC LIMIT 100""", gid())))

    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
