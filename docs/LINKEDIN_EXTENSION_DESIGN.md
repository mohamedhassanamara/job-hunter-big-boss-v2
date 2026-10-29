# LinkedIn capture extension: design proposal

Status: **Phase 0 spike complete; revised for approval. Nothing implemented, nothing committed.** Phase 1 does not start until you approve this version.
Replaces: the bookmarklet + `/import` window (Phase 10 capture).
Scope: a Manifest V3 Chrome extension that captures **job postings and people profiles** on click, and feeds the persona-based outreach flow.

---

## 0. Summary of decisions

| Topic | Recommendation |
|---|---|
| Trigger | One explicit click (or one keyboard shortcut) per page. No observers, timers, scrolling, clicking or requests to LinkedIn. |
| Transport | Content script reads the DOM on click → service worker → `fetch` to `localhost:8000`. The content script never talks to the backend itself. |
| Auth | A revocable local token created in Settings → LinkedIn, pasted once into the extension options, sent as `Authorization: Bearer`. Valid only for new `/api/ext/*` routes. Plus a CORS allow-list for the exact extension ID. |
| Primary UI | Injected floating pill (closed Shadow DOM), bottom-right, on every linkedin.com page. A shortcut (`Alt+Shift+S`) does the same thing. |
| Popup | Keep it tiny: status, pause, open the app. Pairing lives in an options page. Capture history lives in the app, not the extension. |
| Persona | **Role-based: Engineering Manager/Tech Lead, HR/Recruiter, Peer IC.** `is_alum` is a separate flag that feeds the message template and never overrides the persona. The server suggests, the panel shows it, one click overrides. Saving never waits for the tag. |
| Search links | **Classic direct links are confirmed dead** (§9.1). Drop the URL generator and the geoId settings; keep "Today's searches" as a checklist of copyable AI-search prompts (§6). |
| Capture strategy | **No CSS class is ever read** (LinkedIn's classes are hashed and unstable). Thin extractor in the browser, interpretation on the server, anchored on tab title, URL, exact heading text, link shapes and document-order regions (§2.8). |
| Migration | Remove bookmarklet, `ImportPage` handoff and the old `capture.ts` at cutover. Reuse `validate`, `import_job`, `add_person`, `detect_group`, ingest/dedupe/scoring unchanged. Add one table (`linkedin_profile`) and one enum value (`peer`). |

---

## 1. Current state (what exists, what must not regress)

### 1.1 Flow today

```
LinkedIn tab ──click bookmark──▶ capturePage(document) ──▶ window.open(/import#c=<json>)
                                                         └─ postMessage (2nd channel)
/import (ImportPage) ──▶ POST /linkedin/capture  (preview: validate + existing)
                    ──▶ POST /linkedin/import   (validate → import_job → ingest → score)
                    └─▶ POST /linkedin/paste    (fallback: pasted text → from_paste)
```

Backend: `services/linkedin.py` (`validate`, `from_paste`, `existing`, `import_job`, `add_person`, `detect_group`, `search_url`, `search_links`), `api/linkedin.py`, `models/linkedin.py` (`LinkedInOutreach`, `LinkedInLead`, `LinkedInLinkOpen`), `models/job.py` (`linkedin_job_id`, `capture` JSON).

### 1.2 What `capture.ts` actually does

> **Superseded by §2.8 for selectors.** Phase 0 showed every class-based selector below is dead on the current layout (§9.2). What is kept from this design is the *principle* (an ordered chain per field, first hit wins, provenance recorded, text-based anchors, no `innerHTML`), not the class lists.

1. **Per-field strategy chain, first non-empty wins** (`set()` ignores a field once filled), and **the winning strategy is recorded** in `sources[field]` (`json-ld | page | meta | url | you | missing`).
2. Order: JSON-LD `JobPosting` → layout selectors → headings → `og:title` / `<title>` → URL (job id).
3. Layout selectors are **lists of known variants** (`job-details-jobs-unified-top-card__*`, `jobs-unified-top-card__*`, `top-card-layout__*`, `#job-details`, `.show-more-less-html__markup`, …). `first()` skips selectors that throw or match empty elements.
4. **Text-based fallbacks that do not depend on class names:** description = section under an "About the job" heading in 5 languages; company = any `a[href*="/company/"]` in the card; poster = "Meet the hiring team" heading in 4 languages + `a[href*="/in/"]`.
5. **Trusted Types safe:** no `innerHTML`; HTML is stripped with regexes.
6. Downstream: `validate` refuses empty title/company/description, warns on short descriptions (< 200) and on sign-in walls (`_WALL`), and `ImportPage` shows each field with its provenance badge.

### 1.3 Gaps worth fixing in the rewrite (the `description_level` one is confirmed, §9.5)

- **A `meta` description is a snippet** (`og:description` is truncated), but it is accepted if > 200 chars, so a snippet can pass as a full listing. Treat `sources.description == "meta"` as `DescriptionLevel.snippet` and warn. (Verify how `import_job` sets `description_level` today.)
- The bookmarklet had to be **self-contained** (`capturePage.toString()`). That constraint disappears: split into modules, keep the in-browser extractor tiny and test the interpretation on the server against recorded payloads (§2.8.4). Today there are **no tests for `capture.ts` at all**; selector rot is invisible until you click.
- `workplace` is a regex over the whole card text (first match wins) and `h1` is a last-resort title: both can pick the wrong element on a new layout.
- The review step (`ImportPage`) is a safety net the extension flow must keep in some form (§2.5).

**Rule for the rewrite:** keep the chain, the provenance and the text anchors; drop every class selector (none is a fallback, §2.8); add recorded-payload tests on the server and a per-capture anchor report.

---

## 2. Extension architecture

### 2.1 Manifest (MV3), minimal permissions

```jsonc
{
  "manifest_version": 3,
  "name": "Job Hunter capture",
  "key": "<fixed public key so the extension ID is stable when unpacked>",
  "permissions": ["storage"],                    // no "tabs": the host permission already gives URL change events (built and checked in 2a)
  "host_permissions": ["https://www.linkedin.com/*"],   // nothing else
  "content_scripts": [{ "matches": ["https://www.linkedin.com/*"], "js": ["content.js"], "run_at": "document_idle" }],
  "background": { "service_worker": "background.js" },
  "action": { "default_popup": "popup.html" },
  "options_page": "options.html",
  "commands": { "capture": { "suggested_key": { "default": "Alt+Shift+S" }, "description": "Capture this page" } }
  // no web_accessible_resources (see 2.6)
}
```

`localhost` is **not** in `host_permissions`: a service-worker `fetch` to an un-permitted origin is a normal CORS request, so the backend allow-lists the extension origin instead (2.4). This keeps "host permission scoped to linkedin.com" literally true. (Q4, confirmed by §9.7.)

### 2.2 Components

| Part | Job | May do | Must not do |
|---|---|---|---|
| **Content script** | Mounts the panel, detects page type from the URL, reads the DOM **only inside the click handler**, sends the payload to the worker | Read DOM once per click | `fetch`/XHR anywhere, `click()`, `scroll*`, `dispatchEvent`, `MutationObserver`/`setInterval` that reads the page, expanding "See more" |
| **Service worker** | Holds the token, calls the backend, answers status lookups, relays the shortcut | `fetch` to the backend only | Any request to linkedin.com |
| **Panel** (inside content script, Shadow DOM) | The floating control (§3) | | |
| **Options page** | Backend URL + token pairing | | |
| **Popup** | Status, pause, open app | | |

Shared code (field strategies, types) lives in `extension/src/shared/`; types mirror `app/schemas` the same way `frontend/src/lib/types.ts` does.

### 2.3 Page-type detection without touching the DOM

The panel needs to know "job / profile / other" to label the button. That comes from **the URL only**: `/jobs/view/<id>`, `/jobs/search*?currentJobId=<id>` and the AI-search equivalents → `job`; `/in/<slug>` → `profile`. LinkedIn is a single-page app, so URL changes arrive via `chrome.tabs.onUpdated` (worker → content script message). No DOM observation, no polling.

The only automatic network call is a **status lookup keyed by the URL id** ("already saved as job #123 / person #45"), to the local backend, never to LinkedIn. Optional: a setting turns it off.

### 2.4 Talking to the backend

- Content script → `chrome.runtime.sendMessage` → worker → `fetch('http://localhost:8000/api/ext/...')`.
- **CORS** (`app/main.py`): today `allow_origins` is only the Vite origins. Add `allow_origin_regex` built from a new setting `extension_ids` (exact IDs, no wildcard): `^chrome-extension://(id1|id2)$`. `Authorization` triggers a preflight, which `allow_headers=["*"]` already covers.
- **New router `api/ext.py`**, mounted at `/api/ext`, with a dependency `require_extension_token`:
  - `GET  /ext/ping`: token valid, app version, today's counts (jobs, people, requests sent).
  - `GET  /ext/status?job_id=` / `?profile=`: already saved? (URL-derived keys only).
  - `POST /ext/job`: capture → `validate` → `import_job` in one call. Returns `{job_id, created, existing, warnings, missing, scoring, fit}`.
  - `POST /ext/person`: profile capture → persona suggestion → contact + `linkedin_profile` + attach (§5). Returns the saved person, suggested persona and reasons, and the job it attached to.
  - `PATCH /ext/person/{id}`: change persona / attach to another job (undo target).
  - `POST /ext/paste`: the paste fallback (reuses `from_paste`).
- Ext routes **always use the real workspace**: an `X-Workspace: demo` header is rejected on them (the tour sandbox never involves the extension).

### 2.5 Auth: local token

1. Settings → LinkedIn → **Create extension token** → `secrets.token_urlsafe(32)`, shown **once**; only its SHA-256 is stored (`app_setting.extension_auth`).
2. The user pastes it into the extension options page. Stored in `chrome.storage.local` (not `sync`).
3. Every `/api/ext/*` call carries `Authorization: Bearer <token>`; compared with `hmac.compare_digest`. Rotate/revoke from Settings.
4. The token grants **only** `/api/ext/*`. It cannot reach email, queues, or settings.

Why this is worth doing even on localhost: the rest of the API has no auth, and any web page you visit can attempt requests to `localhost:8000`. CORS blocks reading responses, but the token means the new *write* endpoints cannot be driven by a random page at all.

Dev note: the backend must stay bound to `127.0.0.1` (verify the `make dev` uvicorn host).

### 2.6 Review step without a separate window

`ImportPage` showed every field + provenance before saving. Replacement, in the panel:

- **All required fields found** → save immediately; the panel shows `Saved · Data Engineer @ Acme · scoring…` with an **Undo** (undo toast, per DESIGN rules) and a compact line of warnings (short description, from-meta, wall detected).
- **A required field missing** (`title | company | description`) → **nothing is saved**. The panel expands with editable inputs for the missing fields, plus a "Paste the listing instead" box (`/ext/paste`). Same rule as today: never silently saved empty.
- Every saved job links to its app page (`/jobs/<id>`), where the stored `capture` provenance is visible.

### 2.7 Detectability and safety posture

- Capture is a **single user-initiated read of the page you are looking at**: same principle as the bookmarklet. It is *not* automation, but LinkedIn's terms are strict about extensions and it is reported to probe for them. Mitigations: **no `web_accessible_resources`** (nothing for a page to probe), closed Shadow DOM so LinkedIn's CSS/JS cannot see or break the panel, zero requests to linkedin.com, no DOM mutation outside the panel host.
- **Guard test** (parallel to `test_the_backend_never_requests_linkedin`): a build-time check on the extension source that fails on `setInterval`, `setTimeout` polling, `MutationObserver`, `.click(`, `scrollTo/scrollBy/scrollIntoView`, `dispatchEvent`, and any `fetch`/`XMLHttpRequest` in `content/`. The backend test stays as is.
- **Lazy sections:** we never scroll for you. Profile regions that are not rendered are reported as missing in the panel's anchor row (§2.8.5), and the selection/paste fallbacks (§2.8.2) cover them.
- Chromium only, **current stable Chrome or Edge, no version pin** (unpacked, no web-store listing). `make extension` builds to `extension/dist`; load it from `chrome://extensions`.

---

### 2.8 Capture strategy (class-free)

**Why:** Phase 0 confirmed that LinkedIn's class names are short hashed atomic utility classes (`ajrlr8`, `ajrayf`, …), generated by its build and not stable across deploys. So **no class name is read anywhere, not even as a fallback**. This also drops `data-*` and `aria-*` attributes as load-bearing anchors (not observed to be stable; they may be used opportunistically and never alone).

**Allowed anchors, strongest first:** (1) the **tab title** (`document.title`); (2) the **URL**; (3) **exact label text** of headings (normalised, §2.8.1); (4) **tag semantics**: `h2` sections, `h3` sub-labels, `li` items, `a[href]` path shapes (`/company/<id>/`, `/in/<id>/`, `/school/<id>/`, `/jobs/view/<id>/`); (5) **document-order regions**: the nodes between one anchor and the next; (6) **cross-checks** between two independent anchors (a field that two anchors agree on is high confidence; a disagreement is a warning, not a silent pick).

**Architecture: thin extractor, smart server.** The content script only builds a small, redacted-by-construction payload from those anchors (title, URL, region lines, a link inventory, the text under known headings). The **server parses it** (Python, `services/linkedin_page.py`, unit-tested with recorded payloads, reusing `contact_paste` helpers). When LinkedIn changes, the fix is a parser change plus a test: no extension rebuild or reload. Raw lines are never stored, only parsed fields and their provenance.

#### 2.8.1 Normalisation and labels
`norm(text)`: Unicode NFKC, lower-case, accents stripped, whitespace collapsed, trailing punctuation removed, and an exact doubled string collapsed to one (defensive: LinkedIn is known to render a visible and a screen-reader copy of some labels; **not observed**, cheap to tolerate). A heading matches only when `norm(heading) == norm(label)` (exact, never "contains").

Labels are keyed by **LinkedIn UI language** (one language per user, a setting; English is the only one verified). Others come from `capture.ts` today and are best effort until seen:

| Label | en (verified for jobs) | fr | es | it | de |
|---|---|---|---|---|---|
| Job description | About the job | À propos de l'offre d'emploi | Acerca del empleo | Informazioni sull'offerta | Über den Job |
| Hiring team | Meet the hiring team | Rencontrez l'équipe de recrutement | Conoce al equipo de contratación | (add when seen) | (add when seen) |
| Profile: About | About | À propos | Acerca de | Informazioni | Info |
| Profile: Experience | Experience | Expérience | Experiencia | Esperienza | Berufserfahrung |
| Profile: Education | Education | Formation | Educación | Formazione | Ausbildung |
| Profile: Skills | Skills | Compétences | Aptitudes | Competenze | Kenntnisse |
| Contact link | Contact info | Coordonnées | Información de contacto | (add when seen) | (add when seen) |

Arabic and Portuguese are not included (no evidence of the strings): add them when your UI language needs them (Q15).

#### 2.8.2 Job: field by field (priority order, first agreed hit wins)

**Pane scoping (needed because results pages list many jobs with many `/company/` links):** the *detail pane* is the **smallest ancestor of the "About the job" heading that also contains a `/company/` link whose normalised text equals the company parsed from the tab title**. Every other job anchor is read inside that pane only.

| Field | Anchors, in order | Cross-check / notes |
|---|---|---|
| `job_id` | URL `/jobs/view/<id>`, then `currentJobId=<id>`, then `jobId=<id>` (`currentJobId` confirmed on AI-search URLs) | Canonical URL `https://www.linkedin.com/jobs/view/<id>/` |
| `title` | 1. **Tab title**: drop a leading `(<n>) `, drop the trailing ` \| LinkedIn`, **split on the last ` \| `**: left part is the title (it may itself contain `\|`). 2. JSON-LD `JobPosting.title` (only on a logged-out public page; opportunistic). 3. an `h1` in the pane, if one exists (none on the probed layout) | Warn if the tab title is stale: the title text should also appear in the pane's header lines |
| `company` | 1. Tab title, right part. 2. Text of the `/company/` link that matches it. 3. First non-empty `/company/` link text in the pane's header region | Agreement of 1 and 2 = high confidence |
| `company_url` | `href` of the matching `/company/` link, canonicalised to `/company/<slug>/` | |
| `description` | 1. The text of the region **from the "About the job" heading to the next `h2`** in document order (the `h2`/`h3` structure is confirmed), converted to text with newlines at block boundaries and `• ` for `li` (no `innerHTML`, Trusted Types safe). 2. JSON-LD `description` (public page). Nothing else: an `og:description` or a short text is **`DescriptionLevel.snippet`** (§9.5) | Warn under 1,500 chars. We never click "See more": if the text ends on a truncation marker, say so |
| `location` | 1. Header region lines (everything in the pane before the "About the job" heading): the first `·`-separated segment that is not the company or title. 2. Server: `country_from_text` on the header lines. Not a required field | **Not observed in the probes**: unconfirmed, Phase 2 verifies |
| `workplace` | Header region lines, regex `Remote \| Hybrid \| On-site` (+ the UI language's words) | Unconfirmed, same note |
| `poster` | Region from the **"Meet the hiring team"** heading to the next `h2`: the first `a[href*="/in/"]` is the person (`href` canonicalised to `/in/<id>/`, note the id can be an opaque id, not a vanity slug); name = the link's first text line (a doubled string collapsed); title = the first following line that is not a degree badge (`1st/2nd/3rd`), `Job poster`, `Message` or `·` | Saved as the hiring-team person exactly as today (`add_person(hiring_team=True)`), same click |

Required to save: `title`, `company`, `description` (unchanged). A missing required field opens the inline form in the panel (§2.6).

#### 2.8.3 Person (profile page): redesigned from first principles
The probes never produced a usable top card, `h1`, or section labels on any profile (§9.4), so the strategy uses **no top-card selector, no `h1`, and no `h2` assumption**. It reads `main.innerText` (layout-aware lines) and a **link inventory**, and slices by exact label lines.

- **Regions:** `top` = the lines before the first line equal to a section label (About, Experience, Education, Skills, Activity, Featured, Highlights: §2.8.1); then one region per label line to the next label line. Section items = `li` elements inside the region when present (tag rule), otherwise blank-line/date-line grouping.
- **Link inventory:** every `a[href]` in `main` whose path matches `/company/`, `/school/`, `/in/`, with its text and **which region it falls in** (by document order).

| Field | Anchors, in order | Cross-check / notes |
|---|---|---|
| `profile_url` | `location.pathname` `/in/<slug>/` | The page's own URL is authoritative |
| `name` | 1. Tab title: drop `(<n>) `, cut at ` \| LinkedIn` (if the rest contains ` - `, keep the left part and warn). 2. First `top` line | Title name must equal a `top` line exactly, else warn |
| `connection_degree` | A `top` line matching `^·?\s*(1st\|2nd\|3rd\+?)$` (fr: 1er/2e/3e) | None if absent |
| `headline` | First `top` line after the name and degree lines that is not a UI label (Message, Connect, Follow, More, Contact info, …) | Heuristic: server-side, unit-tested |
| `location` | The `top` line just before the "Contact info" label line | Missing if the label is missing |
| `current_company` (+ `company_linkedin_url`) | 1. First `/company/` link in `top` (company chip). 2. Company line of the first Experience item (strip `· Full-time` etc.). 3. Headline `at X` / `@ X` (weak, flagged) | 1 and 2 agree = high confidence |
| `current_title` | 1. Title line of the first Experience item. 2. Headline text before ` at ` / `@` / ` \| ` | |
| `experience` (first 3) | Each Experience `li`: title, company, dates (a year `19xx/20xx`, `Present`/`Présent`), location line | Grouped roles under one company: take the `li`s that carry a date range |
| `education` | Each Education `li`: school = text of its `/school/` link (else first line), degree line, years | |
| `is_alum` | The user's school keyword(s) (from the pool, `linkedin_track.school`) matched, accent/case-insensitive, against **any** `/school/` link text or slug, Education lines, or headline/About | Works even when the Education section is not rendered, via the `top` school chip |
| `about` | Lines under the About label, up to 600 chars; strip "see more" | |
| `mutual connections` (optional) | A `top` line containing "mutual connection(s)"; names from `/in/` links in that line | Low value, skipped if absent |
| `badges` (optional) | `top` lines: "Open to work", "Hiring" | |

Required to save a person: `name` and `profile_url`. Everything else is optional and reported in the anchor row.

**These profile anchors are hypotheses.** They follow from the confirmed facts (the tab title pattern, exact heading text, link shapes, `h2`/`h3` on the job pane) but the profile layout itself was **never read successfully** in Phase 0. They must be validated before persona logic depends on them (Phase 2a gate, §8).

**Fallback ladder for people (each reuses the same server parser):**
1. **Auto:** the extraction above.
2. **Selection:** if you have text selected on the page, the click sends `getSelection()` text instead. You select the header block; no DOM anchor is involved.
3. **Paste:** the app's existing paste box (`contact_paste.parse`, `add_person`), extended to LinkedIn profile text. This exists today and works regardless of LinkedIn's markup.

#### 2.8.4 Tests and self-diagnosis (no new dependency)
- **Server parser tests** (pytest, offline): recorded **payloads**, not HTML. Job payloads are redacted from your own captures; person payloads are **synthetic only** (third-party data). Each anchor has a hit case, a miss case and a disagreement case.
- **Extractor** (`extension/`): kept small enough to be reviewed rather than unit-tested; its only logic is region slicing and link inventory. If you want automated tests of it, that needs `jsdom` as a dev dependency (Q14).
- **Anchor row in the panel** after each capture: `title ✓ company ✓ about ✓ location ✗ poster ✓`, saved in `job.capture.anchors`. A silent layout change shows up the first time it happens.
- **"Copy page structure (redacted)"** in the popup: `skeleton_probe.js` promoted to a user-click tool (class names are never needed, text is shown only for known UI labels). When LinkedIn changes, one click gives the evidence to fix the parser.

#### 2.8.5 What the panel reports
Per capture: the anchor row, the tier used for people (auto / selection / paste), and warnings (stale title, disagreeing anchors, short description, snippet-level description). Nothing is hidden behind a silent default.

---

## 3. In-page UI

### 3.1 Primary: injected floating pill

```
                                                    ┌──────────────────────┐
  any linkedin.com page                             │ ● Job Hunter          │  collapsed: 40px pill
                                                    │  [ Capture job ]  ⌥⇧S │  label follows page type
                                                    └──────────────────────┘
  after a click (same spot, expands upward):
  ┌───────────────────────────────────────────┐
  │ ✓ Saved · Data Engineer @ Acme       Undo │
  │ Fit scoring… · 1 warning: short listing   │
  │ ─────────────────────────────────────── │
  │ Today: 7 jobs · 3 people · 2/10 requests  │
  └───────────────────────────────────────────┘
```

Behaviour:
- Visible on **every** linkedin.com page; button text is `Capture job`, `Capture person`, or disabled `Open a job or profile` (from the URL, §2.3).
- Already-saved pages show `Saved · update` instead.
- Draggable between two corners; position remembered. Collapsible to a dot.
- Keyboard: `Alt+Shift+S` triggers the same action: fewest steps possible, and it works even if LinkedIn covers the corner.
- Closed Shadow DOM; colours come from `styles/tokens.css` values so light/dark follow the system theme (the design-token guard applies to `frontend/`, not the extension, so the extension imports the same raw values by a build step rather than hard-coding hex).
- After a person capture, the panel shows the persona chips (§4) and the "Attach to" job.

### 3.2 Secondary: toolbar popup

| Option | For | Against |
|---|---|---|
| **No popup at all** | Zero surfaces to maintain | No place for status when the pill is hidden (non-LinkedIn tab); a toolbar click does nothing |
| **Tiny popup (recommended)** | Backend reachable? token ok? "pause capture" toggle, open app | A popup closes on blur, so it cannot hold work in progress: keep it read-only |
| **Popup with history/settings** | Everything in one place | Duplicates the app's LinkedIn page; history in extension storage means personal data stored in two places |

**Recommendation:** tiny popup (status, pause, "Open Job Hunter") + a separate **options page** for pairing. **Capture history lives in the app** (LinkedInPage "Captured today", per-job page), where it already has dedupe, undo, and the DNC state. The core loop (browse → click pill → done) never needs the popup.

---

## 4. Persona classification

Three **role-based** personas, plus two flags (decided in the first review, Q3):

| Persona | Enum | Rule |
|---|---|---|
| Engineering Manager / Tech Lead | `lead` | `_LEAD` regex on current title |
| HR / Recruiter | `recruiter` | `_RECRUITER` regex on current title and headline |
| Peer IC | `peer` (was `other`) | default when neither matches |

| Flag | Where | Meaning |
|---|---|---|
| `is_alum` | `linkedin_profile.is_alum`, `LinkedInOutreach.alumni` (exists) | Shares your school. **Never overrides the persona**; the message template adds the alumni hook |
| `hiring_team` | `LinkedInOutreach.hiring_team` (exists) | They posted this job (from the job capture) |

Consequence for existing code: `LinkedInGroup.alumni` stops being a persona value. Existing `alumni` rows migrate to `peer` with `alumni = true`; `linkedin_track.ORDER`, `ANGLE`, the `alumni` prompt angle and the alumni search suggestion need a decision in Phase 1 (Q11).

### 4.1 Options

| | Manual tag at capture | Rule-based inference | Hybrid |
|---|---|---|---|
| Friction | One extra click every capture: exactly what you want to avoid | None | None by default; one click only to correct |
| Accuracy | Perfect when you pay attention | Good on titles ("Talent Acquisition", "Engineering Manager"); weak on "Staff Engineer" (lead or peer?), "Founder", non-English titles; alum needs the Education section, which may not be rendered | Rules decide, you fix the exceptions |
| Failure mode | Skipped tag → procrastination, untagged backlog | Silent misclassification → wrong note angle | Visible suggestion + reasons make errors cheap |
| Code | UI only | Server rules + tests | Both |

### 4.2 Recommendation: hybrid, rules first, computed on the server

- The extension sends the **parsed-by-anchor fields**; the **server** computes the suggestion (extend `detect_group`, so the rules live in Python, are unit-tested, and can be re-run after a rule change with no recapture).
- Persona rules, in order, each returning a *reason* shown in the panel: (1) **recruiter**: `_RECRUITER` on current title/headline; (2) **lead**: `_LEAD` on current title; (3) **peer**: everything else. `is_alum` is computed separately (§2.8.3) and shown as a toggle.
- The panel shows the three persona chips with the suggestion pre-selected and its reason ("Title contains *Talent Acquisition*"), plus the alum toggle. **Saved immediately with the suggestion**; one click on another chip → `PATCH` (`persona_source = manual`, sticky across recaptures).
- With no current title found (anchors missed), the persona is `peer` flagged `low confidence`: the chips show un-highlighted, asking for one click without blocking.

---

## 5. People capture and schema

### 5.1 What a profile capture reads

The fields and anchors are in §2.8.3. Visible page only, on click, no scrolling, no "Contact info" overlay, no posts or activity. Each field carries its provenance (`title | url | heading | link | selection | paste | missing`).

Data minimisation and deletion (decided): store only fields the persona rules or note drafting use; **raw page lines are never stored**. The profile card has a **Delete snapshot** action, and the snapshot is **deleted with its contact** (cascade). No expiry (Q7). `contact.do_not_contact` (`dnc.blocked_reason`) is honoured: the panel shows the flag, the person is still captured, drafting stays blocked as today.

### 5.2 Which job does a person attach to?

`LinkedInOutreach` is per (job, person) and `LinkedInLead` exists only for profile viewers. Proposed server logic on `POST /ext/person`:

1. Resolve the company (`ingest._company`, same normalisation as jobs).
2. If one or more **open jobs at that company** exist → attach to the best (shortlisted, then newest) and say so in the panel: `Attached to Data Engineer @ Acme · change`.
3. If none → keep as a company **contact with a profile snapshot, no outreach row**; shown under "People without a job" and **auto-linked** the moment a job at that company is ingested (extends the existing `leads()` linking).

### 5.3 Schema additions (one migration, reviewed by hand; SQLite batch mode)

New table **`linkedin_profile`** (one per `contact`):

| Column | Type | Notes |
|---|---|---|
| `contact_id` | FK `contact.id`, unique | The canonical person stays `Contact` (dedupe by profile URL, then name: `add_person` unchanged) |
| `profile_url`, `public_id` | text | Canonical `/in/<slug>` |
| `headline`, `current_title`, `current_company`, `company_linkedin_url`, `location` | text | |
| `connection_degree` | int null | 1, 2, 3 |
| `education`, `experience` | JSON | trimmed lists |
| `about` | Text | truncated |
| `badges` | JSON | |
| `persona` | enum (`LinkedInGroup`) | person-level default; `LinkedInOutreach.group` is initialised from it and may differ per job |
| `persona_source` | `auto \| manual` | manual is never overwritten by a recapture |
| `persona_reasons` | JSON | strings shown in the panel |
| `is_alum` | bool | fact, independent of persona |
| `capture_sources`, `captured_at`, `extension_version` | JSON / datetime / text | provenance |

Other changes:
- `LinkedInGroup`: add `peer`; **data migration only** (`other` → `peer`, `alumni` → `peer` + `alumni = true`): the column is `VARCHAR(32)` with no CHECK constraint, so no batch alter (§9.6).
- `LinkedInOutreach.source`: new value `extension` (today `manual | captured | viewed_profile`).
- `Job`: **no schema change** (`linkedin_job_id`, `capture`, `sources`, `source_urls` already fit). `capture` gains `extension_version` and a `health` object.
- Optional: `connection_degree == 1` seen on a re-capture offers **"Mark accepted"** in the panel, reusing `linkedin_track.set_status`. Still click-only; the extension never polls for acceptances.

Post-accept messaging is unchanged (`draft_followup`, review gate, verifier). The extension only supplies better inputs (persona, education, about, company) to `_request`.

---

## 6. The search problem (resolved by Phase 0)

**Confirmed (§9.1):** a geoId + keywords link now redirects into LinkedIn's "describe what you want" prompt; the prompt step is mandatory. After typing, the URL carries `keywords`, `geoId`, `f_TPR=r86400`, `origin=SEMANTIC_SEARCH_HISTORY` and `currentJobId`, but there is **no way to land on rendered results from a direct URL**.

**Does "capture the page you are viewing" make link generation moot? Yes, completely.** Capture keys off the current page, however you reached it, and the job id comes from the URL (`/jobs/view/<id>` or `currentJobId=`, both confirmed). The one remaining dependency is the job pane's structure, handled by §2.8.

**Decision: drop the URL generator, keep a routine.**
- **Removed:** `search_url`, the link `url` in `GET /linkedin/links`, `frontend/src/lib/linkedin.ts`, the geoId settings (`linkedin.geo_ids`, the verified/unverified UI, "Test link", `missing_geo`), the **Easy Apply** toggle (LinkedIn's own filter does it), and their tests.
- **Kept, simplified:** "Today's searches" stays as a daily checklist, one row per role × target country, each with a **Copy prompt** button (text built in code, for example `Data Engineer jobs in Jordan (the country), posted in the last 24 hours, remote or hybrid`) and one plain **Open LinkedIn Jobs** link. A row is ticked "searched today" (reusing `linkedin_link_open`, key `role|country`). Naming the country in words also removes the "Jordan, Pennsylvania" ambiguity that geoIds were for.
- **Not done, on purpose:** the extension never types into LinkedIn's search box or fills the prompt for you. That would be automation of the page, outside the click-only rule.

---

## 7. Migration plan

| | Items |
|---|---|
| **Removed** | The URL search generator and geoId settings (§6); `features/linkedin/bookmarklet.ts`; `features/linkedin/capture.ts` (moves into `extension/src/shared/`, rewritten and tested); `BookmarkInstall` and the Settings "bookmark" card; the `/import` route, the postMessage and `#c=` handoff in `ImportPage.tsx`; `POST /linkedin/capture` and `/linkedin/import` (replaced by `/ext/*`); `useCheckCapture/useImportJob` hooks. The `Source.linkedin` comment "imported with the bookmark". |
| **Kept** | `POST /linkedin/paste` + a paste box on the LinkedIn page (LinkedIn's markup will change again; there must always be a manual path, and for people it is fallback tier 3). |
| **New** | `services/linkedin_page.py` (server-side parsers for job and profile payloads, §2.8); the popup's "Copy page structure" tool; `extension/` (manifest, content, background, panel, options, popup; `make extension`); `api/ext.py` + token dependency + CORS setting; `linkedin_profile` model + migration; persona rules + tests; fixtures for jobs (synthetic or redacted) and profiles (**synthetic only**: real profiles are third-party data); extension guard test; Settings → LinkedIn "Extension" card (token, pairing steps, `TourButton`); LinkedInPage "People" list and "Captured today"; tour entries. |
| **Reused unchanged** | `validate`, `from_paste`, `existing`, `import_job`, `add_person` (extended with the profile snapshot), `detect_group` (extended), `_WALL`, `ingest`, `dedupe_key`, scoring queue trigger (`trigger="linkedin"`), `LinkedInOutreach`, `LinkedInLead` linking, `linkedin_track` drafting/verification/DNC, `test_the_backend_never_requests_linkedin`. |
| **Docs** | CLAUDE.md LinkedIn rule rewritten (still: no scraping or automation; now "reads the page you are viewing, on click, in your browser, through the extension"); SPEC §3.6b; DATA_MODEL (`linkedin_profile`, enum); DESIGN note for the extension panel; new `docs/EXTENSION.md` (install, pairing, permissions, what it reads). |

---

## 8. Phased roadmap (revised)

0. **Spike: done** (§9).
1. **Backend (no extension needed, `make test`):** `/api/ext/*`, token, CORS setting (`allow_origin_regex` for the extension ID), `linkedin_profile` + migration (`other`/`alumni` → `peer`, §9.6), `description_level` fix (§9.5), `services/linkedin_page.py` parsers with payload tests, persona rules, simplified "Today's searches" backend (drop `search_url`/geoIds), paste parser extended for profile text.
2. **Extension skeleton + gate (2a):** build pipeline, manifest, pairing/options, tiny popup with **Copy page structure**, the pill, the anchor row. **Gate:** run the structure tool on at least 3 of your profiles and 3 job pages, check the §2.8.3 profile anchors and the §2.8.2 location/workplace anchors against real output. Pass → continue; fail → people capture ships on fallback tiers 2-3 first and auto extraction follows later.
3. **Job + people capture (2b):** job capture with undo, missing-field flow and poster; person capture with persona chips, alum toggle, attach-to-job, snapshot, "Mark accepted"; shortcut; guard test. (Equal priority, as you decided: they share the pill, the payload and the parser.)
4. **App UI:** LinkedInPage (People list, Captured today, prompt checklist, install/pair card), empty states, tour.
5. **Cutover:** run both for a few days, delete the bookmarklet path (§7), update docs, final guard tests.

Build note: existing Vite with a hand-rolled multi-config build (the content script is a single IIFE, because MV3 content scripts do not support ES module imports); no new dependency.

---

## 9. Phase 0 findings (spike complete)

Method: your own browser with read-only console snippets (no request to linkedin.com from the backend, a script or me), a throwaway extension and server outside the repo (now deleted), and read-only code/DB reads. Raw probe outputs were summarised by you; I did not see the JSON.

| # | Item | Result |
|---|---|---|
| 1 | Classic search URL | **Dead for direct linking** |
| 2 | Job pane DOM | **Class selectors dead; title/heading/link anchors work** |
| 3 | Second (classic-style) job layout | **Not reachable; design for the one confirmed layout** |
| 4 | Profile DOM | **Current approach does not work on this layout (repeatable)** |
| 5 | MV3 CORS-only localhost fetch | **Pass** |
| 6 | Browser | **Current stable Chromium (Chrome/Edge), no pin** |
| 7 | Open questions | **Answered (§10)** |
| (code) | `description_level`, enum rename | **Confirmed (§9.5, §9.6)** |

### 9.1 Classic search URL fate: RESOLVED, dead
A geoId + keywords link redirects to the "describe what you want" AI prompt. After typing into it, the URL still carries `keywords`, `geoId`, `f_TPR=r86400`, plus `origin=SEMANTIC_SEARCH_HISTORY` and `currentJobId`: the backend search still understands the parameters, but there is no way to reach rendered results by direct URL, so link generation has no value. Design impact: §6.

### 9.2 Job detail pane DOM: RESOLVED
- **Dead:** every class-based selector (`job-details-jobs-unified-top-card__*`, `jobs-unified-top-card__*`, `top-card-layout__*`, `#job-details`, `.show-more-less-html__markup`, pane containers). Also no `h1`, no JSON-LD, no `og:title`.
- **Why it will stay dead:** the classes seen in the second probe (`ajrlr8`, `ajrayf`, `ajrij2`, `ajrjqs`, …) are short hashed atomic utility classes from LinkedIn's build tooling. They are not stable across deploys, so class selectors are **not a maintained fallback anywhere**, including the logged-out page unless a separate probe shows that page uses semantic markup (not probed; JSON-LD stays as an opportunistic strategy because it is not class-based).
- **Confirmed reliable on both probes:** tab title `"{title} | {company} | LinkedIn"` (example: `Fullstack web & mobile developer | Hays | LinkedIn`); exact heading text **"About the job"**; exact heading text **"Meet the hiring team"** with an adjacent `/in/<id>/` link (the job poster); `a[href*="/company/"]` appears reliably and repeatedly (several per page, so it must be scoped, §2.8.2); section headings are `h2` with `h3` sub-labels: match by tag + known text.
- **Not confirmed from the probes:** where location, workplace and posting date live. §2.8.2 treats them as header-region lines and says so.
- Design impact: §2.8.2.

### 9.3 Other job layout: RESOLVED (not reachable)
No classic-style results layout could be found to probe. We design for the one confirmed layout; the anchors above are layout-independent, which is the point.

### 9.4 Profile page DOM: RESOLVED, current approach does not work
Run several times across different profiles with the same result: empty top card, no `h1`, most section headings unresolved to their label. An early run did show Education/Experience content and `/school/`, `/company/` links before scrolling, so the data is in the DOM; what fails is locating it through a top card, `h1` or label elements. Design impact: §2.8.3 (line-and-link strategy plus fallback ladder). **Not validated against real profile output** (no further profile probes, as you asked): the Phase 2a gate does that.

### 9.5 `import_job` and `description_level`: CONFIRMED
`import_job` builds `RawJob` without `description_level`, which defaults to `full` (`providers/base.py:54`). A meta-sourced (`og:description`) description would be stored as `full` and scored with full confidence. Your 7 real LinkedIn jobs came from `page` (3) and paste (4), none from `meta`, all `full`, so no row is wrong today. Phase 1 fix: a description that is not from the heading anchor or JSON-LD, or is under 1,500 characters, is `snippet`; `import_job` passes it through; test included.

### 9.6 Enum rename: CONFIRMED, data migration only
`LinkedInGroup` is a Python `StrEnum`; the column is `VARCHAR(32)` with no CHECK constraint (live `sqlite_master`). Migration = `UPDATE linkedin_outreach SET "group"='peer' WHERE "group"='other'`, plus `UPDATE … SET "group"='peer', alumni=1 WHERE "group"='alumni'` (decided). No `batch_alter_table`. The new `linkedin_profile` table is a plain `create_table`. Your DB: 3 rows (1 alumni, 1 other, 1 recruiter). Code to change: `models/enums.py`, `models/linkedin.py:34`, `services/linkedin.py` (`detect_group`), `services/linkedin_track.py` (`ORDER`, `ANGLE`, `suggestions`); `applied_check.PERSONAS` is a different concept and stays.

### 9.7 MV3 service worker `fetch` to localhost with CORS only: PASS
Throwaway extension with `host_permissions: ["https://www.linkedin.com/*"]` only. Run 1 (empty allow-list): `Failed to fetch` ×3; the server log showed the requests arrived and Chrome blocked the **responses**. Run 2 (origin `chrome-extension://jicnknngfmjdbfihfenbmjokcjibkpgj` allow-listed): simple GET, GET with `Authorization`, JSON POST with `Authorization` + `X-Workspace` all returned 200, and the server saw the bearer header. **Q4 is closed: CORS + token is sufficient; `localhost` is not in `host_permissions`.** Caveats for Phase 1: set a fixed manifest `key` so the extension ID is stable; the real FastAPI `CORSMiddleware` (not the throwaway server) gets its own test; the backend binds `127.0.0.1` only (`make dev`: `--port 8000`, no `--host`). No browser version is gated: build and test on current stable Chrome/Edge.

---

## 10. Open questions

**Resolved:**
- Q1 No bulk capture. Q2 People without a job = contact + snapshot, auto-linked later. Q3 Role-based persona (lead/recruiter/peer), `is_alum` a separate flag. Q4 CORS + token, no localhost permission (§9.7). Q5 Hand-rolled multi-config Vite build. Q6 `other` → `peer`, no legacy value. Q7 Keep snapshots, no expiry; **manual Delete snapshot + cascade with the contact is sufficient (confirmed)**. Q8 Search links: dropped, prompt checklist kept (§6). Q10 People and job parity equal priority. **Alum rows → `peer` with `alumni = true` (confirmed).** Browser: current stable Chromium, no pin.

**Still open (each has a default; none blocks Phase 1 except as noted):**
- **Q9** Shortcut `Alt+Shift+S`: free on your setup? (default: yes, rebindable in `chrome://extensions/shortcuts`).
- **Q11** After `alumni` leaves the persona set, what happens to the "alumni" entry in `linkedin_track.suggestions` (the people-search hint)? Default: keep it as a **search hint** (it is not a persona), and drop only the persona/angle value.
- **Q14** Allow `jsdom` as a **dev** dependency to unit-test the extractor, or accept the no-new-dependency default (small reviewed extractor + server payload tests + the on-page anchor row)? Default: no new dependency.
- **Q15** Which LinkedIn **UI language** do you use (the heading labels depend on it)? Default: English only; other languages added when seen.
- **Q16** OK to drop the **Easy Apply** toggle with the generator (§6)? Default: yes.
- **Q17** The hiring-team link can be an opaque id (`/in/<id>/`), not a vanity slug. Dedupe falls back to name + company (as `add_person` does today); when the same person is later captured from their profile page, the vanity URL replaces the opaque one. Default: accept.
- **Q18** Location is not a required field; a job saved without a location has no country. Confirm that open-jobs/location filters should treat "no country" as **visible with a warning**, not hidden (to verify in `services/open_jobs.py` in Phase 1). Default: visible.

---

## 11. Phase 1 progress: gate PASSED, post-gate backend started

Order as approved: skeleton and structure tool first; persona, schema, parsers and capture logic wait for the gate. Nothing is committed.

### 11.1 Q18 verified: today's behaviour is NOT "visible with a warning"
`services/prefilter.check` returns `location_outside:unknown` for a **non-remote job with no country** whenever target countries are set (`prefilter.py:71`), and `open_jobs.open_ids` drops every job with a filter code in `_FILTER_CODES`. `import_job` queues scoring with `enqueue(..., only_open=True)` (the default), so a captured LinkedIn job with no parsed country is **hidden from bulk views and silently not scored**. Fix to include in the post-gate backend work: a job whose source is `linkedin` (you chose it by capturing it) skips the location filters in `open_ids`; missing country adds a warning only. Test: a countryless on-site LinkedIn capture is open and queued.

### 11.2 What was built (all under `extension/`, plus one test and one Makefile target)
- `manifest.json` (MV3, `permissions: ["storage"]`, `host_permissions: ["https://www.linkedin.com/*"]`, no `tabs`, no `web_accessible_resources`, fixed `key`: ID `chmdlkfgnkafhlghokcgggmddahnaoao`); `build.mjs` (hand-rolled multi-config Vite, no new dependency); `make extension` (type-check + build).
- `src/shared/extract.ts` (the §2.8 extractor: tab title, URL, exact labels, link shapes, document-order regions, anchor row), `text.ts` (rendered-text lines by computed `display`, so no class or tag-name assumptions), `report.ts` and `structure.ts` (redacted copies), `labels.ts` (English only), `urls.ts`.
- `src/content/index.ts`: the pill in a closed Shadow DOM (reads the page only on click/shortcut/popup request); `src/background/index.ts` (relays URL changes and the shortcut, no network); `src/popup/*` (status, check, the two copies).
- `backend/tests/test_extension_guard.py` (4 tests): permissions, and no timers, observers, clicks, scrolling, network, `innerHTML`, class reads or class/id selectors in any source.
- **No backend change, no token, no CORS, no migration yet.**

### 11.3 Verified so far, and what is NOT
- Type-check, build and the guard tests pass.
- The extractor ran in a real browser against **synthetic pages I wrote** (a job page with a results list of other companies plus a detail pane; three profile layouts: `h2` + `li`, inline `span`s with a doubled label, and plain text with `<br>`), with hashed junk classes present. Job: all anchors hit and the pane scoping ignored the other companies' links. Profiles: elements mode and lines mode both found the sections; the doubled label was matched. A weakness found and fixed in this run: text was cloned and split by tag name; it now reads the live DOM and breaks lines by computed `display`.
- Known limitation: in lines mode (no label elements) links cannot be assigned to regions (`unknown`).
- **Not verified:** any real LinkedIn page. Synthetic pages prove the code, not LinkedIn's markup.

### 11.4 The gate (needs you)
Load `extension/dist` unpacked (README), open **3 real job pages** (mix: a direct `/jobs/view/…` page and results where the detail pane is selected) and **3 real profiles** (ideally different seniorities/languages of content, at least one with an INSAT education entry), press the pill, and send me **Copy report** for each (redacted by default; "Copy page structure" too if an anchor fails). Include page text only on your own profile.

Pass criteria, fixed in advance so the result is not a judgement call:

| | Core (must hit) | Wanted (informational) |
|---|---|---|
| **Job page** | job id; tab title gives title + company; "About the job" heading; detail pane found; description text ≥ 200 characters; ≥ 1 header line | location/workplace line; "Meet the hiring team" + poster link |
| **Profile** | name starts a top line; ≥ 3 top-region lines; an Experience region with content | degree line; "Contact info" label; company link in the top region; Education region/school link; `li` items |

- **PASS:** core hits on all 3 jobs and all 3 profiles → build persona/schema/parsers and the capture flow.
- **PARTIAL:** core on ≥ 2 of 3 profiles (and all jobs) → job capture ships; profile auto-extraction ships behind the **selection** fallback.
- **FAIL:** otherwise → job capture ships; people capture ships on fallback tiers 2-3 (selection, paste) first while the anchors are redesigned from the structure copies.

I will stop at the gate and report the result to you before any further build.


### 11.5 Gate result: PASS (3 distinct search-layout jobs, 1 direct job page, 3 profiles)
- Core anchors hit on every job and profile; the INSAT profile (the second one) had its degree line, school link and Education region.
- Anchors that were **wrong, not the extraction** (fixed): the profile "company link in the top region" and the `li` counts (LinkedIn renders those as plain lines; replaced by dated lines in Experience/Education), the pill being disabled after an SPA navigation (it now follows the live URL), and the job **location line**: the header region started *below* the top card (the pane was defined by a "life" link in the About section), so it held only LinkedIn's AI widgets and the earlier comma-based match was a false positive ("Job match is medium, review match details"). The header now starts at the last element before "About the job" whose exact text is the tab title; the location anchor accepts only a ` · ` line, a lone `·` between split spans, or Remote/Hybrid/On-site. Confirmed on both layouts.
- Still for the server parsers (recorded text, not code yet): the description ends with a literal "… more" when the listing is collapsed; AI widgets ("Job match…", "Show match details", "People you can reach out to") appear in the header and differ per layout; the Education region runs into Certifications/Volunteering/Projects until the `/details/…` "Show all" link shapes; the top card and profile top region repeat Follow/Message/More.

### 11.6 Post-gate backend, slice 1 (done, uncommitted, full suite 1266 passed)
- **Q18** (`open_jobs.open_ids`): jobs with source `linkedin` skip the location/remote filters; a countryless non-remote capture is saved with the warning "No country found in the location" and stays open and scored.
- **`description_level`** (`linkedin.Capture.description_level`): a collapsed listing ("… more", now stripped by `clean_description` and warned about) or a `meta`-sourced description is stored as `snippet`; everything else `full`. A cut-off re-capture never replaces a complete stored listing.
- Tests: `test_a_collapsed_or_meta_description_is_a_snippet_not_full`, `test_a_countryless_linkedin_capture_stays_open_and_scored`.
- Next (not started): `/api/ext/*` + token + CORS setting, then the `linkedin_profile` table and the `other`/`alumni` → `peer` migration, `services/linkedin_page.py` parsers, persona rules, search checklist.

### 11.7 Post-gate backend, slice 2: `/api/ext/*`, token, CORS, migration 0038 (written, NOT run on the real DB)
- **Restore point before the slice:** `data/backups/jobhunter-before-ext-slice-20261029-101714.db` (online backup, integrity ok, 6383 jobs, 3 `linkedin_outreach` rows, revision 0037).
- **Token** (`services/ext_auth.py`, `api/ext.py`): created in Settings → LinkedIn → Browser extension, shown once, only its SHA-256 in `app_setting.extension_auth` (never returned by `GET /api/settings`: this was a real leak the test caught, now filtered). A JSON body is required to create/rotate, so a plain cross-site form post cannot. One token at a time.
- **CORS** (`config.extension_ids`, `main.py`): `allow_origin_regex` is exactly `^chrome-extension://(<id>)$`, ids validated as 32 chars `a-p`. Note: CORS is app-wide, so the extension origin may read non-`/ext` responses too; only `/ext/*` accepts writes with the token, and the extension guard test forbids the extension from calling anything else.
- **Routes behind the bearer token** (real workspace only, `X-Workspace: demo` refused): `GET /ext/ping`, `GET /ext/status`, `POST /ext/job` (transitional body = the existing `CaptureIn` fields; saves nothing when a required field is missing), `POST /ext/paste`. **Not yet:** `POST /ext/person`, `PATCH /ext/person/{id}` (need the profile parser and persona rules), the thin-payload job parser (needs the recorded top-card text), and the extension's options page / service-worker `fetch` (pairing).
- **Migration 0038** (`alembic/versions/0038_linkedin_profile_and_peer.py`): creates `linkedin_profile` (FK to `contact` with `ON DELETE CASCADE`, unique per contact) and maps `alumni` -> `peer` + `alumni = 1`, then `other` -> `peer`. Code moved in step: `LinkedInGroup` = hiring_team | lead | recruiter | peer; an alum peer keeps the "alumni" drafting angle and sorts right after the hiring team (so drafting and ordering are unchanged for migrated rows); stats count alumni by the flag.
- **Verified on a COPY of the real DB** (scratchpad, never the real file): `alembic upgrade head` fired the automatic backup (`jobhunter-before-migrate-from-0037-…db`, revision 0037) and the 3 real rows became `recruiter/alumni 0/hiring 1`, `peer/alumni 1`, `peer/alumni 0/hiring 1`. Full suite 1274 passed.
- **Open for review:** the alumni row's title contains "Responsable", which the role rule (`_LEAD`) reads as a lead; the migration follows your decision (`peer`).

### 11.8 Migration 0038 applied; to do before persona auto-classification is relied on
- **Applied** to the real DB on 2026-10-29 (backup `jobhunter-before-migrate-from-0037-20261029-104116.db`, revision 0038, integrity ok). Rows: 1 `recruiter` (hiring team), 2 `peer` + alumni (kept `peer` by decision), 3 `peer` (hiring team).
- **Tighten `linkedin._LEAD` before the Phase 1 persona rules:** it matches the generic French word "Responsable" (and "manager", "director"…) on any title, so a non-technical "Responsable de gestion des exigences" reads as a team lead. The persona rule should require a leadership word together with an engineering/data/tech keyword (or the hiring-team flag), and a non-technical manager stays `peer`. Add a test with this title as the negative case.
