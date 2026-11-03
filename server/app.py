#!/usr/bin/env python3
"""Em Tâm Làm Ads — máy chủ nhận khách đặt lịch + trang quản trị.

Chỉ dùng thư viện có sẵn của Python 3 (không cần pip). Dữ liệu lưu trong SQLite.

    python3 app.py --init          tạo cơ sở dữ liệu, in mật khẩu quản trị lần đầu
    python3 app.py --reset-password  đặt lại mật khẩu quản trị (in ra mật khẩu mới)
    python3 app.py                 chạy máy chủ (mặc định 127.0.0.1:8787, đặt sau nginx)

Biến môi trường:
    ETLA_DB             đường dẫn file SQLite (mặc định ./data/leads.db)
    ETLA_HOST/ETLA_PORT địa chỉ lắng nghe
    ETLA_EXTRA_ORIGINS  thêm origin được phép gửi form, cách nhau bằng dấu phẩy
    ETLA_INSECURE_COOKIE=1  chỉ dùng khi thử trên máy (http, không có https)
"""
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ETLA_DB", os.path.join(BASE, "data", "leads.db"))
HOST = os.environ.get("ETLA_HOST", "127.0.0.1")
PORT = int(os.environ.get("ETLA_PORT", "8787"))
ORIGINS = {"https://emtamlamads.com", "https://www.emtamlamads.com"} | {
    o.strip() for o in os.environ.get("ETLA_EXTRA_ORIGINS", "").split(",") if o.strip()
}
SECURE_COOKIE = os.environ.get("ETLA_INSECURE_COOKIE") != "1"
SESSION_TTL = 14 * 24 * 3600
MAX_BODY = 32 * 1024
STATUSES = ["Mới", "Đã liên hệ", "Đã hẹn", "Đã chốt", "Không phù hợp"]
FIELDS = ["kind", "name", "phone", "email", "fanpage", "date", "times", "budget", "goal", "note", "page", "utm"]

# ------------------------------------------------------------------ database
_lock = threading.Lock()


def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _lock, db() as c:
        c.executescript(
            """
            create table if not exists leads(
              id integer primary key autoincrement,
              created_at integer not null,
              kind text, name text, phone text, email text, fanpage text,
              date text, times text, budget text, goal text, note text,
              page text, utm text, ip text,
              status text not null default 'Mới',
              admin_note text not null default '',
              updated_at integer
            );
            create index if not exists leads_created on leads(created_at);
            create table if not exists settings(k text primary key, v text);
            """
        )


def get_setting(k, default=None):
    with db() as c:
        r = c.execute("select v from settings where k=?", (k,)).fetchone()
    return r["v"] if r else default


def set_setting(k, v):
    with _lock, db() as c:
        c.execute("insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v", (k, v))


def secret_key():
    s = get_setting("secret")
    if not s:
        s = secrets.token_hex(32)
        set_setting("secret", s)
    return s


# ------------------------------------------------------------------ password & session
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def check_pw(pw):
    stored = get_setting("pw")
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def new_password():
    pw = "-".join(secrets.token_urlsafe(4) for _ in range(3))
    set_setting("pw", hash_pw(pw))
    set_setting("pw_ver", secrets.token_hex(4))  # đổi mật khẩu = đăng xuất mọi phiên cũ
    return pw


def make_token():
    exp = int(time.time()) + SESSION_TTL
    msg = f"{exp}.{get_setting('pw_ver', '')}"
    sig = hmac.new(secret_key().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid_token(tok):
    try:
        exp, sig = tok.split(".", 1)
        if int(exp) < time.time():
            return False
        msg = f"{exp}.{get_setting('pw_ver', '')}"
        good = hmac.new(secret_key().encode(), msg.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good)
    except Exception:
        return False


# ------------------------------------------------------------------ rate limit
_hits = {}


def limited(key, n, window):
    now = time.time()
    with _lock:
        arr = [t for t in _hits.get(key, []) if now - t < window]
        arr.append(now)
        _hits[key] = arr
        return len(arr) > n


# ------------------------------------------------------------------ telegram
def tg_call(method, params):
    token = get_setting("tg_token")
    if not token:
        raise RuntimeError("Chưa nhập Telegram bot token")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=10) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError(res.get("description", "Telegram lỗi"))
    return res["result"]


def tg_chat_id():
    chat = get_setting("tg_chat")
    if chat:
        return chat
    # Tự nhận: lấy cuộc trò chuyện gần nhất đã nhắn cho bot (bạn chỉ cần bấm Start bot một lần)
    for upd in reversed(tg_call("getUpdates", {"limit": 20})):
        msg = upd.get("message") or upd.get("channel_post") or {}
        if msg.get("chat", {}).get("id"):
            chat = str(msg["chat"]["id"])
            set_setting("tg_chat", chat)
            return chat
    raise RuntimeError("Bot chưa nhận được tin nào — mở Telegram, tìm bot của bạn và bấm Start")


def tg_send(text):
    tg_call("sendMessage", {"chat_id": tg_chat_id(), "text": text, "disable_web_page_preview": "true"})


def notify(lead):
    if not get_setting("tg_token"):
        return
    lines = [f"🔔 Khách mới: {lead.get('kind') or 'Đăng ký'}", f"👤 {lead['name']}"]
    if lead.get("phone"):
        lines.append(f"📞 {lead['phone']}")
    if lead.get("email"):
        lines.append(f"✉️ {lead['email']}")
    if lead.get("date") or lead.get("times"):
        lines.append("🗓 " + ", ".join(x for x in (lead.get("date"), lead.get("times")) if x) + " (giờ VN)")
    for k, label in (("fanpage", "Fanpage"), ("budget", "Ngân sách ads"), ("goal", "Mục tiêu"), ("note", "Ghi chú")):
        if lead.get(k):
            lines.append(f"{label}: {lead[k]}")
    if lead.get("page"):
        lines.append(f"Trang: {lead['page']}")
    try:
        tg_send("\n".join(lines))
    except Exception as e:  # không để lỗi Telegram làm hỏng việc lưu khách
        sys.stderr.write(f"telegram: {e}\n")


# ------------------------------------------------------------------ HTTP
def clean(v, n=500):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or "")).strip()[:n]


class Handler(BaseHTTPRequestHandler):
    server_version = "etla-admin"

    # ---- helpers
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.client_ip(), fmt % args))

    def client_ip(self):
        return (self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For", "").split(",")[0]
                or self.client_address[0]).strip()

    def send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ORIGINS:
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400"}
        return {}

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too large")
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        if "json" in (self.headers.get("Content-Type") or ""):
            return json.loads(raw or "{}")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    def authed(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return "etla" in c and valid_token(c["etla"].value)

    def admin_post_ok(self):
        # Chống CSRF: cookie SameSite=Strict + header riêng (trình duyệt không cho trang khác tự gửi header này)
        return self.authed() and self.headers.get("X-ETLA") == "1"

    # ---- routes
    def do_OPTIONS(self):
        self.send(204, b"", headers=self.cors())

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            return self.send(200, {"ok": True})
        if path in ("/", "/index.html"):
            return self.send(200, ADMIN_HTML if self.authed() else LOGIN_HTML, "text/html; charset=utf-8",
                             {"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})
        if not self.authed():
            return self.send(401, {"ok": False, "error": "login"})
        if path == "/api/leads":
            with db() as c:
                rows = [dict(r) for r in c.execute("select * from leads order by id desc limit 2000")]
            return self.send(200, {"ok": True, "leads": rows, "statuses": STATUSES})
        if path == "/api/leads.csv":
            with db() as c:
                rows = c.execute("select * from leads order by id desc").fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            cols = ["id", "created_at"] + FIELDS + ["status", "admin_note"]
            w.writerow(cols)
            for r in rows:
                vals = [r[k] for k in cols]
                vals[1] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(vals[1] + 7 * 3600))  # giờ Việt Nam
                w.writerow(["'" + v if isinstance(v, str) and v and v[0] in "=+-@" else v for v in vals])
            return self.send(200, "﻿" + buf.getvalue(), "text/csv; charset=utf-8",
                             {"Content-Disposition": "attachment; filename=khach-dang-ky.csv"})
        if path == "/api/settings":
            tok = get_setting("tg_token") or ""
            return self.send(200, {"ok": True, "tg_token_set": bool(tok), "tg_token_hint": tok[:6] + "…" if tok else "",
                                   "tg_chat": get_setting("tg_chat") or ""})
        self.send(404, {"ok": False})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self.body()
        except Exception:
            return self.send(400, {"ok": False, "error": "bad body"})

        if path == "/api/lead":
            h = self.cors()
            if self.headers.get("Origin") and not h:
                return self.send(403, {"ok": False, "error": "origin"})
            if data.get("website"):  # bẫy spam
                return self.send(200, {"ok": True}, headers=h)
            if limited("lead:" + self.client_ip(), 8, 600):
                return self.send(429, {"ok": False, "error": "Gửi quá nhiều lần, thử lại sau ít phút"}, headers=h)
            lead = {k: clean(data.get(k), 2000 if k == "note" else 300) for k in FIELDS}
            if not lead["name"] or not (lead["phone"] or lead["email"]):
                return self.send(400, {"ok": False, "error": "Thiếu tên hoặc liên hệ"}, headers=h)
            with _lock, db() as c:
                cur = c.execute(
                    f"insert into leads(created_at, ip, {', '.join(FIELDS)}) values(?, ?, {', '.join('?' * len(FIELDS))})",
                    [int(time.time()), self.client_ip()] + [lead[k] for k in FIELDS])
                lead_id = cur.lastrowid
            threading.Thread(target=notify, args=(lead,), daemon=True).start()
            return self.send(200, {"ok": True, "id": lead_id}, headers=h)

        if path == "/login":
            if limited("login:" + self.client_ip(), 10, 900):
                return self.send(429, {"ok": False, "error": "Sai quá nhiều lần, đợi 15 phút"})
            if not check_pw(str(data.get("password", ""))):
                time.sleep(1)
                return self.send(401, {"ok": False, "error": "Sai mật khẩu"})
            c = cookies.SimpleCookie()
            c["etla"] = make_token()
            c["etla"].update({"path": "/", "httponly": True, "samesite": "Strict", "max-age": SESSION_TTL})
            if SECURE_COOKIE:
                c["etla"]["secure"] = True
            return self.send(200, {"ok": True}, headers={"Set-Cookie": c["etla"].OutputString()})

        if path == "/logout":
            return self.send(200, {"ok": True}, headers={"Set-Cookie": "etla=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})

        if not self.admin_post_ok():
            return self.send(401, {"ok": False, "error": "login"})

        m = re.fullmatch(r"/api/leads/(\d+)", path)
        if m:
            sets, vals = [], []
            if "status" in data:
                if data["status"] not in STATUSES:
                    return self.send(400, {"ok": False, "error": "status"})
                sets.append("status=?"); vals.append(data["status"])
            if "admin_note" in data:
                sets.append("admin_note=?"); vals.append(clean(data["admin_note"], 2000))
            if not sets:
                return self.send(400, {"ok": False})
            with _lock, db() as c:
                c.execute(f"update leads set {', '.join(sets)}, updated_at=? where id=?", vals + [int(time.time()), int(m.group(1))])
            return self.send(200, {"ok": True})

        m = re.fullmatch(r"/api/leads/(\d+)/delete", path)
        if m:
            with _lock, db() as c:
                c.execute("delete from leads where id=?", (int(m.group(1)),))
            return self.send(200, {"ok": True})

        if path == "/api/settings/telegram":
            tok = clean(data.get("token"), 200)
            if tok and not re.fullmatch(r"\d+:[\w-]{20,}", tok):
                return self.send(400, {"ok": False, "error": "Token không đúng dạng (vd 123456789:AA...)"})
            set_setting("tg_token", tok)
            set_setting("tg_chat", "")
            return self.send(200, {"ok": True})

        if path == "/api/settings/telegram/test":
            try:
                tg_send("✅ Kết nối thành công! Từ giờ có khách đặt lịch trên emtamlamads.com, bạn sẽ nhận tin ở đây.")
                return self.send(200, {"ok": True, "chat": get_setting("tg_chat")})
            except Exception as e:
                return self.send(400, {"ok": False, "error": str(e)})

        if path == "/api/settings/password":
            if not check_pw(str(data.get("old", ""))):
                return self.send(400, {"ok": False, "error": "Mật khẩu cũ không đúng"})
            new = str(data.get("new", ""))
            if len(new) < 8:
                return self.send(400, {"ok": False, "error": "Mật khẩu mới cần ít nhất 8 ký tự"})
            set_setting("pw", hash_pw(new))
            set_setting("pw_ver", secrets.token_hex(4))
            c = cookies.SimpleCookie()
            c["etla"] = make_token()
            c["etla"].update({"path": "/", "httponly": True, "samesite": "Strict", "max-age": SESSION_TTL})
            if SECURE_COOKIE:
                c["etla"]["secure"] = True
            return self.send(200, {"ok": True}, headers={"Set-Cookie": c["etla"].OutputString()})

        self.send(404, {"ok": False})


CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")

_HEAD = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Quản trị — Em Tâm Làm Ads</title>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0F1113;--card:#181B1F;--line:#2A2E34;--fg:#F3F1EA;--dim:#A9A9A2;--gold:#D6B32C;--gold2:#F0D66B;--ok:#2E8B57;--bad:#C0573A}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:'Be Vietnam Pro',system-ui,sans-serif;font-size:15px}
button,input,select,textarea{font:inherit;color:inherit}
.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.55rem .9rem;border-radius:8px;border:1px solid var(--line);background:#20242A;cursor:pointer;text-decoration:none;font-weight:600;font-size:.88rem}
.btn:hover{border-color:var(--gold)}.btn.pri{background:linear-gradient(135deg,var(--gold2),var(--gold));color:#181410;border:0}
a.btn{color:var(--fg)}a.btn.pri{color:#181410}
input,select,textarea{background:#0B0D0F;border:1px solid var(--line);border-radius:8px;padding:.6rem .7rem;width:100%}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--gold)}
</style></head><body>"""

LOGIN_HTML = _HEAD + """
<main style="min-height:100vh;display:grid;place-items:center;padding:1rem">
<form id="f" style="width:100%;max-width:360px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1.6rem">
<div style="font-weight:800;font-size:1.2rem">Em Tâm <span style="color:var(--gold2)">Làm Ads</span></div>
<p style="color:var(--dim);margin:.3rem 0 1.2rem">Trang quản trị khách đặt lịch</p>
<label for="pw" style="font-size:.85rem;font-weight:600">Mật khẩu</label>
<input id="pw" type="password" autocomplete="current-password" autofocus style="margin:.4rem 0 1rem">
<button class="btn pri" style="width:100%;justify-content:center">Đăng nhập</button>
<p id="err" style="color:var(--bad);min-height:1.2em;margin:.8rem 0 0;font-size:.9rem"></p>
</form></main>
<script>
document.getElementById('f').onsubmit=async e=>{e.preventDefault();
 const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
 const j=await r.json().catch(()=>({}));if(j.ok)location.reload();else document.getElementById('err').textContent=j.error||'Lỗi đăng nhập';};
</script></body></html>"""

ADMIN_HTML = _HEAD + r"""
<style>
header{position:sticky;top:0;z-index:5;background:rgba(15,17,19,.95);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.wrap{max-width:1200px;margin:0 auto;padding:0 1rem}
.top{display:flex;align-items:center;justify-content:space-between;gap:.8rem;height:60px}
.brand{font-weight:800}.brand span{color:var(--gold2)}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:.6rem;margin:1rem 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.8rem;cursor:pointer}
.stat.on{border-color:var(--gold)}.stat b{display:block;font-size:1.5rem}.stat span{color:var(--dim);font-size:.8rem}
.tools{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin-bottom:1rem}.tools input{max-width:280px}.tools select{max-width:260px}
.list{display:grid;gap:.7rem;padding-bottom:3rem}
.lead{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem;display:grid;grid-template-columns:1fr 260px;gap:1rem}
.lead.new{border-left:4px solid var(--gold)}
.lead h3{margin:0;font-size:1.05rem}.kind{display:inline-block;font-size:.72rem;font-weight:700;padding:.15rem .5rem;border-radius:20px;background:#2A2410;color:var(--gold2);margin-left:.4rem;vertical-align:2px}
.meta{color:var(--dim);font-size:.82rem;margin-top:.2rem}
.kv{display:grid;grid-template-columns:auto 1fr;gap:.25rem .8rem;margin-top:.7rem;font-size:.9rem}.kv dt{color:var(--dim)}.kv dd{margin:0;word-break:break-word}
.when{display:inline-block;margin-top:.6rem;padding:.35rem .6rem;border-radius:8px;background:#13261C;color:#7BD88F;font-weight:700;font-size:.88rem}
.acts{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.8rem}
.side{display:grid;gap:.5rem;align-content:start}.side textarea{min-height:70px;resize:vertical}
.saved{font-size:.78rem;color:#7BD88F;min-height:1em}
.empty{color:var(--dim);text-align:center;padding:3rem 1rem;border:1px dashed var(--line);border-radius:12px}
dialog{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:14px;max-width:520px;width:92vw;padding:1.4rem}
dialog::backdrop{background:rgba(0,0,0,.6)}dialog h3{margin-top:0}dialog label{display:block;font-size:.85rem;font-weight:600;margin:.8rem 0 .3rem}
.hint{color:var(--dim);font-size:.85rem;line-height:1.55}.hint ol{padding-left:1.2rem}
@media(max-width:820px){.lead{grid-template-columns:1fr}.stats{grid-template-columns:repeat(3,1fr)}.stats .stat:nth-child(n+4){display:none}.top .hide-m{display:none}.brand{font-size:.9rem}.top .btn{padding:.45rem .6rem;font-size:.8rem}.tools input,.tools select{max-width:none;flex:1 1 100%}}
</style>
<header><div class="wrap top">
 <div class="brand">Em Tâm <span>Làm Ads</span> · Quản trị</div>
 <div style="display:flex;gap:.4rem">
  <a class="btn hide-m" href="/api/leads.csv">⬇ Xuất Excel</a>
  <button class="btn" id="bSet">⚙ Cài đặt</button>
  <button class="btn" id="bOut">Đăng xuất</button>
 </div></div></header>
<main class="wrap">
 <div class="stats" id="stats"></div>
 <div class="tools">
  <input id="q" type="search" placeholder="Tìm tên, SĐT, email, fanpage…">
  <select id="fk"><option value="">Tất cả trang</option></select>
  <button class="btn" id="bRef">↻ Tải lại</button>
  <span class="meta" id="upd"></span>
 </div>
 <div class="list" id="list"></div>
</main>
<dialog id="dSet"><form method="dialog" id="fSet">
 <h3>Cài đặt</h3>
 <h4 style="margin:.6rem 0 0">🔔 Báo khách mới qua Telegram</h4>
 <div class="hint"><ol>
  <li>Mở Telegram, tìm <b>@BotFather</b>, gửi <code>/newbot</code>, đặt tên → nhận <b>token</b>.</li>
  <li>Dán token vào ô dưới, bấm <b>Lưu</b>.</li>
  <li>Mở bot vừa tạo, bấm <b>Start</b> (hoặc gửi tin bất kỳ).</li>
  <li>Bấm <b>Gửi tin thử</b> — nhận được tin là xong.</li></ol></div>
 <label for="tgTok">Telegram bot token</label><input id="tgTok" placeholder="123456789:AA…" autocomplete="off">
 <div class="meta" id="tgInfo"></div>
 <div class="acts"><button class="btn pri" type="button" id="bTgSave">Lưu</button><button class="btn" type="button" id="bTgTest">Gửi tin thử</button></div>
 <h4 style="margin:1.4rem 0 0">🔑 Đổi mật khẩu</h4>
 <label for="pOld">Mật khẩu hiện tại</label><input id="pOld" type="password" autocomplete="current-password">
 <label for="pNew">Mật khẩu mới (ít nhất 8 ký tự)</label><input id="pNew" type="password" autocomplete="new-password">
 <div class="acts"><button class="btn pri" type="button" id="bPw">Đổi mật khẩu</button></div>
 <p class="meta" id="setMsg" style="min-height:1.2em"></p>
 <div class="acts" style="justify-content:flex-end"><button class="btn">Đóng</button></div>
</form></dialog>
<script>
const $=s=>document.querySelector(s),H={'Content-Type':'application/json','X-ETLA':'1'};
let LEADS=[],STATUSES=[],FILTER='';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=t=>new Date(t*1000).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit',year:'numeric'});
const telDigits=p=>(p||'').replace(/[^\d+]/g,'');
async function api(u,o){const r=await fetch(u,o);if(r.status===401){location.reload();throw 0}return r.json()}
async function load(){
 const j=await api('/api/leads');LEADS=j.leads;STATUSES=j.statuses;
 const kinds=[...new Set(LEADS.map(l=>l.kind).filter(Boolean))];const fk=$('#fk'),cur=fk.value;
 fk.innerHTML='<option value="">Tất cả trang</option>'+kinds.map(k=>`<option ${k===cur?'selected':''}>${esc(k)}</option>`).join('');
 $('#upd').textContent='Cập nhật '+new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'});
 const nNew=LEADS.filter(l=>l.status==='Mới').length;document.title=(nNew?`(${nNew}) `:'')+'Quản trị — Em Tâm Làm Ads';
 render()}
function render(){
 const counts={};STATUSES.forEach(s=>counts[s]=0);LEADS.forEach(l=>counts[l.status]=(counts[l.status]||0)+1);
 $('#stats').innerHTML=[['',LEADS.length,'Tất cả']].concat(STATUSES.slice(0,4).map(s=>[s,counts[s],s])).map(([k,n,l])=>`<div class="stat ${FILTER===k?'on':''}" data-f="${esc(k)}"><b>${n}</b><span>${esc(l)}</span></div>`).join('');
 document.querySelectorAll('.stat').forEach(el=>el.onclick=()=>{FILTER=el.dataset.f;render()});
 const q=$('#q').value.trim().toLowerCase(),fk=$('#fk').value;
 const rows=LEADS.filter(l=>(!FILTER||l.status===FILTER)&&(!fk||l.kind===fk)&&(!q||[l.name,l.phone,l.email,l.fanpage,l.note,l.admin_note].join(' ').toLowerCase().includes(q)));
 $('#list').innerHTML=rows.length?rows.map(card).join(''):'<div class="empty">Chưa có khách nào ở mục này.</div>';
 rows.forEach(bind)}
function card(l){
 const kv=[['SĐT',l.phone],['Email',l.email],['Fanpage',l.fanpage],['Ngân sách ads',l.budget],['Mục tiêu',l.goal],['Khách ghi chú',l.note],['Trang',l.page],['Nguồn',l.utm]].filter(x=>x[1]);
 const when=[l.date,l.times].filter(Boolean).join(' · ');const t=telDigits(l.phone);
 const fp=l.fanpage?(/^https?:/.test(l.fanpage)?l.fanpage:'https://'+l.fanpage):'';
 return `<div class="lead ${l.status==='Mới'?'new':''}" id="l${l.id}"><div>
  <h3>${esc(l.name)}<span class="kind">${esc((l.kind||'').replace(/^Đăng ký |^Đặt lịch /,''))}</span></h3>
  <div class="meta">#${l.id} · gửi lúc ${fmt(l.created_at)}</div>
  ${when?`<div class="when">🗓 Hẹn: ${esc(when)} (giờ VN)</div>`:''}
  <dl class="kv">${kv.map(([k,v])=>`<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
  <div class="acts">${t?`<a class="btn pri" href="tel:${esc(t)}">📞 Gọi</a><a class="btn" target="_blank" rel="noopener" href="https://zalo.me/${esc(t.replace(/^\+?84/,'0'))}">Zalo</a>`:''}
   ${l.email?`<a class="btn" href="mailto:${esc(l.email)}">✉ Email</a>`:''}${fp?`<a class="btn" target="_blank" rel="noopener noreferrer" href="${esc(fp)}">Fanpage ↗</a>`:''}</div>
 </div><div class="side">
  <label class="meta" for="s${l.id}">Trạng thái</label>
  <select id="s${l.id}">${STATUSES.map(s=>`<option ${s===l.status?'selected':''}>${esc(s)}</option>`).join('')}</select>
  <label class="meta" for="n${l.id}">Ghi chú của bạn</label>
  <textarea id="n${l.id}" placeholder="VD: đã gọi, hẹn 20h thứ 5…">${esc(l.admin_note)}</textarea>
  <div class="saved" id="ok${l.id}"></div>
  <button class="btn" style="justify-self:start;font-size:.78rem;opacity:.75" id="d${l.id}">Xoá</button>
 </div></div>`}
function bind(l){
 const save=async(body)=>{await api('/api/leads/'+l.id,{method:'POST',headers:H,body:JSON.stringify(body)});Object.assign(l,body);$('#ok'+l.id).textContent='Đã lưu ✓';setTimeout(()=>{const e=$('#ok'+l.id);if(e)e.textContent=''},1500)};
 $('#s'+l.id).onchange=async e=>{await save({status:e.target.value});render()};
 let t;$('#n'+l.id).oninput=e=>{clearTimeout(t);t=setTimeout(()=>save({admin_note:e.target.value}),700)};
 $('#d'+l.id).onclick=async()=>{if(!confirm('Xoá khách '+l.name+'?'))return;await api('/api/leads/'+l.id+'/delete',{method:'POST',headers:H,body:'{}'});LEADS=LEADS.filter(x=>x.id!==l.id);render()}}
$('#q').oninput=render;$('#fk').onchange=render;$('#bRef').onclick=load;
$('#bOut').onclick=async()=>{await fetch('/logout',{method:'POST'});location.reload()};
const msg=t=>$('#setMsg').textContent=t;
$('#bSet').onclick=async()=>{const s=await api('/api/settings');$('#tgInfo').textContent=s.tg_token_set?`Đã lưu token ${s.tg_token_hint}${s.tg_chat?' · đã kết nối':' · chưa bấm Start bot'}`:'Chưa cài Telegram';msg('');$('#dSet').showModal()};
$('#bTgSave').onclick=async()=>{const j=await api('/api/settings/telegram',{method:'POST',headers:H,body:JSON.stringify({token:$('#tgTok').value.trim()})});msg(j.ok?'Đã lưu. Mở bot trên Telegram, bấm Start rồi bấm "Gửi tin thử".':j.error)};
$('#bTgTest').onclick=async()=>{msg('Đang gửi…');const j=await api('/api/settings/telegram/test',{method:'POST',headers:H,body:'{}'});msg(j.ok?'✓ Đã gửi — kiểm tra Telegram.':'✗ '+j.error)};
$('#bPw').onclick=async()=>{const j=await api('/api/settings/password',{method:'POST',headers:H,body:JSON.stringify({old:$('#pOld').value,new:$('#pNew').value})});msg(j.ok?'✓ Đã đổi mật khẩu.':'✗ '+j.error)};
load();setInterval(load,60000);
</script></body></html>"""


def main():
    init_db()
    if "--init" in sys.argv:
        secret_key()
        if not get_setting("pw"):
            print("MAT KHAU QUAN TRI:", new_password())
        else:
            print("Da co mat khau quan tri (dung --reset-password de dat lai).")
        return
    if "--reset-password" in sys.argv:
        print("MAT KHAU QUAN TRI MOI:", new_password())
        return
    secret_key()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Em Tam Lam Ads admin dang chay tai http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
