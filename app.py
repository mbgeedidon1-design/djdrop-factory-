# ============================================================
# PREMIUM AI DJ DROP FACTORY - RENDER CLOUD EDITION v2.2
# Works on Render free tier (no system packages needed)
# Offline TTS fallback with graceful degradation
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

# ============================================================
# DETECT AVAILABLE TOOLS
# ============================================================

def has_internet(timeout=3):
    """Check if internet is available."""
    try:
        urllib.request.urlopen('https://www.google.com', timeout=timeout)
        return True
    except Exception:
        return False

def check_ffmpeg():
    """Find FFmpeg command."""
    return shutil.which('ffmpeg')

def check_espeak():
    """Find espeak-ng or espeak command."""
    return shutil.which('espeak-ng') or shutil.which('espeak')

# Check what's available on this server
FFMPEG_AVAILABLE = check_ffmpeg() is not None
ESPEAK_AVAILABLE = check_espeak() is not None
INTERNET_AVAILABLE = has_internet()

print("=" * 60)
print("DJ DROP FACTORY - SYSTEM CHECK")
print("=" * 60)
print(f"Internet: {'YES' if INTERNET_AVAILABLE else 'NO'}")
print(f"FFmpeg:   {'YES' if FFMPEG_AVAILABLE else 'NO'}")
print(f"espeak:   {'YES' if ESPEAK_AVAILABLE else 'NO'}")
print("=" * 60)


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
# 2) AUDIO / FX ENGINE
# ============================================================

class PremiumAudioStudio:
    @classmethod
    def safe_stereo(cls, mlev: float) -> str:
        mlev = max(0.015625, min(64.0, float(mlev)))
        return f"stereotools=mlev={mlev:.6f}"

    @classmethod
    def get_fx_profile(cls, style: str, energy: int):
        style = style.lower().strip()

        profile = {
            "highpass": 100,
            "compressor": "acompressor=threshold=-16dB:ratio=4.5:attack=8:release=120",
            "presence_eq": "equalizer=f=3200:width_type=q:width=1.1:g=2.5",
            "deesser_eq": "equalizer=f=6500:width_type=q:width=1.2:g=-1.2",
            "echo": "",
            "slap": "",
            "space": "",
            "phaser": "",
            "stereo": "",
            "loudness": "loudnorm=I=-12:TP=-1.5:LRA=7",
            "duck_threshold": "0.035",
            "duck_release": "250",
            "bg_gain": 0.23,
            "vocal_gain": 1.0
        }

        if style == "amapiano":
            profile.update({
                "highpass": 95,
                "presence_eq": "equalizer=f=2800:width_type=q:width=1.0:g=2.0",
                "echo": "aecho=0.82:0.55:220|440:0.22|0.12",
                "space": "aecho=0.78:0.45:700|900:0.10|0.06",
                "phaser": "aphaser=speed=0.20:decay=0.35",
                "stereo": cls.safe_stereo(0.02),
                "duck_threshold": "0.03",
                "duck_release": "420",
                "bg_gain": 0.25
            })
            if energy >= 8:
                profile["space"] = "aecho=0.80:0.50:650|850:0.14|0.08"
                profile["phaser"] = "aphaser=speed=0.25:decay=0.40"

        elif style == "dancehall":
            profile.update({
                "highpass": 110,
                "presence_eq": "equalizer=f=3500:width_type=q:width=1.0:g=4.0",
                "slap": "aecho=0.85:0.55:110:0.18",
                "echo": "aecho=0.80:0.50:220:0.10",
                "stereo": cls.safe_stereo(0.02),
                "duck_threshold": "0.04",
                "duck_release": "180",
                "bg_gain": 0.22
            })
            if energy >= 8:
                profile["echo"] = "aecho=0.82:0.55:180|260:0.14|0.08"

        elif style == "radio":
            profile.update({
                "highpass": 100,
                "compressor": "acompressor=threshold=-18dB:ratio=3.5:attack=10:release=140",
                "presence_eq": "equalizer=f=3000:width_type=q:width=1.1:g=3.0",
                "slap": "aecho=0.70:0.35:95:0.08",
                "duck_threshold": "0.04",
                "duck_release": "180",
                "bg_gain": 0.18
            })

        elif style == "afrobeat":
            profile.update({
                "highpass": 100,
                "presence_eq": "equalizer=f=3000:width_type=q:width=1.1:g=2.8",
                "echo": "aecho=0.80:0.50:240|360:0.14|0.08",
                "space": "aecho=0.75:0.42:650|820:0.08|0.05",
                "stereo": cls.safe_stereo(0.02),
                "duck_threshold": "0.032",
                "duck_release": "320",
                "bg_gain": 0.24
            })

        elif style == "trap":
            profile.update({
                "highpass": 105,
                "presence_eq": "equalizer=f=3400:width_type=q:width=1.0:g=3.6",
                "echo": "aecho=0.82:0.60:160|320:0.20|0.10",
                "phaser": "aphaser=speed=0.35:decay=0.30",
                "stereo": cls.safe_stereo(0.03),
                "duck_threshold": "0.03",
                "duck_release": "280",
                "bg_gain": 0.22
            })

        else:
            profile.update({
                "highpass": 105,
                "presence_eq": "equalizer=f=3400:width_type=q:width=1.0:g=3.5",
                "echo": "aecho=0.82:0.60:180|360:0.20|0.10",
                "phaser": "aphaser=speed=0.35:decay=0.30",
                "stereo": cls.safe_stereo(0.03),
                "duck_threshold": "0.03",
                "duck_release": "300",
                "bg_gain": 0.23
            })
            if energy >= 8:
                profile["echo"] = "aecho=0.84:0.62:160|320:0.24|0.12"
                profile["phaser"] = "aphaser=speed=0.45:decay=0.35"

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
            chain.append("acompressor=threshold=-14dB:ratio=3:attack=3:release=90")

        else:
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

            else:
                if p["echo"]:
                    chain.append(p["echo"])
                if energy >= 7 and p["phaser"]:
                    chain.append(p["phaser"])
                if p["stereo"]:
                    chain.append(p["stereo"])

        chain.append(p["loudness"])
        return ",".join([x for x in chain if x]), p

    @classmethod
    def run_ffmpeg(cls, cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg mastering failed:\n" + result.stderr)

    @classmethod
    def render_wet_vocal(cls, vocal_path, wet_output_path, style_preset, energy=8,
                         fx_mode="auto", vocal_gain=1.0):
        vocal_fx, _ = cls.build_vocal_fx_chain(style_preset, energy, fx_mode)

        if abs(vocal_gain - 1.0) > 0.0001:
            vocal_fx = f"volume={vocal_gain},{vocal_fx}"

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
                f"threshold={profile['duck_threshold']}:ratio=12:attack=5:release={profile['duck_release']}[bgduck];"
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
# 3) VOICE PRESETS
# ============================================================

VOICE_PRESETS = {
    "amapiano": {"rate": "+1%", "volume": "+6%"},
    "dancehall": {"rate": "+9%", "volume": "+13%"},
    "radio": {"rate": "0%", "volume": "+7%"},
    "club_banger": {"rate": "+7%", "volume": "+11%"},
    "afrobeat": {"rate": "+3%", "volume": "+8%"},
    "trap": {"rate": "+4%", "volume": "+10%"},
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
    """
    Try online edge-tts first. If no internet, fall back to espeak-ng.
    If neither works, create a silent placeholder.
    Returns: 'edge', 'espeak', or 'silent'
    """
    online = has_internet()

    # Try online edge-tts (best quality)
    if online:
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            await communicate.save(out_path)
            return "edge"
        except Exception as e:
            print(f"Edge TTS failed: {e}")

    # Try offline espeak-ng
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

    # LAST RESORT: Create silent placeholder MP3
    if FFMPEG_AVAILABLE:
        try:
            subprocess.run([
                'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
                '-t', '3', '-b:a', '320k', out_path
            ], capture_output=True, check=True)
            return "silent"
        except Exception as e:
            print(f"Silent MP3 failed: {e}")

    # Absolute fallback - create empty file
    Path(out_path).touch()
    return "silent"


# ============================================================
# 4) MAIN GENERATION FUNCTION
# ============================================================

async def build_premium_drop(dj_name, genre, voice, use_stutter, bg_track,
                             drop_type, mood, energy, city, event_name,
                             user_stutter, station_name, slogan, crew_tag,
                             fx_mode, vocal_gain, bg_gain, mode="ai", custom_script=""):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"{safe_filename(dj_name)}_{timestamp}"
    out_dir = OUTPUT_DIR / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate script
    if mode == "strict" and custom_script.strip():
        selected = custom_script.strip()
        takes = [{"text": selected, "score": 10}]
    else:
        takes = PremiumDJScriptAI.generate(
            dj_name=dj_name,
            genre=genre,
            use_stutter=use_stutter,
            drop_type=drop_type,
            mood=mood,
            energy=energy,
            city=city,
            event_name=event_name,
            user_stutter=user_stutter,
            station_name=station_name,
            slogan=slogan,
            crew_tag=crew_tag,
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

    # Step 1: TTS (with graceful fallback)
    tts_engine = await synthesize_tts_smart(
        selected, voice, str(raw_vocal), preset["rate"], preset["volume"]
    )

    # Step 2: Apply FX if FFmpeg is available
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
            # Copy raw as wet if FX fails
            import shutil as sh
            sh.copy(str(raw_vocal), str(wet_vocal))
    else:
        # No FFmpeg - just copy raw to wet
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
    """Check server capabilities."""
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


@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        mode = data.get("mode", "ai")
        custom_script = data.get("custom_script", "").strip()

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
            custom_script=custom_script
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
            "message": "Drop generated!" + (" (Neural voice)" if result["tts_engine"] == "edge" else " (Basic audio)" if result["tts_engine"] == "espeak" else " (Audio unavailable - install FFmpeg for full features)")
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
# 6) APP STARTUP
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("   PREMIUM AI DJ DROP FACTORY - RENDER CLOUD EDITION")
    print("=" * 60)
    print("Features:")
    print(f"  - Script AI: ALWAYS WORKS")
    print(f"  - Neural TTS: {'YES' if has_internet() else 'NO (no internet)'}")
    print(f"  - FFmpeg FX: {'YES' if FFMPEG_AVAILABLE else 'NO (install for audio)'}")
    print(f"  - Offline TTS: {'YES' if ESPEAK_AVAILABLE else 'NO (install espeak-ng)'}")
    print("=" * 60)
    print("Open browser: http://127.0.0.1:5000")
    print("Press CTRL+C to stop")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
