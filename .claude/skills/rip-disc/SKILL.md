---
name: rip-disc
description: Use when the user wants to rip a Japanese live-concert Blu-ray/DVD into a Plex-cataloged entry. Triggers include "ライブDVDをripして", "新しいライブBD", "コンサート円盤", "Plex用に取り込んで", "セトリ入りで", or invoking /rip-disc. Runs the full bd2mkv pipeline (rip → encode → name-chapters), automates Plex metadata (parses the disc name for artist/tour/date/venue, fetches the setlist from LiveFans, finds the product on Amazon and downloads cover art, writes the NFO), and embeds per-song chapter titles via mkvpropedit — without prompting the user unless data is genuinely ambiguous. NOT for theatrical movies, anime BDs, foreign-language concerts, or non-music discs.
---

# Japanese Live DVD → Plex (autonomous)

Run end-to-end without prompting. Ask only on real ambiguity (multiple LiveFans matches with different dates, multiple Amazon ASINs, etc.). Default to the most plausible inference and surface the chosen value in the final report so the user can correct.

## Pipeline

### 0. Pull latest image, resolve optical drive device paths, and define `bd2mkv`

Always pull the latest image first:

```bash
docker pull ghcr.io/sammrai/bd2mkv
```

`docker run --device` needs both the block device (`/dev/sr*`) and the SCSI generic device (`/dev/sg*`) for the same drive — these are host-dependent and must not be hardcoded. Detect them with `lsscsi -g` and pick the row whose `type` column is `cd/dvd`:

```bash
lsscsi -g
# [7:0:0:0]    cd/dvd  HL-DT-ST BD-RE  BH16NS48      /dev/sr0   /dev/sg3
#                                                    ^^^^^^^^   ^^^^^^^^
#                                                    block      sg
```

Use the right two columns of that row as `--device <block> --device <sg>`. If multiple `cd/dvd` rows exist, ask which drive to use. If `lsscsi` is missing, fall back to `ls /dev/sr*` for the block device and map to `/dev/sg*` via `cat /sys/block/sr0/device/scsi_generic/sg*/uevent`, or install `lsscsi`.

Then define the `bd2mkv` shell function for the rest of the pipeline (the user's shell may already alias it; verify with `type bd2mkv` and reuse if so):

```bash
bd2mkv() {
  docker run --rm --device <BLOCK> --device <SG> --privileged \
    -v "$(pwd):/work" ghcr.io/sammrai/bd2mkv "$@"
}
```

Substitute `<BLOCK>` / `<SG>` with the resolved values.

### 1. Rip + encode

```bash
bd2mkv     # = rip + encode
```

Run in the background. While it runs, proceed with §2 (parse disc name from the log as soon as it appears) and §3–§6-2 (setlist, cover art, NFO, setlist.txt, lyrics fetch) in parallel — encoding takes 1–2 hours and none of these require the MKV. Only §6-3 (`bd2mkv name-chapters`) must wait for encoding to finish.

Output: `output/<DISC>/title_t*.mkv` then `encoded/<DISC>/<DISC>.mkv` (largest title) + `*-scene.mkv`.

### 2. Parse disc identity from `<DISC>`

`bd2mkv` resolves the name from MakeMKV `DRV:0` / `CINFO:2,0` → `BDMV/META/DL/bdmt_*.xml` (`<di:name>`) → timestamp. Descriptive names like `BUMP_OF_CHICKEN_TOUR_2024_Sphery_Rendezvous_2024.12.08_東京ドーム_Day2` parse directly:
- **artist** — text up to `TOUR`/`LIVE`/`ライブ`/`公演`
- **tour** — between artist and date
- **date** — `YYYY[.\-/_]MM[.\-/_]DD` → `YYYY-MM-DD`
- **venue** — token after the date
- **extra** — `Day1`/`Day2`/`初日`/`千秋楽` for tie-breaking

If `<DISC>` is `BD_ROM` / `DVD_ROM` / `disc_<timestamp>`, ask the user for artist/tour/date/venue, then rename `output/<old>`, `encoded/<old>`, `encoded/<old>/<old>.mkv` to a short slug (e.g. `BOC_SR_TOKYO_DOME_DAY2`). `ffprobe` is useless here (only returns `encoder=libmakemkv`).

### 3. Fetch setlist

**Primary**: the BD product page (Amazon §4a) — its tracklist is canonical and chapter-aligned. Do §4a first in practice; the order below is logical, not execution.

**Fallback (LiveFans)**: WebFetch `https://www.livefans.jp/` with `"<artist> <tour> セットリスト"`. Match by 公演日 == parsed date; on multi-show dates pick by 会場 / Day token.

Sanity check: chapter count must be **≥ setlist length** (`ffprobe` is not on the host — use `docker run --rm -v "$(pwd):/work" --entrypoint ffprobe ghcr.io/sammrai/bd2mkv -v quiet -show_chapters /work/encoded/<DISC>/<DISC>.mkv | grep -c '\[CHAPTER\]'`) (MC/SE/interludes add chapters; 21 songs ↔ 28 chapters with 7 MCs is normal). Chapters < setlist → wrong-day match. Prefer the product-page tracklist for canonical title spellings.

### 4. Find cover art

#### 4a. Amazon (first attempt)

WebSearch: `"<artist> <tour> Blu-ray site:amazon.co.jp"`. Pick the first standard-edition result whose title contains both artist and tour. ASIN is in `/dp/<ASIN>` or `/gp/product/<ASIN>`.

```bash
curl -s --compressed "https://www.amazon.co.jp/dp/<ASIN>" \
  -H "User-Agent: Mozilla/5.0" -L -o /tmp/amzn.html
grep -oE '"hiRes":"https://m\.media-amazon\.com/images/I/[^"]+"' /tmp/amzn.html
```

`--compressed` is **required** (Amazon serves brotli; without it the body is binary and grep finds nothing). The same `/tmp/amzn.html` carries the **product tracklist** and 「レーベル」 — reuse for §3 and `<studio>` in §5. If empty / CAPTCHA / Robot Check, move to 4b — don't retry Amazon.

When it works:
```bash
curl -L -o "encoded/<DISC>/poster.jpg" \
  "https://m.media-amazon.com/images/I/<ID>._AC_SL1500_.jpg"
```
On 404 retry `_AC_SL1000_`.

#### 4b. Label store / 4c. HMV / Tower / 楽天

Label EC sites (TOY'S FACTORY / Sony / avex (mu-mo) / Universal / Warner / Victor / King / Pony Canyon / EMI) work with normal `curl`. WebSearch `"<artist> <tour> Blu-ray store"`. If the label store doesn't carry it, fall back to HMV (`/jpg/<id>.jpg`), Tower (JAN-based), or 楽天ブックス (ISBN/JAN-based).

#### 4d. Verify

```bash
python3 -c "from PIL import Image; w,h=Image.open('encoded/<DISC>/poster.jpg').size; print(f'{w}x{h} ratio={w/h:.3f}')"
```

Accept ratio **0.65–0.85** (BD jacket ≈0.80, Plex target 2:3 ≈0.667; both fit). Outside that range → §4e.

#### 4e. Portrait outpaint via gpt-image-1.5 (only if `OPENAI_API_KEY` is present)

When the only acceptable candidate is a square album cover and the user wants strict 2:3, outpaint with OpenAI's image-edits API. Requires `OPENAI_API_KEY` from `~/mkv-ripping/.env`; skip §4e entirely if unset.

```bash
set -a; source "$HOME/mkv-ripping/.env"; set +a

curl -sS -X POST https://api.openai.com/v1/images/edits \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  -F "model=gpt-image-1.5" \
  -F "image[]=@encoded/<DISC>/poster.jpg" \
  -F "prompt=Re-layout this album/jacket cover into a proper 2:3 portrait poster (1024x1536). Keep all design elements byte-identical (subject artwork, title typography, sub-title, any badges, background colour and texture, fonts, colours). Redistribute them with balanced jacket-style hierarchy — header/badges upper third, main artwork centre, large title in middle-lower, sub-title near bottom — proportions like a real BD/DVD jacket cover, not a banner with empty space. ABSOLUTELY DO NOT add any Blu-ray case frame, disc spine, side panels, additional 'Blu-ray Disc' badge, packaging mockup, watermark, or drop shadow. Preserve every existing element exactly; only change layout, spacing, and proportions to fit portrait." \
  -F "size=1024x1536" -F "quality=high" -F "output_format=png" \
  -o /tmp/poster.json
jq -r '.data[0].b64_json' /tmp/poster.json | base64 -d > /tmp/poster.png
python3 -c "from PIL import Image; Image.open('/tmp/poster.png').convert('RGB').save('encoded/<DISC>/poster.jpg', 'JPEG', quality=92)"
```

- Prompt **must forbid** BD case framing — gpt-image-1.5 otherwise wraps the cover in a case mockup (top "Blu-ray Disc" bar + spine).
- `size=1024x1536` (Plex's exact 2:3). Save as JPEG q≥90.
- Read the result back; if a case frame snuck through, re-prompt or fall back to (a)/(b)/(c).
- After applying, re-run §7 copy (Plex won't pick up updates without a file mtime change at the watched path).
- Cost / 1024×1536 high: gpt-image-1.5 $0.20, gpt-image-2 $0.30.

### 5. Write the NFO

`encoded/<DISC>/<DISC>.nfo`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
    <title>{artist + tour + venue + day, e.g. "BUMP OF CHICKEN TOUR 2024 Sphery Rendezvous 東京ドーム Day2"}</title>
    <originaltitle>{product page title verbatim}</originaltitle>
    <year>{YYYY}</year>
    <premiered>{YYYY-MM-DD}</premiered>
    <plot>セットリスト:
1. {song1}
2. {song2}
...</plot>
    <genre>コンサート</genre>
    <genre>音楽</genre>
    <studio>{label}</studio>
</movie>
```

### 6. Chapter auto-naming

Embed per-song titles via `mkvpropedit` (mutates the mkv in place; Plex needs a refresh after).

1. Write `encoded/<DISC>/setlist.txt` from the canonical product tracklist. **One entry per chapter mark, not per song.** First non-comment line: `# @artist NAME`. Rules:
   - **Medley → 1 entry** (e.g. `13th Anniversary Medley`); listing each medley song separately desyncs the cursor.
   - **SE / instrumental → 1 entry** with `(SE)` suffix.
   - **Repeated songs (encore reprise) → 1 entry per occurrence** with a parenthesised disambiguator on later ones (`会いに行く`, `会いに行く (アンコール)`).
   - **Documentary / 御当地紀行 / behind-the-scenes** with a chapter mark → 1 entry.

2. Fetch lyrics (run while encoding is still in progress):

   ```bash
   bd2mkv fetch-lyrics encoded/<DISC>
   ```

   Reads `# @artist NAME` from `setlist.txt`, looks up the artist on j-lyric.net, and saves `encoded/<DISC>/lyrics/<曲名>.txt`. Songs not found (instrumentals, interludes, MCs) are reported as `? not found` and skipped — expected. Run this explicitly so you can spot missing files before the 30-min transcription starts; `bd2mkv name-chapters` would auto-fetch too but only after encoding finishes.

3. Run `bd2mkv name-chapters encoded/<DISC>`. The CLI transcribes each chapter with Whisper, matches against the lyrics, and writes chapter titles into the mkv.

4. Spot-check `encoded/<DISC>/.chapters_cache/match_report.tsv`. If many rows came back as `MC` when they shouldn't, the matched lyric file is probably wrong (a different song under the same title); fix or replace the suspect file in `lyrics/` and re-run (cached snippets/transcripts make the rerun fast).

### 7. Deploy to Plex

Ask the user before deploying:

1. Whether to deploy at all (skip if they only wanted the encoded artifacts under `encoded/<DISC>/`).
2. The Plex library root path — this is host-specific and **must not** be hardcoded. Common locations are `/data/epgstation/movie/`, `/var/lib/plexmediaserver/...`, or a custom mount, but always confirm. Append `<DISC>/` to the chosen root for `$DST`.
3. Copy vs. move. Default to **copy** so `encoded/<DISC>/` stays available for re-runs / cache reuse; only move if the user explicitly wants to free space.

```bash
SRC="./encoded/<DISC>"
DST="<USER_PROVIDED_LIBRARY_ROOT>/<DISC>"     # e.g. /data/epgstation/movie/<DISC>
mkdir -p "$DST"
cp "$SRC/<DISC>.mkv" "$SRC/<DISC>.nfo" "$SRC/poster.jpg" \
   "$SRC/setlist.txt" "$SRC/chapters.xml" "$DST/"
cp -r "$SRC/lyrics" "$DST/"
for f in "$SRC"/*-scene.mkv; do [ -f "$f" ] && cp "$f" "$DST/"; done
```

`.chapters_cache/` stays under `encoded/` (resume-only state). If a previous raw rip exists at `$DST` with a different filename, ask the user before deleting it (Plex would otherwise show duplicates, but they may have intentionally kept the raw alongside).

## Scope guard

Abort and run only `bd2mkv` (rip + encode) if the disc isn't a Japanese live concert (洋楽 live, 映画, アニメ, スポーツ, 教育, etc.).

## Done

1. `<DISC>.mkv` plays, `ffprobe -show_chapters` shows song titles (not `Chapter NN`)
2. `<DISC>.nfo` + `poster.jpg` populated alongside it
3. (If deployment was requested) mirrored to the user-confirmed Plex library path, no stale raw rip there
4. Final report links the LiveFans show / Amazon product so the user can verify in seconds
