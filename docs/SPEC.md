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
| 4 | **Get contact** | The best-ranked imported contact is verified first (still there?); with nobody, you find someone with the Apollo extension (guided, one job at a time). Drafting and research wait for a verified contact | Outreach → Contacts to get, job Outreach step |
| 5 | **Tailored CV** | Generated per job (Claude headless, structured JSON) from the experience pool into a style-only LaTeX template (docs/CV_TEMPLATES.md), fitted in code to exactly one full page | CV Studio |
| 6 | **Both routes** | Every job can have a **web application** (CV, optional cover letter as PDF and/or form text, grounded answers to the form's questions, the listing link; I apply myself) **and** a **cold email** to someone there (contact → draft → review → send queue → sent). Each track shows its own status everywhere; with no contact yet, the app says who to look for and gives search hints | Job detail, Pipeline, Today, Cover letter studio |
| 7 | **Human review** | I review and edit every CV, email, cover letter and answer | CV Studio, Job page, Outreach → Review, Cover letter studio |
| 8 | **Send / track** | Queued Gmail SMTP: 15 min between sends, max 20 per queue, pause/resume. Web-apply jobs: open the listing + approved CV (+ approved cover letter) in one click, then Mark applied (date, method, CV and letter versions locked) | Outreach → Queue, Applications |
| 9 | **Follow up** | Follow-up reminders (7/14 days, configurable), replies and interview rounds logged, closed with an outcome; stats and CSV export. No model calls | Today, Applications |

Pipeline stages: **New → Shortlisted → CV ready → Ready → Applied / Emailed → Interview → Closed**. The stage is
the job's overall position; the two tracks (Application: CV first → Ready to apply → Applied; Outreach: No contact →
Contact found → Draft to review → Approved → Queued → Sent) carry the details. `done` is reached with the first route
("Applied", "Emailed", then "Applied + emailed") and never goes back; the other route can still finish later.
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
  - *Cold emails:* drafts to review, approved emails not in the send queue yet (inline "Add to queue"), and the queue status.
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
- Dropping on **Applied / emailed** opens Mark applied while the web application is still to do; otherwise (and
  on **Ready**) it opens the Job page's Outreach card (`#outreach`).
- Cards show both **track badges** (e.g. "Ready to apply" · "Draft to review"); the table has Application and Email
  columns.
- **Table view** (`?view=table`): sortable columns (Job, Company, Stage, Route, Fit, Contact, Updated), j/k selection, s/d shortcuts, and Enter to open.
- *Empty:* "Nothing in your pipeline yet. Shortlist jobs from Discover", with a "Go to Discover" action. *Loading:* column skeletons. *Error:* retry.

### 3.4 Job detail (`/jobs/:id`)
*Purpose:* everything about one opportunity in one place.
- **Header:** title, company, location/remote, source, and posted date. There is a stage selector (only allowed
  transitions are offered), a **Copilot** button (key `c`), and the primary next-step action: new → Shortlist ·
  shortlisted → Generate CV · web application still to do → Mark applied · otherwise the email's next step (Find a
  contact / Draft email / Review email / Add to send queue) · done → Log interview · interview → Record outcome.
- **Two tiles** at the top, Application and Outreach, each with its status and next step; they scroll to their
  sections.
- **Application** section: open the listing + approved CV (+ approved PDF letter) in one click, Download CV only,
  Mark applied; once applied, the date and method.
- **Outreach** section: a stepper Get contact → Draft → Review → Send queue → Sent with the next action always visible: the Get contact panel (see §3.6), "Draft email with AI" (needs an approved CV), the draft editor inline (checks, sources, test send, Regenerate, Reject, **Approve**), then **Add to send queue** (shows "#2 in the queue · sends around 14:30"), then the sent date. "I sent it myself" records the approved email as sent (date; CV locked).
  - **Who to contact** (no contact yet, `contacts.who_to_contact`): the roles to look for by company size (small:
    Settings → Contacts' small-company order, e.g. CTO or founder; large or unknown: the head of the hiring team or
    the engineering manager, then talent acquisition), the reason, and copyable search hints (a LinkedIn query and
    its URL, Apollo filters). "I found someone" adds the contact; the draft comes next. Nothing is searched or opened.
  - Once the web application is recorded, the draft editor offers **"Mention my web application"** (on by default
    for new drafts): a fixed sentence from Settings → Email, e.g. "I have also applied through your careers page on
    30 September.", never model-written, counted in the length check.
  - The review line says how the draft was made: "Drafted by claude-sonnet-5 via claude -p · subscription".
- **Cover letter**: versions with status, language and word count, and the way into the Cover letter studio.
- **Application questions** (approved CV): paste the form's questions with optional character limits; "Answer with AI" answers the batch in one Claude call (grounded like the letter, in its language). A limit is a hard check: over it → one retry → still over → kept with "412/300 characters" (never cut). Answers are saved on the job, editable (re-checked), with Copy and an undoable delete.
- Once applied, an **Application** section: applied on, method, CV sent (locked version, download), notes, replies, interview rounds (outcome editable), with Log reply / Log interview / Close…. CV versions sent show a "Sent" badge.
- **Main column:** Listing (description, Open original ↗), Fit breakdown, CV versions (list with status + "Open in CV Studio"), Email draft (preview + "Edit in Outreach"), Notes (autosaving textarea).
- **Right column:** Contact (Get contact state: Get contact / Verify first / Verified / Never looked up, person, email, "Get contact" when nobody), Company (contacted flag, other jobs at this company), and the Timeline (stage changes and events, newest first).
- *Not found:* "This job doesn't exist or was removed", with "Back to Discover".

### 3.4b Applications (`/applications`)
*Purpose:* everything after the CV. Nothing here calls a model. Tabs in the URL (`?tab=ready|applied|stats`).
- **Ready to apply:** approved CV + no contact, not applied (`cv_ready`/`ready`, web apply). Rows: job, company, track,
  country, approved CV version, cover letter version. **Open listing + CV** (+ **cover letter** once approved; one
  click) or "Write / Review cover letter", and **Mark applied** (dialog: date default today, method, the CV version
  and the cover letter, checked when one is approved, that get locked; notes). Keys: j/k, `o`, `a`.
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

- **Fit before/after** (on approval, in the background): the job scored against this CV by the same gemma scorer
  (one call, stored in `cv_fit`, never as the job's fit) next to the job's own fit, plus the lexical evidence
  check (`services/fit_lexical.py`, no model): requirements shown on the first screen before → after, backed
  strengths the CV left out, claims your experience doesn't back, the years note.
- **Critique** (CV, letters, emails, LinkedIn messages): one `claude -p` call listing what's still weak from the
  reader's side; never a rewrite (`app/prompts/critique.md`).

### 3.5b Cover letter studio (`/jobs/:id/letter`)
*Purpose:* a cover letter for a web application, from the approved CV, in two formats (tabs, `?format=form`):
**PDF letter** (one page, to upload) and **Form text** (plain text for a text box such as "Expliquez-nous pourquoi
vous souhaitez nous rejoindre": paste the question and the box's character limit; it answers directly, with no
header, date, subject line, salutation or closing formula; live character count, Copy). Each format has its own
versions; Mark applied can record either (both locked).
- **Writing guide v4** (checked in code): never restate the listing (at most one listing sentence, in the opening,
  not copying it); don't copy or translate CV bullets and no CV jargon (Settings list: "schema drift", "N/N tests",
  "collision classes"…); use the current role when it matches (tags, or a title word that's a theme of the role,
  e.g. "Backend"); at most 2 examples of 1-2 sentences; the ask is its own short last paragraph; a fit sentence
  only from Settings → Candidate (where you're based, work authorization, languages; relocation isn't claimed).
  PDF 150-260 words, form text 80-220 words or its character limit.
- **Generate / Regenerate:** one Claude call (`providers/claude_letter.py`, prompt `app/prompts/cover_letter.md`,
  same isolation and subscription check as the CV). Input: the listing, the approved CV's items, the years facts
  (exact statement, and its French wording), the language, the writing guide and banned phrases. Output: 3-4
  paragraphs of cited sentences (or sentences marked as about the listing) and one closing ask.
- **Language:** the listing's (a stop-word vote, `services/text.detect_language`), or Settings → Cover letter, or
  the job's own choice in the studio ("Language of the next letter").
- **Code adds** the CV template's header, the place and date in the letter's language ("Tunis, le 30 septembre
  2026"), the company (and "À l'attention de" a contact), the subject line ("Objet : candidature au poste de …" /
  "Application for the … position"), the salutation, the closing formula and the signature (Settings).
- **Checks** (`services/letter_check.py`): grounding as for emails; word range (default 250-350); 3-4 paragraphs;
  the opening names the company and says something from the listing; 2-3 concrete builds (warning); exactly one
  ask, at the end; per-language banned phrases; only the exact years wording (English or French, with the short
  form beside "software engineer" / "ingénieur logiciel"); one page. One retry with the problems, then kept with
  the problems listed. Errors block approval.
- **Editing:** salutation, each paragraph and the ask, autosaved (700ms) and re-checked; an edited paragraph is
  checked at text level (numbers and tools must be in your experience or the listing); the PDF re-renders with no
  Claude call. Editing an approved letter sends it back to review; a sent (locked) letter is never changed: edits
  create a new draft.
- **Toolbar:** format tabs, versions, Regenerate, **Copy as text** (salutation, paragraphs, closing, name, for web forms),
  Download (`{full_name}_Cover_Letter_{company}.pdf`), **Approve**.
- *Empty:* "No cover letter for this job yet" with Write cover letter (or Open CV Studio without an approved CV).

### 3.5c Studio (`/studio`)
*Purpose:* every CV version and cover letter (PDF and form text) across jobs in one list. Tabs by type (with counts),
a status filter (draft / approved / sent = locked / superseded) and a job or company search, all in the URL. Rows
show the version, the detail (pages and fill, words, "791/1000 characters"), problems to fix and when it changed.
j/k and Enter open the CV studio or the letter studio (form tab for form texts). `GET /studio/documents`.

### 3.5d Copilot (`/copilot` and the Job page)
*Purpose:* ask anything about a job or your search: interview prep, CV gaps, a LinkedIn message, a translation.
- The local model (Settings → Models `models.copilot.model`, default gemma4:12b via Ollama), streamed. It only
  answers: no tools, no write path. Prompt `app/prompts/copilot.md` (versioned).
- **Job Copilot** (a right sheet from the Job page, key `c`): context = the listing, fit score and reasons, the
  approved CV, the latest cover letter, both tracks, your profile and experience pool; one conversation per job,
  saved ("New conversation" keeps the old one).
- **Global Copilot** (`/copilot`, sidebar): conversations with your profile and pool as context.
- Under each answer: warnings for numbers or tools in neither your experience nor the listing, method claims your
  experience doesn't mention (MVC, microservices…), clichés the letters ban, and years wording other than yours.
  Copy per answer. If Ollama isn't running, an error state with retry.

### 3.6 Outreach (`/outreach`)
*Purpose:* one cold email per job, reviewed by you, sent through your Gmail. No bulk drafting.
- **Get contact (Phase 9, `services/get_contact.py`)** is the first step of every job's Outreach track. Contacts are
  found by hand with the Apollo Chrome extension (no Apollo API on the free plan). Per job:
  - **get** (nobody yet): *Who to look for*: the roles for this company by the ranking rule (size aware) with the
    reason; one-click links (LinkedIn people search for those roles, the company's LinkedIn page, its website); the
    steps (profile → extension → reveal the email → paste); a quick form (name, title, email, LinkedIn) with a paste
    box that fills the fields from a block copied from the extension or LinkedIn (`services/contact_paste.py`,
    `POST /contacts/parse`, nothing saved until you do; a company that doesn't match is flagged); contacts already
    known at the company, one click to use; Nobody found (N) / Never look up (X), each with Undo. A new entry counts
    as verified.
  - **verify** (a contact exists, e.g. from a CSV): *Verify first*: the contact, where and when it came from
    ("wissem-list.csv, imported 28 Sep 2026", from `imported_batch` → `contact_import`), a LinkedIn link (their
    profile or a name search), the automatic "may have left" result, and **Still there, verified** (V; dismisses the
    alerts) / **Left or wrong person** (L; never picked again, every job written to them moves to the next contact
    by the ranking, or back to get) / **Edit details** (E; a new email counts as a new entry).
  - A verification lasts `verify_days` (30, Settings → Contacts); older than that it must be verified again.
  - **Drafting, and so research, are refused until the contact is verified** (`get_contact.require_ready`, in
    `outreach.generate*` before research; `approve_draft` re-checks: 409).
- **Contacts to get** (Outreach tab `?tab=contacts&app=`; also a card on Today with the top 5): every job past New
  (shortlisted, cv_ready, ready, done) whose email isn't queued or sent and whose contact is missing or unverified,
  best fit first, "nobody found" last, never-look-up companies left out. One job at a time: the list (j/k) beside the
  panel; ⌘↵ saves and moves on; V / L / E / P (paste box) / N / X. A daily counter "4 / 10 found today" (contacts you
  entered today against Settings → Contacts' Apollo extension daily limit) warns from 80%; it never blocks.
- **Try Hunter** (`providers/hunter.py`, `HUNTER_API_KEY` in `.env`): a button only, never automatic. It shows the
  searches left this month (reading them is free) before each use; finding an email costs 1 search and fills the
  form (you confirm; saved with source hunter), "Verify with Hunter" checks an email that looks wrong (1
  verification). Paid calls are never retried. Without a key the button says so.
- **The email is a personal introduction, not a reply to the listing** (prompt `outreach.md` v9). The listing
  is private intel: it decides what to talk about and is never mentioned. Four parts, assembled by code:
  0. **greeting**: built by code in the email's language ("Hi …," / "Bonjour …,"). The first name is spelled
     as the company's researched pages write the contact's full name (Stéphane vs Apollo's Stephane), otherwise
     as the contact record has it; the editor says which page it came from;
  1. **hook**: how you came across the company (its field, never a job board) + 1-2 facts from its selected,
     verified signals (cited by id), each kept as its own fact: never linked by cause or merged;
  2. **intro**: built by code from Settings → Candidate ("I'm <first name>, a software engineer with 3 years of
     experience in …" / "Je suis …, ingénieur logiciel avec 3 ans d'expérience, sur …");
     the model only picks the areas;
  3. **value**: their problem in one sentence, framed as the kind of problem you like working on (first person,
     varied wording; never a general truth like "… reste un vrai défi"), then 1-2 short proofs from your pool;
  4. **ask**: a direct question about an opening.
  100-150 words, language of the listing.
- **The draft step** (`outreach.generate_intro`, background, polled): research the company first
  (`services/research.py`; fresh signals are reused: no fetch, no model call), then Claude Code headless writes
  the draft (`providers/claude_email.py`, subscription check). Phases shown in the Outreach card: Fetching pages →
  Extracting signals → Drafting. Started by "Draft email with AI" / Regenerate, the CV Studio "Draft email" action,
  or dropping a Pipeline card on Ready. Needs an approved CV and a contact with an email.
- **Company research** runs ONLY at the draft step or with Research now / Refresh signals (Job page and company
  panel): never on discovery, scoring, shortlisting, matching, CV generation or in bulk
  (`tests/test_research_guard.py`). It reads the company's site (domain from the contact's work email, or the
  website you set; robots.txt respected; sitemap + links: about, product, customers/case studies, news, careers;
  at most 8 pages) and recent news (GDELT, Google News RSS; free, no key). gemma4:31b-cloud (12b fallback, the
  scoring 429/quota policy) extracts signals; each keeps its exact quote, verified in code in the fetched page
  (numbers included), or it's dropped. Signals are cached per company for 30 days (Settings → Email → Company
  research) and only a run that kept signals counts as fresh. Each run logs its model calls (model, duration,
  tokens).
- **Signals panel** (Job page, company panel): the verified signals with their quote, source link, page date and
  fetch date; tick the ones emails may use (up to 3 are picked automatically, mixing kinds), dismiss, add your
  own, set the website, Research now / Refresh signals, and the last run's cost. Without a selected signal the
  draft is marked **Needs a signal** and can't be approved.
- **Checks** (`services/intro_check.py`, plus the CV grounding rules for facts about you): never the listing,
  "the role", the position posted or the job title; never your location, country, nationality, visa or work
  authorization; no "Re:"/reply-style or role subjects; no hook or problem that restates the listing (7+ words in
  a row, or overlap); 1-2 proofs of at most 35 words; at most 3 tool names in a sentence; the hook cites a
  selected signal and its numbers and names are in it; the intro line intact; a final question about an opening;
  100-150 words; banned phrases, CV jargon and years wording; not too close to the reference examples (≥ 25%
  shared or 8+ words in a row, the code-built intro excluded) or to drafts to other people. One retry, then the
  draft is kept with its problems listed. Errors block approval. Edits are re-checked (text-level).
- **Hook check** (`services/hook_check.py`, prompt `hook_check.md`): gemma4:31b-cloud (12b fallback, same error
  policy as research) splits the hook into claims and judges each against the cited signals: stated, causal,
  combined or not stated. Anything but "stated" is an error ("sovereign models enabled the 37%"). It runs on
  each draft attempt, and on Approve when you edited the hook since the last check (then against every selected
  signal). The editor shows the result and its cost; if the model can't be reached it's a warning.
- **Contact still there?** (`services/contact_check.py`, no model call): each research run also searches the
  news for every contact's name with the company name (Google News RSS, GDELT; skipped for a name with only an
  initial), stores what it finds as `contact_news` pages, then scans every stored page and news item. A sentence
  naming the contact with a departure word (révoqué, quitte, ancien PDG, stepped down, former CEO…) or announcing
  someone new in their role (a new CEO named) raises a red **"<name> may have left <company>"** warning with the
  excerpt, source and date: on the job page's Contact card (the email editor there shows a one-line pointer) and
  in the Outreach review editor. While it's active the email can't be approved (API 409 too). It offers the next
  contact by the ranking rule (best-ranked, with an email, not flagged; one click), "I've verified them"
  (dismiss, 8s Undo; found again, it stays dismissed) and "Check again" (`POST /contacts/{id}/check`). A cached
  research reuse only rescans the stored pages. Tour: "Contact still there?".
- **Value framing and greeting checks**: a problem sentence without first person, or any "is hard / remains a
  challenge / reste un vrai défi / est difficile" phrase, is an error; so is a greeting not in the email's
  language. The example-similarity check ignores wording both texts take from the same signal.
- **Regression set** (`app/eval/emails.py`): your reference examples (`data/eval/email_examples.json`, imported
  with `make eval-emails ARGS=--import`) and every email you approve or reject (with its inputs). `make
  eval-emails` writes each case again with the current prompt: old vs new side by side in `data/eval/emails/`. A
  prompt change is adopted only once its report is recorded in `app/prompts/eval_log.json` (a test checks it).
- Older reply-style drafts (prompt ≤ v3) keep their shape and checks (`services/outreach_check.py`).
- **Review tab:** list (To review | Approved | Rejected | All); editor with the checks panel, subject, your text,
  "Added when sent" (signature + opt-out from Settings → Email; the phone number is off by default, toggle
  "Phone in the signature", and the signature shows your email and LinkedIn), "Where each sentence comes from" (hover for the
  cited CV items), **Approve** (primary; the job becomes Ready to send), then **Add to send queue** on approved
  drafts (a separate step), Send test to me, Regenerate, Reject. Keys: j/k, a, r. The same editor is on the Job page.
- **Send test to me:** the exact email, CV attached, to your own address with "[TEST]" in the subject; no stage
  change. **The queue can't start before one successful test send.**
- **Queue tab:** Running / Paused / Idle, next send countdown, 15 min between sends, max 20 per queue. The worker
  sends one email per interval through Gmail SMTP (`SMTP_APP_PASSWORD` in `.env`), attaching the approved CV and
  locking that version. Failures are shown with Retry; a login/config failure pauses the queue. An email caught
  mid-send by a restart becomes "Check Gmail" (never resent blindly): Retry or "I found it in Sent". Every attempt
  is in `send_log`. A sent email moves the job to **Sent** (`done`, method email) and feeds follow-ups, replies
  and stats (Applications).
- *Empty review:* "No drafts waiting. Drafts appear after you approve a CV for a job with a contact." *Empty queue:* "Queue is empty. Approved drafts land here."

### 3.6b LinkedIn (`/linkedin`, Phase 10)
*Purpose:* LinkedIn as its own channel. **The app never scrapes, crawls or automates LinkedIn**: it builds links,
and reads only the one job page you hand it with the bookmark (a test guards against any backend request to
linkedin.com).
- **Today's searches:** one LinkedIn job search per role × target country, posted in the past 24 hours, newest
  first (`f_TPR=r86400&sortBy=DD`), optionally remote only (`f_WT=2`) and Easy Apply only (`f_AL=true`). Countries
  are LinkedIn **geoIds** (Settings → LinkedIn, each Unverified until you Test and Confirm it), never a text
  location; a country without a geoId shows a warning and no link. A link you open is marked "opened today".
- **One-click import:** the "Save to Job Hunter" bookmark (Settings → LinkedIn) reads the job page you're on
  (JSON-LD JobPosting → LinkedIn's layout → headings → meta tags → the URL), opens the local `/import` window with
  the data in its URL fragment (postMessage as a second channel), and shows every field with how it was found.
  Required fields (title, company, description) are never saved empty; sign-in walls are detected; a paste box is
  the fallback. Saving dedupes against every source, matches the track, saves the hiring-team person, and scores
  only this job (front of the queue, same scorer and rules); the fit shows in the window.
- **To do on LinkedIn** (also a card on Today): searches not opened today, imports to decide on, requests to send,
  follow-ups due, and today's request counter.
- **Per job, the LinkedIn messages track** (job page section, optional): who to message in order (the hiring team
  captured with the bookmark, alumni of your school from your education, team leads in your track's roles,
  recruiters), each with a code-built people search (company-scoped when its slug is known). You add people (paste
  their profile header). Claude (`claude -p`, prompt `linkedin.md`) drafts a connection note within
  `linkedin.note_max_chars` (200 on a free account), different per group; the school angle is for alumni only and
  only on LinkedIn (email rules unchanged). After "accepted", a follow-up: one proof, one direct ask (a referral, or
  who to talk to); company research is reused, or run only at that step. Checks on every message: length, no links,
  a question, banned phrases, grounding of numbers and tools, years, never location/visa. Statuses to contact →
  request sent → accepted → messaged → replied (one-step undo), a daily request counter (a warning), reminders,
  and the gap rule (no email and LinkedIn request to the same person within `linkedin.gap_days`, 3: a hint).
- **Notes written for their reader:** each person's group (the note's angle) is detected from their title
  (`linkedin.detect_group`: recruiter / team lead / other; alumni when ticked) and overridable on the card; the
  captured poster also carries a "Hiring team" badge (`hiring_team`). Recruiters / talent acquisition: plain words
  (a jargon list is an error), the role match, the years wording, 2-3 tools from the listing that you have, an
  easy ask ("Could I send you my CV?"); for a projects-only track (Data/AI) the transition line is built in code
  ("a software engineer (3 years, mobile and backend) moving into data, with dbt and Airflow projects"). Team
  leads: one concrete technical proof, a short chat. Alumni: the shared school, advice or a referral. Approved
  notes go in the regression set (`email_example`, `inputs.channel = linkedin`) as structure and honesty
  references: 8+ words copied from one is an error.
- **Agency jobs** (`services/agency.py`: the company name, or listing phrases that mean recruiting on someone's
  behalf such as "for one of our clients", never a consultancy's client mission): the job shows
  "Agency, employer not named" with the reasons, and LinkedIn suggestions are the hiring team then recruiters
  only (alumni and team leads there would be the agency's own staff). The Email "who to contact" list is the
  recruiter / talent acquisition only, with no head of team or manager (`contacts.who_to_contact`), and the
  automatic contact ranking puts recruiters / talent acquisition first (`Ranking.order_for(company, job)`).
  Your answer always wins: "It's an employer" on the agency notice (job page, LinkedIn panel) and "It's a
  recruiting agency" / "Let the rule decide" on the job page's Company card (`PUT /companies/{id}/agency`, an
  Undo toast, the company's jobs are matched again).
- **Corrected copy of an approved CV** (`POST /cv/{id}/revise-summary`, `cv_service.revise_summary`): a new
  draft with the original's exact document and only the summary written again; the original stays approved
  until you approve the copy.
- **CV approval blocks on errors**, like letters and emails ("Fix N problems first: …", the button is disabled with
  the reason). Problems the checker already fixed (a skill removed, a source fact restored) are warnings.

### Honesty about years (every generated text)
Each track in Settings → Search profile says whether your experience in it is **Professional** or **Projects
only** (with a note: "personal projects, a graduation project, an internship and certifications"). Your years
wording is professional experience: CVs, cover letters, form answers, emails and LinkedIn notes never attach it
to a projects track ("3 years of experience building data pipelines", "experienced data engineer"); that work is
described as what it is, in its own sentence or as a move. `services/honesty.py` flags it (an error in every
checker: `cv_service.summary_style`, `letter_check`, `intro_check`, `linkedin_check`), and the prompts get
`experience_by_track` + `years_rule`.
- **Job page:** three tracks (Application / Email / LinkedIn) and the suggested order (apply → LinkedIn request
  the same day → email 1-2 days later; a hint). "Apply on LinkedIn" for imported jobs; method LinkedIn.

### 3.6c Motivation and the Motiv Center (`/motivation`, Phase 11)
*Purpose:* keep going on hard days. A separate module: it reads job data, writes only its own tables, never changes
or blocks a step, and Settings → Motivation → "Show motivation features" hides all of it.
- **What counts:** a job marked Applied, on the local day you clicked (Africa/Tunis by default; the applied date
  you pick doesn't move it); optionally sent cold emails and sent LinkedIn requests. Undoing "Mark applied" (the
  toast's Undo, `DELETE /applications/{id}/applied`) or moving a LinkedIn request back removes it.
- **Streak:** computed from history every time (never stored). A workday counts at the daily goal (5); a missed
  workday resets to 0 the next day; today is in progress until midnight; Saturday and Sunday add 1 only while a
  streak is running. Top bar: flame + streak + today x/goal, and the token balance. Today: a Streak card
  (current, longest, 8-week calendar) and a Chest card.
- **Chests:** every `chest_goal` (30) applications since the feature started; opening draws 1-10 tokens on the
  server, with a short skippable animation. Extras carry over, several can wait, nothing is taken back, and a
  goal change never re-awards (each chest keeps its cost).
- **Tokens and shop:** a ledger (chest, purchase, …); your own rewards (name, price, emoji or image), edit,
  archive; Buy asks first and never takes the balance below 0; purchases with a "redeemed" checkbox.
- **Motiv Center tabs:** Breathe (cyclic sighing, 1/3/5 min, optional soft tone, Space/Esc), Start (the 5-minute
  rule with a task suggested from your queue, then Keep going 25 min or Done), Plan (WOOP, saved to reread),
  Wins (real numbers, a journal, and a note after a recent rejection), My goals (your images and videos under
  `data/motivation/<workspace>/`, size limit in Settings, captions, reorder, delete with Undo), Shop.

### 3.7 Contacts (`/contacts`)
*Purpose:* who each job is written to. Tabs in the URL (`?tab=companies|import|merges|match`; the old `lookups` tab
redirects to Outreach → Contacts to get).
- **Resolution (`services/contacts.py`):** (1) the best-ranked contact at the job's company, never one marked left or
  wrong person (Settings → Contacts ranking: CTO → VP/Head of Engineering → Head of Data/AI → Engineering Manager →
  Tech Lead → HR/Talent → Founder/CEO; ties: has an email, then most recent); (2) nobody → tier "to get" (the job
  joins Contacts to get once past New); (3) you found nobody, or the company is marked "never look up" (a job board /
  aggregator) → "No contact", web apply.
- **Ranking by company size:** "small" (exact headcount below the threshold, or an "under N" bound at most the
  threshold; default 200, Settings → Contacts) uses CTO → Founder/CEO → Head of Eng → Head of Data → EM → Tech Lead
  → HR; large or unknown size uses HR/Talent → EM → CTO → Head of Eng → Head of Data → Tech Lead → Founder. Both
  orders are editable. Companies from the Apollo lists are "under 200"; set any company's size in its detail pane.
  Runs after every discovery run and import, and on demand. Never replaces a contact you picked, never touches jobs
  applied to or closed, never changes a route (a web-apply job with a new contact offers "Switch to cold email?").
- **Companies:** filters With jobs / Has contacts / Contact to get / No contact, search, j/k. Detail: contacts ranked
  (role group label, "Written to first"), the company's jobs with their tier and a per-job contact picker
  (Automatic or a person), "Add contact".
- **Import CSV:** several files at once; per-file mapping (auto-detected), row counts, "already imported"/"same
  content as another file" (SHA-256) flags. Imports run one file after another in the background (batches of 500,
  progress bar), after a DB backup (once per 15 min). Dedupe: same email (case-folded) → fill empty fields only;
  else same company (normalized) + folded name → fill; else create. Unknown companies are created. Then matching runs.
- **Merges:** suggested duplicates (one name is the other plus a country/legal/group word, or the same website),
  confirmed one by one: Keep A / Keep B / Different companies. Never automatic. Merging moves jobs, contacts and the
  Get contact state, records the other spelling as an alias (future jobs and imports map to it) and re-matches.
- **Match report:** open jobs with a contact / a contact to get / no contact, by track and by country, plus
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
- **Cover letter:** language (the listing's, or always French / English; a job can override it), the writing guide given to Claude, the word range (250-350), and per language the salutation, the closing formula and the banned phrases; the French years wording (empty = derived from the Candidate statement); the download name (`{full_name}_Cover_Letter_{company}.pdf`).
- **Templates:** style-only CV templates. List, sample preview, set default, add (`.tex.j2` + config) with a validation report; only templates that compile to one page with sample data can be used.
- **Candidate:** the CV header (full name, location, phone, email, links with type/label/URL); empty fields are left out of the CV.
- **Sources** list the target countries each source can't search ("Not supported by this source: Portugal, …"; Adzuna has no endpoint for them).
- **Sources:** a toggle per source, with a note that LinkedIn is not automated. Also the last run status per source.
- **Schedule:** discovery time of day (APScheduler, local time).
- **Contacts:** the role-ranking groups (label + keywords, reorderable; saving re-ranks every contact and re-matches
  open jobs) and the Apollo extension daily limit and how long a verification lasts.
- **Cover letter** also holds the form-text word range and the CV-jargon list.
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
Apollo CSV import (mock preview), and the Get contact step (a job to get, one to verify, one verified).

Not in phase 0: real API clients, Ollama/Claude calls, LaTeX compile, SMTP, and scheduler jobs.
