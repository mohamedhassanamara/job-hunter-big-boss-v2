# Scoring benchmark v4: hard-flag fix, 20 jobs, 2 models (2026-10-20)

> **Correction (added after the judgment test, `judgment-test-2026-10-20.md`):** this report says the models "missed" #765's German C1 requirement and attributes that to the prompt (`when in doubt, answer false`). That is wrong. The app truncates listings over 6,000 characters (`fit.truncate_description`) and #765's `Sehr gute Deutschkenntnisse (C1)` line, at character 4,410 of 6,908, falls in the removed middle, so **no model ever saw it**. Given the full listing, all seven configurations and Claude flag it as a hard flag (score 35). Sections 6 and 7 below, where they treat this as a recall gap or a reason for a v5 language rule, should be read with that in mind.

Test only. **Nothing in the database changed** (no scores written, no setting or default model changed). The code, prompt, tests and docs are changed in the working tree and not committed. Prompt `fit_score/v4` (this run) against `fit_score/v3` (previous report), same 20 jobs, same current experience pool (`3812127ca20f8860`), temperature 0, same models and settings as the v3 follow-up. Raw: `docs/reports/raw/v4-2026-10-20/`; v3 numbers come from `docs/reports/raw/followup-2026-10-20/`.

## 0. What changed

- **Prompt v4** (`app/prompts/fit_score.md`, hash registered in `versions.json`): (1) flag checks are true only when the listing states the requirement in so many words and the evidence is the words that state it; an office, city, country name, on-site/hybrid mode, perks, `we are based in`, a sponsorship/relocation offer or the posting's language never count. (2) Location: on-site/hybrid in a target country scores 8 (10 with sponsorship, relocation or fully remote; 0 only when a requirement is stated). (3) Short output: reasons ≤ 15 words, evidence `""` unless a rule asks for it (a score below 5 on location or language, or a flag that is present), strengths ≤ 6 words each, summary ≤ 20 words.
- **Code check** (`fit.requirement_stated`, used by `flag_severity_detail`, `build_record` and `recompute`): a flag that would be hard (work authorization, no sponsorship, must-be-based-in, nationality, language) stays hard only if its quote contains requirement wording for that type (e.g. a negation + sponsor/visa/permit; right to work / work permit / authorization; `must be located/resident`, `already living`, `resident in`; nationals/citizens + only, or Emiratization-type words; a language + fluent/native/required/verhandlungssicher…). Otherwise it is soft, gets a `severity_note` and a log line (`hard flag … downgraded to soft`). Also fixed in code: `fit.languages_mentioned` did not recognise German compounds (`Deutschkenntnisse`, `deutschsprachig`; never `Deutschland`), so an explicit `Sehr gute Deutschkenntnisse (C1)` could never be a hard language flag. Tests: new cases with the real quotes from the previous benchmark; the full suite passes (848 tests) and lint is clean.
- Two things the v4 rules do not do: they do not make a posting written in German count as a stated requirement (the `language_requirements` sub-score still sees it, but it is only 10% of the score, so those jobs are no longer capped), and a hard flag the model never raises is not rescued by the code check.

## 1. Reliability and speed (v4, with v3 in brackets)

| Metric | 3.1-flash-lite | gemma-4-31b-it |
|---|---|---|
| Jobs run | 20 | 20 |
| Valid JSON on first try | 20/20 (20/20) | 0/20 (0/20) |
| Valid after the app's parse | 20/20 (20/20) | 20/20 (20/20) |
| Retries (429/500/503) | 7 on 4 jobs (0 on 0) | 13 on 7 jobs (13 on 7) |
| Jobs with no answer | 0 (0) | 0 (0) |
| Time per job (s): mean / median / max | 15.9 / 8.9 / 114.8 (11.6 / 10.4 / 24.7) | 81.4 / 71.8 / 147.6 (82.3 / 84.5 / 113.4) |
| Input tokens per job | 4913 (4715) | 5673 (5475) |
| Output tokens per job | 537 (701) | 529 (704) |
| Thinking tokens per job | 0 (0) | 1280 (1279) |
| Evidence quotes found (job, experience or prompt metadata) | 33/34 (134/139) | 22/22 (120/121) |
| Evidence quotes per job | 1.7 (7.0) | 1.1 (6.0) |

The same parse rules are used for both versions. Times are the API call only.

## 2. Flags raised per model

`hard` = caps the score. `downgraded` = the model raised it, the quote was found in the listing, and the code check kept it soft (v4 only; in v3 this did not exist). v3 columns are re-evaluated with the **old** rule, i.e. exactly what the previous report counted.

| | 3.1-flash-lite v4 | 3.1-flash-lite v3 | gemma-4-31b-it v4 | gemma-4-31b-it v3 |
|---|---|---|---|---|
| Jobs with a hard flag (of 20) | 2 | 9 | 2 | 5 |
| Hard flags | 3 | 13 | 3 | 8 |
| Soft flags | 10 | 19 | 10 | 12 |
| Downgraded by the code check | 1 | 0 | 1 | 0 |
| Jobs scored exactly 35 (the cap) | 1 | 8 | 1 | 4 |
| All flags (hard + soft) | 13 | 32 | 13 | 20 |

Hard flags by type, v4: 3.1-flash-lite: no_visa_sponsorship 1, must_be_based_in 1, language_required 1; gemma-4-31b-it: no_visa_sponsorship 1, must_be_based_in 1, language_required 1.

### Every hard flag raised in v4 (judge the quotes yourself)

**3.1-flash-lite**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “Remote - US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”

**gemma-4-31b-it**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “ein sehr gutes mündliches und schriftliches Deutsch erforderlich”

### Flags the code check downgraded in v4

**3.1-flash-lite**

- #765 AI Engineer (m/w/d): `must_be_based_in`: “Remote & Home-Office innerhalb Deutschlands”

**gemma-4-31b-it**

- #2409 Senior Principal Software Engineer, Vertica: `work_authorization_required`: “US based candidates only”

### Flags that were hard in v3 and are gone in v4, same job and model

**3.1-flash-lite**

- #765 AI Engineer (m/w/d): v3 hard ['must_be_based_in', 'work_authorization_required'] → v4 no hard flag; score 35 → 66
- #1913 Backend Engineer (Go): v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 67
- #1914 Location Data engineer: v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 94
- #1921 Senior Data Engineer - BeReal: v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 67
- #2409 Senior Principal Software Engineer, Vertica: v3 hard ['must_be_based_in', 'no_visa_sponsorship', 'work_authorization_required'] → v4 ['must_be_based_in', 'no_visa_sponsorship']; score 10 → 10
- #2410 Data Engineer: v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 82
- #2441 Data Engineer Kubernetes (m/w/d): v3 hard ['language_required', 'must_be_based_in'] → v4 ['language_required']; score 35 → 35
- #3923 Python Engineer – Web Crawling & Data Extraction (: v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 67
- #3924 Senior Data Engineer (x/f/m): v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 67

**gemma-4-31b-it**

- #765 AI Engineer (m/w/d): v3 hard ['language_required'] → v4 no hard flag; score 35 → 81
- #1913 Backend Engineer (Go): v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 66
- #2409 Senior Principal Software Engineer, Vertica: v3 hard ['must_be_based_in', 'no_visa_sponsorship', 'work_authorization_required'] → v4 ['must_be_based_in', 'no_visa_sponsorship']; score 25 → 31
- #2418 Senior Fullstack Engineer — Mobile Healthcare Plat: v3 hard ['must_be_based_in'] → v4 no hard flag; score 35 → 86
- #2441 Data Engineer Kubernetes (m/w/d): v3 hard ['language_required', 'must_be_based_in'] → v4 ['language_required']; score 35 → 35

## 3. Do the two models agree? Do they agree with the stored scores?

Jobs scored by both in v4: **20/20**. Spearman uses average ranks for ties.

| Pair | v4 Spearman ρ | v4 Kendall τ-b | v4 mean abs. diff | v3 Spearman ρ | v3 mean abs. diff |
|---|---|---|---|---|---|
| 3.1-flash-lite vs gemma-4-31b-it | 0.73 | 0.60 | 10.1 | 0.50 | 16.8 |
| 3.1-flash-lite vs stored | 0.76 | 0.63 | 10.0 | 0.35 | 19.1 |
| gemma-4-31b-it vs stored | 0.64 | 0.51 | 12.9 | 0.66 | 11.5 |

The stored scores are `gemma4:31b-cloud` (older ones `gemma4:12b`) under prompt v3 and an older experience pool: a reference, not ground truth; many of them are capped at 35 for the reasons this fix removes.

### All 20 jobs

| Job | Title (company) | Stored | 3.1-flash-lite v3 | 3.1-flash-lite v4 | gemma-4-31b-it v3 | gemma-4-31b-it v4 |
|---|---|---|---|---|---|---|
| #1914 | Location Data engineer (Amo) | 94 | 35 | **94** | 100* | **100*** |
| #794 | Data Analytics Engineer (They/She/He) (Delivery Hero (talabat)) | 90 | 85 | **84** | 79* | **94*** |
| #2410 | Data Engineer (Mentor Talent Acquisitio) | 86 | 35 | **82** | 68* | **80*** |
| #765 | AI Engineer (m/w/d) (Nerdware) | 82 | 35 | **66** | 35* | **81*** |
| #5139 | Software Engineer, AI Coding Tasks (Askable) | 82 | 85 | **85** | 100* | **97*** |
| #3943 | O&M Data Engineer – Munich (Fixed Term 2 years) (Sungrow Europe - Welcome) | 78 | 62 | **67** | 52* | **61*** |
| #3924 | Senior Data Engineer (x/f/m) (Doctolib) | 76 | 35 | **67** | 70* | **70*** |
| #1921 | Senior Data Engineer - BeReal (BeReal) | 68 | 35 | **67** | 70* | **67*** |
| #1927 | Senior Backend Engineer - Scoring & Computation Engine (m/ (Statista) | 66 | 62 | **52** | 62* | **67*** |
| #2431 | Senior AI Engineer, Agents and Platform (f/m/d) (Xu De) | 62 | 62 | **67** | 66* | **67*** |
| #5319 | Senior ML Backend Engineer - Search & Recommendations (Salla) | 62 | 48 | **67** | 56* | **56*** |
| #3923 | Python Engineer – Web Crawling & Data Extraction (m/f/d) (Certivity) | 55 | 35 | **67** | 78* | **82*** |
| #797 | Senior AI Quality Engineer (Foodics) | 54 | 48 | **61** | 55* | **40*** |
| #2427 | Propulsion Data & Modeling Engineer (The Exploration Company) | 38 | 32 | **32** | 32* | **25*** |
| #1913 | Backend Engineer (Go) (Prelude) | 35 | 35 | **67** | 35* | **66*** |
| #2418 | Senior Fullstack Engineer — Mobile Healthcare Platform (Snke) | 35 | 70 | **52** | 35* | **86*** |
| #2441 | Data Engineer Kubernetes (m/w/d) (citema systems GmbH) | 35 | 35 | **35** | 35* | **35*** |
| #5316 | Analytics Engineer II (Delivery Hero (talabat)) | 35 | 62 | **67** | 79* | **80*** |
| #3921 | Sr. Technical Program Manager (TPM) - AI Programs, Vinted  (Vinteden) | 32 | 32 | **37** | 24* | **28*** |
| #2409 | Senior Principal Software Engineer, Vertica (Ladders) | 25 | 10 | **10** | 25* | **31*** |

`*` = not valid as returned, accepted by the app's parse.

## 4. Top 10 by each model (v4), side by side

Ties broken by job id. Only the 20 sample jobs are ranked.

| # | 3.1-flash-lite | gemma-4-31b-it |
|---|---|---|
| 1 | **94** #1914 Location Data engineer (Amo), stored 94 | **100** #1914 Location Data engineer (Amo), stored 94 |
| 2 | **85** #5139 Software Engineer, AI Coding Tasks (Askable), stored 82 | **97** #5139 Software Engineer, AI Coding Tasks (Askable), stored 82 |
| 3 | **84** #794 Data Analytics Engineer (They/She/He) (Delivery Hero (talab), stored 90 | **94** #794 Data Analytics Engineer (They/She/He) (Delivery Hero (talab), stored 90 |
| 4 | **82** #2410 Data Engineer (Mentor Talent Acquis), stored 86 | **86** #2418 Senior Fullstack Engineer — Mobile Healthcare Pl (Snke), stored 35 ◦ |
| 5 | **67** #1913 Backend Engineer (Go) (Prelude), stored 35 ◦ | **82** #3923 Python Engineer – Web Crawling & Data Extraction (Certivity), stored 55 |
| 6 | **67** #1921 Senior Data Engineer - BeReal (BeReal), stored 68 | **81** #765 AI Engineer (m/w/d) (Nerdware), stored 82 ◦ |
| 7 | **67** #2431 Senior AI Engineer, Agents and Platform (f/m/d) (Xu De), stored 62 ◦ | **80** #2410 Data Engineer (Mentor Talent Acquis), stored 86 |
| 8 | **67** #3923 Python Engineer – Web Crawling & Data Extraction (Certivity), stored 55 | **80** #5316 Analytics Engineer II (Delivery Hero (talab), stored 35 ◦ |
| 9 | **67** #3924 Senior Data Engineer (x/f/m) (Doctolib), stored 76 | **70** #3924 Senior Data Engineer (x/f/m) (Doctolib), stored 76 |
| 10 | **67** #3943 O&M Data Engineer – Munich (Fixed Term 2 years) (Sungrow Europe - Wel), stored 78 ◦ | **67** #1921 Senior Data Engineer - BeReal (BeReal), stored 68 |

◦ = in this model's top 10 only. v4 overlap between the two top 10s: **7/10** (v3: 5/10). Overlap with the stored top 10: 3.1-flash-lite 8/10 (v3 6/10), gemma-4-31b-it 7/10 (v3 8/10).

<details><summary>Reasons for the 3.1-flash-lite top 5 (v4)</summary>

- **#1914 Location Data engineer** → 94: A strong candidate with relevant technical skills and projects who fits the role and relocation requirements perfectly.  
  sub-scores: role_match 10, skills_match 8, seniority_fit 10, location_eligibility 10, language_requirements 10  
  strengths: Python and SQL proficiency | dbt and DuckDB experience | Data pipeline orchestration  
  gaps: No professional Spark experience | Limited production data engineering tenure  
  flags: none
- **#5139 Software Engineer, AI Coding Tasks** → 85: The candidate is a strong fit for this remote software engineering role given their technical stack and experience.  
  sub-scores: role_match 5, skills_match 10, seniority_fit 10, location_eligibility 10, language_requirements 10  
  strengths: Python and Java proficiency | Automated testing expertise | Docker and Git skills  
  gaps: Limited open-source contributions | No formal AI evaluation experience  
  flags: none
- **#794 Data Analytics Engineer (They/She/He)** → 84: The candidate is a strong technical match for this Analytics Engineering role, though slightly junior in experience.  
  sub-scores: role_match 10, skills_match 8, seniority_fit 5, location_eligibility 8, language_requirements 10  
  strengths: Python and SQL proficiency | LLM and automation experience | Collaborative engineering practices  
  gaps: Limited professional data experience | Lack of Looker experience  
  flags: none
- **#2410 Data Engineer** → 82: A motivated candidate with strong foundational data engineering skills seeking to transition into a professional data role.  
  sub-scores: role_match 10, skills_match 5, seniority_fit 10, location_eligibility 8, language_requirements 10  
  strengths: Python and SQL proficiency | Data pipeline orchestration | Docker and CI/CD  
  gaps: Production AWS experience | Medallion architecture experience | Professional data engineering tenure  
  flags: none
- **#1913 Backend Engineer (Go)** → 67: The candidate is a capable backend engineer with relevant experience, though they lack the specific Go stack required.  
  sub-scores: role_match 5, skills_match 5, seniority_fit 10, location_eligibility 8, language_requirements 10  
  strengths: Backend development | API design | System architecture  
  gaps: No Go experience | No DynamoDB experience | No AWS Lambda experience  
  flags: none

</details>

<details><summary>Reasons for the gemma-4-31b-it top 5 (v4)</summary>

- **#1914 Location Data engineer** → 100: Excellent match with the required data stack and full alignment on visa sponsorship and location.  
  sub-scores: role_match 10, skills_match 10, seniority_fit 10, location_eligibility 10, language_requirements 10  
  strengths: dbt | DuckDB | Apache Airflow  
  gaps: Spark | BigQuery | ClickHouse  
  flags: none
- **#5139 Software Engineer, AI Coding Tasks** → 97: Highly qualified software engineer with AI experience meeting all technical and seniority requirements for this remote role.  
  sub-scores: role_match 10, skills_match 9, seniority_fit 10, location_eligibility 10, language_requirements 10  
  strengths: Python, Java, C++ | Docker, Linux, Git | LLM and AI experience  
  gaps: Explicit open-source contributions  
  flags: none
- **#794 Data Analytics Engineer (They/She/He)** → 94: Strong technical match for an Analytics Engineer I role with relevant data and AI project experience.  
  sub-scores: role_match 10, skills_match 9, seniority_fit 10, location_eligibility 8, language_requirements 10  
  strengths: Python and SQL | LLM and RAG | dbt and Airflow  
  gaps: Looker | GCP | n8n or Make  
  flags: none
- **#2418 Senior Fullstack Engineer — Mobile Healthcare Platform** → 86: Technically strong match for the Flutter/Backend requirements, though slightly under-experienced for a Senior role.  
  sub-scores: role_match 10, skills_match 9, seniority_fit 5, location_eligibility 8, language_requirements 10  
  strengths: Flutter and Dart | Clean Architecture | Python and Java backend  
  gaps: Healthcare interoperability standards | Senior-level experience | German language  
  flags: none
- **#3923 Python Engineer – Web Crawling & Data Extraction (m/f/d)** → 82: Experienced software engineer with strong Python and AI skills, but lacks the required specialized web scraping expertise.  
  sub-scores: role_match 10, skills_match 5, seniority_fit 10, location_eligibility 8, language_requirements 10  
  strengths: Python | Docker | Java/Spring Boot  
  gaps: Web scraping at scale | Anti-bot defenses | GCP/Azure  
  flags: none

</details>

## 5. Stored scores capped at 35: how many lose the cap (code check only, no model calls)

Method: each job's latest OK score; every stored hard flag is re-evaluated with the new `fit.recompute` (same function the app uses when you change weights); nothing was written. This measures only the **code check** (item 3). The prompt changes (items 1, 2 and 4) need new model calls and are what the benchmark above tests.

| | Jobs |
|---|---|
| Stored scores equal to the cap (35) | 1975 of 5319 |
| of those, with a hard flag | 1967 |
| of those, 35 without any hard flag (a natural 35) | 8 |
| **lose the cap under the new code check** | **1876** (95% of the 35s) |
| keep the cap (at least one hard flag still states the requirement) | 91 |

Hard flags among the capped jobs, before → after: `must_be_based_in` 905 → 11; `language_required` 1050 → 49; `no_visa_sponsorship` 10 → 5; `work_authorization_required` 469 → 26; `nationality_restricted` 21 → 19.

Where the lost caps are: adzuna 1675 of 1724; arbeitnow 42 of 77; wttj 158 of 164; remotive 0 of 1; boards 1 of 1 (by source: jobs losing the cap / jobs with a hard flag); by listing length: snippet 1675 of 1724; full 43 of 79; summary 158 of 164.

The jobs that lose the cap would score, from their stored sub-scores alone (so before any v4 model run): ≥ 80: 327, 65-79: 746, 50-64: 680, < 50: 123 (mean 66.0). This is large: with the stored sub-scores, these jobs would flood the top of Discover, so rescoring all of them with one v4 model (not just recomputing) is worth doing before you rely on the ranking. A further 113 stored rows carry a hard flag but score below 35 already, so the cap does not bind there.

`recompute_all` runs when you change weights, cap or work authorization in Settings and rewrites stored scores and flags. After this code change, the next such edit will apply the new flag rule to all stored flags (the counts above). Until then nothing changes.


## 6. Observations

**Caveats first.** 20 jobs, one run each, temperature 0 (which is not fully deterministic). The stored scores are another LLM's output under an older prompt and experience pool, so agreement with them is a reference, not proof of correctness. Read the two top 10s yourself.

**The hard-flag fix works on this sample.**
- Jobs with a hard flag: `gemini-3.1-flash-lite` 9 → 2, `gemma-4-31b-it` 5 → 2. Jobs scored exactly 35: 8 → 1 and 4 → 1. Hard flags overall: 13 → 3 and 8 → 3.
- Both models now raise the same hard flags, and I read the quotes: #2409 (`no visa sponsorship available`, plus `US based candidates only`) and #2441 (`… sehr gutes mündliches und schriftliches Deutsch erforderlich`). All three state a real requirement. #2409 is a low-fit job anyway (10 and 31).
- The jobs that were capped for the wrong reason in v3 now score on their sub-scores. For example #1914 (stored 94): 35 → 94 with the lite model; #2410: 35 → 82; #3924: 35 → 67; #1921: 35 → 67.
- The code check downgraded only 2 flags in v4 (`Remote & Home-Office innerhalb Deutschlands` for the lite model on #765, and a `work_authorization_required` flag quoting `US based candidates only` for gemma on #2409). Most of the improvement therefore comes from the prompt: the models simply stopped raising these flags. The code check is the safety net for when they do.
- While reading the downgrades I found two defects in my own check and fixed them: `US based candidates only` is a residency restriction and was being downgraded (pattern added), and German compounds such as `Deutschkenntnisse` or `deutschsprachig` were not recognised as naming a language, so an explicit language requirement phrased that way could never be a hard flag (fixed; `Deutschland` still does not match). Both have tests.

**A recall gap the fix did not close.** #765's listing says `Sehr gute Deutschkenntnisse (C1) in Wort und Schrift`. In v4 neither model answered `language_required` present for it: the lite model scored language 5 with the reason that the posting is in German, gemma scored 0 but raised no flag. So #765 now scores 66 (lite) and 81 (gemma) although you do not speak German at C1. In v3 gemma capped it, with a quote that did not state the requirement (`Wir suchen erfahrene AI Engineers`), so it was right by accident. Across the 20 jobs there were two explicit German requirements: both models caught #2441 and both missed #765. That is one example, not a rate, but it points at the instruction `When in doubt, answer false`. A possible v5 wording is to say explicitly that a stated language level (C1, fluent, `Deutschkenntnisse`) counts as stating the requirement. I have not made that change: it needs another prompt version and a rerun, so it is your call.

**Agreement.**
- Lite vs stored: Spearman 0.35 → 0.76. Lite vs gemma: 0.50 → 0.73. Gemma vs stored: 0.66 → 0.64 (flat).
- Top-10 overlap between the models: 5/10 → 7/10. With the stored top 10: lite 6 → 8, gemma 8 → 7.

**Resolution of the ranking.** The lite model's scores are coarse: 8 of its 20 jobs score exactly 67 (sub-scores built from 0 / 5 / 8 / 10, typically skills 5 plus the same location and language values), and it uses 12 distinct scores over 20 jobs; gemma uses 17. In the lite top 10, positions 5 to 10 are a six-way tie at 67, broken only by job id in my table, so the order there carries no information. Gemma separates more but tops out at 100 / 97 / 94 and gave #2418 (Senior Fullstack Mobile Healthcare, stored 35) an 86 where the lite model says 52; that is one to check against your own judgment.

**Output size and speed (v4 vs v3).** Output tokens per job fell about a quarter (lite 701 → 537, gemma 704 → 529) and evidence quotes per job from 7.0 / 6.0 to 1.7 / 1.1, and the quotes that remain are found in the listing (33/34 and 22/22). Gemma's time did not move (81 s, dominated by about 1,280 thinking tokens it spends regardless). The lite model's median time improved (10.4 → 8.9 s) but its mean worsened (11.6 → 15.9 s) because of seven 503 responses on four jobs (max 114.8 s); that was the service, not the prompt, but it is a reminder that the free tier is not always instant.

**Format validity is unchanged.** Lite: 20/20 valid as returned. Gemma: 0/20 valid as returned, 20/20 accepted by the app's parse (fence and `properties` wrapper).

**Stored scores (section 5).** 1,876 of the 1,975 capped jobs (95%) lose the cap under the code check alone, 91 keep it, and 8 are a natural 35. 1,675 of the lost caps are Adzuna snippets, which is why `must_be_based_in` drops from 905 to 11. Nothing was written; these are the numbers `recompute_all` would produce the next time you change weights, cap or work authorization.

## 7. State of the working tree and what needs your decision

- Changed, not committed: `backend/app/prompts/fit_score.md` (v4) and `versions.json`, `backend/app/services/fit.py`, `backend/tests/test_fit.py`, `docs/SPEC.md`, `docs/DATA_MODEL.md`, `CLAUDE.md`, and the two reports with raw data under `docs/reports/`. The suite passes (848 tests), lint is clean. No `make eval` was run (it calls the real model and would write to `data/eval/`).
- The database is untouched and the bulk scorer is still `gemma4:31b-cloud`. New jobs scored from now on would use prompt v4 with whatever model is configured.
- Decisions for you: (1) whether to add the v5 wording for explicit language levels before choosing a model; (2) which model becomes the bulk scorer; (3) whether to rescore everything with it, since recomputing alone would only change jobs whose stored flags were the problem, not the v3 sub-scores (for example location 0 or 5 for on-site jobs, which v4 scores 8).
