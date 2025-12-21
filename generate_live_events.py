import json
import os
import re
import sys
from typing import Dict, List, Tuple

import requests

DEFAULT_TIMEOUT = 30

EVENT_KEYWORDS = [
    "event", "events", "live", "ppv",
    "nfl", "football", "nba", "wnba", "nhl", "mlb", "ncaa",
    "soccer", "epl", "mls", "uefa",
    "ufc", "mma", "boxing", "fight",
    "formula", "f1", "nascar",
    "golf", "tennis",
    "poker",
]

REDZONE_KEYWORDS = ["red zone", "redzone"]

# Categories we NEVER want in a live-events playlist
BLOCKED_GROUP_KEYWORDS = [
    "24/7",
    "movie",
    "movies",
    "program",
    "programs",
    "news",
    "radio",
    "music",
    "moveonjoy",
    "temp",
]

GROUP_PRIORITY = [
    ("red zone", 0),
    ("nfl", 10), ("football", 11),
    ("ncaa", 20),
    ("nba", 30), ("wnba", 31),
    ("nhl", 40),
    ("mlb", 50),
    ("soccer", 60),
    ("ufc", 70), ("mma", 71), ("boxing", 72),
    ("formula", 80),
    ("golf", 90),
    ("tennis", 91),
    ("live", 200),
    ("event", 210),
]


def norm(s: str) -> str:
    return (s or "").strip().lower()


def is_blocked_group(group_title: str) -> bool:
    g = norm(group_title)
    return any(b in g for b in BLOCKED_GROUP_KEYWORDS)


def is_redzone(name: str) -> bool:
    n = norm(name)
    return any(k in n for k in REDZONE_KEYWORDS)


def looks_like_event(group_title: str, channel_name: str) -> bool:
    hay = f"{norm(group_title)} {norm(channel_name)}"
    return any(k in hay for k in EVENT_KEYWORDS)


def group_rank(group_title: str) -> Tuple[int, str]:
    gt = norm(group_title)
    best = 9999
    for key, score in GROUP_PRIORITY:
        if key in gt:
            best = min(best, score)
    return best, gt


def fetch_text(url: str) -> str:
    r = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": "live-events-bot/1.3"},
    )
    r.raise_for_status()
    return r.text


def parse_extinf_attrs(extinf_line: str) -> Dict[str, str]:
    attrs = {}
    for m in re.finditer(r'([\w-]+)\s*=\s*"([^"]*)"', extinf_line):
        attrs[m.group(1)] = m.group(2)
    return attrs


def parse_m3u_entries(m3u_text: str) -> List[Dict[str, str]]:
    lines = [ln.strip() for ln in m3u_text.splitlines() if ln.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:"):
            extinf = lines[i]
            url = lines[i + 1] if i + 1 < len(lines) else ""
            name = extinf.split(",", 1)[1] if "," in extinf else ""
            attrs = parse_extinf_attrs(extinf)
            group = attrs.get("group-title", "")
            entries.append({
                "extinf": extinf,
                "url": url,
                "name": name,
                "group": group,
            })
            i += 2
        else:
            i += 1
    return entries


def build_output(sources: List[Dict[str, str]]) -> str:
    grouped = {"RED ZONE": []}
    seen_urls = set()

    for src in sources:
        src_name = src.get("name", "").strip()
        src_url = src.get("url", "").strip()
        if not src_name or not src_url:
            continue

        try:
            text = fetch_text(src_url)
        except Exception as e:
            print(f"WARNING: {src_name} failed: {e}", file=sys.stderr)
            continue

        for ent in parse_m3u_entries(text):
            stream_url = ent["url"]
            if not stream_url or stream_url.startswith("#"):
                continue

            # RED ZONE
            if is_redzone(ent["name"]):
                if stream_url not in seen_urls:
                    seen_urls.add(stream_url)
                    grouped["RED ZONE"].append(ent)
                continue

            # Block junk categories
            if is_blocked_group(ent["group"]):
                continue

            # Live / event logic
            if looks_like_event(ent["group"], ent["name"]):
                if stream_url in seen_urls:
                    continue
                seen_urls.add(stream_url)
                group_name = (
                    f"{src_name} | {ent['group']}".strip()
                    if ent["group"] else f"{src_name} | Events"
                )
                grouped.setdefault(group_name, []).append(ent)

    out = ["#EXTM3U"]

    for group in sorted(grouped.keys(), key=lambda g: group_rank(g)):
        for ent in sorted(grouped[group], key=lambda e: norm(e["name"])):
            extinf = ent["extinf"]
            if 'group-title="' in extinf:
                extinf = re.sub(
                    r'group-title="[^"]*"',
                    f'group-title="{group}"',
                    extinf
                )
            else:
                left, right = extinf.split(",", 1)
                extinf = f'{left} group-title="{group}",{right}'
            out.append(extinf)
            out.append(ent["url"])

    return "\n".join(out) + "\n"


def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    os.makedirs("docs", exist_ok=True)
    playlist = build_output(sources)

    with open("docs/live-events.m3u", "w", encoding="utf-8") as f:
        f.write(playlist)


if __name__ == "__main__":
    main()
