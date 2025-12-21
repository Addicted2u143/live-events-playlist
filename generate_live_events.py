import requests
from collections import OrderedDict

PLAYLIST_URLS = [
    # keep your existing list here
]

OUTPUT_FILE = "docs/live-events.m3u"

BLACKLIST_GROUPS = {
    "24/7 Movies | Other",
    "24/7 Programs | Other",
    "Live | Other",
    "Local TV | Other",
    "MoveOnJoy+ | Other",
    "Radio/Music | Other",
    "Sport Outdoors | Other",
    "Sports Temp 1 | Other",
    "Sports Temp 2 | Other",
    "News Other | Other",
    "PPVLand - Live Channels 24/7 | PPV Land"
}

PROTECTED_GROUP_PREFIXES = (
    "Events |",
    "PPVLand - Combat Sports |"
)

def fetch_playlist(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text.splitlines()

def parse_playlists():
    entries = OrderedDict()

    for url in PLAYLIST_URLS:
        lines = fetch_playlist(url)
        current_meta = None

        for line in lines:
            if line.startswith("#EXTINF"):
                current_meta = line
            elif line.startswith("http") and current_meta:
                stream_url = line.strip()

                # Extract group-title
                group = ""
                if 'group-title="' in current_meta:
                    group = current_meta.split('group-title="')[1].split('"')[0]

                # Extract source name (fallback safe)
                source = group.split(" - ")[0] if " - " in group else group

                # Normalize final group name
                final_group = f"{group} | {source}".strip(" |")

                # Blacklist check
                if (
                    final_group in BLACKLIST_GROUPS
                    and not final_group.startswith(PROTECTED_GROUP_PREFIXES)
                ):
                    current_meta = None
                    continue

                # Deduplicate ONLY by stream URL
                if stream_url not in entries:
                    entries[stream_url] = (current_meta, final_group)

                current_meta = None

    return entries

def write_playlist(entries):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for url, (meta, group) in entries.items():
            meta_clean = meta.split(" group-title=")[0]
            f.write(f'{meta_clean} group-title="{group}"\n')
            f.write(f"{url}\n")

if __name__ == "__main__":
    entries = parse_playlists()
    write_playlist(entries)
