# AUSSNSC — app + server (one repository)

## What's new in tar3 (Android 7 and older phones)
- Works on **Android 6.0+** (minSdk 23), including **Android 7.0 / 7.1**.
- **HTTPS fix for old phones:** Android 7.0 doesn't trust the newer public root certificates (Let's Encrypt ISRG X1/X2, Google Trust Services),
  so connecting to a modern server fails there. The app now adds those roots to the phone's own list, for the API **and** for gallery pictures.
- **Launcher icon** now ships as PNGs (all densities) plus an adaptive icon for Android 8+, so it shows correctly on Android 7.
- The second patch you uploaded is byte-identical to the first one, which was already merged in tar2 — nothing new to merge.

## What was new in tar2
- **Your UI phase-1 patch is merged**: new home hero card and the single "name or roll number" result search.
- **Compile error fixed**: `Session.setTheme` clashed with the property's generated setter (JVM signature clash) → renamed `applyTheme` (the patch already expected this).
- **Safer navigation**: signing in / out now clears the whole back stack (no more "back" into a stale login screen).
- **Polish**: per-tile icons, full light/dark colour schemes (chat bubbles, chips, dialogs readable in dark mode), status-bar icon colours, edge-to-edge screens, gradient welcome screen, app icon, Bengali digits accepted in result search (১২৫ → 125), lists stay on screen while refreshing.
- **Faster/cheaper**: the APK is now a *release* build (much smoother than debug); chat only polls while the screen is visible; the server computes channel access once per request (was one query per channel), uses gzip, recycles idle DB connections and has a message-pagination index.
- **Server address** now lives in `android/api.properties` (written by `termux-build.sh`) so re-extracting a new tar never resets it.
- **New server option** `RESET_ADMIN=1` to recover a lost admin password.

```
android/   Kotlin / Jetpack Compose app  -> built into an APK by GitHub Actions
backend/   FastAPI server + database     -> runs on Render
render.yaml          Render blueprint (server + PostgreSQL in one click)
.github/workflows/   builds the APK on GitHub (no Android Studio needed)
termux-setup.sh      first-time setup from Termux
termux-build.sh      rebuild + download the APK after any change
```

How it fits together: the app talks to the server over HTTPS. Google login goes
**Google → Firebase → app → your server**, and your server checks the Firebase token,
then issues its own login for the school (roles, classes, results, chat all live on your server).

---

## Step 1 · Firebase (Google login) — about 10 minutes, in the browser

1. https://console.firebase.google.com → **Add project** (name it e.g. `aussnsc`; Analytics can be off).
2. **Build → Authentication → Get started → Sign-in method → Google → Enable** → choose a support email → Save.
3. **Project settings (gear) → General → Your apps → Android icon** and enter:
   - Package name: `com.aussnsc.app`
   - **Debug signing certificate SHA-1:** `EA:50:FE:0D:5F:9F:2D:68:02:C8:48:66:AB:2C:DB:53:90:D4:01:39`
   - Register app → **Download `google-services.json`** (save it in your phone's *Downloads*).
   - If you downloaded it before adding the SHA-1 or before enabling Google sign-in, download it again afterwards.
4. Same page: copy the **Project ID** (you'll paste it into Render).

> The SHA-1 above belongs to the fixed key in `android/app/debug.keystore`, so every GitHub build has the
> same fingerprint. If you ever change that key, add the new SHA-1 in Firebase.

## Step 2 · Termux → GitHub (uploads the project, builds the APK)

```bash
pkg install tar -y
termux-setup-storage                       # allow storage access (once)
cd ~ && tar xzf ~/storage/downloads/tar3.tar.gz
cd AUSSNSC
cp ~/storage/downloads/google-services.json android/app/   # the Firebase file from step 1
bash termux-setup.sh
```

It logs in to GitHub (you approve a code in the browser), creates a **private** repo, stores
`google-services.json` as the secret `GOOGLE_SERVICES_JSON`, pushes, waits for the build and downloads
`AUSSNSC.apk`. When asked for the Render URL, press Enter (you don't have it yet).

## Step 3 · Render (the server)

1. https://dashboard.render.com → **New → Blueprint** → connect GitHub → pick your repo.
2. Render reads `render.yaml` and asks for three values:
   - `ADMIN_PHONE` – your admin login (e.g. `01712345678`)
   - `ADMIN_PASSWORD` – a strong password
   - `FIREBASE_PROJECT_ID` – from step 1.4
3. **Apply**. After the first deploy open `https://YOUR-SERVICE.onrender.com/health` – you should see `{"status":"ok"}`.
4. Copy the service URL (e.g. `https://aussnsc-api.onrender.com`).

## Step 4 · Point the app at your server and rebuild

```bash
cd ~/AUSSNSC
bash termux-build.sh https://YOUR-SERVICE.onrender.com
```
The APK downloads to *Downloads/AUSSNSC.apk* (Termux offers to open it; allow “install unknown apps” for Termux/your browser).

**Every later change:** edit files, then `bash termux-build.sh`. You can also download the newest APK from the
repo's **Releases → apk-latest** page in the GitHub app.

---

## Already installed an earlier tar? Update in place

```bash
cd ~/AUSSNSC
tar xzf ~/storage/downloads/tar3.tar.gz --strip-components=1   # overwrites code; keeps your .git, google-services.json and api.properties
bash termux-build.sh        # commit + push + build + download the new APK
```
Render redeploys the server by itself when the push reaches GitHub. (Your server address is kept in `android/api.properties`;
if you've never run `termux-build.sh https://YOUR-URL` with the new scripts, run it once that way.)

## First use as admin

1. Open the app → **Sign in** with `ADMIN_PHONE` + `ADMIN_PASSWORD`. You'll see the admin tools (dashboard, users, parent links, admission applications, post notice).
2. Classes 6–10 (A/B) and each class's chat channels already exist.
3. **Adding students, teachers, results, routines, gallery, school info** is done in the server's built-in admin page
   `https://YOUR-SERVICE.onrender.com/docs`:
   - Open **POST /api/v1/auth/login** → *Try it out* → your phone + password → copy `access_token`.
   - Press **Authorize** (top right), paste the token → Authorize. (Tokens last 60 minutes; log in again when expired.)
   - Then use the `/admin/...` endpoints: `POST /admin/students`, `POST /admin/students/import` (CSV), `POST /admin/teachers`,
     `POST /admin/teachers/{id}/classes`, `POST /admin/results/import` (CSV) + `POST /admin/results/publish`,
     `PUT /admin/routines/class/{class_id}`, `PUT /admin/content/about`, gallery endpoints, etc.
4. A person registers in the app (or with Google) → becomes a **public** account. In the app: **Users → tap the person → Make student/parent/teacher**.
   - **Student:** create their student record with `POST /admin/students` and `"user_id": <their user id>` (user ids are in `GET /admin/users`).
   - **Teacher:** `POST /admin/teachers` with their `user_id`, then `POST /admin/teachers/{id}/classes`.
   - **Parent:** they send *Link a child* in the app → you approve it under **Pending Parent Links** (this also makes them a parent).

---

## What works / what doesn't yet (read this)

- Built and checked as far as possible without a phone or internet: the Kotlin app was **not compiled** and the server was **not run** in
  the sandbox. The first GitHub build may fail on a small compile error — open the failed run in GitHub (Actions tab), copy the red
  error lines and send them to me; they're usually one-line fixes.
- **Free-tier behaviour (Render):** the server sleeps after ~15 minutes idle and the first request takes up to a minute. The free
  PostgreSQL database has an expiry/size limit — check Render's current free-plan terms before relying on it for real school data
  and upgrade the database (or take backups) when you go live.
- **Uploaded files are not persistent on Render's free plan** (the disk resets on every restart/deploy). The app does not
  upload files yet; teachers share materials as links. Before enabling uploads, move files to persistent storage (Render disk or
  Firebase Storage).
- **SMS/email OTP are placeholders** — codes only appear in the Render logs until you connect an SMS provider. Nothing in the app
  needs them: sign-in uses password or Google.
- **Push notifications** are not wired in the app yet (the server side is ready).
- **Language:** the English/বাংলা choice is saved on the account, but the app text itself is English only for now.
- Chat refreshes every 4 seconds (the server also has a WebSocket for real-time when you want it).
- The APK is a release build signed with the fixed key in `android/app/debug.keystore` — fine for installing directly on phones, not for Google Play. For Play you need your own private release key.
- Teachers can't attach files to assignments, and students can't attach files to submissions, in this version (text only).
- Name-based public result search is on by design (limited and rate-limited). Think about student privacy before using real data.

## Troubleshooting

| Symptom | Fix |
|---|---|
| “Can't reach the server” | Free server waking up – wait a minute and retry. Check the URL ends in `.onrender.com` and `/api/v1/` is in `android/gradle.properties`. |
| Google button says “isn't set up in this build” | The `GOOGLE_SERVICES_JSON` secret was missing. Put the file in `android/app/` and run `bash termux-build.sh`. |
| Google sign-in error 10 / “developer error” | SHA-1 not added in Firebase (step 1.3), or you didn't re-download `google-services.json` after adding it. |
| “Google sign-in could not be verified” | `FIREBASE_PROJECT_ID` on Render must equal the Firebase Project ID exactly. |
| Build fails | Open GitHub → your repo → Actions → the red run → copy the error text. (To test faster, change `assembleRelease` to `assembleDebug` in `.github/workflows/build-apk.yml` and the two `apk/release/app-release.apk` paths to `apk/debug/app-debug.apk`.) |
| Forgot admin password | Render → your service → Environment: set `ADMIN_PASSWORD` to a new value and add `RESET_ADMIN` = `1`, save (it redeploys), sign in, then **delete `RESET_ADMIN`**. |
