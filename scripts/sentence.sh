#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/sentence.sh 契約
# Reads APP_SECRET from .env and requests a sentence for the given word
# from the deployed jp-srs API.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <word>" >&2
    exit 1
fi

WORD="$1"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found" >&2
    exit 1
fi

APP_SECRET="$(grep -E '^APP_SECRET=' "$ENV_FILE" | head -n1 | cut -d= -f2-)"

if [ -z "$APP_SECRET" ]; then
    echo "Error: APP_SECRET not set in $ENV_FILE" >&2
    exit 1
fi

curl -sS -G \
    -H "X-App-Secret: $APP_SECRET" \
    --data-urlencode "word=$WORD" \
    "https://jp-srs-production.up.railway.app/sentence"
