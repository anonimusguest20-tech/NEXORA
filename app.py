from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os, requests, phonenumbers, hashlib, subprocess
from phonenumbers import carrier, geocoder, timezone as pn_timezone
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'nexora-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexora.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
ADMIN_EMAILS = ['admin@nexora.local', 'amico@nexora.local']
PLANS = {
    'free':     {'name':'Free',     'price':0,   'daily_limit':5,      'modules':['users','email','phone']},
    'pro':      {'name':'Pro',      'price':20,  'daily_limit':10,     'modules':['users','email','phone','domains','social']},
    'elite':    {'name':'Elite',    'price':50,  'daily_limit':50,     'modules':['users','email','phone','domains','social','ip','breaches','images']},
    'ultimate': {'name':'Ultimate', 'price':100, 'daily_limit':999999, 'modules':['users','email','phone','domains','social','ip','breaches','images']},
}
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    plan = db.Column(db.String(20), default='free')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class LookupLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    type = db.Column(db.String(20))
    query = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
@login_manager.user_loader
def load_user(uid): return db.session.get(User, int(uid))
def check_lookup(user, ltype):
    if user.is_admin: return True, None
    plan = PLANS.get(user.plan, PLANS['free'])
    if ltype not in plan['modules']: return False, f"Modulo '{ltype}' non incluso."
    since = datetime.utcnow() - timedelta(days=1)
    count = db.session.query(LookupLog).filter(LookupLog.user_id == user.id, LookupLog.created_at >= since).count()
    if count >= plan['daily_limit']: return False, f"Limite ({plan['daily_limit']}) raggiunto."
    return True, None
def log_lookup(user, ltype, query):
    db.session.add(LookupLog(user_id=user.id, type=ltype, query=query)); db.session.commit()
def lookup_phone(number):
    try:
        p = phonenumbers.parse(number, None)
        if not phonenumbers.is_valid_number(p):
            return {"error": "Numero non valido"}
        result = {
            "number": number,
            "operator": carrier.name_for_number(p, "it") or "Sconosciuto",
            "region": geocoder.description_for_number(p, "it") or "Sconosciuta",
            "country": phonenumbers.region_code_for_number(p),
            "type": "Mobile" if phonenumbers.number_type(p) == phonenumbers.PhoneNumberType.MOBILE else "Fisso",
            "timezone": pn_timezone.time_zones_for_number(p),
            "international": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            "national": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.NATIONAL),
            "e164": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164),
            "sites_registered": []
        }
        try:
            import trio, httpx
            from ignorant.modules.shopping.amazon import amazon
            from ignorant.modules.social.instagram import instagram
            from ignorant.modules.social.snapchat import snapchat
            cc = str(p.country_code); nn = str(p.national_number)
            async def check():
                client = httpx.AsyncClient(timeout=10)
                out = []
                await amazon(nn, cc, client, out)
                await instagram(nn, cc, client, out)
                await snapchat(nn, cc, client, out)
                await client.aclose()
                return out
            results = trio.run(check)
            for r in results:
                result["sites_registered"].append({
                    "site": r.get("name", "Unknown"),
                    "registered": bool(r.get("exists"))
                })
        except Exception as e:
            result["ignorant_error"] = str(e)
        return result
    except Exception as e:
        return {"error": str(e)}

def lookup_email(email):
    result = {"email":email,"sources":[]}
    domain = email.split("@")[-1]
    try:
        r = requests.get(f"https://emailrep.io/{email}", headers={"User-Agent":"NEXORA"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            result["reputation"] = d.get("reputation")
            result["suspicious"] = d.get("suspicious")
            result["domain"] = d.get("domain")
            result["profiles"] = d.get("profiles", [])
            result["sources"].append("emailrep")
    except: pass
    try:
        dns = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=10).json()
        result["mx_records"] = len(dns.get("Answer", []))
    except: pass
    try:
        res = subprocess.run(["holehe", email, "--only-used", "--no-color"], capture_output=True, text=True, timeout=120)
        sites = []
        for line in res.stdout.splitlines():
            if "[+]" in line:
                s = line.split("[+]")[1].strip()
                if s: sites.append(s)
        result["sites_registered"] = sites
        result["sources"].append("holehe")
    except Exception as e: result["holehe_error"] = str(e)
    try:
        h = hashlib.md5(email.lower().encode()).hexdigest()
        gr = requests.get(f"https://gravatar.com/{h}.json", timeout=10)
        if gr.status_code == 200:
            entry = gr.json().get("entry",[{}])[0]
            result["gravatar"] = {"username":entry.get("preferredUsername"),"displayName":entry.get("displayName"),
                                  "profileUrl":entry.get("profileUrl"),"avatar":entry.get("thumbnailUrl"),
                                  "accounts":entry.get("accounts",[])}
            result["sources"].append("gravatar")
    except: pass
    try:
        gh = requests.get(f"https://api.github.com/search/users?q={email}+in:email",
                          headers={"Accept":"application/vnd.github+json"}, timeout=10)
        if gh.status_code == 200:
            data = gh.json()
            if data.get("total_count",0) > 0:
                result["github"] = [{"login":u["login"],"url":u["html_url"]} for u in data.get("items",[])[:5]]
                result["sources"].append("github")
    except: pass
    try:
        hb = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=true",
                          headers={"User-Agent":"NEXORA"}, timeout=10)
        if hb.status_code == 200:
            result["breaches"] = [b["Name"] for b in hb.json()]
            result["sources"].append("hibp")
        elif hb.status_code == 404: result["breaches"] = []
    except: pass
    return result
def lookup_ip(ip):
    try: return requests.get(f"http://ip-api.com/json/{ip}", timeout=10).json()
    except Exception as e: return {"error":str(e)}
def lookup_username(username):
    sites = {"GitHub":f"https://github.com/{username}","Twitter":f"https://twitter.com/{username}",
             "Instagram":f"https://instagram.com/{username}","Reddit":f"https://reddit.com/user/{username}",
             "TikTok":f"https://tiktok.com/@{username}","YouTube":f"https://youtube.com/@{username}",
             "Twitch":f"https://twitch.tv/{username}","Steam":f"https://steamcommunity.com/id/{username}",
             "Pinterest":f"https://pinterest.com/{username}","Telegram":f"https://t.me/{username}"}
    found = []
    for site, url in sites.items():
        try:
            r = requests.get(url, timeout=5, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200: found.append({"site":site,"url":url})
        except: pass
    return {"username":username,"found":found}
def lookup_domain(d):
    try: return requests.get(f"https://dns.google/resolve?name={d}&type=A", timeout=10).json()
    except Exception as e: return {"error":str(e)}
def lookup_breaches(email):
    try:
        r = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=true",
                         headers={"User-Agent":"NEXORA"}, timeout=10)
        if r.status_code == 200: return {"email":email,"breaches":[b["Name"] for b in r.json()]}
        elif r.status_code == 404: return {"email":email,"breaches":[]}
        return {"error":f"API {r.status_code}"}
    except Exception as e: return {"error":str(e)}
LOOKUP_MAP = {'phone':lookup_phone,'email':lookup_email,'ip':lookup_ip,'username':lookup_username,
              'users':lookup_username,'domains':lookup_domain,'social':lookup_username,
              'breaches':lookup_breaches,'images':lookup_username}
@app.route('/')
def index(): return render_template('index.html')
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pwd = request.form['password']
        if db.session.query(User).filter_by(email=email).first():
            flash('Email già registrata.'); return redirect(url_for('register'))
        is_admin = email in ADMIN_EMAILS
        u = User(email=email, password=pwd, is_admin=is_admin, plan='ultimate' if is_admin else 'free')
        db.session.add(u); db.session.commit(); login_user(u)
        return redirect(url_for('dashboard'))
    return render_template('register.html')
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pwd = request.form['password']
        u = db.session.query(User).filter_by(email=email, password=pwd).first()
        if u:
            login_user(u); return redirect(url_for('dashboard'))
        flash('Credenziali errate.')
    return render_template('login.html')
@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('index'))
@app.route('/dashboard')
@login_required
def dashboard():
    plan = PLANS.get(current_user.plan, PLANS['free'])
    since = datetime.utcnow() - timedelta(days=1)
    used = db.session.query(LookupLog).filter(LookupLog.user_id==current_user.id, LookupLog.created_at>=since).count()
    remaining = "∞" if current_user.is_admin else max(0, plan['daily_limit']-used)
    return render_template('dashboard.html', user=current_user, plan=plan, remaining=remaining, plans=PLANS)
@app.route('/api/lookup', methods=['POST'])
@login_required
def api_lookup():
    data = request.get_json()
    ltype = data.get('type'); query = data.get('query','').strip()
    if not query: return jsonify({"error":"Query vuota"}), 400
    ok, msg = check_lookup(current_user, ltype)
    if not ok: return jsonify({"error":msg,"upgrade":True}), 403
    fn = LOOKUP_MAP.get(ltype)
    if not fn: return jsonify({"error":"Tipo non valido"}), 400
    result = fn(query); log_lookup(current_user, ltype, query)
    return jsonify(result)
@app.route('/pricing')
def pricing(): return render_template('pricing.html', plans=PLANS)
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    users = db.session.query(User).all()
    logs = db.session.query(LookupLog).order_by(LookupLog.created_at.desc()).limit(100).all()
    return render_template('admin.html', users=users, logs=logs)
os.makedirs('instance', exist_ok=True)
with app.app_context(): db.create_all()
if __name__ == '__main__': app.run(debug=True, host='0.0.0.0', port=5000)


os.makedirs('instance', exist_ok=True)
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
