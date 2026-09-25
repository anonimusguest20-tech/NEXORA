from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os, requests, smtplib, phonenumbers, hashlib, subprocess, random, string
from phonenumbers import carrier, geocoder, timezone as pn_timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv

import random, string
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
login_manager.remember_cookie_duration = timedelta(days=30)
login_manager.session_protection = 'basic'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_SECURE'] = False
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
ADMIN_EMAILS = ['admin@nexora.local', 'anonimus.guest20@gmail.com', 'amico@nexora.local']

PLAN_EMAILS = {
    'plaiko@nexora.local': 'starter',
    'gwt@nexora.local': 'elite',
    'chicoria@nexora.local': 'ultimate',
}
PLANS = {
    'starter':  {'name':'Starter',  'price':10,  'daily_limit':10,     'modules':['users','email','phone']},
    'basic':    {'name':'Basic',    'price':25,  'daily_limit':25,     'modules':['users','email','phone','domains','social']},
    'free':     {'name':'Free',     'price':0,   'daily_limit':5,      'modules':['users','email','phone']},
    'pro':      {'name':'Pro',      'price':20,  'daily_limit':10,     'modules':['users','email','phone','domains','social','discord']},
    'elite':    {'name':'Elite',    'price':50,  'daily_limit':50,     'modules':['users','email','phone','domains','social','ip','breaches','images','discord']},
    'ultimate': {'name':'Ultimate', 'price':100, 'daily_limit':999999, 'modules':['users','email','phone','domains','social','ip','breaches','images','discord']},
}
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(40), unique=True)
    verified = db.Column(db.Boolean, default=True)
    nexora_id = db.Column(db.String(20), unique=True)
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

class VerifyCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), nullable=False)
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
    since = datetime.utcnow() - timedelta(hours=30)
    count = db.session.query(LookupLog).filter(LookupLog.user_id == user.id, LookupLog.created_at >= since).count()
    if count >= plan['daily_limit']: return False, f"Limite ({plan['daily_limit']}) raggiunto."
    return True, None
def log_lookup(user, ltype, query):
    db.session.add(LookupLog(user_id=user.id, type=ltype, query=query)); db.session.commit()
def lookup_phone_advanced(number):
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder
        p = phonenumbers.parse(number, None)
        if not phonenumbers.is_valid_number(p):
            return {"error": "Numero non valido"}
        result = {
            "number": number,
            "operator": carrier.name_for_number(p, "it") or None,
            "region": geocoder.description_for_number(p, "it") or None,
            "country": phonenumbers.region_code_for_number(p),
        }
        region_name = result.get("region") or "Italy"
        try:
            import requests
            geo_api_url = "https://nominatim.openstreetmap.org/search?q=" + region_name + ",Italy&format=json&limit=1"
            geo_response = requests.get(geo_api_url, headers={"User-Agent": "NEXORA-OSINT-Tool"}, timeout=10).json()
            if geo_response:
                lat = geo_response[0]['lat']
                lon = geo_response[0]['lon']
                result["latitude"] = lat
                result["longitude"] = lon
                result["google_maps_link"] = "https://www.google.com/maps?q=" + lat + "," + lon
        except Exception as e:
            result["geo_error"] = str(e)
        return result
    except Exception as e:
        return {"error": str(e)}









def lookup_phone(number):
    try:
        p = phonenumbers.parse(number, None)
        if not phonenumbers.is_valid_number(p):
            return {"error": "Numero non valido"}
        result = {
            "number": number,
            "operator": carrier.name_for_number(p, "it") or None,
            "region": geocoder.description_for_number(p, "it") or None,
            "country": phonenumbers.region_code_for_number(p),
            "type": "Mobile" if phonenumbers.number_type(p) == phonenumbers.PhoneNumberType.MOBILE else "Fisso",
            "timezone": list(pn_timezone.time_zones_for_number(p)),
            "international": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            "national": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.NATIONAL),
            "e164": phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164),
            "country_name": None, "location": None, "line_type": None,
            "sources": [], "links": []
        }
        # Veriphone
        vk = os.getenv("VERIPHONE_KEY", "")
        if vk:
            try:
                r = requests.get("https://api.veriphone.io/v2/verify",
                                 params={"phone": number, "key": vk}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("status") == "success":
                        result["operator"] = d.get("carrier") or result["operator"]
                        result["country_name"] = d.get("country")
                        result["region"] = d.get("phone_region") or result["region"]
                        result["line_type"] = d.get("phone_type")
                        result["sources"].append("veriphone")
            except: pass
        # Abstract
        ak = os.getenv("ABSTRACT_KEY", "")
        if ak:
            try:
                r = requests.get("https://phonevalidation.abstractapi.com/v1/",
                                 params={"api_key": ak, "phone": number}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if not d.get("error"):
                        result["location"] = d.get("location")
                        result["country_name"] = d.get("country", {}).get("name") or result["country_name"]
                        if d.get("carrier"): result["operator"] = d["carrier"]
                        if d.get("type"): result["line_type"] = d["type"]
                        result["sources"].append("abstract")
            except: pass
        # Numverify
        nk = os.getenv("NUMVERIFY_KEY", "")
        if nk:
            try:
                r = requests.get("http://apilayer.net/api/validate",
                                 params={"access_key": nk, "number": number}, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("valid"):
                        result["country_name"] = d.get("country_name") or result["country_name"]
                        if d.get("carrier") and not result["operator"]:
                            result["operator"] = d["carrier"]
                        if d.get("location") and not result["location"]:
                            result["location"] = d["location"]
                        if d.get("line_type"): result["line_type"] = d["line_type"]
                        result["sources"].append("numverify")
            except: pass
        # Nominatim geocoding → Google Maps link
        try:
            region_query = result.get("location") or result.get("region") or result.get("country_name") or "Italy"
            geo = requests.get("https://nominatim.openstreetmap.org/search",
                               params={"q": region_query + ", Italy", "format": "json", "limit": 1},
                               headers={"User-Agent": "NEXORA-OSINT"}, timeout=10).json()
            if geo:
                lat = geo[0]["lat"]; lon = geo[0]["lon"]
                result["latitude"] = lat
                result["longitude"] = lon
                result["google_maps_link"] = "https://www.google.com/maps?q=" + lat + "," + lon
        except: pass
        # Link diretti per verifica manuale
        digits = number.replace("+", "").replace(" ", "").replace("-", "")
        result["links"] = [
            {"name": "Truecaller", "url": "https://www.truecaller.com/search/it/" + digits, "desc": "Trova nome proprietario"},
            {"name": "Sync.me", "url": "https://sync.me/search/?number=" + digits, "desc": "Nome da rubrica social"},
            {"name": "Numlookup", "url": "https://www.numlookup.com/?phone=" + digits, "desc": "Lookup internazionale"},
            {"name": "SpyDialer", "url": "https://www.spydialer.com/default.aspx?phone=" + digits, "desc": "Reverse phone USA"},
            {"name": "WhatsApp", "url": "https://wa.me/" + digits, "desc": "Verifica se ha WhatsApp"},
            {"name": "Telegram", "url": "https://t.me/+" + digits, "desc": "Verifica se ha Telegram"},
            {"name": "Facebook", "url": "https://www.facebook.com/login/identify", "desc": "Recupero account Facebook"},
            {"name": "Google", "url": "https://accounts.google.com/signin/recovery", "desc": "Recupero account Google"}
        ]
        return result
    except Exception as e:
        return {"error": str(e)}


def lookup_email(email):
    result = {"email": email, "breaches": [], "sites_registered": [], "sources": [], "profiles": []}
    domain = email.split("@")[-1]
    try:
        dns = requests.get("https://dns.google/resolve?name=" + domain + "&type=MX", timeout=10).json()
        result["mx_records"] = len(dns.get("Answer", []))
    except: pass
    try:
        r = requests.get("https://emailrep.io/" + email, headers={"User-Agent":"NEXORA"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            result["reputation"] = d.get("reputation")
            result["suspicious"] = d.get("suspicious")
            result["profiles"] = d.get("profiles", [])
            result["sources"].append("emailrep")
    except: pass
    # Holehe - account collegati
    try:
        res = subprocess.run(["holehe", email, "--only-used", "--no-color"],
                             capture_output=True, text=True, timeout=180)
        for line in res.stdout.splitlines():
            if "[+]" in line:
                s = line.split("[+]")[1].strip()
                if s and len(s) < 40:
                    result["sites_registered"].append(s)
        result["sources"].append("holehe")
    except Exception as e:
        result["holehe_error"] = str(e)
    # Gravatar
    try:
        h = hashlib.md5(email.lower().encode()).hexdigest()
        gr = requests.get("https://gravatar.com/" + h + ".json", timeout=10)
        if gr.status_code == 200:
            entry = gr.json().get("entry", [{}])[0]
            result["gravatar"] = {
                "username": entry.get("preferredUsername"),
                "displayName": entry.get("displayName"),
                "profileUrl": entry.get("profileUrl"),
                "accounts": entry.get("accounts", [])
            }
            result["sources"].append("gravatar")
    except: pass
    # GitHub
    try:
        gh = requests.get("https://api.github.com/search/users?q=" + email + "+in:email",
                          headers={"Accept":"application/vnd.github+json"}, timeout=10)
        if gh.status_code == 200:
            data = gh.json()
            if data.get("total_count", 0) > 0:
                result["github"] = [{"login":u["login"],"url":u["html_url"]} for u in data.get("items",[])[:10]]
                result["sources"].append("github")
    except: pass
    # Breach via XposedOrNot
    try:
        xon = requests.get("https://api.xposedornot.com/v1/check-email/" + email, timeout=15)
        if xon.status_code == 200:
            xd = xon.json()
            if xd.get("status") == "success":
                bl = xd.get("breaches", [])
                if bl and len(bl) > 0:
                    result["breaches"] = bl[0] if isinstance(bl[0], list) else bl
                    result["sources"].append("xposedornot")
    except: pass
    # Hudson Rock
    try:
        hr = requests.get("https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email",
                          params={"email": email}, timeout=15)
        if hr.status_code == 200:
            hd = hr.json()
            if hd.get("data"):
                result["hudsonrock"] = hd["data"]
                result["sources"].append("hudsonrock")
    except: pass
    return result


def lookup_ip(ip):
    try:
        r = requests.get("http://ip-api.com/json/" + ip + "?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query", timeout=10)
        if r.status_code != 200:
            return {"error": "API " + str(r.status_code)}
        d = r.json()
        if d.get("status") != "success":
            return {"error": d.get("message", "IP non valido")}
        result = {
            "ip": d.get("query"), "country": d.get("country"), "country_code": d.get("countryCode"),
            "region": d.get("regionName"), "city": d.get("city"), "zip": d.get("zip"),
            "latitude": d.get("lat"), "longitude": d.get("lon"), "timezone": d.get("timezone"),
            "isp": d.get("isp"), "org": d.get("org"), "asn": d.get("as"), "as_name": d.get("asname"),
            "reverse": d.get("reverse"), "mobile": d.get("mobile"), "proxy": d.get("proxy"),
            "hosting": d.get("hosting"), "sources": ["ip-api.com"]
        }
        if result["latitude"] and result["longitude"]:
            result["google_maps_link"] = "https://www.google.com/maps?q=" + str(result["latitude"]) + "," + str(result["longitude"])
        return result
    except Exception as e:
        return {"error": str(e)}


def lookup_username(username):
    sites = {
        "GitHub": "https://github.com/" + username,
        "Twitter": "https://twitter.com/" + username,
        "Instagram": "https://instagram.com/" + username,
        "Reddit": "https://reddit.com/user/" + username,
        "TikTok": "https://tiktok.com/@" + username,
        "YouTube": "https://youtube.com/@" + username,
        "Twitch": "https://twitch.tv/" + username,
        "Steam": "https://steamcommunity.com/id/" + username,
        "Pinterest": "https://pinterest.com/" + username,
        "Telegram": "https://t.me/" + username,
        "SoundCloud": "https://soundcloud.com/" + username,
        "Spotify": "https://open.spotify.com/user/" + username,
        "Medium": "https://medium.com/@" + username,
        "Dev.to": "https://dev.to/" + username,
        "Behance": "https://behance.net/" + username,
        "Dribbble": "https://dribbble.com/" + username,
        "Flickr": "https://flickr.com/people/" + username,
        "Vimeo": "https://vimeo.com/" + username,
        "GitLab": "https://gitlab.com/" + username,
        "BitBucket": "https://bitbucket.org/" + username,
        "Mastodon": "https://mastodon.social/@" + username,
        "Keybase": "https://keybase.io/" + username,
        "Facebook": "https://facebook.com/" + username,
        "LinkedIn": "https://linkedin.com/in/" + username
    }
    found = []
    for site, url in sites.items():
        try:
            r = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                found.append({"site": site, "url": url})
        except: pass
    return {"username": username, "found": found, "total_checked": len(sites)}


def lookup_domain(d):
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    result = {"domain": d, "sources": []}
    try:
        a = requests.get("https://dns.google/resolve?name=" + d + "&type=A", timeout=10).json()
        result["a_records"] = [x.get("data") for x in a.get("Answer", [])]
        mx = requests.get("https://dns.google/resolve?name=" + d + "&type=MX", timeout=10).json()
        result["mx_records"] = [x.get("data") for x in mx.get("Answer", [])]
        txt = requests.get("https://dns.google/resolve?name=" + d + "&type=TXT", timeout=10).json()
        result["txt_records"] = [x.get("data") for x in txt.get("Answer", [])][:5]
        ns = requests.get("https://dns.google/resolve?name=" + d + "&type=NS", timeout=10).json()
        result["ns_records"] = [x.get("data") for x in ns.get("Answer", [])]
        result["sources"].append("dns.google")
    except: pass
    try:
        r = requests.get("https://crt.sh/?q=%25." + d + "&output=json", timeout=15)
        if r.status_code == 200:
            subs = set()
            for entry in r.json()[:50]:
                nv = entry.get("name_value", "")
                for name in nv.split(chr(10)):
                    if name.endswith(d) and name != d:
                        subs.add(name)
            result["subdomains"] = list(subs)[:30]
            result["sources"].append("crt.sh")
    except: pass
    return result


def lookup_breaches(query):
    result = {"query": query, "breaches": [], "sources": []}
    try:
        r = requests.get("https://api.xposedornot.com/v1/check-email/" + query, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "success":
                raw = d.get("breaches", [])
                flat = []
                for item in raw:
                    if isinstance(item, list): flat.extend(item)
                    else: flat.append(item)
                result["breaches"] = flat
                result["sources"].append("xposedornot")
    except: pass
    try:
        hr = requests.get("https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email",
                          params={"email": query}, timeout=15)
        if hr.status_code == 200:
            hd = hr.json()
            if hd.get("data"):
                result["hudsonrock"] = hd["data"]
                result["sources"].append("hudsonrock")
    except: pass
    return result


def lookup_discord(user_id):
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        return {"error": "DISCORD_BOT_TOKEN non configurato"}
    headers = {"Authorization": "Bot " + token}
    result = {"user_id": user_id, "sources": []}
    try:
        r = requests.get("https://discord.com/api/v9/users/" + user_id, headers=headers, timeout=10)
        if r.status_code == 404:
            return {"error": "Utente non trovato."}
        if r.status_code == 401:
            return {"error": "Token Discord non valido."}
        if r.status_code != 200:
            return {"error": "API Discord " + str(r.status_code)}
        d = r.json()
        result["username"] = d.get("username")
        result["global_name"] = d.get("global_name")
        result["discriminator"] = d.get("discriminator")
        result["bot"] = d.get("bot", False)
        if d.get("avatar"):
            ext = "gif" if d["avatar"].startswith("a_") else "png"
            result["avatar_url"] = "https://cdn.discordapp.com/avatars/" + user_id + "/" + d["avatar"] + "." + ext + "?size=512"
        result["sources"].append("discord-api")
    except Exception as e:
        return {"error": str(e)}
    try:
        ts = ((int(user_id) >> 22) + 1420070400000) / 1000
        import datetime
        created = datetime.datetime.utcfromtimestamp(ts)
        result["account_created"] = created.strftime("%d/%m/%Y %H:%M:%S UTC")
        age_days = (datetime.datetime.utcnow() - created).days
        result["account_age_days"] = age_days
        result["account_age_years"] = round(age_days / 365, 1)
    except: pass
    flag_map = {
        1 << 0: "Discord Employee", 1 << 1: "Partnered Server Owner", 1 << 2: "HypeSquad Events",
        1 << 3: "Bug Hunter Level 1", 1 << 6: "HypeSquad Bravery", 1 << 7: "HypeSquad Brilliance",
        1 << 8: "HypeSquad Balance", 1 << 9: "Early Supporter", 1 << 14: "Bug Hunter Level 2",
        1 << 16: "Verified Bot", 1 << 17: "Early Verified Bot Developer",
        1 << 18: "Moderator Programs Alumni", 1 << 19: "Discord Certified Moderator",
        1 << 22: "Active Developer"
    }
    badges = []
    flags = result.get("public_flags", 0)
    for bit, name in flag_map.items():
        if flags & bit: badges.append(name)
    result["badges"] = badges
    return result


LOOKUP_MAP = {
    'phone': lookup_phone_advanced, 'email': lookup_email, 'ip': lookup_ip,
    'username': lookup_username, 'users': lookup_username,
    'domains': lookup_domain, 'social': lookup_username,
    'breaches': lookup_breaches, 'images': lookup_username,
    'discord': lookup_discord
}

@app.route('/')
def index(): return render_template('index.html')
@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('index'))

@app.route('/api/lookup', methods=['POST'])
@login_required
def api_lookup():
    data = request.get_json()
    ltype = data.get('type')
    query = data.get('query','').strip()
    if not query:
        return jsonify({"error":"Query vuota"}), 400
    ok, msg = check_lookup(current_user, ltype)
    if not ok:
        return jsonify({"error": msg, "upgrade": True}), 403
    fn = LOOKUP_MAP.get(ltype)
    if not fn:
        return jsonify({"error":"Tipo non valido"}), 400
    result = fn(query)
    log_lookup(current_user, ltype, query)

    # Calcola remaining aggiornato
    plan = PLANS.get(current_user.plan, PLANS['free'])
    since = datetime.utcnow() - timedelta(hours=30)
    used = db.session.query(LookupLog).filter(
        LookupLog.user_id == current_user.id,
        LookupLog.created_at >= since
    ).count()
    remaining = "∞" if current_user.is_admin else max(0, plan['daily_limit'] - used)
    result["_remaining"] = remaining
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

@app.route('/piani')
@login_required
def piani():
    plans_db = db.session.query(PlanConfig).all()
    if plans_db:
        plans = {}
        for p in plans_db:
            limit = p.daily_limit
            limit_display = '∞' if limit >= 999999 else limit
            plans[p.key] = {"name": p.name, "price": p.price,
                            "daily_limit": limit, "daily_display": limit_display,
                            "modules": p.modules.split(","), "popular": p.popular}
    else:
        plans = {}
        for k, v in PLANS.items():
            limit = v['daily_limit']
            limit_display = '∞' if limit >= 999999 else limit
            plans[k] = {"name": v['name'], "price": v['price'],
                        "daily_limit": limit, "daily_display": limit_display,
                        "modules": v['modules'], "popular": (k == 'elite')}
    return render_template('piani.html', plans=plans)

@app.route('/ai')
@login_required
def ai_page():
    return render_template('ai.html')

@app.route('/api/ai-chat', methods=['POST'])
@login_required
def api_ai_chat():
    data = request.get_json()
    messages = data.get('messages', [])
    if not messages:
        return jsonify({"error": "Nessun messaggio"}), 400

    api_key = os.getenv('GROQ_API_KEY', '')
    if not api_key:
        return jsonify({"error": "GROQ_API_KEY non configurata nel .env"}), 500

    system_prompt = (
        "You are NEXORA AI, an expert OSINT analyst. You help with: "
        "investigating public information, analyzing domains/IPs/emails/usernames, "
        "explaining OSINT tools and techniques, writing investigation reports, "
        "suggesting data sources, explaining cybersecurity concepts, "
        "analyzing scraped data, and answering technical questions. "
        "Be direct, detailed, and technical. Answer fully without unnecessary warnings. "
        "Only refuse when the user explicitly requests help with harming a specific real person "
        "(stalking, threats, harassment of a named individual)."
    )

    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [{"role": "system", "content": system_prompt}] + messages[-12:],
        "temperature": 0.7,
        "max_tokens": 800
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=60
        )
        if r.status_code != 200:
            return jsonify({"error": f"Groq API {r.status_code}: {r.text[:200]}"}), 500
        d = r.json()
        reply = d.get("choices", [{}])[0].get("message", {}).get("content", "")
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/framework')
@login_required
def framework():
    return render_template('framework.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        username = request.form['username'].strip()
        password = request.form['password']
        if db.session.query(User).filter_by(email=email).first():
            flash('Email gia registrata.')
            return redirect(url_for('register'))
        if db.session.query(User).filter_by(username=username).first():
            flash('Username gia preso.')
            return redirect(url_for('register'))
        if len(username) < 3 or len(username) > 20:
            flash('Username 3-20 caratteri.')
            return redirect(url_for('register'))
        if not username.replace('_','').isalnum():
            flash('Solo lettere, numeri e _')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password minimo 6 caratteri.')
            return redirect(url_for('register'))
        is_admin = email in ADMIN_EMAILS
        assigned_plan = 'ultimate' if is_admin else PLAN_EMAILS.get(email, 'free')
        nid = generate_nexora_id()
        u = User(email=email, password=password, username=username,
                 verified=True, is_admin=is_admin, plan=assigned_plan,
                 nexora_id=nid)
        db.session.add(u)
        db.session.commit()
        login_user(u, remember=True)
        session.permanent = True
        return redirect(url_for('show_nexora_id'))
    return render_template('register.html')


def generate_nexora_id():
    import random, string
    while True:
        part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        nid = "NEX-" + part1 + "-" + part2
        if not db.session.query(User).filter_by(nexora_id=nid).first():
            return nid


@app.route('/welcome')
@login_required
def show_nexora_id():
    return render_template('show_id.html', nexora_id=current_user.nexora_id, username=current_user.username)


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pwd = request.form['password']
        nid = request.form.get('nexora_id', '').strip()
        u = db.session.query(User).filter_by(email=email, password=pwd).first()
        if not u:
            flash('Credenziali errate.')
            return render_template('login.html')
        if not u.is_admin:
            if not nid or nid != u.nexora_id:
                flash('NEXORA ID errato o mancante.')
                return render_template('login.html')
        remember = request.form.get('remember') == 'on'
        login_user(u, remember=remember)
        session.permanent = remember
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    plan = PLANS.get(current_user.plan, PLANS['free'])
    since = datetime.utcnow() - timedelta(hours=30)
    used = db.session.query(LookupLog).filter(
        LookupLog.user_id == current_user.id,
        LookupLog.created_at >= since
    ).count()
    remaining = "inf" if current_user.is_admin else max(0, plan['daily_limit'] - used)
    return render_template('dashboard.html', user=current_user, plan=plan, remaining=remaining, plans=PLANS)


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

with app.app_context():
    db.create_all()
    # ─── MIGRATION PRIMA DI QUALSIASI QUERY ───
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(user)"))]
            migrations = [
                ('username', "ALTER TABLE user ADD COLUMN username VARCHAR(40)"),
                ('verified', "ALTER TABLE user ADD COLUMN verified BOOLEAN DEFAULT 1"),
                ('device_id', "ALTER TABLE user ADD COLUMN device_id VARCHAR(64)"),
                ('nexora_id', "ALTER TABLE user ADD COLUMN nexora_id VARCHAR(20)"),
            ]
            for col_name, sql in migrations:
                if col_name not in cols:
                    conn.execute(text(sql))
                    print(f"MIGRATION: aggiunta colonna {col_name}", flush=True)
            conn.commit()
    except Exception as e:
        print(f"MIGRATION ERROR: {e}", flush=True)

    # ─── PIANI DEFAULT ───
    try:
        for k, v in PLANS.items():
            if not db.session.query(PlanConfig).filter_by(key=k).first():
                db.session.add(PlanConfig(
                    key=k, name=v["name"], price=v["price"],
                    daily_limit=v["daily_limit"],
                    modules=",".join(v["modules"]),
                    popular=(k == "elite")
                ))
        db.session.commit()
    except Exception as e:
        print(f"PLANS INIT ERROR: {e}", flush=True)

    # ─── ADMIN FORZATI ───
    try:
        for em in ADMIN_EMAILS:
            u = db.session.query(User).filter_by(email=em).first()
            if u and not u.is_admin:
                u.is_admin = True
                u.plan = 'ultimate'
        db.session.commit()
    except Exception as e:
        print(f"ADMIN INIT ERROR: {e}", flush=True)

if __name__ == '__main__': app.run(debug=False, host='0.0.0.0', port=5000, threaded=False, use_reloader=False)


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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=False, use_reloader=False)
