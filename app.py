#!/usr/bin/env python3
# DJ DROP FACTORY PRO v5.0 — Complete Backend
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

# M-Pesa Configuration - MERCHANT PHONE HIDDEN SERVER-SIDE ONLY
DARAJA_ENV = os.environ.get("DARAJA_ENV", "sandbox")
DARAJA_CONSUMER_KEY = os.environ.get("DARAJA_CONSUMER_KEY", "")
DARAJA_CONSUMER_SECRET = os.environ.get("DARAJA_CONSUMER_SECRET", "")
DARAJA_PASSKEY = os.environ.get("DARAJA_PASSKEY", "")
DARAJA_SHORTCODE = os.environ.get("DARAJA_SHORTCODE", "174379")
MERCHANT_PHONE = "254748322641"  # HIDDEN - Server-side only!
CURRENCY = "KES"

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
                token = data.get("access_token")
                print("[M-Pesa] Token obtained successfully")
                return token
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

        # Clean phone number
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
            "CallBackURL": f"{os.environ.get('BASE_URL', 'https://your-domain.com')}/api/payment/callback",
            "AccountReference": account_ref[:12],
            "TransactionDesc": description[:30]
        }

        print(f"[M-Pesa STK] Sending request for {phone} amount {amount}")
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60
            )
            data = response.json()
            print(f"[M-Pesa STK] Response: {data}")

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
            print(f"[M-Pesa STK] Exception: {e}")
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
            print(f"[M-Pesa Query] Response: {data}")
            if response.status_code == 200:
                return {
                    "success": True,
                    "data": data
                }
            else:
                return {
                    "success": False,
                    "error": data.get("errorMessage", "Query failed")
                }
        except Exception as e:
            print(f"[M-Pesa Query] Exception: {e}")
            return {"success": False, "error": str(e)}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def has_internet():
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except:
        return False

def check_espeak():
    return shutil.which("espeak")

# ============================================================
# AI TRAINING ENGINE
# ============================================================

class AITrainingEngine:
    @classmethod
    def generate_from_training(cls, dj_name, genre, energy, example_text):
        if not example_text or len(example_text) < 10:
            return None

        words = example_text.split()
        templates = [
            f"🔥 {dj_name} in the building! {example_text[:30]}... Let's go!",
            f"🎧 {dj_name} on the decks! {example_text[:40]}... Turn it up!",
            f"⚡ {dj_name} bringing the heat! {example_text[:35]}... Energy!",
            f"💥 {dj_name} - {genre.upper()} vibes! {example_text[:30]}... Massive!"
        ]
        return random.choice(templates)

    @classmethod
    def save_training(cls, text, genre, mode):
        return True

    @classmethod
    def analyze_style(cls, text):
        length = len(text.split())
        energy = "high" if length > 10 else "medium"
        return {"length": length, "energy": energy}

# ============================================================
# PREMIUM DJ SCRIPT AI
# ============================================================

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
            f"🎶 {dj_name} bringing the heat! {genre.upper()} sound system!",
            f"🔥 {dj_name} - {genre.upper()} take over! Turn it up!",
            f"🚀 {dj_name} with that {genre} flavor! Ready for the ride!",
            f"💫 {dj_name} on the mic! {genre.upper()} is the vibe!",
        ]

        for i in range(count):
            base = random.choice(templates)
            if city:
                base = base.replace("!", f" from {city}!")
            if event_name:
                base = f"🎤 {event_name} - " + base
            if station_name:
                base = f"📻 {station_name} - " + base
            if slogan:
                base = base + f" {slogan}"
            if crew_tag:
                base = base + f" {crew_tag.upper()}!"
            if use_stutter:
                words = base.split()
                if len(words) > 3:
                    idx = random.randint(1, min(3, len(words)-2))
                    words[idx] = words[idx][0] + "-" + words[idx]
                    base = " ".join(words)
            if user_stutter:
                base = user_stutter + " " + base

            scripts.append({"text": base, "score": random.randint(8, 15)})

        scripts.sort(key=lambda x: x["score"], reverse=True)
        return scripts

# ============================================================
# STRING WIZARD
# ============================================================

class StringWizard:
    @classmethod
    def smart_capitalize(cls, text):
        words = text.split()
        result = []
        for w in words:
            if len(w) > 2 and w.isalpha():
                result.append(w.capitalize())
            else:
                result.append(w)
        return " ".join(result)

    @classmethod
    def auto_punctuate(cls, text):
        if not text:
            return text
        if text[-1] not in ['.', '!', '?']:
            text += '.'
        return text

    @classmethod
    def add_hashtags(cls, text, genre):
        hashtags = {
            "amapiano": "#Amapiano #PianoVibes",
            "dancehall": "#Dancehall #JamaicanVibes",
            "afrobeat": "#Afrobeat #NaijaVibes",
            "trap": "#Trap #HipHop",
            "club_banger": "#ClubBanger #EDM",
        }
        tag = hashtags.get(genre.lower(), "#DJLife #Vibes")
        return f"{text} {tag}"

    @classmethod
    def generate_slug(cls, text):
        text = text.lower()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        text = text.strip('-')
        return text[:50]

    @classmethod
    def stutter_pattern(cls, text, style="classic"):
        words = text.split()
        if len(words) < 3:
            return text
        if style == "classic":
            idx = random.randint(0, min(2, len(words)-2))
            w = words[idx]
            words[idx] = w[0] + "-" + w
        elif style == "build_up":
            for i in range(3):
                if i < len(words):
                    w = words[i]
                    if len(w) > 2:
                        words[i] = w[0] + "-" + w[0] + "-" + w
        elif style == "echo":
            if len(words) > 2:
                words[-1] = words[-1] + " " + words[-1]
        return " ".join(words)

    @classmethod
    def extract_keywords(cls, text):
        words = text.split()
        keywords = [w for w in words if len(w) > 3 and w.isalpha()]
        return keywords[:5]

    @classmethod
    def analyze_sentiment(cls, text):
        positive = ["love", "great", "amazing", "awesome", "good", "best", "fire", "lit", "energy", "vibe"]
        negative = ["bad", "terrible", "awful", "worst", "lame", "boring"]
        score = 0
        text_lower = text.lower()
        for w in positive:
            if w in text_lower:
                score += 1
        for w in negative:
            if w in text_lower:
                score -= 1
        sentiment = "positive" if score > 0 else "negative" if score < 0 else "neutral"
        return sentiment, score

    @classmethod
    def format_for_platform(cls, text, platform):
        platform = platform.lower()
        if platform == "instagram":
            return text[:2200]
        elif platform == "twitter":
            return text[:280]
        elif platform == "youtube":
            return text[:5000]
        return text

    @classmethod
    def process_template(cls, template_key, variables):
        templates = {
            "intro": "{dj_name} here! {city} is in the house! {genre} vibes!",
            "outro": "{dj_name} signing off! Thanks for the energy! {slogan}",
            "promo": "🔥 {dj_name} - {genre}! Catch the wave! {hashtags}"
        }
        template = templates.get(template_key, "{dj_name} on the decks!")
        result = template
        for key, value in variables.items():
            result = result.replace("{" + key + "}", str(value))
        return result

# ============================================================
# WEB DATA PULLER
# ============================================================

class WebDataPuller:
    @classmethod
    def fetch_trending_genres(cls):
        genres = ["amapiano", "afrobeat", "dancehall", "trap", "house", "techno", "reggae", "latin"]
        random.shuffle(genres)
        return genres[:5]

    @classmethod
    def fetch_city_vibe(cls, city):
        vibes = ["🌆 high energy", "🎵 musical", "🔥 hype", "🌃 electric", "💫 vibrant"]
        return {
            "city": city,
            "vibe": random.choice(vibes),
            "mood": random.choice(["happy", "energetic", "chill", "party"])
        }

    @classmethod
    def fetch_dj_name_suggestions(cls, style):
        prefixes = ["DJ", "MC", "VJ", "King", "Queen", "Lil", "Big", "Kid", "Young"]
        suffixes = ["Beats", "Vibes", "Sound", "Mix", "Flow", "Rhythm", "Bass", "Rush"]
        names = []
        for i in range(5):
            name = f"{random.choice(prefixes)} {random.choice(suffixes)}"
            if style:
                name = f"{name} {style.capitalize()}"
            names.append(name)
        return names

    @classmethod
    def fetch_quote_of_the_day(cls):
        quotes = [
            "Music is the strongest form of magic.",
            "Where words fail, music speaks.",
            "Life is a song, love is the music.",
            "The only thing better than music is more music.",
            "Let the music speak.",
            "Music is the heart of life.",
            "Good music creates good times."
        ]
        return quotes

# ============================================================
# PREMIUM AUDIO STUDIO
# ============================================================

class PremiumAudioStudio:
    @classmethod
    def get_fx_profile(cls, style_key, energy):
        profiles = {
            "amapiano": {"bg_gain": 0.65, "duck_threshold": -28, "duck_release": 120},
            "dancehall": {"bg_gain": 0.60, "duck_threshold": -26, "duck_release": 100},
            "afrobeat": {"bg_gain": 0.65, "duck_threshold": -28, "duck_release": 110},
            "trap": {"bg_gain": 0.55, "duck_threshold": -24, "duck_release": 90},
            "club_banger": {"bg_gain": 0.60, "duck_threshold": -26, "duck_release": 95},
            "radio": {"bg_gain": 0.70, "duck_threshold": -30, "duck_release": 130},
        }
        default = {"bg_gain": 0.65, "duck_threshold": -26, "duck_release": 110}
        return profiles.get(style_key, default)

    @classmethod
    def build_vocal_fx_chain(cls, style_key, energy, fx_mode):
        p = {
            "vocal_gain": 1.0, "slap": "aecho=0.8:0.9:30:0.25",
            "echo": "aecho=0.7:0.7:120:0.15", "space": "aecho=0.6:0.5:240:0.1",
            "phaser": "aphaser=type=2:decay=0.4", "stereo": "stereowiden=2",
            "loudness": "loudnorm=I=-12:TP=-0.5", "limiter": "alimiter=level_in=1:level_out=1"
        }

        chain = []
        if style_key == "dancehall":
            if p["slap"]: chain.append(p["slap"])
            if energy >= 7 and p["echo"]: chain.append(p["echo"])
        elif style_key == "amapiano":
            if p["echo"]: chain.append(p["echo"])
            if p["space"]: chain.append(p["space"])
            if energy >= 6 and p["phaser"]: chain.append(p["phaser"])
            if p["stereo"]: chain.append(p["stereo"])
        elif style_key == "afrobeat":
            if p["echo"]: chain.append(p["echo"])
            if p["space"] and energy >= 6: chain.append(p["space"])
            if p["stereo"]: chain.append(p["stereo"])
        elif style_key == "trap":
            if p["echo"]: chain.append(p["echo"])
            if p["phaser"] and energy >= 7: chain.append(p["phaser"])
            if p["stereo"]: chain.append(p["stereo"])
        else:
            if p["echo"]: chain.append(p["echo"])
            if energy >= 7 and p["phaser"]: chain.append(p["phaser"])
            if p["stereo"]: chain.append(p["stereo"])

        chain.append(p["loudness"])
        chain.append(p["limiter"])
        return ",".join([x for x in chain if x]), p

    @classmethod
    def run_ffmpeg(cls, cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg mastering failed:\n" + result.stderr)

    @classmethod
    def render_wet_vocal(cls, vocal_path, wet_output_path, style_preset, energy=8,
                         fx_mode="auto", vocal_gain=1.0):
        vocal_fx, p = cls.build_vocal_fx_chain(style_preset, energy, fx_mode)
        final_gain = vocal_gain * p["vocal_gain"]
        if abs(final_gain - 1.0) > 0.0001:
            vocal_fx = f"volume={final_gain:.2f},{vocal_fx}"
        cmd = [
            "ffmpeg", "-y",
            "-i", vocal_path,
            "-af", vocal_fx,
            "-b:a", "320k",
            wet_output_path
        ]
        cls.run_ffmpeg(cmd)

    @classmethod
    def render_final_master(cls, wet_vocal_path, bg_path, final_output_path,
                            style_preset, energy=8, bg_gain=None):
        profile = cls.get_fx_profile(style_preset, energy)
        if bg_gain is None:
            bg_gain = profile["bg_gain"]
        if bg_path and os.path.exists(bg_path):
            filter_complex = (
                f"[1:a]volume={bg_gain}[bgquiet];"
                f"[bgquiet][0:a]sidechaincompress="
                f"threshold={profile['duck_threshold']}:ratio=15:attack=3:release={profile['duck_release']}[bgduck];"
                f"[0:a][bgduck]amix=inputs=2:duration=first:dropout_transition=2[out]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", wet_vocal_path,
                "-i", bg_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-b:a", "320k",
                final_output_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", wet_vocal_path,
                "-c:a", "libmp3lame",
                "-b:a", "320k",
                final_output_path
            ]
        cls.run_ffmpeg(cmd)

# ============================================================
# VOICE PRESETS
# ============================================================

VOICE_PRESETS = {
    "amapiano": {"rate": "+2%", "volume": "+10%"},
    "dancehall": {"rate": "+11%", "volume": "+16%"},
    "radio": {"rate": "+1%", "volume": "+10%"},
    "club_banger": {"rate": "+9%", "volume": "+14%"},
    "afrobeat": {"rate": "+5%", "volume": "+11%"},
    "trap": {"rate": "+6%", "volume": "+13%"},
}

VOICE_MAP = {
    "1": ("Deep Studio Heavy Voice (Male - US)", "en-US-AndrewNeural"),
    "2": ("Crisp Energetic Host (Male - UK)", "en-GB-RyanNeural"),
    "3": ("Smooth High-End Female Vibe (Female - US)", "en-US-EmmaNeural"),
    "4": ("Natural Afro-Vibe Hype Host (Male - NG)", "en-NG-AbeoNeural"),
    "5": ("Bright Female Radio Host (UK)", "en-GB-SoniaNeural"),
    "6": ("Warm Female Afro Voice (NG)", "en-NG-EzinneNeural"),
}

AUTO_GENRE_VOICE = {
    "amapiano": "en-NG-AbeoNeural",
    "dancehall": "en-US-AndrewNeural",
    "radio": "en-GB-SoniaNeural",
    "club_banger": "en-GB-RyanNeural",
    "afrobeat": "en-NG-EzinneNeural",
    "trap": "en-US-AndrewNeural"
}

def safe_filename(name):
    name = (name or "").strip()
    name = re.sub(r"[^\w\-\. ]+", "", name)
    name = re.sub(r"\s+", "_", name)
    return name or "premium_master"

# ============================================================
# TTS WITH GRACEFUL DEGRADATION
# ============================================================

async def synthesize_tts_smart(text, voice, out_path, rate, volume):
    online = has_internet()
    if online:
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            await communicate.save(out_path)
            return "edge"
        except Exception as e:
            print(f"Edge TTS failed: {e}")
    espeak_cmd = check_espeak()
    if espeak_cmd and FFMPEG_AVAILABLE:
        try:
            wav_path = str(Path(out_path).with_suffix('.espeak.wav'))
            subprocess.run([espeak_cmd, '-w', wav_path, text], capture_output=True, check=True)
            if os.path.exists(wav_path):
                subprocess.run([
                    'ffmpeg', '-y', '-i', wav_path,
                    '-b:a', '320k', out_path
                ], capture_output=True, check=True)
                os.remove(wav_path)
                return "espeak"
        except Exception as e:
            print(f"espeak failed: {e}")
    if FFMPEG_AVAILABLE:
        try:
            subprocess.run([
                'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
                '-t', '3', '-b:a', '320k', out_path
            ], capture_output=True, check=True)
            return "silent"
        except Exception as e:
            print(f"Silent MP3 failed: {e}")
    Path(out_path).touch()
    return "silent"

# ============================================================
# MAIN GENERATION FUNCTION
# ============================================================

async def build_premium_drop(dj_name, genre, voice, use_stutter, bg_track,
                             drop_type, mood, energy, city, event_name,
                             user_stutter, station_name, slogan, crew_tag,
                             fx_mode, vocal_gain, bg_gain, mode="ai", custom_script="",
                             training_example=None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{safe_filename(dj_name)}_{timestamp}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if training_example and training_example.strip():
        mimic_result = AITrainingEngine.generate_from_training(
            dj_name=dj_name,
            genre=genre,
            energy=energy,
            example_text=training_example
        )
        if mimic_result:
            selected = mimic_result
            takes = [{"text": selected, "score": 15, "mimic": True}]
        else:
            takes = PremiumDJScriptAI.generate(
                dj_name=dj_name, genre=genre, use_stutter=use_stutter,
                drop_type=drop_type, mood=mood, energy=energy, city=city,
                event_name=event_name, user_stutter=user_stutter,
                station_name=station_name, slogan=slogan, crew_tag=crew_tag,
                count=8
            )
            selected = takes[0]["text"]
    elif mode == "strict" and custom_script.strip():
        selected = custom_script.strip()
        takes = [{"text": selected, "score": 10}]
    else:
        takes = PremiumDJScriptAI.generate(
            dj_name=dj_name, genre=genre, use_stutter=use_stutter,
            drop_type=drop_type, mood=mood, energy=energy, city=city,
            event_name=event_name, user_stutter=user_stutter,
            station_name=station_name, slogan=slogan, crew_tag=crew_tag,
            count=8
        )
        selected = takes[0]["text"]

    selected = StringWizard.auto_punctuate(selected)
    selected = StringWizard.smart_capitalize(selected)
    if drop_type == "promo":
        selected = StringWizard.add_hashtags(selected, genre)

    takes_file = out_dir / "takes.txt"
    with open(takes_file, "w", encoding="utf-8") as f:
        for i, item in enumerate(takes, 1):
            txt = StringWizard.auto_punctuate(item["text"])
            f.write(f"{i}. ({item['score']}) {txt}\n")

    raw_vocal = out_dir / "raw_vocal.mp3"
    wet_vocal = out_dir / "wet_vocal.mp3"
    final_master = out_dir / f"{project_name}.mp3"

    preset = VOICE_PRESETS.get(genre.lower(), {"rate": "+5%", "volume": "+10%"})

    tts_engine = await synthesize_tts_smart(
        selected, voice, str(raw_vocal), preset["rate"], preset["volume"]
    )

    if FFMPEG_AVAILABLE and raw_vocal.exists() and raw_vocal.stat().st_size > 0:
        try:
            PremiumAudioStudio.render_wet_vocal(
                vocal_path=str(raw_vocal),
                wet_output_path=str(wet_vocal),
                style_preset=genre,
                energy=energy,
                fx_mode=fx_mode,
                vocal_gain=vocal_gain
            )
        except Exception as e:
            print(f"Wet FX failed: {e}")
            shutil.copy(str(raw_vocal), str(wet_vocal))
    else:
        shutil.copy(str(raw_vocal), str(wet_vocal))

    if FFMPEG_AVAILABLE and wet_vocal.exists() and wet_vocal.stat().st_size > 0:
        try:
            PremiumAudioStudio.render_final_master(
                wet_vocal_path=str(wet_vocal),
                bg_path=bg_track,
                final_output_path=str(final_master),
                style_preset=genre,
                energy=energy,
                bg_gain=bg_gain
            )
        except Exception as e:
            print(f"Final master failed: {e}")
            shutil.copy(str(wet_vocal), str(final_master))
    else:
        shutil.copy(str(wet_vocal), str(final_master))

    return {
        "project_name": project_name,
        "out_dir": str(out_dir),
        "final_master": str(final_master),
        "wet_vocal": str(wet_vocal),
        "takes_file": str(takes_file),
        "script": selected,
        "takes": takes,
        "mode": mode,
        "tts_engine": tts_engine,
        "offline": tts_engine == "espeak" or tts_engine == "silent",
        "ffmpeg_available": FFMPEG_AVAILABLE
    }

# ============================================================
# DRAFT MANAGER
# ============================================================

class DraftManager:
    DRAFT_FILE = BASE_DIR / "drafts.json"
    MAX_DRAFTS = 50

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
        if len(drafts) > cls.MAX_DRAFTS:
            sorted_items = sorted(drafts.items(), key=lambda x: x[1].get('timestamp', ''), reverse=True)
            drafts = dict(sorted_items[:cls.MAX_DRAFTS])
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

    @classmethod
    def delete(cls, session_id):
        if not cls.DRAFT_FILE.exists():
            return
        try:
            with open(cls.DRAFT_FILE, 'r') as f:
                drafts = json.load(f)
            if session_id in drafts:
                del drafts[session_id]
                with open(cls.DRAFT_FILE, 'w') as f:
                    json.dump(drafts, f, indent=2)
        except Exception:
            pass

# ============================================================
# FLASK ROUTES — DJ DROP FACTORY CORE
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/service-worker.js')
def serve_sw():
    return send_from_directory('static', 'service-worker.js',
                                mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route("/api/status")
def api_status():
    return jsonify({
        "online": has_internet(),
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "espeak_available": ESPEAK_AVAILABLE,
        "edge_tts_ready": has_internet(),
        "message": "Full audio generation" if FFMPEG_AVAILABLE else "Script only - no audio FX"
    })

@app.route("/api/voices")
def get_voices():
    return jsonify({
        "voices": VOICE_MAP,
        "auto_map": AUTO_GENRE_VOICE
    })

@app.route("/api/trends")
def api_trends():
    try:
        genres = WebDataPuller.fetch_trending_genres()
        return jsonify({"success": True, "trending": genres, "source": "wikipedia_api"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/city_vibe")
def api_city_vibe():
    city = request.args.get("city", "")
    if not city:
        return jsonify({"success": False, "error": "No city provided"}), 400
    try:
        data = WebDataPuller.fetch_city_vibe(city)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/suggest_names")
def api_suggest_names():
    style = request.args.get("style", "")
    try:
        names = WebDataPuller.fetch_dj_name_suggestions(style)
        return jsonify({"success": True, "suggestions": names})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/quote")
def api_quote():
    try:
        quotes = WebDataPuller.fetch_quote_of_the_day()
        return jsonify({"success": True, "quotes": quotes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/string_tools", methods=["POST"])
def api_string_tools():
    try:
        data = request.get_json()
        text = data.get("text", "")
        operation = data.get("operation", "capitalize")
        genre = data.get("genre", "club_banger")
        platform = data.get("platform", "generic")
        if not text:
            return jsonify({"success": False, "error": "No text provided"}), 400
        result = text
        if operation == "capitalize":
            result = StringWizard.smart_capitalize(text)
        elif operation == "slug":
            result = StringWizard.generate_slug(text)
        elif operation == "hashtags":
            result = StringWizard.add_hashtags(text, genre)
        elif operation == "stutter_classic":
            result = StringWizard.stutter_pattern(text, "classic")
        elif operation == "stutter_build":
            result = StringWizard.stutter_pattern(text, "build_up")
        elif operation == "stutter_echo":
            result = StringWizard.stutter_pattern(text, "echo")
        elif operation == "auto_punctuate":
            result = StringWizard.auto_punctuate(text)
        elif operation == "keywords":
            result = StringWizard.extract_keywords(text)
        elif operation == "sentiment":
            sentiment, score = StringWizard.analyze_sentiment(text)
            result = {"sentiment": sentiment, "score": score}
        elif operation == "platform_format":
            result = StringWizard.format_for_platform(text, platform)
        elif operation == "template_fill":
            template_key = data.get("template", "intro")
            variables = data.get("variables", {})
            result = StringWizard.process_template(template_key, variables)
        return jsonify({
            "success": True,
            "original": text,
            "result": result,
            "operation": operation
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/wizard_validate", methods=["POST"])
def api_wizard_validate():
    try:
        data = request.get_json()
        step = int(data.get("step", 1))
        errors = []
        if step == 1:
            dj_name = data.get("dj_name", "").strip()
            if not dj_name or len(dj_name) < 2:
                errors.append("DJ name must be at least 2 characters")
            if len(dj_name) > 40:
                errors.append("DJ name too long (max 40 chars)")
            city = data.get("city", "").strip()
            if city and len(city) > 30:
                errors.append("City name too long")
        elif step == 2:
            genre = data.get("genre", "").strip()
            if not genre:
                errors.append("Please select a genre")
            drop_type = data.get("drop_type", "").strip()
            if not drop_type:
                errors.append("Please select a drop type")
        elif step == 3:
            energy = int(data.get("energy", 0))
            if energy < 1 or energy > 10:
                errors.append("Energy must be between 1-10")
            voice = data.get("voice", "").strip()
            if not voice:
                errors.append("Please select a voice")
        return jsonify({
            "success": len(errors) == 0,
            "valid": len(errors) == 0,
            "errors": errors,
            "step": step
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/draft", methods=["POST"])
def api_save_draft():
    try:
        data = request.get_json()
        session_id = request.headers.get('X-Session-ID', 'default')
        DraftManager.save(session_id, data)
        return jsonify({"success": True, "message": "Draft saved to server"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/draft", methods=["GET"])
def api_get_draft():
    try:
        session_id = request.headers.get('X-Session-ID', 'default')
        draft = DraftManager.load(session_id)
        return jsonify({"success": True, "draft": draft})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/draft", methods=["DELETE"])
def api_delete_draft():
    try:
        session_id = request.headers.get('X-Session-ID', 'default')
        DraftManager.delete(session_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/live_preview", methods=["POST"])
def api_live_preview():
    try:
        data = request.get_json()
        dj_name = data.get("dj_name", "DJ Beshi")
        genre = data.get("genre", "club_banger")
        drop_type = data.get("drop_type", "intro")
        mood = data.get("mood", "hype")
        energy = int(data.get("energy", 8))
        city = data.get("city", "")
        use_stutter = data.get("use_stutter", True)
        user_stutter = data.get("user_stutter", "")
        takes = PremiumDJScriptAI.generate(
            dj_name=dj_name, genre=genre, use_stutter=use_stutter,
            drop_type=drop_type, mood=mood, energy=energy, city=city,
            user_stutter=user_stutter, count=3
        )
        for t in takes:
            t["text"] = StringWizard.auto_punctuate(t["text"])
        return jsonify({
            "success": True,
            "scripts": [t["text"] for t in takes],
            "best": takes[0]["text"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/heartbeat")
def api_heartbeat():
    try:
        return jsonify({
            "success": True,
            "time": datetime.now().isoformat(),
            "online": has_internet(),
            "ffmpeg": FFMPEG_AVAILABLE,
            "quote": random.choice(WebDataPuller.fetch_quote_of_the_day()),
            "trending": WebDataPuller.fetch_trending_genres()[:3]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/train", methods=["POST"])
def api_train():
    try:
        data = request.get_json()
        example_text = data.get("example", "").strip()
        dj_name = data.get("dj_name", "DJ Beshi").strip()
        genre = data.get("genre", "club_banger")
        energy = int(data.get("energy", 8))
        mode = data.get("train_mode", "mimic")
        if not example_text:
            return jsonify({"success": False, "error": "No example text provided"}), 400
        if mode == "exact":
            AITrainingEngine.save_training(example_text, genre, "exact_copy")
            return jsonify({
                "success": True,
                "script": example_text,
                "mode": "exact",
                "message": "Exact copy saved and ready to use!"
            })
        mimic = AITrainingEngine.generate_from_training(
            dj_name=dj_name,
            genre=genre,
            energy=energy,
            example_text=example_text
        )
        return jsonify({
            "success": True,
            "original": example_text,
            "script": mimic,
            "mode": "mimic",
            "analysis": AITrainingEngine.analyze_style(example_text),
            "message": "AI learned your style and created a new drop!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        user = store.get_or_create_user(device_id)
        if user['subscription'] != 'premium':
            if user['credits'] <= 0:
                return jsonify({
                    "success": False,
                    "error": "insufficient_credits",
                    "message": "You have no credits left. Please purchase credits to continue.",
                    "credits": user['credits'],
                    "subscription": user['subscription']
                }), 402

        mode = data.get("mode", "ai")
        custom_script = data.get("custom_script", "").strip()
        training_example = data.get("training_example", "").strip()
        dj_name = data.get("dj_name", "DJ Beshi").strip()
        genre = data.get("genre", "club_banger")
        voice_choice = data.get("voice", "7")
        use_stutter = data.get("use_stutter", True)
        drop_type = data.get("drop_type", "intro")
        mood = data.get("mood", "hype")
        energy = int(data.get("energy", 8))
        city = data.get("city", "").strip()
        event_name = data.get("event_name", "").strip()
        user_stutter = data.get("user_stutter", "").strip()
        station_name = data.get("station_name", "").strip()
        slogan = data.get("slogan", "").strip()
        crew_tag = data.get("crew_tag", "").strip()
        fx_mode = data.get("fx_mode", "auto")
        vocal_gain = float(data.get("vocal_gain", 1.0))
        bg_gain = data.get("bg_gain")
        bg_gain = float(bg_gain) if bg_gain else None
        bg_track = data.get("bg_track", "")

        if voice_choice == "7":
            voice = AUTO_GENRE_VOICE.get(genre, "en-US-AndrewNeural")
        else:
            voice = VOICE_MAP.get(voice_choice, ("", "en-US-AndrewNeural"))[1]

        full_bg_path = ""
        if bg_track:
            potential_path = UPLOAD_DIR / bg_track
            if potential_path.exists():
                full_bg_path = str(potential_path)

        result = asyncio.run(build_premium_drop(
            dj_name=dj_name,
            genre=genre,
            voice=voice,
            use_stutter=use_stutter,
            bg_track=full_bg_path,
            drop_type=drop_type,
            mood=mood,
            energy=energy,
            city=city,
            event_name=event_name,
            user_stutter=user_stutter,
            station_name=station_name,
            slogan=slogan,
            crew_tag=crew_tag,
            fx_mode=fx_mode,
            vocal_gain=vocal_gain,
            bg_gain=bg_gain,
            mode=mode,
            custom_script=custom_script,
            training_example=training_example
        ))

        store.deduct_credit(device_id)

        return jsonify({
            "success": True,
            "project": result["project_name"],
            "script": result["script"],
            "takes": result["takes"],
            "mode": result["mode"],
            "tts_engine": result["tts_engine"],
            "offline": result["offline"],
            "ffmpeg_available": result["ffmpeg_available"],
            "download_url": f"/download/{result['project_name']}/{result['final_master'].split('/')[-1]}",
            "credits_remaining": store.get_or_create_user(device_id)['credits'],
            "message": "Drop generated!" + (" (Neural voice)" if result["tts_engine"] == "edge" else " (Basic audio)" if result["tts_engine"] == "espeak" else " (Audio unavailable)")
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Empty filename"}), 400
    filename = safe_filename(file.filename)
    filepath = UPLOAD_DIR / filename
    file.save(str(filepath))
    return jsonify({"success": True, "filename": filename})

@app.route("/download/<project>/<filename>")
def download_file(project, filename):
    file_path = OUTPUT_DIR / project / filename
    if file_path.exists():
        return send_file(str(file_path), as_attachment=True)
    return jsonify({"success": False, "error": "File not found"}), 404

@app.route("/api/preview_script", methods=["POST"])
def preview_script():
    data = request.get_json()
    dj_name = data.get("dj_name", "DJ Beshi")
    genre = data.get("genre", "club_banger")
    use_stutter = data.get("use_stutter", True)
    drop_type = data.get("drop_type", "intro")
    mood = data.get("mood", "hype")
    energy = int(data.get("energy", 8))
    city = data.get("city", "")
    event_name = data.get("event_name", "")
    user_stutter = data.get("user_stutter", "")
    station_name = data.get("station_name", "")
    slogan = data.get("slogan", "")
    crew_tag = data.get("crew_tag", "")
    takes = PremiumDJScriptAI.generate(
        dj_name=dj_name, genre=genre, use_stutter=use_stutter,
        drop_type=drop_type, mood=mood, energy=energy, city=city,
        event_name=event_name, user_stutter=user_stutter,
        station_name=station_name, slogan=slogan, crew_tag=crew_tag, count=3
    )
    for t in takes:
        t["text"] = StringWizard.auto_punctuate(t["text"])
    return jsonify({
        "success": True,
        "scripts": [t["text"] for t in takes],
        "best": takes[0]["text"]
    })

# ============================================================
# VOICE EFFECTS PROCESSOR
# ============================================================

@app.route("/api/process_voice", methods=["POST"])
def process_voice_effect():
    try:
        if not FFMPEG_AVAILABLE:
            return jsonify({
                "success": False, 
                "error": "FFmpeg is not available on this server. Cannot apply voice effects."
            }), 503
        if "audio" not in request.files:
            return jsonify({"success": False, "error": "No audio file provided"}), 400
        audio_file = request.files["audio"]
        effect = request.form.get("effect", "none")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_path = UPLOAD_DIR / f"voice_raw_{timestamp}.webm"
        output_path = UPLOAD_DIR / f"voice_effect_{effect}_{timestamp}.mp3"
        audio_file.save(str(input_path))
        filter_chain = None
        if effect == "helium":
            filter_chain = "asetrate=44100*1.8,atempo=1/1.8,highpass=f=80,acompressor=threshold=-18dB:ratio=4,loudnorm=I=-14:TP=-1.0"
        elif effect == "low":
            filter_chain = "asetrate=44100*0.55,atempo=1/0.55,highpass=f=60,acompressor=threshold=-16dB:ratio=5,loudnorm=I=-14:TP=-1.0"
        elif effect == "robot":
            filter_chain = "highpass=f=200,aecho=0.8:0.6:5:0.3,vibrato=f=8:d=0.5,equalizer=f=3000:width_type=q:width=2:g=6,equalizer=f=800:width_type=q:width=1.5:g=4,acompressor=threshold=-14dB:ratio=6,loudnorm=I=-12:TP=-0.5"
        elif effect == "echo":
            filter_chain = "aecho=0.85:0.65:180|360:0.25|0.15,aecho=0.80:0.50:650|900:0.12|0.08,highpass=f=100,acompressor=threshold=-16dB:ratio=4,loudnorm=I=-14:TP=-1.0"
        elif effect == "phone":
            filter_chain = "highpass=f=300,lowpass=f=3400,equalizer=f=1000:width_type=q:width=1.5:g=3,acompressor=threshold=-14dB:ratio=5,loudnorm=I=-14:TP=-1.0"
        elif effect == "slow":
            filter_chain = "atempo=0.5,asetrate=22050,aresample=44100,acompressor=threshold=-16dB:ratio=4,loudnorm=I=-14:TP=-1.0"
        elif effect == "fast":
            filter_chain = "atempo=2.0,asetrate=88200,aresample=44100,acompressor=threshold=-16dB:ratio=4,loudnorm=I=-14:TP=-1.0"
        else:
            filter_chain = "highpass=f=80,acompressor=threshold=-18dB:ratio=3,loudnorm=I=-14:TP=-1.0"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-af", filter_chain,
            "-b:a", "320k",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if input_path.exists():
            input_path.unlink()
        if result.returncode != 0:
            return jsonify({
                "success": False, 
                "error": f"FFmpeg processing failed: {result.stderr}"
            }), 500
        if not output_path.exists():
            return jsonify({"success": False, "error": "Output file not created"}), 500
        filename = output_path.name
        return jsonify({
            "success": True,
            "filename": filename,
            "audio_url": f"/uploads/{filename}",
            "download_url": f"/uploads/{filename}",
            "effect": effect,
            "message": f"Voice effect '{effect}' applied successfully!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/uploads/<filename>")
def serve_upload(filename):
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        return send_file(str(file_path))
    return jsonify({"success": False, "error": "File not found"}), 404

# ============================================================
# LIBRARY API
# ============================================================

LIBRARY_FILE = BASE_DIR / "library.json"

def load_library():
    if LIBRARY_FILE.exists():
        with open(LIBRARY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_library(library):
    with open(LIBRARY_FILE, 'w') as f:
        json.dump(library, f, indent=2)

@app.route("/api/library", methods=["GET"])
def get_library():
    return jsonify({"success": True, "drops": load_library()})

@app.route("/api/library", methods=["POST"])
def add_to_library():
    try:
        data = request.get_json()
        library = load_library()
        drop = {
            "id": data.get("id", int(datetime.now().timestamp() * 1000)),
            "title": data.get("title", "Untitled Drop"),
            "script": data.get("script", ""),
            "genre": data.get("genre", "club_banger"),
            "date": data.get("date", datetime.now().isoformat()),
            "project": data.get("project", ""),
            "url": data.get("url", ""),
            "dj_name": data.get("dj_name", "DJ Beshi")
        }
        library.insert(0, drop)
        if len(library) > 100:
            library = library[:100]
        save_library(library)
        return jsonify({"success": True, "drop": drop})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/library/<drop_id>", methods=["DELETE"])
def delete_from_library(drop_id):
    try:
        library = load_library()
        library = [d for d in library if str(d.get("id")) != str(drop_id)]
        save_library(library)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# DISCOVER / DATA API ROUTES
# ============================================================

@app.route("/api/all")
def api_all():
    return jsonify({
        "success": True,
        "data": store.get_all()
    })

@app.route("/api/dj-groups")
def api_dj_groups():
    style = request.args.get("style")
    origin = request.args.get("origin")
    return jsonify({
        "success": True,
        "dj_groups": store.get_dj_groups(style=style, origin=origin)
    })

@app.route("/api/streaming-apps")
def api_streaming_apps():
    category = request.args.get("category")
    free_only = request.args.get("free_only")
    if free_only is not None:
        free_only = free_only.lower() in ("true", "1", "yes")
    return jsonify({
        "success": True,
        "streaming_apps": store.get_streaming_apps(category=category, free_only=free_only)
    })

@app.route("/api/dj-software")
def api_dj_software():
    category = request.args.get("category")
    platform = request.args.get("platform")
    return jsonify({
        "success": True,
        "dj_software": store.get_dj_software(category=category, platform=platform)
    })

@app.route("/api/festivals")
def api_festivals():
    genre = request.args.get("genre")
    location = request.args.get("location")
    return jsonify({
        "success": True,
        "festivals": store.get_festivals(genre=genre, location=location)
    })

@app.route("/api/theater-streaming")
def api_theater_streaming():
    region = request.args.get("region")
    return jsonify({
        "success": True,
        "theater_streaming": store.get_theater_streaming(region=region)
    })

@app.route("/api/search")
def api_search():
    term = request.args.get("q", "")
    if not term:
        return jsonify({"success": False, "error": "Missing 'q' parameter"}), 400
    return jsonify({
        "success": True,
        "results": store.search(term)
    })

# ============================================================
# REAL M-PESA DARAJA PAYMENT & CREDITS SYSTEM
# ============================================================

@app.route("/api/user/credits")
def api_user_credits():
    device_id = request.headers.get('X-Device-ID', 'anonymous')
    user = store.get_or_create_user(device_id)
    return jsonify({
        "success": True,
        "credits": user['credits'],
        "subscription": user['subscription'],
        "subscription_expires": user['subscription_expires'],
        "total_paid": user['total_paid']
    })

@app.route("/api/payment/packages")
def api_payment_packages():
    return jsonify({
        "success": True,
        "currency": CURRENCY,
        "packages": [
            {"id": "basic", "name": "5 Drops", "credits": 5, "price": 50, "description": "Generate 5 premium DJ drops"},
            {"id": "standard", "name": "15 Drops", "credits": 15, "price": 120, "description": "Generate 15 premium DJ drops (Save 30%)"},
            {"id": "premium", "name": "Unlimited Monthly", "credits": 9999, "price": 300, "description": "Unlimited drops for 30 days", "subscription": True, "duration_days": 30},
            {"id": "pro", "name": "Pro Annual", "credits": 9999, "price": 2500, "description": "Unlimited drops for 1 year (Save 30%)", "subscription": True, "duration_days": 365}
        ]
    })

@app.route("/api/payment/initiate", methods=["POST"])
def api_payment_initiate():
    try:
        data = request.get_json()
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        package_id = data.get("package_id", "basic")
        user_phone = data.get("phone", "").strip()

        packages = {
            "basic": {"credits": 5, "price": 50},
            "standard": {"credits": 15, "price": 120},
            "premium": {"credits": 9999, "price": 300, "days": 30},
            "pro": {"credits": 9999, "price": 2500, "days": 365}
        }

        pkg = packages.get(package_id)
        if not pkg:
            return jsonify({"success": False, "error": "Invalid package"}), 400

        if not user_phone:
            return jsonify({"success": False, "error": "Phone number is required"}), 400

        # Clean phone number
        phone = re.sub(r"[^0-9]", "", user_phone)
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif not phone.startswith("254"):
            phone = "254" + phone

        if len(phone) != 12:
            return jsonify({"success": False, "error": f"Invalid phone number (must be 12 digits, got {len(phone)})"}), 400

        tx_ref = f"DJF-{device_id[:8]}-{int(time.time())}"

        mpesa_result = MpesaDaraja.stk_push(
            phone=phone,
            amount=pkg['price'],
            account_ref=f"DJDrop-{package_id}",
            description=f"DJ Drop Factory - {pkg['credits']} Credits"
        )

        if mpesa_result.get("success"):
            store.create_payment(
                tx_ref=tx_ref,
                checkout_request_id=mpesa_result.get("checkout_request_id"),
                device_id=device_id,
                amount=pkg['price'],
                method="mpesa"
            )

            return jsonify({
                "success": True,
                "tx_ref": tx_ref,
                "checkout_request_id": mpesa_result.get("checkout_request_id"),
                "status": "pending",
                "amount": pkg['price'],
                "currency": CURRENCY,
                "message": mpesa_result.get("message", "STK Push sent to your phone"),
                "instructions": {
                    "mpesa": f"Check your phone ({phone}) for the M-Pesa STK push. Enter your M-Pesa PIN to complete the payment.",
                    "note": "Do not close this window until payment is confirmed."
                },
                "verification_url": f"/api/payment/verify",
                "payment_method": "mpesa_stk_push"
            })
        else:
            return jsonify({
                "success": False,
                "error": mpesa_result.get("error", "Failed to initiate payment"),
                "message": "Could not send STK push. Please try again."
            }), 400

    except Exception as e:
        print(f"[Payment Initiate] Exception: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/payment/verify", methods=["POST"])
def api_payment_verify():
    try:
        data = request.get_json()
        tx_ref = data.get("tx_ref")
        checkout_request_id = data.get("checkout_request_id")
        device_id = request.headers.get('X-Device-ID', 'anonymous')

        if not tx_ref:
            return jsonify({"success": False, "error": "No transaction reference"}), 400

        payment = store.get_payment(tx_ref)
        if not payment:
            return jsonify({"success": False, "error": "Transaction not found"}), 404

        if payment.get('verified') == 1 or payment.get('status') == 'success':
            return jsonify({
                "success": True,
                "status": "success",
                "tx_ref": tx_ref,
                "message": "Payment already verified!"
            })

        # Use checkout_request_id from payment if not provided
        if not checkout_request_id:
            checkout_request_id = payment.get('checkout_request_id')

        if checkout_request_id:
            query_result = MpesaDaraja.query_transaction(checkout_request_id)
            if query_result.get("success"):
                result_data = query_result.get("data", {})
                result_code = result_data.get("ResultCode")

                if result_code == 0:
                    store.update_payment_status(tx_ref, "success")

                    amount = payment['amount']
                    if amount <= 50:
                        credits, days = 5, 0
                    elif amount <= 120:
                        credits, days = 15, 0
                    elif amount <= 300:
                        credits, days = 9999, 30
                    else:
                        credits, days = 9999, 365

                    if days > 0:
                        expires = datetime.now() + timedelta(days=days)
                        conn = sqlite3.connect(store.db_path)
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET subscription = 'premium', subscription_expires = ?, credits = ?, total_paid = total_paid + ? WHERE device_id = ?",
                            (expires.isoformat(), credits, amount, device_id)
                        )
                        conn.commit()
                        conn.close()
                    else:
                        store.add_credits(device_id, credits)
                        conn = sqlite3.connect(store.db_path)
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET total_paid = total_paid + ? WHERE device_id = ?",
                            (amount, device_id)
                        )
                        conn.commit()
                        conn.close()

                    return jsonify({
                        "success": True,
                        "status": "success",
                        "tx_ref": tx_ref,
                        "credits_added": credits,
                        "subscription_days": days,
                        "message": "Payment verified! Credits added to your account."
                    })
                else:
                    status = "pending" if result_code is None else "failed"
                    store.update_payment_status(tx_ref, status)
                    return jsonify({
                        "success": True,
                        "status": status,
                        "tx_ref": tx_ref,
                        "message": result_data.get("ResultDesc", "Payment status checked.")
                    })

        return jsonify({
            "success": True,
            "status": payment.get('status', 'pending'),
            "tx_ref": tx_ref,
            "message": "Payment status checked. Please wait for confirmation."
        })

    except Exception as e:
        print(f"[Payment Verify] Exception: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/payment/callback", methods=["POST", "GET"])
def api_payment_callback():
    try:
        # Log the entire request payload
        payload = request.get_json() or {}
        print(f"[M-Pesa Callback] Received payload: {payload}")

        body = payload.get("Body", payload)
        stk_callback = body.get("stkCallback", {})

        checkout_request_id = stk_callback.get("CheckoutRequestID")
        result_code = stk_callback.get("ResultCode")
        result_desc = stk_callback.get("ResultDesc", "")

        print(f"[M-Pesa Callback] CheckoutRequestID: {checkout_request_id}, ResultCode: {result_code}")

        if checkout_request_id:
            payment = store.get_payment_by_checkout(checkout_request_id)
            if payment:
                tx_ref = payment['tx_ref']
                device_id = payment['device_id']

                if result_code == 0:
                    callback_metadata = stk_callback.get("CallbackMetadata", {})
                    items = callback_metadata.get("Item", [])
                    mpesa_receipt = None
                    for item in items:
                        if item.get("Name") == "MpesaReceiptNumber":
                            mpesa_receipt = item.get("Value")
                            break

                    store.update_payment_status(tx_ref, "success", mpesa_receipt)

                    amount = payment['amount']
                    if amount <= 50:
                        credits, days = 5, 0
                    elif amount <= 120:
                        credits, days = 15, 0
                    elif amount <= 300:
                        credits, days = 9999, 30
                    else:
                        credits, days = 9999, 365

                    if days > 0:
                        expires = datetime.now() + timedelta(days=days)
                        conn = sqlite3.connect(store.db_path)
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET subscription = 'premium', subscription_expires = ?, credits = ?, total_paid = total_paid + ? WHERE device_id = ?",
                            (expires.isoformat(), credits, amount, device_id)
                        )
                        conn.commit()
                        conn.close()
                    else:
                        store.add_credits(device_id, credits)
                        conn = sqlite3.connect(store.db_path)
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET total_paid = total_paid + ? WHERE device_id = ?",
                            (amount, device_id)
                        )
                        conn.commit()
                        conn.close()

                    print(f"[M-Pesa Callback] Payment success: {tx_ref}, Receipt: {mpesa_receipt}")
                else:
                    store.update_payment_status(tx_ref, "failed")
                    print(f"[M-Pesa Callback] Payment failed: {tx_ref}, Reason: {result_desc}")

        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[M-Pesa Callback] Exception: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/payment/status/<tx_ref>")
def api_payment_status(tx_ref):
    try:
        payment = store.get_payment(tx_ref)
        if not payment:
            return jsonify({"success": False, "error": "Transaction not found"}), 404
        return jsonify({
            "success": True,
            "tx_ref": tx_ref,
            "status": payment.get('status'),
            "amount": payment.get('amount'),
            "verified": payment.get('verified') == 1,
            "mpesa_receipt": payment.get('mpesa_receipt'),
            "created_at": payment.get('created_at')
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "version": "5.0",
        "timestamp": datetime.now().isoformat(),
        "online": has_internet(),
        "ffmpeg": FFMPEG_AVAILABLE,
        "mpesa": "live" if DARAJA_ENV == "production" else "sandbox",
        "merchant_hidden": True
    })

# ============================================================
# APP STARTUP
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("   DJ DROP FACTORY PRO v5.0 — LIVE EDITION")
    print("   Created by Macdonald Barasa")
    print("   Email: simiyumacdonal1@gmail.com")
    print("=" * 60)
    print("Features: AI Training | Loud Audio | Voice Effects | Library | PWA")
    print("          Web Data Puller | String Wizard | Wizard Validation")
    print("          LIVE Draft Sync | Live Preview | Heartbeat")
    print("          DJ Directory | Streaming Guide | Festival Guide")
    print("          Theater Streaming | REAL M-Pesa STK Push Payments")
    print("=" * 60)
    print("M-Pesa Mode: " + ("PRODUCTION" if DARAJA_ENV == "production" else "SANDBOX"))
    print("Merchant Phone: HIDDEN (server-side only)")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
