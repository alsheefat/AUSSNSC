#!/data/data/com.termux/files/usr/bin/bash
# First-time setup from Termux: creates your private GitHub repo, uploads this project,
# stores the Firebase config as a secret, builds the APK on GitHub and downloads it.
set -e
cd "$(dirname "$0")"

echo "== Installing tools =="
pkg update -y && pkg install -y git gh

echo "== GitHub login =="
if ! gh auth status >/dev/null 2>&1; then
  echo "A code will appear. Open https://github.com/login/device in your browser and enter it."
  gh auth login -p https -w
fi
gh auth setup-git

git config user.name  >/dev/null 2>&1 || git config --global user.name  "$(gh api user -q .login)"
git config user.email >/dev/null 2>&1 || git config --global user.email "$(gh api user -q .login)@users.noreply.github.com"

read -r -p "Name for the GitHub repository [aussnsc]: " REPO
REPO=${REPO:-aussnsc}

read -r -p "Render server URL (e.g. https://aussnsc-api.onrender.com) - press Enter if not deployed yet: " RURL
if [ -n "$RURL" ]; then
  RURL=${RURL%/}
  sed -i "s|^API_BASE_URL=.*|API_BASE_URL=${RURL}/api/v1/|" android/gradle.properties
fi

# Firebase config: look next to the app, then in Downloads
GS=android/app/google-services.json
if [ ! -f "$GS" ] && [ -f "$HOME/storage/downloads/google-services.json" ]; then
  cp "$HOME/storage/downloads/google-services.json" "$GS"
fi
if [ ! -f "$GS" ]; then
  echo "NOTE: google-services.json not found. The app will be built WITHOUT Google sign-in."
  echo "      (Run 'termux-setup-storage', save the file in Downloads, then run ./termux-build.sh)"
fi

[ -d .git ] || git init -b main
git add -A
git commit -m "AUSSNSC app and server" >/dev/null 2>&1 || true

echo "== Creating private repository =="
gh repo create "$REPO" --private --source=. --remote=origin 2>/dev/null || echo "(repository already exists, continuing)"
if [ -f "$GS" ]; then
  base64 -w0 "$GS" | gh secret set GOOGLE_SERVICES_JSON
  echo "Firebase config saved as a GitHub secret."
fi
git push -u origin main

echo "== Building the APK on GitHub (about 5-8 minutes) =="
sleep 8
gh run watch "$(gh run list --workflow build-apk.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status || true
./termux-build.sh --download-only
