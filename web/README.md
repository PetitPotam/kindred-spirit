# The Kindred Spirit website

The public site for Pip: who she is, the showcase video, the guides, the roadmap, how to contribute, credits and the
legal pages. Hosted on Firebase Hosting (project `kindred-spirit-pip`), deployed from GitHub Actions.

It's plain HTML, one stylesheet and two small scripts, built by `build.mjs` with Node's standard library: **no
dependencies** to install, update or audit. System fonts only, nothing loaded from another site until a visitor asks
for it (the video) or accepts analytics.

## Working on it

```bash
cd web
node build.mjs        # src/ -> dist/
node check.mjs        # links, #anchors, ids, headings, alt text, the CSP rules, no personal data
node serve.mjs        # http://127.0.0.1:5050, with clean URLs and the headers from firebase.json
```

Needs Node 22 or newer. CI also validates the HTML (`html-validate`) and runs Lighthouse.

| Path | What |
|---|---|
| `src/pages/` | one HTML fragment per page, with a small `---` header (title, description, layout); `guides/x.html` is served as `/guides/x` |
| `src/layout.html` | the page around every page: header, footer, cookie settings link, the Mojang notice |
| `src/assets/` | `site.css`, `consent.js` (cookie choice and Google Analytics), `video.js` (the showcase player), `download.js` (the Download page asks GitHub for the newest Setup, only when a button is pressed) |
| `src/media/`, `src/img/` | stills from the showcase, its poster and captions, Pip's icon |
| `site.config.json` | the site address, repository, measurement ID, the video's address, the guides' order, the legal pages' date |
| `firebase.json`, `.firebaserc` | Hosting (clean URLs, security headers, caching) and the rules files below |
| `database.rules.json`, `storage.rules`, `firestore.rules` | deny everything (Storage: anyone may read single files under `public/`, nothing else) |
| `BACKEND.md` | design note: what Firebase could host later, and how to keep it safe |

`{{name}}` in a page is replaced from `site.config.json` (`{{repo}}`, `{{blob}}` for a file on main, `{{issues}}`,
`{{video.src}}`...). An unknown name stops the build. Write links from the site root (`/guides/install`).

**The Content-Security-Policy** in `firebase.json` blocks inline scripts, `style="..."` and anything from another
site that isn't listed. `check.mjs` fails on the first two; when you add a new outside service, add it to the policy
and to the privacy and cookie pages.

**Legal pages** (`src/pages/legal/`) are drafts written for a lawyer to review before the site goes public. When one
changes, update `legalUpdated` in `site.config.json`.

## The showcase video

The page shows a poster and loads the video only when the visitor presses play. `site.config.json` → `video`:

- `"provider": "file"` with `src`: any MP4 address. The default is Cloud Storage for Firebase,
  `public/kindred-spirit-showcase-720p.mp4` in the project's bucket (`storage.rules` lets anyone read files in
  `public/` and nothing else).
- `"provider": "youtube"` with `youtubeId`: a youtube-nocookie.com player, loaded only on click. If you switch to
  this, update the privacy and cookie pages: YouTube sets its own cookies once the player loads.

Captions are in `src/media/showcase.en.vtt` (transcribed locally with whisper.cpp, corrected by hand).

## Deploying

CI (`.github/workflows/website.yml`) deploys a **preview** for each pull request that touches `web/` (a temporary
address posted on the pull request, kept 7 days) and the **live** site on every push to main that touches `web/`.
Both need one secret; without it, the checks run and the deploy steps are skipped.

### The deploy secret (once)

A service account that can deploy Hosting and nothing else:

1. Google Cloud console → **IAM & Admin → Service Accounts**, project `kindred-spirit-pip` → **Create service
   account**. Name: `github-hosting-deploy`.
2. Roles: **Firebase Hosting Admin** (`roles/firebasehosting.admin`), **API Keys Viewer**
   (`roles/serviceusage.apiKeysViewer`) and **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`:
   the deploy tool first checks that the Hosting API is on; this role can see services, not turn them on or off).
   Nothing else. With gcloud (a new account can take a minute before roles can be granted):
   ```bash
   SA=github-hosting-deploy@kindred-spirit-pip.iam.gserviceaccount.com
   gcloud iam service-accounts create github-hosting-deploy --project kindred-spirit-pip
   for role in firebasehosting.admin serviceusage.apiKeysViewer serviceusage.serviceUsageConsumer; do
     gcloud projects add-iam-policy-binding kindred-spirit-pip --member "serviceAccount:$SA" --role "roles/$role" --condition=None
   done
   ```
3. Open the account → **Keys → Add key → Create new key → JSON**. A file downloads: it is a password, keep it out of
   the repository.
4. GitHub → the repository → **Settings → Secrets and variables → Actions → New repository secret**. Name:
   `FIREBASE_SERVICE_ACCOUNT_KINDRED_SPIRIT_PIP`; value: the whole JSON file's content.
5. Delete the downloaded file from your computer.

If the key ever leaks: delete it on the service account's Keys tab, then make a new one.

### By hand

```bash
cd web
firebase deploy --only hosting               # the site (builds and checks it first)
firebase deploy --only database,storage      # the rules, after Storage is set up
```
