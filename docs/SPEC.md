# Job Hunter v2: product spec

A local, single-user workspace for my Data Engineering / AI Engineering job search, targeting Spain,
Portugal, France, Italy, or remote. The app finds jobs, scores fit, prepares a tailored CV and
outreach, and keeps me in control. **Nothing is final or sent without my review.**

## 1. The flow

| # | Step | What happens | Where in the UI |
|---|---|---|---|
| 1 | **Discover** | A daily scheduled pull from Adzuna, Remotive, Arbeitnow, and Welcome to the Jungle, filtered by the active search profile. LinkedIn is excluded from automation | Discover, Today, Settings → Sources |
| 2 | **Score fit** | An LLM (Ollama, local) scores each job 0–100 against the master experience, with strengths and gaps | Fit badge everywhere, fit panel |
| 3 | **Dedupe** | The same job from 2 sources is flagged as a duplicate. Companies already contacted or applied to are flagged | Discover flags, Job detail |
| 4 | **Resolve contact** | Tier (a) is the imported Apollo dump. Tier (b) queues a manual Apollo extension lookup, with a small daily cap. Tier (c) is no contact | Contact block, Contacts |
| 5 | **Tailored CV** | Generated per job (Claude) from the master experience into ONE universal LaTeX template, then compiled to PDF. Always exactly one full page | CV Studio |
| 6 | **Route** | With a contact, the route is **cold email** (a draft is generated). Without one, it is **web apply** (I get the CV and the listing link, and apply myself) | Job detail, Pipeline |
| 7 | **Human review** | I review and edit every CV and every email | CV Studio, Outreach → Review |
| 8 | **Send / track** | Queued Gmail SMTP: 15 min between sends, max 20 per queue, pause/resume. Web-apply jobs are tracked when I mark them applied | Outreach → Queue, Pipeline |

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
| `Esc` | Close panel / dialog | Everywhere |
| `/` | Focus page search or filter | Everywhere |
| `⌘K` | Command palette | Everywhere |
| `g` then `t d p o c e s` | Go to Today, Discover, Pipeline, Outreach, Contacts, Experience, Settings | Everywhere |
| `?` | Shortcut help | Everywhere |

Shortcuts are ignored while focus is in an input, textarea, or contenteditable.

- **States:** every data view implements *loading* (a skeleton matching the layout), *empty* (an explanation plus one clear next action), *error* (a message plus **Retry**), and *populated*. Dev aids: `MOCK_LATENCY_MS` on the backend simulates slow responses.
- **No dead ends:** every detail screen links to the next step of the flow and back to its list.

## 3. Screens

### 3.1 Today (`/`)
*Purpose:* the "what needs me now" inbox. It is the landing page.
- A greeting with the date and a one-line summary ("4 things need you").
- **Attention cards**, each with a count, the top 3 items, and a "View all" deep link:
  - *New high-fit jobs:* stage `new` with fit ≥ the profile's min score → Discover filtered to `new` and sorted by fit.
  - *CVs to review:* the latest CV version in `draft` → CV Studio.
  - *Drafts to approve:* outreach drafts in `draft` → Outreach Review.
  - *Ready to apply manually:* stage `ready` with route `web_apply` → the Job page (shows the "Open listing" and "Download CV" actions and a "Mark applied" button).
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
- The **Closed** column hides dismissed jobs unless "Show dismissed" is on. Dropping a card on Closed asks for a reason (rejected, no response, withdrew, offer, not a fit).
- **Table view** (`?view=table`): sortable columns (Job, Company, Stage, Route, Fit, Contact, Updated), j/k selection, s/d shortcuts, and Enter to open.
- *Empty:* "Nothing in your pipeline yet. Shortlist jobs from Discover", with a "Go to Discover" action. *Loading:* column skeletons. *Error:* retry.

### 3.4 Job detail (`/jobs/:id`)
*Purpose:* everything about one opportunity in one place.
- **Header:** title, company, location/remote, source, and posted date. There is a stage selector (only allowed transitions are offered), a route toggle (cold email / web apply), and the primary next-step action, which depends on stage:
  new → Shortlist · shortlisted → Generate CV · cv_ready → Draft email *or* Mark ready to apply · ready (email) → Approve & queue · ready (web) → Mark applied · done → Log interview.
- **Main column:** Listing (description, Open original ↗), Fit breakdown, CV versions (list with status + "Open in CV Studio"), Email draft (preview + "Edit in Outreach"), Notes (autosaving textarea).
- **Right column:** Contact (tier, person, email, "Queue Apollo lookup" when tier is none), Company (contacted flag, other jobs at this company), and the Timeline (stage changes and events, newest first).
- *Not found:* "This job doesn't exist or was removed", with "Back to Discover".

### 3.5 CV Studio (`/jobs/:id/cv`)
*Purpose:* review and edit the tailored CV for one job.
- **Left:** a structured editor with sections for Headline, Summary, Experience (entries → bullets; add, remove, reorder), Projects, Skills (groups → items), and Education. Edits autosave to the current draft version.
- **Right:** PDF preview at A4 aspect ratio (a placeholder in phase 0 that renders the structured content as a paper-like mock), with a page-fit indicator ("1 page ✓").
- **Toolbar:** version switcher (v1, v2… with status), **Regenerate** (creates a new draft version from the mock generator), **Approve** (marks it approved, supersedes the others, moves the application to `cv_ready`, and toasts a next step: "Draft email" or "Mark ready to apply").
- *Empty (no CV yet):* "No CV for this job yet", with a "Generate CV" action.

### 3.6 Outreach (`/outreach`)
- **Review tab:** a list of drafts (filter: To review | Approved | Rejected) on the left. The editor on the right has To (contact), Subject, Body, the linked job and CV, and **Approve** (primary), Reject, and Regenerate. Keys: j/k, a, r.
- **Queue tab:** a status header (Running / Paused / Idle, next send countdown, "15 min between sends · max 20 per queue"), with Pause/Resume. The items table shows position, recipient, company, subject, scheduled time, and status. Pending items can be removed from the queue.
- *Empty review:* "No drafts waiting. Drafts appear after you approve a CV for a job with a contact." *Empty queue:* "Queue is empty. Approved drafts land here."

### 3.7 Contacts (`/contacts`)
- **Companies tab:** a searchable company list with contact count, contacted flag, and open-jobs count. Selecting a company shows its contacts (name, title, email, source tier badge, LinkedIn).
- **Import tab:** Apollo CSV import in 3 steps: (1) dropzone / file picker (plus "Try a sample file"), (2) column mapping with auto-detected fields and the first 5 rows, (3) summary (new / updated / skipped). In phase 0 the preview parses the real file, but the import itself is a mock that writes nothing.
- **Lookup queue** (section): jobs with `lookup_queued` and the daily cap indicator (e.g. 3/10 today).
- *Empty:* "No contacts yet. Import your Apollo export to resolve contacts automatically", with "Import CSV".

### 3.8 Experience (`/experience`)
*Purpose:* maintain the master experience, which is the source for all CVs and scoring.
- Grouped by kind (Work, Projects, Skills, Education, Certifications) with a count per group. Tag filter chips appear at the top.
- Each item row shows the title, org, dates, tags, and bullet count. Rows can be dragged to reorder within a group (with ↑/↓ buttons as a keyboard-accessible alternative), and an active toggle is available.
- **Add / Edit** opens a side sheet with fields matching the kind: title, org, location, dates (with a "present" toggle), summary, bullets (add/remove/reorder), and tags (token input).
- Delete offers Undo in the toast.
- *Empty:* "Add your experience. Every tailored CV is built from it", with "Add first item".

### 3.9 Settings (`/settings`)
Sections in a left sub-nav:
- **Search profile:** roles, keywords, excluded keywords, countries, remote policy, and min fit score.
- **Sources:** a toggle per source, with a note that LinkedIn is not automated. Also the last run status per source.
- **Schedule:** discovery time of day (APScheduler, local time).
- **Models:** scoring provider/model (Ollama, model name), CV generation (Claude, model name), and email drafting.
- **Email (SMTP):** Gmail address, from name, and send interval / cap (read-only defaults). The app password is set in `.env` and shown as "configured / not configured".
- **Data:** DB path, plus "Reset demo data" and "Start with an empty workspace" (dev only, with a confirmation dialog).
- Each section saves independently, with a toast.

## 4. Phase 0 scope

Built: every screen above, clickable, backed by real FastAPI endpoints over a seeded SQLite DB,
with mutations that persist (shortlist, dismiss, stage moves, notes, experience CRUD and reorder, CV edit,
regenerate, and approve, draft edit, approve, and reject, queue pause/resume, and settings).

Mocked: discovery (the "Run discovery" button inserts fixture jobs via the `MockJobSource`), fit scoring,
CV generation, PDF rendering (preview placeholder), email drafting, sending (nothing leaves the machine),
Apollo CSV import (mock preview), and Apollo lookup.

Not in phase 0: real API clients, Ollama/Claude calls, LaTeX compile, SMTP, and scheduler jobs.
