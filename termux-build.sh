#!/data/data/com.termux/files/usr/bin/bash
# Rebuild the APK after any change.
#   ./termux-build.sh                       commit + push + build + download
#   ./termux-build.sh https://x.onrender.com   also point the app at your Render server first
#   ./termux-build.sh --download-only       just fetch the newest APK
set -e
cd "$(dirname "$0")"

if [ "$1" != "--download-only" ]; then
  if [ -n "$1" ]; then
    sed -i "s|^API_BASE_URL=.*|API_BASE_URL=${1%/}/api/v1/|" android/gradle.properties
  fi
  GS=android/app/google-services.json
  [ -f "$GS" ] || { [ -f "$HOME/storage/downloads/google-services.json" ] && cp "$HOME/storage/downloads/google-services.json" "$GS"; } || true
  [ -f "$GS" ] && base64 -w0 "$GS" | gh secret set GOOGLE_SERVICES_JSON
  git add -A
  git commit -m "Update app" >/dev/null 2>&1 || true
  git push
  gh workflow run build-apk.yml >/dev/null 2>&1 || true
  sleep 10
  gh run watch "$(gh run list --workflow build-apk.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
fi

mkdir -p "$HOME/storage/downloads" 2>/dev/null || true
OUT="$HOME/storage/downloads"
[ -d "$OUT" ] || OUT="$HOME"
gh release download apk-latest -p AUSSNSC.apk -D "$OUT" --clobber
echo "APK saved to: $OUT/AUSSNSC.apk"
command -v termux-open >/dev/null && termux-open "$OUT/AUSSNSC.apk" || true
