import os, json, uuid, shutil, subprocess, threading, time
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from cryptography.fernet import Fernet

BASE = Path(__file__).resolve().parent
BOTS = BASE / "bots"
DATA = BASE / "data"
BOTS.mkdir(exist_ok=True); DATA.mkdir(exist_ok=True)
DB_FILE = DATA / "bots.json"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "2")) * 1024 * 1024
ALLOWED = {".py", ".txt"}
processes = {}
locks = {}

# Token encryption. Generate FERNET_KEY with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY = os.environ.get("FERNET_KEY")
if FERNET_KEY:
    fernet = Fernet(FERNET_KEY.encode())
else:
    fernet = None

def load_db():
    if not DB_FILE.exists():
        return {}
    try: return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def save_db(db):
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB_FILE)

def enc(value):
    if not fernet: return value
    return fernet.encrypt(value.encode()).decode()

def dec(value):
    if not fernet: return value
    return fernet.decrypt(value.encode()).decode()

def auth_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return jsonify(error="غير مصرح") if request.path.startswith("/api/") else redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper

def bot_path(bot_id):
    return BOTS / bot_id

def is_running(bot_id):
    p = processes.get(bot_id)
    return bool(p and p.poll() is None)

def start_bot(bot_id):
    db = load_db()
    bot = db.get(bot_id)
    if not bot: return False, "البوت غير موجود"
    if is_running(bot_id): return True, "يعمل بالفعل"
    folder = bot_path(bot_id)
    code = folder / "bot.py"
    if not code.exists(): return False, "ملف البوت غير موجود"
    env = os.environ.copy()
    env["BOT_TOKEN"] = dec(bot["token"])
    env["PYTHONUNBUFFERED"] = "1"
    log = open(folder / "output.log", "a", encoding="utf-8", buffering=1)
    try:
        p = subprocess.Popen(
            ["python", "bot.py"],
            cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        processes[bot_id] = p
        bot["status"] = "running"; save_db(db)
        return True, "تم التشغيل"
    except Exception as e:
        log.close()
        return False, str(e)

def stop_bot(bot_id):
    p = processes.get(bot_id)
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill()
    processes.pop(bot_id, None)
    db = load_db()
    if bot_id in db:
        db[bot_id]["status"] = "stopped"; save_db(db)

@app.route("/")
def home():
    if not session.get("admin"): return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("home"))
        return render_template("login.html", error="كلمة المرور غير صحيحة")
    return render_template("login.html", error=None)

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/api/bots")
@auth_required
def api_bots():
    db = load_db()
    out = []
    for bid, b in db.items():
        running = is_running(bid)
        out.append({"id": bid, "name": b["name"], "filename": b["filename"],
                    "running": running, "created": b["created"]})
    return jsonify(out)

@app.post("/api/bots")
@auth_required
def api_upload():
    f = request.files.get("file")
    token = request.form.get("token", "").strip()
    if not f: return jsonify(error="اختر ملفًا"), 400
    if not token: return jsonify(error="أدخل Bot Token"), 400
    ext = Path(f.filename or "").suffix.lower()
    if ext not in ALLOWED: return jsonify(error="المسموح فقط .py و .txt"), 400
    data = f.read()
    if len(data) > MAX_BYTES: return jsonify(error=f"الحد الأقصى {MAX_BYTES//1024//1024}MB"), 400
    # Basic token shape validation; Telegram remains the authority.
    if ":" not in token or len(token) < 20:
        return jsonify(error="صيغة Bot Token تبدو غير صحيحة"), 400
    bid = uuid.uuid4().hex
    folder = bot_path(bid); folder.mkdir()
    (folder/"bot.py").write_bytes(data)
    (folder/"output.log").write_text("", encoding="utf-8")
    db = load_db()
    db[bid] = {"name": Path(f.filename).stem[:80], "filename": f.filename,
               "token": enc(token), "created": int(time.time()), "status":"stopped"}
    save_db(db)
    ok, msg = start_bot(bid)
    if not ok:
        return jsonify(error=msg, id=bid), 500
    return jsonify(ok=True, id=bid)

@app.post("/api/bots/<bid>/start")
@auth_required
def api_start(bid):
    ok,msg=start_bot(bid)
    return jsonify(ok=ok,message=msg), (200 if ok else 404)

@app.post("/api/bots/<bid>/stop")
@auth_required
def api_stop(bid):
    if bid not in load_db(): return jsonify(error="غير موجود"),404
    stop_bot(bid); return jsonify(ok=True)

@app.post("/api/bots/<bid>/restart")
@auth_required
def api_restart(bid):
    if bid not in load_db(): return jsonify(error="غير موجود"),404
    stop_bot(bid); time.sleep(.3)
    ok,msg=start_bot(bid); return jsonify(ok=ok,message=msg),(200 if ok else 500)

@app.get("/api/bots/<bid>/logs")
@auth_required
def api_logs(bid):
    p=bot_path(bid)/"output.log"
    if not p.exists(): return jsonify(log="")
    text=p.read_text(encoding="utf-8",errors="replace")
    return jsonify(log=text[-20000:])

@app.delete("/api/bots/<bid>")
@auth_required
def api_delete(bid):
    if bid not in load_db(): return jsonify(error="غير موجود"),404
    stop_bot(bid)
    db=load_db(); db.pop(bid); save_db(db)
    shutil.rmtree(bot_path(bid), ignore_errors=True)
    return jsonify(ok=True)

# Re-launch bots after a process exits. This is a simple supervisor for a single-user deployment.
def supervisor():
    while True:
        time.sleep(5)
        db=load_db()
        for bid in list(db):
            if db[bid].get("status")=="running" and not is_running(bid):
                start_bot(bid)

threading.Thread(target=supervisor, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","10000")))
