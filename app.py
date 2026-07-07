import os
import re
import json
import uuid
import shutil
import random
import asyncio
import sqlite3
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Literal, Dict, Any

import edge_tts
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator


# ============================================================
# APP CONFIG
# ============================================================

APP_NAME = "DJ DROP FACTORY PRO v4"
APP_VERSION = "4.0.0"

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "generated_drops"
TRAINING_DIR = BASE_DIR / "training_data"

for d in [DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "dj_drop_factory.db"

MAX_UPLOAD_SIZE_MB = 50
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".aac"}
ALLOWED_BG_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="AI DJ Drop Generator backend with training, voice FX, audio mastering, library, and search."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def has_internet(timeout=3) -> bool:
    try:
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except Exception:
        return False

def check_ffmpeg():
    return shutil.which("ffmpeg")

def check_espeak():
    return shutil.which("espeak-ng") or shutil.which("espeak")

FFMPEG_AVAILABLE = check_ffmpeg() is not None
ESPEAK_AVAILABLE = check_espeak() is not None

def safe_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w\-. ]+", "", name)
    name = re.sub(r"\s+", "_", name)
    return name or "file"

def slugify_text(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "")
    text = re.sub(r"\s+", "_", text.strip())
    return text[:80] if text else "item"

def file_ext(name: str) -> str:
    return Path(name).suffix.lower()

def ensure_upload_extension(filename: str, allowed: set):
    ext = file_ext(filename)
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(list(allowed))}"
        )

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS training_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_name TEXT,
        genre TEXT NOT NULL,
        example_text TEXT NOT NULL,
        style_notes TEXT,
        created_at TEXT NOT NULL,
        length INTEGER DEFAULT 0,
        exclamation_count INTEGER DEFAULT 0,
        uppercase_ratio REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS library_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        script TEXT,
        genre TEXT,
        project_name TEXT,
        dj_name TEXT,
        file_url TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS generation_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_uuid TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        dj_name TEXT,
        genre TEXT,
        drop_type TEXT,
        mood TEXT,
        energy INTEGER,
        script TEXT,
        output_file TEXT,
        tts_engine TEXT,
        mode TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

init_db()


# ============================================================
# ENUMS / CONSTANTS
# ============================================================

GENRES = {"amapiano", "dancehall", "radio", "club_banger", "afrobeat", "trap"}
DROP_TYPES = {"intro", "sweeper", "hype", "promo", "producer_tag", "radio_id", "crowd_call"}
MOODS = {"hype", "luxury", "aggressive", "dark", "festival"}
FX_MODES = {"auto", "dry", "light", "heavy", "insane"}
TRAIN_MODES = {"mimic", "exact"}
GENERATION_MODES = {"ai", "strict"}

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


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================

class TrainRequest(BaseModel):
    example: str = Field(..., min_length=1, max_length=3000)
    dj_name: str = Field(default="DJ Beshi", max_length=120)
    genre: str = Field(default="club_banger")
    energy: int = Field(default=8, ge=1, le=10)
    train_mode: str = Field(default="mimic")

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v):
        if v not in GENRES:
            raise ValueError(f"genre must be one of {sorted(GENRES)}")
        return v

    @field_validator("train_mode")
    @classmethod
    def validate_train_mode(cls, v):
        if v not in TRAIN_MODES:
            raise ValueError(f"train_mode must be one of {sorted(TRAIN_MODES)}")
        return v


class GenerateRequest(BaseModel):
    mode: str = Field(default="ai")
    custom_script: str = Field(default="", max_length=4000)
    training_example: str = Field(default="", max_length=3000)

    dj_name: str = Field(default="DJ Beshi", max_length=120)
    genre: str = Field(default="club_banger")
    voice: str = Field(default="7")
    use_stutter: bool = True
    drop_type: str = Field(default="intro")
    mood: str = Field(default="hype")
    energy: int = Field(default=8, ge=1, le=10)

    city: str = Field(default="", max_length=120)
    event_name: str = Field(default="", max_length=200)
    user_stutter: str = Field(default="", max_length=200)
    station_name: str = Field(default="", max_length=120)
    slogan: str = Field(default="", max_length=200)
    crew_tag: str = Field(default="", max_length=120)

    fx_mode: str = Field(default="auto")
    vocal_gain: float = Field(default=1.0, ge=0.1, le=4.0)
    bg_gain: Optional[float] = Field(default=None, ge=0.01, le=3.0)
    bg_track: str = Field(default="")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        if v not in GENERATION_MODES:
            raise ValueError(f"mode must be one of {sorted(GENERATION_MODES)}")
        return v

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v):
        if v not in GENRES:
            raise ValueError(f"genre must be one of {sorted(GENRES)}")
        return v

    @field_validator("drop_type")
    @classmethod
    def validate_drop_type(cls, v):
        if v not in DROP_TYPES:
            raise ValueError(f"drop_type must be one of {sorted(DROP_TYPES)}")
        return v

    @field_validator("mood")
    @classmethod
    def validate_mood(cls, v):
        if v not in MOODS:
            raise ValueError(f"mood must be one of {sorted(MOODS)}")
        return v

    @field_validator("fx_mode")
    @classmethod
    def validate_fx_mode(cls, v):
        if v not in FX_MODES:
            raise ValueError(f"fx_mode must be one of {sorted(FX_MODES)}")
        return v


class PreviewRequest(BaseModel):
    dj_name: str = Field(default="DJ Beshi", max_length=120)
    genre: str = Field(default="club_banger")
    use_stutter: bool = True
    drop_type: str = Field(default="intro")
    mood: str = Field(default="hype")
    energy: int = Field(default=8, ge=1, le=10)
    city: str = Field(default="", max_length=120)
    event_name: str = Field(default="", max_length=200)
    user_stutter: str = Field(default="", max_length=200)
    station_name: str = Field(default="", max_length=120)
    slogan: str = Field(default="", max_length=200)
    crew_tag: str = Field(default="", max_length=120)

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v):
        if v not in GENRES:
            raise ValueError(f"genre must be one of {sorted(GENRES)}")
        return v

    @field_validator("drop_type")
    @classmethod
    def validate_drop_type(cls, v):
        if v not in DROP_TYPES:
            raise ValueError(f"drop_type must be one of {sorted(DROP_TYPES)}")
        return v

    @field_validator("mood")
    @classmethod
    def validate_mood(cls, v):
        if v not in MOODS:
            raise ValueError(f"mood must be one of {sorted(MOODS)}")
        return v


class LibraryCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    script: str = Field(default="", max_length=4000)
    genre: str = Field(default="club_banger")
    project: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    dj_name: str = Field(default="DJ Beshi", max_length=120)

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v):
        if v not in GENRES:
            raise ValueError(f"genre must be one of {sorted(GENRES)}")
        return v


# ============================================================
# TRAINING ENGINE
# ============================================================

class AITrainingEngine:
    @classmethod
    def save_training(cls, example_text: str, genre: str, dj_name: str = "", style_notes: str = "") -> int:
        example_text = example_text.strip()
        uppercase_ratio = (
            sum(1 for c in example_text if c.isupper()) / len(example_text)
            if example_text else 0
        )

        conn = db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO training_examples (
                dj_name, genre, example_text, style_notes, created_at,
                length, exclamation_count, uppercase_ratio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dj_name,
            genre,
            example_text,
            style_notes,
            now_iso(),
            len(example_text),
            example_text.count("!"),
            uppercase_ratio
        ))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    @classmethod
    def load_training(cls, genre: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = db_conn()
        cur = conn.cursor()
        if genre:
            cur.execute("""
                SELECT * FROM training_examples
                WHERE genre = ?
                ORDER BY id DESC
            """, (genre,))
        else:
            cur.execute("""
                SELECT * FROM training_examples
                ORDER BY id DESC
            """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    @classmethod
    def analyze_style(cls, text: str) -> Dict[str, Any]:
        return {
            "length": len(text),
            "words": text.split(),
            "has_stutter": bool(re.search(r'(\w)\.\.\.|\1-\1', text)),
            "energy_markers": text.count("!") + text.count("?"),
            "has_location": bool(re.search(r'\bin\b|\bfrom\b', text.lower())),
            "has_callout": bool(re.search(r'stand up|make some noise|hands up', text.lower())),
            "repeated_words": [
                word for word in set(text.split())
                if text.lower().split().count(word.lower()) > 1
            ]
        }

    @classmethod
    def mimic_drop(cls, example_text: str, dj_name: str, genre="club_banger", energy=8) -> str:
        style = cls.analyze_style(example_text)
        has_closer = bool(re.search(r'[!.,]\s*[^.!?]+[!.,]?$', example_text))

        parts = []

        if style["has_callout"]:
            openers = ["Yo!", "Listen up!", "Check it!", "Ayo!"]
            parts.append(random.choice(openers))

        if style["has_stutter"] or random.random() < 0.5:
            first_letter = dj_name[0] if dj_name else "D"
            stutter_patterns = [
                f"{first_letter}-{first_letter}-{dj_name}",
                f"{first_letter}... {first_letter}... {dj_name}",
                f"{dj_name}! {dj_name}!",
                dj_name
            ]
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

        phrases = energy_phrases.get(genre, energy_phrases["club_banger"])
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
        return re.sub(r'\s+', ' ', result).strip()

    @classmethod
    def generate_from_training(cls, dj_name: str, genre: str, energy: int, example_text: Optional[str] = None) -> Optional[str]:
        if example_text and example_text.strip():
            cls.save_training(example_text, genre, dj_name=dj_name, style_notes="user_provided")
            return cls.mimic_drop(example_text, dj_name, genre, energy)

        examples = cls.load_training(genre=genre)
        if examples:
            best = max(examples, key=lambda x: x.get("exclamation_count", 0) * max(1, energy) / 10)
            return cls.mimic_drop(best["example_text"], dj_name, genre, energy)

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

        options = [
            f"{opener} {display_name} is {verb}{city_part}. {energy_line.capitalize()}{p['exclaim']} {closer.capitalize()}",
            f"{opener} Locked in with {display_name}{city_part}. {energy_line.capitalize()}{p['exclaim']} {p['extra']}",
        ]

        if mood == "luxury":
            options.append(
                f"{opener} Premium settings only. {display_name}{city_part} is {verb}. {energy_line.capitalize()}."
            )
        elif mood == "aggressive":
            options.append(
                f"{opener} {display_name}{city_part} is here to cause major damage. {p['extra']}"
            )
        elif mood == "dark":
            options.append(
                f"{opener} {display_name}{city_part}. Dark pressure. {energy_line.capitalize()}{p['exclaim']}"
            )
        elif mood == "festival":
            options.append(
                f"{opener} {display_name}{city_part}. Main-stage pressure. {energy_line.capitalize()}{p['exclaim']}"
            )

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
        return (
            f"{opener} {display_name} in full effect{p['exclaim']} "
            f"{city_part} {closer.capitalize()} {p['extra']}"
        )

    @classmethod
    def build_promo(cls, display_name, data, city, event_name):
        promo_word = random.choice(data["promo_words"])
        city_part = f" in {city}" if city else ""
        event_part = f" for {event_name}" if event_name else ""
        return (
            f"{display_name} invites you{city_part}{event_part}. "
            f"Get ready for {promo_word}. Pull up live and experience the energy!"
        )

    @classmethod
    def build_producer_tag(cls, display_name, data):
        opener = random.choice(data["openers"])
        return f"{opener} {display_name}. Premium sound design only."

    @classmethod
    def build_radio_id(cls, display_name, city="", station_name="", slogan=""):
        city_part = f" in {city}" if city else ""
        station_part = f" on {station_name}" if station_name else ""
        slogan_part = f" -- {slogan}" if slogan else ""
        return (
            f"You're locked in with {display_name}{city_part}{station_part}{slogan_part}. "
            f"Premium radio sound."
        )

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
            score = cls.score_line(line, genre, energy, drop_type)
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
# AUDIO / FX ENGINE
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
                "duck_threshold": "0.025",
                "duck_release": "400",
                "bg_gain": 0.22,
                "vocal_gain": 1.3
            })
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

        return profile

    @classmethod
    def build_vocal_fx_chain(cls, style, energy, fx_mode="auto"):
        p = cls.get_fx_profile(style, energy)
        chain = []

        chain.append(f"highpass=f={p['highpass']}")
        chain.append(p["compressor"])
        chain.append(p["presence_eq"])
        chain.append(p["deesser_eq"])

        if fx_mode == "dry":
            pass
        elif fx_mode == "light":
            if p["slap"]:
                chain.append(p["slap"])
            elif p["echo"]:
                chain.append(p["echo"])
        elif fx_mode in {"heavy", "insane"}:
            if p["slap"]:
                chain.append(p["slap"])
            if p["echo"]:
                chain.append(p["echo"])
            if p["space"]:
                chain.append(p["space"])
            if p["phaser"]:
                chain.append(p["phaser"])
            if p["stereo"]:
                chain.append(p["stereo"])
            if fx_mode == "insane":
                chain.append("acompressor=threshold=-12dB:ratio=4:attack=2:release=80")
        else:
            if p["slap"]:
                chain.append(p["slap"])
            if p["echo"]:
                chain.append(p["echo"])
            if energy >= 7 and p["space"]:
                chain.append(p["space"])
            if energy >= 7 and p["phaser"]:
                chain.append(p["phaser"])
            if p["stereo"]:
                chain.append(p["stereo"])

        chain.append(p["loudness"])
        chain.append(p["limiter"])
        return ",".join([x for x in chain if x]), p

    @classmethod
    def run_ffmpeg(cls, cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg mastering failed:\n" + result.stderr)

    @classmethod
    def render_wet_vocal(cls, vocal_path, wet_output_path, style_preset, energy=8, fx_mode="auto", vocal_gain=1.0):
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
    def render_final_master(cls, wet_vocal_path, bg_path, final_output_path, style_preset, energy=8, bg_gain=None):
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
# TTS
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
            wav_path = str(Path(out_path).with_suffix(".espeak.wav"))
            subprocess.run([espeak_cmd, "-w", wav_path, text], capture_output=True, check=True)

            if os.path.exists(wav_path):
                subprocess.run([
                    "ffmpeg", "-y", "-i", wav_path,
                    "-b:a", "320k", out_path
                ], capture_output=True, check=True)
                os.remove(wav_path)
                return "espeak"
        except Exception as e:
            print(f"espeak failed: {e}")

    if FFMPEG_AVAILABLE:
        try:
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", "3", "-b:a", "320k", out_path
            ], capture_output=True, check=True)
            return "silent"
        except Exception as e:
            print(f"Silent MP3 failed: {e}")

    Path(out_path).touch()
    return "silent"


# ============================================================
# JOB STORAGE
# ============================================================

def create_job_record(
    job_uuid: str,
    status: str,
    dj_name: str,
    genre: str,
    drop_type: str,
    mood: str,
    energy: int,
    mode: str
):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO generation_jobs (
            job_uuid, status, dj_name, genre, drop_type, mood, energy,
            mode, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_uuid, status, dj_name, genre, drop_type, mood, energy,
        mode, now_iso(), now_iso()
    ))
    conn.commit()
    conn.close()

def update_job_record(job_uuid: str, **kwargs):
    if not kwargs:
        return
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    fields.append("updated_at = ?")
    values.append(now_iso())
    values.append(job_uuid)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(f"""
        UPDATE generation_jobs
        SET {", ".join(fields)}
        WHERE job_uuid = ?
    """, values)
    conn.commit()
    conn.close()

def get_job_record(job_uuid: str) -> Optional[Dict[str, Any]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM generation_jobs WHERE job_uuid = ?", (job_uuid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# MAIN GENERATION FUNCTION
# ============================================================

async def build_premium_drop(req: GenerateRequest):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    project_name = f"{slugify_text(req.dj_name)}_{timestamp}_{uuid.uuid4().hex[:8]}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if req.training_example and req.training_example.strip():
        mimic_result = AITrainingEngine.generate_from_training(
            dj_name=req.dj_name,
            genre=req.genre,
            energy=req.energy,
            example_text=req.training_example
        )
        if mimic_result:
            selected = mimic_result
            takes = [{"text": selected, "score": 15, "mimic": True}]
        else:
            takes = PremiumDJScriptAI.generate(
                dj_name=req.dj_name, genre=req.genre, use_stutter=req.use_stutter,
                drop_type=req.drop_type, mood=req.mood, energy=req.energy,
                city=req.city, event_name=req.event_name, user_stutter=req.user_stutter,
                station_name=req.station_name, slogan=req.slogan, crew_tag=req.crew_tag,
                count=8
            )
            selected = takes[0]["text"]
    elif req.mode == "strict" and req.custom_script.strip():
        selected = req.custom_script.strip()
        takes = [{"text": selected, "score": 10}]
    else:
        takes = PremiumDJScriptAI.generate(
            dj_name=req.dj_name, genre=req.genre, use_stutter=req.use_stutter,
            drop_type=req.drop_type, mood=req.mood, energy=req.energy,
            city=req.city, event_name=req.event_name, user_stutter=req.user_stutter,
            station_name=req.station_name, slogan=req.slogan, crew_tag=req.crew_tag,
            count=8
        )
        selected = takes[0]["text"]

    takes_file = out_dir / "takes.txt"
    with open(takes_file, "w", encoding="utf-8") as f:
        for i, item in enumerate(takes, 1):
            f.write(f"{i}. ({item['score']}) {item['text']}\n")

    voice_choice = req.voice
    if voice_choice == "7":
        voice = AUTO_GENRE_VOICE.get(req.genre, "en-US-AndrewNeural")
    else:
        voice = VOICE_MAP.get(voice_choice, ("", "en-US-AndrewNeural"))[1]

    raw_vocal = out_dir / "raw_vocal.mp3"
    wet_vocal = out_dir / "wet_vocal.mp3"
    final_master = out_dir / f"{project_name}.mp3"

    preset = VOICE_PRESETS.get(req.genre.lower(), {"rate": "+5%", "volume": "+10%"})

    tts_engine = await synthesize_tts_smart(
        selected, voice, str(raw_vocal), preset["rate"], preset["volume"]
    )

    full_bg_path = ""
    if req.bg_track:
        candidate = UPLOAD_DIR / req.bg_track
        if candidate.exists():
            full_bg_path = str(candidate)

    if FFMPEG_AVAILABLE and raw_vocal.exists() and raw_vocal.stat().st_size > 0:
        try:
            PremiumAudioStudio.render_wet_vocal(
                vocal_path=str(raw_vocal),
                wet_output_path=str(wet_vocal),
                style_preset=req.genre,
                energy=req.energy,
                fx_mode=req.fx_mode,
                vocal_gain=req.vocal_gain
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
                bg_path=full_bg_path,
                final_output_path=str(final_master),
                style_preset=req.genre,
                energy=req.energy,
                bg_gain=req.bg_gain
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
        "mode": req.mode,
        "tts_engine": tts_engine,
        "offline": tts_engine in {"espeak", "silent"},
        "ffmpeg_available": FFMPEG_AVAILABLE
    }


# ============================================================
# API ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "message": "DJ DROP FACTORY PRO v4 backend is running"
    }


@app.get("/api/status")
def api_status():
    return {
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "online": has_internet(),
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "espeak_available": ESPEAK_AVAILABLE,
        "edge_tts_ready": has_internet(),
        "message": "Full audio generation" if FFMPEG_AVAILABLE else "Script only - no audio FX"
    }


@app.get("/api/voices")
def get_voices():
    return {
        "success": True,
        "voices": VOICE_MAP,
        "auto_map": AUTO_GENRE_VOICE
    }


@app.post("/api/train")
def api_train(payload: TrainRequest):
    if not payload.example.strip():
        raise HTTPException(status_code=400, detail="No example text provided")

    if payload.train_mode == "exact":
        row_id = AITrainingEngine.save_training(
            payload.example,
            payload.genre,
            dj_name=payload.dj_name,
            style_notes="exact_copy"
        )
        return {
            "success": True,
            "training_id": row_id,
            "script": payload.example,
            "mode": "exact",
            "message": "Exact copy saved and ready to use!"
        }

    mimic = AITrainingEngine.generate_from_training(
        dj_name=payload.dj_name,
        genre=payload.genre,
        energy=payload.energy,
        example_text=payload.example
    )

    return {
        "success": True,
        "original": payload.example,
        "script": mimic,
        "mode": "mimic",
        "analysis": AITrainingEngine.analyze_style(payload.example),
        "message": "AI learned your style and created a new drop!"
    }


@app.get("/api/training")
def list_training(
    genre: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None)
):
    rows = AITrainingEngine.load_training(genre=genre)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.get("example_text") or "").lower() or ql in (r.get("dj_name") or "").lower()]
    return {
        "success": True,
        "count": len(rows),
        "items": rows
    }


@app.post("/api/preview_script")
def preview_script(payload: PreviewRequest):
    takes = PremiumDJScriptAI.generate(
        dj_name=payload.dj_name,
        genre=payload.genre,
        use_stutter=payload.use_stutter,
        drop_type=payload.drop_type,
        mood=payload.mood,
        energy=payload.energy,
        city=payload.city,
        event_name=payload.event_name,
        user_stutter=payload.user_stutter,
        station_name=payload.station_name,
        slogan=payload.slogan,
        crew_tag=payload.crew_tag,
        count=3
    )

    return {
        "success": True,
        "scripts": [t["text"] for t in takes],
        "best": takes[0]["text"] if takes else ""
    }


@app.post("/api/generate")
async def api_generate(payload: GenerateRequest):
    job_uuid = uuid.uuid4().hex
    create_job_record(
        job_uuid=job_uuid,
        status="processing",
        dj_name=payload.dj_name,
        genre=payload.genre,
        drop_type=payload.drop_type,
        mood=payload.mood,
        energy=payload.energy,
        mode=payload.mode
    )

    try:
        result = await build_premium_drop(payload)

        filename = Path(result["final_master"]).name
        download_url = f"/download/{result['project_name']}/{filename}"

        update_job_record(
            job_uuid,
            status="completed",
            script=result["script"],
            output_file=download_url,
            tts_engine=result["tts_engine"]
        )

        return {
            "success": True,
            "job_id": job_uuid,
            "project": result["project_name"],
            "script": result["script"],
            "takes": result["takes"],
            "mode": result["mode"],
            "tts_engine": result["tts_engine"],
            "offline": result["offline"],
            "ffmpeg_available": result["ffmpeg_available"],
            "download_url": download_url,
            "message": "Drop generated!" + (
                " (Neural voice)" if result["tts_engine"] == "edge"
                else " (Basic audio)" if result["tts_engine"] == "espeak"
                else " (Audio unavailable)"
            )
        }
    except Exception as e:
        update_job_record(job_uuid, status="failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = get_job_record(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job}


@app.get("/api/jobs")
def list_jobs(
    q: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200)
):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM generation_jobs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if genre:
        rows = [r for r in rows if r.get("genre") == genre]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if q:
        ql = q.lower()
        rows = [
            r for r in rows
            if ql in (r.get("dj_name") or "").lower()
            or ql in (r.get("script") or "").lower()
            or ql in (r.get("job_uuid") or "").lower()
        ]

    return {"success": True, "count": len(rows), "jobs": rows}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="Empty filename")

    ensure_upload_extension(filename, ALLOWED_AUDIO_EXTENSIONS | ALLOWED_BG_EXTENSIONS)

    ext = file_ext(filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = UPLOAD_DIR / unique_name

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_UPLOAD_SIZE_MB}MB limit")

    with open(filepath, "wb") as f:
        f.write(content)

    return {
        "success": True,
        "filename": unique_name,
        "original_name": filename,
        "size": len(content),
        "url": f"/uploads/{unique_name}"
    }


@app.get("/uploads/{filename}")
def serve_upload(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@app.get("/download/{project}/{filename}")
def download_file(project: str, filename: str):
    file_path = OUTPUT_DIR / project / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), filename=filename)


@app.post("/api/process_voice")
async def process_voice_effect(
    audio: UploadFile = File(...),
    effect: str = Form(default="none")
):
    if not FFMPEG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="FFmpeg is not available on this server. Cannot apply voice effects."
        )

    ensure_upload_extension(audio.filename or "audio.webm", ALLOWED_AUDIO_EXTENSIONS)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    input_ext = file_ext(audio.filename or ".webm") or ".webm"
    input_path = UPLOAD_DIR / f"voice_raw_{timestamp}_{uuid.uuid4().hex[:6]}{input_ext}"
    output_path = UPLOAD_DIR / f"voice_effect_{effect}_{timestamp}_{uuid.uuid4().hex[:6]}.mp3"

    content = await audio.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_UPLOAD_SIZE_MB}MB limit")

    with open(input_path, "wb") as f:
        f.write(content)

    if effect == "helium":
        filter_chain = (
            "asetrate=44100*1.8,atempo=1/1.8,"
            "highpass=f=80,acompressor=threshold=-18dB:ratio=4,"
            "loudnorm=I=-14:TP=-1.0"
        )
    elif effect == "low":
        filter_chain = (
            "asetrate=44100*0.55,atempo=1/0.55,"
            "highpass=f=60,acompressor=threshold=-16dB:ratio=5,"
            "loudnorm=I=-14:TP=-1.0"
        )
    elif effect == "robot":
        filter_chain = (
            "highpass=f=200,aecho=0.8:0.6:5:0.3,"
            "vibrato=f=8:d=0.5,"
            "equalizer=f=3000:width_type=q:width=2:g=6,"
            "equalizer=f=800:width_type=q:width=1.5:g=4,"
            "acompressor=threshold=-14dB:ratio=6,"
            "loudnorm=I=-12:TP=-0.5"
        )
    elif effect == "echo":
        filter_chain = (
            "aecho=0.85:0.65:180|360:0.25|0.15,"
            "aecho=0.80:0.50:650|900:0.12|0.08,"
            "highpass=f=100,acompressor=threshold=-16dB:ratio=4,"
            "loudnorm=I=-14:TP=-1.0"
        )
    elif effect == "phone":
        filter_chain = (
            "highpass=f=300,lowpass=f=3400,"
            "equalizer=f=1000:width_type=q:width=1.5:g=3,"
            "acompressor=threshold=-14dB:ratio=5,"
            "loudnorm=I=-14:TP=-1.0"
        )
    elif effect == "slow":
        filter_chain = (
            "atempo=0.5,asetrate=22050,aresample=44100,"
            "acompressor=threshold=-16dB:ratio=4,"
            "loudnorm=I=-14:TP=-1.0"
        )
    elif effect == "fast":
        filter_chain = (
            "atempo=2.0,asetrate=88200,aresample=44100,"
            "acompressor=threshold=-16dB:ratio=4,"
            "loudnorm=I=-14:TP=-1.0"
        )
    else:
        filter_chain = (
            "highpass=f=80,acompressor=threshold=-18dB:ratio=3,"
            "loudnorm=I=-14:TP=-1.0"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", filter_chain,
        "-b:a", "320k",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        if input_path.exists():
            input_path.unlink()
    except Exception:
        pass

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg processing failed: {result.stderr}")

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Output file not created")

    filename = output_path.name
    return {
        "success": True,
        "filename": filename,
        "audio_url": f"/uploads/{filename}",
        "download_url": f"/uploads/{filename}",
        "effect": effect,
        "message": f"Voice effect '{effect}' applied successfully!"
    }


# ============================================================
# LIBRARY API
# ============================================================

@app.get("/api/library")
def get_library(
    q: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM library_items ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if genre:
        rows = [r for r in rows if r.get("genre") == genre]
    if q:
        ql = q.lower()
        rows = [
            r for r in rows
            if ql in (r.get("title") or "").lower()
            or ql in (r.get("script") or "").lower()
            or ql in (r.get("dj_name") or "").lower()
            or ql in (r.get("project_name") or "").lower()
        ]

    return {"success": True, "count": len(rows), "drops": rows}


@app.post("/api/library")
def add_to_library(payload: LibraryCreateRequest):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO library_items (
            title, script, genre, project_name, dj_name, file_url, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.title,
        payload.script,
        payload.genre,
        payload.project,
        payload.dj_name,
        payload.url,
        now_iso()
    ))
    conn.commit()
    row_id = cur.lastrowid

    cur.execute("SELECT * FROM library_items WHERE id = ?", (row_id,))
    row = dict(cur.fetchone())
    conn.close()

    return {"success": True, "drop": row}


@app.delete("/api/library/{drop_id}")
def delete_from_library(drop_id: int):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM library_items WHERE id = ?", (drop_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="Library item not found")

    return {"success": True}


# ============================================================
# SEARCH API
# ============================================================

@app.get("/api/search")
def global_search(
    q: str = Query(..., min_length=1),
    scope: Literal["all", "library", "jobs", "training"] = "all",
    limit: int = Query(default=50, ge=1, le=200)
):
    ql = q.lower()
    results = {"library": [], "jobs": [], "training": []}

    conn = db_conn()
    cur = conn.cursor()

    if scope in {"all", "library"}:
        cur.execute("SELECT * FROM library_items ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        results["library"] = [
            r for r in rows
            if ql in (r.get("title") or "").lower()
            or ql in (r.get("script") or "").lower()
            or ql in (r.get("dj_name") or "").lower()
        ]

    if scope in {"all", "jobs"}:
        cur.execute("SELECT * FROM generation_jobs ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        results["jobs"] = [
            r for r in rows
            if ql in (r.get("dj_name") or "").lower()
            or ql in (r.get("script") or "").lower()
            or ql in (r.get("job_uuid") or "").lower()
        ]

    if scope in {"all", "training"}:
        cur.execute("SELECT * FROM training_examples ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        results["training"] = [
            r for r in rows
            if ql in (r.get("example_text") or "").lower()
            or ql in (r.get("dj_name") or "").lower()
        ]

    conn.close()

    return {
        "success": True,
        "query": q,
        "scope": scope,
        "results": results
    }


# ============================================================
# STARTUP INFO
# ============================================================

@app.on_event("startup")
async def startup_log():
    print("=" * 60)
    print(f"{APP_NAME} v{APP_VERSION}")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Uploads: {UPLOAD_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Internet: {'YES' if has_internet() else 'NO'}")
    print(f"FFmpeg:   {'YES' if FFMPEG_AVAILABLE else 'NO'}")
    print(f"espeak:   {'YES' if ESPEAK_AVAILABLE else 'NO'}")
    print("=" * 60)


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
