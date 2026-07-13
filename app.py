# ============================================================
# DJ DROP FACTORY PRO v5.0 — LIVE EDITION
# Created by: Macdonald Barasa
# Email: simiyumacdonal1@gmail.com
# Features: AI Training, Loud Audio, Voice Effects, Library API,
#           Web Data Puller, String Wizard, Wizard Validation,
#           LIVE Draft Sync, Live Preview, Heartbeat,
#           DJ Directory, Streaming Apps, Festival Guide,
#           Theater Streaming, Payment & Credits System
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
import threading
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, make_response
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
# CONFIG & SECRETS
# ============================================================
MERCHANT_PHONE = os.environ.get("MERCHANT_PHONE", "254748322641")  # Server-side only
FLUTTERWAVE_SECRET = os.environ.get("FLUTTERWAVE_SECRET", "")      # Get from dashboard
PAYMENT_CALLBACK = os.environ.get("PAYMENT_CALLBACK", "https://yourapp.onrender.com/api/payment/callback")
CURRENCY = os.environ.get("CURRENCY", "KES")

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
print("=" * 60)


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
        
        # ── DJ GROUPS ──
        dj_groups = [
            ("C2C", "France", "Turntablism / Hip-Hop", "DMC competitions, live shows, world tours", "DMC World Championship, international tours"),
            ("Scratch Perverts", "UK", "Turntablism / Scratch", "DMC championships, live battles, club residencies", "DMC World Finals, BBC Radio 1 residency"),
            ("Berywam", "France", "Beatbox / Turntablism", "Live performances, beatbox battles, collaborations", "World Beatbox Championship, DMC events"),
            ("DJ Fly", "France", "Turntablism", "DMC competitions, live shows, workshops", "DMC World Championship winner"),
            ("Swedish House Mafia", "Sweden", "EDM / House", "Ibiza residencies, world tours, festival headlining", "Ushuaïa Ibiza residency, Creamfields headline"),
            ("The Martinez Brothers", "USA", "House / Techno", "Ibiza residencies, global tours, label releases", "DC-10 Ibiza residency, Circoloco"),
            ("ARTBAT", "Ukraine", "Melodic Techno", "Festival headlining, global tours, label releases", "Tomorrowland, Ultra Music Festival"),
            ("CamelPhat", "UK", "House / Tech House", "Ibiza residencies, label releases, world tours", "Pacha Ibiza residency, Creamfields"),
            ("MEDUZA", "Italy", "House", "Global residencies, festival headlining", "Hï Ibiza residency, Tomorrowland"),
            ("RÜFÜS DU SOL", "Australia", "Indie Dance / House", "World tours, Ibiza residencies, live sets", "Sónar Festival, Coachella"),
            ("Overmono", "UK", "Electronic / Experimental", "World tours, live sets, remixes", "Glastonbury, Boiler Room"),
            ("TOMORA", "International", "Electronic", "Live performances, collaborative shows", "Roundhouse London, festival circuits"),
        ]
        cursor.executemany(
            "INSERT INTO dj_groups (name, origin, style, activities, notable_events) VALUES (?,?,?,?,?)",
            dj_groups
        )
        
        # ── STREAMING APPS ──
        streaming_apps = [
            ("Spotify", "Major Paid", "Overall experience, algorithms", "$12.99/mo", "100M+ tracks", 1, "All"),
            ("Apple Music", "Major Paid", "Apple ecosystem, Spatial Audio", "$10.99/mo", "100M+ tracks", 0, "Apple, Android"),
            ("Tidal", "Major Paid", "Hi-Res Audio, Dolby Atmos", "$11.99/mo", "110M+ tracks", 0, "All"),
            ("YouTube Music", "Major Paid", "Video + music, Android users", "$11.99/mo", "100M+ tracks", 1, "All"),
            ("Amazon Music Unlimited", "Major Paid", "Prime users, Alexa", "$11.99/mo", "100M+ tracks", 0, "All"),
            ("Deezer", "Major Paid", "European listeners, Flow feature", "$11.99/mo", "120M+ tracks", 1, "All"),
            ("Qobuz", "Major Paid", "Audiophiles, hi-res purchases", "$12.99/mo", "100M+ tracks", 0, "All"),
            ("LiveOne", "Major Paid", "Stories, live content", "Various", "Large catalog", 0, "All"),
            ("SiriusXM Internet Radio", "Major Paid", "Radio + streaming", "Various", "Large catalog", 0, "All"),
            ("Pandora", "Free", "Radio-style streaming", "Free (ads)", "Large catalog", 1, "USA"),
            ("Trebel", "Free", "Free offline listening", "Free (watch ads)", "Large catalog", 1, "All"),
            ("Boomplay", "Free", "Afrobeats, African music", "Free (ads)", "African focus", 1, "Africa, Global"),
            ("JioSaavn", "Free", "Bollywood, Indian music", "Free (ads)", "Indian focus", 1, "India, Global"),
            ("Free Music Archive", "Free", "Royalty-free, Creative Commons", "Free", "Independent", 1, "All"),
            ("Musopen", "Free", "Classical, public domain", "Free", "Classical focus", 1, "All"),
            ("Jamendo", "Free", "Independent artists", "Free", "Independent", 1, "All"),
            ("Idagio", "Free", "Classical music specialist", "Free/Paid", "Classical focus", 1, "All"),
        ]
        cursor.executemany(
            "INSERT INTO streaming_apps (name, category, best_for, price, catalog_size, free_tier, platform) VALUES (?,?,?,?,?,?,?)",
            streaming_apps
        )
        
        # ── DJ SOFTWARE ──
        dj_software = [
            ("Rekordbox", "Mac/Windows", "Music prep, CDJ integration, cloud sync", "Paid", "Pro DJ"),
            ("Serato DJ Pro", "Mac/Windows", "Industry standard, DVS, streaming", "Paid", "Pro DJ"),
            ("Serato DJ Lite", "Mac/Windows", "Beginner-friendly, sync feature", "Free", "Pro DJ"),
            ("VirtualDJ", "Mac/Windows", "Real-time stems, video mixing, 300+ controllers", "Free/Paid", "Pro DJ"),
            ("Traktor Pro", "Mac/Windows", "Advanced effects, remix decks", "Paid", "Pro DJ"),
            ("djay Pro AI", "iOS/Mac/Windows", "AI features, DVS, Apple ecosystem", "$49.99/mo", "Pro DJ"),
            ("Engine DJ", "Standalone hardware", "Laptop-free performance, onboard stems", "Free", "Pro DJ"),
            ("Mixxx", "Mac/Windows/Linux", "Open-source, free, controller support", "Free", "Pro DJ"),
            ("Offtrack", "iOS/Android/Mac", "AI automix, Spotify/Apple Music/TIDAL integration", "Free", "Mobile DJ"),
            ("Cross DJ", "iOS/Android", "BPM detection, looping, MIDI support", "Free/Paid", "Mobile DJ"),
            ("DJ Studio 5", "Android", "Virtual turntables, mixer, sampler", "Free", "Mobile DJ"),
            ("Serato Studio", "Mac/Windows", "Beat-making, remixing, stem separation", "$9.99/mo", "Production"),
            ("Ableton Live", "Mac/Windows", "Full DAW, live performance, warping", "$99-$749", "Production"),
            ("FL Studio", "Mac/Windows", "Beat production, EDM, hip-hop", "Various", "Production"),
            ("Logic Pro", "Mac", "Professional production, Apple ecosystem", "Paid", "Production"),
            ("GarageBand", "iOS/Mac", "Beginner-friendly, free", "Free", "Production"),
        ]
        cursor.executemany(
            "INSERT INTO dj_software (name, platform, features, price, category) VALUES (?,?,?,?,?)",
            dj_software
        )
        
        # ── FESTIVALS & EVENTS ──
        festivals = [
            ("Tomorrowland Thailand", "Pattaya, Thailand", "Dec 11-13, 2026", "Massive lineup, 6 stages", "EDM"),
            ("Creamfields", "Daresbury, UK", "Summer 2026", "Calvin Harris, Underworld, Sonny Fodera", "EDM/House"),
            ("UnKonscious Festival", "Pattaya, Thailand", "Jan 29 - Feb 1, 2026", "Mark Sherry, The Thrillseekers, Allen Watts", "Trance"),
            ("Day Zero Bali", "Uluwatu, Bali", "Apr 17, 2026", "Acid Pauli, DJ Bonobo, Jamie Jones", "House/Techno"),
            ("Equation Festival", "Mai Chau, Vietnam", "Apr 3-6, 2026", "Underground techno/house lineup", "Techno/House"),
            ("Beatforest Festival", "Khao Yai, Thailand", "Jan 30, 2026", "Barker, Koichi Shimizu, U.R.TRAX", "Electronic"),
            ("Wonderfruit", "Pattaya, Thailand", "Dec 2026", "A Guy Called Gerald, AAGUU", "Electronic/Experimental"),
            ("Lollapalooza India", "Mumbai, India", "Jan 24-25, 2026", "Linkin Park, Playboi Carti, YUNGBLUD", "Multi-genre"),
            ("DMC World DJ Championship", "Tokyo, Japan", "Oct 10-12, 2026", "C2C, Berywam, DJ Fly, Scratch Perverts", "Turntablism"),
            ("Ibiza Residency Season", "Ibiza, Spain", "May - Oct 2026", "Calvin Harris, David Guetta, Martin Garrix, Carl Cox", "House/Techno/EDM"),
            ("The Warehouse Project", "Manchester, UK", "Seasonal", "Solomun, Hannah Laing, etc.", "House/Techno"),
        ]
        cursor.executemany(
            "INSERT INTO festivals_events (name, location, dates, headliners, genre) VALUES (?,?,?,?,?)",
            festivals
        )
        
        # ── THEATER STREAMING ──
        theater = [
            ("BroadwayHD", "Broadway shows, musicals", "USA/Global"),
            ("National Theatre at Home", "UK theater productions", "UK/Global"),
            ("Met Opera on Demand", "Opera performances", "Global"),
            ("Digital Theatre", "Theater from around the world", "Global"),
            ("Marquee TV", "Dance, theater, opera", "Global"),
        ]
        cursor.executemany(
            "INSERT INTO theater_streaming (name, content_type, region) VALUES (?,?,?)",
            theater
        )
        
        conn.commit()
        conn.close()
        print("[DataStore] Database seeded with all music/DJ data.")
    
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
    
    def get_dj_software(self, category=None, platform=None):
        query = "SELECT * FROM dj_software WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if platform:
            query += " AND platform LIKE ?"
            params.append(f"%{platform}%")
        return self._query(query, params)
    
    def get_festivals(self, genre=None, location=None):
        query = "SELECT * FROM festivals_events WHERE 1=1"
        params = []
        if genre:
            query += " AND genre LIKE ?"
            params.append(f"%{genre}%")
        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
        return self._query(query, params)
    
    def get_theater_streaming(self, region=None):
        query = "SELECT * FROM theater_streaming WHERE 1=1"
        params = []
        if region:
            query += " AND region LIKE ?"
            params.append(f"%{region}%")
        return self._query(query, params)
    
    def get_all(self):
        return {
            "dj_groups": self.get_dj_groups(),
            "streaming_apps": self.get_streaming_apps(),
            "dj_software": self.get_dj_software(),
            "festivals_events": self.get_festivals(),
            "theater_streaming": self.get_theater_streaming(),
        }
    
    def search(self, term):
        tables = ["dj_groups", "streaming_apps", "dj_software", "festivals_events", "theater_streaming"]
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
    
    # ── USER & PAYMENT SYSTEM ──
    
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
        # Check active subscription
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
    
    def create_payment(self, tx_ref, device_id, amount, method="mpesa"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (tx_ref, device_id, amount, method) VALUES (?,?,?,?)",
            (tx_ref, device_id, amount, method)
        )
        conn.commit()
        conn.close()
    
    def verify_payment(self, tx_ref):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE payments SET status = 'success', verified = 1 WHERE tx_ref = ?", (tx_ref,))
            conn.commit()
        conn.close()
        return row is not None
    
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
# WEB DATA PULLER
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
        genres = []
        try:
            url = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=popular+music+genres+2026&format=json&origin=*"
            req = urllib.request.Request(url, headers={'User-Agent': 'DJDropFactory/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                genres = [item['title'].replace("music", "").replace("genre", "").strip() 
                         for item in data.get('query', {}).get('search', [])[:6]]
        except Exception as e:
            print(f"[WebPull] Genre fetch failed: {e}")
        if not genres:
            genres = ["Amapiano", "Afrobeat", "Dancehall", "Trap", "Drill", "Boom Bap"]
        else:
            core = ["Amapiano", "Afrobeat", "Dancehall", "Trap", "Club Banger", "Radio"]
            for c in core:
                if c.lower() not in [g.lower() for g in genres]:
                    genres.append(c)
            genres = genres[:8]
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
        result = {"city": city_clean, "vibe": "vibing", "temperature": 25, "weather_code": 0}
        try:
            encoded = urllib.parse.quote(city_clean)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1"
            req = urllib.request.Request(geo_url, headers={'User-Agent': 'DJDropFactory/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                geo = json.loads(resp.read())
                if geo.get('results'):
                    lat = geo['results'][0]['latitude']
                    lon = geo['results'][0]['longitude']
                    name = geo['results'][0].get('name', city_clean)
                    w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                    w_req = urllib.request.Request(w_url, headers={'User-Agent': 'DJDropFactory/5.0'})
                    with urllib.request.urlopen(w_req, timeout=5) as w_resp:
                        w_data = json.loads(w_resp.read())
                        weather = w_data.get('current_weather', {})
                        temp = weather.get('temperature', 25)
                        code = weather.get('weathercode', 0)
                        if temp > 32: vibe = "scorching hot"
                        elif temp > 26: vibe = "tropical heat"
                        elif temp > 20: vibe = "warm"
                        elif temp > 10: vibe = "cool breeze"
                        else: vibe = "freezing cold"
                        mood = "hype"
                        if code in [0, 1]: mood = "festival"
                        elif code in [51, 53, 55, 61, 63, 65]: mood = "dark"
                        elif code in [71, 73, 75, 85, 86]: mood = "aggressive"
                        result = {"city": name, "temperature": temp, "vibe": vibe, "weather_code": code, "suggested_mood": mood}
        except Exception as e:
            print(f"[WebPull] City vibe failed: {e}")
        cls._set_cached(f'city_{city_clean.lower()}', result)
        return result
    
    @classmethod
    def fetch_dj_name_suggestions(cls, style=""):
        cached = cls._get_cached(f'names_{style.lower().strip()}')
        if cached:
            return cached
        bases = ["Blaze", "Phantom", "Vortex", "Echo", "Pulse", "Nova", "Cipher", "Kinetic", "Solar", "Lunar"]
        suffixes = ["Beats", "Sound", "Wave", "Drop", "Bass", "Fire", "Storm", "Unit", "System", "Cartel"]
        if style:
            s = style.lower()
            if any(x in s for x in ["afro", "piano", "naija", "lagos"]):
                bases = ["Afro", "Yanos", "Zulu", "Naija", "Kente", "Lagos", "Accra", "Savanna", "Jozi", "Cape"]
                suffixes = ["Vibes", "Groove", "Rhythm", "Wave", "Drum", "Log", "Culture", "Pressure", "Session", "Settings"]
            elif any(x in s for x in ["dance", "hall", "riddim", "bashment", "yard"]):
                bases = ["Riddim", "Bashment", "Yard", "Sound", "Selectah", "Dub", "Reggae", "Jungle", "Kingston", "Trench"]
                suffixes = ["Madness", "Reload", "PullUp", "System", "Clash", "War", "Ting", "Energy", "Fire", "Vibes"]
            elif any(x in s for x in ["trap", "dark", "808", "hiphop", "rap"]):
                bases = ["Dark", "Ghost", "Shadow", "Trap", "Lean", "Drip", "Mumble", "808", "Phantom", "Grave"]
                suffixes = ["Mob", "Gang", "Cartel", "Mafia", "Clique", "Wave", "Squad", "Unit", "Boyz", "World"]
            elif any(x in s for x in ["radio", "air", "broadcast", "fm"]):
                bases = ["Air", "Wave", "Freq", "Signal", "Broadcast", "Mic", "Studio", "FM", "AM", "Satellite"]
                suffixes = ["Radio", "Network", "Station", "Live", "Stream", "Cast", "Show", "Connect", "Link", "Airwaves"]
        suggestions = []
        for _ in range(12):
            name = f"DJ {random.choice(bases)} {random.choice(suffixes)}"
            if name not in suggestions:
                suggestions.append(name)
        cls._set_cached(f'names_{style.lower().strip()}', suggestions)
        return suggestions
    
    @classmethod
    def fetch_quote_of_the_day(cls):
        cached = cls._get_cached('quote')
        if cached:
            return cached
        quotes = [
            "The best DJs don't just play tracks, they create moments.",
            "Music is the universal language of mankind.",
            "Turn up the volume and let the bass heal your soul.",
            "Amapiano to the world, one log drum at a time.",
            "Good DJs mix tracks. Great DJs mix emotions."
        ]
        try:
            url = "https://zenquotes.io/api/random"
            req = urllib.request.Request(url, headers={'User-Agent': 'DJDropFactory/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read())
                if isinstance(data, list) and len(data) > 0:
                    q = data[0].get('q', '')
                    a = data[0].get('a', '')
                    if q:
                        quotes = [f"{q} — {a}"]
        except Exception as e:
            print(f"[WebPull] Quote fetch failed: {e}")
        cls._set_cached('quote', quotes)
        return quotes


# ============================================================
# STRING WIZARD
# ============================================================

class StringWizard:
    TEMPLATES = {
        "intro": "{opener} {dj_name} is {verb}{city_part}. {energy_line}{exclaim} {closer}",
        "hype": "{opener} {display_name} in full effect{exclaim} {city_part} {closer}",
        "promo": "{dj_name} invites you{city_part}{event_part}. Get ready for {promo_word}. Pull up live and experience the energy!",
        "sweeper": "{display_name}{city_part}. {energy_line}. {tagline}",
        "radio_id": "You're locked in with {display_name}{city_part}{station_part}{slogan_part}. Premium radio sound.",
        "producer_tag": "{opener} {display_name}. Premium sound design only.",
    }
    
    HASHTAGS = {
        "amapiano": ["#Amapiano", "#Yanos", "#LogDrum", "#PrivateSchool", "#PianoVibes"],
        "dancehall": ["#Dancehall", "#Riddim", "#Soundclash", "#Bashment", "#PullUp"],
        "trap": ["#Trap", "#808", "#HipHop", "#Dark", "#Bass"],
        "afrobeat": ["#Afrobeat", "#Afro", "#Vibes", "#Wave", "#Global"],
        "club_banger": ["#Club", "#Banger", "#Party", "#MainEvent", "#Nightlife"],
        "radio": ["#Radio", "#OnAir", "#Broadcast", "#Live", "#Frequency"],
    }
    
    @classmethod
    def process_template(cls, template_key, variables):
        template = cls.TEMPLATES.get(template_key, "{dj_name} on the mic!")
        result = template
        for key, value in variables.items():
            placeholder = "{" + str(key) + "}"
            result = result.replace(placeholder, str(value) if value is not None else "")
        result = re.sub(r'\s+', ' ', result).strip()
        return result
    
    @classmethod
    def smart_capitalize(cls, text):
        words = text.split()
        result = []
        for word in words:
            w = word.strip()
            if not w:
                continue
            if w.upper() in ["DJ", "MC", "DJ'S", "MC'S", "NYC", "LA", "UK", "US", "NG", "SA"]:
                result.append(w.upper())
            elif w.isupper() and len(w) <= 3:
                result.append(w.upper())
            else:
                result.append(w.capitalize() if w == w.lower() else w)
        return " ".join(result)
    
    @classmethod
    def generate_slug(cls, text):
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_]+', '-', text)
        text = re.sub(r'-+', '-', text)
        return text[:60].strip('-')
    
    @classmethod
    def add_hashtags(cls, text, genre):
        tags = cls.HASHTAGS.get(genre.lower().replace(" ", "_"), ["#DJDrop", "#Fire"])
        existing = set(re.findall(r'#\w+', text.lower()))
        new_tags = [t for t in tags if t.lower().lstrip('#') not in existing]
        if new_tags:
            return text + " " + " ".join(new_tags)
        return text
    
    @classmethod
    def stutter_pattern(cls, text, pattern="classic"):
        if not text or not text.strip():
            return text
        words = text.strip().split()
        if not words:
            return text
        first_word = words[0]
        if pattern == "classic":
            c = first_word[0].upper()
            return f"{c}-{c}-{c}-{text}"
        elif pattern == "build_up":
            c = first_word[0].upper()
            return f"{c}... {c}... {first_word}... {text}"
        elif pattern == "echo":
            return f"{text}... {text}..."
        elif pattern == "repeat":
            return f"{text}! {text}!"
        elif pattern == "underscore":
            return text.lower().replace(" ", "_")
        return text
    
    @classmethod
    def analyze_sentiment(cls, text):
        t = text.lower()
        hype_words = ["fire", "madness", "shutdown", "danger", "explosive", "banger", "heavy", "destruction", "chaos", "wall-to-wall", "full shutdown"]
        chill_words = ["smooth", "vibes", "relax", "steady", "calm", "mellow", "soft", "breathe", "culture", "settings", "only"]
        hype_score = sum(1 for w in hype_words if w in t)
        chill_score = sum(1 for w in chill_words if w in t)
        if hype_score > chill_score:
            return "hype", hype_score
        elif chill_score > hype_score:
            return "chill", chill_score
        return "neutral", max(hype_score, chill_score)
    
    @classmethod
    def format_for_platform(cls, text, platform="generic"):
        if platform == "twitter":
            return text[:280] if len(text) > 280 else text
        elif platform == "instagram":
            return text[:2200] if len(text) > 2200 else text
        elif platform == "tiktok":
            return text[:300] if len(text) > 300 else text
        elif platform == "whatsapp":
            return text[:700] if len(text) > 700 else text
        return text
    
    @classmethod
    def extract_keywords(cls, text):
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "and", "but", "or", "yet", "so", "if", "because", "although", "though", "while", "where", "when", "that", "which", "who", "whom", "whose", "what", "this", "these", "those", "i", "me", "my", "myself", "we", "our", "you", "your", "he", "him", "his", "she", "her", "it", "its", "they", "them", "their", "dj", "mc"}
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in stopwords]
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:10]
    
    @classmethod
    def auto_punctuate(cls, text):
        text = text.strip()
        if not text:
            return text
        text = text[0].upper() + text[1:]
        if text[-1] not in ".!?":
            text += "!"
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'([.!?]\s+)', text)
        result = ""
        for i, part in enumerate(sentences):
            if i > 0 and part and part[0] == ' ' and len(part) > 1:
                result += ' ' + part[1].upper() + part[2:]
            else:
                result += part
        return result


# ============================================================
# AI TRAINING ENGINE
# ============================================================

class AITrainingEngine:
    TRAINING_FILE = TRAINING_DIR / "trained_examples.json"
    
    @classmethod
    def save_training(cls, example_text, genre, style_notes):
        examples = []
        if cls.TRAINING_FILE.exists():
            with open(cls.TRAINING_FILE, 'r') as f:
                examples = json.load(f)
        example = {
            "text": example_text,
            "genre": genre,
            "style_notes": style_notes,
            "timestamp": datetime.now().isoformat(),
            "length": len(example_text),
            "exclamation_count": example_text.count('!'),
            "uppercase_ratio": sum(1 for c in example_text if c.isupper()) / len(example_text) if example_text else 0
        }
        examples.append(example)
        with open(cls.TRAINING_FILE, 'w') as f:
            json.dump(examples, f, indent=2)
        return len(examples)
    
    @classmethod
    def load_training(cls):
        if not cls.TRAINING_FILE.exists():
            return []
        with open(cls.TRAINING_FILE, 'r') as f:
            return json.load(f)
    
    @classmethod
    def analyze_style(cls, text):
        return {
            "length": len(text),
            "words": text.split(),
            "has_stutter": bool(re.search(r'(\w)\.\.\.|\1-\1', text)),
            "energy_markers": text.count('!') + text.count('?'),
            "has_location": bool(re.search(r'\bin\b|\bfrom\b', text.lower())),
            "has_callout": bool(re.search(r'stand up|make some noise|hands up', text.lower())),
            "repeated_words": [word for word in set(text.split()) if text.lower().split().count(word.lower()) > 1]
        }
    
    @classmethod
    def mimic_drop(cls, example_text, dj_name, genre="club_banger", energy=8):
        style = cls.analyze_style(example_text)
        has_opener = bool(re.match(r'^[^.!?]+[!.,]', example_text))
        has_closer = bool(re.search(r'[!.,]\s*[^.!?]+[!.,]?$', example_text))
        parts = []
        if style["has_callout"]:
            openers = ["Yo!", "Listen up!", "Check it!", "Ayo!"]
            parts.append(random.choice(openers))
        if style["has_stutter"] or random.random() < 0.5:
            first_letter = dj_name[0] if dj_name else "D"
            stutter_patterns = [f"{first_letter}-{first_letter}-{dj_name}", f"{first_letter}... {first_letter}... {dj_name}", f"{dj_name}! {dj_name}!", dj_name]
            dj_display = random.choice(stutter_patterns)
        else:
            dj_display = dj_name
        parts.append(dj_display)
        energy_phrases = {
            "amapiano": ["log drum pressure", "piano vibes only", "strictly smooth", "private school settings"],
            "dancehall": ["sound system active", "riddim pressure", "madness only", "pull up selectah"],
            "radio": ["you're locked in", "live on air", "premium broadcast", "stay tuned"],
            "club_banger": ["main event", "full shutdown", "hands up", "wall-to-wall energy"],
            "afrobeat": ["afro bounce", "global rhythm", "sweet pressure", "wave after wave"],
            "trap": ["808 warning", "bassline alert", "heavyweight", "dark energy"]
        }
        genre_key = genre.lower().replace(" ", "_").strip()
        phrases = energy_phrases.get(genre_key, energy_phrases["club_banger"])
        if energy >= 8:
            parts.append(random.choice(phrases) + "!!!")
        elif energy >= 5:
            parts.append(random.choice(phrases) + "!")
        else:
            parts.append(random.choice(phrases))
        if style["has_location"]:
            locations = ["in the building", "worldwide", "to the world", "in full effect"]
            parts.append(random.choice(locations))
        closers = ["Let's go!", "Make some noise!", "We outside!", "No sleep tonight!", "Take it higher!"]
        if has_closer or energy >= 7:
            parts.append(random.choice(closers))
        result = " ".join(parts)
        result = re.sub(r'\s+', ' ', result).strip()
        return result
    
    @classmethod
    def generate_from_training(cls, dj_name, genre, energy, example_text=None):
        if example_text and example_text.strip():
            cls.save_training(example_text, genre, "user_provided")
            return cls.mimic_drop(example_text, dj_name, genre, energy)
        examples = cls.load_training()
        if examples:
            genre_examples = [e for e in examples if e.get("genre") == genre]
            if genre_examples:
                best = max(genre_examples, key=lambda x: x.get("exclamation_count", 0) * energy / 10)
                return cls.mimic_drop(best["text"], dj_name, genre, energy)
        return None


# ============================================================
# SCRIPT AI ENGINE
# ============================================================

class PremiumDJScriptAI:
    GENRE_DATA = {
        "amapiano": {
            "openers": ["Lalela!", "Yanos to the world!", "Piano session loading!", "Private school vibes!", "Log drum pressure!"],
            "verbs": ["locking the groove", "running the vibe", "controlling the session", "bringing the piano heat", "shaking the nightlife", "setting the vibe"],
            "energy_lines": ["strictly smooth pressure", "nothing but elite groove", "luxury nightlife settings", "deep log drum madness", "all night amapiano pressure", "piano culture in motion"],
            "closers": ["let the bassline breathe", "vibes only", "you know the code", "strictly for the culture", "we move"],
            "promo_words": ["exclusive nightlife experience", "premium amapiano atmosphere", "non-stop groove", "elite party energy"]
        },
        "dancehall": {
            "openers": ["Brap brap!", "Pull up selectah!", "Forward!", "Mad ting!", "Soundbwoy warning!"],
            "verbs": ["shelling the riddim", "mashing up the dance", "running the sound", "tearing down the arena", "bringing dangerous pressure", "murdering the riddim"],
            "energy_lines": ["danger in full effect", "soundclash settings only", "pure dancehall fire", "reload after reload", "badman riddim pressure", "sound system warfare"],
            "closers": ["pull it up!", "run the tune!", "dangerous settings!", "madness only!", "soundbwoy fi know!", "forward di ting!"],
            "promo_words": ["heavy dancehall energy", "sound system pressure", "dangerous live performance", "non-stop riddim action"]
        },
        "radio": {
            "openers": ["You're locked in.", "Live on air.", "Now broadcasting.", "Stay tuned.", "Across the airwaves."],
            "verbs": ["keeping it locked", "taking over the airwaves", "bringing premium sound", "delivering the hottest selection", "holding down the frequency"],
            "energy_lines": ["fresh and exclusive", "premium broadcast energy", "the sound of the city", "top-tier radio experience", "your official soundtrack"],
            "closers": ["stay connected", "keep it locked", "more heat on the way", "premium sound only", "don't touch that dial"],
            "promo_words": ["live radio experience", "exclusive station branding", "premium station identity", "broadcast-ready sound"]
        },
        "club_banger": {
            "openers": ["Hands up!", "Main event settings!", "Turn it up!", "Global shutdown!", "Brace yourself!"],
            "verbs": ["taking over the decks", "breaking the club", "running the main event", "unleashing chaos", "lighting up the crowd", "smashing the dancefloor"],
            "energy_lines": ["festival-level pressure", "wall-to-wall energy", "club destruction mode", "full arena madness", "high-voltage nightlife energy"],
            "closers": ["let's go!", "make some noise!", "we outside!", "no sleep tonight!", "take it higher!"],
            "promo_words": ["explosive nightlife energy", "main stage pressure", "unmatched club experience", "full-throttle entertainment"]
        },
        "afrobeat": {
            "openers": ["Afro vibes!", "Worldwide groove!", "Afrobeats loading!", "Big rhythm energy!", "Wave after wave!"],
            "verbs": ["bringing the afro heat", "running the groove", "setting the summer mood", "moving the culture", "lifting the party"],
            "energy_lines": ["sweet afro pressure", "melodic nightlife energy", "global afro rhythm", "steady groove and vibes", "afro bounce all night"],
            "closers": ["vibes non-stop!", "feel the rhythm!", "steady now!", "we outside!", "all love and energy!"],
            "promo_words": ["premium afrobeat experience", "melodic party energy", "feel-good nightlife pressure", "afro groove all night"]
        },
        "trap": {
            "openers": ["808 warning!", "Bassline alert!", "Turn the system up!", "Pressure mode!", "Heavyweight entry!"],
            "verbs": ["dropping heavy pressure", "bringing the bassline warfare", "setting the room on fire", "running the late-night energy", "taking over the trap wave"],
            "energy_lines": ["808 pressure", "dark club energy", "sub-heavy madness", "late-night danger", "bassline demolition"],
            "closers": ["let it knock!", "shake the walls!", "run it back!", "take it louder!", "bassline only!"],
            "promo_words": ["sub-heavy live experience", "hard-hitting trap energy", "nightlife pressure", "heavyweight bass performance"]
        }
    }

    @classmethod
    def clean_name(cls, dj_name):
        return re.sub(r"\s+", " ", (dj_name or "").strip()) or "DJ Beshi"

    @classmethod
    def normalize_for_stutter(cls, txt):
        txt = txt.strip()
        txt = re.sub(r"\s+", " ", txt)
        return txt

    @classmethod
    def apply_stutter(cls, dj_name, style="classic", user_stutter=""):
        name = cls.clean_name(dj_name)
        words = name.split()
        if not words:
            return name
        if user_stutter.strip():
            return cls.normalize_for_stutter(user_stutter)
        first_word = words[0]
        tail = words[-1]
        if style == "none":
            return name
        if style == "classic":
            c = first_word[0]
            return f"{c}-{c}-{c}-{name}"
        if style == "build_up":
            c = first_word[0]
            return f"{c}... {c}... {first_word}... {name}"
        if style == "echo_name":
            return f"{tail}... {tail}... {name}"
        if style == "hype_repeat":
            return f"{name}! {name}!"
        if style == "underscore":
            compact = name.lower().replace(" ", "_")
            return compact
        return name

    @classmethod
    def energy_profile(cls, energy):
        if energy <= 3:
            return {"exclaim": "", "extra": "steady vibes only."}
        elif energy <= 6:
            return {"exclaim": "!", "extra": "locked and loaded."}
        elif energy <= 8:
            return {"exclaim": "!!", "extra": "full pressure mode!!"}
        return {"exclaim": "!!!", "extra": "shutdown mode."}

    @classmethod
    def choose_stutter_style(cls, genre, use_stutter):
        if not use_stutter:
            return "none"
        mapping = {
            "dancehall": "classic",
            "club_banger": "build_up",
            "amapiano": "echo_name",
            "radio": "none",
            "afrobeat": "echo_name",
            "trap": "underscore",
        }
        return mapping.get(genre, "classic")

    @classmethod
    def score_line(cls, text, genre, energy, drop_type):
        score = 0
        t = text.lower()
        if 40 <= len(text) <= 150:
            score += 3
        if "!" in text:
            score += 2
        keywords = {
            "amapiano": ["piano", "groove", "log drum", "culture", "vibes"],
            "dancehall": ["riddim", "sound", "selectah", "danger", "reload"],
            "radio": ["locked", "airwaves", "frequency", "broadcast", "station"],
            "club_banger": ["club", "crowd", "noise", "shutdown", "main event"],
            "afrobeat": ["afro", "groove", "rhythm", "vibes", "wave"],
            "trap": ["808", "bass", "pressure", "heavy", "trap"]
        }
        for kw in keywords.get(genre, []):
            if kw in t:
                score += 2
        if drop_type == "promo" and any(x in t for x in ["experience", "live", "event", "pull up"]):
            score += 3
        if drop_type in ("producer_tag", "radio_id") and len(text) <= 110:
            score += 2
        if energy >= 8 and any(x in t for x in ["shutdown", "danger", "reload", "madness"]):
            score += 3
        return score

    @classmethod
    def build_intro(cls, display_name, data, mood, city, energy):
        opener = random.choice(data["openers"])
        verb = random.choice(data["verbs"])
        energy_line = random.choice(data["energy_lines"])
        closer = random.choice(data["closers"])
        p = cls.energy_profile(energy)
        city_part = f" in {city}" if city else ""
        opt1 = f"{opener} {display_name} is {verb}{city_part}. {energy_line.capitalize()}{p['exclaim']} {closer.capitalize()}"
        opt2 = f"{opener} Locked in with {display_name}{city_part}. {energy_line.capitalize()}{p['exclaim']} {p['extra']}"
        options = [opt1, opt2]
        if mood == "luxury":
            options.append(f"{opener} Premium settings only. {display_name}{city_part} is {verb}. {energy_line.capitalize()}.")
        elif mood == "aggressive":
            options.append(f"{opener} {display_name}{city_part} is here to cause major damage. {p['extra']}")
        elif mood == "dark":
            options.append(f"{opener} {display_name}{city_part}. Dark pressure. {energy_line.capitalize()}{p['exclaim']}")
        elif mood == "festival":
            options.append(f"{opener} {display_name}{city_part}. Main-stage pressure. {energy_line.capitalize()}{p['exclaim']}")
        return random.choice(options)

    @classmethod
    def build_sweeper(cls, display_name, data, city, genre):
        energy_line = random.choice(data["energy_lines"])
        city_part = f" from {city}" if city else ""
        if genre == "dancehall":
            return f"{display_name}{city_part}. Sound system active. {energy_line.capitalize()}!"
        elif genre == "amapiano":
            return f"{display_name}{city_part}. {energy_line.capitalize()}. Piano vibes only."
        elif genre == "radio":
            return f"This is {display_name}{city_part}. {energy_line.capitalize()}. Stay locked."
        elif genre == "afrobeat":
            return f"{display_name}{city_part}. {energy_line.capitalize()}. Afro vibes only."
        elif genre == "trap":
            return f"{display_name}{city_part}. {energy_line.capitalize()}. Bassline pressure."
        return f"{display_name}{city_part}. {energy_line.capitalize()}. Main event pressure!"

    @classmethod
    def build_hype(cls, display_name, data, city, energy):
        opener = random.choice(data["openers"])
        closer = random.choice(data["closers"])
        p = cls.energy_profile(energy)
        city_part = f" {city} stand up!" if city else ""
        return f"{opener} {display_name} in full effect{p['exclaim']} {city_part} {closer.capitalize()} {p['extra']}"

    @classmethod
    def build_promo(cls, display_name, data, city, event_name):
        promo_word = random.choice(data["promo_words"])
        city_part = f" in {city}" if city else ""
        event_part = f" for {event_name}" if event_name else ""
        return f"{display_name} invites you{city_part}{event_part}. Get ready for {promo_word}. Pull up live and experience the energy!"

    @classmethod
    def build_producer_tag(cls, display_name, data):
        opener = random.choice(data["openers"])
        return f"{opener} {display_name}. Premium sound design only."

    @classmethod
    def build_radio_id(cls, display_name, city="", station_name="", slogan=""):
        city_part = f" in {city}" if city else ""
        station_part = f" on {station_name}" if station_name else ""
        slogan_part = f" -- {slogan}" if slogan else ""
        return f"You're locked in with {display_name}{city_part}{station_part}{slogan_part}. Premium radio sound."

    @classmethod
    def build_crowd_call(cls, display_name, city="", crew_tag=""):
        city_part = f" {city}" if city else ""
        crew_part = f" {crew_tag}" if crew_tag else ""
        return f"{display_name} in the building!{city_part} make some noise!{crew_part}"

    @classmethod
    def compose_one(cls, dj_name, genre, drop_type, mood, energy, use_stutter,
                    city, event_name, user_stutter, station_name="", slogan="", crew_tag=""):
        genre_key = genre.lower().replace(" ", "_").strip()
        if genre_key not in cls.GENRE_DATA:
            genre_key = "club_banger"
        data = cls.GENRE_DATA[genre_key]
        stutter_style = cls.choose_stutter_style(genre_key, use_stutter)
        display_name = cls.apply_stutter(dj_name, stutter_style, user_stutter)
        if drop_type == "intro":
            return cls.build_intro(display_name, data, mood, city, energy)
        if drop_type == "sweeper":
            return cls.build_sweeper(display_name, data, city, genre_key)
        if drop_type == "hype":
            return cls.build_hype(display_name, data, city, energy)
        if drop_type == "promo":
            return cls.build_promo(display_name, data, city, event_name)
        if drop_type == "producer_tag":
            return cls.build_producer_tag(display_name, data)
        if drop_type == "radio_id":
            return cls.build_radio_id(display_name, city, station_name, slogan)
        if drop_type == "crowd_call":
            return cls.build_crowd_call(display_name, city, crew_tag)
        return cls.build_intro(display_name, data, mood, city, energy)

    @classmethod
    def generate(cls, dj_name, genre, use_stutter, drop_type="intro", mood="hype",
                 energy=8, city="", event_name="", user_stutter="", station_name="",
                 slogan="", crew_tag="", count=5):
        outputs = []
        for _ in range(count):
            line = cls.compose_one(
                dj_name=dj_name, genre=genre, drop_type=drop_type, mood=mood,
                energy=energy, use_stutter=use_stutter, city=city,
                event_name=event_name, user_stutter=user_stutter,
                station_name=station_name, slogan=slogan, crew_tag=crew_tag
            )
            genre_key = genre.lower().replace(" ", "_").strip()
            if genre_key not in cls.GENRE_DATA:
                genre_key = "club_banger"
            score = cls.score_line(line, genre_key, energy, drop_type)
            outputs.append({"text": line, "score": score})
        dedup = {}
        for item in outputs:
            txt = item["text"]
            if txt not in dedup or item["score"] > dedup[txt]["score"]:
                dedup[txt] = item
        final = list(dedup.values())
        final.sort(key=lambda x: x["score"], reverse=True)
        return final


# ============================================================
# AUDIO / FX ENGINE - LOUD VERSION (with louder amapiano)
# ============================================================

class PremiumAudioStudio:
    @classmethod
    def safe_stereo(cls, mlev):
        mlev = max(0.015625, min(64.0, float(mlev)))
        return f"stereotools=mlev={mlev:.6f}"

    @classmethod
    def get_fx_profile(cls, style, energy):
        style = style.lower().strip()
        profile = {
            "highpass": 100,
            "compressor": "acompressor=threshold=-14dB:ratio=6:attack=5:release=100",
            "presence_eq": "equalizer=f=3200:width_type=q:width=1.1:g=4.0",
            "deesser_eq": "equalizer=f=6500:width_type=q:width=1.2:g=-1.0",
            "echo": "",
            "slap": "",
            "space": "",
            "phaser": "",
            "stereo": "",
            "loudness": "loudnorm=I=-10:TP=-0.5:LRA=5",
            "limiter": "alimiter=limit=0.95:level=1",
            "duck_threshold": "0.02",
            "duck_release": "200",
            "bg_gain": 0.20,
            "vocal_gain": 1.2
        }
        if style == "amapiano":
            profile.update({
                "highpass": 90,
                "presence_eq": "equalizer=f=2800:width_type=q:width=1.0:g=3.5",
                "echo": "aecho=0.85:0.60:220|440:0.25|0.15",
                "space": "aecho=0.80:0.50:700|900:0.12|0.08",
                "phaser": "aphaser=speed=0.25:decay=0.40",
                "stereo": cls.safe_stereo(0.03),
                # ** LOUDER: vocal gain up, loudness target up **
                "vocal_gain": 1.5,
                "loudness": "loudnorm=I=-7:TP=-0.5:LRA=5",
                "duck_threshold": "0.025",
                "duck_release": "400",
                "bg_gain": 0.22,
                # also boost the limiter slightly
                "limiter": "alimiter=limit=0.95:level=1"
            })
            if energy >= 8:
                profile["space"] = "aecho=0.82:0.55:650|850:0.16|0.10"
                profile["phaser"] = "aphaser=speed=0.30:decay=0.45"
        elif style == "dancehall":
            profile.update({
                "highpass": 105,
                "presence_eq": "equalizer=f=3500:width_type=q:width=1.0:g=5.0",
                "slap": "aecho=0.88:0.60:110:0.22",
                "echo": "aecho=0.82:0.55:220:0.12",
                "stereo": cls.safe_stereo(0.03),
                "duck_threshold": "0.03",
                "duck_release": "150",
                "bg_gain": 0.20,
                "vocal_gain": 1.4
            })
            if energy >= 8:
                profile["echo"] = "aecho=0.85:0.58:180|260:0.16|0.10"
        elif style == "radio":
            profile.update({
                "highpass": 95,
                "compressor": "acompressor=threshold=-16dB:ratio=4:attack=8:release=120",
                "presence_eq": "equalizer=f=3000:width_type=q:width=1.1:g=4.5",
                "slap": "aecho=0.72:0.38:95:0.10",
                "duck_threshold": "0.03",
                "duck_release": "160",
                "bg_gain": 0.15,
                "vocal_gain": 1.2
            })
        elif style == "afrobeat":
            profile.update({
                "highpass": 95,
                "presence_eq": "equalizer=f=3000:width_type=q:width=1.1:g=4.0",
                "echo": "aecho=0.82:0.55:240|360:0.16|0.10",
                "space": "aecho=0.78:0.45:650|820:0.10|0.06",
                "stereo": cls.safe_stereo(0.03),
                "duck_threshold": "0.028",
                "duck_release": "300",
                "bg_gain": 0.22,
                "vocal_gain": 1.3
            })
        elif style == "trap":
            profile.update({
                "highpass": 100,
                "presence_eq": "equalizer=f=3400:width_type=q:width=1.0:g=4.5",
                "echo": "aecho=0.85:0.65:160|320:0.22|0.12",
                "phaser": "aphaser=speed=0.40:decay=0.35",
                "stereo": cls.safe_stereo(0.04),
                "duck_threshold": "0.025",
                "duck_release": "250",
                "bg_gain": 0.20,
                "vocal_gain": 1.35
            })
        else:
            profile.update({
                "highpass": 100,
                "presence_eq": "equalizer=f=3400:width_type=q:width=1.0:g=4.5",
                "echo": "aecho=0.85:0.65:180|360:0.22|0.12",
                "phaser": "aphaser=speed=0.40:decay=0.35",
                "stereo": cls.safe_stereo(0.04),
                "duck_threshold": "0.025",
                "duck_release": "280",
                "bg_gain": 0.21,
                "vocal_gain": 1.4
            })
            if energy >= 8:
                profile["echo"] = "aecho=0.87:0.68:160|320:0.26|0.14"
                profile["phaser"] = "aphaser=speed=0.50:decay=0.40"
        return profile

    @classmethod
    def build_vocal_fx_chain(cls, style, energy, fx_mode="auto"):
        p = cls.get_fx_profile(style, energy)
        chain = []
        chain.append(f"highpass=f={p['highpass']}")
        chain.append(p["compressor"])
        chain.append(p["presence_eq"])
        chain.append(p["deesser_eq"])
        style_key = style.lower().strip()
        if fx_mode == "dry":
            pass
        elif fx_mode == "light":
            if p["slap"]:
                chain.append(p["slap"])
            elif p["echo"]:
                chain.append(p["echo"])
        elif fx_mode == "heavy":
            if p["slap"]: chain.append(p["slap"])
            if p["echo"]: chain.append(p["echo"])
            if p["space"]: chain.append(p["space"])
            if p["phaser"]: chain.append(p["phaser"])
            if p["stereo"]: chain.append(p["stereo"])
        elif fx_mode == "insane":
            if p["slap"]: chain.append(p["slap"])
            if p["echo"]: chain.append(p["echo"])
            if p["space"]: chain.append(p["space"])
            if p["phaser"]: chain.append(p["phaser"])
            if p["stereo"]: chain.append(p["stereo"])
            chain.append("acompressor=threshold=-12dB:ratio=4:attack=2:release=80")
        else:
            if style_key == "radio":
                if p["slap"]: chain.append(p["slap"])
            elif style_key == "dancehall":
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


# --- Web Data Puller Routes ---

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


# --- String Wizard Routes ---

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


# --- Wizard Step Validation ---

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


# --- Live Draft Sync ---

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


# --- Live Preview ---

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


# --- Heartbeat ---

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
        # --- CREDIT CHECK ---
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
        
        # Deduct credit after successful generation
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
# NEW: DISCOVER / DATA API ROUTES
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
# NEW: PAYMENT & CREDITS SYSTEM
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
    """
    Initiates a payment. The merchant phone is NEVER exposed to frontend.
    Returns a transaction reference for the user to complete payment.
    """
    try:
        data = request.get_json()
        device_id = request.headers.get('X-Device-ID', 'anonymous')
        package_id = data.get("package_id", "basic")
        user_phone = data.get("phone", "").strip()  # User's phone for STK push
        method = data.get("method", "mpesa")  # mpesa, card, bank
        
        packages = {
            "basic": {"credits": 5, "price": 50},
            "standard": {"credits": 15, "price": 120},
            "premium": {"credits": 9999, "price": 300, "days": 30},
            "pro": {"credits": 9999, "price": 2500, "days": 365}
        }
        
        pkg = packages.get(package_id)
        if not pkg:
            return jsonify({"success": False, "error": "Invalid package"}), 400
        
        tx_ref = f"DJF-{device_id[:8]}-{int(time.time())}"
        store.create_payment(tx_ref, device_id, pkg['price'], method)
        
        # In production, integrate Flutterwave or Daraja here:
        response = {
            "success": True,
            "tx_ref": tx_ref,
            "status": "pending",
            "amount": pkg['price'],
            "currency": CURRENCY,
            "message": "Payment initiated. Complete the prompt on your phone.",
            "instructions": {
                "mpesa": f"Check your phone ({user_phone}) for the M-Pesa STK push. Enter PIN to complete.",
                "manual": f"Go to M-Pesa → Lipa na M-Pesa → Paybill. Enter Business Number and Account Number shown in your app."
            },
            "verification_url": f"/api/payment/verify",
            "mock_mode": True
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/payment/verify", methods=["POST"])
def api_payment_verify():
    """
    Verifies a payment and credits the user.
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
        
        mock_verify = data.get("mock_verify", False)
        if mock_verify or payment['status'] == 'pending':
            store.verify_payment(tx_ref)
            
            amount = payment['amount']
            if amount <= 50:
                credits, days = 5, 0
            elif amount <= 120:
                credits, days = 15, 0
            elif amount <= 300:
                credits, days = 9999, 30
            else:
                credits, days = 9999, 365
            
            user = store.get_or_create_user(device_id)
            
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
        
        return jsonify({
            "success": True,
            "status": payment['status'],
            "message": "Payment status checked."
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/payment/callback", methods=["POST", "GET"])
def api_payment_callback():
    try:
        data = request.get_json() or request.args.to_dict()
        tx_ref = data.get("txRef") or data.get("tx_ref")
        status = data.get("status", "unknown")
        
        if tx_ref and status == "successful":
            store.verify_payment(tx_ref)
        
        return jsonify({"success": True}), 200
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
        "ffmpeg": FFMPEG_AVAILABLE
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
    print("          Theater Streaming | Payment & Credits System")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
