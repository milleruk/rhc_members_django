#!/usr/bin/env bash
set -euo pipefail

# Source your actual .env file
ENV_FILE="${1:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ No $ENV_FILE found"
  exit 1
fi

OUTPUT=".env.example"

echo "Generating $OUTPUT from $ENV_FILE ..."

# Parse and strip secrets, keep only keys and placeholders
awk -F= '
  /^[A-Za-z0-9_]+=/ {
    key=$1
    print key"="
  }
' "$ENV_FILE" > "$OUTPUT"

echo "✅ Done. Review $OUTPUT and commit it (never commit real .env)."
