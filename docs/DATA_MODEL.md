# Data model

Two SQLite files share this schema: `data/jobhunter.db` (the real workspace, only real data) and
`data/demo.db` (the tour sandbox, rebuilt from fixtures at each tour start). The API picks one per
request from the `X-Workspace` header.

SQLite via SQLModel. Schema changes go through Alembic (`backend/alembic/versions`). Models live in
`backend/app/models/`, with one module per aggregate.

Conventions:
- Every table has `id` (int PK), `created_at`, and `updated_at` (UTC, set by the app).
- Enums are `str` enums stored as `VARCHAR`, so adding a value needs no migration of the column type.
- List/dict fields (`roles`, `bullets`, `tags`, `strengths`…) are `JSON` columns.
- Foreign keys are declared, and SQLite FK enforcement is enabled per connection (`PRAGMA foreign_keys=ON`).

```
search_profile 1─* source_run 1─* job *─1 company 1─* contact
                                   │                    │
                                   1                    │
                                   │                    │
                 fit_score *─1 ────┤                    │
                                   1                    │
                              application ─────────────*┘ (contact_id)
                     ┌───────────┼──────────────┐
                     *           *              *
          application_event  cv_version   outreach_draft 1─0..1 send_queue_item *─1 send_queue
          cover_letter · application_answer   (*─1 application, web apply)
          application_response · interview · reminder_action   (*─1 application, tracking after applying)
experience_item (standalone master data)      app_setting (key/value)
```

## Tables

### search_profile
What discovery looks for.
| Column | Type | Notes |
|---|---|---|
| name | str | e.g. "Data/AI Engineering, South EU" |
| tracks | JSON | `[{name, years_experience, experience: professional\|projects, experience_note, roles: [{title, variants: {en,fr,es,de,it,nl: [..]}}]}]` (`experience` drives `services/honesty.py`), edited in Settings → Search profile. The only source of roles: queries, pre-filter and the scorer all read it (`services/roles.py` holds language data only) |
| roles | JSON list[str] | All role titles, derived from `tracks` on save |
| keywords | JSON list[str] | Boosting keywords (spark, dbt, llm…) |
| excluded_keywords | JSON list[str] | **Title** keywords the pre-filter drops (default: intern, stage, alternance…). No seniority words by default |
| locations | JSON list[str] | Target ISO country codes, edited in Settings (any code from `GET /api/countries`, i.e. `services/geo.COUNTRY_ALIASES`). Nothing else hardcodes a country list. |
| remote_policy | enum `any \| remote_ok \| remote_only` | on-site/hybrid vs remote preference |
| remote_scope | enum `anywhere \| europe \| targets` | which remote jobs are eligible (`geo.remote_allows`): worldwide/EMEA, Europe, or target countries. Worldwide and unstated regions always pass; US/Americas/Asia-only never do. A remote job that names one country outright ("Remote, Netherlands", a London office) is remote within it and passes only if that country is a target; region words ("Europe", "MENA") follow the scope. |
| min_fit_score | int | Jobs below this are hidden from Today's highlights |
| max_age_days | int | Pre-filter drops listings posted longer ago (default 30) |
| is_active | bool | Exactly one profile is active in v2 |

### discovery_run
One press of "Run discovery", one scheduled run, or one dry-run test. Groups a `source_run` per source.
| Column | Type | Notes |
|---|---|---|
| trigger | enum `manual \| scheduled \| test` | |
| status | enum `running \| success \| partial \| failed` | `partial` when some sources failed |
| started_at / finished_at | datetime | |
| totals | JSON | `{fetched, kept, filtered, new, updated, duplicate, failed}` |

### source_run
One execution of one source within a discovery run. Powers Settings → Sources, the Today banner and tuning.
| Column | Type | Notes |
|---|---|---|
| discovery_run_id | FK discovery_run? | |
| source | enum `adzuna \| remotive \| arbeitnow \| wttj` | |
| profile_id | FK search_profile | |
| started_at / finished_at | datetime | |
| status | enum `pending \| running \| success \| failed \| skipped` | `skipped` = inside the source's cooldown |
| fetched / kept / filtered / new / updated / duplicate _count | int | kept = passed the pre-filter; new/updated/duplicate = ingest outcome |
| error | str? | Full error, or the not-configured/cooldown reason |
| details | JSON | `{requests, warnings[], reasons{code: n}, samples[{title, company, location, reason, url}]}`; `dry_run: true` for tests |

### company
| Column | Type | Notes |
|---|---|---|
| name | str | Display name |
| normalized_name | str unique | Lowercased and stripped of legal suffixes (SL, SA, SAS, SpA, Lda, GmbH…). The dedupe anchor |
| domain / website / linkedin_url | str? | |
| notes | str? | |
| contacted_at | datetime? | Denormalized. Set when any application to this company reaches `done` (sent/applied). Drives the "already contacted" flag |

### job
| Column | Type | Notes |
|---|---|---|
| source | enum (as above) | |
| external_id | str | Unique together with `source` |
| source_run_id | FK source_run? | |
| url | str | Original listing |
| title | str | |
| company_id | FK company | |
| location | str | Free text as provided ("Madrid, Spain") |
| country | str? | ISO code, normalized |
| remote_type | enum `remote \| hybrid \| onsite \| unknown` | |
| description | text | Plain text / markdown |
| salary_text | str? | |
| posted_at | datetime? | |
| discovered_at | datetime | First seen |
| last_seen_at | datetime? | Updated every time a run sees the listing again (idempotent upsert) |
| dedupe_key | str (indexed) | `normalized_company::normalized_title` today; Part 2 adds the country back (`company::title::country`) |
| duplicate_of_id | FK job? | Rows that were duplicates before migration 0032; new cross-source duplicates are merged into the canonical row instead |
| sources | JSON list[str] | Every source that listed this job (migration 0032) |
| source_urls | JSON dict[str,str] | The listing URL per source |
| description_level | enum `full \| summary \| snippet` | Set per source at ingest (WTTJ = summary, Adzuna = snippet). Becomes full after fetch/paste |
| full_fetched_at | datetime? | Fetched/pasted full listing (never overwritten by the feed) |
| user_label / labeled_at | enum `good \| maybe \| no`? | Your judgment for `make eval`, not a stage |

### company (size, aliases, merges)
`company` also has `employees` (exact), `employees_max` ("under N"), `size_source` (`manual | apollo_list`) and
`aggregator_reviewed` (you said "it's an employer" to the job-board suggestion), `agency_override` (migration
0019: `employer | agency | null`, your answer to the recruiting-agency rule; null = the rule decides), and the Get
contact state
`contact_search` (`none | not_found | never`: nobody found with the extension / never look up, a job board) with
`contact_search_at` and `contact_search_notes`. Migration 0016 moved these from the removed `company_lookup` table
(never → never, not_found → not_found, queued/skipped/found → none) and renamed tiers and sources. `company_alias`
(`normalized_name` unique → `company_id`) maps merged-away spellings; `company_merge_decision` (`pair_key` unique,
`decision merged | rejected`) remembers your answer to each suggestion.

### contact
| Column | Type | Notes |
|---|---|---|
| company_id | FK company | |
| full_name / first_name / last_name / title | str | |
| normalized_name | str | Accent/case-folded name; dedupe key with company_id (index) |
| email / email_normalized | str? | Lowercased copy is unique when present (partial index) |
| linkedin_url | str? | |
| source | enum `apollo_dump \| found \| manual \| hunter` | Import / found with the Apollo extension (Get contact) / added by hand (never replaced) / found with Try Hunter |
| verified_at / verified_how | datetime? / str? | Get contact: `entered` (you entered them), `still_there`, `hunter`; stale after `contacts.verify_days` |
| left_at / left_reason | datetime? / str? | `left \| wrong_person`: never picked again by matching or ranking |
| imported_batch | str? | `contact_import.id` |
| role_rank | int | Position in `app_setting.contacts.role_ranking` (999 = unranked); re-derived when the ranking changes |
| notes | text | |

### contact_import
One Apollo CSV import run (background, batches of 500).
| Column | Type | Notes |
|---|---|---|
| filename / file_sha256 | str | The hash flags a file imported before |
| status | enum `running \| done \| failed` | A failure keeps committed batches; re-running is idempotent |
| total / processed / created / updated / skipped / companies_created | int | Progress and result |
| skipped_reasons | JSON | `{duplicate_in_file, already_known, no_company, no_name_or_email}` counts |
| mapping | JSON | Our field → CSV column |
| error / started_at / finished_at | | |

### experience_item
The master experience that CVs are generated from.
| Column | Type | Notes |
|---|---|---|
| kind | enum `job \| project \| skill \| education \| certification \| volunteering \| summary` | `summary` = summary snippets the CV generator picks from |
| url / credential_id | str? | Certifications (verification link, ID) and projects (link) |
| title | str | Role, project name, skill group, degree |
| org | str? | Company, school |
| location | str? | |
| start_date / end_date | date? | `end_date` null = present |
| summary | text? | |
| bullets | JSON list[str] | Achievement bullets (the CV generator picks from these) |
| tags | JSON list[str] | "spark", "llm", "gcp", "leadership"… |
| position | int | Manual order within a kind |
| is_active | bool | Inactive items are never used in CVs or scoring |
| date_label | str? | The dates exactly as written ("Sep 2020 – June 2025", "2020"); CVs print it as is (migration 0022) |
| is_placeholder | bool | Test-CV data. Warned about in the UI and removable in one click. Editing an item makes it yours |

### experience_history (migration 0022)
One row per change of an item's text, written only by `services/experience_write.py`.
| Column | Type | Notes |
|---|---|---|
| item_id | int | The experience item (kept after the item is deleted) |
| action | str | created, edited, archived, undo, deleted |
| source | str | user (Experience screen), master_import, undo |
| before / after | JSON | The text fields (kind, title, org, location, dates, date_label, summary, bullets, tags, url, credential_id, is_active) |
| note | str? | e.g. "not in the master document" |
Undo restores `before` (and is itself a row).

### generation_task (background CV / email drafts, migration 0031)
| Column | Type | Notes |
|---|---|---|
| application_id, kind | int, `cv\|email` | One live task (queued/running) per job and kind |
| status | str | `queued\|running\|done\|failed\|skipped\|cancelled`. Done and cancelled say nothing on the card (the draft is the state) |
| trigger, use | str | `shortlist\|cv_approved\|contact_ready\|retry`; `use = claude` is the one-shot "Generate with Claude" |
| model, details | str, JSON | What wrote it; calls, 429/503 retries, seconds, tokens |
| attempts, not_before, error, warning, retryable | | Task-level retry (one more after 3 min), quota-reset wait, the failure text, the skip reason ("pool incomplete") |
| result_id | int | The CV version or the draft it produced |
Inserted in-session by `services/generation` hooks (`pipeline.transition`, CV approval, a contact becoming verified), run by one worker thread (real workspace only), recovered at startup (running → queued). Settings: `app_setting.generation = {auto_cv, auto_email}`; `models.cv` / `models.email` = `{provider, model, thinking_level}`.

### scoring_run / scoring_task (persistent queue)
| Table | Columns | Notes |
|---|---|---|
| scoring_run | trigger, started_at, finished_at, primary_model, fallback_model, fallback_reason/at, done, failed, retried_429, quota_hits, concurrency_min/max | One pass of the queue. `fallback_reason` = a cloud usage limit switched the rest of the run to the local model |
| scoring_task | run_id, job_id, force, position, status `queued\|in_progress\|done\|failed\|cancelled`, attempts, final_retry, last_error, model_used | Survives restarts: at startup in_progress → queued and the queue resumes. Concurrency 429s never count as attempts |

### fit_score
One scoring attempt. History is kept, and the latest row per job is authoritative.
| Column | Type | Notes |
|---|---|---|
| job_id | FK job | |
| profile_id | FK search_profile? | |
| status | enum `ok \| failed` | failed rows keep the error and have no score |
| error | str? | Visible in the UI |
| score | int 0–100? | **Computed in code** from sub_scores and weights, capped by hard flags. Bands: ≥80 strong, 65–79 good, 50–64 fair, <50 weak |
| sub_scores | JSON | `{dimension: {score 0-10, reason, evidence, evidence_verified}}` for role_match, skills_match, seniority_fit, location_eligibility, language_requirements |
| red_flags | JSON | `[{type, text, evidence, evidence_verified, severity hard\|soft, severity_note?}]`; `severity_note` is set when a flag that would be hard stayed soft because its quote doesn't state the requirement (prompt v4) |
| core_requirements | JSON | Prompt v5+: `[{requirement, evidence, evidence_verified, missing, named, excluded, counts, note?}]`. `missing`/`evidence_verified` come from scoring; `named` (your experience text names it), `excluded` (on "Never cap on these alone" and not in the title) and `counts` (missing, verified, not named, not excluded: only these cap the score at `scoring.missing_core_cap`, default 60) are re-derived by `recompute_all`. Empty on older rows (migration 0027) |
| strengths / gaps | JSON list[str] | ≤3 each |
| summary | str | One sentence |
| confidence | str | high / medium / low (from job.description_level) |
| model / prompt_version | str | e.g. `gemma4:31b-cloud`, `fit_score/v3` (shown in the fit badge tooltip and FitCard). A null prompt_version means a legacy mock score (treated as unscored) |
| content_hash / experience_version / cache_key | str | Cache: same key and status ok means no rescoring. Stale when experience_version ≠ current |
| duration_ms | int? | |

### application
The pipeline record. It is created when a job is discovered and passes filters, so stage `new` means "untriaged".
| Column | Type | Notes |
|---|---|---|
| job_id | FK job unique | |
| stage | enum `new \| shortlisted \| cv_ready \| ready \| done \| interview \| closed` | The overall position; `done` = the first route finished ("Applied", "Emailed", "Applied + emailed"). `drafted` was retired in 0012 (moved to `cv_ready`) |
| route | enum `undecided \| cold_email \| web_apply` | Legacy default focus only: both routes are open on every job. DTOs carry `tracks` (`services/tracks.py`): `application` not_ready/ready/applied and `outreach` no_contact/contact/drafted/approved/queued/sent, derived from `web_applied_at`, the approved CV, `contact_id` and the drafts |
| contact_id | FK contact? | |
| contact_tier | enum `imported \| found \| to_get \| none` | Resolution result (`services/contacts.resolve`): an imported contact, one you found or added, nobody yet (Contacts to get), nobody (not found / never looked up) |
| close_reason | enum? `dismissed \| rejected \| withdrawn \| no_response \| offer_accepted \| offer_declined \| offer` | Only when `closed`. After applying only rejected / no_response / withdrawn / offer_accepted / offer_declined (`services/tracking.close`); `offer` is legacy (shown as "Offer") |
| notes | text | |
| applied_at | datetime? | The date you applied (user-chosen in "Mark applied", noon UTC); for cold email, when it hit `done` |
| applied_method | enum? `company_site \| job_board \| email \| other` | Set by "Mark applied" |
| applied_cv_version_id | FK cv_version? | The CV version sent (locked). `use_alter` FK: cv_version also points at application |
| applied_cover_letter_id | FK cover_letter? | The cover letter sent (locked); null = none. `use_alter` FK, like the CV's |
| letter_language | str | `auto` (the listing's language) \| `fr` \| `en`: this job's cover letter language |
| web_applied_at / web_method | datetime? / enum? | The web application (Mark applied), apart from the email (0012; backfilled) |
| applied_notes | text | Notes from "Mark applied" |
| stage_changed_at | datetime | Last stage change, which drives "days in stage" on cards |

UI labels for `ready` / `done` depend on route: *Ready to send / Sent* (cold_email) versus *Ready to apply / Applied* (web_apply).

**Allowed transitions** (enforced in `services/pipeline.py`):
```
new → shortlisted | closed
shortlisted → cv_ready | new | closed
cv_ready → ready | shortlisted | closed
ready → done | cv_ready | closed
done → interview | closed
interview → closed | done
closed → new (reopen, clears close_reason)
```
Dismiss = `→ closed` with `close_reason=dismissed`. Every transition writes an `application_event`.

Tracked moves (`services/tracking.py`, always through `pipeline.transition`):
- **Mark applied** (`POST /applications/{id}/applied`): only from `cv_ready`/`ready` (steps through `ready`), needs an
  approved CV of this job (default: the latest), locks it, sets `applied_*`, → `done`. `PATCH stage=done` is refused
  for web apply, and `PATCH stage=interview` always (use Mark applied / Log interview).
- Approving a CV leaves the job at `cv_ready`: both routes can start.
- **Email** (`api/outreach.py`, `services/send_queue.py`): a draft doesn't move the stage; approving it moves
  `cv_ready → ready`; **Add to send queue** (`POST /outreach/drafts/{id}/queue`) is a separate step; reject/restore
  only change the draft. The queue sending it, or "I sent it myself" (`POST /applications/{id}/sent-manually`),
  moves `ready → done` unless the job is already done (a web application went first); the CV is locked either way.
- **Mark applied** works from `cv_ready`/`ready` (→ `done`) and from `done`/`interview` when the email went first (no
  stage change); it sets `web_applied_at`/`web_method`, keeps `applied_at` as the first time you reached out, and
  takes `cover_letter_id` (PDF) and `form_letter_id` (form text), both locked like the CV. `PATCH stage=done` is
  always refused (Mark applied or send the email).
- Automatic contact matching skips closed jobs and jobs with an email draft; applied jobs still get a contact.
- **Log interview**: the first one moves `done → interview`. **Log reply** never moves the stage.
- **Ghosting** is only suggested (a reminder); `POST /reminders/{id}/ghost/confirm` closes as `no_response`.

### application_event
Timeline and stage history.
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| kind | enum `discovered \| stage_change \| note \| cv_generated \| cv_approved \| draft_created \| draft_approved \| letter_generated \| letter_approved \| sent \| applied \| contact_resolved \| response \| interview \| reminder` | |
| from_stage / to_stage | str? | For stage_change |
| message | str? | Human-readable line |
| payload | JSON | Extra data |
| at | datetime | |

### cv_version
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| version | int | 1, 2, 3… per application |
| content | JSON | The rendered CVDocument: `{summary, skills[{category, items}], roles[], projects[], certifications[], education[], volunteering[]}` (see docs/CV_TEMPLATES.md) |
| plan | JSON | `{plan: CVPlan (pool ids, ranked bullets: each the pool fact or a checked light adaptation, with `adapted`/`fallback`), tailoring: {adapted, original, fallbacks, verifier}, fit: {counts, short_summary}, history, prompt_version, cost_usd, generation_ms}` |
| overrides | JSON | `{force_in[], force_out[], text{key: edited}}`; keys like `role:12:0`, `project:7`, `cert:3`, `summary` |
| template | str | Template used (templates/ or data/templates/) |
| tex | text? | Rendered LaTeX |
| pdf_path | str? | Under `data/cv/<application>/v<n>/` |
| page_count / fill / fit_passes | int? / float? / int | Pages must be 1 to approve; fill = how full the page is |
| violations | JSON | No-fabrication checks `[{type, severity, message, where}]` |
| duration_ms / error | int? / text? | Total generation time; LaTeX error + log tail |
| status | enum `draft \| approved \| superseded` | Approving one supersedes the others; changing an approved one creates a new draft |
| generator_model | str | e.g. `claude-sonnet-5`, `mock-cv` |
| locked_at / pdf_sha256 | datetime? / str? | Set when sent with an application: never re-rendered, re-approved or superseded (edits create a new draft); the hash proves the PDF never changes |

### cover_letter
A cover letter version for a web application (`services/cover_letter.py`), written from the approved CV.
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| version | int | 1, 2, 3… per application |
| status | enum `draft \| approved \| superseded` | Regenerating supersedes the draft under review; approving supersedes the other unlocked approved one; editing an approved one sends it back to draft |
| language | str | `fr \| en` |
| format | str | `pdf` (letter to upload) \| `form` (text for a form's box; no PDF). Versions are numbered per format |
| question / char_limit | text? / int? | Form text: the form's question and the box's limit (a hard check) |
| content | JSON | `{salutation, ask, paragraphs: [{sentences: [{text, citations, about_job}]} \| {text}]}`; an edited paragraph becomes `{text}` (checked at text level) |
| text | text | Plain text (Copy as text): salutation, paragraphs, closing, name |
| tex / pdf_path / page_count | text? / str? / int? | Under `data/letters/<application>/v<n>/`; must be 1 page |
| template | str | The CV template's `cover_letter.tex.j2` |
| cv_version_id | FK cv_version? | The approved CV it was written from |
| generator_model / prompt_version | str / str? | e.g. `cover_letter/v2` |
| plan | JSON | `{plan: CoverLetterPlan, attempts}` |
| violations | JSON | `services/letter_check.py` findings; errors block approval |
| duration_ms / error | int? / text? | |
| locked_at / pdf_sha256 | datetime? / str? | Set by Mark applied: never changed again (edits create a new draft) |

### application_answer
Answers to an application form's questions (`services/answers.py`).
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| question | text | |
| char_limit | int? | Hard check: over it is an error, the answer is never cut |
| answer | text | |
| language | str | The letter language of the job |
| position | int | Order on the Job page |
| edited | bool | Your text: re-checked at text level (citations no longer apply) |
| plan | JSON | `{sentences: [{text, citations, about_job}], attempts}` |
| violations | JSON | Grounding, length, banned phrases, years |
| generator_model / prompt_version | str / str? | |

### company_page / company_signal / research_run (company research, migration 0014)
- `company_page`: company_id, research_run_id, url, kind (page | news), title, text, page_date, fetched_at: what
  the last research read.
- `company_signal`: company_id, research_run_id, kind (product | technical | customer_result | launch | funding |
  expansion | other), fact, quote (exact, verified in the page), source_url, page_date, fetched_at, origin
  (research | manual), verified, selected (used by emails), dismissed. A refresh replaces research signals and
  keeps yours.
- `research_run`: company_id, trigger (draft | manual), status (running | done | failed | cached), started/finished,
  pages, signals_kept/dropped, `calls` (one entry per model call: model, prompt version, outcome, duration,
  tokens), warnings (skipped pages, dropped signals with the reason), error.
- `company.research_refreshed_at`: set only when a run kept signals (fresh = within `research.refresh_days`).

### email_example (the email regression set)
kind (reference_good | reference_bad | approved | rejected), language, subject, body, draft_id, company, inputs
(the `EmailRequest` snapshot, or the application to rebuild it from), note.

Job-linked drafts (prompt v11) store `format: "applied"`, `mode: "applied"`, the plan (role, opening, experience
sentences with citations, constraint + its listing quote, optional signal with ids, ask), `application`
(`{applied, date}` when drafted), `language`, `signal_ids`, `signals`, the request, attempts, `via`, `auth` and
`name_source`; the subject is `<Role> application – <name>`. Speculative drafts store `mode: "speculative"` or,
older ones, no mode. `email_example.inputs.mode` is `applied` | `speculative`; `kind: must_fail` rows (with
`case` and `expect: fail`) belong to the verifier's regression set.

Outreach drafts written as introductions store in `plan`: `format: "intro"`, the plan (hook with signal ids,
intro focus, problem, proofs, ask), `intro_line`, `language`, `signal_ids`, the signals snapshot,
`research_run_id`, the request, attempts, `via`, `auth`, `hook_check` (`{status: ok|unchecked|skipped, hash
of the hook text it checked, model, claims: [{claim, signal_ids, verdict, why}], calls}`) and `name_source`
(`{first_name, url, title, excerpt}` when the greeting uses the pages' spelling).

### contact_alert
A sign the contact may have left (`services/contact_check.py`): `contact_id`, `company_id`, `key` (unique:
contact + source URL + kind, so a sign found again stays one row with its state), `kind` (left | new_holder),
`reason`, `excerpt`, `source_url`, `source_title`, `page_date`, `detected_at`, `dismissed_at` (set = you verified
the contact; an active alert blocks approving the email). `company_page.kind` gains `contact_news` (news found by
searching the contact's name).

### copilot_thread / copilot_message
The Copilot's conversations (`services/copilot.py`). `copilot_thread`: `application_id?` (null = global), `title`,
`archived` ("New conversation" on a job archives the old thread). `copilot_message`: `thread_id`, `role`
(user/assistant), `content`, `model` (with the prompt version), `warnings` JSON (facts that aren't yours, clichés,
years wording), `duration_ms`, `error`.

### application_response
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| kind | enum `positive \| rejection \| other` | |
| received_at | datetime | |
| notes | text | |

`application_response.channel`: `application | email | linkedin` (replies per track in Stats).

### Claim verification (migration 0021)
- `outreach_draft.verification`, `cover_letter.verification`, `application_answer.verification` (JSON; LinkedIn keeps it
  inside `note` / `followup`): status passed | failed | error, claims [{sentence, claim, about, verdict, source_id,
  source_quote, reason, quote_not_found?, skipped?}], blocking, hash (sha256 of the exact text; emails: "Subject: …"
  + the body as sent), attachment_sha256 (emails: the CV PDF), model, prompt_version, duration_ms, at.
- `email_example.kind` gains `must_fail` (the verifier's regression set; `inputs.case`, `inputs.expect`).

### Motivation (Phase 11, migration 0020)
- `chest_open` (opened_at, tokens 1-10, cost = the chest goal then, ordinal), `token_entry` (the ledger: at,
  amount ±, kind chest | purchase | refund | adjust, ref_id, note; balance = sum), `shop_item` (name, price,
  emoji, image_name, archived, position), `purchase` (item_id, name/price/emoji as bought, bought_at,
  redeemed_at), `woop`, `win_entry`, `goal_tile` (kind image | video, file_name under data/motivation/<ws>/,
  mime, size, caption, position).
- The streak is never stored: `services/motivation/streak.compute` over `activity.per_day` (applied jobs by
  their latest `applied` event, optional sent emails and LinkedIn requests).
- Setting `motivation`: enabled, daily_goal 5, count_emails, count_linkedin, chest_goal 30, timezone
  Africa/Tunis, max_upload_mb 100, chests_since (stamped once on first read; never moved by a save).
- `application_event.kind` gains `applied_undone`; the `applied` event payload records what undo restores
  (stage_before, cv_locked_now, letters_locked_now, applied_at_before, applied_method_before).

### linkedin_outreach / linkedin_link_open / cv_fit (Phase 10, migration 0017)
- `linkedin_outreach`: one person to message on LinkedIn about one job (unique application + contact):
  `group` (hiring_team | alumni | lead | recruiter | other), `alumni`, `status` (to_contact | sent | accepted |
  messaged | replied), `note` / `followup` (JSON: text, citations, violations, model, prompt version, edited,
  max_chars), `critique`, `sent_at` / `accepted_at` / `messaged_at` / `replied_at`. People are `contact` rows
  (source `linkedin` when added only for LinkedIn: never the email's contact without an email).
- `linkedin_outreach.hiring_team` (migration 0018): they posted this job (captured poster). `group` is then the
  note's angle (recruiter | lead | alumni | other), detected from the title and overridable; 0018 moved old
  `hiring_team` groups to the flag.
- `linkedin_outreach` (migration 0029, LinkedIn Premium): `inmail` (JSON: subject, text, citations, violations,
  verification, model, edited, max_chars), `inmail_sent_at`, `inmail_refunded_at` (a reply within 90 days),
  `source` (manual | captured | viewed_profile), `reason` ("viewed my profile on 20 Oct": for the user only,
  never given to a model) and `viewed_on`. Credits are computed (sent this month, refunds dated by the reply).
- `linkedin_lead` (migration 0029): someone who viewed your profile whose company has no job yet (name, title,
  company_name, profile URL, viewed_on, reason, `linked_outreach_id` once linked).
- `linkedin_link_open`: (key, day) for the "opened today" mark on search links.
- `cv_fit`: per approved CV version: base fit id/score, the tailored score and sub-scores, model, prompt version,
  status (pending | ok | failed), the lexical report.
- `job.linkedin_job_id` (indexed), `job.capture` (how each field of an import was found, plus warnings);
  `source = linkedin` (never a discovery source).
- Settings `linkedin` (also `inmail_monthly_credits` 5, `inmail_max_chars` 1000, `premium_end_date`, `premium_remind_days` 14): `note_max_chars` 200, `daily_requests` 10, `followup_days` 5, `gap_days` 3,
  `geo_ids` {ISO code: {id, verified}}.

### interview
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| round | int | 1, 2… (automatic) |
| scheduled_at | datetime | |
| type | enum `hr \| technical \| take_home \| final \| other` | |
| outcome | enum `pending \| passed \| failed \| cancelled` | |
| notes | text | |

### reminder_action
Reminders are **computed** (`tracking.reminders`), not stored: for applications in `done`/`interview` with no reply and
no interview, a follow-up at `applied_at + d` for each `d` in `tracking.followup_days` (only the latest due one shows) and
a ghosting suggestion at `applied_at + ghost_after_days`. This table only records what you did with one.
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| key | str | `followup:7`, `followup:14`, `ghost` |
| snoozed_until / dismissed_at | datetime? | Snoozed hides until then; dismissed hides for good |

### outreach_draft
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| contact_id | FK contact? | |
| subject / body | str / text | |
| status | enum `draft \| approved \| rejected \| queued \| sent \| failed` | |
| model | str | |
| edited | bool | True once the user changed the generated text |

`outreach_draft` also stores `parent_id` (the draft it was regenerated from), `feedback` (what you asked to change)
and `unverified_approval` (`{at, ignored: [{type, severity, message}], hash, attachment_sha256, contact_id,
recipient, cv_version_id, verification_state}` for an approval without the claim verifier; empty = a normal
approval); `plan.language_choice` = `{language, detected, source: auto|override|job|setting, reason}` and
`plan.source: "external"` for a draft pasted from another AI. `cover_letter.feedback` keeps the same for letters;
LinkedIn messages keep `feedback` and `history` inside their JSON. Migration 0030.

`outreach_draft` also stores `cv_version_id` (the approved CV it's written from and attaches), `plan` (the
model's sentences with citations, attempts), `violations` (the checks), `prompt_version`, `duration_ms`, `error`,
`test_sent_at`, `sent_at`, `message_id`. `body` is your text only; the signature (sign-off + name; contact line opt-in) and an optional last line are added at send time.

### send_log
Every send attempt (never deleted): `draft_id`, `kind test | real`, `to`, `subject`, `status sent | failed`,
`error`, `message_id`, `attachment`, `at`. A successful `test` row is required before the queue can start.

### send_queue
A single row in v2 (the global queue).
| Column | Type | Notes |
|---|---|---|
| status | enum `idle \| running \| paused` | |
| interval_minutes | int = 15 | Legacy, no longer used: the gap is random (`app_setting.smtp` `gap_min_minutes` / `gap_max_minutes`, default 4 and 7) |
| max_items | int = 20 | Max items per queue batch |
| next_send_at | datetime? | The planned next send. Drawn fresh (uniform between the gap bounds) after every send or failed attempt and stored here, so a restart keeps the schedule and never sends early or twice |

### send_queue_item
| Column | Type | Notes |
|---|---|---|
| queue_id | FK send_queue | |
| draft_id | FK outreach_draft unique | |
| position | int | |
| scheduled_at / sent_at | datetime? | |
| status | enum `pending \| sending \| sent \| failed \| cancelled \| unknown` | `sending` at startup → `unknown` (never resent blindly) |
| attempts / last_attempt_at / message_id | int / datetime? / str? | |
| error | str? | |

### app_setting
| Column | Type | Notes |
|---|---|---|
| key | str unique | `sources`, `models` (`{scoring: {provider, model, fallback, cloud_concurrency, local_concurrency}, cv, email: {provider, model, thinking_level}, letter, interview, rewrite, confirm, verifier: {model}}`; APInex ids only in `scoring` and `cv`), `smtp`, `schedule`, `lookup` (`{daily_cap}`: the Apollo extension daily limit), `contacts` (`{role_ranking: [{label, keywords[]}], small_order, large_order, small_company_threshold, verify_days}`), `hunter_log` (Try Hunter uses), `contacts_last_match` (report), `tracking` (`{followup_days: [7, 14], ghost_after_days: 30}`), … |
| value | JSON | Non-secret config only. Secrets (SMTP password, API keys) go in `.env` |


## Phase 12: contact providers and the company cache

- `company` (added): `domain_source` (manual | pdl | listing | provider), `industry`, `email_pattern`
  (`{first}.{last}` notation), `pattern_confidence`, `pattern_evidence` (JSON: source + sample emails),
  `last_enriched_at`. `domain`, `linkedin_url`, `employees(_max)` already existed.
- `contact` (added): `found_by_provider` (hunter | prospeo | apollo | apify | pattern), `found_by_key` (a
  label like `prospeo#2`), `found_by_actor`, `found_at`, `verification_status` (valid | accept_all | unknown |
  invalid: the email's deliverability; different from `verified_at`, which is you confirming the person).
  `ContactSource` gained prospeo, apollo, apify, pattern.
- `company_provider_run`: which provider was queried for which company and when (`status` ok | empty | error,
  credits, cost_usd, the people it listed in `candidates`). This is the cache: a fresh run is not repeated.
- `provider_key_state` (provider, key_label, `disabled_at/reason`, `monthly_limit`), `provider_usage`
  (provider, key_label, period `YYYY-MM`, credits, cost_usd, calls: unique per month) and `provider_call`
  (the log). Keys themselves are never stored.
- `app_setting.providers`: `{max_age_days: 90, max_reveals: 2, limits: {hunter, prospeo, apollo, apify}}`.


## Phase 12b: interview prep, glossary, listing flags, apply link

- `interview_prep` (migration 0025): `application_id`, `version`, `status` (draft | approved | superseded),
  `language`, `content` JSON (`pitch`, `stories` [{requirement, title, situation, task, action, result}: each a
  list of `{text, citations, about_job, about_candidate}`], `questions` [{question, probes, story}], `ask_them`),
  `violations` (code checks; errors block approval), `verification` (the claim verifier's record, tied to the
  exact text), `generator_model`, `prompt_version`, `plan` (what the model returned + attempts), `duration_ms`.
- `job.apply_url` (migration 0024): where the listing says to apply (ATS boards, listing JSON-LD) when it is not
  the listing page itself; used with `company.website` to find the company's domain.
- `app_setting.profile.glossary`: `[{from, to, note}]` written by you in Settings → Candidate (at most 60 terms).
  `app_setting.contacts.exclude_keywords`: words a title may not contain to match a role group (default business
  development, sales, account).
- Listing red flags are not stored: `services/listing_flags.scan(job)` runs on every job detail.

## Phase 12c: company domains

- `company.email_domain` (migration 0026): the domain mail and provider lookups use when it differs from
  `company.domain` (the website's); set from verified emails or by you ("Use this one").
- `company.domains` JSON: `{domain: {source, mx, checked_at, note}}`, every known domain (pdl, listing, apply link,
  website, website contact page, verified email, guess, you) with its MX answer cached for 30 days.
- `company_provider_run.domain`: the domain a run searched (NULL on runs from before: they match any domain).

**Gemini quota (no new tables):** `provider_usage` holds one row per (model, key label "key N", Pacific date) with `calls` = requests made that day; `provider_key_state` (provider `gemini`) holds a key Google refused. Settings → Scoring also gained `never_cap_on` (list) and `auto_score_new` (bool); a missing value means the default.

**`fit_confirmation` (migration 0028):** a second opinion on one job (Ask Claude). `job_id`, `source` (claude | gemma | manual | mock), `model`, `via`, `prompt_version` (the scoring prompt used), `confirm_prompt_version`, `experience_version`, then the same `score` / `sub_scores` / `red_flags` / `core_requirements` / `strengths` / `gaps` / `summary` / `confidence` as `fit_score` (same arithmetic and caps), `verdict` (`{advice apply|maybe|skip, why, seniority, skills, location_visa, language}`), `notes` (what was skipped and why), `duration_ms`. History is kept, the newest row is shown; scoring never reads this table and it never changes `fit_score`.
