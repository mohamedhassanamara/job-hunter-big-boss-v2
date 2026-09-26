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
| roles | JSON list[str] | Title keywords: "data engineer", "ai engineer", … |
| keywords | JSON list[str] | Boosting keywords (spark, dbt, llm…) |
| excluded_keywords | JSON list[str] | **Title** keywords the pre-filter drops (default: intern, stage, alternance…). No seniority words by default |
| locations | JSON list[str] | ISO country codes: ES, PT, FR, IT |
| remote_policy | enum `any \| remote_ok \| remote_only` | |
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
| kind | enum `job \| project \| skill \| education \| certification` | |
| title | str | Role, project name, skill group, degree |
| org | str? | Company, school |
| location | str? | |
| start_date / end_date | date? | `end_date` null = present |
| summary | text? | |
| bullets | JSON list[str] | Achievement bullets (the CV generator picks from these) |
| tags | JSON list[str] | "spark", "llm", "gcp", "leadership"… |
| position | int | Manual order within a kind |
| is_active | bool | Inactive items are never used in CVs |

### fit_score
History is kept, and the latest row per job is authoritative.
| Column | Type | Notes |
|---|---|---|
| job_id | FK job | |
| profile_id | FK search_profile? | |
| score | int 0–100 | Bands: ≥80 strong, 65–79 good, 50–64 fair, <50 weak |
| strengths / gaps | JSON list[str] | Short reasons |
| summary | str | One line |
| model | str | e.g. `ollama:qwen2.5:7b`, `mock` |

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
| content | JSON | Structured CV: `{headline, summary, experience:[{title, org, dates, bullets[]}], projects, skills:[{group, items[]}], education}` |
| tex | text? | Rendered LaTeX (from the universal template) |
| pdf_path | str? | Relative to `data/cv/` |
| page_count | int? | Must be 1 to approve (enforced later) |
| status | enum `draft \| approved \| superseded` | Approving one supersedes the others |
| generator_model | str | |

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
