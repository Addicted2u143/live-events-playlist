import json
import os
import re
import sys
from typing import Dict, List, Tuple

import requests

DEFAULT_TIMEOUT = 30

EVENT_KEYWORDS = [
    "event", "events", "live", "ppv", "pay per view",
    "nfl", "football", "nba", "wnba", "nhl", "mlb", "ncaa",
    "soccer", "epl", "mls", "uefa", "champions league",
    "ufc", "mma", "boxing", "fight", "fights", "wwe", "aew",
    "golf", "pga", "tennis", "atp", "wta",
    "formula", "f1", "nascar", "motorsport", "motorsports",
    "cricket", "ipl", "rugby", "darts",
    "poker",
]

REDZONE_KEYWORDS = ["red zone", "redzone"]

# Lower number = higher in the playlist
GROUP_PRIORITY = [
    ("red zone", 0),
    ("nfl", 10), ("football", 11),
    ("ncaa", 20),
    ("nba", 30), ("wnba", 31),
    ("nhl", 40),
    ("mlb", 50),
    ("soccer", 60), ("epl", 61), ("uefa", 62), ("mls", 63),
    ("ufc", 70), ("mma", 71), ("boxing", 72), ("fight", 73), ("ppv", 74),
    ("formula", 80), ("f1", 81), ("nascar", 82), ("motorsport", 83),
    ("golf", 90), ("tennis", 91),
    ("poker", 95),
    ("live", 200),
    ("event", 210), ("events", 211),
]


def norm(s: str) -> str:
    return (s or "").strip().lower()


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
        headers={"User-Agent": "live-events-bot/1.0"},
    )
    r.raise_for_status()
    return r.text


def parse_extinf_attrs(extinf_line: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for m in re.finditer(r'([\w-]+)\s*=\s*"([^"]*)"', extinf_line):
        attrs[m.group(1)] = m.group(2)
    return attrs


def parse_m3u_entries(m3u_text: str) -> List[Dict[str, str]]:
    lines = [ln.rstrip("\n") for ln in m3u_text.splitlines() if ln.strip()]
    entries: List[Dict[str, str]] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("#EXTINF:"):
            extinf = ln
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            name = extinf.split(",", 1)[1].strip() if "," in extinf else ""
            attrs = parse_extinf_attrs(extinf)
            group = attrs.get("group-title", "").strip()
            entries.append(
                {
                    "extinf": extinf,
                    "url": url,
                    "name": name,
                    "group": group,
                }
            )
            i += 2
        else:
            i += 1
    return entries


def build_output(sources: List[Dict[str, str]]) -> str:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    seen_urls = set()

    # Always include RED ZONE category (even if empty)
    grouped["RED ZONE"] = []

    for src in sources:
        src_name = (src.get("name") or "").strip()
        url = (src.get("url") or "").strip()

        if not src_name or not url:
            continue

        try:
            text = fetch_text(url)
        except Exception as e:
            print(f"WARNING: Failed to fetch {src_name}: {e}", file=sys.stderr)
            continue

        entries = parse_m3u_entries(text)

        for ent in entries:
            stream_url = ent.get("url") or ""
            if not stream_url or stream_url.startswith("#"):
                continue

            # RED ZONE capture first (by channel name only)
            if is_redzone(ent.get("name", "")):
                if stream_url not in seen_urls:
                    seen_urls.add(stream_url)
                    grouped["RED ZONE"].append(ent)
                continue

            # Live/event capture (by group-title OR name keywords)
            if looks_like_event(ent.get("group", ""), ent.get("name", "")):
                if stream_url in seen_urls:
                    continue

                seen_urls.add(stream_url)
                out_group = (
                    f"{src_name} | {ent['group']}".strip()
                    if ent.get("group")
                    else f"{src_name} | (No Group)"
                )
                grouped.setdefault(out_group, []).append(ent)

    group_names = sorted(grouped.keys(), key=lambda g: group_rank(g))

    out_lines = ["#EXTM3U"]

    for gname in group_names:
        ents_sorted = sorted(grouped[gname], key=lambda e: norm(e.get("name", "")))

        for ent in ents_sorted:
            extinf = ent["extinf"]

            # Force group-title to output group name
            if 'group-title="' in extinf:
                extinf = re.sub(r'group-title="[^"]*"', f'group-title="{gname}"', extinf)
            else:
                if "," in extinf:
                    left, right = extinf.split(",", 1)
                    extinf = f'{left} group-title="{gname}",{right}'
                else:
                    extinf = f'{extinf} group-title="{gname}"'

            out_lines.append(extinf)
            out_lines.append(ent["url"])

    return "\n".join(out_lines) + "\n"


def main() -> None:
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    os.makedirs("docs", exist_ok=True)
    output = build_output(sources)

    with open("docs/live-events.m3u", "w", encoding="utf-8") as f:
        f.write(output)


if __name__ == "__main__":
    main()
