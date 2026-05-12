---
name: rip-disc
description: Use when the user wants to rip a Japanese live-concert Blu-ray/DVD into a Plex-cataloged entry. Triggers include "ライブDVDをripして", "新しいライブBD", "コンサート円盤", "Plex用に取り込んで", "セトリ入りで", or invoking /rip-disc. Runs the full bd2mkv pipeline (rip → encode → name-chapters), automates Plex metadata (parses the disc name for artist/tour/date/venue, fetches the setlist from LiveFans, finds the product on Amazon and downloads cover art, writes the NFO), and embeds per-song chapter titles via mkvpropedit — without prompting the user unless data is genuinely ambiguous. NOT for theatrical movies, anime BDs, foreign-language concerts, or non-music discs.
---

# Japanese Live DVD → Plex (autonomous)

Run end-to-end without prompting. Ask only on real ambiguity (multiple LiveFans matches with different dates, multiple Amazon ASINs, etc.).

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

Then define the `bd2mkv` shell function:

```bash
bd2mkv() {
  local entry=()
  [ "$1" = "ffprobe" ] && { entry=(--entrypoint ffprobe); shift; }
  docker run --rm --device <BLOCK> --device <SG> --privileged \
    -v "$(pwd):/work" -w /work "${entry[@]}" ghcr.io/sammrai/bd2mkv "$@"
}
```

`-w /work` で相対パス (`output/<DISC>`, `encoded/<DISC>`) がそのまま使える。

Substitute `<BLOCK>` / `<SG>` with the resolved values.

### 1. Rip + encode

```bash
bd2mkv > /tmp/bd2mkv.log 2>&1 &   # = rip + encode
```

パイプライン中は `<DISC>` = MakeMKVが返す名前のまま使う。リネームは §7 で行う。

rip+encodeの間に §2–§6-2（identify, setlist, cover art, NFO, lyrics）を並行で進める。§6-3（name-chapters）のみencode完了を待つ。Monitorで自動連結:

```bash
tail -f /tmp/bd2mkv.log | grep -E --line-buffered "Done: /work/encoded|[Ee]rror|Invalid data"
```

Output: `output/<DISC>/title_t*.mkv` → `encoded/<DISC>/<DISC>.mkv` + `*-scene.mkv`。

### 2. Identify the disc

`<DISC>` 名はripログの `Disc: <NAME>` から取得。`BUMP_OF_CHICKEN_TOUR_2024_Sphery_Rendezvous_2024.12.08_東京ドーム_Day2` のような記述的な名前ならそこからartist/tour/date/venue/extraをパース（artist=最初のTOUR/LIVE手前、tour=date手前、date=`YYYY[.\-/_]MM[.\-/_]DD`、venue=date直後、extra=`Day1`/`千秋楽`等）。

`BD_ROM` / `DVD_ROM` / `disc_<ts>` / カタログ番号（例: `UPXX_20142`）の場合はWebSearchで特定。確定できなければユーザーに確認。**ここで特定できないとsetlist/cover art/NFOがすべて作れないのでpipelineを止める**（rip+encodeのみ完走させてskill終了）。

特定した内容を元に **slug**（例: `MGA_HARMONY_2024`）を決め、NFOの `<title>` 等にも反映する。

**⚠️ 必須確認ステップ（セットリスト着手前に必ず停止）**: ディスク特定後、rip+encodeを継続しながら、以下をユーザーに提示して確認を得てから §3 以降（setlist/cover art/NFO/lyrics）に進む：

```
特定結果:
  アーティスト: {artist}
  タイトル: {product title verbatim}
  日程/会場: {date} {venue}
  SLUG候補: {SLUG}

このパッケージで進めてよいですか？
```

ユーザーが承認したら §3 以降を開始する。否認または修正があれば再特定してから再確認する。rip+encode は承認を待たず継続してよい。

### 3. Fetch setlist

**Primary**: §4a の Amazon 商品ページのtracklist（チャプター対応で正確）。

**Fallback**: LiveFans (`https://www.livefans.jp/`) で `"<artist> <tour> セットリスト"` 検索。公演日と会場/Dayでマッチ。

Sanity check: chapter count must be **≥ setlist length**:

```bash
bd2mkv ffprobe -v quiet -show_chapters encoded/<DISC>/<DISC>.mkv | grep -c '\[CHAPTER\]'
```

MC/SE/interludes add chapters（21曲 ↔ 28チャプターで7 MCsは正常）。Chapters < setlist → wrong-day match。曲名の表記揺れは product-page tracklist 優先。

### 4. Find cover art

#### 4a. Amazon (first attempt)

WebSearch: `"<artist> <tour> Blu-ray site:amazon.co.jp"`. Pick the first standard-edition result whose title contains both artist and tour. ASIN is in `/dp/<ASIN>` or `/gp/product/<ASIN>`.

```bash
curl -s --compressed "https://www.amazon.co.jp/dp/<ASIN>" \
  -H "User-Agent: Mozilla/5.0" -L -o /tmp/amzn.html
grep -oE '"hiRes":"https://m\.media-amazon\.com/images/I/[^"]+"' /tmp/amzn.html
```

`--compressed` 必須（brotli圧縮のため）。同じHTMLからtracklist（§3）とレーベル（§5の `<studio>`）も取れる。CAPTCHA/Robot Check が出たら 4b へ。

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

**必ず目視確認**: ratio合格後、Read toolで `encoded/<DISC>/poster.jpg` を開いて画像を表示し、コンサートのジャケットとして適切か確認する。バッグ・グッズ・BOX特典の写真など不適切な場合は別の画像ソースを探して差し替える。

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

- プロンプトでBD case枠を**禁止**（gpt-image-1.5は放置するとcase mockupを描く）。
- ケース枠が混入したら再プロンプトか §4a/b/c へフォールバック。
- 適用後は §8 で再copy（Plexはmtime更新を見るため）。
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

1. Write `encoded/<DISC>/setlist.txt` from the canonical product tracklist. **One entry per chapter mark, not per song.** First non-comment line: `# @artist NAME`. Rules:
   - **Medley → 1 entry** (e.g. `13th Anniversary Medley`); listing each medley song separately desyncs the cursor.
   - **SE / instrumental → 1 entry** with `(SE)` suffix.
   - **Repeated songs (encore reprise) → 1 entry per occurrence** with a parenthesised disambiguator on later ones (`会いに行く`, `会いに行く (アンコール)`).
   - **Documentary / 御当地紀行 / behind-the-scenes** with a chapter mark → 1 entry.

2. Fetch lyrics (run while encoding is still in progress):

   ```bash
   bd2mkv fetch-lyrics encoded/<DISC>
   ```

   Reads `# @artist NAME` from `setlist.txt`, looks up the artist on j-lyric.net, and saves `encoded/<DISC>/lyrics/<曲名>.txt`. SE/インタールード/MCが見つからないのは正常。**それ以外で `? not found` になった曲は必ずWebSearchで正しい曲名を調べてsetlist.txtを修正し、fetch-lyricsを再実行する**（ライブ曲が存在しないことはまずない）。

3. Run `bd2mkv name-chapters encoded/<DISC>`. Whisperで全チャプター文字起こし→lyricsとマッチ→chapter名をmkvに書き込み。stderrに3種の警告が出る:
   - `WARNING: N setlist song(s) NOT assigned` — 未紐付き曲。setlist.txt の順序を疑う
   - `WARNING: long MC runs detected` — 3曲以上連続MC、順序誤りのサイン
   - `WARNING: N high-score anchor(s) rejected by monotonicity` — 高スコアanchorがmonotonicityで破棄、順序誤り確定
   - `WARNING: N MC chapter(s) contain lyric-like content` — MC扱いだが歌詞っぽい。**setlist.txt に未掲載の曲**（インタールード/アンコール/特典）の可能性

4. **警告に応じてループ**:
   - 順序疑い → LiveFans／Amazon の正しい順で setlist.txt 書き換え → 再実行
   - 未掲載曲疑い → chapter位置の transcript を見て曲名特定 → setlist.txt に追加 → 再実行
   - 警告ゼロまで繰り返す（snippets/transcripts はキャッシュされるので再実行は数秒）

### 7. Rename to `encoded/<SLUG>/`

pipeline完了後、`encoded/<DISC>/` を `encoded/<SLUG>/` にrename。raw rip (`output/<DISC>/`) は残す（再rip回避用）。

```bash
SLUG=MGA_HARMONY_2024     # §2 で決めた人間可読の名前
DISC=UPXX_20142           # MakeMKVの出力名

# rootで作成されたファイルがあるので Docker 経由
docker run --rm --entrypoint sh -v "$(pwd):/work" -w /work ghcr.io/sammrai/bd2mkv -c "
  set -e
  mv encoded/$DISC encoded/$SLUG
  cd encoded/$SLUG
  mv $DISC.mkv $SLUG.mkv
  mv $DISC.nfo $SLUG.nfo
  i=1
  for f in title_t*-scene.mkv; do
    [ -f \"\$f\" ] || continue
    mv \"\$f\" \"$SLUG-scene\$(printf '%02d' \$i).mkv\"
    i=\$((i+1))
  done
"
```

### 8. Deploy to Plex

**最終レポートと同時に**Plexへのデプロイ確認を行う（§ Done を先に出してから別途聞くのではなく、レポートの末尾に確認を含めること）。

Plexライブラリのルートパスはユーザーのグローバル設定（CLAUDE.md）に記載があればそれを使う。なければ確認する。

```bash
cp -r "encoded/<SLUG>" "<LIBRARY_ROOT>/<SLUG>"
```

`$DST` に旧ripが残っていればユーザーに確認してから削除。

## Scope guard

Abort and run only `bd2mkv` (rip + encode) if the disc isn't a Japanese live concert (洋楽 live, 映画, アニメ, スポーツ, 教育, etc.).

## Done — 最終レポート

name-chapters完了後、以下をまとめて**1つのメッセージ**でユーザーに報告し、末尾にPlexデプロイの確認を添える:

1. **保存先パス**: `encoded/<SLUG>/` のフルパス
2. **セトリ紐付け**: `.chapters_cache/assignment.tsv` を見て setlist.txt の全曲がチャプターに割り当てられているか明示。未割当があれば曲名を列挙
3. **Plexデプロイ確認**: `encoded/<SLUG>/` を `<LIBRARY_ROOT>/<SLUG>/` にコピーしてよいか確認
