#!/bin/bash
# 自動チャプター命名スクリプト
# Usage: ./name_chapters.sh <encoded_folder>
#
# Required inputs in <encoded_folder>:
#   <FOLDER_NAME>.mkv          メイン動画
#   setlist.txt                曲順 (1行1曲、# はコメント)
#   lyrics/<song>.txt          各曲の歌詞 (空白は _ に置換した曲名)
#
# 動作:
#   1. ffprobe で MKV からチャプター時刻取得
#   2. ffmpeg で各チャプター冒頭 90 秒の音声抽出 (mp3)
#   3. faster-whisper (medium → large-v3 リトライ) で文字起こし
#   4. 歌詞 4-gram Jaccard で曲を特定、MC は keyword + score で判定
#   5. mkvpropedit でチャプター名を書き戻し

set -euo pipefail

FOLDER="${1:?Usage: $0 <encoded_folder>}"
FOLDER=$(realpath "$FOLDER")
NAME=$(basename "$FOLDER")
MKV="$FOLDER/$NAME.mkv"
SETLIST="$FOLDER/setlist.txt"
LYRICS_DIR="$FOLDER/lyrics"
WORK="$FOLDER/.chapters_cache"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

[ -f "$MKV" ]      || { echo "Missing: $MKV"; exit 1; }
[ -f "$SETLIST" ]  || { echo "Missing: $SETLIST"; exit 1; }
[ -d "$LYRICS_DIR" ] || { echo "Missing lyrics dir: $LYRICS_DIR"; exit 1; }

mkdir -p "$WORK/snippets" "$WORK/transcripts" "$WORK/whisper-cache"

# ---- 1. extract chapter timeline -------------------------------------------
echo "[1/5] reading chapter timeline"
docker run --rm -v "$FOLDER:/in:ro" --entrypoint ffprobe \
    jrottenberg/ffmpeg:4.4-alpine \
    -v error -show_chapters -of csv=p=0 "/in/$NAME.mkv" \
| awk -F, 'BEGIN{print "idx,start,end,duration"} {printf "%d,%s,%s,%.6f\n", NR, $4, $6, $6-$4}' \
> "$WORK/chapters.csv"
wc -l "$WORK/chapters.csv"

# ---- 2. extract 90s mp3 per chapter ----------------------------------------
echo "[2/5] extracting audio snippets"
tail -n +2 "$WORK/chapters.csv" | while IFS=, read idx start end dur; do
    snippet_dur=$(awk -v d="$dur" 'BEGIN{print (d<90?d:90)}')
    out="$WORK/snippets/ch$(printf '%02d' $idx).mp3"
    [ -f "$out" ] && continue
    docker run --rm -v "$FOLDER:/in:ro" -v "$WORK:/out" \
        jrottenberg/ffmpeg:4.4-alpine \
        -ss "$start" -t "$snippet_dur" -i "/in/$NAME.mkv" \
        -vn -ac 1 -ar 16000 -b:a 64k -loglevel error \
        "/out/snippets/ch$(printf '%02d' $idx).mp3"
done

# ---- 3. transcribe ---------------------------------------------------------
echo "[3/5] transcribing (medium → large-v3 retry)"
# mount lib so the python script is in /w too
cp "$SCRIPT_DIR/lib/transcribe.py" "$WORK/transcribe.py"
ln -snf snippets "$WORK/chapters"  # transcribe.py expects /w/chapters
docker run --rm \
    -v "$WORK:/w" \
    -v "$WORK/whisper-cache:/cache" \
    python:3.11-slim \
    bash -c "pip install --quiet --no-cache-dir faster-whisper && python /w/transcribe.py"

# ---- 4. match -> chapter titles --------------------------------------------
echo "[4/5] matching transcripts to setlist"
python3 "$SCRIPT_DIR/lib/match_chapters.py" \
    --chapters    "$WORK/chapters.csv" \
    --setlist     "$SETLIST" \
    --lyrics      "$LYRICS_DIR" \
    --transcripts "$WORK/transcripts" \
    --report      "$WORK/match_report.tsv" \
    > "$WORK/assignment.tsv"
column -t -s $'\t' "$WORK/match_report.tsv" | head -40

# ---- 5. build XML and apply ------------------------------------------------
echo "[5/5] applying chapter names"
python3 "$SCRIPT_DIR/lib/build_chapters_xml.py" \
    --chapters   "$WORK/chapters.csv" \
    --assignment "$WORK/assignment.tsv" \
    > "$FOLDER/chapters.xml"

docker run --rm -v "$FOLDER:/storage" jlesage/mkvtoolnix \
    /usr/bin/mkvpropedit "/storage/$NAME.mkv" \
    --chapters "/storage/chapters.xml"

echo "Done. Saved chapter XML to $FOLDER/chapters.xml"
