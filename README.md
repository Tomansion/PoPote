# Po'Pote

Shared recipe book — a responsive web app and an Android APK built from the same
Vue codebase, backed by a FastAPI + ArangoDB server. Everyone connected sees new
and edited recipes appear live over a WebSocket, with no account to create.

> **Status: proof of concept.** Only the *Recettes* section works. *Planificateur*
> and *Liste de courses* are navigable placeholders.

---

## How it fits together

```
        Vue 3 + Vuetify  (one codebase, two builds)
                │
    ┌───────────┴───────────┐
    │                       │
  web build              APK build
  VITE_API_URL unset     VITE_API_URL=https://popote-back.tomansion.fr/api
  → calls /api           → calls that absolute URL
    │                       │
    └───────────┬───────────┘
                │  REST (writes)  +  WebSocket (live updates)
                ▼
         FastAPI  ──────────▶  ArangoDB
                              (collection: recipes)

  Dexie / IndexedDB — read-only mirror of the server, identical code in
  the browser and in the Android WebView. Makes the app open instantly
  and stay readable with no connection.
```

**The server is the source of truth.** Every write goes over HTTP, comes back as
a WebSocket broadcast, and only then is mirrored into IndexedDB. The cache never
accumulates local changes, so there is nothing to reconcile and no conflict
resolution to get wrong. Creating or editing a recipe requires a connection;
reading never does.

---

## Run it locally

### Option A — Docker (everything, including a local ArangoDB)

```bash
cp .env.example .env          # optional; defaults work as-is
docker compose up --build
```

> **Use Compose v2** (`docker compose`, the CLI plugin). The older standalone
> `docker-compose` v1.29 parses this file, but on Docker Engine 26+ it crashes
> with `KeyError: 'ContainerConfig'` whenever it recreates an existing
> container — so `up --build` only works after a `down`. Install the plugin
> with `sudo apt install docker-compose-plugin`.

| | URL |
|---|---|
| Web app | <http://localhost:8080> |
| API docs | <http://localhost:8100/docs> |
| ArangoDB UI | <http://localhost:8529> (user `root`, password `popote`) |

Six demo recipes are inserted on first start, when the collection is empty.

> Ports 8100 and 8080 are used instead of the more usual 8000/80 because
> port 8000 is already taken on the current dev machine.

### Option B — Run the two services directly

**Backend** (needs Python 3.10+, and an ArangoDB to talk to):

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env         # then edit: point ARANGO_* at your database
.venv/bin/uvicorn app.main:app --reload --port 8100
```

**Frontend** (needs Node 20.19+ or 22.12+):

```bash
cd frontend
npm install
npm run serve                  # http://localhost:5173
```

The dev server proxies `/api` (including the WebSocket upgrade) to
`localhost:8100`, so no CORS setup is needed while developing.

To see the live sync working, open <http://localhost:5173> in two windows and
add a recipe in one.

---

## Configuration

Backend, via `backend/.env` (see `backend/.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `ARANGO_URL` | `http://localhost:8529` | |
| `ARANGO_DB` | `popote` | |
| `ARANGO_USER` / `ARANGO_PASSWORD` | `root` / `popote` | |
| `CORS_ORIGINS` | `*` | Comma-separated. Must include `https://localhost` — the APK's origin — if you narrow it. |
| `SEED_DEMO_DATA` | `true` | Only seeds when the collection is empty. |

The backend opens `ARANGO_DB` directly and only falls back to creating it via
`_system` if that fails, so a user scoped to a single database works fine.

Frontend, at **build** time:

| Build | Command | `VITE_API_URL` |
|---|---|---|
| Web | `npm run build` | unset → same-origin `/api` |
| APK | `npm run build:apk` | from `.env.apk` |
| Web image | `docker build ./frontend` | `--build-arg VITE_API_URL=…`, unset → same-origin `/api` |

Deploying the frontend image on its own — without a `backend` container next to
it — means there is no same-origin API to proxy to, so the absolute URL has to
be passed as a **build arg**; a runtime env var on the container arrives after
Vite has already inlined the value and does nothing:

```sh
docker build --build-arg VITE_API_URL=https://popote-back.tomansion.fr/api ./frontend
```

That backend is then a different origin, so its `CORS_ORIGINS` must list the
frontend's origin (and the live feed goes to `wss://…/api/ws`, which the reverse
proxy in front of the backend has to allow to upgrade).

---

## The Android APK

### Download one

Every push to `main` builds an APK in CI (`.github/workflows/apk.yml`) and
publishes it to the rolling `latest` prerelease, so this link always serves the
newest build as a plain `.apk` — installable straight from a phone browser:

<https://github.com/Tomansion/EveryMeal/releases/download/latest/popote-latest.apk>

The same APK is also attached to the workflow run's **Artifacts** section, but
GitHub zips artifacts, so that copy has to be unzipped first. For a version you
can pin to, tag a release:

```bash
git tag v0.1.0 && git push --tags     # attaches the APK to a GitHub Release
```

To build against a different backend, run the workflow manually
(**Actions → Build Android APK → Run workflow**) and fill in the URL.

The APK is **debug-signed**, so Android will ask you to allow installation from
an unknown source. That is expected; a Play Store build would need a real
signing key.

### Build one locally

Needs **JDK 21** and the Android SDK (easiest via Android Studio) — neither is
required for web development.

```bash
cd frontend
npm run apk:add       # once: generates the android/ Gradle project
npm run apk:build     # builds the web assets and assembles the APK
# → android/app/build/outputs/apk/debug/app-debug.apk
```

`android/` is generated rather than committed, so it is regenerated from
whatever Capacitor version `package.json` pins.

### Versioning

`version` in `frontend/package.json` is the source of truth. CI stamps it into
the generated Gradle project as the Android `versionName` (the number the app
info screen shows) and names the artifact after it; `versionCode`, which only
has to increase, is the CI run number. A local `npm run apk:build` skips that
stamping and keeps Capacitor's template default of `1.0`, so bump the version in
`package.json` and let CI build the APK you actually hand out.

### Branding

`frontend/assets/logo.png` (1354x1423) is the master artwork; everything else is
derived from it and committed, so no build step needs an image toolchain:

| File | What it feeds |
|---|---|
| `assets/icon.png` | 1024x1024 square icon (the master stretched to square) |
| `assets/icon-foreground.png` | adaptive-icon foreground: the artwork alone, scaled into Android's safe zone so no mask shape clips it |
| `assets/icon-background.png` | adaptive-icon background: flat `#0D3744` |
| `assets/splash.png`, `assets/splash-dark.png` | 2732x2732 launch screen |
| `public/favicon.ico` | browser tab (16/32/48) |
| `public/apple-touch-icon.png` | iOS home-screen bookmark (180x180) |
| `public/intro.mp4` | the launch animation (see Intro animation) |

`@capacitor/assets` turns the `assets/` sources into every Android density
(`npm run apk:assets`, run automatically by `npm run apk:build` and by CI). It
has to run after `cap add android`, since it writes into the generated project.

`assets/logo.svg` is kept as the vector master but is not used by any build —
its outlines do not survive rasterisation, so the PNG is the reference.

### Why the APK needs an absolute URL

Inside the APK the app is served from `https://localhost` by the WebView, so a
relative `/api` path resolves to nothing. `.env.apk` bakes in the real backend
URL, and CI fails the build if no absolute URL ends up in the bundle.

---

## API

Everything is under `/api`.

| Method | Path | |
|---|---|---|
| `GET` | `/recipes` | All recipes, sorted by name |
| `GET` | `/recipes/{id}` | One recipe |
| `POST` | `/recipes` | Create → broadcasts `recipe.created` |
| `PUT` | `/recipes/{id}` | Replace → broadcasts `recipe.updated` |
| `DELETE` | `/recipes/{id}` | Delete → broadcasts `recipe.deleted` |
| `GET` | `/aisles` | Aisle vocabulary for the override dropdown |
| `GET` | `/aisles/detect?name=…` | Guessed aisle for an ingredient name |
| `GET` | `/health` | Status, recipe count, connected WS clients |
| `WS` | `/ws` | Live feed |

On connect, `/api/ws` sends a `hello` event containing the full recipe list.
That makes it both the initial load and the resync after a dropped connection —
the client never has to work out what it missed. After that it receives one
event per change.

Ingredients get a supermarket aisle ("rayon") guessed from a keyword table in
`backend/app/aisles.py`. The form shows it as *rayon détecté* and lets the user
override it; an override is always kept.

---

## Layout

```
backend/
  app/
    main.py          FastAPI app, CORS, lifespan, /health
    db.py            ArangoDB access; Arango _key is exposed as `id`
    models.py        Pydantic models + the WebSocket event envelope
    ws.py            In-memory connection manager and broadcast
    aisles.py        Ingredient → aisle keyword table
    seed.py          Demo recipes
    routers/recipes.py   CRUD + the /ws endpoint
frontend/
  src/
    api/             REST client, reconnecting WebSocket, URL resolution
    db/cache.js      Dexie read-only offline mirror
    stores/recipes.js    Pinia store: cache → live feed → UI
    components/      Card, detail, form dialog, filters, sync indicator
    views/           RecipesView (list + detail), PlaceholderView
  assets/          icon/splash sources for the launcher icon (see Branding)
  public/          favicon.ico, apple-touch-icon.png, intro.mp4 — copied to dist/ as-is
  capacitor.config.json
.github/workflows/apk.yml
docker-compose.yml
```

---

## Intro animation

`IntroSplash.vue` covers the app with `public/intro.mp4` (5s, 720p, 887 KB) on
every start, then fades out over 320ms. It is the same component on the web and
in the APK — the APK is this bundle in a WebView, so nothing about it is
Android-specific.

Three things it has to get right:

- **Muted.** The clip has an audio track, and both Chrome and the Android
  WebView refuse to autoplay one unless the element is muted at `play()` time.
  It is set as a property, since Vue does not reflect the `muted` attribute.
- **Never traps the app.** A tap anywhere, the *Passer* button, any key, a
  decode error, a rejected `play()` and an 8s failsafe all land on the same
  fade-out. The store loads behind the overlay, so the list is ready underneath.
- **Skipped entirely under `prefers-reduced-motion`.**

The letterbox bars are invisible because the overlay's background is sampled
from the clip (`#0A3341`).

The one real difference between the platforms is cost: in the APK the video is
bundled, while on the web it is 887 KB fetched on each visit (cached for 30 days
by `nginx.conf`). To show it only once per browser session instead, guard
`showIntro` in `App.vue` with a `sessionStorage` flag.

---

## Known limits

- **One backend process only.** The WebSocket client set lives in process
  memory, so a second worker would only broadcast to its own clients. Scaling
  out needs a shared broker (Redis pub/sub) first — see `backend/app/ws.py`.
- **No auth.** Anyone who can reach the API can edit and delete any recipe.
  That is the intended POC behaviour ("no account creation"), but it means the
  deployment should not be publicly writable long-term.
- **Web offline is data-only.** Recipes are cached, but the app *shell* is not:
  loading `popote.tomansion.fr` with no connection still fails. Adding
  `vite-plugin-pwa` would fix that for the web. The APK is unaffected, since it
  ships its assets on the device.
- **Last write wins.** Two people editing the same recipe at once — the second
  save overwrites the first.
- Node 20.19+/22.12+ is required by Vite 7. Vite 8 needs a newer Node than is
  installed on the current dev machine, which is why it is pinned.
