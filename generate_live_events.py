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
    "thetvapp",
    "thetvapp sd",
}

# =============================
# PROVIDER NORMALIZATION
# =============================
PROVIDER_ALIASES = {
    "pixelsports": "Pixel Sports",
    "ppvland": "PPV Land",
    "tvpass": "TVPASS",
    "thetvapp": "TheTVApp",
    "streamedsu": "StreamedSU",
    "buddylive": "Buddy Live",
    "buddy": "Buddy",
}

# =============================
# SPORT DETECTION (FOR NAMING)
# =============================
SPORT_KEYWORDS = [
    "NFL", "NBA", "NHL", "MLB",
    "NCAAF", "NCAAB",
    "Football", "Basketball", "Hockey",
    "Baseball", "Cricket", "Darts",
    "Fight", "UFC", "MMA"
]

# =============================
# HELPERS
# =============================
def norm(text):
    return (text or "").strip()

def norm_lower(text):
    return norm(text).lower()

def is_blacklisted(group):
    return norm_lower(group) in CATEGORY_BLACKLIST

def extract_provider(group):
    g = norm_lower(group)
    for key, name in PROVIDER_ALIASES.items():
        if key in g:
            return name
    return "Other"

def extract_sport(group):
    for sport in SPORT_KEYWORDS:
        if sport.lower() in norm_lower(group):
            return sport
    return None

# =============================
# LOAD SOURCES
# =============================
with open("sources.json", "r", encoding="utf-8") as f:
    SOURCES = json.load(f)

# =============================
# PROCESS PLAYLISTS
# =============================
categories = defaultdict(list)
seen_stream_urls = set()

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

            # DEDUPE — URL ONLY
            if stream_url in seen_stream_urls:
                current_extinf = None
                current_group = None
                continue

            seen_stream_urls.add(stream_url)

            # CATEGORY BLACKLIST ONLY
            if is_blacklisted(current_group):
                current_extinf = None
                current_group = None
                continue

            provider = extract_provider(current_group)
            sport = extract_sport(current_group)

            if sport:
                final_group = f"{sport} | {provider}"
            else:
                final_group = f"Events | {provider}"

            categories[final_group].append((current_extinf, stream_url))

            current_extinf = None
            current_group = None

# =============================
# WRITE OUTPUT
# =============================
os.makedirs("docs", exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
    out.write("#EXTM3U\n\n")

    for category in sorted(categories.keys()):
        for extinf, url in categories[category]:
            cleaned_extinf = re.sub(
                r'group-title="[^"]+"',
                f'group-title="{category}"',
                extinf
            )
            out.write(f"{cleaned_extinf}\n{url}\n")
