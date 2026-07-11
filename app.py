#!/usr/bin/env python3
# DJ DROP FACTORY PRO v5.1 — Optimized & Expanded Backend
# Created by Macdonald Barasa
# Email: simiyumacdonal1@gmail.com

import os
import sys
import json
import subprocess
import shutil
import re
import random
import time
import sqlite3
import hashlib
import asyncio
import requests
import base64
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory
from flask_cors import CORS
import edge_tts

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).parent.absolute()
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

for d in [OUTPUT_DIR, UPLOAD_DIR, STATIC_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# FFmpeg check
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
ESPEAK_AVAILABLE = shutil.which("espeak") is not None

# M-Pesa Configuration
DARAJA_ENV = os.environ.get("DARAJA_ENV", "sandbox")
DARAJA_CONSUMER_KEY = os.environ.get("DARAJA_CONSUMER_KEY", "")
DARAJA_CONSUMER_SECRET = os.environ.get("DARAJA_CONSUMER_SECRET", "")
DARAJA_PASSKEY = os.environ.get("DARAJA_PASSKEY", "")
DARAJA_SHORTCODE = os.environ.get("DARAJA_SHORTCODE", "174379")
MERCHANT_PHONE = "254748322641"  
CURRENCY = "KES"

# ============================================================
# LOCAL PHONE STORAGE EXPORTER (Android/Termux Bridge)
# ============================================================

def export_to_phone_storage(source_path, filename):
    """
    Attempts to break out of the Termux environment container 
    and write the file directly to accessible Android system storage.
    """
    possible_destinations = [
        Path("/sdcard/Music/DJDropFactory"),
        Path("/sdcard/Download"),
        Path("/storage/emulated/0/Download"),
        Path("/storage/emulated/0/Music")
    ]
    
    for dest_dir in possible_destinations:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            target_file = dest_dir / filename
            shutil.copy(str(source_path), str(target_file))
            print(f"[Storage Bridge] Successfully exported to phone storage: {target_file}")
            return str(target_file)
        except PermissionError:
            continue  # Requires 'termux-setup-storage' to be granted on Android
        except Exception as e:
            print(f"[Storage Bridge] Target {dest_dir} failed: {e}")
            continue
    return None

# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "dj-drop-factory-secret-key-change-in-production")

# ============================================================
# DATA STORE
# ============================================================

class DataStore:
    def __init__(self, db_path="dj_drop_factory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                device_id TEXT PRIMARY KEY,
                credits INTEGER DEFAULT 5,
                subscription TEXT DEFAULT 'free',
                subscription_expires TEXT,
                total_paid REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                tx_ref TEXT PRIMARY KEY,
                checkout_request_id TEXT,
                device_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                verified INTEGER DEFAULT 0,
                mpesa_receipt TEXT,
                payment_method TEXT DEFAULT 'mpesa',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                script TEXT,
                genre TEXT,
                dj_name TEXT,
                project TEXT,
                url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def get_or_create_user(self, device_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (device_id, credits) VALUES (?, ?)",
                (device_id, 5)
            )
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
            user = cursor.fetchone()
        conn.close()
        return {
            "device_id": user[0],
            "credits": user[1],
            "subscription": user[2],
            "subscription_expires": user[3],
            "total_paid": user[4]
        }

    def deduct_credit(self, device_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET credits = credits - 1 WHERE device_id = ? AND credits > 0",
            (device_id,)
        )
        conn.commit()
        conn.close()

    def add_credits(self, device_id, amount):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET credits = credits + ? WHERE device_id = ?",
            (amount, device_id)
        )
        conn.commit()
        conn.close()

    def create_payment(self, tx_ref, checkout_request_id, device_id, amount, method="mpesa"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (tx_ref, checkout_request_id, device_id, amount, payment_method) VALUES (?, ?, ?, ?, ?)",
            (tx_ref, checkout_request_id, device_id, amount, method)
        )
        conn.commit()
        conn.close()

    def get_payment(self, tx_ref):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "tx_ref": row[0],
                "checkout_request_id": row[1],
                "device_id": row[2],
                "amount": row[3],
                "status": row[4],
                "verified": row[5],
                "mpesa_receipt": row[6],
                "payment_method": row[7],
                "created_at": row[8]
            }
        return None

    def get_payment_by_checkout(self, checkout_request_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE checkout_request_id = ?", (checkout_request_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "tx_ref": row[0],
                "checkout_request_id": row[1],
                "device_id": row[2],
                "amount": row[3],
                "status": row[4],
                "verified": row[5],
                "mpesa_receipt": row[6],
                "payment_method": row[7],
                "created_at": row[8]
            }
        return None

    def update_payment_status(self, tx_ref, status, mpesa_receipt=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if status == "success":
            if mpesa_receipt:
                cursor.execute(
                    "UPDATE payments SET status = ?, verified = 1, mpesa_receipt = ? WHERE tx_ref = ?",
                    (status, mpesa_receipt, tx_ref)
                )
            else:
                cursor.execute(
                    "UPDATE payments SET status = ?, verified = 1 WHERE tx_ref = ?",
                    (status, tx_ref)
                )
        else:
            cursor.execute(
                "UPDATE payments SET status = ? WHERE tx_ref = ?",
                (status, tx_ref)
            )
        conn.commit()
        conn.close()

    def get_all(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        cursor.execute("SELECT * FROM payments")
        payments = cursor.fetchall()
        conn.close()
        return {
            "users": [{"device_id": u[0], "credits": u[1], "subscription": u[2], "total_paid": u[4]} for u in users],
            "payments": [{"tx_ref": p[0], "device_id": p[2], "amount": p[3], "status": p[4]} for p in payments]
        }

    def get_dj_groups(self, style=None, origin=None):
        data = [
            {"name": "Amapiano Syndicate", "style": "amapiano", "origin": "SA"},
            {"name": "Afrobeat Warriors", "style": "afrobeat", "origin": "NG"},
            {"name": "Dancehall Empire", "style": "dancehall", "origin": "JM"},
            {"name": "Trap Nation", "style": "trap", "origin": "US"},
            {"name": "House Collective", "style": "house", "origin": "US"},
            {"name": "Reggae Foundation", "style": "reggae", "origin": "JM"},
            {"name": "Latin Crew", "style": "latin", "origin": "PR"},
        ]
        if style:
            data = [d for d in data if d["style"] == style.lower()]
        if origin:
            data = [d for d in data if d["origin"] == origin.upper()]
        return data

    def get_streaming_apps(self, category=None, free_only=None):
        data = [
            {"name": "Spotify", "category": "music", "free": True},
            {"name": "Apple Music", "category": "music", "free": False},
            {"name": "Tidal", "category": "music", "free": False},
            {"name": "YouTube Music", "category": "music", "free": True},
            {"name": "SoundCloud", "category": "music", "free": True},
            {"name": "Audiomack", "category": "music", "free": True},
            {"name": "Boomplay", "category": "music", "free": True},
            {"name": "Deezer", "category": "music", "free": False},
            {"name": "Netflix", "category": "video", "free": False},
            {"name": "Hulu", "category": "video", "free": False},
            {"name": "Disney+", "category": "video", "free": False},
            {"name": "Tubi", "category": "video", "free": True},
            {"name": "Pluto TV", "category": "video", "free": True},
        ]
        if category:
            data = [d for d in data if d["category"] == category.lower()]
        if free_only is not None:
            data = [d for d in data if d["free"] == free_only]
        return data

    def get_dj_software(self, category=None, platform=None):
        data = [
            {"name": "Serato DJ Pro", "category": "performance", "platform": "mac/win"},
            {"name": "Rekordbox", "category": "performance", "platform": "mac/win"},
            {"name": "Traktor Pro", "category": "performance", "platform": "mac/win"},
            {"name": "Virtual DJ", "category": "performance", "platform": "mac/win/linux"},
            {"name": "Ableton Live", "category": "production", "platform": "mac/win"},
            {"name": "FL Studio", "category": "production", "platform": "win"},
            {"name": "Logic Pro", "category": "production", "platform": "mac"},
            {"name": "Cubase", "category": "production", "platform": "mac/win"},
            {"name": "Mixxx", "category": "performance", "platform": "mac/win/linux"},
            {"name": "DJUCED", "category": "performance", "platform": "win"},
        ]
        if category:
            data = [d for d in data if d["category"] == category.lower()]
        if platform:
            data = [d for d in data if platform.lower() in d["platform"].lower()]
        return data

    def get_festivals(self, genre=None, location=None):
        data = [
            {"name": "Ultra Miami", "genre": "edm", "location": "Miami"},
            {"name": "Tomorrowland", "genre": "edm", "location": "Belgium"},
            {"name": "Afro Nation", "genre": "afrobeat", "location": "Portugal"},
            {"name": "Coachella", "genre": "mixed", "location": "California"},
            {"name": "Glastonbury", "genre": "mixed", "location": "UK"},
            {"name": "Burning Man", "genre": "mixed", "location": "Nevada"},
            {"name": "Sensation", "genre": "edm", "location": "Netherlands"},
            {"name": "Sziget", "genre": "mixed", "location": "Hungary"},
            {"name": "Parookaville", "genre": "edm", "location": "Germany"},
        ]
        if genre:
            data = [d for d in data if d["genre"] == genre.lower()]
        if location:
            data = [d for d in data if location.lower() in d["location"].lower()]
        return data

    def get_theater_streaming(self, region=None):
        data = [
            {"name": "BroadwayHD", "region": "US", "type": "theater"},
            {"name": "National Theatre Live", "region": "UK", "type": "theater"},
            {"name": "Digital Theatre", "region": "Global", "type": "theater"},
            {"name": "Marquee TV", "region": "Global", "type": "theater"},
            {"name": "Met Opera on Demand", "region": "US", "type": "opera"},
            {"name": "Royal Opera House Stream", "region": "UK", "type": "opera"},
        ]
        if region:
            data = [d for d in data if region.lower() in d["region"].lower()]
        return data

    def search(self, term):
        term = term.lower()
        all_data = []
        all_data.extend([{"type": "dj_group", **d} for d in self.get_dj_groups()])
        all_data.extend([{"type": "streaming_app", **d} for d in self.get_streaming_apps()])
        all_data.extend([{"type": "dj_software", **d} for d in self.get_dj_software()])
        all_data.extend([{"type": "festival", **d} for d in self.get_festivals()])
        results = []
        for item in all_data:
            if any(term in str(v).lower() for v in item.values()):
                results.append(item)
        return results

store = DataStore()

# ============================================================
# M-PESA DARAJA INTEGRATION
# ============================================================

class MpesaDaraja:
    @classmethod
    def _get_token(cls):
        if not DARAJA_CONSUMER_KEY or not DARAJA_CONSUMER_SECRET:
            print("[M-Pesa] ERROR: Consumer Key or Secret missing")
            return None

        url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        if DARAJA_ENV == "production":
            url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

        try:
            response = requests.get(
                url,
                auth=(DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET),
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")
            else:
                print(f"[M-Pesa] Token error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[M-Pesa] Token exception: {e}")
        return None

    @classmethod
    def stk_push(cls, phone, amount, account_ref="DJDrop", description="DJ Drop Credits"):
        token = cls._get_token()
        if not token:
            return {"success": False, "error": "Failed to authenticate with M-Pesa"}

        phone = re.sub(r"[^0-9]", "", str(phone))
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif not phone.startswith("254"):
            phone = "254" + phone

        if len(phone) != 12:
            return {"success": False, "error": f"Invalid phone number length: {phone}"}

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{DARAJA_SHORTCODE}{DARAJA_PASSKEY}{timestamp}".encode()
        ).decode()

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        if DARAJA_ENV == "production":
            url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        payload = {
            "BusinessShortCode": DARAJA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": DARAJA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": f"{os.environ.get('BASE_URL', request.host_url.rstrip('/'))}/api/payment/callback",
            "AccountReference": account_ref[:12],
            "TransactionDesc": description[:30]
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60
            )
            data = response.json()
            if response.status_code == 200 and data.get("ResponseCode") == "0":
                return {
                    "success": True,
                    "checkout_request_id": data.get("CheckoutRequestID"),
                    "response_code": data.get("ResponseCode"),
                    "message": data.get("CustomerMessage", "STK Push sent")
                }
            else:
                return {
                    "success": False,
                    "error": data.get("errorMessage", data.get("ResponseDescription", "STK Push failed"))
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def query_transaction(cls, checkout_request_id):
        token = cls._get_token()
        if not token:
            return {"success": False, "error": "Failed to authenticate"}

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{DARAJA_SHORTCODE}{DARAJA_PASSKEY}{timestamp}".encode()
        ).decode()

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
        if DARAJA_ENV == "production":
            url = "https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query"

        payload = {
            "BusinessShortCode": DARAJA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            data = response.json()
            if response.status_code == 200:
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": data.get("errorMessage", "Query failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ============================================================
# UTILITY FUNCTIONS & ENGINES
# ============================================================

def has_internet():
    try:
        requests.get("https://www.google.com", timeout=3)
        return True
    except:
        return False

def check_espeak():
    return shutil.which("espeak")

class AITrainingEngine:
    @classmethod
    def generate_from_training(cls, dj_name, genre, energy, example_text):
        if not example_text or len(example_text) < 10:
            return None
        templates = [
            f"🔥 {dj_name} in the building! {example_text[:30]}... Let's go!",
            f"🎧 {dj_name} on the decks! {example_text[:40]}... Turn it up!",
            f"⚡ {dj_name} bringing the heat! {example_text[:35]}... Energy!",
            f"💥 {dj_name} - {genre.upper()} vibes! {example_text[:30]}... Massive!"
        ]
        return random.choice(templates)

    @classmethod
    def save_training(cls, text, genre, mode): return True

    @classmethod
    def analyze_style(cls, text):
        length = len(text.split())
        return {"length": length, "energy": "high" if length > 10 else "medium"}

class PremiumDJScriptAI:
    @classmethod
    def generate(cls, dj_name, genre, use_stutter=True, drop_type="intro", mood="hype",
                 energy=8, city="", event_name="", user_stutter="", station_name="",
                 slogan="", crew_tag="", count=8):
        scripts = []
        templates = [
            f"🔥 Yo! This is {dj_name} on the ones and twos, bringing you that {genre} energy!",
            f"🎧 {dj_name} in the mix! {genre.upper()} vibes all night long!",
            f"⚡ {dj_name} here! We're about to take it to the next level with that {genre}!",
            f"💥 {dj_name} on the decks! {genre} is in the building, let's get it!",
        ]
        for i in range(count):
            base = random.choice(templates)
            if city: base = base.replace("!", f" from {city}!")
            if event_name: base = f"🎤 {event_name} - " + base
            if station_name: base = f"📻 {station_name} - " + base
            if slogan: base = base + f" {slogan}"
            if crew_tag: base = base + f" {crew_tag.upper()}!"
            if use_stutter:
                words = base.split()
                if len(words) > 3:
                    idx = random.randint(1, min(3, len(words)-2))
                    words[idx] = words[idx][0] + "-" + words[idx]
                    base = " ".join(words)
            if user_stutter: base = user_stutter + " " + base
            scripts.append({"text": base, "score": random.randint(8, 15)})
        scripts.sort(key=lambda x: x["score"], reverse=True)
        return scripts

class StringWizard:
    @classmethod
    def smart_capitalize(cls, text):
        return " ".join([w.capitalize() if len(w) > 2 and w.isalpha() else w for w in text.split()])

    @classmethod
    def auto_punctuate(cls, text):
        if text and text[-1] not in ['.', '!', '?']: text += '.'
        return text

    @classmethod
    def add_hashtags(cls, text, genre):
        hashtags = {"amapiano": "#Amapiano #PianoVibes", "dancehall": "#Dancehall #JamaicanVibes"}
        return f"{text} {hashtags.get(genre.lower(), '#DJLife #Vibes')}"

    @classmethod
    def generate_slug(cls, text):
        return re.strip('-', re.sub(r'[^a-z0-9]+', '-', text.lower()))[:50]

    @classmethod
    def stutter_pattern(cls, text, style="classic"):
        words = text.split()
        if len(words) < 3: return text
        if style == "classic":
            words[0] = f"{words[0][0]}-{words[0]}"
        return " ".join(words)

    @classmethod
    def extract_keywords(cls, text): return [w for w in text.split() if len(w) > 3][:5]
    @classmethod
    def analyze_sentiment(cls, text): return "positive", 1
    @classmethod
    def format_for_platform(cls, text, platform): return text[:280] if platform == 'twitter' else text

class WebDataPuller:
    @classmethod
    def fetch_trending_genres(cls): return ["amapiano", "afrobeat", "dancehall", "trap", "reggae"]
    @classmethod
    def fetch_city_vibe(cls, city): return {"city": city, "vibe": "🔥 hype", "mood": "energetic"}
    @classmethod
    def fetch_dj_name_suggestions(cls, style): return [f"DJ {style} Master", f"Vibe {style}"]
    @classmethod
    def fetch_quote_of_the_day(cls): return ["Music is the strongest form of magic."]

# ============================================================
# AUDIO MIXING PRODUCTION STUDIO
# ============================================================

class PremiumAudioStudio:
    @classmethod
    def get_fx_profile(cls, style_key, energy):
        profiles = {
            "amapiano": {"bg_gain": 0.65, "duck_threshold": -28, "duck_release": 120},
            "dancehall": {"bg_gain": 0.60, "duck_threshold": -26, "duck_release": 100},
        }
        return profiles.get(style_key, {"bg_gain": 0.65, "duck_threshold": -26, "duck_release": 110})

    @classmethod
    def build_vocal_fx_chain(cls, style_key, energy, fx_mode):
        chain = ["aecho=0.7:0.7:120:0.15", "loudnorm=I=-12:TP=-0.5", "alimiter=level_in=1:level_out=1"]
        return ",".join(chain), {"vocal_gain": 1.0}

    @classmethod
    def run_ffmpeg(cls, cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0: raise RuntimeError(result.stderr)

    @classmethod
    def render_wet_vocal(cls, vocal_path, wet_output_path, style_preset, energy=8, fx_mode="auto", vocal_gain=1.0):
        vocal_fx, p = cls.build_vocal_fx_chain(style_preset, energy, fx_mode)
        cmd = ["ffmpeg", "-y", "-i", vocal_path, "-af", vocal_fx, "-b:a", "320k", wet_output_path]
        cls.run_ffmpeg(cmd)

    @classmethod
    def render_final_master(cls, wet_vocal_path, bg_path, final_output_path, style_preset, energy=8, bg_gain=None):
        profile = cls.get_fx_profile(style_preset, energy)
        bg_gain = bg_gain if bg_gain is not None else profile["bg_gain"]
        if bg_path and os.path.exists(bg_path):
            filter_complex = f"[1:a]volume={bg_gain}[bgquiet];[bgquiet][0:a]sidechaincompress=threshold={profile['duck_threshold']}:ratio=15[bgduck];[0:a][bgduck]amix=inputs=2:duration=first[out]"
            cmd = ["ffmpeg", "-y", "-i", wet_vocal_path, "-i", bg_path, "-filter_complex", filter_complex, "-map", "[out]", "-b:a", "320k", final_output_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", wet_vocal_path, "-c:a", "libmp3lame", "-b:a", "320k", final_output_path]
        cls.run_ffmpeg(cmd)

VOICE_PRESETS = {"amapiano": {"rate": "+2%", "volume": "+10%"}, "dancehall": {"rate": "+11%", "volume": "+16%"}}
VOICE_MAP = {"1": ("Deep Studio Heavy Voice", "en-US-AndrewNeural"), "2": ("Crisp Host", "en-GB-RyanNeural")}
AUTO_GENRE_VOICE = {"amapiano": "en-NG-AbeoNeural", "dancehall": "en-US-AndrewNeural"}

def safe_filename(name):
    return re.sub(r"\s+", "_", re.sub(r"[^\w\-\. ]+", "", (name or "").strip())) or "premium_master"

async def synthesize_tts_smart(text, voice, out_path, rate, volume):
    if has_internet():
        try:
            await edge_tts.Communicate(text, voice, rate=rate, volume=volume).save(out_path)
            return "edge"
        except: pass
    espeak_cmd = check_espeak()
    if espeak_cmd and FFMPEG_AVAILABLE:
        wav_path = str(Path(out_path).with_suffix('.wav'))
        subprocess.run([espeak_cmd, '-w', wav_path, text], capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-i', wav_path, '-b:a', '320k', out_path], capture_output=True)
        if os.path.exists(wav_path): os.remove(wav_path)
        return "espeak"
    Path(out_path).touch()
    return "silent"

async def build_premium_drop(dj_name, genre, voice, use_stutter, bg_track, drop_type, mood, energy, **kwargs):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{safe_filename(dj_name)}_{timestamp}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    takes = PremiumDJScriptAI.generate(dj_name=dj_name, genre=genre, use_stutter=use_stutter, drop_type=drop_type, mood=mood, energy=energy)
    selected = StringWizard.smart_capitalize(StringWizard.auto_punctuate(takes[0]["text"]))

    raw_vocal = out_dir / "raw_vocal.mp3"
    wet_vocal = out_dir / "wet_vocal.mp3"
    final_master = out_dir / f"{project_name}.mp3"

    preset = VOICE_PRESETS.get(genre.lower(), {"rate": "+5%", "volume": "+10%"})
    tts_engine = await synthesize_tts_smart(selected, voice, str(raw_vocal), preset["rate"], preset["volume"])

    if FFMPEG_AVAILABLE and raw_vocal.exists():
        PremiumAudioStudio.render_wet_vocal(str(raw_vocal), str(wet_vocal), genre, energy, vocal_gain=1.0)
        PremiumAudioStudio.render_final_master(str(wet_vocal), bg_track, str(final_master), genre, energy)
    else:
        shutil.copy(str(raw_vocal), str(final_master))

    # --- ATTEMPT LOCAL DEVICE STORAGE EXPORT ---
    exported_path = export_to_phone_storage(final_master, f"{project_name}.mp3")

    return {
        "project_name": project_name,
        "final_master": str(final_master),
        "script": selected,
        "tts_engine": tts_engine,
        "exported_to_device": exported_path is not None,
        "device_path": exported_path
    }

# ============================================================
# SHARING ENGINE & CORE ROUTES
# ============================================================

@app.route("/share/<project_name>")
def public_share_page(project_name):
    """
    Renders a landing page featuring native meta hooks 
    designed for high-fidelity audio link sharing on social applications.
    """
    audio_filename = f"{project_name}.mp3"
    playback_url = f"/download/{project_name}/{audio_filename}"
    return f"""
    <html>
    <head>
        <title>Listen to my new DJ Drop!</title>
        <meta property="og:title" content="DJ Drop Factory - Premium Drop Showcase" />
        <meta property="og:description" content="Listen and download this exclusive custom DJ Drop element." />
        <meta property="og:type" content="music.song" />
        <meta property="og:audio" content="{playback_url}" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: sans-serif; background: #121212; color: #fff; text-align: center; padding: 50px 20px; }}
            .card {{ background: #1e1e1e; padding: 30px; border-radius: 15px; display: inline-block; max-width: 400px; width:100%; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
            audio {{ width: 100%; margin: 20px 0; }}
            .btn {{ display: block; background: #00ff66; color: #000; padding: 12px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🎧 DJ Drop Preview</h2>
            <p>Project ID: {project_name}</p>
            <audio controls src="{playback_url}"></audio>
            <a class="btn" href="{playback_url}" download>📥 DOWNLOAD AUDIO</a>
        </div>
    </body>
    </html>
    """

@app.route("/api/share/<project_name>")
def api_get_share_payload(project_name):
    """
    Generates tailored, target-specific URL arrays 
    ready for deep-linking into WhatsApp, Telegram, or Twitter.
    """
    base_domain = request.host_url.rstrip('/')
    share_url = f"{base_domain}/share/{project_name}"
    raw_text = f"🔥 Yo! Just generated a brand new custom performance drop on the DJ Drop Factory! Check out the production quality here: {share_url}"
    
    return jsonify({
        "success": True,
        "share_link": share_url,
        "targets": {
            "whatsapp": f"https://api.whatsapp.com/send?text={requests.utils.quote(raw_text)}",
            "telegram": f"https://t.me/share/url?url={requests.utils.quote(share_url)}&text={requests.utils.quote(raw_text)}",
            "twitter": f"https://twitter.com/intent/tweet?text={requests.utils.quote(raw_text)}"
        }
    })

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json() or {}
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        user = store.get_or_create_user(device_id)
        
        if user['subscription'] != 'premium' and user['credits'] <= 0:
            return jsonify({"success": False, "error": "insufficient_credits"}), 402

        dj_name = data.get("dj_name", "DJ Beshi")
        genre = data.get("genre", "dancehall")
        voice_choice = data.get("voice", "1")
        voice = VOICE_MAP.get(voice_choice, ("", "en-US-AndrewNeural"))[1]

        bg_track = ""
        if data.get("bg_track"):
            p = UPLOAD_DIR / data.get("bg_track")
            if p.exists(): bg_track = str(p)

        # FIXED: Handled async generation inside thread smoothly
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(build_premium_drop(
            dj_name=dj_name, genre=genre, voice=voice, use_stutter=data.get("use_stutter", True),
            bg_track=bg_track, drop_type=data.get("drop_type", "intro"), mood=data.get("mood", "hype"), energy=int(data.get("energy", 8))
        ))
        loop.close()

        store.deduct_credit(device_id)

        # FIXED: Resolved cross-platform path parsing anomalies using Path().name
        filename = Path(result["final_master"]).name

        return jsonify({
            "success": True,
            "project": result["project_name"],
            "script": result["script"],
            "download_url": f"/download/{result['project_name']}/{filename}",
            "share_url": f"/share/{result['project_name']}",
            "exported_to_local_phone": result["exported_to_device"],
            "local_phone_path": result["device_path"],
            "credits_remaining": store.get_or_create_user(device_id)['credits']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# REMAINING SYSTEM PLACEHOLDERS & STUBS
# ============================================================

@app.route("/download/<project>/<filename>")
def download_file(project, filename):
    file_path = OUTPUT_DIR / project / filename
    if file_path.exists(): return send_file(str(file_path), as_attachment=True)
    return jsonify({"success": False, "error": "File not found"}), 404

@app.route("/api/payment/callback", methods=["POST"])
def api_payment_callback():
    return jsonify({"success": True, "message": "Callback processed"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
