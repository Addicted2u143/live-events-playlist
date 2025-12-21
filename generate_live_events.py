import json
import requests
import re
import os
from collections import defaultdict

OUTPUT_PATH = "docs/live-events.m3u"
SOURCES_PATH = "sources.json"

# =============================
# BLACKLIST (SAFE MODE)
# Base labels ONLY – never sports or live events
# =============================
CATEGORY_BLACKLIST = {
    "24/7 movies",
    "24/7 programs",
    "radio",
    "radio/music",
    "local tv",
    "moveonjoy+",
    "news other",
    "sport outdoors",
    "ppvland - live channels 24/7",
    "sports temp 1",
    "sports temp 2",
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
    "streamsu": "StreamSU",
    "buddylive": "Buddy Live",
    "buddy": "Buddy",
}

# =============================
# PROVIDER PRIORITY (lower = wins)
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

SPORT_KEYWORDS = [
    "NFL", "NBA", "NHL", "MLB",
    "NCAAF", "NCAAB",
    "Football", "Basketball",
    "Hockey", "Baseball",
    "Cricket", "Darts",
    "Soccer", "UFC", "MMA"
]

# =============================
# HELPERS
# =============================
def norm(t): return (t or "").strip()
def low(t): return norm(t).lower()

def extract_provider(text):
    t = low(text)
    for k, v in PROVIDER_ALIASES.items():
        if k in t:
            return v
    return "Other"

def extract_sport(group):
    g = low(group)
    for s in SPORT_KEYWORDS:
        if s.lower() in g:
            return s
    return None

def provider_rank(p):
    return PROVIDER_PRIORITY.get(p, 99)

def is_blacklisted(base_label):
    return low(base_label) in CATEGORY_BLACKLIST

# =============================
# LOAD SOURCES (FIXES YOUR ERROR)
# =============================
with open(SOURCES_PATH, "r", encoding="utf-8") as f:
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

    extinf = None
    group = None

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF"):
            extinf = line
            m = re.search(r'group-title="([^"]+)"', line)
            group = m.group(1) if m else source_name

        elif line.startswith("http") and extinf:
            stream_url = line
            base_group = norm(group or source_name)
            base_lower = low(base_group)

            provider = extract_provider(base_group)

            # -------- STREAMEDSU RULE --------
            if provider == "StreamedSU" and base_lower == "other":
                final_group = "Other | StreamedSU"

            else:
                sport = extract_sport(base_group)

                if provider == "PPV Land" and sport == "Football":
                    final_group = "Global Football Streams | PPV Land"
                elif sport:
                    final_group = f"{sport} | {provider}"
                else:
                    label = base_group if base_group else "Events"
                    final_group = f"{label} | {provider}"

            # -------- BLACKLIST CHECK (SAFE) --------
            base_label = final_group.split("|")[0].strip()
            if is_blacklisted(base_label):
                extinf = None
                group = None
                continue

            # -------- DEDUPE BY URL ONLY --------
            if stream_url in url_map:
                prev_provider, prev_cat = url_map[stream_url]
                if provider_rank(provider) < provider_rank(prev_provider):
                    categories[prev_cat].pop(stream_url, None)
                    categories[final_group][stream_url] = extinf
                    url_map[stream_url] = (provider, final_group)
            else:
                categories[final_group][stream_url] = extinf
                url_map[stream_url] = (provider, final_group)

            extinf = None
            group = None

# =============================
# WRITE OUTPUT
# =============================
os.makedirs("docs", exist_ok=True)

with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
    out.write("#EXTM3U\n\n")
    for cat in sorted(categories.keys()):
        for url, extinf in categories[cat].items():
            clean = re.sub(r'group-title="[^"]+"',
                           f'group-title="{cat}"',
                           extinf)
            out.write(f"{clean}\n{url}\n")
