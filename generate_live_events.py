# --- SNIP: imports unchanged ---

OUTPUT_PATH = "docs/live-events.m3u"

# =============================
# EXPLICIT CATEGORY BLACKLIST
# (ONLY junk, NEVER real events)
# =============================
CATEGORY_BLACKLIST = {
    "favorites",
    "24/7 movies | other",
    "24/7 programs | other",
    "radio | other",
    "radio/music | other",
    "local tv | other",
    "moveonjoy+ | other",
    "news other | other",
    "sport outdoors | other",
}

# --- providers, priorities, helpers UNCHANGED ---

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
                continue

            provider = extract_provider(original_group or source_name)

            # -------------------------
            # CATEGORY RULES
            # -------------------------
            if provider == "StreamedSU" and original_group_l == "other":
                final_group = "Other | StreamedSU"
            else:
                sport = extract_sport_from_group(original_group)

                if provider == "PPV Land" and sport == "Football":
                    final_group = "Global Football Streams | PPV Land"
                elif sport:
                    final_group = f"{sport} | {provider}"
                else:
                    base = original_group if original_group else "Events"
                    if base.lower() in ("event", "events", "live events"):
                        base = "Events"
                    final_group = f"{base} | {provider}"

            # Blacklist only explicit junk
            if norm_lower(final_group) in CATEGORY_BLACKLIST:
                current_extinf = None
                continue

            # -------------------------
            # DEDUPE BY URL ONLY
            # -------------------------
            if stream_url in url_map:
                prev_provider, prev_category = url_map[stream_url]
                if provider_rank(provider) < provider_rank(prev_provider):
                    categories[prev_category].pop(stream_url, None)
                    categories[final_group][stream_url] = current_extinf
                    url_map[stream_url] = (provider, final_group)
            else:
                categories[final_group][stream_url] = current_extinf
                url_map[stream_url] = (provider, final_group)

            current_extinf = None

# =============================
# WRITE OUTPUT (GUARDRAIL)
# =============================
total = sum(len(v) for v in categories.values())
if total == 0:
    raise RuntimeError("ABORT: zero channels survived filtering")

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
