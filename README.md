# Po'Pote

Personal recipe book and shared events — a responsive web app and an Android APK
built from the same Vue codebase, backed by a FastAPI + ArangoDB server. Sign in
once on each device and your recipes follow you; changes appear live over a
WebSocket on every device you are signed in on.

> **Status: proof of concept.** *Recettes* and *Planificateur* work.
> *Liste de courses* is a navigable placeholder.

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
                              (recipes, users, events, app_settings)

  Dexie / IndexedDB — read-only mirror of the server, identical code in
  the browser and in the Android WebView. Makes the app open instantly
  and stay readable with no connection.
```

**The server is the source of truth.** Every write goes over HTTP, comes back as
a WebSocket event, and only then is mirrored into IndexedDB. The cache never
accumulates local changes, so there is nothing to reconcile and no conflict
resolution to get wrong. Creating or editing a recipe requires a connection;
reading never does.

---

## Accounts

The login is email + password, and nothing else: no email delivery, no OAuth, no
password reset, no refresh-token rotation. That is a deliberate choice about
*this* app rather than a shortcut.

The deciding constraint is the APK. It runs from `https://localhost` inside the
WebView, so any flow that leaves the app and has to come back — Google Sign-In,
magic links, any OAuth — needs a custom URL scheme or Android App Links pinned
to the app's signing certificate. The APK is debug-signed and rebuilt by CI on
every push, so that fingerprint is not stable. Email and password is one POST
that behaves identically in a browser and in the WebView.

Three consequences worth knowing:

- **The token is a bearer token, not a cookie.** Cookies would force
  `allow_credentials=True`, an exact CORS origin list, and `SameSite=None`,
  which is fragile from the `https://localhost` WebView origin. An
  `Authorization: Bearer` header lets CORS stay at `allow_credentials=False`.
  The WebSocket takes the same token as `?token=…`, because a browser cannot
  set headers on a handshake.
- **Sessions last ten years and survive a restart.** The signing key is
  generated on first start and stored in ArangoDB (`app_settings/jwt_secret`),
  not held in memory — a key that changed on each restart would sign everyone
  out, which is exactly what the long TTL exists to prevent. Set `JWT_SECRET`
  explicitly only to share one key across several backends.
- **There is no password reset.** Nothing in the design blocks adding one: it
  is one endpoint plus an SMTP provider, and no other part changes.

**Recipes are private to their owner.** The user id always comes from the token,
never from the request, and the ownership check lives in `db.py` so no endpoint
can forget it. A recipe belonging to someone else answers 404 rather than 403,
so the API never confirms that a guessed id exists.

**Invites are share links, not email invitations.** Each event carries an opaque
code; the app turns it into `…/join/<code>` and anyone signed in who opens it
can join. No SMTP, no user directory, and no way to look someone up by address.
Opening an invite while signed out carries the destination through the login
screen, so you land on the invitation and not on the recipe list.

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
| `SEED_DEMO_DATA` | `true` | Gives each newly registered account its own copy of the demo recipes. |
| `JWT_SECRET` | *(generated)* | Left empty, a key is generated on first start and stored in ArangoDB, so sessions survive restarts with no configuration. Changing it signs everyone out. |
| `JWT_TTL_DAYS` | `3650` | Session lifetime. Long on purpose. |

The backend opens `ARANGO_DB` directly and only falls back to creating it via
`_system` if that fails, so a user scoped to a single database works fine.

Frontend, at **build** time:

| Build | Command | `VITE_API_URL` |
|---|---|---|
| Web | `npm run build` | unset → same-origin `/api` |
| APK | `npm run build:apk` | from `.env.apk` |
| Web image | `docker build ./frontend` | `--build-arg VITE_API_URL=…`, unset → same-origin `/api` |

`VITE_PUBLIC_WEB_URL` is the second build-time variable, and only the APK needs
it. Invite links must point at the public web address; inside the APK
`window.location.origin` is `https://localhost`, so a link built from it would
be dead for whoever received it. The web build falls back to its own origin.

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

Everything except `/auth/register`, `/auth/login`, `/aisles*` and `/health`
requires an `Authorization: Bearer <token>` header.

| Method | Path | |
|---|---|---|
| `POST` | `/auth/register` | Create an account → token + profile |
| `POST` | `/auth/login` | → token + profile |
| `GET` | `/auth/me` | Validate a stored token, refresh the profile |
| `PUT` | `/auth/me` | Rename, or save a rerolled avatar seed |
| `GET` | `/recipes` | Your recipes, sorted by name |
| `GET` | `/recipes/{id}` | One of your recipes |
| `POST` | `/recipes` | Create → `recipe.created` to you |
| `PUT` | `/recipes/{id}` | Replace → `recipe.updated` to you |
| `DELETE` | `/recipes/{id}` | Delete → `recipe.deleted` to you |
| `GET` | `/events` | Events you belong to, soonest first |
| `GET` | `/events/{id}` | One event you belong to |
| `POST` | `/events` | Create → `event.created` to its members |
| `PUT` | `/events/{id}` | Rename/reschedule (owner only) |
| `DELETE` | `/events/{id}` | Delete (owner only) |
| `POST` | `/events/{id}/leave` | Leave (members, not the owner) |
| `GET` | `/invites/{code}` | Invite preview, for the join screen |
| `POST` | `/invites/{code}/join` | Join. Idempotent |
| `GET` | `/aisles` | Aisle vocabulary for the override dropdown |
| `GET` | `/aisles/detect?name=…` | Guessed aisle for an ingredient name |
| `GET` | `/health` | Status, recipe count, connected WS clients |
| `WS` | `/ws?token=…` | Live feed |

On connect, `/api/ws` sends a `hello` event containing that user's full recipe
list and events. That makes it both the initial load and the resync after a
dropped connection — the client never has to work out what it missed. After that
it receives one event per change.

**Fan-out is per user, never global.** A recipe event reaches only its owner; an
event reaches each of its members. One person signed in on a phone and a laptop
has two sockets under the same id, and both receive the same messages — which is
what keeps the two devices in sync.

Ingredients get a supermarket aisle ("rayon") guessed from a keyword table in
`backend/app/aisles.py`. The form shows it as *rayon détecté* and lets the user
override it; an override is always kept.

---

## Layout

```
backend/
  app/
    main.py          FastAPI app, CORS, lifespan, /health
    auth.py          Password hashing, tokens, request dependencies
    db.py            ArangoDB access; Arango _key is exposed as `id`
    models.py        Pydantic models + the WebSocket event envelope
    ws.py            Per-user connection manager and fan-out
    aisles.py        Ingredient → aisle keyword table
    seed.py          Demo recipes
    routers/auth.py      register / login / me
    routers/recipes.py   CRUD + the /ws endpoint
    routers/events.py    Events, invites, join / leave
frontend/
  src/
    api/             REST client, reconnecting WebSocket, URL resolution,
                     session.js (the token in localStorage)
    db/cache.js      Dexie read-only offline mirror, wiped on logout
    stores/auth.js       Pinia store: session, profile, avatar
    stores/recipes.js    Pinia store: cache → live feed → UI
    stores/events.js     Pinia store: events and invites
    components/      Card, detail, form dialogs, filters, sync indicator,
                     UserAvatar (DiceBear), ProfileMenu
    views/           RecipesView (list + detail), PlannerView, LoginView,
                     JoinView (the invite link target), PlaceholderView
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

## Avatars

There is no image upload. An account stores a single number — `avatar_seed` —
and `UserAvatar.vue` turns it into a DiceBear *thumbs* avatar as inline SVG.
An avatar therefore costs four bytes in the database, renders identically on the
web and in the APK, needs no upload endpoint or file storage, and works offline
because nothing is fetched at runtime. "Changer d'avatar" just rolls a new
number.

The style definition (`@dicebear/styles/thumbs.json`, 12 KB) is parsed once at
module load rather than per component.

---

## Known limits

- **One backend process only.** The WebSocket connection map lives in process
  memory, so a second worker would only reach its own clients. Scaling out
  needs a shared broker (Redis pub/sub) first — see `backend/app/ws.py`.
- **No password reset.** There is no email delivery at all, so a forgotten
  password cannot be recovered — the signup screen says so. Adding it is one
  endpoint plus an SMTP provider.
- **Recipes created before accounts existed are orphaned.** They have no
  `owner_id`, so they match no user and are never listed. They are left in
  place rather than deleted automatically; to clear them out:

  ```aql
  FOR r IN recipes FILTER r.owner_id == null OR r.owner_id == "" REMOVE r IN recipes
  ```

- **Anyone with an invite link can join**, and links do not expire. That is the
  intended trade-off — it is what removes the need for email invitations — but
  a leaked link cannot currently be revoked without deleting the event.
- **Web offline is data-only.** Recipes are cached, but the app *shell* is not:
  loading `popote.tomansion.fr` with no connection still fails. Adding
  `vite-plugin-pwa` would fix that for the web. The APK is unaffected, since it
  ships its assets on the device.
- **Last write wins.** Two people editing the same recipe at once — the second
  save overwrites the first.
- Node 20.19+/22.12+ is required by Vite 7. Vite 8 needs a newer Node than is
  installed on the current dev machine, which is why it is pinned.
