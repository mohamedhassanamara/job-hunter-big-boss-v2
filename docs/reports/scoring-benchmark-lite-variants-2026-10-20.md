# Scoring benchmark: lite model variants (2026-10-20)

> **Correction (added after the judgment test, `judgment-test-2026-10-20.md`):** the #765 columns and the statements in sections 3, 6 and 7 that no configuration "caught" its German C1 requirement, and that a v5 language rule is therefore a prerequisite for choosing a bulk model, are wrong. The requirement was never in the prompt: the app truncates listings over 6,000 characters and cut that line (character 4,410 of 6,908). With the full listing every configuration tested later catches it. The v5 wording may still be useful, but these results do not show that it is needed.

Test only: **no database writes**, no setting or default changed, nothing committed by this step. Same 20 jobs as the v4 benchmark, same current experience pool (`3812127ca20f8860`), temperature 0, native JSON schema, prompt `fit_score/v4` unless stated. Raw: `docs/reports/raw/lite-variants-2026-10-20/` (new runs) and `docs/reports/raw/v4-2026-10-20/` (reused runs).

## 0. What was run

| Key | Model | Prompt | Thinking | Source |
|---|---|---|---|---|
| gemma v4 | `gemma-4-31b-it` | v4 | its own (about 1,280 thinking tokens per job, not controllable) | existing v4 run (reused) |
| 3.1 a | `gemini-3.1-flash-lite` | v4 | none | existing v4 run (reused) |
| 3.1 b | `gemini-3.1-flash-lite` | v4 | budget 1024 | **not run: see below** |
| 3.1 c | `gemini-3.1-flash-lite` | v4b | none | new |
| 3.5 a | `gemini-3.5-flash-lite` | v4 | none | new |
| 3.5 b | `gemini-3.5-flash-lite` | v4 | budget 1024 | new |
| 3.5 c | `gemini-3.5-flash-lite` | v4b | none | new |

**Thinking-budget check (one real job, v4 prompt, native schema):**

| Model | `thinkingBudget: 1024` | dynamic (`-1`) | `thinkingLevel: high` | no thinkingConfig |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` (metadata `thinking: true`) | accepted, 961 thinking tokens | 2,443 | 2,257 | 0 |
| `gemini-3.1-flash-lite` (metadata `thinking: true`) | accepted (HTTP 200) but **0 thinking tokens** (also 0 with 4096 and with `includeThoughts`) | 1,157 | 1,157 | 0 |

So 3.5-flash-lite honours a budget. 3.1-flash-lite thinks (dynamic budget and `thinkingLevel` both produce thinking tokens) but ignores a fixed budget of 1024: the request succeeds and nothing is thought. As you asked, variant b is skipped for 3.1-flash-lite. If you want thinking on that model, `thinkingLevel` (low/medium/high) or a dynamic budget are what works; I did not run them.

**v4b** is the v4 system prompt with one sentence replaced (`raw/lite-variants-2026-10-20/_prompt_v4b_change.txt`): sub-scores may be any integer 0-10, the anchors are examples (use 1-4, 6-7, 9 between anchors). The repo prompt is unchanged (still v4); v4b exists only in this test.

## 1. Reliability, speed and tokens

| Metric | gemma-4-31b-it v4 | 3.1-lite v4 (a) | 3.1-lite v4b (c) | 3.5-lite v4 (a) | 3.5-lite v4 + budget 1024 (b) | 3.5-lite v4b (c) |
|---|---|---|---|---|---|---|
| Jobs run | 20 | 20 | 20 | 20 | 20 | 20 |
| Valid JSON as returned | 0/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| Valid after the app's parse | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| Retries (429/500/503) | 13 on 7 jobs | 7 on 4 jobs | 14 on 10 jobs | 0 on 0 jobs | 0 on 0 jobs | 0 on 0 jobs |
| Jobs with no answer | 0 | 0 | 0 | 0 | 0 | 0 |
| Time per job (s): mean / median / max | 81.4 / 71.8 / 147.6 | 15.9 / 8.9 / 114.8 | 25.7 / 18.8 / 84.6 | 8.8 / 7.8 / 27.2 | 10.4 / 10.1 / 15.9 | 5.8 / 4.8 / 10.3 |
| Input tokens per job | 5673 | 4913 | 5005 | 4913 | 4913 | 5005 |
| Output tokens per job | 529 | 537 | 556 | 527 | 498 | 548 |
| Thinking tokens per job | 1280 | 0 | 0 | 0 | 1329 | 0 |

Times are the API call that succeeded (retried 503s are not included).

## 2. Distinct scores, ties in the top 10, agreement

| Metric | gemma-4-31b-it v4 | 3.1-lite v4 (a) | 3.1-lite v4b (c) | 3.5-lite v4 (a) | 3.5-lite v4 + budget 1024 (b) | 3.5-lite v4b (c) |
|---|---|---|---|---|---|---|
| Distinct scores (of 20) | 17 | 12 | 16 | 13 | 13 | 16 |
| Most common score (jobs with it) | 67 (3) | 67 (8) | 67 (3) | 67 (4) | 74 (4) | 72 (2) |
| Top 10: jobs sharing a score with another top-10 job | 2 | 6 | 5 | 6 | 6 | 6 |
| Top 10: largest tie group / distinct scores | 2 / 9 | 6 / 5 | 3 / 7 | 3 / 6 | 4 / 6 | 2 / 7 |
| Tie across the 10th/11th place | yes | yes | no | yes | yes | no |
| Spearman ρ vs gemma v4 | – | 0.73 | 0.78 | 0.70 | 0.88 | 0.68 |
| Kendall τ-b vs gemma v4 | – | 0.60 | 0.64 | 0.51 | 0.75 | 0.53 |
| Mean abs. score diff vs gemma v4 | – | 10.1 | 8.9 | 10.1 | 7.2 | 10.5 |
| Spearman ρ vs stored scores | 0.64 | 0.76 | 0.79 | 0.73 | 0.56 | 0.72 |
| Kendall τ-b vs stored scores | 0.51 | 0.63 | 0.69 | 0.61 | 0.51 | 0.57 |
| Top-10 overlap with gemma v4 | – | 7/10 | 7/10 | 6/10 | 8/10 | 7/10 |
| Top-10 overlap with the stored top 10 | 7/10 | 8/10 | 9/10 | 8/10 | 6/10 | 8/10 |

Spearman uses average ranks for ties, so heavy tying lowers the usable information in a ranking even where ρ looks fine. Ties inside the top 10 are broken by job id in the lists below, which means the order of tied jobs is arbitrary.

## 3. Hard flags raised, and #765's German C1 requirement

#765's listing says `Sehr gute Deutschkenntnisse (C1) in Wort und Schrift`. "Caught" = the model answered `language_required` present and the resulting flag is hard (the code now recognises `Deutschkenntnisse`).

| Config | Jobs with a hard flag | Hard flags | #765: language_required present | #765: hard flag | #765 language score | #765 final score |
|---|---|---|---|---|---|---|
| gemma-4-31b-it v4 | 2 | 3 | no | no | 0 | 81 |
| 3.1-lite v4 (a) | 2 | 3 | no | no | 5 | 66 |
| 3.1-lite v4b (c) | 2 | 3 | no | no | 5 | 64 |
| 3.5-lite v4 (a) | 2 | 3 | no | no | 0 | 64 |
| 3.5-lite v4 + budget 1024 (b) | 2 | 3 | no | no | 0 | 70 |
| 3.5-lite v4b (c) | 2 | 3 | no | no | 0 | 72 |

**gemma-4-31b-it v4**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “ein sehr gutes mündliches und schriftliches Deutsch erforderlich”
- (downgraded to soft by the code check) #2409: `work_authorization_required`: “US based candidates only”

**3.1-lite v4 (a)**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “Remote - US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”
- (downgraded to soft by the code check) #765: `must_be_based_in`: “Remote & Home-Office innerhalb Deutschlands”

**3.1-lite v4b (c)**

- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”
- (downgraded to soft by the code check) #765: `must_be_based_in`: “Remote & Home-Office innerhalb Deutschlands”

**3.5-lite v4 (a)**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”

**3.5-lite v4 + budget 1024 (b)**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”

**3.5-lite v4b (c)**

- #2409 Senior Principal Software Engineer, Vertica: `no_visa_sponsorship`: “no visa sponsorship available”
- #2409 Senior Principal Software Engineer, Vertica: `must_be_based_in`: “US based candidates only”
- #2441 Data Engineer Kubernetes (m/w/d): `language_required`: “Für die effektive Kommunikation im Projektumfeld sowie mit unseren deutschsprachigen Kunden ist ein sehr gutes mündliches und schriftliches Deutsch erforderlich”

## 4. All 20 jobs

| Job | Title | Stored | gemma-4-31b-it v4 | 3.1-lite v4 (a) | 3.1-lite v4b (c) | 3.5-lite v4 (a) | 3.5-lite v4 + budget 1024 (b) | 3.5-lite v4b (c) |
|---|---|---|---|---|---|---|---|---|
| #1914 | Location Data engineer | 94 | 100 | 94 | 94 | 100 | 92 | 88 |
| #794 | Data Analytics Engineer (They/She/He) | 90 | 94 | 84 | 82 | 84 | 88 | 84 |
| #2410 | Data Engineer | 86 | 80 | 82 | 84 | 82 | 70 | 91 |
| #765 | AI Engineer (m/w/d) | 82 | 81 | 66 | 64 | 64 | 70 | 72 |
| #5139 | Software Engineer, AI Coding Tasks | 82 | 97 | 85 | 79 | 85 | 85 | 76 |
| #3943 | O&M Data Engineer – Munich (Fixed Term 2 yea | 78 | 61 | 67 | 67 | 82 | 74 | 88 |
| #3924 | Senior Data Engineer (x/f/m) | 76 | 70 | 67 | 73 | 67 | 70 | 70 |
| #1921 | Senior Data Engineer - BeReal | 68 | 67 | 67 | 73 | 67 | 67 | 76 |
| #1927 | Senior Backend Engineer - Scoring & Computat | 66 | 67 | 52 | 67 | 67 | 67 | 52 |
| #2431 | Senior AI Engineer, Agents and Platform (f/m | 62 | 67 | 67 | 67 | 67 | 67 | 73 |
| #5319 | Senior ML Backend Engineer - Search & Recomm | 62 | 56 | 67 | 61 | 55 | 56 | 52 |
| #3923 | Python Engineer – Web Crawling & Data Extrac | 55 | 82 | 67 | 58 | 60 | 90 | 62 |
| #797 | Senior AI Quality Engineer | 54 | 40 | 61 | 54 | 60 | 55 | 56 |
| #2427 | Propulsion Data & Modeling Engineer | 38 | 25 | 32 | 38 | 40 | 32 | 25 |
| #1913 | Backend Engineer (Go) | 35 | 66 | 67 | 58 | 82 | 74 | 72 |
| #2418 | Senior Fullstack Engineer — Mobile Healthcar | 35 | 86 | 52 | 66 | 60 | 74 | 66 |
| #2441 | Data Engineer Kubernetes (m/w/d) | 35 | 35 | 35 | 35 | 35 | 35 | 35 |
| #5316 | Analytics Engineer II | 35 | 80 | 67 | 78 | 74 | 74 | 80 |
| #3921 | Sr. Technical Program Manager (TPM) - AI Pro | 32 | 28 | 37 | 28 | 37 | 22 | 31 |
| #2409 | Senior Principal Software Engineer, Vertica | 25 | 31 | 10 | 10 | 10 | 10 | 10 |

## 5. Top 10 side by side

Ties broken by job id. ◦ = the job is not in gemma v4's top 10.

| # | gemma-4-31b-it v4 | 3.1-lite v4 (a) | 3.1-lite v4b (c) | 3.5-lite v4 (a) | 3.5-lite v4 + budget 1024 (b) | 3.5-lite v4b (c) |
|---|---|---|---|---|---|---|
| 1 | **100** #1914 Location Data engineer | **94** #1914 Location Data engineer | **94** #1914 Location Data engineer | **100** #1914 Location Data engineer | **92** #1914 Location Data engineer | **91** #2410 Data Engineer |
| 2 | **97** #5139 Software Engineer, AI Coding T | **85** #5139 Software Engineer, AI Coding T | **84** #2410 Data Engineer | **85** #5139 Software Engineer, AI Coding T | **90** #3923 Python Engineer – Web Crawling | **88** #1914 Location Data engineer |
| 3 | **94** #794 Data Analytics Engineer (They/ | **84** #794 Data Analytics Engineer (They/ | **82** #794 Data Analytics Engineer (They/ | **84** #794 Data Analytics Engineer (They/ | **88** #794 Data Analytics Engineer (They/ | **88** #3943 O&M Data Engineer – Munich (Fi ◦ |
| 4 | **86** #2418 Senior Fullstack Engineer — Mo | **82** #2410 Data Engineer | **79** #5139 Software Engineer, AI Coding T | **82** #1913 Backend Engineer (Go) ◦ | **85** #5139 Software Engineer, AI Coding T | **84** #794 Data Analytics Engineer (They/ |
| 5 | **82** #3923 Python Engineer – Web Crawling | **67** #1913 Backend Engineer (Go) ◦ | **78** #5316 Analytics Engineer II | **82** #2410 Data Engineer | **74** #1913 Backend Engineer (Go) ◦ | **80** #5316 Analytics Engineer II |
| 6 | **81** #765 AI Engineer (m/w/d) | **67** #1921 Senior Data Engineer - BeReal | **73** #1921 Senior Data Engineer - BeReal | **82** #3943 O&M Data Engineer – Munich (Fi ◦ | **74** #2418 Senior Fullstack Engineer — Mo | **76** #1921 Senior Data Engineer - BeReal |
| 7 | **80** #2410 Data Engineer | **67** #2431 Senior AI Engineer, Agents and ◦ | **73** #3924 Senior Data Engineer (x/f/m) | **74** #5316 Analytics Engineer II | **74** #3943 O&M Data Engineer – Munich (Fi ◦ | **76** #5139 Software Engineer, AI Coding T |
| 8 | **80** #5316 Analytics Engineer II | **67** #3923 Python Engineer – Web Crawling | **67** #1927 Senior Backend Engineer - Scor ◦ | **67** #1921 Senior Data Engineer - BeReal | **74** #5316 Analytics Engineer II | **73** #2431 Senior AI Engineer, Agents and ◦ |
| 9 | **70** #3924 Senior Data Engineer (x/f/m) | **67** #3924 Senior Data Engineer (x/f/m) | **67** #2431 Senior AI Engineer, Agents and ◦ | **67** #1927 Senior Backend Engineer - Scor ◦ | **70** #765 AI Engineer (m/w/d) | **72** #765 AI Engineer (m/w/d) |
| 10 | **67** #1921 Senior Data Engineer - BeReal | **67** #3943 O&M Data Engineer – Munich (Fi ◦ | **67** #3943 O&M Data Engineer – Munich (Fi ◦ | **67** #2431 Senior AI Engineer, Agents and ◦ | **70** #2410 Data Engineer | **72** #1913 Backend Engineer (Go) ◦ |


## 6. Observations

**Read this first: 20 jobs, one run each.** Temperature 0 is not deterministic for these models (earlier, the same job and settings gave 68 and 78 on 3.5-flash-lite). Individual score swings between variants, for example #3923 at 60 vs 90 or #2410 at 82 vs 70 on 3.5-lite, are the size of that noise. Only the mechanical effects (how many distinct values a variant produces, how many ties) and the time and token costs are reliable here. Differences of a few hundredths in correlation are not.

**Thinking budget (variant b).**
- `gemini-3.5-flash-lite` honours it, but the budget is soft: 1,329 thinking tokens per job on average against a budget of 1,024. `gemini-3.1-flash-lite` accepts the parameter and thinks nothing, so b was skipped for it.
- On 3.5-lite thinking did not fix the resolution problem: 13 distinct scores (same as without), 6 jobs tied inside the top 10, largest tie group 4 (was 3). It did cost time (8.8 → 10.4 s mean) and about 1,300 tokens per job.
- Its correlation with gemma v4 is the highest of all configurations (ρ 0.88, 8/10 top-10 overlap), but its correlation with the stored scores is the lowest (0.56, 6/10). With n=20 and the noise above, I read that as "thinking moves it toward gemma, which is itself a thinking model", not as better ranking.

**v4b (any integer 0-10).**
- It does what it was meant to do mechanically. Distinct scores: 3.1-lite 12 → 16, 3.5-lite 13 → 16 (gemma v4: 17). The models used intermediate sub-scores (2, 3, 4, 6, 7) on 14 of 100 sub-scores for 3.1-lite and 19 of 100 for 3.5-lite; v4 used only 0 / 5 / 8 / 10.
- Ties in the top 10: 3.1-lite 6 jobs tied in the top 10 → 5, with the largest tie group 6 → 3, and the tie across the 10th/11th place is gone. 3.5-lite stays at 6 tied jobs but the largest group drops 3 → 2 and the cut-off tie is gone. Gemma v4 has 2 tied jobs.
- Agreement: 3.1-lite improves (ρ vs gemma 0.73 → 0.78, vs stored 0.76 → 0.79, top-10 overlap with the stored top 10 8 → 9); 3.5-lite is flat (0.70 → 0.68 and 0.73 → 0.72). I would not claim either change is real.
- Time: 3.5-lite v4b is the fastest configuration (5.8 s mean). 3.1-lite v4b is the slowest of the lite runs (25.7 s mean) because of 14 retries (503) on 10 jobs.

**Reliability in this window.** `gemini-3.5-flash-lite`: 0 retries across 60 calls, max 27 s. `gemini-3.1-flash-lite`: 7 retries on 4 jobs in the v4 run and 14 on 10 jobs in the v4b run, up to 115 s. This is one afternoon on the free tier, not a rate, but it is the clearest difference between the two models. Retried 503s may count against the 500 requests per day.

**Hard flags.** All six configurations raise the same three hard flags, and I read the quotes: #2409 `no visa sponsorship available` and `US based candidates only`, and #2441 `… sehr gutes mündliches und schriftliches Deutsch erforderlich`. No variant added a false hard flag, and the code check downgraded the same single `Remote & Home-Office innerhalb Deutschlands` flag (3.1-lite) and one gemma flag. The earlier wrong caps (an office, a city, perks) did not come back under v4b.

**#765's German C1 requirement was not caught by any configuration**, including gemma v4. All six answered `language_required` absent; the language sub-score was 0 on gemma and 3.5-lite and 5 on 3.1-lite, so #765 scores 64-81 although the listing states `Sehr gute Deutschkenntnisse (C1) in Wort und Schrift`. Neither thinking nor v4b changes this. It is a prompt problem (the instruction `when in doubt, answer false`), so it needs the v5 wording discussed in the v4 report, whichever model you pick.

**Top 10.** #1914 and #794 are in the top 5 of every configuration; #5139 is in five of the six top 5s (7th on 3.5-lite v4b) and #2410 in five of six (not in gemma's). The lower half differs by model and variant, and in the v4 lite runs positions 5-10 were tied at 67. Jobs the lite variants rate high and gemma does not: #1913 Backend Engineer (Go) and #3943 O&M Data Engineer; jobs gemma rates high and the lite models place lower: #2418 Senior Fullstack Mobile Healthcare (86 on gemma, 52-74 on lite) and #3923 Python Engineer, Web Crawling (82 on gemma, 58-90 on lite). Those are the ones worth reading against your own judgment.

## 7. Recommendation for bulk scoring

**Use `gemini-3.5-flash-lite` without thinking, with a prompt that allows any 0-10 sub-score (v4b), after adding the explicit-language wording (so a v5 prompt, not the current v4).** Reasons:
1. **Reliability.** 0 retries in 60 calls and the shortest times (5.8-8.8 s). The 500 requests/day is the binding limit for a rescore (about 4,000 jobs ≈ 8-12 days at the observed discovery inflow), so wasted retries and slow calls matter; 3.1-lite spent 7-14 retries per 20 jobs.
2. **Resolution.** v4b gives 16 distinct scores and no tie at the top-10 cut-off, close to gemma's 17. Without it the lite models plateau (8 of 20 jobs at 67 on 3.1-lite) and the order inside Discover's top 10 is partly arbitrary.
3. **Thinking is not worth it on these models.** On 3.5-lite it costs about 20% more time and 1,300 tokens per job without fewer ties or a better match to the stored scores; on 3.1-lite it cannot be set with a budget at all.
4. **Flags behave.** Under v4 and v4b the lite models raise the same three genuine hard flags as gemma, and the code check catches the rest.

**Where I am less sure.** 3.1-flash-lite with v4b has the best agreement with the stored scores (ρ 0.79, 9/10 top-10 overlap) and with gemma (0.78), slightly better than 3.5-lite v4b (0.72 and 0.68), but that gap is inside the noise at n=20 and 3.1-lite was the flaky one. If you weight agreement over speed and reliability, 3.1-flash-lite v4b is a defensible choice. Using both lite models as each other's fallback would double the daily capacity (separate 500/day limits), at the price of two models in Discover, which you wanted to avoid.

**Before switching anything:**
- v4b and the language wording are not in the repo yet. Adopting them means prompt v5 (new version, hash in `versions.json`, tests), then a real rescore with that exact prompt; the v4b runs here do not count as that rescore.
- `make eval` on your labeled jobs would tell you more than these 20 jobs and one run each; I have not run it.
- None of the lite models found #765's C1 requirement, so the v5 wording is a prerequisite, not an extra.
- gemma-4-31b-it remains the better-resolved and slower option (81 s per job, about 1 day for the whole backlog because its limit is TPM, not RPD) and would be the fallback if the 500/day limit becomes the problem.
