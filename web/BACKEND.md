# Design note: what Firebase could host later

**Status: design only. Nothing here is built or deployed.** Today the Firebase project `kindred-spirit-pip` serves
the static website and nothing else. This note records how it could later host parts of Pip's backend, what must stay
true when it does, and the rules that are already in place so nothing is open by accident.

Principles that don't change: everything a player needs runs on their own computer; a hosted part is optional and
the local one keeps working; nothing a player says or remembers is stored on a shared server without them choosing
it; the project never holds players' AI keys.

## What's in place now

| Product | State | Rules |
|---|---|---|
| Hosting | the website (`web/`) | security headers and a strict Content-Security-Policy in `firebase.json` |
| Realtime Database | created (europe-west1), unused | `database.rules.json`: deny all reads and writes (checked live: anonymous reads are refused, and the deployed rules are `false`/`false`) |
| Cloud Storage | only for the showcase video, if chosen | `storage.rules`: anyone may *get* a single file under `public/`; listing, other paths and every write are denied |
| Cloud Firestore | not enabled | `firestore.rules`: deny all, ready for the day it's turned on |
| Analytics | GA4 on the website, only after consent | see `src/assets/consent.js` and the privacy page |

Rules only govern the client SDKs (browsers, apps). Server code with the Admin SDK or a service account bypasses
them, so server access is controlled with IAM (least-privilege service accounts) instead.

## 1. The knowledge base (`services/knowledge`)

Today each player builds their own knowledge base (`kb.py crawl ...`): about 1,200 pages from minecraft.wiki plus
the game's recipe data from minecraft-data, a ~50 MB SQLite file with full-text and vector search, kept on their
computer. The gateway searches it locally (~90 ms) and Pip can learn missing pages while you play.

**Why it's built locally, and not shipped or served by the project:**

- **The Minecraft Wiki's text is CC BY-NC-SA 3.0.** *Non-commercial*: hosting it is fine only while the hosting and
  the project around it stay non-commercial; anything paid, ad-supported or sold that serves the text would break the
  licence. *Attribution*: every passage must keep its page, its authors ("Minecraft Wiki contributors"), the licence
  and its link, and say if it was changed (the knowledge base already stores all of this with each chunk).
  *Share-alike*: a hosted copy, and anything adapted from it (the cleaned and chunked passages are an adaptation),
  must be offered under the same licence, which is incompatible with the project's AGPL code: the data and the code
  have to stay separate works, each with its own licence.
- **minecraft-data** is MIT, but the game data in it is Mojang's; the project asks each player's OK before using it.
- Each player downloading at one request per second, with robots.txt respected, is a good guest of the wiki. A
  central crawler would be one more heavy client, and must follow the wiki operator's (Weird Gloop) rules for bots.
- Local search works offline and leaks nothing about what a player asks.

**If it's hosted one day**, the safest shape is a **read-only, prebuilt download**, not a query API:

- A scheduled job (below) builds the same SQLite file from the same code, with the licence notice, an attribution
  page and a list of changes inside it, and publishes it as a versioned file in Cloud Storage (`public/kb/...`) or as
  a GitHub release asset.
- `kb.py` gets an `import` command that downloads it and checks its hash; players can still build their own.
- The download is free of charge and ad-free, forever, which keeps it non-commercial. That needs to be written down
  as a project rule before the first file is published, and checked with whoever reviews the legal pages.
- A query API (the gateway in the cloud answering searches) would see every player's questions and costs money per
  request; it isn't needed while the file is small.

## 2. Refreshing it automatically

A scheduled job, nothing that runs per player:

- **Cloud Run job** (a container with Python and `services/knowledge`) started by **Cloud Scheduler**, weekly:
  `kb.py refresh` against a cached copy (only pages that changed are fetched), `kb.py eval` must not get worse,
  then the new file is uploaded with its hash and the old one kept for rollback. A Cloud Run job suits a crawl
  that takes minutes better than a Cloud Function (time limits, no long-running process).
- It runs as its own service account with write access to `kb/` in the bucket only.
- It identifies itself to the wiki with a descriptive user agent and a project contact URL, keeps the one-request-
  per-second pace, and stops on errors instead of retrying hard.
- Alternative with no Google Cloud cost: a scheduled GitHub Actions workflow that builds the file and attaches it to
  a release. Same rules apply.

## 3. Backend parts: the gateway, and Firestore

The gateway (`services/kindred_gateway.py`) can already run on another machine for **remote memory** (one memory for
several computers, or AI keys off the gaming PC), protected by an access key and HTTPS (docs/GATEWAY.md). A hosted
version would be **one per player, run by that player**, never a shared service holding everyone's memories:

- **Cloud Run** service from the gateway's container, in the player's own Google Cloud project, with
  `KINDRED_GATEWAY_KEY` from Secret Manager, min instances 0 (no cost when idle), HTTPS by default. Its memory store
  would need a real database instead of a local SQLite file: **Firestore** (one document per memory, vectors in
  Firestore's vector search) or Cloud SQL.
- If the project ever offers anything shared (say, players sharing blueprints or skins), that is where
  **Firestore** fits: public read of approved items only, writes only through a server function that checks
  content, never directly from clients. It would need sign-in (Firebase Auth), moderation, a privacy policy update
  and a data protection review before it opens.

## 4. App Check

When anything other than static files is served (a function, Firestore, a download that costs money), turn on
**App Check** for it, with reCAPTCHA Enterprise for the website, and **enforce** it after watching the metrics for
a week. It makes it harder for scripts to call the backend directly. It isn't authentication: it never replaces
security rules or IAM. reCAPTCHA itself processes visitor data, so the privacy and cookie pages must say so when it
is added.

## 5. The web API key

The site doesn't use the Firebase web SDK, so it doesn't load the API key at all. The key is in the Firebase web app's
config (it's public by design: it identifies the project, it doesn't grant access). Restrict it anyway, now:

- Google Cloud console → **APIs & Services → Credentials** → the "Browser key (auto created by Firebase)" →
  **Application restrictions: Websites**, allowed: `kindred-spirit-pip.web.app/*`,
  `kindred-spirit-pip.firebaseapp.com/*`, and a custom domain if one is added; for local testing add
  `localhost:5050/*` only while testing.
- **API restrictions:** only the APIs a web client needs (when one is added: Firebase Installations, Firebase
  Management for Analytics, Identity Toolkit if Auth is used, the App Check and Firestore APIs if those are used).
- Never give this key extra permissions; server code uses service accounts, not API keys.

## 6. Security rules: deny by default

- Every product starts with the deny-all rules in this folder. A rule opens **one path for one purpose**, with a
  comment saying why, and with **tests in the Emulator Suite** (`@firebase/rules-unit-testing`) run in CI before
  the rules are deployed.
- Never `allow read, write: if true`, never test-mode rules with a date, never `request.auth != null` alone
  (anyone can sign in): check the user's own path (`request.auth.uid == userId`) and validate the data's shape and
  size.
- Rules are deployed from the repository only (`firebase deploy --only database,storage,firestore`), never edited in
  the console, so what's live is what's reviewed. The website workflow deploys Hosting only; rules stay a manual,
  reviewed step until they have tests.
- Budgets and alerts in Google Cloud Billing before turning on anything that can cost money, and the project's
  owner accounts with two-factor authentication.

## 7. Deploying with less secret material

The website workflow authenticates with a service-account key stored as a GitHub secret (simple, and what the
Firebase deploy action expects). Later, **Workload Identity Federation** (`google-github-actions/auth`) can replace
the key with short-lived credentials tied to this repository's workflow, so no long-lived key exists at all.
