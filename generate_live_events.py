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
    "events | ppv land",  # per your request
}

# =============================
# PROVIDER NORMALIZATION
# =============================
PROVIDER_ALIASES = {
    "pixelsports": "Pixel Sports",
    "ppvland": "PPV Land",
    "tvpass": "TheTVApp",   # tvpass feed is TheTVApp
    "thetvapp": "TheTVApp",
    "streamedsu": "StreamedSU",
    "streamsu": "StreamSU",
    "buddylive": "Buddy Live",
    "buddy": "Buddy",
}

# =============================
# PROVIDER PRIORITY (LOWER WINS)
# This fixes TVPASS NHL getting eaten by duplicates.
# =============================
PROVIDER_PRIORITY = {
    "TheTVApp": 1,      # TVPASS first
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
    # IMPORTANT: only look at group-title, not channel name
    g = norm_lower(group_title)
    for sport in SPORT_KEYWORDS:
        if sport.lower() in g:
            return sport
    return None

def is_blacklisted(final_group):
    return norm_lower(final_group) in CATEGORY_BLACKLIST

def provider_rank(provider):
    return PROVIDER_PRIORITY.get(provider, 99)

# =============================
# LOAD SOURCES
# =============================
with open("sources.json", "r", encoding="utf-8") as f:
    SOURCES = json.load(f)

# categories[category][url] = extinf
categories = defaultdict(dict)

# url_map[url] = (provider, category)
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

            # Drop Favorites immediately (source label)
            if original_group_l == "favorites":
                current_extinf = None
                current_group = None
                continue

            provider = extract_provider(original_group or source_name)

            # -------------------------
            # CATEGORY NAMING RULES
            # -------------------------

            # StreamedSU: if the SOURCE group-title is "Other", it MUST stay Other.
            if provider == "StreamedSU" and original_group_l == "other":
                final_group = "Other | StreamedSU"

            else:
                sport = extract_sport_from_group(original_group)

                # PPV Land Football rename
                if provider == "PPV Land" and sport == "Football":
                    final_group = "Global Football Streams | PPV Land"
                elif sport:
                    final_group = f"{sport} | {provider}"
                else:
                    # keep original group as label if it’s meaningful, otherwise Events
                    # (This preserves "Events" buckets and avoids lying)
                    base = original_group if original_group else "Events"
                    # Avoid absurd long names: keep it simple
                    if base.lower() in ("events", "event", "live events"):
                        base = "Events"
                    final_group = f"{base} | {provider}" if base != provider else f"Events | {provider}"

            # Blacklist ONLY by final group name
            if is_blacklisted(final_group):
                current_extinf = None
                current_group = None
                continue

            # -------------------------
            # DEDUPE BY URL ONLY, WITH PROVIDER PRIORITY
            # -------------------------
            if stream_url in url_map:
                prev_provider, prev_category = url_map[stream_url]
                if provider_rank(provider) < provider_rank(prev_provider):
                    # Replace: remove from old category, add to new
                    if stream_url in categories[prev_category]:
                        del categories[prev_category][stream_url]
                    categories[final_group][stream_url] = current_extinf
                    url_map[stream_url] = (provider, final_group)
                # else: keep existing, discard this one
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
