import json
import requests
import re
import os
from collections import defaultdict

OUTPUT_PATH = "docs/live-events.m3u"

# =============================
# SAFE CATEGORY BLACKLIST
# =============================
CATEGORY_BLACKLIST = {
    "24/7 movies | other",
    "24/7 programs | other",
    "radio | other",
    "radio/music | other",
    "local tv | other",
    "moveonjoy+ | other",
    "news other | other",
    "sport outdoors | other",
    "sports temp 1 | other",
    "sports temp 2 | other",
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
    "buddy": "Buddy",
}

# =============================
# PROVIDER PRIORITY
# =============================
PROVIDER_PRIORITY = {
    "TheTVApp": 1,
    "PPV Land": 2,
    "StreamedSU": 3,
    "Pixel Sports": 4,
    "Buddy": 5,
    "Other": 99,
}

# =============================
# SPORT KEYWORDS (GROUP TITLE ONLY)
# =============================
SPORT_KEYWORDS = [
    "NFL", "NBA", "NHL", "MLB",
    "NCAAF", "NCAAB",
    "Football", "Basketball", "Hockey",
    "Baseball", "Cricket", "Darts",
    "Fight", "UFC", "MMA", "Soccer",
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

def extract_sport(group_title):
    g = norm_lower(group_title)
    for sport in SPORT_KEYWORDS:
        if sport.lower() in g:
            return sport
    return None

def is_blacklisted(category):
    return norm_lower(category) in CATEGORY_BLACKLIST

def provider_rank(provider):
    return PROVIDER_PRIORITY.get(provider, 99)

# =============================
# LOAD SOURCES
# =============================
with open("sources.json", "r", encoding="utf-8") as f:
    SOURCES = json.load(f)

categories = defaultdict(dict)
url_map = {}

# =============================
# PROCESS SOURCES
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
            base_group = norm(current_group or source_name)
            provider = extract_provider(base_group)

            sport = extract_sport(base_group)

            if provider == "StreamedSU" and base_group.lower() == "other":
                final_group = "StreamedSU - Other | StreamedSU"
            elif provider == "PPV Land" and sport == "Football":
                final_group = "Global Football Streams | PPV Land"
            elif sport:
                final_group = f"{sport} | {provider}"
            else:
                base = base_group if base_group else "Live"
                final_group = f"{base} | {provider}"

            if is_blacklisted(final_group):
                current_extinf = None
                continue

            if stream_url in url_map:
                prev_provider, prev_group = url_map[stream_url]
                if provider_rank(provider) < provider_rank(prev_provider):
                    del categories[prev_group][stream_url]
                else:
                    current_extinf = None
                    continue

            categories[final_group][stream_url] = current_extinf
            url_map[stream_url] = (provider, final_group)

            current_extinf = None

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
