#!/usr/bin/env python3
# DJ DROP FACTORY PRO v5.1 — Full Backend (All Features)
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
import tempfile
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
            continue
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
        # Library now includes device_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT DEFAULT 'anonymous',
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
            filter_complex = (
                f"[1:a]volume={bg_gain}[bgquiet];"
                f"[bgquiet][0:a]sidechaincompress=threshold={profile['duck_threshold']}:ratio=15[bgduck];"
                f"[0:a][bgduck]amix=inputs=2:duration=first[out]"
            )
            cmd = ["ffmpeg", "-y", "-i", wet_vocal_path, "-i", bg_path,
                   "-filter_complex", filter_complex, "-map", "[out]", "-b:a", "320k", final_output_path]
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

    # Use script override if provided (for strict/training modes)
    script_override = kwargs.get("script_override", None)
    if script_override:
        selected = script_override
    else:
        takes = PremiumDJScriptAI.generate(
            dj_name=dj_name, genre=genre, use_stutter=use_stutter,
            drop_type=drop_type, mood=mood, energy=energy
        )
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
# ROUTES
# ============================================================

# ---------- SYSTEM STATUS ----------
@app.route("/api/status")
def api_status():
    return jsonify({
        "success": True,
        "online": has_internet(),
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "espeak_available": check_espeak() is not None
    })

# ---------- WIZARD VALIDATION ----------
@app.route("/api/wizard_validate", methods=["POST"])
def api_wizard_validate():
    return jsonify({"valid": True, "errors": []})

# ---------- TRENDS, CITY VIBE, NAME SUGGESTIONS ----------
@app.route("/api/trends")
def api_trends():
    return jsonify({"success": True, "trending": WebDataPuller.fetch_trending_genres()})

@app.route("/api/city_vibe")
def api_city_vibe():
    city = request.args.get("city", "")
    if not city:
        return jsonify({"success": False, "error": "No city"}), 400
    vibe = WebDataPuller.fetch_city_vibe(city)
    return jsonify({"success": True, "data": vibe})

@app.route("/api/suggest_names")
def api_suggest_names():
    style = request.args.get("style", "")
    names = WebDataPuller.fetch_dj_name_suggestions(style)
    return jsonify({"success": True, "suggestions": names})

# ---------- STRING TOOLS ----------
@app.route("/api/string_tools", methods=["POST"])
def api_string_tools():
    data = request.get_json() or {}
    text = data.get("text", "")
    operation = data.get("operation", "")
    genre = data.get("genre", "")
    if not text:
        return jsonify({"success": False, "error": "No text"}), 400
    try:
        if operation == "capitalize":
            result = StringWizard.smart_capitalize(text)
        elif operation == "auto_punctuate":
            result = StringWizard.auto_punctuate(text)
        elif operation == "hashtags":
            result = StringWizard.add_hashtags(text, genre)
        elif operation == "stutter_classic":
            result = StringWizard.stutter_pattern(text, "classic")
        else:
            return jsonify({"success": False, "error": "Unknown operation"}), 400
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ---------- VOICE EFFECTS ----------
EFFECT_MAP = {
    "helium": "atempo=1.5,asetrate=44100*1.5",
    "low": "asetrate=44100*0.75,atempo=1.0",
    "robot": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75",
    "echo": "aecho=0.8:0.9:40:0.4",
    "phone": "lowpass=f=3000,highpass=f=200,volume=1.5",
    "slow": "atempo=0.8",
    "fast": "atempo=1.3"
}

@app.route("/api/process_voice", methods=["POST"])
def api_process_voice():
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "No audio file"}), 400
    audio = request.files['audio']
    effect = request.form.get('effect', 'none')
    if effect == 'none' or not FFMPEG_AVAILABLE:
        audio_path = UPLOAD_DIR / f"raw_{int(time.time())}.webm"
        audio.save(audio_path)
        return jsonify({"success": True, "audio_url": f"/uploads/{audio_path.name}", "effect": "none"})
    if effect not in EFFECT_MAP:
        return jsonify({"success": False, "error": "Unknown effect"}), 400
    input_path = UPLOAD_DIR / f"input_{int(time.time())}.webm"
    output_path = UPLOAD_DIR / f"processed_{int(time.time())}.mp3"
    audio.save(input_path)
    try:
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-af", EFFECT_MAP[effect], "-b:a", "320k", str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        return jsonify({"success": True, "audio_url": f"/uploads/{output_path.name}", "effect": effect})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if input_path.exists(): input_path.unlink()

# ---------- BACKGROUND TRACK UPLOAD ----------
@app.route("/api/upload_bg", methods=["POST"])
def api_upload_bg():
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "No file"}), 400
    file = request.files['audio']
    if file.filename == '':
        return jsonify({"success": False, "error": "Empty filename"}), 400
    filename = f"bg_{int(time.time())}_{safe_filename(file.filename)}"
    filepath = UPLOAD_DIR / filename
    file.save(filepath)
    if FFMPEG_AVAILABLE and not filepath.suffix.lower() == '.mp3':
        mp3_path = UPLOAD_DIR / f"{filename.rsplit('.', 1)[0]}.mp3"
        try:
            subprocess.run(["ffmpeg", "-y", "-i", str(filepath), "-b:a", "320k", str(mp3_path)],
                           check=True, capture_output=True)
            filepath.unlink()
            filename = mp3_path.name
        except Exception as e:
            print(f"Background conversion failed: {e}")
    return jsonify({"success": True, "filename": filename})

# ---------- LIVE PREVIEW ----------
@app.route("/api/live_preview", methods=["POST"])
def api_live_preview():
    data = request.get_json() or {}
    dj_name = data.get("dj_name", "DJ Beshi")
    genre = data.get("genre", "dancehall")
    use_stutter = data.get("use_stutter", True)
    mood = data.get("mood", "hype")
    energy = int(data.get("energy", 8))
    city = data.get("city", "")
    user_stutter = data.get("user_stutter", "")
    try:
        scripts = PremiumDJScriptAI.generate(
            dj_name=dj_name, genre=genre, use_stutter=use_stutter,
            mood=mood, energy=energy, city=city, user_stutter=user_stutter,
            count=3
        )
        best = scripts[0]["text"]
        return jsonify({"success": True, "best": best})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ---------- HEARTBEAT ----------
@app.route("/api/heartbeat")
def api_heartbeat():
    return jsonify({
        "success": True,
        "online": has_internet(),
        "ffmpeg": FFMPEG_AVAILABLE,
        "trending": WebDataPuller.fetch_trending_genres()
    })

# ---------- DRAFT SYNC ----------
draft_store = {}

@app.route("/api/draft", methods=["POST"])
def api_draft_save():
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"success": False, "error": "No session"}), 400
    draft_store[session_id] = request.get_json() or {}
    return jsonify({"success": True})

@app.route("/api/draft", methods=["GET"])
def api_draft_load():
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"success": False, "error": "No session"}), 400
    draft = draft_store.get(session_id)
    return jsonify({"success": True, "draft": draft})

@app.route("/api/draft", methods=["DELETE"])
def api_draft_clear():
    session_id = request.headers.get("X-Session-ID")
    if session_id and session_id in draft_store:
        del draft_store[session_id]
    return jsonify({"success": True})

# ---------- USER CREDITS ----------
@app.route("/api/user/credits")
def api_user_credits():
    device_id = request.headers.get("X-Device-ID", "anonymous")
    user = store.get_or_create_user(device_id)
    return jsonify({
        "success": True,
        "credits": user["credits"],
        "subscription": user["subscription"]
    })

# ---------- PAYMENT PACKAGES ----------
PACKAGES = [
    {"id": "starter", "name": "Starter", "credits": 5, "price": 50, "duration_days": 0, "description": "5 drops", "subscription": False},
    {"id": "standard", "name": "Standard", "credits": 20, "price": 150, "duration_days": 0, "description": "20 drops – best value", "subscription": False},
    {"id": "premium_month", "name": "Premium Monthly", "credits": 9999, "price": 300, "duration_days": 30, "description": "Unlimited drops for 30 days", "subscription": True},
    {"id": "premium_year", "name": "Premium Yearly", "credits": 9999, "price": 2500, "duration_days": 365, "description": "Unlimited drops for a year", "subscription": True}
]

@app.route("/api/payment/packages")
def api_payment_packages():
    return jsonify({"success": True, "packages": PACKAGES, "currency": CURRENCY})

# ---------- PAYMENT INITIATE ----------
@app.route("/api/payment/initiate", methods=["POST"])
def api_payment_initiate():
    device_id = request.headers.get("X-Device-ID", "anonymous")
    data = request.get_json() or {}
    package_id = data.get("package_id")
    phone = data.get("phone", "")
    method = data.get("method", "mpesa")

    pkg = next((p for p in PACKAGES if p["id"] == package_id), None)
    if not pkg:
        return jsonify({"success": False, "error": "Invalid package"}), 400

    phone = re.sub(r"[^0-9]", "", phone)
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        phone = "254" + phone
    if len(phone) != 12:
        return jsonify({"success": False, "error": "Invalid phone number"}), 400

    tx_ref = "TX" + datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))
    amount = pkg["price"]

    result = MpesaDaraja.stk_push(phone, amount, account_ref="DJDrop")
    if not result["success"]:
        return jsonify({"success": False, "error": result.get("error", "M-Pesa push failed")}), 500

    store.create_payment(tx_ref, result["checkout_request_id"], device_id, amount, method)
    return jsonify({
        "success": True,
        "tx_ref": tx_ref,
        "checkout_request_id": result["checkout_request_id"],
        "message": "STK push sent. Check your phone."
    })

# ---------- PAYMENT VERIFY ----------
@app.route("/api/payment/verify", methods=["POST"])
def api_payment_verify():
    data = request.get_json() or {}
    tx_ref = data.get("tx_ref")
    if not tx_ref:
        return jsonify({"success": False, "error": "Missing tx_ref"}), 400

    payment = store.get_payment(tx_ref)
    if not payment:
        return jsonify({"success": False, "error": "Transaction not found"}), 404

    if payment["status"] == "success":
        return jsonify({"success": True, "status": "success", "credits_added": 0})

    query_result = MpesaDaraja.query_transaction(payment["checkout_request_id"])
    if query_result["success"]:
        data_mpesa = query_result["data"]
        result_code = data_mpesa.get("ResultCode", "1")
        if result_code == "0":
            store.update_payment_status(tx_ref, "success", mpesa_receipt=data_mpesa.get("MpesaReceiptNumber", ""))
            pkg = next((p for p in PACKAGES if p["price"] == payment["amount"]), None)
            if pkg:
                if pkg["subscription"]:
                    expires = (datetime.now() + timedelta(days=pkg["duration_days"])).isoformat()
                    conn = sqlite3.connect(store.db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET subscription='premium', subscription_expires=?, total_paid=total_paid+? WHERE device_id=?",
                                   (expires, pkg["price"], payment["device_id"]))
                    conn.commit()
                    conn.close()
                else:
                    store.add_credits(payment["device_id"], pkg["credits"])
            return jsonify({"success": True, "status": "success", "credits_added": pkg["credits"] if pkg else 0})
    return jsonify({"success": True, "status": "pending"})

# ---------- PAYMENT CALLBACK (M-Pesa) ----------
@app.route("/api/payment/callback", methods=["POST"])
def api_payment_callback():
    return jsonify({"success": True, "message": "Callback processed"}), 200

# ---------- LIBRARY CRUD ----------
@app.route("/api/library", methods=["GET"])
def api_library_get():
    device_id = request.headers.get("X-Device-ID", "anonymous")
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, script, genre, dj_name, project, url, created_at FROM library WHERE device_id = ? ORDER BY created_at DESC", (device_id,))
    rows = cursor.fetchall()
    conn.close()
    drops = [{
        "id": row[0],
        "title": row[1],
        "script": row[2],
        "genre": row[3],
        "dj_name": row[4],
        "project": row[5],
        "url": row[6],
        "date": row[7]
    } for row in rows]
    return jsonify({"success": True, "drops": drops})

@app.route("/api/library", methods=["POST"])
def api_library_post():
    device_id = request.headers.get("X-Device-ID", "anonymous")
    data = request.get_json() or {}
    required = ["title", "script", "url"]
    if not all(k in data for k in required):
        return jsonify({"success": False, "error": "Missing fields"}), 400
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO library (title, script, genre, dj_name, project, url, device_id) VALUES (?,?,?,?,?,?,?)",
        (data.get("title"), data.get("script"), data.get("genre", ""), data.get("dj_name", ""), data.get("project", ""), data.get("url"), device_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Saved"})

@app.route("/api/library/<int:drop_id>", methods=["DELETE"])
def api_library_delete(drop_id):
    device_id = request.headers.get("X-Device-ID", "anonymous")
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM library WHERE id = ? AND device_id = ?", (drop_id, device_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ---------- DISCOVER ENDPOINTS ----------
@app.route("/api/all")
def api_all():
    return jsonify({
        "success": True,
        "data": {
            "dj_groups": store.get_dj_groups(),
            "streaming_apps": store.get_streaming_apps(),
            "dj_software": store.get_dj_software(),
            "festivals": store.get_festivals(),
            "theater_streaming": store.get_theater_streaming()
        }
    })

@app.route("/api/dj-groups")
def api_dj_groups():
    style = request.args.get("style")
    origin = request.args.get("origin")
    return jsonify({"success": True, "dj_groups": store.get_dj_groups(style=style, origin=origin)})

@app.route("/api/streaming-apps")
def api_streaming_apps():
    category = request.args.get("category")
    free = request.args.get("free_only")
    free_only = free.lower() == "true" if free else None
    return jsonify({"success": True, "streaming_apps": store.get_streaming_apps(category=category, free_only=free_only)})

@app.route("/api/dj-software")
def api_dj_software():
    category = request.args.get("category")
    platform = request.args.get("platform")
    return jsonify({"success": True, "dj_software": store.get_dj_software(category=category, platform=platform)})

@app.route("/api/festivals")
def api_festivals():
    genre = request.args.get("genre")
    location = request.args.get("location")
    return jsonify({"success": True, "festivals": store.get_festivals(genre=genre, location=location)})

@app.route("/api/theater-streaming")
def api_theater_streaming():
    region = request.args.get("region")
    return jsonify({"success": True, "theater_streaming": store.get_theater_streaming(region=region)})

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    results = store.search(q)
    return jsonify({"success": True, "results": {"all": results}})

# ---------- SHARE & DOWNLOAD ----------
@app.route("/share/<project_name>")
def public_share_page(project_name):
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

@app.route("/download/<project>/<filename>")
def download_file(project, filename):
    file_path = OUTPUT_DIR / project / filename
    if file_path.exists():
        return send_file(str(file_path), as_attachment=True)
    return jsonify({"success": False, "error": "File not found"}), 404

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ---------- MAIN GENERATION ENDPOINT (UPDATED) ----------
@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json() or {}
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        user = store.get_or_create_user(device_id)

        mode = data.get("mode", "ai")
        dj_name = data.get("dj_name", "DJ Beshi")
        genre = data.get("genre", "dancehall")
        voice_choice = data.get("voice", "4")
        use_stutter = data.get("use_stutter", True)
        custom_script = data.get("custom_script", "")
        training_example = data.get("training_example", "")
        drop_type = data.get("drop_type", "intro")
        mood = data.get("mood", "hype")
        energy = int(data.get("energy", 8))
        city = data.get("city", "")
        user_stutter = data.get("user_stutter", "")
        bg_track_filename = data.get("bg_track", "")

        # Voice mapping
        voice_map = {
            "1": "en-US-AndrewNeural",
            "2": "en-GB-RyanNeural",
            "3": "en-US-AriaNeural",
            "4": "en-NG-AbeoNeural",
            "5": "en-GB-SoniaNeural",
            "6": "en-NG-NgoziNeural",
            "7": AUTO_GENRE_VOICE.get(genre.lower(), "en-NG-AbeoNeural")
        }
        voice = voice_map.get(voice_choice, "en-NG-AbeoNeural")

        # Background track
        bg_track = ""
        if bg_track_filename:
            p = UPLOAD_DIR / bg_track_filename
            if p.exists():
                bg_track = str(p)

        # Check credits
        if user['subscription'] != 'premium' and user['credits'] <= 0:
            return jsonify({"success": False, "error": "insufficient_credits", "message": "No credits left"}), 402

        # Determine script
        if mode == "strict" and custom_script:
            selected_script = custom_script
        elif mode == "training" and training_example:
            generated = AITrainingEngine.generate_from_training(dj_name, genre, energy, training_example)
            selected_script = generated if generated else "DJ Drop Factory custom drop."
        else:
            takes = PremiumDJScriptAI.generate(
                dj_name=dj_name, genre=genre, use_stutter=use_stutter,
                drop_type=drop_type, mood=mood, energy=energy,
                city=city, user_stutter=user_stutter, count=1
            )
            selected_script = takes[0]["text"] if takes else "DJ Drop Factory premium drop."

        selected_script = StringWizard.smart_capitalize(StringWizard.auto_punctuate(selected_script))

        # Async generation with script_override
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(build_premium_drop(
            dj_name=dj_name,
            genre=genre,
            voice=voice,
            use_stutter=use_stutter,
            bg_track=bg_track,
            drop_type=drop_type,
            mood=mood,
            energy=energy,
            script_override=selected_script
        ))
        loop.close()

        # Deduct credit
        store.deduct_credit(device_id)

        filename = Path(result["final_master"]).name
        return jsonify({
            "success": True,
            "project": result["project_name"],
            "script": selected_script,
            "download_url": f"/download/{result['project_name']}/{filename}",
            "share_url": f"/share/{result['project_name']}",
            "exported_to_local_phone": result.get("exported_to_device", False),
            "local_phone_path": result.get("device_path", ""),
            "credits_remaining": store.get_or_create_user(device_id)['credits']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
