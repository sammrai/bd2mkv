#!/bin/bash

# MakeMKV Ripping Script
# Automatically rips all titles from disc to a directory named after the disc
# Skips already ripped titles

CONTAINER="makemkv"
MAKEMKV="/opt/makemkv/bin/makemkvcon"
OUTPUT_DIR="/output"

echo "Getting disc info..."
DISC_INFO=$(docker exec $CONTAINER $MAKEMKV -r info disc:0 2>&1)

# Extract disc name from DRV line (6th field)
# Format: DRV:0,2,999,12,"drive info","DISC_NAME","/dev/sr0"
DISC_NAME=$(echo "$DISC_INFO" | grep -E "^DRV:0," | sed 's/.*","\([^"]*\)",".*/\1/')

if [ -z "$DISC_NAME" ] || [ "$DISC_NAME" = "" ]; then
    # Fallback: try CINFO:2 (disc name)
    DISC_NAME=$(echo "$DISC_INFO" | grep -E "^CINFO:2,0," | sed 's/CINFO:2,0,"//' | sed 's/"$//')
fi

if [ -z "$DISC_NAME" ]; then
    echo "Could not detect disc name. Using timestamp."
    DISC_NAME="disc_$(date +%Y%m%d_%H%M%S)"
fi

FOLDER_NAME="$DISC_NAME"
OUTPUT_PATH="./output/$FOLDER_NAME"

echo "Disc name: $DISC_NAME"
echo "Output folder: $OUTPUT_PATH/"

# Create output directory
mkdir -p "$OUTPUT_PATH"
docker exec $CONTAINER mkdir -p "$OUTPUT_DIR/$FOLDER_NAME"

# Get list of titles from disc (title numbers)
TITLES=$(echo "$DISC_INFO" | grep -E "^TINFO:[0-9]+," | sed 's/TINFO:\([0-9]*\),.*/\1/' | sort -n | uniq)

if [ -z "$TITLES" ]; then
    echo "No titles found on disc."
    exit 1
fi

echo ""
echo "Titles on disc: $(echo $TITLES | tr '\n' ' ')"

# Check existing files and determine which titles to rip
TITLES_TO_RIP=""
SKIPPED=""

for t in $TITLES; do
    # Check if file matching *_t0X.mkv exists
    PATTERN=$(printf "_t%02d.mkv" $t)
    if ls "$OUTPUT_PATH"/*"$PATTERN" 1>/dev/null 2>&1; then
        SKIPPED="$SKIPPED $t"
    else
        TITLES_TO_RIP="$TITLES_TO_RIP $t"
    fi
done

if [ -n "$SKIPPED" ]; then
    echo "Skipping already ripped:$SKIPPED"
fi

if [ -z "$TITLES_TO_RIP" ]; then
    echo ""
    echo "All titles already ripped!"
    ls -lh "$OUTPUT_PATH/"
    exit 0
fi

echo "Titles to rip:$TITLES_TO_RIP"
echo ""

# Rip each missing title
for t in $TITLES_TO_RIP; do
    echo "=== Ripping title $t ==="
    docker exec $CONTAINER $MAKEMKV mkv disc:0 $t "$OUTPUT_DIR/$FOLDER_NAME" --progress=-stdout
    echo ""
done

echo ""
echo "Done! Files saved to: $OUTPUT_PATH/"
ls -lh "$OUTPUT_PATH/"
