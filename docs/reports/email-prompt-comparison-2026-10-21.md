# Email prompt v14: Gemini and Claude side by side (2026-10-21)

Facts only: no ranking, no recommendation. **Automatic email drafting stays OFF** until you choose.
Raw: `docs/reports/raw/email-prompt-comparison-2026-10-21/` (`results.json`, `report-body.md`; `results-run1-partial.json` is the first full pass, in which the Claude usage limit cut off Qonto's Claude verifier and both ILLUIN Claude steps, so those two jobs were run again). Harness: `backend/scripts/email_prompt_comparison.py`.

## How it was run

- Production code on a scratch copy of the real DB (nothing real written, nothing approved or sent): `outreach.generate_applied` (prompt v14, the code checks, the automatic copy retry), then the Claude claim verifier (`claude-opus-5-5`, verify prompt v6) on each result. The style reference (your paragraph) was in the request for both generators.
- Generators: Gemini = `gemini-3.5-flash-lite`, thinking minimal (the Settings default); Claude = `claude-sonnet-5`. Each writes from the CV approved for the job.
- 5 real jobs with a posting, 3 tracks, 3 languages: Healy World (Mobile, English listing), SaltRock (Mobile, German listing), ElevenLabs (Backend, English), Qonto (Data/AI, French company, English output by the language rule), ILLUIN Technology (Data/AI, French listing, French output).
- Prerequisites missing in the real data were supplied **in the scratch copy only**: ElevenLabs, Qonto and ILLUIN had no approved CV (a Gemini CV was generated and marked approved there) and ElevenLabs and Qonto had no contact (a placeholder, "Alex Morgan", is the recipient; the verifier then judges claims about "Alex's team" against that placeholder). ILLUIN used an existing contact.
- Two false positives found in these first results were fixed in the checks before the re-run of Qonto and ILLUIN, so those two jobs were checked by the fixed rules while the first three were checked by the earlier ones (company names such as "GmbH", "SaltRock", "ElevenLabs" counted as tools; a bare "I have 3 years of software engineering experience." sentence was reported as uncited). The tool-count warnings for Healy, SaltRock and ElevenLabs below include those words.

## Summary (5 jobs each)

| | Gemini 3.5 flash-lite (minimal) | Claude Sonnet 5 |
|---|---|---|
| Language matches the rule | 5 / 5 | 5 / 5 |
| Words (aim 90-120; warning outside 90-170) | 111, 121, 104, 101, 82 | 96, 129, 114, 99, 112 |
| Longest run copied from a pool bullet or the reference | 10, 8, 4, 4, 7 words | 7, 8, 4, 4, 2 words |
| Ran the automatic "summarize in your own words" retry | 3 / 5 | 3 / 5 |
| Still at 8+ copied words after the retry (a warning) | 2 / 5 | 1 / 5 |
| Drafts with a code error (would block approval) | 1 / 5 | 2 / 5 |
| Claude verifier passed / blocked | 2 / 3 | 1 / 4 |
| Draft time | 4.2, 4.9, 1.9, 1.6, 3.5 s | 31.4, 40.0, 26.0, 70.9, 65.7 s |
| Verifier time | 16.9-27.5 s | 23.4-29.4 s |
| Gemini requests / 429 / 503 | 8 for the 5 final drafts, 0 / 0 (44,726 tokens in, 2,037 out) | n/a (Claude CLI) |

The verifier blocked 3 of 5 Gemini drafts and 4 of 5 Claude drafts. What it blocked (every claim that was not supported):

- **Healy, Claude:** exaggerated ("builds the screens for a sports platform": the source says 10+ screens); merged (the screens' backend named as Spring Boot, which is a separate bullet).
- **SaltRock, Gemini:** merged ("At Lovester I migrated the codebase to Riverpod and GoRouter": Lovester's migration was Provider to Riverpod; GoRouter belongs to the Reality Sports refactor).
- **ElevenLabs, Gemini:** unsupported (asynchronous backend services; independent end-to-end ownership; features across the stack), exaggerated (full-stack applications, plural; shipped them to production), and a garbled warning (the courtesy "if that rules me out, I understand" fused onto the relocation clause).
- **ElevenLabs, Claude:** exaggerated (the 3 years tied to full-stack work; "built" the REST services that the source says were integrated), merged (the FastAPI backend orchestrating the local LLM with STT and TTS).
- **Qonto, Gemini:** merged (Python pipelines "with dbt and DuckDB": the sources keep the ingestion pipelines and the dbt star schema apart).
- **Qonto, Claude:** unsupported ("the Business Analytics team is Alex's team", against the placeholder recipient); plus a code error: the years wording ("I have 3 years of professional software engineering experience in backend and mobile…" is not the allowed statement).
- **ILLUIN, Claude:** merged (Spring Boot APIs "serve a sports platform in production").
- The two passes that were Gemini's (Healy, ILLUIN) and Claude's one pass (SaltRock) carry only warnings.

Warnings that appeared (code checks, never blocking): the listing states no location or visa requirement but the email brings up location, visa or relocation (Gemini in 5 of 5 drafts, Claude in 1 of 5); tool count above 3 (both); a sentence that doesn't start from "I" or is vague (Gemini); length outside 90-170 (Gemini ILLUIN, 79-82 words).

# Per job

### Healy World GmbH: Flutter developer for mobile apps (m/f/d)

Track Mobile · country DE · listing 5,305 characters · language rule: **en**

| | gemini-3.5-flash-lite (minimal) | claude-sonnet-5 |
|---|---|---|
| Language (matches rule) | en (yes) | en (yes) |
| Words (aim 90-120, warn outside 90-170) | 111 | 96 |
| Copy overlap, longest run with a pool bullet or the style reference | 10 words (a CV bullet) | 7 words (the style reference) |
| Draft attempts (2 = the automatic retry ran) | 2 | 2 |
| Code errors | 0 | 1 |
| Code warnings | 3 | 2 |
| Claude verifier | passed (0 blocking) | failed (2 blocking) |
| Verdicts | not_a_claim 5, supported 10 | exaggerated 1, merged 1, not_a_claim 5, supported 9 |
| Draft time | 4.2 s | 31.4 s |
| Verifier time | 17.9 s | 27.9 s |
| Gemini calls / retries 429 / 503 / tokens in-out-thinking | 2 / 0 / 0 / 10767-517-0 | n/a (Claude CLI) |

**gemini-3.5-flash-lite (minimal)**

```text
Subject: Flutter Software Developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter Software Developer role at Healy World GmbH and wanted to reach out directly.

With 3 years of software engineering experience, I build cross-platform applications using Flutter and integrate backend services through REST APIs. At Reality Sports I set up automated build and deployment pipelines with GitHub Actions.

I am based in Tunis, Tunisia, and would need visa sponsorship to work in the job's country, though I am willing to relocate for the job. If that rules me out, I understand.

Please take a look at my attached CV, and let me know if you would be open to a short call.

Best regards,
Mohamed Hassen Amara
```

- warning [cv_copy] “At Reality Sports I set up automated build and deployment pipelines with GitHub Actions.” copies 10 words in a row from a CV bullet: summarize in your own words
- warning [tools] Names 4 tools (Flutter, GitHub, GmbH, REST): 3 at most reads better
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- none

Longest copied run (10 words, a CV bullet): “At Reality Sports I set up automated build and deployment pipelines with GitHub Actions.”

**claude-sonnet-5**

```text
Subject: Flutter Developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter Developer role at Healy World and wanted to reach out directly.

I have 3 years of software engineering experience building Flutter apps, most recently at Reality Sports. There I build the screens for a sports platform live on the App Store and Google Play and connect them to a Spring Boot backend through REST APIs, and I also set up our GitHub Actions pipelines so builds and releases stay consistent.

Would you be open to a short call, or could you take a look at my CV attached.

Best regards,
Mohamed Hassen Amara
```

- ERROR [grounding] “There I build the screens for a sports platform live on the App Store and Google Play and connect them to a Spring Boot backend through REST APIs, and I also set up our GitHub Actions pipelines so builds and releases stay consistent.”: cites unknown ids 6
- warning [company] The company name “Healy World GmbH” isn't mentioned
- warning [tools] Names 4 tools (Flutter, GitHub, REST, Spring): 3 at most reads better

Verifier verdicts that are not supported / not_a_claim:
- **exaggerated** “At Reality Sports the candidate builds the screens for a sports platform” (The source says he built 10+ Flutter screens, not that he builds all of the platform's screens ('the screens').)
- **merged** “The backend the screens connect to is a Spring Boot backend” (Spring Boot appears in a separate bullet about BFF endpoints; the screens and REST bullet never names Spring Boot as the backend the screens use.)

Longest copied run (7 words, the style reference): “There I build the screens for a sports platform live on the App Store and Google Play and connect them to a Spring Boot backend through REST APIs, and I also set up our GitHub Actions pipelines so builds and releases stay consistent.”

### SaltRock: Mobile Engineer (m/w/d) – Flutter, Enterprise-App

Track Mobile · country DE · listing 6,770 characters · language rule: **en**

| | gemini-3.5-flash-lite (minimal) | claude-sonnet-5 |
|---|---|---|
| Language (matches rule) | en (yes) | en (yes) |
| Words (aim 90-120, warn outside 90-170) | 121 | 129 |
| Copy overlap, longest run with a pool bullet or the style reference | 8 words (a CV bullet) | 8 words (the style reference) |
| Draft attempts (2 = the automatic retry ran) | 2 | 2 |
| Code errors | 1 | 0 |
| Code warnings | 3 | 3 |
| Claude verifier | failed (1 blocking) | passed (0 blocking) |
| Verdicts | merged 1, not_a_claim 5, supported 11 | not_a_claim 6, supported 12 |
| Draft time | 4.9 s | 40.0 s |
| Verifier time | 22.4 s | 29.2 s |
| Gemini calls / retries 429 / 503 / tokens in-out-thinking | 2 / 0 / 0 / 11647-532-0 | n/a (Claude CLI) |

**gemini-3.5-flash-lite (minimal)**

```text
Subject: Mobile Engineer application – Mohamed Hassen Amara

Hi David,

I applied for the Mobile Engineer role at SaltRock and wanted to reach out directly.

I have 3 years of software engineering experience. At Reality Sports I built screens in Flutter and integrated RESTful backend services, shipping our platform to the App Store and Google Play. Before that I developed the Flutter frontend for the dating application Lovester across 25+ screens and migrated the codebase to Riverpod and GoRouter.

I am based in Tunis, Tunisia, and would need visa sponsorship to work in the role's country, though I am willing to relocate for the job. If that rules me out, I understand.

Would you be open to a brief call to discuss my background and the attached CV?

Best regards,
Mohamed Hassen Amara
```

- ERROR [grounding] “Before that I developed the Flutter frontend for the dating application Lovester across 25+ screens and migrated the codebase to Riverpod and GoRouter.”: “GoRouter” isn't in the cited items
- warning [cv_copy] “I have 3 years of software engineering experience. At Reality Sports I built screens in Flutter and integrated RESTful backend services, shipping our platform to the App Store and Google Play.” copies 8 words in a row from a CV bullet: summarize in your own words
- warning [tools] Names 5 tools (Flutter, GoRouter, RESTful, SaltRock, riverpod): 3 at most reads better
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- **merged** “At Lovester I migrated the codebase to Riverpod and GoRouter” (At Lovester the migration was from Provider to Riverpod only; the move to Riverpod and GoRouter was the Reality Sports refactor (pool:1).)

Longest copied run (8 words, a CV bullet): “At Reality Sports I built screens in Flutter and integrated RESTful backend services, shipping our platform to the App Store and Google Play.”

**claude-sonnet-5**

```text
Subject: Mobile Engineer application – Mohamed Hassen Amara

Hi David,

I'm applying for the Mobile Engineer role at SaltRock and wanted to reach out directly.

I have 3 years of software engineering experience building Flutter apps that ship to the App Store and Google Play, and at Reality Sports I also built the backend endpoints the app talks to. Before that, I built the Flutter frontend for a dating app with more than 25 screens and led its move from Provider to Riverpod.

I'm based in Tunis and would relocate for the role, but I should mention I work in English, French, Arabic and Spanish, not German, so if that rules me out, I understand.

Would you be open to a short call sometime, or could you take a look at my CV attached here?

Best regards,
Mohamed Hassen Amara
```

- warning [cv_copy] “Before that, I built the Flutter frontend for a dating app with more than 25 screens and led its move from Provider to Riverpod.” copies 8 words in a row from the style reference: summarize in your own words
- warning [tools] Names 4 tools (Flutter, SaltRock, provider, riverpod): 3 at most reads better
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- none

Longest copied run (8 words, the style reference): “Before that, I built the Flutter frontend for a dating app with more than 25 screens and led its move from Provider to Riverpod.”

### ElevenLabs: Full-Stack Engineer (Backend Leaning) - Creative Agents

Track Backend · country None · listing 5,572 characters · language rule: **en**

- scratch only: no approved CV in the real data; a gemini-3.5-flash-lite CV was generated (7 s) and marked approved in the copy
- scratch only: no contact for this company; a placeholder (Alex Morgan) is used

| | gemini-3.5-flash-lite (minimal) | claude-sonnet-5 |
|---|---|---|
| Language (matches rule) | en (yes) | en (yes) |
| Words (aim 90-120, warn outside 90-170) | 104 | 114 |
| Copy overlap, longest run with a pool bullet or the style reference | 4 words (the style reference) | 4 words (the style reference) |
| Draft attempts (2 = the automatic retry ran) | 1 | 1 |
| Code errors | 0 | 0 |
| Code warnings | 3 | 1 |
| Claude verifier | failed (5 blocking) | failed (3 blocking) |
| Verdicts | exaggerated 2, garbled 1, not_a_claim 6, supported 9, unsupported 3 | exaggerated 2, merged 1, not_a_claim 5, supported 8 |
| Draft time | 1.9 s | 26.0 s |
| Verifier time | 27.5 s | 29.4 s |
| Gemini calls / retries 429 / 503 / tokens in-out-thinking | 1 / 0 / 0 / 5678-258-0 | n/a (Claude CLI) |

**gemini-3.5-flash-lite (minimal)**

```text
Subject: Full-Stack Engineer application – Mohamed Hassen Amara

Hi Alex,

I'm applying for the Full-Stack Engineer role at ElevenLabs and wanted to reach out directly.

With 3 years of software engineering experience, I built asynchronous backend services and RESTful APIs using Spring Boot and FastAPI. I also developed full-stack applications with independent end-to-end ownership, delivering features across the stack and shipping them to production.

I am based in Tunis, Tunisia, and would need visa sponsorship to work in the job's country, though I am willing to relocate if that rules me out, I understand.

Would you be open to a brief call to discuss my background?

Best regards,
Mohamed Hassen Amara
```

- warning [vague] “I also developed full-stack applications with independent end-to-end ownership, delivering features across the stack and shipping them to production.” is vague: say what it is and with which tools
- warning [tools] Names 4 tools (ElevenLabs, FastAPI, RESTful, Spring): 3 at most reads better
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- **unsupported** “The candidate built asynchronous backend services” (No source says any of the candidate's backend work was asynchronous.)
- **exaggerated** “The candidate developed full-stack applications (plural)” (The source names only one full-stack platform.)
- **unsupported** “The candidate had independent end-to-end ownership of that work” (No source says the candidate had independent end-to-end ownership; the wording comes from the listing.)
- **unsupported** “The candidate delivered features across the stack” (No source says the candidate delivered features across the whole stack; pool:1 says they built Flutter screens and integrated REST services.)
- **exaggerated** “The candidate shipped them to production” (The source says one platform was shipped to the app stores, not several applications.)
- **garbled** “I am based in Tunis, Tunisia, and would need visa sponsorship to work in the job's country, though I am willing to relocate if that rules me out, I understand.” (The courtesy 'if that rules me out, I understand' is fused onto the relocation clause, so it reads as 'willing to relocate if that rules me out'.)

**claude-sonnet-5**

```text
Subject: Full-Stack Engineer application – Mohamed Hassen Amara

Hi Alex,

I'm applying for the Full-Stack Engineer (Backend Leaning) - Creative Agents role at ElevenLabs and wanted to reach out directly.

I have 3 years of software engineering experience focused on backend and full-stack work: at Reality Sports I designed Spring Boot backend-for-frontend endpoints and built the REST services that power our production mobile app. For my graduation project, I built a FastAPI backend that orchestrated a local LLM together with speech-to-text and text-to-speech models into an automated interview pipeline, and packaged the whole system with Docker.

Would you be open to a short call, or could you take a look at my attached CV?

Best regards,
Mohamed Hassen Amara
```

- warning [tools] Names 6 tools (ElevenLabs, FastAPI, REST, Spring, docker, llm): 3 at most reads better

Verifier verdicts that are not supported / not_a_claim:
- **exaggerated** “The 3 years of experience are focused on full-stack work” (Only one Reality Sports platform is called full-stack; the sources never tie the 3 years to full-stack work, and much of that time was Flutter mobile work.)
- **exaggerated** “At Reality Sports the candidate built the REST services that power the production mobile app” (The source says the candidate integrated the RESTful services into the app, not that they built them.)
- **merged** “The FastAPI backend orchestrated a local LLM together with STT and TTS models into an automated interview pipeline” (The interview system combines only Whisper and gTTS; the local Mistral LLM is used for resume parsing and scoring, so putting the LLM into the interview pipeline fuses separate bullets.)

### Qonto: Analytics Engineer

Track Data/AI · country FR · listing 5,997 characters · language rule: **en**

- scratch only: no approved CV in the real data; a gemini-3.5-flash-lite CV was generated (11 s) and marked approved in the copy
- scratch only: no contact for this company; a placeholder (Alex Morgan) is used

| | gemini-3.5-flash-lite (minimal) | claude-sonnet-5 |
|---|---|---|
| Language (matches rule) | en (yes) | en (yes) |
| Words (aim 90-120, warn outside 90-170) | 101 | 99 |
| Copy overlap, longest run with a pool bullet or the style reference | 4 words (a CV bullet) | 4 words (a CV bullet) |
| Draft attempts (2 = the automatic retry ran) | 1 | 2 |
| Code errors | 0 | 2 |
| Code warnings | 3 | 1 |
| Claude verifier | failed (1 blocking) | failed (1 blocking) |
| Verdicts | merged 1, not_a_claim 6, supported 10 | not_a_claim 5, supported 10, unsupported 1 |
| Draft time | 1.6 s | 70.9 s |
| Verifier time | 26.3 s | 27.6 s |
| Gemini calls / retries 429 / 503 / tokens in-out-thinking | 1 / 0 / 0 / 5831-246-0 | n/a (Claude CLI) |

**gemini-3.5-flash-lite (minimal)**

```text
Subject: Analytics Engineer application – Mohamed Hassen Amara

Hi Alex,

I applied for the Analytics Engineer role at Qonto and wanted to reach out directly.

At Reality Sports I architected custom backend endpoints in Spring Boot and built data-driven mobile screens. I have 3 years of software engineering experience and built Python pipelines with dbt and DuckDB through personal projects.

I am based in Tunis, Tunisia, and would need visa sponsorship to work in France, though I am willing to relocate for the job. If that rules me out, I understand.

Would you be open to a short call to discuss how my background aligns with your team?

Best regards,
Mohamed Hassen Amara
```

- warning [constraint] Quote the listing's own words for the requirement you mention (it doesn't state it as written)
- warning [tools] Names 4 tools (DuckDB, Python, Spring, dbt): 3 at most reads better
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- **merged** “Through personal projects, the candidate built Python pipelines with dbt and DuckDB” (The source keeps the Python ingestion pipelines (into LocalStack S3) separate from the dbt star schema on DuckDB, and it describes one personal project, not several.)

**claude-sonnet-5**

```text
Subject: Analytics Engineer application – Mohamed Hassen Amara

Hi Alex,

I'm applying for the Analytics Engineer role on your Business Analytics team at Qonto and wanted to reach out directly.

I have 3 years of professional software engineering experience in backend and mobile, most recently at Reality Sports where I build backend services that power our Flutter app. On my own time I also built a data lakehouse project where I used dbt to model football data into an analytics-ready schema on DuckDB, with Python pipelines handling ingestion.

Would you be open to a short call, or could you take a look at my CV?

Best regards,
Mohamed Hassen Amara
```

- ERROR [grounding] “I have 3 years of professional software engineering experience in backend and mobile, most recently at Reality Sports where I build backend services that power our Flutter app.”: years claim “3 years” isn't allowed (write exactly “3 years of software engineering experience”)
- ERROR [years] Years claim “3 years” isn't allowed
- warning [tools] Names 4 tools (DuckDB, Flutter, Python, dbt): 3 at most reads better

Verifier verdicts that are not supported / not_a_claim:
- **unsupported** “The Business Analytics team is Alex's team” (Alex is listed only as an Engineering Manager; the listing says the role's manager is Jules Jeanroy, and no source ties Alex to the Business Analytics team.)

### ILLUIN Technology: AI System Engineer (F/H)

Track Data/AI · country FR · listing 3,135 characters · language rule: **fr**

- scratch only: no approved CV in the real data; a gemini-3.5-flash-lite CV was generated (18 s) and marked approved in the copy

| | gemini-3.5-flash-lite (minimal) | claude-sonnet-5 |
|---|---|---|
| Language (matches rule) | fr (yes) | fr (yes) |
| Words (aim 90-120, warn outside 90-170) | 82 | 112 |
| Copy overlap, longest run with a pool bullet or the style reference | 7 words (a CV bullet) | 2 words (a CV bullet) |
| Draft attempts (2 = the automatic retry ran) | 2 | 1 |
| Code errors | 0 | 0 |
| Code warnings | 4 | 0 |
| Claude verifier | passed (0 blocking) | failed (1 blocking) |
| Verdicts | not_a_claim 4, supported 8 | merged 1, not_a_claim 5, supported 9 |
| Draft time | 3.5 s | 65.7 s |
| Verifier time | 16.9 s | 23.4 s |
| Gemini calls / retries 429 / 503 / tokens in-out-thinking | 2 / 0 / 0 / 10803-484-0 | n/a (Claude CLI) |

**gemini-3.5-flash-lite (minimal)**

```text
Subject: Candidature AI System Engineer – Mohamed Hassen Amara

Bonjour Robert,

I'm applying for the AI System Engineer position at ILLUIN Technology and wanted to reach out directly.

During my time at Nexaminds, I designed and shipped a modular FastAPI backend and containerized the system using Docker.

I am based in Tunis and would need visa sponsorship to work in France, though I am willing to relocate for the job.

Please take a look at my attached CV, and let me know if you have time for a short call.

Bien cordialement,
Mohamed Hassen Amara
```

- warning [fragment] “During my time at Nexaminds, I designed and shipped a modular FastAPI backend and containerized the system using Docker.” isn't a sentence about you: write it with “I”
- warning [constraint] Quote the listing's own words for the requirement you mention (it doesn't state it as written)
- warning [length] 79 words (about 90-170 reads best)
- warning [constraint] The listing states no residency, work-permit, on-site or relocation requirement: leave your location, visa and relocation out

Verifier verdicts that are not supported / not_a_claim:
- none

Longest copied run (7 words, a CV bullet): “During my time at Nexaminds, I designed and shipped a modular FastAPI backend and containerized the system using Docker.”

**claude-sonnet-5**

```text
Subject: Candidature AI System Engineer – Mohamed Hassen Amara

Bonjour Robert,

Je postule actuellement au poste d'AI System Engineer chez ILLUIN Technology et je voulais vous contacter directement.

Je suis ingénieur logiciel avec 3 ans d'expérience en ingénierie logicielle. Chez Reality Sports, je conçois des APIs backend avec Spring Boot pour une plateforme sportive en production, et j'ai mis en place des pipelines CI/CD automatisés pour fiabiliser les livraisons. En parallèle, j'ai construit un projet personnel de data lakehouse qui ingère plusieurs saisons de données Premier League via des pipelines Python conteneurisés avec Docker et orchestrés automatiquement.

Seriez-vous disponible pour un bref échange, ou pourriez-vous jeter un œil à mon CV en pièce jointe ?

Bien cordialement,
Mohamed Hassen Amara
```

Verifier verdicts that are not supported / not_a_claim:
- **merged** “These Spring Boot APIs serve a sports platform in production” (The sources keep apart the Spring Boot BFF endpoints (for mobile API integration) and the shipped sports platform; they never say the Spring Boot endpoints are that platform's backend.)


## What was not measured

- This comparison ran with the v14 text before one clause was added to the experience part ("cite by the item's own id, never a fact number or an index"), after the regression eval showed Gemini citing ids that don't exist ("cites unknown ids 6") on the first attempt in all four applied cases. The eval with the clause (the same one retry production makes) has 0 errors on those four cases; the comparison above was not re-run.
- One run per job and generator (no repeat), so run-to-run variance is unknown.
- Claude's draft time includes the CLI start-up; the verifier time includes the call to Claude Opus.
- The Healy and SaltRock listings are the two with an approved CV in the real data; the other three use the scratch CVs described above.
- Requests to the Gemini API for this report (all runs, including the aborted ones and the scratch CVs): about 25, none of them a 429 or 503. They used the scratch copy's counters, not the real DB's, so Settings → Models won't show them.
