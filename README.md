# Po'Pote

Personal recipe book and shared events — a responsive web app and an Android APK
built from the same Vue codebase, backed by a FastAPI + ArangoDB server. Sign in
once on each device and your recipes follow you; changes appear live over a
WebSocket on every device you are signed in on.

> **Status: proof of concept.** All three sections work: *Recettes*,
> *Planificateur* (a shared meal calendar) and *Liste de courses* (generated
> from a plan, and shareable with people who have no account).

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
                              (recipes, users, events, plans,
                               grocery_lists, app_settings)
             │
             └──────────────▶  RustFS (S3-compatible)
                              recipe photos, full size + thumbnail

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

**Recipes are private to their owner — writing them, at least.** The user id
always comes from the token, never from the request, and both checks live in
`db.py` so no endpoint can forget them. Editing and deleting are the owner's
alone. *Reading* extends to anyone who shares an event with them, which is what
makes member pages and the planner's recipe picker possible: an event is the
only place two accounts ever meet, so "we are cooking together" is exactly the
moment recipes need to cross between them. Anything outside both rules answers
404 rather than 403, so the API never confirms that a guessed id exists.

The same rule covers the ten profile answers — what someone eats, what they
will not touch, and their favourite cheese. Visible to the people you are
planning a weekend with; invisible to everyone else.

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
| ArangoDB UI | <http://localhost:8529> (user `root`, password `popote`) |

Each account is given its own copy of six demo recipes when it registers
(`SEED_DEMO_DATA`), so a new sign-up opens onto something rather than nothing.

### Option B — Run the two services directly

**Backend** (needs Python 3.10+, and an ArangoDB to talk to):

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env         # then edit: point ARANGO_* at your database
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**Frontend** (needs Node 20.19+ or 22.12+):

```bash
cd frontend
npm install
npm run serve                  # http://localhost:5173
```

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
| `RUSTFS_ENDPOINT` | *(empty)* | Object store for recipe photos. Left empty, uploading a photo answers 503 and everything else works. |
| `RUSTFS_PUBLIC_URL` | `http://localhost:9000` | What the *browser* can reach — different from `RUSTFS_ENDPOINT` whenever that one is an internal container hostname. |
| `OPENAI_API_KEY` | *(empty)* | Used for one thing: estimating what a shopping list costs. Left empty, the list works without an estimate. |
| `OPENAI_MODEL` | `gpt-4o-mini` | |

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
| `PUT` | `/auth/me` | Rename, reroll the avatar, or save the ten answers |
| `GET` | `/users/{id}` | Someone else's page: their answers + the recipes you may read. 404 unless you share an event |
| `GET` | `/recipes` | Your recipes, sorted by name |
| `GET` | `/recipes/{id}` | One recipe — yours, or a co-member's |
| `POST` | `/recipes` | Create → `recipe.created` to you |
| `PUT` | `/recipes/{id}` | Replace → `recipe.updated` to you |
| `DELETE` | `/recipes/{id}` | Delete → `recipe.deleted` to you |
| `POST` | `/recipes/{id}/image` | Upload a photo (multipart). Resized server-side into two sizes |
| `DELETE` | `/recipes/{id}/image` | Drop the photo, back to the generated gradient |
| `GET` | `/events` | Events you belong to, soonest first |
| `GET` | `/events/{id}` | One event you belong to |
| `POST` | `/events` | Create → `event.created` to its members |
| `PUT` | `/events/{id}` | Rename/reschedule/re-count (owner only) |
| `DELETE` | `/events/{id}` | Delete, taking its plan and list with it (owner only) |
| `POST` | `/events/{id}/leave` | Leave (members, not the owner) |
| `GET` | `/events/{id}/recipes` | Every member's recipes, for the planner's picker |
| `GET` | `/events/{id}/plan` | The meal plan |
| `PUT` | `/events/{id}/plan/{day}/{slot}` | Replace one part of one day → `plan.updated` to members |
| `PUT` | `/events/{id}/plan/{day}/cooks` | Set who is on duty for the whole day |
| `POST` | `/events/{id}/plan/move` | Drag & drop, one or many meals at once |
| `GET` | `/events/{id}/grocery-list` | The event's list |
| `POST` | `/events/{id}/grocery-list` | (Re)generate it from the plan: unit-aware aggregation, then an LLM pass that merges what the unit table alone could not, keeping ticks and assignments |
| `POST` | `/events/{id}/grocery-list/prices` | Ask the model to price it |
| `POST` | `/events/{id}/grocery-list/assign` | Put members on some lines — one article, a whole rayon, or a whole recipe's worth |
| `GET` | `/grocery-lists` | Every list from every event you belong to |
| `GET` | `/invites/{code}` | Invite preview, for the join screen |
| `POST` | `/invites/{code}/join` | Join. Idempotent |
| `GET` | `/aisles` | Aisle vocabulary for the override dropdown |
| `GET` | `/aisles/detect?name=…` | Guessed aisle for an ingredient name |
| `GET` | `/health` | Status, recipe count, connected WS clients |
| `WS` | `/ws?token=…` | Live feed |

**No token at all** — these three are the shared shopping list, and the code in
the URL is the only credential:

| Method | Path | |
|---|---|---|
| `GET` | `/public/grocery-lists/{code}` | Read one list, members included (names + avatars, never emails — needed to show who is assigned) |
| `PATCH` | `/public/grocery-lists/{code}/items/{key}` | Tick or untick a line |
| `WS` | `/public/grocery-lists/{code}/ws` | Live feed for that one list |

On connect, `/api/ws` sends a `hello` event containing that user's full recipe
list and events. That makes it both the initial load and the resync after a
dropped connection — the client never has to work out what it missed. After that
it receives one event per change.

**Fan-out is per user, never global.** A recipe event reaches only its owner; an
event — and the plan or grocery list hanging off it — reaches each of its
members. One person signed in on a phone and a laptop has two sockets under the
same id, and both receive the same messages, which is what keeps the two devices
in sync.

The shared shopping list needs a second scheme, because the person ticking boxes
at the shop may have no account and so no user id to address. `ws.py` therefore
has a *room* manager keyed by the list's share code: whoever holds the link is
in the room, and every tick reaches everyone else looking at the same list.

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
    ws.py            Per-user fan-out, and per-room fan-out for shared lists
    aisles.py        Ingredient → aisle keyword table
    groceries.py     Plan + recipes → one aggregated shopping list, plus the
                     deterministic veto in front of the model's fusion pass
    images.py        Uploaded photo → full size + thumbnail (Pillow)
    storage.py       RustFS/S3 put and delete
    ai.py            The two LLM calls: pricing a list, and merging its lines
    seed.py          Demo recipes
    routers/auth.py      register / login / me / member pages
    routers/recipes.py   CRUD, photo upload + the /ws endpoint
    routers/events.py    Events, invites, join / leave, the meal plan
    routers/groceries.py Lists, prices, and the three unauthenticated routes
frontend/
  src/
    api/             REST client, reconnecting WebSocket, URL resolution,
                     session.js (the token in localStorage)
    db/cache.js      Dexie read-only offline mirror, wiped on logout
    stores/auth.js       Pinia store: session, profile, avatar, answers
    stores/recipes.js    Pinia store: cache → live feed → UI; owns the socket
    stores/events.js     Pinia store: events and invites
    stores/plan.js       Pinia store: meal plans and the drag selection
    stores/grocery.js    Pinia store: lists, ticking, the shared page's socket
    components/      Cards, detail, form dialogs, filters, UserAvatar
                     (DiceBear), AppLogo (doubles as the way home),
                     SectionHeader (shared by form and display),
                     PlannerCalendar + MealSlotCell (drag & drop),
                     MemberAssign (who's on it — day, dish, or grocery line),
                     RecipePickerDialog
    utils/           prefs.js (the ten questions), aisles.js (display names),
                     gradient.js (the colour a photo-less recipe gets)
    views/           RecipesView (list + detail), PlannerView, EventDetailView,
                     EventDayView (one day, on its own page),
                     GroceriesView, GroceryListView (works signed out),
                     ProfileView, UserProfileView, LoginView, JoinView
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

Accounts have no image upload (recipes do — see *Photos*). An account stores a
single number — `avatar_seed` —
and `UserAvatar.vue` turns it into a DiceBear *thumbs* avatar as inline SVG.
An avatar therefore costs four bytes in the database, renders identically on the
web and in the APK, needs no upload endpoint or file storage, and works offline
because nothing is fetched at runtime. "Changer d'avatar" just rolls a new
number.

The style definition (`@dicebear/styles/thumbs.json`, 12 KB) is parsed once at
module load rather than per component.

---

## Photos

A recipe can carry one photo, uploaded by whoever owns it. `POST
/recipes/{id}/image` takes a multipart file, and `images.py` turns it into two
JPEGs before anything is stored: a full size capped at 1600px for the detail
page, and a 480px thumbnail for the cards, where a single screen is a dozen
images at once. Uploads are capped at 10 MB, EXIF rotation is applied (phones
store the sensor's frame plus a flag), and transparency is flattened onto white
rather than onto JPEG's black.

Both live in RustFS — S3-compatible, so the generic `minio` client talks to it
unchanged — and the bucket is public-read, because the browser shows the URLs in
plain `<img>` tags with no per-request auth available to it. Replacing or
deleting a photo deletes the objects it replaced, so re-cropping the same dish
five times does not leave five photos behind.

**A recipe with no photo is not a broken photo.** It gets a light two-stop
gradient, its hue derived from the recipe's own id (`utils/gradient.js`), so it
looks deliberate, renders instantly, needs no network, and never changes between
visits or devices. The same hue, saturated, is the stripe on that recipe's line
in the planner.

Photos replaced an earlier experiment where both the recipe text and its
picture were generated. They were removed on purpose: a generated recipe is
somebody else's cooking, and a generated photo is of a dish nobody made.

---

## The planner

An event has dates and an expected headcount. Its plan is a document keyed by
the event id, nested day → part of day (`matin`, `midi`, `soir`), and every
member may write to it — the point of planning a weekend together is that
everyone can say what they are cooking on Saturday night.

Each part of a day holds three things: whether there is *nothing to cook* (a
decision, and distinct from an undecided slot), how many people will be there
(`null` means "whatever the event expects", so correcting the event's number
fixes every slot nobody has overridden), and the recipes planned for it with
the number of portions each needs and, per dish, who is cooking it.

**A day is its own page** (`/planner/{id}/{day}`), not a dialog per part of the
day — most of the actual planning happens there, it holds more than a dialog
can without scrolling on a phone, and being a real route means it survives a
reload and Back leaves it, including Android's inside the APK. Everything on
it saves as it changes rather than behind one "Enregistrer": the page is
shared by every member live, and a draft nobody else can see is the wrong
model for a kitchen table.

**Two separate kinds of responsibility.** A day carries a roster —
`day_cooks`, `plans.day_cooks[day]` — for whoever is generally on duty
(shopping, cooking, tidying up); each planned dish separately carries its own
`cooks`, for whoever is actually making *that* one. Written the same way as a
slot: one AQL UPSERT recomputing the sub-document from `OLD`, so two members
setting Saturday's and Sunday's rosters at once never clobber each other.

- **Writes are per slot, not per plan.** `db.set_slot` recomputes `days` from
  `OLD` inside one AQL statement rather than merging: a merge would silently
  keep an override the user has just cleared, and replacing the whole document
  would drop whatever someone else changed while the dialog was open.
- **A planned meal remembers its own name and owner.** The plan has to stay
  readable after the recipe behind it is renamed or deleted, and after the
  member who owns it has left the event.
- **Drag & drop is Sortable.js**, one group across every slot, so a meal moves
  from Saturday lunch to Sunday dinner directly. Ctrl-click builds a selection
  and dragging any member of it moves the whole set. On a touch screen a press
  and hold starts the drag (`delayOnTouchOnly`), so scrolling the calendar with
  a finger still scrolls it.
- **The DOM is put back after every drop.** Sortable moves the node itself;
  the plan the server returns is the source of truth, and letting both stand
  would show the meal in two slots until the next render.

The calendar is a real month grid on a desktop, with the days around the event
greyed and inert, and a list of day cards on a phone, where seven columns of
meals would be unreadable.

---

## The shopping list

`groceries.py` folds an event's whole plan into one list in two passes.

**The first pass is mechanical and always runs.** Every planned recipe is
scaled by the portions it is planned for, units are converted to one base per
family (kg → g, cl/dl/l → ml), and names are compared with case, accents and
plural endings folded away — "Oignon" and "oignons" become one line before
anything clever happens. Lines are still kept apart by name *and* unit:
merging "200 g de tomates" with "3 tomates" needs a density table per
ingredient to be anything but wrong, and two honest lines beat one invented
one. Each line's key is a hash of its comparison form, which is what lets a
regenerated list keep the ticks and assignments already on it. Aisles come
from the same keyword table the recipe form uses, in the order you walk a
supermarket.

**The second pass is the model's**, and catches what the table cannot: "blancs
de poulet" beside "poulet", "huile d'olive vierge extra" beside "huile
d'olive". It only ever decides which lines are the same product and what to
call the result (`ai.fuse_ingredients`); the arithmetic — including a group
that spans two unit families, split back into one line per family — stays in
`groceries.apply_fusion`. A deterministic veto sits in front of whatever the
model answers: two lines differing by a word from a fixed list (`vert`,
`rouge`, `complet`, `liquide`, `épais`, `cerise`, `coco`, `rapé`… — see
`_DISTINGUISHING` in `groceries.py`) are never merged, even if the model says
to. This exists because the same question asked twice does not reliably get
the same answer — a model that correctly separates "citron" from "citron
vert" once will sometimes merge them the next time — and an extra line is
untidy where a missing product is a problem at the shop. Optional throughout:
no API key, a refused call, or a mangled answer all fall back to the first
pass's list, which is already correct.

**Assignment is who is fetching what** — separate from the plan's `cooks`,
which is who is *making* a dish. One call (`POST …/grocery-list/assign`)
covers one article, a whole rayon, or everything one recipe needs, since the
page already knows which keys each of those covers; it survives a
regeneration the same way a tick does.

**The list is shared with a link, and the link needs no account.** That is the
whole design constraint: the person holding the trolley is often not the person
who planned the meals, and asking them to sign up first would defeat the point.
The public half of the API can read one list — its items *and* the event's
members, so an assignment has a name and a face to show — and tick its boxes,
and nothing else: not the event itself, not a single recipe, not who is
cooking what, and never an email address. Changing *who is assigned* stays a
members-only action; the shared page renders it read-only. Ticks and
assignments reach everyone looking at the same list live, through the
room-keyed socket described above.

The price estimate is the app's only LLM call, and it is on demand rather than
automatic: it is the one thing that costs money per use, the list is perfectly
usable without it, and the result is stored so reopening the page does not pay
for it again. Lines the model skips simply have no price rather than a zero.

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
  a leaked link cannot currently be revoked without deleting the event. The
  same goes for a shopping list's share code, which is deliberately weaker
  still: no account is needed to read the list or tick its boxes. The worst a
  leaked list allows is a stranger unticking the yoghurts, and it exposes
  nothing about the event or its members.
- **Recipe sharing is all-or-nothing per event.** Joining an event makes your
  whole recipe book readable by its members, with no per-recipe opt-out.
  Leaving closes it again.
- **Web offline is data-only.** Recipes are cached, but the app *shell* is not:
  loading `popote.tomansion.fr` with no connection still fails. Adding
  `vite-plugin-pwa` would fix that for the web. The APK is unaffected, since it
  ships its assets on the device.
- **Last write wins.** Two people editing the same recipe at once — the second
  save overwrites the first. The meal plan is finer-grained: two people editing
  *different* slots never collide, because each write touches only its own slot.
  Two people dragging meals in the same second still race, and the last one
  wins.
- **The price estimate is a guess.** It is a language model's idea of French
  supermarket prices, not a quote, and it is not re-checked when the plan
  changes — regenerating the list clears the price of any line whose quantity
  moved.
- **The ingredient-fusion pass is a convenience, not a guarantee.** The
  deterministic veto (see *The shopping list*) stops it from ever merging two
  products that differ by a known distinguishing word, but that list is not
  exhaustive — a pair it does not know about can still be merged incorrectly,
  and the model can also *fail* to merge two lines that plainly are the same
  thing. Either way the list stays usable: worst case is an extra line, or two
  that could have been one.
- **Responsibility is a courtesy, not an enforcement.** Assigning a day, a
  dish or a grocery line to someone does not stop anyone else from editing it,
  and nothing reminds a member who has taken something on. It is a shared
  to-do list, not a scheduler.
- Node 20.19+/22.12+ is required by Vite 7. Vite 8 needs a newer Node than is
  installed on the current dev machine, which is why it is pinned.
