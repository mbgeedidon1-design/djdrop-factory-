import json
import random
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

WAITLIST_FILE = DATA_DIR / "waitlist.json"

VOICE_MAP = {
    "1": "Deep Studio Heavy Voice",
    "2": "Crisp Energetic Host",
    "3": "Smooth Female Vibe",
    "4": "Afro Hype Host",
    "5": "Radio Queen",
    "6": "Trap Voice"
}

GENRE_BANK = {
    "club_banger": {
        "openers": ["Hands up!", "Main event settings!", "Turn it up!", "Brace yourself!"],
        "energy": ["wall-to-wall energy", "shutdown mode", "club destruction", "full pressure"],
        "closers": ["Let's go!", "Make some noise!", "No sleep tonight!", "Take it higher!"]
    },
    "amapiano": {
        "openers": ["Yanos to the world!", "Private school vibes!", "Log drum pressure!"],
        "energy": ["strictly smooth pressure", "piano vibes only", "deep groove settings", "elite nightlife vibes"],
        "closers": ["We move!", "Piano vibes only!", "Amapiano to the world!", "Lock in the groove!"]
    },
    "afrobeat": {
        "openers": ["Afro vibes!", "Worldwide groove!", "Wave after wave!"],
        "energy": ["sweet afro pressure", "global rhythm", "steady groove and vibes", "melodic nightlife energy"],
        "closers": ["Feel the rhythm!", "Vibes non-stop!", "All love and energy!", "We outside!"]
    },
    "dancehall": {
        "openers": ["Brap brap!", "Pull up selectah!", "Mad ting!"],
        "energy": ["riddim pressure", "dangerous dancehall fire", "sound system active", "reload after reload"],
        "closers": ["Forward di ting!", "Pull it up!", "Run the tune!", "Madness only!"]
    },
    "radio": {
        "openers": ["You're locked in.", "Live on air.", "Stay tuned."],
        "energy": ["premium broadcast energy", "the sound of the city", "top-tier radio pressure", "fresh exclusive vibes"],
        "closers": ["Keep it locked.", "More heat on the way.", "Don't touch that dial.", "Premium sound only."]
    },
    "trap": {
        "openers": ["808 warning!", "Bassline alert!", "Pressure mode!"],
        "energy": ["heavyweight bass pressure", "dark energy", "sub-heavy madness", "late-night danger"],
        "closers": ["Let it knock!", "Shake the walls!", "Run it back!", "Take it louder!"]
    }
}


def load_waitlist():
    if WAITLIST_FILE.exists():
        try:
            with open(WAITLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_waitlist(items):
    with open(WAITLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def clean_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def generate_drop(dj_name, genre, city="", drop_type="intro", energy=8):
    genre = (genre or "club_banger").strip().lower()
    if genre not in GENRE_BANK:
        genre = "club_banger"

    dj_name = clean_text(dj_name) or "DJ Beshi"
    city = clean_text(city)

    bank = GENRE_BANK[genre]
    opener = random.choice(bank["openers"])
    energy_line = random.choice(bank["energy"])
    closer = random.choice(bank["closers"])

    city_part = f" in {city}" if city else ""

    options = [
        f"{opener} {dj_name}{city_part} is in full effect. {energy_line.capitalize()}! {closer}",
        f"{opener} Locked in with {dj_name}{city_part}. {energy_line.capitalize()}! {closer}",
        f"{dj_name}{city_part} taking over the sound. {energy_line.capitalize()}! {closer}",
    ]

    if drop_type == "promo":
        options = [
            f"{dj_name} invites you{city_part}. Get ready for a premium {genre.replace('_', ' ')} experience. {closer}",
            f"{opener} {dj_name}{city_part} is bringing live energy and {energy_line}. Pull up and experience the vibe!",
        ]
    elif drop_type == "radio":
        options = [
            f"You're locked in with {dj_name}{city_part}. {energy_line.capitalize()}. Premium radio sound only.",
            f"Live on air with {dj_name}{city_part}. {energy_line.capitalize()}. Stay tuned for more heat."
        ]
    elif drop_type == "hype":
        options = [
            f"{opener} {dj_name}{city_part}! {energy_line.capitalize()}! {closer}",
            f"{dj_name}{city_part} in the building! {energy_line.capitalize()}! Make some noise!"
        ]

    return random.choice(options)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "success": True,
        "app": "DJ DROP FACTORY",
        "mode": "temporary_public_app",
        "message": "Public preview is live while the full studio upgrade is in progress."
    })


@app.route("/api/voices")
def api_voices():
    return jsonify({
        "success": True,
        "voices": VOICE_MAP
    })


@app.route("/api/preview_script", methods=["POST"])
def preview_script():
    data = request.get_json(silent=True) or {}
    dj_name = data.get("dj_name", "")
    genre = data.get("genre", "club_banger")
    city = data.get("city", "")
    drop_type = data.get("drop_type", "intro")
    energy = int(data.get("energy", 8))

    previews = []
    for _ in range(3):
        previews.append(generate_drop(dj_name, genre, city, drop_type, energy))

    return jsonify({
        "success": True,
        "best": previews[0],
        "scripts": previews
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}

    dj_name = data.get("dj_name", "")
    genre = data.get("genre", "club_banger")
    city = data.get("city", "")
    drop_type = data.get("drop_type", "intro")
    energy = int(data.get("energy", 8))
    voice = data.get("voice", "1")

    script = generate_drop(dj_name, genre, city, drop_type, energy)

    return jsonify({
        "success": True,
        "message": "Preview drop generated successfully.",
        "project": f"preview-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "script": script,
        "voice_label": VOICE_MAP.get(str(voice), "Auto Voice"),
        "note": "This is the temporary public preview build. Full audio generation is being upgraded."
    })


@app.route("/api/waitlist", methods=["POST"])
def waitlist():
    data = request.get_json(silent=True) or {}

    name = clean_text(data.get("name", ""))
    phone = clean_text(data.get("phone", ""))
    email = clean_text(data.get("email", ""))
    note = clean_text(data.get("note", ""))

    if not name and not phone and not email:
        return jsonify({"success": False, "error": "Provide at least a name, phone, or email."}), 400

    items = load_waitlist()
    row = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "name": name,
        "phone": phone,
        "email": email,
        "note": note,
        "created_at": datetime.now().isoformat()
    }
    items.insert(0, row)
    save_waitlist(items)

    return jsonify({
        "success": True,
        "message": "Saved successfully. We’ll reach out when the full studio version is live.",
        "entry": row
    })


@app.route("/api/waitlist", methods=["GET"])
def get_waitlist():
    items = load_waitlist()
    return jsonify({
        "success": True,
        "count": len(items),
        "entries": items[:100]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True
