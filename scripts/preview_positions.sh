#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/preview_positions.sh /absolute/path/to/image.jpg ["Recipe Title"] ["Optional subtitle"]

Environment overrides:
  API_URL       Default: http://127.0.0.1:8764
  AUTH_TOKEN    Default: dev-token-change-me
  OUTPUT_DIR    Default: preview_outputs
  THEMES        Default: "warm_light sage mocha"
  POSITIONS     Default: "top center bottom"
  TITLE_ALIGN   Default: center
  BRAND         Default: nomadmouse.com
EOF
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 1
fi

IMAGE_PATH="$1"
TITLE="${2:-Brown Butter Banana Bread}"
SUBTITLE="${3:-Soft, moist, and easy to make}"

API_URL="${API_URL:-http://127.0.0.1:8764}"
AUTH_TOKEN="${AUTH_TOKEN:-dev-token-change-me}"
OUTPUT_DIR="${OUTPUT_DIR:-preview_outputs}"
THEMES="${THEMES:-warm_light sage mocha}"
POSITIONS="${POSITIONS:-top center bottom}"
TITLE_ALIGN="${TITLE_ALIGN:-center}"
BRAND="${BRAND:-nomadmouse.com}"

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "Input image not found: $IMAGE_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "API_URL=$API_URL"
echo "OUTPUT_DIR=$OUTPUT_DIR"
echo "TITLE=$TITLE"
echo "SUBTITLE=$SUBTITLE"
echo "TITLE_ALIGN=$TITLE_ALIGN"
echo "BRAND=$BRAND"
echo

for position in $POSITIONS; do
  for theme in $THEMES; do
    echo "Rendering position=$position theme=$theme"

    response="$(
      curl -sS -X POST "$API_URL/images/process" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
        -F "file=@${IMAGE_PATH}" \
        -F "title=${TITLE}" \
        -F "subtitle=${SUBTITLE}" \
        -F "position=${position}" \
        -F "theme=${theme}" \
        -F "title_align=${TITLE_ALIGN}" \
        -F "brand=${BRAND}"
    )"

    stored_filename="$(
      printf '%s' "$response" | python -c 'import json, sys; print(json.load(sys.stdin)["stored_filename"])'
    )"

    curl -sS -L \
      -H "Authorization: Bearer $AUTH_TOKEN" \
      "$API_URL/images/$stored_filename" \
      --output "$OUTPUT_DIR/${position}_${theme}.jpeg"

    printf '%s\n' "$response" > "$OUTPUT_DIR/${position}_${theme}.json"
    echo "Saved $OUTPUT_DIR/${position}_${theme}.jpeg"
  done
done

echo
echo "Done. Outputs are in $OUTPUT_DIR/"
