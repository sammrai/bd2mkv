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
import argparse, csv, json, os, re, sys


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
    "作詞・作曲", "作詞作曲", "編曲・編曲", "歌詞・歌詞",
    "Instagram",
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


def looks_like_mc(text: str, best_song_score: float, strict: bool = False) -> bool:
    """Decide whether a transcript is MC content.

    `strict=True` is used when the next position-fill slot has no lyrics (the
    chapter could be a song we just don't have lyrics for) — in that case we
    only call it MC when the audience-direct signal is unmistakable.
    `strict=False` is the normal case where the next slot has lyrics, so a
    mismatched lyric score with even one MC keyword is enough.
    """
    cleaned = strip_hallucinations(text or "").strip()
    body = re.sub(r"\s+", "", cleaned)

    if len(body) < 12:
        # almost nothing real -> instrumental / silence, not MC
        return False

    mc_hits = sum(k in cleaned for k in MC_KEYWORDS)

    if strict:
        # only the strongest MC signals; song lyrics often share 1-2 keywords
        if mc_hits >= 4:
            return True
        if mc_hits >= 2 and len(body) < 50:
            return True
        return False

    if mc_hits >= 3:
        return True
    if mc_hits >= 2:
        return True
    if mc_hits >= 1 and best_song_score < MC_KEYWORD_LOW_SCORE:
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

    def lyric_path(title: str) -> str | None:
        # explicit instrumental marker -> no lyric match (let position-fill take it)
        if re.search(r"\(\s*SE\s*\)\s*$", title, re.IGNORECASE):
            return None
        # exact slug first; otherwise strip parenthesised suffix like "(アンコール)"
        cand = [slug(title)]
        base = re.sub(r"\s*[\(\[].+?[\)\]]\s*$", "", title).strip()
        if base and base != title:
            cand.append(slug(base))
        for c in cand:
            p = os.path.join(args.lyrics, f"{c}.txt")
            if os.path.isfile(p):
                return p
        return None

    lyrics: dict[int, str] = {}
    for i, title in enumerate(setlist):
        p = lyric_path(title)
        if p:
            with open(p, encoding="utf-8") as f:
                lyrics[i] = f.read()

    chapters = list(csv.DictReader(open(args.chapters)))
    chapters.sort(key=lambda r: int(r["idx"]))

    def get_text(idx: int) -> str:
        p = os.path.join(args.transcripts, f"ch{idx:02d}.json")
        if not os.path.isfile(p):
            return ""
        return json.load(open(p)).get("text", "")

    # 1. score (ties broken by earliest setlist position)
    scored: list[list[tuple[float, int]]] = []
    for row in chapters:
        idx = int(row["idx"])
        t = strip_hallucinations(get_text(idx))
        s = [(score(t, lyr), i) for i, lyr in lyrics.items()]
        s.sort(key=lambda x: (-x[0], x[1]))
        scored.append(s)

    # 2. pick anchors with monotonic invariant.
    # When the same lyric content appears at multiple setlist positions
    # (encore reprises etc.) the chapter falls through to its next-best
    # candidate if its top pick is already taken by a higher-scoring chapter.
    chapter_anchor: dict[int, int] = {}
    setlist_used: dict[int, tuple[int, float]] = {}
    for ch_pos, sc in enumerate(scored):
        ch_idx = int(chapters[ch_pos]["idx"])
        for cand_score, cand_i in sc:
            if cand_score < SONG_THRESHOLD:
                break
            if cand_i in setlist_used:
                other_ch, other_score = setlist_used[cand_i]
                if cand_score <= other_score:
                    continue
                chapter_anchor.pop(other_ch, None)
            chapter_anchor[ch_idx] = cand_i
            setlist_used[cand_i] = (ch_idx, cand_score)
            break

    # enforce monotonicity (collect drops for warning)
    dropped_anchors: list[tuple[int, int, float]] = []  # (chapter_idx, setlist_pos, score)
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
        sc_dropped = setlist_used.pop(i, (None, 0.0))[1]
        dropped_anchors.append((bad, i, sc_dropped))

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
        # strict MC test when the candidate setlist slot has no lyrics file
        # (lyric-less songs would otherwise lose to weak MC keyword overlap)
        next_has_lyrics = cursor in lyrics
        if looks_like_mc(text, best, strict=not next_has_lyrics):
            assignment[idx] = "MC"
            continue
        assignment[idx] = setlist[cursor]
        cursor += 1

    # 5. emit assignment + optional report
    for idx in ch_idx_in_order:
        print(f"{idx}\t{assignment[idx]}")

    # 6. sanity warnings to stderr (setlist order errors / unused songs)
    assigned_titles = {assignment[idx] for idx in ch_idx_in_order}
    unused = [s for s in setlist if s not in assigned_titles]
    if unused:
        print(f"WARNING: {len(unused)} setlist song(s) NOT assigned to any chapter:",
              file=sys.stderr)
        for s in unused:
            print(f"  - {s}", file=sys.stderr)
        print("  → setlist.txt の曲順を疑ってください (LiveFans等で実演奏順を確認)。",
              file=sys.stderr)

    # consecutive MCs (3+) suggest setlist order is wrong
    run = 0
    runs: list[tuple[int, int]] = []  # (start_chapter_idx, length)
    run_start = None
    for idx in ch_idx_in_order:
        if assignment[idx] == "MC":
            if run == 0:
                run_start = idx
            run += 1
        else:
            if run >= 3:
                runs.append((run_start, run))
            run = 0
    if run >= 3:
        runs.append((run_start, run))
    if runs:
        print(f"WARNING: long MC runs detected (>=3 consecutive MCs):", file=sys.stderr)
        for start, length in runs:
            print(f"  - chapters {start}..{start+length-1} ({length} MCs)", file=sys.stderr)
        print("  → 曲がMC扱いになっている可能性。setlist.txt の順序を確認。",
              file=sys.stderr)

    # high-score anchors dropped by monotonicity = strong signal setlist order is wrong
    strong_drops = [(c, i, s) for c, i, s in dropped_anchors if s >= 0.25]
    if strong_drops:
        print(f"WARNING: {len(strong_drops)} high-score anchor(s) rejected by monotonicity:",
              file=sys.stderr)
        for ch, pos, sc in strong_drops:
            print(f"  - chapter {ch} matched '{setlist[pos]}' (setlist#{pos+1}, score={sc:.2f})",
                  file=sys.stderr)
        print("  → setlist.txt の曲順が disc の実演奏順と食い違っている可能性が高い。",
              file=sys.stderr)

    # MC chapters with lyric-like content = possibly unlisted songs
    suspicious_mc: list[tuple[int, str]] = []
    for idx in ch_idx_in_order:
        if assignment[idx] != "MC":
            continue
        text = get_text(idx)
        cleaned = strip_hallucinations(text).strip()
        body = re.sub(r"\s+", "", cleaned)
        if len(body) < 50:
            continue
        if sum(k in cleaned for k in MC_KEYWORDS) >= 1:
            continue
        suspicious_mc.append((idx, body[:60]))
    if suspicious_mc:
        print(f"WARNING: {len(suspicious_mc)} MC chapter(s) contain lyric-like content (possibly unlisted songs):",
              file=sys.stderr)
        for ch, snippet in suspicious_mc:
            print(f"  - chapter {ch}: {snippet}…", file=sys.stderr)
        print("  → setlist.txt に未掲載の曲（インタールード/アンコール等）の可能性。追加して再実行。",
              file=sys.stderr)

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
