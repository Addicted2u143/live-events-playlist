import json
import requests
import re
import os
from collections import defaultdict

OUTPUT_PATH = "docs/live-events.m3u"

# =============================
# EXPLICIT CATEGORY BLACKLIST
# =============================
CATEGORY_BLACKLIST = {
    "favorites",
    "24/7 movies",
    "24/7 programs",
    "radio",
    "radio / music",
    "music",
    "local tv",
    "moveonjoy+",
    "news other",
    "sport outdoors",
}

# =============================
# PROVIDER NORMALIZATION
# =============================
PROVIDER_ALIASES = {
    "pixelsports": "Pixel Sports",
    "ppvland": "PPV Land",
    "tvpass": "TheTVApp",
    "thetvapp": "TheTVApp",
    "streamedsu": "StreamedSU",
    "streamsu": "StreamedSU",
    "buddylive": "Buddy Live",
    "buddy": "Buddy",
}

# =============================
# PROVIDER PRIORITY (LOWER WINS)
# =============================
PROVIDER_PRIORITY = {
    "TheTVApp": 1,
    "PPV Land": 2,
    "StreamedSU": 3,
    "Pixel Sports": 4,
    "Buddy": 5,
    "Buddy Live": 6,
    "Other": 99,
}

# =============================
# SPORT KEYWORDS (GROUP-TITLE ONLY)
# =============================
SPORT_KEYWORDS = [
    "NFL", "NBA", "NHL", "MLB",
    "NCAAF", "NCAAB",
    "Football", "Basketball", "Hockey",
    "Baseball", "Cricket", "Darts",
    "Fight", "UFC", "MMA", "Soccer"
]

# =============================
# HELPERS
# =============================
def norm(text):
    return (text or "").strip()

def norm_lower(text):
    return norm(text).lower()

def extract_provider(text):
    t = norm_lower(text)
    for key, name in PROVIDER_ALIASES.items():
        if key in t:
            return name
    return "Other"

def extract_sport_from_group(group_title):
    g = norm_lower(group_title)
    for sport in SPORT_KEYWORDS:
        if sport.lower() in g:
            return sport
    return None

def is_blacklisted(final_group):
    return norm_lower(final_group) in CATEGORY_BLACKLIST

def provider_rank(provider):
    return PROVIDER_PRIORITY.get(provider, 99)

def is_allowed_final_group(final_group):
    """Hard gate: prevent Live TV / full channel dumps"""
    g = norm_lower(final_group)

    if g.startswith("events |") or g.startswith("live events |"):
        return True

    if any(g.startswith(s.lower() + " |") for s in [k.lower() for k in SPORT_KEYWORDS]):
        return True

    return False

# =============================
# LOAD SOURCES
# =============================
with open("sources.json", "r", encoding="utf-8") as f:
    SOURCES = json.load(f)

categories = defaultdict(dict)
url_map = {}

# =============================
# PROCESS
# =============================
for source in SOURCES:
    source_name = source.get("name", "Unknown")
    url = source.get("url")

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        lines = resp.text.splitlines()
    except Exception:
        continue

    current_extinf = None
    current_group = None

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF"):
            current_extinf = line
            m = re.search(r'group-title="([^"]+)"', line)
            current_group = m.group(1) if m else source_name

        elif line.startswith("http") and current_extinf:
            stream_url = line
            original_group = norm(current_group or source_name)
            original_group_l = norm_lower(original_group)

            if original_group_l == "favorites":
                current_extinf = None
                current_group = None
                continue

            provider = extract_provider(original_group or source_name)

            # -------- CATEGORY LOGIC --------
            sport = extract_sport_from_group(original_group)

            if provider == "PPV Land" and sport == "Football":
                final_group = "Global Football Streams | PPV Land"
            elif sport:
                final_group = f"{sport} | {provider}"
            else:
                base = original_group if original_group else "Events"
                if base.lower() in ("events", "event", "live events"):
                    base = "Events"
                final_group = f"{base} | {provider}"

            # HARD FILTERS
            if is_blacklisted(final_group):
                current_extinf = None
                current_group = None
                continue

            if not is_allowed_final_group(final_group):
                current_extinf = None
                current_group = None
                continue

            # -------- DEDUPE (URL ONLY) --------
            if stream_url in url_map:
                prev_provider, prev_category = url_map[stream_url]
                if provider_rank(provider) < provider_rank(prev_provider):
                    if stream_url in categories[prev_category]:
                        del categories[prev_category][stream_url]
                    categories[final_group][stream_url] = current_extinf
                    url_map[stream_url] = (provider, final_group)
            else:
                categories[final_group][stream_url] = current_extinf
                url_map[stream_url] = (provider, final_group)

            current_extinf = None
            current_group = None

# =============================
# WRITE OUTPUT
# =============================
os.makedirs("docs", exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
    out.write("#EXTM3U\n\n")
    for category in sorted(categories.keys()):
        for url, extinf in categories[category].items():
            cleaned = re.sub(
                r'group-title="[^"]+"',
                f'group-title="{category}"',
                extinf
            )
            out.write(f"{cleaned}\n{url}\n")
