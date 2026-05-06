"""Match chapter transcripts to a setlist of songs and output chapter titles.

Input:
  --chapters    chapters.csv produced from ffprobe (idx,start,end,duration)
  --setlist     setlist.txt: one song title per line; lines starting with #
                or empty are skipped. Title is also the lyrics-file basename.
  --lyrics      directory of <title>.txt lyrics files (optional; missing
                lyrics = instrumental / unknown -> matched purely by position)
  --transcripts directory of <ch>.json transcripts

Output (stdout): TSV `chapter_idx<TAB>title` for every chapter, in order.

Algorithm:
  1. For each chapter, score its transcript against every song with lyrics
     using character-4-gram Jaccard (transcript ∩ lyric / transcript).
  2. SONG_THRESHOLD picks anchors. Anchors are forced monotonic in setlist
     order; on conflict the higher score wins.
  3. Walk chapters in order with a setlist cursor. For each chapter:
       - anchored -> use anchor, cursor = anchor_pos + 1
       - cursor has reached the next anchor's slot -> MC (no song to give it)
       - transcript looks like MC (keywords / very short / hallucination)
         -> MC, cursor unchanged
       - otherwise consume setlist[cursor] (covers instrumentals that have
         no lyrics to match)
"""
from __future__ import annotations
import argparse, csv, json, os, re


SONG_THRESHOLD = 0.15           # n-gram score to count as a song anchor
MC_KEYWORD_LOW_SCORE = 0.20     # below this, even one MC keyword -> MC

MC_KEYWORDS = (
    "ありがとう", "みんな", "東京", "ツアー",
    "また会", "拍手", "もう一回", "嬉しい", "寂しい",
    "聞こえてる", "聞こえるか", "メンバー", "みなさん", "ライト消",
    "最高",
)

HALLUCINATION_MARKERS = (
    "JR東日本", "Sound Hodori", "Subscribe", "おやすみなさい",
    "by H.", "サウンドゥ", "サブタイトル",
)


def slug(title: str) -> str:
    return re.sub(r"\s+", "_", title.strip())


def ngrams(s: str, n=4):
    s = re.sub(r"\s+", "", s or "")
    return {s[i:i+n] for i in range(len(s)-n+1)}


def score(transcript: str, lyrics: str) -> float:
    t = ngrams(transcript)
    l = ngrams(lyrics)
    if not t or not l:
        return 0.0
    return len(t & l) / len(t)


def strip_hallucinations(text: str) -> str:
    out = text
    for m in HALLUCINATION_MARKERS:
        out = out.replace(m, "")
    return out


def looks_like_mc(text: str, best_song_score: float) -> bool:
    """Decide whether this transcript is MC content.

    Songs scoring above SONG_THRESHOLD are already anchored before we get here,
    so a non-anchored chapter is at most a weak song match. We pick MC if the
    transcript contains audience-direct phrasing or is too short to be a song.

    An *instrumental* track shows up as no transcript / pure hallucination, so
    we explicitly do not call those MC -- the caller will fall back to position
    fill.
    """
    cleaned = strip_hallucinations(text or "").strip()
    body = re.sub(r"\s+", "", cleaned)

    if not body:
        # nothing real -> caller should treat as instrumental, not MC
        return False

    mc_hits = sum(k in cleaned for k in MC_KEYWORDS)
    if mc_hits >= 2:
        return True
    if mc_hits >= 1 and best_song_score < MC_KEYWORD_LOW_SCORE:
        return True
    if len(body) < 8 and best_song_score < 0.10:
        # very brief utterance, no song match
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", required=True)
    ap.add_argument("--setlist", required=True)
    ap.add_argument("--lyrics", required=True)
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--report", help="write a TSV scoring report")
    args = ap.parse_args()

    setlist: list[str] = []
    for line in open(args.setlist, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        setlist.append(line)

    lyrics: dict[int, str] = {}
    for i, title in enumerate(setlist):
        path = os.path.join(args.lyrics, f"{slug(title)}.txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                lyrics[i] = f.read()

    chapters = list(csv.DictReader(open(args.chapters)))
    chapters.sort(key=lambda r: int(r["idx"]))

    def get_text(idx: int) -> str:
        p = os.path.join(args.transcripts, f"ch{idx:02d}.json")
        if not os.path.isfile(p):
            return ""
        return json.load(open(p)).get("text", "")

    # 1. score
    scored: list[list[tuple[float, int]]] = []
    for row in chapters:
        idx = int(row["idx"])
        t = get_text(idx)
        s = sorted(((score(t, lyr), i) for i, lyr in lyrics.items()), reverse=True)
        scored.append(s)

    # 2. pick anchors with monotonic invariant
    chapter_anchor: dict[int, int] = {}
    setlist_used: dict[int, tuple[int, float]] = {}
    for ch_pos, sc in enumerate(scored):
        if not sc:
            continue
        best_score, best_i = sc[0]
        if best_score < SONG_THRESHOLD:
            continue
        ch_idx = int(chapters[ch_pos]["idx"])
        if best_i in setlist_used:
            other_ch, other_score = setlist_used[best_i]
            if best_score <= other_score:
                continue
            chapter_anchor.pop(other_ch, None)
        chapter_anchor[ch_idx] = best_i
        setlist_used[best_i] = (ch_idx, best_score)

    # enforce monotonicity
    while True:
        items = sorted(chapter_anchor.items())
        bad = None
        for k in range(len(items) - 1):
            (ch_a, i_a), (ch_b, i_b) = items[k], items[k+1]
            if i_b < i_a:
                sa = setlist_used[i_a][1]
                sb = setlist_used[i_b][1]
                bad = ch_b if sb <= sa else ch_a
                break
        if bad is None:
            break
        i = chapter_anchor.pop(bad)
        setlist_used.pop(i, None)

    # 3. precompute next-anchor song position for each chapter position
    ch_idx_in_order = [int(r["idx"]) for r in chapters]
    next_anchor_song = [len(setlist)] * len(ch_idx_in_order)
    last = len(setlist)
    for i in range(len(ch_idx_in_order) - 1, -1, -1):
        if ch_idx_in_order[i] in chapter_anchor:
            last = chapter_anchor[ch_idx_in_order[i]]
        next_anchor_song[i] = last

    # 4. position-fill walk
    assignment: dict[int, str] = {}
    cursor = 0
    for i, idx in enumerate(ch_idx_in_order):
        if idx in chapter_anchor:
            ai = chapter_anchor[idx]
            assignment[idx] = setlist[ai]
            cursor = ai + 1
            continue
        ceiling = next_anchor_song[i]   # exclusive: this slot belongs to the next anchor
        text = get_text(idx)
        best = scored[i][0][0] if scored[i] else 0.0
        if cursor >= ceiling:
            assignment[idx] = "MC"
            continue
        if looks_like_mc(text, best):
            assignment[idx] = "MC"
            continue
        assignment[idx] = setlist[cursor]
        cursor += 1

    # 5. emit assignment + optional report
    for idx in ch_idx_in_order:
        print(f"{idx}\t{assignment[idx]}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("idx\ttitle\tbest_score\tbest_song\t2nd_score\t2nd_song\ttext\n")
            for ch_pos, sc in enumerate(scored):
                idx = int(chapters[ch_pos]["idx"])
                top = list(sc[:2])
                while len(top) < 2:
                    top.append((0.0, -1))
                t = get_text(idx).replace("\t", " ").replace("\n", " ")
                a, b = top
                f.write(
                    f"{idx}\t{assignment[idx]}\t{a[0]:.2f}\t"
                    f"{setlist[a[1]] if a[1] >= 0 else ''}\t"
                    f"{b[0]:.2f}\t{setlist[b[1]] if b[1] >= 0 else ''}\t"
                    f"{t[:100]}\n"
                )


if __name__ == "__main__":
    main()
