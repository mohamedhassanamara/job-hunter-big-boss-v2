# CV and email generation with Gemini models (2026-10-21)

Facts only: no ranking, no recommendation. Raw files: `docs/reports/raw/cv-email-model-test-2026-10-21/`
(`<config>/cv.json, cv.pdf, email.md, email_verification.json, metrics.json, calls.json, raw/`, plus `claude-baseline/`).
Harness: `backend/scripts/cv_email_model_test.py`.

## How it was run

- The real DB was copied (sqlite online backup) into a temp dir. Every write (CV versions, drafts, events, PDFs) went to the copy, so the real DB, approvals, settings and default models are untouched. CV renders go to the raw folder, not `data/cv`.
- Production code, unchanged: prompts (`cv_generate` v-current, `outreach` applied mode), request builders, code checks, bullet tailoring, summary grounding, fit-to-page loop, PDF compile. Only the generator is swapped for a Gemini client that returns the same schema models.
- Claude (`claude-opus-5-5`, `claude -p`) stays the verifier: the adapted-bullet check for the CV (it was never called: no config produced an adapted bullet) and the claim verifier on every email. I ran the email verifier even where production would have stopped at a code error (that did not occur in the end).
- Gemini calls: native JSON schema (`responseJsonSchema`, same inlined schema as the Claude path), the provider's default temperature, keys rotated per attempt. Invalid JSON would get one retry with the error fed back (it was never needed). 429/503 retried with 5, 10, 20, 40, 60, 60, 60, 60 s backoff.
- Privacy: the request builders carry no phone, email or links of yours (`prompt_pool` documents "no contact data"). The client also refuses to send a request containing your profile's email, phone digits or link URLs (checked on every call; it never triggered). **One exception to say plainly:** the pool bullet for the Lovester project (item 3) contains the project's own domain, `lovester.net`. It is in the pool, so Claude gets it too, and it was sent to Gemini. The dynamic-thinking email copied it into the text (see below).
- Thinking configs: `gemini-3.5-flash-lite` rejects `thinkingBudget: 0` (400), so "no thinking" is `thinkingLevel: minimal` (0 thinking tokens measured in every call) and "dynamic" is `thinkingBudget: -1`.

## 1. Job

Application **1622, Healy World GmbH, "Flutter developer for mobile apps (m/f/d)"**, Berlin, track Mobile.
It has an approved CV (v1) and an approved email (draft 25, queued), and a full English listing (5,305 characters).

Other candidates today, all also on the Mobile track (so one job, as asked): 889 Codeway (listing is a 500-character snippet), 4951 SaltRock (full German listing, email already sent live), 4960 GAIA (German listing, 1,845 characters). No two jobs from different tracks had both approvals.
The email is written from the approved Claude CV (as in production), so the three email results do not depend on the Gemini CV.

## 2. Baseline (approved Claude versions, no new Claude generation)

CV v1 and draft 25, both `claude-sonnet-5`. CV generation 75.4 s (stored), email 7.5 s (stored).

## 3. Keys

- `.env` has **5 keys** in `GEMINI_API_KEY` (singular name, comma-separated; the code reads it as well as `GEMINI_API_KEYS`). **All 5 work**: model listing 200 and a test call to `gemini-3.5-flash-lite` 200 on each.
- `gemini-3.1-flash-lite`: all 5 returned 503 ("high demand") on the key probe, after 4 tries each. Earlier in the session one key (key 3) answered it. The 503 is not tied to a key.
- Separate projects: **not measurable from outside**. The API shows no project id and the keys have distinct fingerprints (970c14, cabc34, ec8ff9, 8ee33e, f8a88a). The repo's own docs assume one project per key. Check in AI Studio.
- Daily capacity per model: **not reported by the API either**. If each key is a separate project at the free-tier limits the code assumes (15 requests/min, 250K tokens/min, 500 requests/day per key and model), that is 5 keys x 500 = 2,500 requests/day per model. That is an assumption, not a measurement.

## 4. Results

### Run summary

| | Claude baseline | 3.5-flash-lite, no thinking | 3.5-flash-lite, dynamic thinking | 3.1-flash-lite, no thinking |
|---|---|---|---|---|
| **CV** valid JSON first try | n/a (CLI-validated) | yes, 2/2 calls | yes, 2/2 calls | first call yes; second call never answered |
| CV 429/503 retries | n/a | 0 / 0 | 0 / 0 | 0 / 17 |
| CV model time | 75.4 s | 44.8 s (2 calls) | 28.9 s (2 calls) | 339 s, then failed |
| CV tokens in / out / thinking | n/a | 15,250 / 2,216 / 0 | 15,199 / 2,758 / 7,133 | 7,474 / 1,496 / 0 (first call only) |
| **Email** valid JSON first try | n/a | yes, 2/2 calls | yes, 1/1 | no answer |
| Email 429/503 retries | n/a | 0 / 0 | 0 / 0 | 0 / 9 |
| Email model time | 7.5 s | 5.6 s (2 calls) | 13.8 s (1 call) | no answer |
| Email tokens in / out / thinking | n/a | 10,262 / 552 / 0 | 5,095 / 257 / 5,007 | 0 |
| Email draft attempts (production retry on code errors) | 1 | 2 | 1 | none |

**gemini-3.1-flash-lite** produced no CV and no email: the CV's first call was valid, then the summary-retry call got 503 on all 9 attempts and generation raised; the email got 503 on all 9 attempts. Nothing past that was run (stopped there at your request, no second attempt). The failed run is in `gemini-3.1-flash-lite__no-thinking/` (calls, raw first response, metrics). Both would be blocked from approval trivially: there is no output.

### CV

| | Claude baseline | 3.5 no thinking | 3.5 dynamic thinking |
|---|---|---|---|
| Pages / fill | 1 / 98.2% | 1 / 87.9% | 1 / 91.5% |
| Errors | 0 | 0 | 0 |
| Warnings | 0 | 1 | 1 |
| Role bullets / project bullets shown | 11 / 2 | 11 / 0 | 7 / 0 |
| Bullets changed vs pool | 0 | 0 | 0 |
| Numbers or tools added / dropped | none | none | none |
| Pool-grounded bullet count (tailoring report: original / adapted) | 28 / 0 | 21 / 0 | 27 / 0 |
| Summary regenerated | no (1 attempt) | yes (2 attempts) | yes (2 attempts) |
| Would be blocked from approval | no | no | no |

No bullet was adapted by any config: every bullet is the pool text verbatim, so there are no bullet diffs to show and the Claude adapted-bullet verifier was not called.

The one warning in both Gemini CVs: `[summary_style] summary: The summary still breaks the writing guide after one retry: opens like another CV (“Software engineer with 3…”): vary the opening`.
In both, the first summary was rejected by the grounding check: `years claim “3 years” isn't allowed (write exactly “3 years of software engineering experience”)`; the retry passed.

**Summary text**
- Baseline: "Flutter engineer with 3 years of software engineering experience shipping production mobile apps to the App Store and Google Play. Recent work includes refactoring a dating app to Riverpod and Clean Architecture, and integrating Firebase and BFF services into a sports platform at Reality Sports."
- 3.5 no thinking: "Software engineer with 3 years of experience in mobile and backend development, specializing in cross-platform applications and scalable API integrations. Recent work includes building production Flutter applications, refactoring legacy codebases to Riverpod, and developing a privacy-first resume parsing engine."
- 3.5 dynamic: "Software engineer with 3 years of experience specializing in Flutter, building production applications and shipping releases to the App Store and Google Play. Recent work includes architecting custom Backend-for-Frontend endpoints in Spring Boot and refactoring legacy codebases under Clean Architecture."

**Skills lines** (all pass `verbatim_skills`; categories and items are the pool's)
- Baseline: Mobile & Frontend (8 items); Core Languages: Dart, Kotlin, Swift, Java, Python, SQL, Bash, C/C++; DevOps, Cloud & Release (8 items). 3 lines.
- 3.5 no thinking: Mobile & Frontend (8 items, incl. "RESTful APIs"); Core Languages: Dart, Python, Java, SQL, Bash; DevOps, Cloud & Release (6 items); Backend & Data Engineering: Spring Boot, FastAPI, PostgreSQL, MQTT. 4 lines. Dropped Kotlin, Swift, C/C++ and Linux vs the baseline.
- 3.5 dynamic: Mobile & Frontend (8 items, incl. "RESTful APIs", "BFF Integration"); Core Languages: Dart, Python, Java, SQL; DevOps, Cloud & Release (6 items); Backend & Data Engineering: Spring Boot, FastAPI, PostgreSQL. 4 lines. Dropped Kotlin, Swift, Bash and C/C++ vs the baseline.
Full lists: `<config>/cv.json` → `content.skills`.

### Email (language rule: English, "the listing is in English and you speak it at a working level")

| | Claude baseline | 3.5 no thinking | 3.5 dynamic thinking |
|---|---|---|---|
| Language chosen / matches rule | en / yes | en / yes | en / yes |
| Words (body, 90-170 allowed) | 98 | 127 | 108 |
| Code errors | 0 | 0 | 0 |
| Code warnings | 1 | 2 | 2 |
| Claude verifier | passed (20.6 s) | passed (23.0 s) | passed (22.6 s) |
| Claims judged | 12 | 19 | 17 |
| Blocking verdicts | 0 | 0 | 0 |
| Would be blocked from approval | no | no | no |

Warnings: baseline `[company] body: The company name “Healy World GmbH” isn't mentioned` (it says "Healy World"). Both Gemini emails: `[cv_copy]` on both experience sentences ("reads like a CV bullet").

**3.5 no thinking, full text**
```
Subject: Flutter developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter developer position at Healy World GmbH and wanted to reach out directly.

Shipped a full-stack sports management platform to the App Store and Google Play Store, building 10+ data-driven Flutter screens and integrating 15+ RESTful backend services for real-time data synchronization. Engineered the complete Flutter frontend for the "Lovester" dating application, achieving fluid 60fps user interfaces and complex custom animations across 25+ unique screens.

I am based in Tunis, Tunisia, and would need visa sponsorship to work in Germany, though I am fully willing to relocate for the job if that rules me out, I understand.

Please take a look at my attached CV, and let me know if you are open to a short call.

Best regards,
Mohamed Hassen Amara
```
Verifier verdicts: 13 supported (applying; name; Healy World GmbH; the Reality Sports sentence split into 3 claims, pool:1; the Lovester sentence split into 3 claims, pool:3; "based in Tunis, Tunisia", "would need visa sponsorship to work in Germany", "willing to relocate" all from facts) and 6 not_a_claim (greeting, intent, the courtesy "If that rules me out, I understand", request, sign-off, name). None blocking.

**3.5 dynamic thinking, full text**
```
Subject: Flutter Developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter Developer role at Healy World GmbH and wanted to reach out directly to connect with the team.

Shipped a full-stack sports management platform to the App Store and Google Play Store, building 10+ data-driven Flutter screens and integrating 15+ RESTful backend services for real-time data synchronization. Engineered the complete Flutter frontend for the "Lovester" dating application (`lovester.net`), achieving fluid 60fps user interfaces and complex custom animations across 25+ unique screens.

Please take a look at my attached CV, and I would welcome a short call to discuss how my mobile development experience aligns with your work.

Best regards,
Mohamed Hassen Amara
```
Verifier: 11 supported (incl. all pool:1 and pool:3 claims "word for word", and "has mobile development experience" from facts), 6 not_a_claim. None blocking.

**Claude baseline, full text** (verifier: 8 supported, 4 not_a_claim)
```
Subject: Flutter Developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter Developer role at Healy World and wanted to reach out directly.

At Reality Sports I built the Flutter frontend for a sports management app with 10+ screens and integrated 15+ RESTful backend services for real-time data sync. I also set up GitHub Actions pipelines for automated builds and releases, and refactored a legacy codebase under Clean Architecture, cutting the app's binary size by 15%.

Would you be able to take a look at my attached CV and let me know if you'd recommend me for the role?

Best regards,
Mohamed Hassen Amara
```
Every claim of every email with its source and reason is in `<config>/email.md` and `email_verification.json`.

## 5. Anything invented, exaggerated, or against the rules (with quotes)

No verifier verdict was `unsupported`, `exaggerated`, `merged` or `causal`, and no code error fired. These are what I found by reading the outputs against the pool and the prompt rules. None was flagged by any check.

1. **3.5 no thinking, email, a constraint sentence the rules don't allow here.** "I am based in Tunis, Tunisia, and would need visa sponsorship to work in Germany, though I am fully willing to relocate for the job if that rules me out, I understand." The applied-email rule is: a constraint only when the listing states a requirement you don't meet. I searched the listing text (visa, work permit, residen-, relocat-, eligib-, authori-) and found no such requirement; Germany appears only as a location and a perk. Each fact in the sentence is true (it is in FACTS), so the verifier passed it, and the code checks have no warning for it. The Claude baseline and the dynamic email don't contain it.
2. **3.5 no thinking, CV summary: "specializing in cross-platform applications and scalable API integrations".** No pool sentence says "scalable" or "cross-platform". Closest pool text: the Mobile snippet "specializing in Flutter" and the BFF bullet "to streamline mobile API integration". Passed the grounding check (cited 21, 23).
3. **3.5 no thinking, CV summary: "developing a privacy-first resume parsing engine".** Supported by pool item 2 (AI Engineer Intern graduation project: "Designed a privacy-first resume parsing and candidate scoring engine…") but it is the Data/AI project, placed in a Mobile-track summary. Not an invention; reported as a fact about the content.
4. **3.5 no thinking, CV summary: "refactoring legacy codebases to Riverpod".** Pool bullet 1: "legacy codebase refactor to Riverpod and GoRouter under Clean Architecture"; plural "codebases" is the model's. Same for the dynamic summary, "refactoring legacy codebases under Clean Architecture".
5. **Both summaries open "Software engineer with 3 years of experience…"**: the writing-guide warning above, kept after one retry. The baseline opens "Flutter engineer with 3 years of software engineering experience".
6. **Dynamic email: `lovester.net` in the text.** It copies the domain from the pool bullet. Your instruction was to keep links away from the models; this one is a project link inside the pool text, so it reached both Claude and Gemini by design of the pool, and the dynamic model then repeated it in the email. The baseline email doesn't contain it.
7. **Both Gemini emails copy two pool bullets almost verbatim** as the experience paragraph ("Shipped a full-stack sports management platform…", "Engineered the complete Flutter frontend for the "Lovester" dating application…"); the `cv_copy` warning is the code's flag for that. The Claude baseline rewrote them into first-person sentences.
8. **Email CTA.** Both Gemini emails offer "a short call" (no thinking: "let me know if you are open to a short call"). The baseline asks whether the recipient would recommend you for the role. Not a rule violation; stated as a difference.

The CV bullets are all original pool text, so nothing in the CV bullets was invented or exaggerated by any config.

## 6. Which outputs would have been blocked from approval

- Claude baseline: none (approved).
- 3.5 no thinking: CV no (0 errors); email no (0 code errors, verifier passed). The unflagged constraint sentence (item 1) would not have been caught.
- 3.5 dynamic thinking: CV no; email no.
- 3.1 no thinking: no output at all (503 on every attempt).

## Notes

- n = 1 job and 1 run per config (temperature left at the provider default), so run-to-run variance is not measured. The first, partial trial run of the no-thinking config (in a scratch folder, not saved) produced a different email: one grounding error `cites unknown ids 6, 6`, which the production retry would have fixed. That is the only place a code error appeared.
- The 3.5 no-thinking CV call took 44.8 s in the saved run and about 6 s in the trial. Timing varies a lot.
- Thinking tokens were 7,133 (CV) and 5,007 (email) for dynamic, against 257-2,758 output tokens.
- Everything for the failed 3.1 attempt, including the one valid CV plan response it did get, is in `gemini-3.1-flash-lite__no-thinking/raw`.
