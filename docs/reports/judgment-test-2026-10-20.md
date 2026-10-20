# Judgment test: five jobs, Claude first and blind (2026-10-20)

Test only: **no database writes**, nothing committed by this step. Draft **v5** prompt for every run: v4 + v4b (any integer 0-10) + the explicit language-level rule (a stated level such as C1, fluent or `sehr gute Deutschkenntnisse` counts as the requirement). The draft system prompt is in `docs/reports/raw/judgment-test/prompt-v5-draft-system.md`; the repo prompt is unchanged (still v4). Same experience pool and the same JSON schema for everyone. Raw: `docs/reports/raw/judgment-test/` (`claude.json` was saved before any other model ran).

## 0. How the test ran, and a finding that changes earlier conclusions

- **Claude (blind):** `claude -p` on your subscription (`claude-sonnet-5-5`, auth source `none` = login, no API key), no tools, no settings, empty temp directory, the exact same system prompt, user prompt and schema as the other models. It ran in a fresh process that saw only the prompt. I also asked it for an independent apply/maybe/skip verdict, and wrote my own verdict (`assistant_verdict` in `claude.json`) from the listings and your profile, after the `claude -p` ratings were saved and before any other model ran. **Honest limit on blindness:** I cannot unsee the earlier benchmark tables in this conversation. I did not reopen any model's output for these five jobs; the `claude -p` ratings are blind in the strict sense, my own verdicts are blind only in that sense.
- **The #765 German C1 requirement was never in the prompt.** The app truncates listings above 6,000 characters (`fit.truncate_description`: first 70%, last 30%, the middle is replaced by `[…]`). #765's listing is 6,908 characters and the line `Sehr gute Deutschkenntnisse (C1) in Wort und Schrift` sits at character 4,410, inside the removed part. So **no model ever saw it**, in this test or in the earlier v3, v4, v4b benchmarks, and my earlier statement that all models 'missed' it, and the 'recall gap' I attributed to the instruction `when in doubt, answer false`, were wrong. This test therefore runs #765 twice: as the app renders it, and with the full listing.
- Scale of the truncation: 37 of the 3,999 non-duplicate jobs are over 6,000 characters, but 35 of those are full listings, i.e. about a quarter of all full-description jobs lose their middle section. No change was made to the app.

## 1. Claude's ratings and verdicts

| Job | Claude score | claude -p verdict | My verdict |
|---|---|---|---|
| #1914 Location Data Engineer, Amo (Paris, onsite) | 90 | apply | apply |
| #2418 Senior Fullstack Mobile Healthcare, Snke (Munich, hybrid) | 67 | maybe | maybe (lean apply) |
| #1913 Backend Engineer (Go), Prelude (Paris) | 64 | skip | skip |
| #3923 Python Engineer Web Crawling, Certivity (Munich) | 61 | maybe | skip |
| #765 AI Engineer, Nerdware (Nürnberg, onsite) [as the app renders it: truncated] | 76 | maybe | skip |
| #765 AI Engineer, Nerdware: full listing | 35 | skip | skip |

Full text of both verdicts, per job:

**#1914 Location Data Engineer, Amo (Paris, onsite)**: Claude's score 90

- *claude -p, apply:* Visa sponsorship is offered and the stack overlaps well (dbt, DuckDB, orchestration, ML). Scale experience and seniority are modest gaps, but the fit is strong enough to apply. (seniority: No years are stated and the role reads mid-level; 3 years total with 1 in data is a slight stretch but plausible. Skills: Good match on dbt, DuckDB, Airflow, Python, SQL and ML; gaps in Spark, BigQuery, ClickHouse and large-scale or geospatial data. Location/visa: Onsite in Paris, and the company explicitly offers a sponsored visa and relocation help, which fits a Tunisia-based candidate. Language: English is the working language (the listing is in English and the team is 68% international), and the candidate also has professional French.)
- *My verdict, apply:* This is the one listing that offers visa sponsorship and relocation explicitly for a role squarely in your Data Engineer track, so apply. (seniority: No years are stated and the duties read mid-level; you have about 1 year in data plus projects, a modest stretch. Skills: dbt, DuckDB, Airflow, SQL and Python match the stack and the 'or equivalent tools' wording; Spark, BigQuery, ClickHouse and large-scale or geospatial data are gaps. Location/visa: Onsite in Paris 5 days a week, with 'Help and sponsored visa process', a month of Airbnb and a relocation agency, which is what you need. Language: English works (team is 68% international); your French is a bonus.)

**#2418 Senior Fullstack Mobile Healthcare, Snke (Munich, hybrid)**: Claude's score 67

- *claude -p, maybe:* Mobile and backend skills fit well and English is enough. The senior level and sponsorship from Tunisia are the risks, but the Flutter Android need makes it worth a low-cost try. (seniority: Senior title with "several years" required; the candidate has 3 years, so this is a stretch but their full-stack range helps. Skills: Strong Flutter, Spring Boot, Docker, CI/CD and testing; Android Flutter port fits, but no Go, .NET, Rust, FHIR or regulated-software experience. Location/visa: Onsite/hybrid in Munich, and the candidate needs visa sponsorship from Tunisia; startups may hesitate, though the Blue Card route is plausible. Language: English is sufficient; German is only a plus.)
- *My verdict, maybe (lean apply):* The concrete Flutter-to-Android need is a real match and the language bar is low. Seniority and sponsorship are the risks, so apply with a tailored application but don't expect it to be easy. (seniority: 'Several years' and a Senior title against your 3 years is the main risk, but the mix of mobile and backend work is what you have actually done. Skills: They need Flutter for the Android app and Python/backend work; you have 3 years of Flutter plus Spring Boot BFF and FastAPI. Go/.NET/Rust, FHIR and regulated-software experience are missing, and the listing says fundamentals matter more than stack. Location/visa: Hybrid in Munich; sponsorship is not mentioned. A degree-holding engineer can plausibly go through a Blue Card, but expect that question early. Language: English is enough; German is only 'a strong advantage'.)

**#1913 Backend Engineer (Go), Prelude (Paris)**: Claude's score 64

- *claude -p, skip:* The candidate has no Go or AWS serverless experience and about 1 year of backend work. The role wants large-scale systems experience and is onsite in Paris with no stated sponsorship, so the fit is weak. (seniority: The role implies experience designing large-scale systems, and the candidate has only about 1 year of backend experience. Skills: The role needs strong Go plus DynamoDB, SQS, Lambda and gRPC, and the candidate has none of these (Spring Boot, FastAPI and Python instead). Location/visa: The job is onsite in Paris, 3 days a week, and the listing doesn't mention visa sponsorship, which the candidate needs from Tunis. Language: English is required and the candidate has full professional English, so this is met.)
- *My verdict, skip:* The gap is the stack and the scale of systems experience, so it is a poor use of an application. (seniority: They want experience designing large-scale systems and on-call ownership; you have about 1 year of backend work. Skills: Strong Go plus DynamoDB, SQS, Lambda, Redshift and gRPC; you have Spring Boot, FastAPI and Python, but no Go or AWS serverless. Location/visa: Hybrid in Paris (3 days in the office); sponsorship is not mentioned. Language: Fluent professional English, which you meet.)

**#3923 Python Engineer Web Crawling, Certivity (Munich)**: Claude's score 61

- *claude -p, maybe:* The core requirement is large-scale scraping with anti-bot experience, which the candidate lacks. Visa sponsorship for an onsite Munich job is also unclear. The Python, Docker and LLM extraction overlap makes it a stretch application. (seniority: Role asks for 3+ years of professional development, which matches the candidate's 3 years, though most of that is Flutter rather than Python. Skills: Python, Docker, FastAPI, Airflow, LLM work and Spring Boot match, but there is no web scraping or anti-bot experience and no production cloud (GCP/Azure) work, and those are the core requirements. Location/visa: Onsite in Munich (up to 60% remote) and the candidate needs visa sponsorship; the listing doesn't mention sponsorship, so relocation is uncertain. Language: English is the working language (the listing is in English) and the candidate's full professional English meets it.)
- *My verdict, skip:* The must-have is firsthand anti-bot scraping experience, which you lack; a stretch application would likely be filtered out. (seniority: Asks 3+ years of professional development; you have 3, but mostly Flutter, with Python mainly in an internship and projects. Skills: The core is hands-on large-scale web scraping against anti-bot defences, async Python and a cloud stack (GCP/Azure); you have none of that, only LLM-based extraction as a nice-to-have. Location/visa: Onsite in Munich with up to 60% remote; sponsorship is not mentioned. Language: English listing, English is enough.)

**#765 AI Engineer, Nerdware: full listing**: Claude's score 35

- *claude -p, skip:* Deciding factor is the missing German C1 for an onsite Senior role in Germany. Seniority, visa sponsorship and cloud/agentic gaps compound it. (seniority: Role is Senior with multi-year experience required; candidate has about 3 years total and 1 in AI, so it's too senior. Skills: Partial match: LLM, RAG, FastAPI, Docker and Terraform fit, but there is no AWS/Azure, agentic production work or full-stack depth. Location/visa: Onsite in Nürnberg, Germany, and the candidate needs visa sponsorship from Tunisia; the listing offers no relocation or sponsorship. Language: Requires German C1; the candidate has no German (Arabic, English, French, limited Spanish), so this is not met.)
- *My verdict, skip:* The stated C1 German requirement disqualifies it before seniority, cloud gaps or visa questions even matter. (seniority: Senior level with 'mehrjährige Erfahrung'; you have 3 years in total and about 1 in AI, so it is a stretch. Skills: LLM, RAG, FastAPI and Docker fit; AWS/Azure cloud work and agent frameworks in production are missing. Location/visa: Onsite in Nürnberg (remote only within Germany); no sponsorship or relocation is mentioned, which you would need from Tunis. Language: The listing states 'Sehr gute Deutschkenntnisse (C1) in Wort und Schrift'. You have no German, so this alone rules it out.)

Claude's ordering of the five jobs (full listing for #765): #1914 (90) > #2418 (67) > #1913 (64) > #3923 (61) > #765 (35). The two verdicts agree on #1914 (apply), #1913 (skip) and #765 with the full listing (skip). They differ on #3923 (`claude -p` maybe, me skip), on #2418 (both maybe; I lean to apply) and on #765 as rendered (`claude -p` maybe because the German line was cut from what it saw; I skip because I read the whole listing).

## 2. Per config: agreement with Claude

Two readings, because of the truncation: **as rendered** (#765 truncated for both Claude and the config; apples to apples) and **full listing** (#765 full for both). Mean absolute difference is over the 5 jobs; "same order" means the five jobs are ranked exactly as Claude ranks them.

| Config | MAD, as rendered | MAD, full #765 | Same exact order (rendered / full) | Pairs ordered like Claude, of 10 (rendered / full) | #765 C1 caught: truncated prompt | #765 C1 caught: full listing | Time per job (s), mean | Thinking tokens per job: mean / median / max | Valid as returned |
|---|---|---|---|---|---|---|---|---|---|
| 3.5-lite none | 5.0 | 4.6 | no / no | 8 / 8 | present, soft | yes (hard flag) | 21.8 | 0 / 0 / 0 | 5/5 |
| 3.5-lite dynamic | 6.0 | 4.4 | no (tie) / no (tie) | 5.5 / 7.5 | no | yes (hard flag) | 24.8 | 2293 / 2095 / 3166 | 5/5 |
| 3.5-lite high | 7.0 | 5.8 | no / no | 8 / 8 | no | yes (hard flag) | 25.6 | 2461 / 2627 / 3175 | 5/5 |
| 3.1-lite none | 9.4 | 7.0 | no / no | 5 / 8 | present, soft | yes (hard flag) | 30.8 | 0 / 0 / 0 | 5/5 |
| 3.1-lite dynamic | 11.0 | 8.6 | no (tie) / no | 6.5 / 7 | no | yes (hard flag) | 52.5 | 13620 / 1057 / 62913 | 5/5 |
| 3.1-lite high | 11.0 | 8.6 | no (tie) / no | 6.5 / 7 | no | yes (hard flag) | 56.0 | 13620 / 1057 / 62913 | 5/5 |
| gemma-4-31b-it default | 4.2 | 3.8 | no (tie) / no (tie) | 7.5 / 7.5 | no | yes (hard flag) | 79.7 | 1682 / 1094 / 4264 | 0/5 |

Claude itself, truncated prompt: no flag (it wrote `no explicit level stated`, which was true of what it saw); full listing: `language_required` present, hard flag, score 35, verdict skip.

## 3. Per job: Claude and every config, side by side

### #765 AI Engineer, Nerdware (Nürnberg, onsite) [as the app renders it: truncated]

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| skills_match | 6 | 8 | 6 | 9 | 7 | 8 | 8 | 8 |
| seniority_fit | 7 | 5 | 5 | 5 | 5 | 8 | 8 | 5 |
| location_eligibility | 8 | 8 | 8 | 8 | 0 | 8 | 8 | 8 |
| language_requirements | 5 | 0 | 0 | 5 | 5 | 10 | 10 | 0 |
| **final score** | **76** | **74** | **68** | **82** | **64** | **88** | **88** | **74** |
| flags | none | language_required (soft) | none | none | must_be_based_in (soft), language_required (soft) | none | none | none |

*Claude's reasons:* **role** AI Engineer building LLM applications, RAG and agents. **skills** Strong LLM, RAG, FastAPI, Docker; lacks AWS/Azure and agent frameworks. **seniority** Asks 'mehrjährige Erfahrung' (several years); candidate has 3 years software, 1 in AI. **location** Onsite in Germany, a target country; no sponsorship or authorization restrictions stated. **language** Posting written in German; no explicit level stated, candidate lacks German.

### #765 AI Engineer, Nerdware: full listing

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 9 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| skills_match | 5 | 7 | 7 | 6 | 6 | 6 | 6 | 7 |
| seniority_fit | 3 | 5 | 0 | 5 | 0 | 0 | 0 | 0 |
| location_eligibility | 8 | 8 | 8 | 8 | 5 | 8 | 8 | 8 |
| language_requirements | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **final score** | **35** | **35** | **35** | **35** | **35** | **35** | **35** | **35** |
| flags | language_required (hard) | language_required (hard) | language_required (hard), seniority_mismatch (soft) | language_required (hard) | language_required (hard), seniority_mismatch (soft) | language_required (hard), seniority_mismatch (soft) | language_required (hard), seniority_mismatch (soft) | language_required (hard), seniority_mismatch (soft) |

*Claude's reasons:* **role** AI Engineer role building LLM, RAG and agentic applications. **skills** LLM, RAG, FastAPI, Docker match; lacks AWS/Azure, agents, production experience. **seniority** Senior level with multi-year experience; candidate has 1 year in track. **location** Onsite in Germany, a target country; no sponsorship restriction stated. **language** Requires C1 German; candidate has no German.

### #2418 Senior Fullstack Mobile Healthcare, Snke (Munich, hybrid)

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 6 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| skills_match | 6 | 7 | 8 | 9 | 7 | 8 | 8 | 7 |
| seniority_fit | 6 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| location_eligibility | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | **67** | **66** | **68** | **72** | **66** | **68** | **68** | **66** |
| flags | none | none | none | none | none | none | none | none |

*Claude's reasons:* **role** Fullstack role with mobile/Flutter component; mixed adjacent role. **skills** Flutter, Python, CI/CD, Docker, testing match; no Go/.NET/FHIR experience. **seniority** Senior, 'several years' unspecified; candidate has 3 years. **location** Onsite in Germany, a target country; no sponsorship or authorization statements. **language** English required; German only a strong advantage, not required.

### #1914 Location Data Engineer, Amo (Paris, onsite)

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| skills_match | 7 | 8 | 8 | 8 | 8 | 9 | 9 | 9 |
| seniority_fit | 9 | 10 | 5 | 8 | 10 | 10 | 10 | 10 |
| location_eligibility | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | **90** | **94** | **86** | **91** | **94** | **97** | **97** | **97** |
| flags | none | none | none | none | none | none | none | none |

*Claude's reasons:* **role** Core work is building data pipelines as a Data Engineer. **skills** dbt, DuckDB, Airflow, SQL, Python match; lacks Spark, BigQuery, ClickHouse. **seniority** No years stated; mid-level wording, candidate has 1 year in track. **location** Job explicitly offers sponsored visa and relocation to Paris. **language** Posting in English; no other language required.

### #3923 Python Engineer Web Crawling, Certivity (Munich)

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 4 | 5 | 8 | 10 | 5 | 10 | 10 | 7 |
| skills_match | 5 | 7 | 7 | 7 | 7 | 7 | 7 | 4 |
| seniority_fit | 8 | 10 | 5 | 5 | 10 | 10 | 10 | 10 |
| location_eligibility | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | **61** | **73** | **74** | **80** | **73** | **88** | **88** | **70** |
| flags | none | none | none | none | none | none | none | none |

*Claude's reasons:* **role** Web crawling Python engineer with data pipelines; adjacent to Data Engineer. **skills** Python, Docker, LLMs, pipelines match; no scraping, anti-bot, async, or production cloud. **seniority** Asks 3+ years software development; candidate has 3 total. **location** Onsite in Germany, a target country; no sponsorship or authorization statements. **language** Posting in English; no other language required.

### #1913 Backend Engineer (Go), Prelude (Paris)

| | Claude | 3.5-lite none | 3.5-lite dynamic | 3.5-lite high | 3.1-lite none | 3.1-lite dynamic | 3.1-lite high | gemma-4-31b-it default |
|---|---|---|---|---|---|---|---|---|
| role_match | 8 | 5 | 10 | 10 | 10 | 10 | 10 | 10 |
| skills_match | 3 | 2 | 3 | 3 | 5 | 4 | 4 | 2 |
| seniority_fit | 6 | 10 | 5 | 5 | 10 | 5 | 5 | 5 |
| location_eligibility | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | **64** | **58** | **68** | **68** | **82** | **72** | **72** | **66** |
| flags | none | none | none | none | none | none | none | none |

*Claude's reasons:* **role** Backend engineer role, though Go-focused distributed systems. **skills** No Go, DynamoDB, SQS or large-scale systems; only general backend overlap. **seniority** No years stated, but large-scale systems experience implied; candidate has 1 year. **location** Onsite hybrid in France, a target country; no sponsorship statement. **language** Only fluent English required; candidate is full professional.

## 4. Where a config differs from Claude by more than 15 points

| Config | Job view | Claude | Config | Difference |
|---|---|---|---|---|
| 3.5-lite high | #3923 Python Engineer Web Crawling | 61 | 80 | +19 |
| 3.1-lite none | #1913 Backend Engineer (Go) | 64 | 82 | +18 |
| 3.1-lite dynamic | #3923 Python Engineer Web Crawling | 61 | 88 | +27 |
| 3.1-lite high | #3923 Python Engineer Web Crawling | 61 | 88 | +27 |


## 5. Where a config differs from Claude by more than 15 points: who is right

Only four of the 42 runs differ by more than 15 points, all on the lite models. Written by me after seeing all outputs, from the listings and your profile.

**#3923 Python Engineer, Web Crawling (Claude 61): `3.1-lite dynamic` and `high` 88 (+27, the same run twice), `3.5-lite high` 80 (+19). Claude is closer, and my verdict on the job is skip.**
- The listing's core requirement is "hands-on web scraping at scale, including firsthand experience with anti-bot defenses", plus "strong Python: real production code, async" and one major cloud. Your pool has LLM-assisted extraction, FastAPI and Airflow, but no scraping, no async production Python and no cloud in production (LocalStack S3 and Terraform only).
- The high scores come from role_match 10 ("data extraction pipelines align with the Data Engineer track") and seniority_fit 10 or 5. `3.1-lite dynamic` even writes in its skills reason that you lack "professional experience with large-scale anti-bot scraping", the main requirement, and still gives skills 7. The reasoning is right and the arithmetic hides it.
- One point for the models: Claude's role_match 4 is probably a little harsh (extraction pipelines are partly data engineering; gemma gave 7). A fair score is nearer 65-70 than 61, still a borderline role you should not spend an application on.
- This is not only a lite problem: every config scores #3923 above Claude (70 to 88 vs 61). The weighted sum cannot express "the one thing the job is about is missing".

**#1913 Backend Engineer (Go) (Claude 64): `3.1-lite none` 82 (+18). Claude is right (skip).**
- It gave seniority_fit 10 ("does not specify a seniority level") although the listing asks for "experience designing and engineering large-scale systems" and on-call ownership, and skills_match 5 although Go, the named core language, is something you do not have. The same model with thinking (72) wrote the correct reasons (no Go, no AWS serverless, large-scale systems beyond your 1 year of backend work) and landed 8 points above Claude. Other configs: 58 to 72.

**#765 as the app renders it (Claude 76): no run is more than 15 points off (64 to 88), but all of them are wrong in the same way.** The German C1 line is not in the prompt, so every config, Claude included, scores a job you cannot take as a 64 to 88. With the full listing all eight raters agree on 35.

**#2418 and #1914: no real disagreement.** #2418 lands at 66 to 72 for all seven configs against Claude's 67 (in the earlier benchmarks the models disagreed there, gemma 86 vs lite 52; that spread is gone under this prompt, and I cannot say whether the prompt change or run-to-run variation did it). #1914 lands at 86 to 97 against Claude's 90.

## 6. Answers to your questions

- **Did each config catch #765's German C1 requirement?** From the prompt as the app renders it, **no config could, and none did**: the line is cut by the truncation. Two configs answered `language_required` present but soft: `3.5-lite none` quoted "Deutsch verhandlungssicher", which is example text from the prompt itself, not the listing (an unsupported quote that the verification step correctly kept soft), and `3.1-lite none` quoted "The entire job description is written in German". With the full listing, **all seven configs and Claude catch it: `language_required` present, hard flag, score 35.** Whether the new language-level rule was needed for that is untested: I did not run the v4 prompt on the full listing.
- **Which config is closest to Claude?** `gemma-4-31b-it` (mean absolute difference 4.2 as rendered, 3.8 with the full listing), then `3.5-lite none` (5.0 / 4.6). `3.1-lite` is the furthest (9.4 to 11.0). No config reproduces Claude's exact order: the top (#1914) agrees everywhere, and with the full listing so does the bottom (#765), but the middle three (Claude 67 / 64 / 61, six points apart) get reshuffled, mostly by #3923 moving up. Pairs ordered like Claude, out of 10 with the full listing: 8 for `3.5-lite none`, `3.5-lite high` and `3.1-lite none`, 7 to 7.5 for the rest.
- **Did thinking make a real difference? Not in a useful direction.**
  - `3.5-lite`: no thinking 5.0 / 4.6, dynamic 6.0 / 4.4, high 7.0 / 5.8 (rendered / full). Thinking cost about 2,100 to 2,600 thinking tokens per job and a few seconds, without getting closer to Claude.
  - `3.1-lite`: no thinking 9.4 / 7.0, dynamic and high 11.0 / 8.6. **Dynamic (budget -1) and `thinkingLevel: high` are the same run on this model** (identical thinking tokens and scores on every job). One job (#1913) triggered 62,913 thinking tokens and 138 to 159 s, which is why the mean (13,620) is far above the median (1,057). Thinking helped that model on #1913 (82 to 72) and moved #3923 further from Claude (73 to 88).
  - `gemma-4-31b-it` always thinks (median about 1,100 tokens) and is closest, but I cannot separate that from model quality.
  - Five jobs and one run each: read these as direction, not proof.
- **Timing.** All seven configs ran in parallel, and times are roughly double those of the earlier benchmarks (for example `3.5-lite none` 21.8 s vs 8.8 s), so use them only relatively: no-thinking lite is fastest, gemma slowest (80 s).
- **Other:** no config raised a hard flag on the other four jobs; gemma's answers were 0/5 valid as returned and 5/5 after the app's parse (fence and wrapper), as before.

## 7. What this changes, and what needs your decision

1. **The truncation is the real problem behind the "recall gap" I reported earlier, and I was wrong about it.** `fit.truncate_description` keeps the first 4,200 and last 1,800 characters of any listing over 6,000 and drops the middle, where requirements often are. 35 of the 144 non-duplicate full listings (a quarter) are affected, plus 2 summaries. Options: raise the limit (the longest listing is 9,309 characters, about 2,700 tokens, which is no problem for the Gemini models; the Ollama scorer's `num_ctx` of 8,192 would be tight), or drop low-value sections (benefits, perks, boilerplate) instead of the middle. Either way the scores of those long listings are stale and should be rescored. I changed nothing.
2. **My earlier reports state the wrong cause.** `scoring-benchmark-v4-2026-10-20.md` (sections 6 and 7) and `scoring-benchmark-lite-variants-2026-10-20.md` (sections 3, 6 and 7) say the models missed #765's C1 requirement because of the prompt wording, and that a v5 language rule is a prerequisite for choosing a bulk model. I have added a correction note at the top of both. The v5 language rule may still be a good idea, but this test does not show that it is needed.
3. **The additive score cannot express a missing must-have** (#3923, and #1913 on one config). That is a design choice for the scoring formula, not something to fix in the prompt; a "core requirement missing" cap on skills would be one option. Not done.
4. **For the bulk model:** among the lite models `gemini-3.5-flash-lite` without thinking is the closest to Claude's judgment and the cheapest; thinking did not help; `gemini-3.1-flash-lite` was both the furthest from Claude and the one with the runaway-thinking tail. `gemma-4-31b-it` is the closest overall but about 80 s per job.
