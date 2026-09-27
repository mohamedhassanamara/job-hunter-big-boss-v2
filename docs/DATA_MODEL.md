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
experience_item (standalone master data)      app_setting (key/value)
```

## Tables

### search_profile
What discovery looks for.
| Column | Type | Notes |
|---|---|---|
| name | str | e.g. "Data/AI Engineering, South EU" |
| tracks | JSON | `[{name, years_experience, roles: [{title, variants: {en,fr,es,de,it,nl: [..]}}]}]`, edited in Settings → Search profile. The only source of roles: queries, pre-filter and the scorer all read it (`services/roles.py` holds language data only) |
| roles | JSON list[str] | All role titles, derived from `tracks` on save |
| keywords | JSON list[str] | Boosting keywords (spark, dbt, llm…) |
| excluded_keywords | JSON list[str] | **Title** keywords the pre-filter drops (default: intern, stage, alternance…). No seniority words by default |
| locations | JSON list[str] | Target ISO country codes, edited in Settings (any code from `GET /api/countries`, i.e. `services/geo.COUNTRY_ALIASES`). Nothing else hardcodes a country list. |
| remote_policy | enum `any \| remote_ok \| remote_only` | on-site/hybrid vs remote preference |
| remote_scope | enum `anywhere \| europe \| targets` | which remote jobs are eligible (`geo.remote_allows`): worldwide/EMEA, Europe, or target countries. Worldwide and unstated regions always pass; US/Americas/Asia-only never do. |
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
| dedupe_key | str (indexed) | `normalized_company|normalized_title|country` |
| duplicate_of_id | FK job? | Set when the same dedupe_key already exists from another source |
| description_level | enum `full \| summary \| snippet` | Set per source at ingest (WTTJ = summary, Adzuna = snippet). Becomes full after fetch/paste |
| full_fetched_at | datetime? | Fetched/pasted full listing (never overwritten by the feed) |
| user_label / labeled_at | enum `good \| maybe \| no`? | Your judgment for `make eval`, not a stage |

### contact
| Column | Type | Notes |
|---|---|---|
| company_id | FK company | |
| full_name / title | str | |
| email | str? | |
| linkedin_url | str? | |
| source | enum `apollo_dump \| apollo_lookup \| manual` | Tier (a) = apollo_dump, tier (b) = apollo_lookup |
| imported_batch | str? | Import file identifier |

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
| is_placeholder | bool | Test-CV data. Warned about in the UI and removable in one click. Editing an item makes it yours |

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
| red_flags | JSON | `[{type, text, evidence, evidence_verified, severity hard\|soft}]` |
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
| stage | enum `new \| shortlisted \| cv_ready \| ready \| done \| interview \| closed` | |
| route | enum `undecided \| cold_email \| web_apply` | Derived from contact resolution. Can be overridden |
| contact_id | FK contact? | |
| contact_tier | enum `apollo_dump \| lookup_queued \| lookup_found \| none` | 3-tier resolution result |
| close_reason | enum? `dismissed \| rejected \| withdrawn \| no_response \| offer` | Only when `closed` |
| notes | text | |
| applied_at | datetime? | When it hit `done` |
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

### application_event
Timeline and stage history.
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| kind | enum `discovered \| stage_change \| note \| cv_generated \| cv_approved \| draft_created \| draft_approved \| sent \| applied \| contact_resolved` | |
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
| plan | JSON | `{plan: CVPlan (pool ids, ranked reworded bullets), fit: {counts, short_summary}, history, prompt_version, cost_usd, generation_ms}` |
| overrides | JSON | `{force_in[], force_out[], text{key: edited}}`; keys like `role:12:0`, `project:7`, `cert:3`, `summary` |
| template | str | Template used (templates/ or data/templates/) |
| tex | text? | Rendered LaTeX |
| pdf_path | str? | Under `data/cv/<application>/v<n>/` |
| page_count / fill / fit_passes | int? / float? / int | Pages must be 1 to approve; fill = how full the page is |
| violations | JSON | No-fabrication checks `[{type, severity, message, where}]` |
| duration_ms / error | int? / text? | Total generation time; LaTeX error + log tail |
| status | enum `draft \| approved \| superseded` | Approving one supersedes the others; changing an approved one creates a new draft |
| generator_model | str | e.g. `claude-sonnet-5`, `mock-cv` |

### outreach_draft
| Column | Type | Notes |
|---|---|---|
| application_id | FK | |
| contact_id | FK contact? | |
| subject / body | str / text | |
| status | enum `draft \| approved \| rejected \| queued \| sent \| failed` | |
| model | str | |
| edited | bool | True once the user changed the generated text |

### send_queue
A single row in v2 (the global queue).
| Column | Type | Notes |
|---|---|---|
| status | enum `idle \| running \| paused` | |
| interval_minutes | int = 15 | |
| max_items | int = 20 | Max items per queue batch |
| next_send_at | datetime? | |

### send_queue_item
| Column | Type | Notes |
|---|---|---|
| queue_id | FK send_queue | |
| draft_id | FK outreach_draft unique | |
| position | int | |
| scheduled_at / sent_at | datetime? | |
| status | enum `pending \| sending \| sent \| failed \| cancelled` | |
| error | str? | |

### app_setting
| Column | Type | Notes |
|---|---|---|
| key | str unique | `sources`, `models`, `smtp`, `schedule` |
| value | JSON | Non-secret config only. Secrets (SMTP password, API keys) go in `.env` |
