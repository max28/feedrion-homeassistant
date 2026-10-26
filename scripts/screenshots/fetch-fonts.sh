#!/usr/bin/env bash
# Downloads the open-licence (SIL OFL) Google fonts the screenshots are drawn
# with, so every language renders with a real face instead of whatever the
# machine happens to have. Output: fonts/fonts.css + the woff2 files beside it
# (git-ignored). Optional: render.mjs falls back on system fonts without it.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p fonts
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
FAMILIES="family=Roboto:wght@300;400;500;700&family=Lora:wght@700&family=Noto+Sans+JP:wght@400;700&family=Noto+Sans+SC:wght@400;700&family=Noto+Sans+KR:wght@400;700&family=Noto+Sans+Bengali:wght@400;700&family=Noto+Sans+Devanagari:wght@400;700&family=Noto+Sans+Arabic:wght@400;700"
curl -fsS -A "$UA" "https://fonts.googleapis.com/css2?${FAMILIES}&display=block" -o fonts/remote.css
: > fonts/fonts.css
i=0
while IFS= read -r line; do
  if [[ "$line" =~ url\((https://fonts\.gstatic\.com/[^\)]+\.woff2)\) ]]; then
    url="${BASH_REMATCH[1]}"
    name="f$(printf '%04d' "$i").woff2"
    i=$((i + 1))
    [ -s "fonts/$name" ] || curl -fsS -A "$UA" "$url" -o "fonts/$name"
    line="${line/$url/$name}"
  fi
  printf '%s\n' "$line" >> fonts/fonts.css
done < fonts/remote.css
rm fonts/remote.css
echo "fetch-fonts: $i files in $(pwd)/fonts"
