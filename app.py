# ============================================================
# PREMIUM AI DJ DROP FACTORY v3.0
# Created by: Macdonald Barasa
# Email: simiyumacdonal1@gmail.com
# Features: AI Training Mode, Loud Audio, Voice Effects, PWA Install
# ============================================================

import os
import re
import random
import asyncio
import subprocess
import shutil
import urllib.request
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import edge_tts

# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "generated_drops"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# AI Training storage
TRAINING_DIR = BASE_DIR / "training_data"
TRAINING_DIR.mkdir(exist_ok=True)

# ============================================================
# DETECT AVAILABLE TOOLS
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
print("DJ DROP FACTORY v3.0 - Macdonald Barasa")
print("Email: simiyumacdonal1@gmail.com")
print("=" * 60)
print(f"Internet: {'YES' if has_internet() else 'NO'}")
print(f"FFmpeg:   {'YES' if FFMPEG_AVAILABLE else 'NO'}")
print(f"espeak:   {'YES' if ESPEAK_AVAILABLE else 'NO'}")
print("=" * 60)


# ============================================================
# AI TRAINING ENGINE
# ============================================================

class AITrainingEngine:
    """
    Learns from user-provided example drops.
    Extracts patterns, style, energy level, and mimics them.
    """
    
    TRAINING_FILE = TRAINING_DIR / "trained_examples.json"
    
    @classmethod
    def save_training(cls, example_text, genre, style_notes):
        """Save a training example for future mimicry."""
        import json
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
        """Load all training examples."""
        import json
        if not cls.TRAINING_FILE.exists():
            return []
        with open(cls.TRAINING_FILE, 'r') as f:
            return json.load(f)
    
    @classmethod
    def analyze_style(cls, text):
        """Analyze the style of a drop text."""
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
        """
        Create a new drop that mimics the style of the example.
        Preserves structure, energy, and flow while changing content.
        """
        style = cls.analyze_style(example_text)
        
        has_opener = bool(re.match(r'^[^.!?]+[!.,]', example_text))
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
        """Generate a drop using training data or a fresh example."""
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
# 1) SCRIPT AI ENGINE
# ============================================================

class PremiumDJScriptAI:
    GENRE_DATA = {
        "amapiano": {
            "openers": ["Lalela!", "Yanos to the world!", "Piano session loading!",
                        "Private school vibes!", "Log drum pressure!"],
            "verbs": ["locking the groove", "running the vibe", "controlling the session",
                      "bringing the piano heat", "shaking the nightlife", "setting the vibe"],
            "energy_lines": ["strictly smooth pressure", "nothing but elite groove",
                             "luxury nightlife settings", "deep log drum madness",
                             "all night amapiano pressure", "piano culture in motion"],
            "closers": ["let the bassline breathe", "vibes only", "you know the code",
                        "strictly for the culture", "we move"],
            "promo_words": ["exclusive nightlife experience", "premium amapiano atmosphere",
                            "non-stop groove", "elite party energy"]
        },
        "dancehall": {
            "openers": ["Brap brap!", "Pull up selectah!", "Forward!",
                        "Mad ting!", "Soundbwoy warning!"],
            "verbs": ["shelling the riddim", "mashing up the dance", "running the sound",
                      "tearing down the arena", "bringing dangerous pressure",
                      "murdering the riddim"],
            "energy_lines": ["danger in full effect", "soundclash settings only",
                             "pure dancehall fire", "reload after reload",
                             "badman riddim pressure", "sound system warfare"],
            "closers": ["pull it up!", "run the tune!", "dangerous settings!",
                        "madness only!", "soundbwoy fi know!", "forward di ting!"],
            "promo_words": ["heavy dancehall energy", "sound system pressure",
                            "dangerous live performance", "non-stop riddim action"]
        },
        "radio": {
            "openers": ["You're locked in.", "Live on air.", "Now broadcasting.",
                        "Stay tuned.", "Across the airwaves."],
            "verbs": ["keeping it locked", "taking over the airwaves",
                      "bringing premium sound", "delivering the hottest selection",
                      "holding down the frequency"],
            "energy_lines": ["fresh and exclusive", "premium broadcast energy",
                             "the sound of the city", "top-tier radio experience",
                             "your official soundtrack"],
            "closers": ["stay connected", "keep it locked", "more heat on the way",
                        "premium sound only", "don't touch that dial"],
            "promo_words": ["live radio experience", "exclusive station branding",
                            "premium station identity", "broadcast-ready sound"]
        },
        "club_banger": {
            "openers": ["Hands up!", "Main event settings!", "Turn it up!",
                        "Global shutdown!", "Brace yourself!"],
            "verbs": ["taking over the decks", "breaking the club", "running the main event",
                      "unleashing chaos", "lighting up the crowd", "smashing the dancefloor"],
            "energy_lines": ["festival-level pressure", "wall-to-wall energy",
                             "club destruction mode", "full arena madness",
                             "high-voltage nightlife energy"],
            "closers": ["let's go!", "make some noise!", "we outside!",
                        "no sleep tonight!", "take it higher!"],
            "promo_words": ["explosive nightlife energy", "main stage pressure",
                            "unmatched club experience", "full-throttle entertainment"]
        },
        "afrobeat": {
            "openers": ["Afro vibes!", "Worldwide groove!", "Afrobeats loading!",
                        "Big rhythm energy!", "Wave after wave!"],
            "verbs": ["bringing the afro heat", "running the groove",
                      "setting the summer mood", "moving the culture", "lifting the party"],
            "energy_lines": ["sweet afro pressure", "melodic nightlife energy",
                             "global afro rhythm", "steady groove and vibes",
                             "afro bounce all night"],
            "closers": ["vibes non-stop!", "feel the rhythm!", "steady now!",
                        "we outside!", "all love and energy!"],
            "promo_words": ["premium afrobeat experience", "melodic party energy",
                            "feel-good nightlife pressure", "afro groove all night"]
        },
        "trap": {
            "openers": ["808 warning!", "Bassline alert!", "Turn the system up!",
                        "Pressure mode!", "Heavyweight entry!"],
            "verbs": ["dropping heavy pressure", "bringing the bassline warfare",
                      "setting the room on fire", "running the late-night energy",
                      "taking over the trap wave"],
            "energy_lines": ["808 pressure", "dark club energy", "sub-heavy madness",
                             "late-night danger", "bassline demolition"],
            "closers": ["let it knock!", "shake the walls!", "run it back!",
                        "take it louder!", "bassline only!"],
            "promo_words": ["sub-heavy live experience", "hard-hitting trap energy",
                            "nightlife pressure", "heavyweight bass performance"]
        }
    }

    DROP_TYPES = ["intro", "sweeper", "hype", "promo",
                  "producer_tag", "radio_id", "crowd_call"]

    @classmethod
    def clean_name(cls, dj_name: str) -> str:
        return re.sub(r"\s+", " ", (dj_name or "").strip()) or "DJ Beshi"

    @classmethod
    def normalize_for_stutter(cls, txt: str) -> str:
        txt = txt.strip()
        txt = re.sub(r"\s+", " ", txt)
        return txt

    @classmethod
    def apply_stutter(cls, dj_name: str, style: str = "classic", user_stutter: str = "") -> str:
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
    def energy_profile(cls, energy: int):
        if energy <= 3:
            return {"exclaim": "", "extra": "steady vibes only."}
        elif energy <= 6:
            return {"exclaim": "!", "extra": "locked and loaded."}
        elif energy <= 8:
            return {"exclaim": "!!", "extra": "full pressure mode!!"}
        return {"exclaim": "!!!", "extra": "shutdown mode."}

    @classmethod
    def choose_stutter_style(cls, genre: str, use_stutter: bool) -> str:
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
    def score_line(cls, text: str, genre: str, energy: int, drop_type: str) -> int:
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
        return f"{opener} {display_name} in full effect{p['exclaim']} {city_part} {closer.capitalize()} {p['extra']}"

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
        slogan_part = f" — {slogan}" if slogan else ""
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
# 2) AUDIO / FX ENGINE - LOUD VERSION
# ============================================================

class PremiumAudioStudio:
    """
    Audio engine with LOUD output for maximum impact.
    """
    
    @classmethod
    def safe_stereo(cls, mlev: float) -> str:
        mlev = max(0.015625, min(64.0, float(mlev)))
        return f"stereotools=mlev={mlev:.6f}"

    @classmethod
    def get_fx_profile(cls, style: str, energy: int):
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

        else:  # club_banger - MAXIMUM LOUD
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
    def build_vocal_fx_chain(cls, style: str, energy: int, fx_mode: str = "auto"):
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

        elif fx_mode == "insane":
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
            chain.append("acompressor=threshold=-12dB:ratio=4:attack=2:release=80")

        else:  # auto
            if style_key == "radio":
                if p["slap"]:
                    chain.append(p["slap"])

            elif style_key == "dancehall":
                if p["slap"]:
                    chain.append(p["slap"])
                if energy >= 7 and p["echo"]:
                    chain.append(p["echo"])

            elif style_key == "amapiano":
                if p["echo"]:
                    chain.append(p["echo"])
                if p["space"]:
                    chain.append(p["space"])
                if energy >= 6 and p["phaser"]:
                    chain.append(p["phaser"])
                if p["stereo"]:
                    chain.append(p["stereo"])

            elif style_key == "afrobeat":
                if p["echo"]:
                    chain.append(p["echo"])
                if p["space"] and energy >= 6:
                    chain.append(p["space"])
                if p["stereo"]:
                    chain.append(p["stereo"])

            elif style_key == "trap":
                if p["echo"]:
                    chain.append(p["echo"])
                if p["phaser"] and energy >= 7:
                    chain.append(p["phaser"])
                if p["stereo"]:
                    chain.append(p["stereo"])

            else:  # club_banger
                if p["echo"]:
                    chain.append(p["echo"])
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
# 3) VOICE PRESETS - LOUD
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


def safe_filename(name: str) -> str:
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
# 4) MAIN GENERATION FUNCTION
# ============================================================

async def build_premium_drop(dj_name, genre, voice, use_stutter, bg_track,
                             drop_type, mood, energy, city, event_name,
                             user_stutter, station_name, slogan, crew_tag,
                             fx_mode, vocal_gain, bg_gain, mode="ai", custom_script="",
                             training_example=None):
    """
    Generate a drop with optional AI training.
    training_example: A drop text to mimic/copy
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{safe_filename(dj_name)}_{timestamp}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Handle AI Training mode
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

    # Save takes
    takes_file = out_dir / "takes.txt"
    with open(takes_file, "w", encoding="utf-8") as f:
        for i, item in enumerate(takes, 1):
            f.write(f"{i}. ({item['score']}) {item['text']}\n")

    raw_vocal = out_dir / "raw_vocal.mp3"
    wet_vocal = out_dir / "wet_vocal.mp3"
    final_master = out_dir / f"{project_name}.mp3"

    preset = VOICE_PRESETS.get(genre.lower(), {"rate": "+5%", "volume": "+10%"})

    # Step 1: TTS
    tts_engine = await synthesize_tts_smart(
        selected, voice, str(raw_vocal), preset["rate"], preset["volume"]
    )

    # Step 2: Apply FX if FFmpeg available
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
            import shutil as sh
            sh.copy(str(raw_vocal), str(wet_vocal))
    else:
        import shutil as sh
        sh.copy(str(raw_vocal), str(wet_vocal))

    # Step 3: Final master mix
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
            import shutil as sh
            sh.copy(str(wet_vocal), str(final_master))
    else:
        import shutil as sh
        sh.copy(str(wet_vocal), str(final_master))

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
# 5) FLASK ROUTES
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


@app.route("/api/train", methods=["POST"])
def api_train():
    """
    Save a training example and return a mimicked version.
    """
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
    """
    Receive a recorded voice, apply audio effect using FFmpeg,
    and return the processed MP3.
    """
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
            filter_chain = (
                "highpass=f=200,"
                "aecho=0.8:0.6:5:0.3,"
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
                "highpass=f=100,"
                "acompressor=threshold=-16dB:ratio=4,"
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
            filter_chain = "atempo=0.5,asetrate=22050,aresample=44100,acompressor=threshold=-16dB:ratio=4,loudnorm=I=-14:TP=-1.0"

        elif effect == "fast":
            filter_chain = "atempo=2.0,asetrate=88200,aresample=44100,acompressor=threshold=-16dB:ratio=4,loudnorm=I=-14:TP=-1.0"

        else:
            filter_chain = "highpass=f=@app.route("/api/process_voice", methods=["POST"])
def process_voice_effect():
    """
    Receive a recorded voice, apply audio effect using FFmpeg,
    and return the processed MP3.
    """
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
            filter_chain = (
                "highpass=f=200,"
                "aecho=0.8:0.6:5:0.3,"
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
                "highpass=f=100,"
                "acompressor=threshold=-16dB:ratio=4,"
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
# 6) APP STARTUP
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("   PREMIUM AI DJ DROP FACTORY v3.0")
    print("   Created by: Macdonald Barasa")
    print("   Email: simiyumacdonal1@gmail.com")
    print("=" * 60)
    print("Features: AI Training Mode | Loud Audio | Voice Effects | PWA Install")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)

