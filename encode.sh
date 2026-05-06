#!/bin/bash

# MKV H.265エンコードスクリプト (Plex形式対応)
# Usage: ./encode.sh <input_folder> [crf]
# Example: ./encode.sh output/MY_DISC

set -e

INPUT_DIR="$1"
CRF="${2:-20}"  # デフォルト CRF 20

if [ -z "$INPUT_DIR" ]; then
    echo "Usage: $0 <input_folder> [crf]"
    echo "Example: $0 output/MY_DISC"
    echo "         $0 output/MY_DISC 22"
    exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Directory not found: $INPUT_DIR"
    exit 1
fi

# 絶対パスに変換
INPUT_DIR=$(realpath "$INPUT_DIR")
FOLDER_NAME=$(basename "$INPUT_DIR")
OUTPUT_DIR="$(dirname "$INPUT_DIR")/../encoded/$FOLDER_NAME"

mkdir -p "$OUTPUT_DIR"

# ファイルサイズ最大のファイルをメインとして検出
MAIN_FILE=$(ls -S "$INPUT_DIR"/*.mkv 2>/dev/null | head -1)
MAIN_FILENAME=$(basename "$MAIN_FILE")

echo "================================"
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_DIR"
echo "CRF:    $CRF"
echo "Main:   $MAIN_FILENAME (largest file)"
echo "================================"

# MKVファイルをエンコード
for mkv in "$INPUT_DIR"/*.mkv; do
    [ -f "$mkv" ] || continue

    filename=$(basename "$mkv")
    basename_noext="${filename%.mkv}"

    # 出力ファイル名を決定
    # ファイルサイズ最大 → メイン (フォルダ名.mkv)
    # それ以外 → シーン (元ファイル名-scene.mkv)
    if [[ "$filename" == "$MAIN_FILENAME" ]]; then
        output_file="$OUTPUT_DIR/${FOLDER_NAME}.mkv"
        echo ""
        echo "[MAIN] $filename -> ${FOLDER_NAME}.mkv"
    else
        output_file="$OUTPUT_DIR/${basename_noext}-scene.mkv"
        echo ""
        echo "[SCENE] $filename -> ${basename_noext}-scene.mkv"
    fi

    if [ -f "$output_file" ]; then
        echo "Skip (exists): $(basename "$output_file")"
        continue
    fi

    echo "----------------------------------------"

    docker run --rm \
        -v "$INPUT_DIR:/input:ro" \
        -v "$OUTPUT_DIR:/output" \
        jrottenberg/ffmpeg:4.4-alpine \
        -i "/input/$filename" \
        -map 0:v -map 0:a -map 0:s? -map_chapters 0 \
        -c:v libx265 -crf "$CRF" -preset medium \
        -c:a aac -b:a 320k \
        -c:s copy \
        "/output/$(basename "$output_file")"

    echo "Done: $(basename "$output_file")"
done

echo ""
echo "================================"
echo "All done!"
echo "Output: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"
