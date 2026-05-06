"""Fetch lyrics for setlist songs from j-lyric.net.

Usage:
  python3 fetch_lyrics.py --setlist FILE --lyrics-dir DIR --artist NAME

Skips entries that are SE/instrumental (`(SE)` or `(インスト)` suffix), already
have a lyric file, or whose title can't be matched on the artist page. Reports
which titles weren't found so the user can fix their setlist.

The match is against j-lyric's BUMP/Oda/etc. artist page — j-lyric is the only
free site whose pages are scrape-friendly without bot defences.
"""
from __future__ import annotations
import argparse, os, re, sys, urllib.parse, urllib.request, time

UA = "Mozilla/5.0 (X11; Linux x86_64)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def slug(title: str) -> str:
    return re.sub(r"\s+", "_", title.strip())


def find_artist_id(name: str) -> str | None:
    enc = urllib.parse.quote(name)
    html = fetch(f"https://j-lyric.net/index.php?ka={enc}")
    ids = re.findall(r"/artist/(a[0-9a-z]+)/", html)
    return ids[0] if ids else None


def list_artist_songs(artist_id: str) -> dict[str, str]:
    """Return {song_id: title} across all artist pages."""
    songs: dict[str, str] = {}
    pat = re.compile(rf"/artist/{artist_id}/(l[0-9a-z]+)\.html[^>]*>([^<]+)</a>")
    last_count = -1
    for page in range(1, 30):
        html = fetch(f"https://j-lyric.net/artist/{artist_id}/?p={page}")
        before = len(songs)
        for sid, title in pat.findall(html):
            songs.setdefault(sid, title.strip())
        if len(songs) == before:
            # no new entries -> last page
            break
        # crude rate limit
        time.sleep(0.3)
    return songs


def normalise(title: str) -> str:
    return re.sub(r"[\s\u3000]+", "", title).lower()


def match_titles(setlist: list[str], songs: dict[str, str]) -> dict[str, str]:
    """Return {clean_title: song_id} for each setlist entry that matches.

    Strips parenthesised suffix from the setlist side ("会いに行く (アンコール)"
    -> "会いに行く"). Skips SE / インスト markers entirely.
    """
    title_to_sid_norm = {normalise(t): sid for sid, t in songs.items()}
    out: dict[str, str] = {}
    for raw in setlist:
        if re.search(r"\(\s*(SE|インスト|instrumental)\s*\)\s*$", raw, re.IGNORECASE):
            continue
        clean = re.sub(r"\s*[\(\[].+?[\)\]]\s*$", "", raw).strip()
        n = normalise(clean)
        sid = title_to_sid_norm.get(n)
        if sid:
            out[clean] = sid
    return out


def fetch_lyric(artist_id: str, song_id: str) -> str | None:
    html = fetch(f"https://j-lyric.net/artist/{artist_id}/{song_id}.html")
    m = re.search(r"<p[^>]*id=[\"']Lyric[\"'][^>]*>(.*?)</p>", html, re.DOTALL)
    if not m:
        return None
    text = re.sub(r"<br[^>]*>", "\n", m.group(1))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[\r\n]+", "\n", text).strip()
    return text or None


def parse_setlist(path: str) -> tuple[list[str], str | None]:
    titles: list[str] = []
    artist: str | None = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^\s*#\s*@artist\s+(.+?)\s*$", line)
        if m:
            artist = m.group(1)
            continue
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        titles.append(s)
    return titles, artist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setlist", required=True)
    ap.add_argument("--lyrics-dir", required=True)
    ap.add_argument("--artist", help="override @artist line in setlist.txt")
    args = ap.parse_args()

    titles, artist = parse_setlist(args.setlist)
    artist = args.artist or artist
    if not artist:
        sys.exit("error: artist not given (use --artist or `# @artist NAME` in setlist.txt)")

    aid = find_artist_id(artist)
    if not aid:
        sys.exit(f"error: artist not found on j-lyric.net: {artist}")
    print(f"j-lyric artist id={aid}", flush=True)

    songs = list_artist_songs(aid)
    print(f"  {len(songs)} songs found on artist page", flush=True)

    matches = match_titles(titles, songs)
    os.makedirs(args.lyrics_dir, exist_ok=True)

    saved = 0
    skipped = 0
    for title, sid in matches.items():
        out = os.path.join(args.lyrics_dir, f"{slug(title)}.txt")
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            skipped += 1
            continue
        text = fetch_lyric(aid, sid)
        if not text:
            print(f"  ! empty lyric: {title}", flush=True)
            continue
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        saved += 1
        print(f"  + {title}", flush=True)
        time.sleep(0.3)

    missing = [t for t in titles if not (
        re.search(r"\(\s*(SE|インスト|instrumental)\s*\)\s*$", t, re.IGNORECASE)
        or re.sub(r"\s*[\(\[].+?[\)\]]\s*$", "", t).strip() in matches
    )]
    if missing:
        print(f"  ? not found ({len(missing)}): " + " / ".join(missing[:5])
              + (" ..." if len(missing) > 5 else ""), flush=True)
    print(f"saved={saved}, cached={skipped}, missing={len(missing)}", flush=True)


if __name__ == "__main__":
    main()
