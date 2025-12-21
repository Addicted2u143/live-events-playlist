import json
import requests
import re
from collections import defaultdict

OUTPUT_PATH = "docs/live-events.m3u"

# -----------------------------
# CATEGORY BLACKLIST (EXPLICIT)
# -----------------------------
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

# -----------------------------
# PROVIDER NORMALIZATION
# -----------------------------
PROVIDER_ALIASES = {
    "pixelsports": "Pixel Sports",
    "ppvland": "PPV Land",
    "tvpass": "TVPASS",
    "thetvapp": "TheTVApp",
    "streamedsu": "StreamedSU",
    "buddy": "Buddy",
}

SPORT_KEYWORDS = [
    "NFL", "NBA", "NHL", "MLB",
    "NCAAF", "NCAAB",
    "Football", "Basketball", "Hockey", "Baseball",
    "Fight", "Cricket", "Darts"
]

# -----------------------------
# HELPERS
# -----------------------------
def norm(text):
    return (text or "").strip()

def norm_lower(text):
    return norm(text).lower()

def extract_provider(group):
    for key, val in PROVIDER_ALIASES.items():
        if key in norm_lower(group):
            return val
    return "Other"

def extract_sport(group):
    for sport in SPORT_KEYWORDS:
        if sport.lower() in norm_lower(group):
            return sport
    return None

def is_blacklisted(group):
    return norm_lower(group) in CATEGORY_BLACKLIST

# -----------------------------
# LOAD SOURCES
# -----------------------------
with open("sources.json", "r", encoding="utf-8") as f:
    SOURCES = json.load(f)

# -----------------------------
# PROCESS
# -----------------------------
categories = defaultdict(list)
seen_stream_urls = set()

for source in SOURCES:
    source_name = source.get("name", "Unknown")
    url = source.get("url")

    try:
        resp = requests.get(url, timeout=15)
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

            group_match = re.search(r'group-title="([^"]+)"', line)
            current_group = group_match.group(1) if group_match else source_name

        elif line.startswith("http") and current_extinf:
            stream_url = line

            # DEDUPE BY STREAM URL ONLY
            if stream_url in seen_stream_urls:
                continue
            seen_stream_urls.add(stream_url)

            if is_blacklisted(current_group):
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

# -----------------------------
# WRITE PLAYLIST
#
