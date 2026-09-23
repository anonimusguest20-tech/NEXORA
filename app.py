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
db_path = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'instance', 'nexora.db'))
os.makedirs(os.path.dirname(db_path), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
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
class PlanConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(50))
    price = db.Column(db.Integer, default=0)
    daily_limit = db.Column(db.Integer, default=5)
    modules = db.Column(db.String(500), default="users,email,phone")
    popular = db.Column(db.Boolean, default=False)

class SiteContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True)
    value = db.Column(db.Text, default="")

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
    since = datetime.utcnow() - timedelta(hours=30)
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
            "carrier": carrier.name_for_number(p, "en") or "Unknown",
            "sources": []
        }

        # Veriphone
        vk = os.getenv("VERIPHONE_KEY", "")
        if vk:
            try:
                r = requests.get(f"https://api.veriphone.io/v2/verify",
                                 params={"phone": number, "key": vk}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("status") == "success":
                        result["carrier"] = d.get("carrier") or result.get("carrier")
                        result["type"] = d.get("phone_type") or result.get("type")
                        result["region"] = d.get("phone_region") or result.get("region")
                        result["country_name"] = d.get("country")
                        result["country_code"] = d.get("country_code")
                        result["international"] = d.get("international_number") or result.get("international")
                        result["local"] = d.get("local_number")
                        result["e164"] = d.get("e164") or result.get("e164")
                        result["sources"].append("veriphone")
            except Exception as e:
                result["veriphone_error"] = str(e)

        # Abstract API
        ak = os.getenv("ABSTRACT_KEY", "")
        if ak:
            try:
                r = requests.get("https://phonevalidation.abstractapi.com/v1/",
                                 params={"api_key": ak, "phone": number}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if not d.get("error"):
                        result["abstract_valid"] = d.get("valid")
                        result["abstract_format_int"] = d.get("format", {}).get("international")
                        result["abstract_format_local"] = d.get("format", {}).get("local")
                        result["abstract_country"] = d.get("country", {}).get("name")
                        result["abstract_country_code"] = d.get("country", {}).get("code")
                        result["abstract_location"] = d.get("location")
                        result["abstract_type"] = d.get("type")
                        result["abstract_carrier"] = d.get("carrier")
                        if d.get("location"): result["region"] = d.get("location")
                        if d.get("carrier"): result["operator"] = d.get("carrier")
                        result["sources"].append("abstract")
            except Exception as e:
                result["abstract_error"] = str(e)

        # Numverify
        nk = os.getenv("NUMVERIFY_KEY", "")
        if nk:
            try:
                r = requests.get("http://apilayer.net/api/validate",
                                 params={"access_key": nk, "number": number}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("valid"):
                        result["numverify_valid"] = d.get("valid")
                        result["numverify_number"] = d.get("number")
                        result["numverify_local"] = d.get("local_format")
                        result["numverify_international"] = d.get("international_format")
                        result["numverify_country_prefix"] = d.get("country_prefix")
                        result["numverify_country_code"] = d.get("country_code")
                        result["numverify_country_name"] = d.get("country_name")
                        result["numverify_location"] = d.get("location")
                        result["numverify_carrier"] = d.get("carrier")
                        result["numverify_line_type"] = d.get("line_type")
                        if d.get("carrier") and result.get("operator") == "Sconosciuto":
                            result["operator"] = d.get("carrier")
                        if d.get("location") and result.get("region") == "Sconosciuta":
                            result["region"] = d.get("location")
                        if d.get("line_type"): result["type"] = d.get("line_type").capitalize()
                        result["sources"].append("numverify")
            except Exception as e:
                result["numverify_error"] = str(e)

        result["sites_registered"] = []

        # Ignorant (funziona in locale, non su Railway Python 3.13)
        try:
            import trio, httpx
            from ignorant.modules.shopping.amazon import amazon
            from ignorant.modules.social.instagram import instagram
            from ignorant.modules.social.snapchat import snapchat

            cc = str(p.country_code)
            nn = str(p.national_number)

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
                    "registered": bool(r.get("exists")),
                    "domain": r.get("domain", "")
                })
        except ImportError:
            result["ignorant_note"] = "ignorant non installato"
        except Exception as e:
            result["ignorant_error"] = str(e)

        return result
    except Exception as e:
        return {"error": str(e)}

def lookup_email(email):
    result = {"email": email, "sources": [], "sites_registered": []}
    domain = email.split("@")[-1]

    # MX records
    try:
        dns = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=10).json()
        result["mx_records"] = len(dns.get("Answer", []))
    except: pass

    # EmailRep
    try:
        r = requests.get(f"https://emailrep.io/{email}",
                         headers={"User-Agent":"NEXORA"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            result["reputation"] = d.get("reputation")
            result["suspicious"] = d.get("suspicious")
            result["domain"] = d.get("domain")
            result["profiles"] = d.get("profiles", [])
            result["sources"].append("emailrep")
        elif r.status_code == 429:
            result["emailrep_note"] = "rate limit"
    except: pass

    # Gravatar
    try:
        h = hashlib.md5(email.lower().encode()).hexdigest()
        gr = requests.get(f"https://gravatar.com/{h}.json", timeout=10)
        if gr.status_code == 200:
            entry = gr.json().get("entry",[{}])[0]
            result["gravatar"] = {
                "username": entry.get("preferredUsername"),
                "displayName": entry.get("displayName"),
                "profileUrl": entry.get("profileUrl"),
                "accounts": entry.get("accounts",[])
            }
            result["sources"].append("gravatar")
    except: pass

    # GitHub
    try:
        gh = requests.get(f"https://api.github.com/search/users?q={email}+in:email",
                          headers={"Accept":"application/vnd.github+json"}, timeout=10)
        if gh.status_code == 200:
            d = gh.json()
            if d.get("total_count",0) > 0:
                result["github"] = [{"login":u["login"],"url":u["html_url"]} for u in d.get("items",[])[:5]]
                result["sources"].append("github")
    except: pass

    # Firefox Monitor (breach check gratuito)
    try:
        fm = requests.get(f"https://monitor.firefox.com/api/v1/breaches", timeout=10).json()
        # Firefox non ha API pubblica per email specifica, skip
    except: pass

    # holehe (funziona solo in locale, su Railway è disabilitato)
    try:
        res = subprocess.run(["holehe", email, "--only-used", "--no-color"],
                             capture_output=True, text=True, timeout=60)
        for line in res.stdout.splitlines():
            if "[+]" in line:
                s = line.split("[+]")[1].strip()
                if s: result["sites_registered"].append(s)
        result["sources"].append("holehe")
    except FileNotFoundError:
        pass
    except Exception as e:
        result["holehe_error"] = str(e)

    # Fallback: se holehe non c'è, verifica manuale su piattaforme comuni
    if not result["sites_registered"]:
        common_sites = ["firefox.com","office365.com","spotify.com","adobe.com","amazon.com","pinterest.com","twitter.com","instagram.com","reddit.com","discord.com","github.com","tumblr.com","snapchat.com","linkedin.com","yahoo.com","dropbox.com"]
        result["sites_registered"] = common_sites
        result["sites_note"] = "Verifica manuale — clicca per controllare"

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
    return {
        "email": email,
        "breaches": [],
        "note": "Servizio breach disabilitato. HIBP, LeakCheck e Firefox Monitor ora richiedono API key a pagamento. Visita https://haveibeenpwned.com manualmente.",
        "manual_link": f"https://haveibeenpwned.com/account/{email}"
    }


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
    plan_db = db.session.query(PlanConfig).filter_by(key=current_user.plan).first()
    if plan_db:
        plan = {"name":plan_db.name,"price":plan_db.price,"daily_limit":plan_db.daily_limit,
                "modules":plan_db.modules.split(","),"popular":plan_db.popular}
    else:
        plan = PLANS.get(current_user.plan, PLANS['free'])
    since = datetime.utcnow() - timedelta(hours=30)
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
@app.route('/api/search-multi', methods=['POST'])
@login_required
def api_search_multi():
    data = request.get_json()
    query = data.get('query','').strip()
    mode = data.get('mode','auto')
    if not query:
        return jsonify({"error":"Query vuota"}), 400

    # Auto-detect del tipo di query
    detected = None
    if '@' in query and '.' in query.split('@')[-1]:
        detected = 'email'
    elif query.replace('+','').replace(' ','').isdigit() and len(query.replace('+','').replace(' ','')) > 6:
        detected = 'phone'
    elif query.count('.') == 3 and all(p.isdigit() for p in query.split('.')):
        detected = 'ip'
    elif '.' in query and ' ' not in query:
        detected = 'domains'
    else:
        detected = 'users'

    if mode == 'fast':
        modules = [detected]
    elif mode == 'auto':
        modules = [detected]
    elif mode == 'deep':
        modules = ['users','email','phone','domains','ip','breaches']
    elif mode == 'compare':
        modules = ['users','email','phone']
    else:
        modules = [detected]

    results = {}
    for m in modules:
        # Check limiti
        ok, msg = check_lookup(current_user, m)
        if not ok:
            results[m] = {"error": msg, "skipped": True}
            continue
        fn = LOOKUP_MAP.get(m)
        if not fn:
            continue
        try:
            res = fn(query)
            results[m] = res
            log_lookup(current_user, m, query)
        except Exception as e:
            results[m] = {"error": str(e)}

    return jsonify({
        "query": query,
        "detected": detected,
        "mode": mode,
        "modules_used": modules,
        "results": results
    })

@app.route('/pricing')
def pricing():
    plans_db = db.session.query(PlanConfig).all()
    if plans_db:
        plans = {}
        for p in plans_db:
            plans[p.key] = {"name":p.name,"price":p.price,"daily_limit":p.daily_limit,
                            "modules":p.modules.split(","),"popular":p.popular}
    else:
        plans = PLANS
    return render_template('pricing.html', plans=plans)
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
DEFAULT_CONTENT = {
    'hero_title': 'NEXORA',
    'hero_tag': 'INTELLIGENCE FOR A MORE TRANSPARENT WEB',
    'hero_desc': 'Open source intelligence tools to search, analyze and connect information from across the web.',
    'home_quote': 'Information reveals patterns.',
    'stat1_num': '300+', 'stat1_label': 'Data Sources',
    'stat2_num': '50+', 'stat2_label': 'OSINT Tools',
    'stat3_num': 'Global', 'stat3_label': 'Faster Research',
    'stat4_text': 'Same information. A more transparent world.',
}

with app.app_context():
    db.create_all()
    for k, v in PLANS.items():
        if not db.session.query(PlanConfig).filter_by(key=k).first():
            db.session.add(PlanConfig(
                key=k, name=v["name"], price=v["price"],
                daily_limit=v["daily_limit"],
                modules=",".join(v["modules"]),
                popular=(k == "elite")
            ))
    db.session.commit()
    for k, v in DEFAULT_CONTENT.items():
        if not db.session.query(SiteContent).filter_by(key=k).first():
            db.session.add(SiteContent(key=k, value=v))
    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
