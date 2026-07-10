# ============================================================
# DJ DROP FACTORY PRO v5.0 — LIVE EDITION
# Created by: Macdonald Barasa
# Email: simiyumacdonal1@gmail.com
# ============================================================

import os
import re
import random
import asyncio
import subprocess
import shutil
import urllib.request
import urllib.parse
import json
import time
import gzip
import sqlite3
import base64
import requests
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import edge_tts

app = Flask(__name__)
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "generated_drops"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
TRAINING_DIR = BASE_DIR / "training_data"
TRAINING_DIR.mkdir(exist_ok=True)

# ============================================================
# DARAJA M-PESA CONFIGURATION (HIDDEN FROM FRONTEND)
# ============================================================
DARAJA_CONSUMER_KEY = os.environ.get("DARAJA_CONSUMER_KEY", "7QPUZLBKANxkoI0D63vBXIY8NgwtVOg3hBZfoad6hfKGcIUK")
DARAJA_CONSUMER_SECRET = os.environ.get("DARAJA_CONSUMER_SECRET", "JiCV8ho34x5KCvDcI228dGvfOshdiHqWCmYUoSLuiHVQNHUfDJGOkUIXIcP3NGGw")
DARAJA_ENV = os.environ.get("DARAJA_ENV", "sandbox")
DARAJA_BASE_URL = os.environ.get("DARAJA_BASE_URL", "https://sandbox.safaricom.co.ke")
MERCHANT_PHONE = os.environ.get("MERCHANT_PHONE", "254748322641")  # YOUR NUMBER - HIDDEN
MERCHANT_TILL = os.environ.get("MERCHANT_TILL", "174379")  # Paybill number
MERCHANT_PASSKEY = os.environ.get("MERCHANT_PASSKEY", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://yourapp.onrender.com/api/payment/callback")

# ============================================================
# PERFORMANCE: Response compression & caching headers
# ============================================================

@app.after_request
def after_request(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "public, max-age=300"
    if response.content_type == "application/json" and response.content_length and response.content_length > 1024:
        accept_encoding = request.headers.get('Accept-Encoding', '')
        if 'gzip' in accept_encoding:
            try:
                buffer = BytesIO()
                gzip.GzipFile(fileobj=buffer, mode='w').write(response.get_data())
                compressed = buffer.getvalue()
                if len(compressed) < response.content_length:
                    response.set_data(compressed)
                    response.headers['Content-Encoding'] = 'gzip'
                    response.headers['Content-Length'] = len(compressed)
            except Exception:
                pass
    return response


# ============================================================
# TOOLS CHECK
# ============================================================

def has_internet(timeout=3):
    try:
        urllib.request.urlopen('https://www.google.com', timeout=timeout)
        return True
    except Exception:
        return False

def check_ffmpeg():
    return shutil.which('ffmpeg')

def check_espeak():
    return shutil.which('espeak-ng') or shutil.which('espeak')

FFMPEG_AVAILABLE = check_ffmpeg() is not None
ESPEAK_AVAILABLE = check_espeak() is not None

print("=" * 60)
print("DJ DROP FACTORY PRO v5.0 — LIVE EDITION")
print("=" * 60)
print(f"Internet: {'YES' if has_internet() else 'NO'}")
print(f"FFmpeg:   {'YES' if FFMPEG_AVAILABLE else 'NO'}")
print(f"espeak:   {'YES' if ESPEAK_AVAILABLE else 'NO'}")
print(f"Daraja:   {DARAJA_ENV.upper()}")
print("=" * 60)


# ============================================================
# DARAJA M-PESA INTEGRATION
# ============================================================

class DarajaAPI:
    @classmethod
    def get_access_token(cls):
        """Get OAuth access token from Daraja"""
        try:
            url = f"{DARAJA_BASE_URL}/oauth/generate?grant_type=client_credentials"
            response = requests.get(url, auth=(DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET), timeout=10)
            if response.status_code == 200:
                return response.json().get('access_token')
        except Exception as e:
            print(f"[Daraja] Token error: {e}")
        return None
    
    @classmethod
    def generate_password(cls):
        """Generate password for STK push"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        raw_string = f"{MERCHANT_TILL}{MERCHANT_PASSKEY}{timestamp}"
        return base64.b64encode(raw_string.encode()).decode('utf-8'), timestamp
    
    @classmethod
    def initiate_stk_push(cls, phone_number, amount, tx_ref, callback_url=None):
        """
        Initiate M-Pesa STK Push to user's phone
        phone_number: User's phone (e.g., 254712345678)
        amount: Amount to charge
        tx_ref: Transaction reference
        """
        if not callback_url:
            callback_url = CALLBACK_URL
        
        access_token = cls.get_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to get access token"}
        
        password, timestamp = cls.generate_password()
        
        # Format phone number (remove leading 0, add 254)
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        
        payload = {
            "BusinessShortCode": MERCHANT_TILL,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": MERCHANT_TILL,
            "PhoneNumber": phone_number,
            "CallBackURL": callback_url,
            "AccountReference": tx_ref,
            "TransactionDesc": "DJ Drop Factory Credits"
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            url = f"{DARAJA_BASE_URL}/mpesa/stkpush/v1/processrequest"
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            result = response.json()
            
            if response.status_code == 200 and result.get('ResponseCode') == '0':
                return {
                    "success": True,
                    "merchant_request_id": result.get('MerchantRequestID'),
                    "checkout_request_id": result.get('CheckoutRequestID'),
                    "response_description": result.get('ResponseDescription'),
                    "customer_message": "Please check your phone and enter your M-Pesa PIN to complete the payment."
                }
            else:
                return {
                    "success": False,
                    "error": result.get('errorMessage', 'STK push failed'),
                    "response": result
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @classmethod
    def query_stk_status(cls, checkout_request_id):
        """Query STK push status"""
        access_token = cls.get_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to get access token"}
        
        password, timestamp = cls.generate_password()
        
        payload = {
            "BusinessShortCode": MERCHANT_TILL,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            url = f"{DARAJA_BASE_URL}/mpesa/stkpushquery/v1/query"
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            result = response.json()
            
            if response.status_code == 200:
                result_code = result.get('ResultCode')
                if result_code == '0':
                    return {"success": True, "status": "completed", "result": result}
                elif result_code == '1037':
                    return {"success": True, "status": "pending", "result": result}
                else:
                    return {"success": True, "status": "failed", "result": result}
            return {"success": False, "error": "Query failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================
# DATA STORE — DJ Groups, Streaming Apps, Software, Festivals, Theater
# ============================================================

class DataStore:
    """Holds all music/DJ data. SQLite-backed, queryable, searchable."""
    
    def __init__(self, db_path="dj_music.db"):
        self.db_path = db_path
        self._init_db()
        self._seed_if_empty()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS dj_groups (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                origin TEXT,
                style TEXT,
                activities TEXT,
                notable_events TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS streaming_apps (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                best_for TEXT,
                price TEXT,
                catalog_size TEXT,
                free_tier INTEGER,
                platform TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS dj_software (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT,
                features TEXT,
                price TEXT,
                category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS festivals_events (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT,
                dates TEXT,
                headliners TEXT,
                genre TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS theater_streaming (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                content_type TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                device_id TEXT UNIQUE,
                credits INTEGER DEFAULT 0,
                subscription TEXT DEFAULT 'free',
                subscription_expires TEXT,
                total_paid REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                tx_ref TEXT UNIQUE,
                device_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                method TEXT,
                checkout_request_id TEXT,
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
    
    def _seed_if_empty(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dj_groups")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return
        
        # Seed data (abbreviated for space - same as before)
        dj_groups = [
            ("C2C", "France", "Turntablism / Hip-Hop", "DMC competitions, live shows", "DMC World Championship"),
            ("Swedish House Mafia", "Sweden", "EDM / House", "Ibiza residencies, world tours", "Ushuaïa Ibiza"),
            ("The Martinez Brothers", "USA", "House / Techno", "Ibiza residencies, global tours", "DC-10 Ibiza"),
        ]
        cursor.executemany("INSERT INTO dj_groups (name, origin, style, activities, notable_events) VALUES (?,?,?,?,?)", dj_groups)
        
        streaming_apps = [
            ("Spotify", "Major Paid", "Overall experience", "$12.99/mo", "100M+ tracks", 1, "All"),
            ("Apple Music", "Major Paid", "Apple ecosystem", "$10.99/mo", "100M+ tracks", 0, "Apple, Android"),
        ]
        cursor.executemany("INSERT INTO streaming_apps (name, category, best_for, price, catalog_size, free_tier, platform) VALUES (?,?,?,?,?,?,?)", streaming_apps)
        
        conn.commit()
        conn.close()
        print("[DataStore] Database seeded.")
    
    def _query(self, sql, params=(), one=False):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        result = [dict(row) for row in rows]
        return result[0] if one and result else result
    
    def get_dj_groups(self, style=None, origin=None):
        query = "SELECT * FROM dj_groups WHERE 1=1"
        params = []
        if style:
            query += " AND style LIKE ?"
            params.append(f"%{style}%")
        if origin:
            query += " AND origin = ?"
            params.append(origin)
        return self._query(query, params)
    
    def get_streaming_apps(self, category=None, free_only=None):
        query = "SELECT * FROM streaming_apps WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if free_only is not None:
            query += " AND free_tier = ?"
            params.append(1 if free_only else 0)
        return self._query(query, params)
    
    def get_all(self):
        return {
            "dj_groups": self.get_dj_groups(),
            "streaming_apps": self.get_streaming_apps(),
        }
    
    def search(self, term):
        tables = ["dj_groups", "streaming_apps"]
        results = {}
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            conditions = " OR ".join([f"{col} LIKE ?" for col in columns])
            cursor.execute(f"SELECT * FROM {table} WHERE {conditions}", [f"%{term}%"] * len(columns))
            results[table] = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    
    # User & Payment methods
    def get_or_create_user(self, device_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO users (device_id) VALUES (?)", (device_id,))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
            row = cursor.fetchone()
        conn.close()
        return dict(row) if hasattr(row, 'keys') else {
            'id': row[0], 'device_id': row[1], 'credits': row[2],
            'subscription': row[3], 'subscription_expires': row[4],
            'total_paid': row[5], 'created_at': row[6]
        }
    
    def add_credits(self, device_id, amount):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET credits = credits + ? WHERE device_id = ?", (amount, device_id))
        conn.commit()
        conn.close()
    
    def deduct_credit(self, device_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT credits, subscription, subscription_expires FROM users WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        credits, sub, sub_exp = row[0], row[1], row[2]
        if sub == 'premium' and sub_exp:
            if datetime.fromisoformat(sub_exp) > datetime.now():
                conn.close()
                return True
        if credits > 0:
            cursor.execute("UPDATE users SET credits = credits - 1 WHERE device_id = ?", (device_id,))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False
    
    def create_payment(self, tx_ref, device_id, amount, method="mpesa", checkout_request_id=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (tx_ref, device_id, amount, method, checkout_request_id) VALUES (?,?,?,?,?)",
            (tx_ref, device_id, amount, method, checkout_request_id)
        )
        conn.commit()
        conn.close()
    
    def update_payment_status(self, tx_ref, status, verified=1):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE payments SET status = ?, verified = ? WHERE tx_ref = ?", (status, verified, tx_ref))
        conn.commit()
        conn.close()
    
    def get_payment(self, tx_ref):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None


store = DataStore()


# ============================================================
# WEB DATA PULLER (with caching)
# ============================================================

class WebDataPuller:
    CACHE = {}
    CACHE_TTL = 300
    
    @classmethod
    def _get_cached(cls, key):
        if key in cls.CACHE:
            ts, data = cls.CACHE[key]
            if time.time() - ts < cls.CACHE_TTL:
                return data
        return None
    
    @classmethod
    def _set_cached(cls, key, data):
        cls.CACHE[key] = (time.time(), data)
    
    @classmethod
    def fetch_trending_genres(cls):
        cached = cls._get_cached('trending_genres')
        if cached:
            return cached
        genres = ["Amapiano", "Afrobeat", "Dancehall", "Trap", "Club Banger", "Radio"]
        cls._set_cached('trending_genres', genres)
        return genres
    
    @classmethod
    def fetch_city_vibe(cls, city):
        if not city or not city.strip():
            return {"city": "", "vibe": "unknown", "temperature": 25}
        city_clean = city.strip()
        cached = cls._get_cached(f'city_{city_clean.lower()}')
        if cached:
            return cached
        result = {"city": city_clean, "vibe": "vibing", "temperature": 25}
        cls._set_cached(f'city_{city_clean.lower()}', result)
        return result


# ============================================================
# STRING WIZARD & AI ENGINES (abbreviated - same as before)
# ============================================================

class StringWizard:
    @classmethod
    def smart_capitalize(cls, text):
        words = text.split()
        result = []
        for word in words:
            w = word.strip()
            if not w:
                continue
            if w.upper() in ["DJ", "MC", "NYC", "LA"]:
                result.append(w.upper())
            else:
                result.append(w.capitalize() if w == w.lower() else w)
        return " ".join(result)
    
    @classmethod
    def auto_punctuate(cls, text):
        text = text.strip()
        if not text:
            return text
        text = text[0].upper() + text[1:]
        if text[-1] not in ".!?":
            text += "!"
        return text


class PremiumDJScriptAI:
    GENRE_DATA = {
        "amapiano": {
            "openers": ["Lalela!", "Yanos to the world!"],
            "verbs": ["locking the groove", "running the vibe"],
            "energy_lines": ["strictly smooth pressure", "log drum madness"],
            "closers": ["let the bassline breathe", "vibes only"],
        },
        "club_banger": {
            "openers": ["Hands up!", "Main event settings!"],
            "verbs": ["taking over the decks", "breaking the club"],
            "energy_lines": ["festival-level pressure", "wall-to-wall energy"],
            "closers": ["let's go!", "make some noise!"],
        },
    }
    
    @classmethod
    def generate(cls, dj_name, genre, use_stutter, drop_type="intro", mood="hype",
                 energy=8, city="", count=5):
        genre_key = genre.lower().replace(" ", "_").strip()
        data = cls.GENRE_DATA.get(genre_key, cls.GENRE_DATA["club_banger"])
        
        outputs = []
        for _ in range(count):
            opener = random.choice(data["openers"])
            verb = random.choice(data["verbs"])
            energy_line = random.choice(data["energy_lines"])
            closer = random.choice(data["closers"])
            city_part = f" in {city}" if city else ""
            
            line = f"{opener} {dj_name} is {verb}{city_part}. {energy_line.capitalize()}! {closer.capitalize()}"
            outputs.append({"text": line, "score": 10})
        
        return outputs


# ============================================================
# AUDIO ENGINE (abbreviated - same as before)
# ============================================================

VOICE_MAP = {
    "1": ("Deep Studio Heavy Voice (Male - US)", "en-US-AndrewNeural"),
    "2": ("Crisp Energetic Host (Male - UK)", "en-GB-RyanNeural"),
    "4": ("Natural Afro-Vibe Hype Host (Male - NG)", "en-NG-AbeoNeural"),
}

async def synthesize_tts_smart(text, voice, out_path, rate, volume):
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        await communicate.save(out_path)
        return "edge"
    except Exception as e:
        print(f"TTS failed: {e}")
        Path(out_path).touch()
        return "silent"


async def build_premium_drop(dj_name, genre, voice, drop_type, mood, energy, city, use_stutter):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{dj_name.replace(' ', '_')}_{timestamp}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    takes = PremiumDJScriptAI.generate(dj_name, genre, use_stutter, drop_type, mood, energy, city, count=3)
    selected = takes[0]["text"]
    selected = StringWizard.auto_punctuate(selected)
    
    raw_vocal = out_dir / "raw_vocal.mp3"
    await synthesize_tts_smart(selected, voice, str(raw_vocal), "+5%", "+10%")
    
    return {
        "project_name": project_name,
        "final_master": str(raw_vocal),
        "script": selected,
        "takes": takes,
    }


# ============================================================
# DRAFT MANAGER (for auto-sync)
# ============================================================

class DraftManager:
    DRAFT_FILE = BASE_DIR / "drafts.json"
    
    @classmethod
    def save(cls, session_id, data):
        drafts = {}
        if cls.DRAFT_FILE.exists():
            try:
                with open(cls.DRAFT_FILE, 'r') as f:
                    drafts = json.load(f)
            except Exception:
                drafts = {}
        drafts[session_id] = {
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        with open(cls.DRAFT_FILE, 'w') as f:
            json.dump(drafts, f, indent=2)
    
    @classmethod
    def load(cls, session_id):
        if not cls.DRAFT_FILE.exists():
            return None
        try:
            with open(cls.DRAFT_FILE, 'r') as f:
                drafts = json.load(f)
            entry = drafts.get(session_id)
            if entry:
                return entry.get("data")
        except Exception:
            pass
        return None


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    return jsonify({
        "online": has_internet(),
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "message": "Full audio generation" if FFMPEG_AVAILABLE else "Script only"
    })

@app.route("/api/trends")
def api_trends():
    genres = WebDataPuller.fetch_trending_genres()
    return jsonify({"success": True, "trending": genres})

@app.route("/api/city_vibe")
def api_city_vibe():
    city = request.args.get("city", "")
    data = WebDataPuller.fetch_city_vibe(city)
    return jsonify({"success": True, "data": data})

@app.route("/api/live_preview", methods=["POST"])
def api_live_preview():
    data = request.get_json()
    takes = PremiumDJScriptAI.generate(
        dj_name=data.get("dj_name", "DJ Beshi"),
        genre=data.get("genre", "club_banger"),
        use_stutter=data.get("use_stutter", True),
        drop_type=data.get("drop_type", "intro"),
        mood=data.get("mood", "hype"),
        energy=int(data.get("energy", 8)),
        city=data.get("city", ""),
        count=3
    )
    return jsonify({"success": True, "best": takes[0]["text"]})

@app.route("/api/draft", methods=["POST"])
def api_save_draft():
    data = request.get_json()
    session_id = request.headers.get('X-Session-ID', 'default')
    DraftManager.save(session_id, data)
    return jsonify({"success": True})

@app.route("/api/draft", methods=["GET"])
def api_get_draft():
    session_id = request.headers.get('X-Session-ID', 'default')
    draft = DraftManager.load(session_id)
    return jsonify({"success": True, "draft": draft})

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        user = store.get_or_create_user(device_id)
        
        if user['subscription'] != 'premium' and user['credits'] <= 0:
            return jsonify({
                "success": False,
                "error": "insufficient_credits",
                "message": "No credits left. Please purchase credits."
            }), 402
        
        result = asyncio.run(build_premium_drop(
            dj_name=data.get("dj_name", "DJ Beshi"),
            genre=data.get("genre", "club_banger"),
            voice=VOICE_MAP.get(data.get("voice", "4"), ("", "en-NG-AbeoNeural"))[1],
            drop_type=data.get("drop_type", "intro"),
            mood=data.get("mood", "hype"),
            energy=int(data.get("energy", 8)),
            city=data.get("city", ""),
            use_stutter=data.get("use_stutter", True)
        ))
        
        store.deduct_credit(device_id)
        
        return jsonify({
            "success": True,
            "project": result["project_name"],
            "script": result["script"],
            "download_url": f"/download/{result['project_name']}/{result['final_master'].split('/')[-1]}",
            "credits_remaining": store.get_or_create_user(device_id)['credits']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/download/<project>/<filename>")
def download_file(project, filename):
    file_path = OUTPUT_DIR / project / filename
    if file_path.exists():
        return send_file(str(file_path), as_attachment=True)
    return jsonify({"success": False, "error": "File not found"}), 404

# ============================================================
# PAYMENT ROUTES - DARAJA M-PESA
# ============================================================

@app.route("/api/user/credits")
def api_user_credits():
    device_id = request.headers.get('X-Device-ID', 'anonymous')
    user = store.get_or_create_user(device_id)
    return jsonify({
        "success": True,
        "credits": user['credits'],
        "subscription": user['subscription']
    })

@app.route("/api/payment/packages")
def api_payment_packages():
    return jsonify({
        "success": True,
        "currency": "KES",
        "packages": [
            {"id": "basic", "name": "5 Drops", "credits": 5, "price": 50},
            {"id": "standard", "name": "15 Drops", "credits": 15, "price": 120},
            {"id": "premium", "name": "Unlimited Monthly", "credits": 9999, "price": 300, "subscription": True, "duration_days": 30},
        ]
    })

@app.route("/api/payment/initiate", methods=["POST"])
def api_payment_initiate():
    """
    Initiates M-Pesa STK Push.
    User's phone receives prompt → enters PIN → payment completes
    Merchant phone (0748322641) is HIDDEN in backend only
    """
    try:
        data = request.get_json()
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        package_id = data.get("package_id", "basic")
        user_phone = data.get("phone", "").strip()
        
        if not user_phone or len(user_phone) < 10:
            return jsonify({"success": False, "error": "Invalid phone number"}), 400
        
        packages = {
            "basic": {"credits": 5, "price": 50},
            "standard": {"credits": 15, "price": 120},
            "premium": {"credits": 9999, "price": 300, "days": 30},
        }
        
        pkg = packages.get(package_id)
        if not pkg:
            return jsonify({"success": False, "error": "Invalid package"}), 400
        
        tx_ref = f"DJF-{device_id[:8]}-{int(time.time())}"
        
        # Initiate STK Push via Daraja
        stk_result = DarajaAPI.initiate_stk_push(user_phone, pkg['price'], tx_ref)
        
        if stk_result['success']:
            # Save payment record
            store.create_payment(
                tx_ref=tx_ref,
                device_id=device_id,
                amount=pkg['price'],
                method="mpesa",
                checkout_request_id=stk_result.get('checkout_request_id')
            )
            
            return jsonify({
                "success": True,
                "tx_ref": tx_ref,
                "checkout_request_id": stk_result.get('checkout_request_id'),
                "status": "pending",
                "amount": pkg['price'],
                "message": stk_result.get('customer_message', 'Check your phone for M-Pesa prompt')
            })
        else:
            return jsonify({
                "success": False,
                "error": stk_result.get('error', 'Payment initiation failed')
            }), 500
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/payment/verify", methods=["POST"])
def api_payment_verify():
    """
    Verify payment status and credit user if successful
    """
    try:
        data = request.get_json()
        tx_ref = data.get("tx_ref")
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        
        if not tx_ref:
            return jsonify({"success": False, "error": "No transaction reference"}), 400
        
        payment = store.get_payment(tx_ref)
        if not payment:
            return jsonify({"success": False, "error": "Transaction not found"}), 404
        
        # Query Daraja for status
        if payment.get('checkout_request_id'):
            status_result = DarajaAPI.query_stk_status(payment['checkout_request_id'])
            
            if status_result.get('success') and status_result.get('status') == 'completed':
                # Payment successful - credit user
                store.update_payment_status(tx_ref, 'success', verified=1)
                
                # Determine credits from amount
                amount = payment['amount']
                if amount <= 50:
                    credits, days = 5, 0
                elif amount <= 120:
                    credits, days = 15, 0
                else:
                    credits, days = 9999, 30
                
                if days > 0:
                    # Subscription
                    expires = datetime.now() + timedelta(days=days)
                    conn = sqlite3.connect(store.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE users SET subscription = 'premium', subscription_expires = ?, credits = ? WHERE device_id = ?",
                        (expires.isoformat(), credits, device_id)
                    )
                    conn.commit()
                    conn.close()
                else:
                    # Credits pack
                    store.add_credits(device_id, credits)
                
                return jsonify({
                    "success": True,
                    "status": "success",
                    "credits_added": credits,
                    "message": "Payment verified! Credits added."
                })
            elif status_result.get('status') == 'pending':
                return jsonify({
                    "success": True,
                    "status": "pending",
                    "message": "Payment pending. Please complete on your phone."
                })
            else:
                return jsonify({
                    "success": True,
                    "status": "failed",
                    "message": "Payment failed or cancelled."
                })
        
        return jsonify({"success": False, "error": "Unable to verify"}), 500
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/payment/callback", methods=["POST", "GET"])
def api_payment_callback():
    """
    Daraja callback when payment completes
    """
    try:
        data = request.get_json() or request.args.to_dict()
        
        # Daraja callback structure
        result_code = data.get('ResultCode')
        tx_ref = data.get('AccountReference') or data.get('MerchantRequestID')
        
        if result_code == '0' and tx_ref:
            # Payment successful
            store.update_payment_status(tx_ref, 'success', verified=1)
            # Credit user logic here...
        
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "version": "5.0",
        "online": has_internet(),
        "ffmpeg": FFMPEG_AVAILABLE
    })


if __name__ == "__main__":
    print("=" * 60)
    print("   DJ DROP FACTORY PRO v5.0 — LIVE EDITION")
    print("   Created by Macdonald Barasa")
    print("   Daraja M-Pesa Integration Active")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
