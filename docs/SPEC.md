# Job Hunter v2: product spec

A local, single-user workspace for my Data Engineering / AI Engineering job search, targeting the
countries chosen in Settings (currently France, Spain, Italy, Portugal, Germany, Belgium, the UAE, Qatar,
Bahrain, Kuwait, Jordan) or remote. The app finds jobs, scores fit, prepares a tailored CV and
outreach, and keeps me in control. **Nothing is final or sent without my review.**

## 1. The flow

| # | Step | What happens | Where in the UI |
|---|---|---|---|
| 1 | **Discover** | A daily scheduled pull from Adzuna, Remotive, Arbeitnow, and Welcome to the Jungle, filtered by the active search profile. LinkedIn is excluded from automation | Discover, Today, Settings → Sources |
| 2 | **Score fit** | An LLM (Ollama, local) scores each job 0–100 against the master experience, with strengths and gaps | Fit badge everywhere, fit panel |
| 3 | **Dedupe** | The same job from 2 sources is flagged as a duplicate. Companies already contacted or applied to are flagged | Discover flags, Job detail |
| 4 | **Resolve contact** | Tier (a) is the imported Apollo dump. Tier (b) queues a manual Apollo extension lookup, with a small daily cap. Tier (c) is no contact | Contact block, Contacts |
| 5 | **Tailored CV** | Generated per job (Claude headless, structured JSON) from the experience pool into a style-only LaTeX template (docs/CV_TEMPLATES.md), fitted in code to exactly one full page | CV Studio |
| 6 | **Route** | With a contact, the route is **cold email** (a draft is generated). Without one, it is **web apply** (I get the CV and the listing link, and apply myself) | Job detail, Pipeline |
| 7 | **Human review** | I review and edit every CV and every email | CV Studio, Outreach → Review |
| 8 | **Send / track** | Queued Gmail SMTP: 15 min between sends, max 20 per queue, pause/resume. Web-apply jobs: open the listing + approved CV, then Mark applied (date, method, CV version locked) | Outreach → Queue, Applications |
| 9 | **Follow up** | Follow-up reminders (7/14 days, configurable), replies and interview rounds logged, closed with an outcome; stats and CSV export. No model calls | Today, Applications |

Pipeline stages: **New → Shortlisted → CV ready → Ready to send / Ready to apply → Sent / Applied → Interview → Closed**
(see DATA_MODEL.md for the allowed transitions).

## 2. Global UX

- **Layout:** left sidebar (nav with counts, collapsible, auto-collapses below 1280px), a 48px top bar (page context, global search, theme toggle, "Run discovery" action), and the content area. Minimum width is 1024px.
- **Global search / command palette:** `⌘K`, or clicking the search field. It searches jobs, companies, and contacts, and has actions (go to page, run discovery, pause queue, toggle theme).
- **Toasts** (bottom-right) confirm every mutation. Dismiss and reject actions carry an **Undo**.
- **Keyboard:**

| Key | Action | Scope |
|---|---|---|
| `j` / `k` | Next / previous item | List views (Discover, Pipeline table, Outreach review, Contacts) |
| `Enter` / `o` | Open the selected item | List views |
| `s` | Shortlist | Discover, Pipeline table |
| `d` | Dismiss (with undo) | Discover, Pipeline table |
| `a` / `r` | Approve / reject draft | Outreach review |
| `o` / `a` | Open listing + download CV / Mark applied | Applications → Ready to apply |
| `Esc` | Close panel / dialog | Everywhere |
| `/` | Focus page search or filter | Everywhere |
| `⌘K` | Command palette | Everywhere |
| `g` then `t d p a o c e s` | Go to Today, Discover, Pipeline, Applications, Outreach, Contacts, Experience, Settings | Everywhere |
| `?` | Shortcut help | Everywhere |

Shortcuts are ignored while focus is in an input, textarea, or contenteditable.

- **States:** every data view implements *loading* (a skeleton matching the layout), *empty* (an explanation plus one clear next action), *error* (a message plus **Retry**), and *populated*. Dev aids: `MOCK_LATENCY_MS` on the backend simulates slow responses.
- **No dead ends:** every detail screen links to the next step of the flow and back to its list.

## 3. Screens

### 3.1 Today (`/`)
*Purpose:* the "what needs me now" inbox. It is the landing page.
- A greeting with the date and a one-line summary ("4 things need you"), plus a stats line once you have applied
  ("2 applied this week · response rate 67% (2/3)", links to Applications → Stats).
- **Attention cards**, each with a count, the top 3 items, and a "View all" deep link:
  - *New high-fit jobs:* stage `new` with fit ≥ the profile's min score → Discover filtered to `new` and sorted by fit.
  - *CVs to review:* the latest CV version in `draft` → CV Studio.
  - *Drafts to approve:* outreach drafts in `draft` → Outreach Review.
  - *Ready to apply manually:* approved CV, route `web_apply`, not applied → Applications → Ready to apply; "Mark applied" opens the dialog.
  - *Follow-ups:* due reminders (Snooze 3 days / Dismiss / Log reply) and ghosting suggestions ("no reply in 30 days: close as no response?" → Close as no response / Not yet). Nothing closes without the click.
  - *Upcoming interviews:* pending rounds in the next 14 days.
  - *Send queue:* status, next send time, count pending, and an inline Pause/Resume.
- **Last discovery:** per-source result of the latest run (new / duplicates / failed) + a "Run discovery now" button.
- *Brand-new workspace* (discovery never ran): a 3-step onboarding card (add experience → import contacts → run discovery).
- *Empty:* "You're all caught up", with a "Browse Discover" action. *Loading:* card skeletons. *Error:* page-level error with retry.

### 3.2 Discover (`/discover`)
*Purpose:* triage newly discovered jobs.
- **Tabs:** New (default, with count) · All open · All.
- **Toolbar:** a search input (title/company), filters (Source; Remote type; Country; Min fit; Posted within; Hide duplicates), and sort (Best fit, Newest). Active filters show as removable chips, with a "Clear all" option. Filters live in the URL.
- **List rows:** fit badge, title, company, source badge, location + remote badge, and relative posted date. Flags: duplicate, already contacted. Hover shows quick actions (shortlist / dismiss).
- **Side panel** (`?job=<id>`): title/company/location header, actions (Shortlist, Dismiss, Open full page, Open listing ↗), fit card (score, band, summary, strengths ✓, gaps △), contact status (tier badge + contact or "no contact → web apply"), flags, and the description.
- *Actions:* shortlist (→ `shortlisted`, toast, auto-advance to the next item), dismiss (→ closed/dismissed, toast with Undo, auto-advance).
- *Keyboard:* j/k, Enter, s, d, Esc.
- *Empty (no jobs at all):* "No jobs yet", with a "Run discovery" action. *Empty (filtered):* "No jobs match these filters", with "Clear filters". *Loading:* row skeletons. *Error:* inline error + Retry.

### 3.3 Pipeline (`/pipeline`)
*Purpose:* see and move everything I'm pursuing.
- **Board view** (default): 7 columns with a count per column. Cards show the title, company, fit badge, route icon (mail / globe), and days in stage. Cards can be dragged between columns, but only allowed transitions are accepted (the target highlights; a disallowed move snaps back with a toast explanation). Clicking a card opens the Job page.
- The **Closed** column hides dismissed jobs unless "Show dismissed" is on. Dropping a card on Closed asks for a reason: after applying rejected, no response, withdrew, offer accepted, offer declined; before, not a fit or withdrew.
- Dropping a web-apply card on **Applied** opens Mark applied; dropping on **Interview** opens Log interview.
- **Table view** (`?view=table`): sortable columns (Job, Company, Stage, Route, Fit, Contact, Updated), j/k selection, s/d shortcuts, and Enter to open.
- *Empty:* "Nothing in your pipeline yet. Shortlist jobs from Discover", with a "Go to Discover" action. *Loading:* column skeletons. *Error:* retry.

### 3.4 Job detail (`/jobs/:id`)
*Purpose:* everything about one opportunity in one place.
- **Header:** title, company, location/remote, source, and posted date. There is a stage selector (only allowed transitions are offered), a route toggle (cold email / web apply), and the primary next-step action, which depends on stage:
  new → Shortlist · shortlisted → Generate CV · cv_ready (email) → Draft email · cv_ready/ready (web) → Mark applied · ready (email) → View send queue · done → Log interview · interview → Record outcome.
- Web apply with an approved CV: a callout with **Open listing + CV** (one click: listing in a new tab, PDF downloaded), Download CV only, Mark applied.
- Once applied, an **Application** section: applied on, method, CV sent (locked version, download), notes, replies, interview rounds (outcome editable), with Log reply / Log interview / Close…. CV versions sent show a "Sent" badge.
- **Main column:** Listing (description, Open original ↗), Fit breakdown, CV versions (list with status + "Open in CV Studio"), Email draft (preview + "Edit in Outreach"), Notes (autosaving textarea).
- **Right column:** Contact (tier, person, email, "Queue Apollo lookup" when tier is none), Company (contacted flag, other jobs at this company), and the Timeline (stage changes and events, newest first).
- *Not found:* "This job doesn't exist or was removed", with "Back to Discover".

### 3.4b Applications (`/applications`)
*Purpose:* everything after the CV. Nothing here calls a model. Tabs in the URL (`?tab=ready|applied|stats`).
- **Ready to apply:** approved CV + no contact, not applied (`cv_ready`/`ready`, web apply). Rows: job, company, track,
  country, approved CV version. **Open listing + CV** (one click) and **Mark applied** (dialog: date default today,
  method, the CV version that gets locked, notes). Keys: j/k, `o`, `a`.
- **Applied:** every application with `applied_at`, filtered by track, country, source, stage and applied date range
  (URL params). Row: date, job, stage (close reason when closed), source, reply/interview counts, days to first answer.
  j/k, Enter opens the job, the side panel (`?app=`) shows applied facts, Log reply / Log interview / Close…, and the
  timeline. **Export CSV** (same filters; one row per application).
- A positive reply suggests "Log interview"; a rejection suggests "Close as rejected" (toast actions, nothing automatic).
- **Stats:** applied count, response rate (any reply or interview ÷ applied), interview rate, median days to the first
  answer, applications per ISO week (CSS bars), and both rates by track, country and source, always with counts ("2/3").
- *Empty:* each tab explains the next step (approve a CV / go to Ready to apply) with "See how it works".

### 3.5 CV Studio (`/jobs/:id/cv`)
*Purpose:* review and adjust the tailored CV for one job. The contract is in docs/CV_TEMPLATES.md.
- **How a CV is shaped** (Settings → CV → "How CVs are written"): a writing guide (given to Claude with the
  reference CV's summary and bullets as a style example) and structure rules enforced in code:
  - bullets by role type, not relevance alone: current role 3-4, roles over a year 2-3, graduation project /
    short roles 1-3 by relevance (2+ when highly relevant), internships at most 2; at most 2 projects with 2-3
    bullets each (never a 1-bullet project); inside each entry, the most relevant bullets first, generic ones last;
  - page fill target 88%: entries start at their minimum and only grow within the allowances; a CV that can't
    reach it stays shorter (never filler);
  - skills: at most 4 groups of ~8, most relevant first, known pairs merged ("LLMs (Mistral, Ollama)",
    "LocalStack (S3)", "Linux/Bash"), nothing repeated across groups, tools spelled as usual;
  - summary: at most 2 sentences, ~45 words, no numbers from the bullets, no certifications, no internships, no
    tool lists; checked in code and regenerated once, then flagged if still off.
- **Generate / Regenerate:** one Claude call per job (never in bulk). It returns a plan (pool ids, reworded and ranked bullets, skill order, summary). Code then checks it (nothing invented, numbers exact, every role kept) and fits it to exactly one full page (≤ 4 compile passes, no further model call). About a minute.
- **Left, "From your experience pool":**
  - readiness warnings (e.g. no full name blocks generation; no education or summary snippet warns)
  - the checks that failed or are worth a look
  - summary (editable, plus the short version used on tight pages)
  - every role with its bullets, projects and certifications. The eye toggles force an item in or out; text edits inline. Each change re-fits and recompiles without calling Claude, and every role keeps at least one bullet.
- **Right:** the real PDF (iframe), with a fit badge ("1 page · 97% full", passes and template in the tooltip).
- **Toolbar:**
  - version switcher
  - template picker (valid templates; per-CV override)
  - **Regenerate** (new draft)
  - Download (filename pattern from Settings → CV)
  - **Approve**: only at one page. It supersedes the others, moves the application to `cv_ready` and offers "Draft email" or "Mark ready to apply".
  - Changing an approved CV creates a new draft.
- *Empty:* "No CV for this job yet" with Generate (or "Open Candidate settings" when the full name is missing).

### 3.6 Outreach (`/outreach`)
*Purpose:* one cold email per job, reviewed by you, sent through your Gmail. No bulk drafting.
- **Drafting** (`services/outreach.py`): Claude Code headless with the CV generator's isolation and subscription
  check (`providers/claude_email.py`, prompt `app/prompts/outreach.md`, versioned). Input: the job listing, the
  contact (first name, title, role group), the items on the **approved CV** (the only candidate facts it may use),
  the years facts, and the rules. Output: subject, greeting, 2–4 sentences (each citing CV items, or marked as
  about the listing) and one ask. Needs an approved CV and a contact with an email.
- **Checks** (`services/outreach_check.py`): candidate sentences grounded in the cited items (the CV checks:
  numbers, tools, capabilities, scope, years); listing sentences only state what the listing says; ≤ word limit;
  exactly one ask; the greeting uses the contact's first name; the company is named; no other draft's company;
  no banned phrase (editable list); near-duplicates of drafts to other people are warnings. One retry with the
  problems as feedback, then the draft is kept with its problems listed. Errors block approval. Edits are
  re-checked (text-level).
- **Review tab:** list (To review | Approved | Rejected | All); editor with the checks panel, subject, your text,
  "Added when sent" (signature + opt-out from Settings → Email), "Where each sentence comes from" (hover for the
  cited CV items), **Approve & queue** (primary), Send test to me, Regenerate, Reject. Keys: j/k, a, r.
- **Send test to me:** the exact email, CV attached, to your own address with "[TEST]" in the subject; no stage
  change. **The queue can't start before one successful test send.**
- **Queue tab:** Running / Paused / Idle, next send countdown, 15 min between sends, max 20 per queue. The worker
  sends one email per interval through Gmail SMTP (`SMTP_APP_PASSWORD` in `.env`), attaching the approved CV and
  locking that version. Failures are shown with Retry; a login/config failure pauses the queue. An email caught
  mid-send by a restart becomes "Check Gmail" (never resent blindly): Retry or "I found it in Sent". Every attempt
  is in `send_log`. A sent email moves the job to **Sent** (`done`, method email) and feeds follow-ups, replies
  and stats (Applications).
- *Empty review:* "No drafts waiting. Drafts appear after you approve a CV for a job with a contact." *Empty queue:* "Queue is empty. Approved drafts land here."

### 3.7 Contacts (`/contacts`)
*Purpose:* who each job is written to. Tabs in the URL (`?tab=companies|lookups|import|match`).
- **Resolution (3 tiers, `services/contacts.py`):** (1) the best-ranked imported contact at the job's company
  (Settings → Contacts ranking: CTO → VP/Head of Engineering → Head of Data/AI → Engineering Manager → Tech Lead →
  HR/Talent → Founder/CEO; ties: has an email, then most recent); (2) no contact → the **company** joins the lookup
  queue (one row per company); (3) the lookup found nobody, or the company is marked "never look up" (a job
  board / aggregator) → "No contact", web apply.
- **Ranking by company size:** "small" (exact headcount below the threshold, or an "under N" bound at most the
  threshold; default 200, Settings → Contacts) uses CTO → Founder/CEO → Head of Eng → Head of Data → EM → Tech Lead
  → HR; large or unknown size uses HR/Talent → EM → CTO → Head of Eng → Head of Data → Tech Lead → Founder. Both
  orders are editable. Companies from the Apollo lists are "under 200"; set any company's size in its detail pane.
  Runs after every discovery run and import, and on demand. Never replaces a contact you picked, never touches jobs
  applied to or closed, never changes a route (a web-apply job with a new contact offers "Switch to cold email?").
- **Companies:** filters With jobs / Has contacts / Needs lookup / No contact, search, j/k. Detail: contacts ranked
  (role group label, "Written to first"), the company's jobs with their tier and a per-job contact picker
  (Automatic or a person), "Add contact".
- **Lookup queue:** per company: shortlisted jobs first, then the best fit, then the newest job, each row showing
  why ("1 shortlisted job", "Best fit 92", "Fit 92, newest job 3 days ago"). Companies that look like job boards
  (name contains remote/jobs/hire/recruit/talent…, most listings "for a client", many jobs across tracks) show a
  suggestion: Never look up / It's an employer. Never (X) takes the company out, with Undo. Daily counter "3 / 10 today" (resolved lookups since local
  midnight, cap in Settings). Enter contact (E) → every open job there gets it; Nobody found (N) → tier 3; Skip →
  hidden until tomorrow. At the cap: "next lookups tomorrow", entering results still works.
- **Import CSV:** several files at once; per-file mapping (auto-detected), row counts, "already imported"/"same
  content as another file" (SHA-256) flags. Imports run one file after another in the background (batches of 500,
  progress bar), after a DB backup (once per 15 min). Dedupe: same email (case-folded) → fill empty fields only;
  else same company (normalized) + folded name → fill; else create. Unknown companies are created. Then matching runs.
- **Merges:** suggested duplicates (one name is the other plus a country/legal/group word, or the same website),
  confirmed one by one: Keep A / Keep B / Different companies. Never automatic. Merging moves jobs, contacts and the
  lookup, records the other spelling as an alias (future jobs and imports map to it) and re-matches.
- **Match report:** open jobs with a contact / waiting on a lookup / no contact, by track and by country, plus
  "Run matching now".
- *Empty:* each tab explains the next step, with "See how it works".

### 3.8 Experience (`/experience`)
*Purpose:* maintain the master experience, which is the source for all CVs and scoring.
- Grouped by kind (Work, Projects, Volunteering & leadership, Skills, Education, Certifications; volunteering matters most for juniors with little paid experience) with a count per group. Tag filter chips appear at the top.
- Each item row shows the title, org, dates, tags, and bullet count. Rows can be dragged to reorder within a group (with ↑/↓ buttons as a keyboard-accessible alternative), and an active toggle is available.
- **Add / Edit** opens a side sheet with fields matching the kind: title, org, location, dates (with a "present" toggle), summary, bullets (add/remove/reorder), and tags (token input).
- Delete offers Undo in the toast.
- *Empty:* "Add your experience. Every tailored CV is built from it", with "Add first item".

### 3.9 Settings (`/settings`)
Sections in a left sub-nav:
- **Search profile:** roles, keywords, excluded keywords, countries (searchable picker over every country the location parser knows, grouped Europe / Middle East & North Africa / Other), remote policy, remote scope (remote anywhere = worldwide or EMEA / remote Europe / remote in target countries only; US-only remote is never eligible), and min fit score.
- **Company job boards** (a source): an editable list of employers (platform: Greenhouse, Lever, Ashby, Workable or SmartRecruiters, plus the board token and a display name), each with its job count or error from the last run. A board answering with 0 jobs is flagged ("check the token").
- **Bayt** (a source): Gulf/MENA board read from its public per-country search pages; summaries only, the full listing is fetched per job.
- **CV:** download filename pattern (`{full_name}_CV_{company}.pdf`), and per-track emphasis (skill groups and tags each track's CV leads with).
- **Templates:** style-only CV templates. List, sample preview, set default, add (`.tex.j2` + config) with a validation report; only templates that compile to one page with sample data can be used.
- **Candidate:** the CV header (full name, location, phone, email, links with type/label/URL); empty fields are left out of the CV.
- **Sources** list the target countries each source can't search ("Not supported by this source: Portugal, …"; Adzuna has no endpoint for them).
- **Sources:** a toggle per source, with a note that LinkedIn is not automated. Also the last run status per source.
- **Schedule:** discovery time of day (APScheduler, local time).
- **Contacts:** the role-ranking groups (label + keywords, reorderable; saving re-ranks every contact and re-matches
  open jobs) and the daily Apollo lookup cap.
- **Tracking:** follow-up days (e.g. 7, 14) and the ghosting suggestion delay (30 days). Applies immediately (reminders are computed).
- **Candidate** also has "Total years of experience (override)": used instead of the role-date total in CV facts and checks; never makes scores stale.
- **Models:** scoring provider/model (Ollama, model name), CV generation (Claude, model name), and email drafting.
- **Email (SMTP):** Gmail address, from name, and send interval / cap (read-only defaults). The app password is set in `.env` and shown as "configured / not configured".
- **Data:** DB path, plus "Reset demo data" and "Start with an empty workspace" (dev only, with a confirmation dialog).
- Each section saves independently, with a toast.

## 4. Discovery (Phase 1)

- **Sources**, each behind the `JobSource` interface:
  - **Adzuna:** official API with free keys; ES/FR/IT only (no PT endpoint); ~12 requests/run.
  - **Remotive:** public API; one request/run, with a 6h cooldown (their guidance is ≤ 4/day); link back and attribution.
  - **Arbeitnow:** public feed, newest pages, mostly DACH listings.
  - **Welcome to the Jungle:** the public Algolia search key the site itself uses; one multi-query request/run; unofficial.
- **Pipeline per source:**
  1. Fetch with a polite client (timeouts, retries with backoff, Retry-After, per-source spacing, User-Agent).
  2. Normalize: HTML becomes clean text, and country and remote type are detected.
  3. **Pre-filter** by the search profile: role match against your **tracks** (each role title and its FR/ES/DE/IT/NL variants; the matched track/role is recorded on the job), title exclude keywords, target countries or compatible remote region, remote policy, max age. Every drop has a reason code.
  4. **Ingest** additively: a job seen again only gets `last_seen_at` updated (content, score, label, stage and notes never change); cross-source duplicates are flagged via a normalized dedupe key; new jobs get an application. After every run (manual or scheduled) only jobs that have **never been scored** enter the scoring queue.
- **Runs:**
  - One at a time (409 otherwise), in the background.
  - One failing source never breaks the others.
  - A daily APScheduler run (Settings → Schedule) plus the manual button.
- **UI:**
  - A Discover progress strip while running, and a summary toast at the end ("34 fetched · 12 new · 9 filtered · 3 duplicates").
  - Settings → Sources: status, counts, full errors, config hints, **Test source** (a dry run), and a filter report.
  - A Today banner when an enabled source failed or isn't configured.
  - Listing links name their source ("Open on Remotive").

## 5. Fit scoring (Phase 2)

- **Model:** Ollama Cloud first (`gemma4:31b-cloud`), local fallback (`gemma4:12b`), both in Settings → Models. Local models use native structured output; cloud models get the schema in the prompt plus validation (one corrective retry). It never falls back to a default number. A missing model or an Ollama that's down pauses the queue with one clear message and the `ollama pull` command.
- **Tracks:** role_match and seniority are judged against the track the job matched and your years in that track (prompt v3), so 2+ years of Flutter counts fully for Mobile roles.
- **The LLM returns** five 0–10 sub-scores, each with a reason and a verbatim evidence quote:
  - role_match
  - skills_match (against your experience items)
  - seniority_fit
  - location_eligibility (work authorization, "must be based in"; you're in Tunisia and need sponsorship)
  - language_requirements (against Settings → Candidate languages)

  It also answers an explicit yes/no **flag check** per disqualifier type (turned into red flags in code), ≤3 strengths, ≤3 gaps and a one-sentence summary.
- **The code computes the 0–100 score** from weights (Settings → Scoring). Verified, disqualifying red flags cap it (default 35): work authorization / no sponsorship / must be based in (when the candidate needs sponsorship), nationality-restricted roles ("UAE nationals only", Emiratization/Qatarization/Kuwaitization…; unless it's the candidate's nationality), and a required language the candidate doesn't speak at a working level (B2+ or Professional working; "Dutch or French" is met by either). A flag whose quote isn't in the listing can never be hard. Quotes are checked against the listing text and marked "unverified" when not found.
- **Confidence:** high (full listing), medium (summary, e.g. WTTJ search index) or low (snippet), downgraded when the text is short. For non-high confidence: **Fetch full listing** (one job, our honest User-Agent, JSON-LD `JobPosting`). If a site blocks automated access, **Paste description** is offered instead.
- **Cache and staleness:** cache key = content + experience version + model + prompt version, so nothing is rescored unless something changed. Experience or candidate edits mark scores **stale**, and "Rescore stale" is a user action. Weight, cap and work-authorization changes recompute scores instantly from stored sub-scores, with no model calls.
- **Queue:** persistent (resumes after a restart), runs in the background after discovery, shows progress, model, parallelism and an ETA in Discover, and can be cancelled.
  - "Too many concurrent requests" (429) is never a failure: the same job goes back to the front, new calls pause with backoff + jitter, and parallelism drops by one (min/max in Settings); it climbs back after a streak of successes.
  - A cloud **usage limit** switches the rest of the run to the local model, with a notice in Discover and on Today; the next run tries cloud again.
  - Other errors: up to 3 attempts, then failed; failed jobs get one more try at the end of the run.
- **Rescoring existing scores** only on explicit action: per-job Rescore, or "Rescore all / stale" behind a confirm dialog (count, model, estimated time).
- **Labels and eval:** Good / Maybe / No per job (keys 1/2/3), separate from the pipeline stage. `make eval` scores the labeled jobs and reports bucket accuracy, a confusion matrix, Spearman correlation, per-label means, the worst disagreements with the model's reasons, and timing. Reports are saved per model and prompt version under `data/eval/`.
- **Prompt:** `backend/app/prompts/fit_score.md`, versioned. A test fails if the body changes without a version bump.

## 6. Sample data and guided tours

- The real workspace **never contains fake data**. A fresh install shows real empty states and an onboarding card.
- **Guided tours, one per feature** (Today, Discover, Pipeline, Applications, Job detail, CV Studio, Outreach, Contacts, Experience, Settings), start from the **?** menu, the ⌘K palette, or an empty state's "See how it works".
- A tour rebuilds the sandbox, switches the app to it (a persistent "Tour · Sample data" strip), spotlights 3–6 elements with a short explanation (→ / ← / Esc), and returns to the real workspace on exit. Anything clicked during a tour only changes the sandbox.

## 7. Phase 0 scope

Built: every screen above, clickable, backed by real FastAPI endpoints over a seeded SQLite DB,
with mutations that persist (shortlist, dismiss, stage moves, notes, experience CRUD and reorder, CV edit,
regenerate, and approve, draft edit, approve, and reject, queue pause/resume, and settings).

Mocked: discovery (the "Run discovery" button inserts fixture jobs via the `MockJobSource`), fit scoring,
CV generation, PDF rendering (preview placeholder), email drafting, sending (nothing leaves the machine),
Apollo CSV import (mock preview), and Apollo lookup.

Not in phase 0: real API clients, Ollama/Claude calls, LaTeX compile, SMTP, and scheduler jobs.
