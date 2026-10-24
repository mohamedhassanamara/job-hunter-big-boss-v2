# AI Actions Catalog & Token Estimation Guide

> Comprehensive analysis of all AI-powered actions across **Job Hunter v2**, detailing their purpose, prompt templates, model configurations, execution runtimes, and input/output token estimates.

---

## 1. AI Architecture & Execution Runtimes

The system employs a multi-tier AI strategy designed to balance cost, quality, and rate limits across three distinct runtimes:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Job Hunter v2                                  │
└──────┬───────────────────────────────┬───────────────────────────────┬───────┘
       │                               │                               │
       ▼                               ▼                               ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│  Google API  │               │ Claude Code  │               │    Ollama    │
│  (AI Studio) │               │ Headless CLI │               │ (Local/Cloud)│
└──────┬───────┘               └──────┬───────┘               └──────┬───────┘
       │                               │                               │
       ├─ Fit Scoring                  ├─ Claim Verifier (Opus)        ├─ Local Copilot (Chat)
       ├─ CV Plan Generator            ├─ Fit Confirm (Sonnet)         ├─ Research Extractor
       └─ Email Drafter                ├─ Cover Letters & Answers      └─ Hook Check
                                       ├─ LinkedIn Drafter
                                       ├─ Interview Prep
                                       ├─ Document Critique
                                       └─ Copilot Rewriter
```

1. **Google AI Studio API (Free Tier Key Pool)**:
   - *Driver*: `app/providers/gemini.py`, `app/providers/gemini_generate.py`
   - *Key Management*: `app/services/gemini_keys.py` (rotates across free keys, handles 15 RPM / 250K TPM / 500 RPD, auto-parks exhausted keys).
   - *Mechanism*: Native JSON schema validation (`responseJsonSchema`), configurable thinking levels (`minimal`, `dynamic`).
   - *Tasks*: Bulk Fit Scoring, CV Plan Generation, Outreach Emails.

2. **Claude Code Headless Mode (`claude -p`)**:
   - *Driver*: `app/providers/claude_cv.py` (base class for all Claude drafters)
   - *Isolation*: Runs `claude -p` inside an empty temp directory without tools, MCP configs, or session persistence. Enforces `apiKeySource == "none"` (billed exclusively to the user's Anthropic Pro/Team subscription, never an API key).
   - *Mechanism*: Constrained JSON schema output via CLI `--json-schema`.
   - *Tasks*: Claim Verification (Opus), Fit Confirmation, Cover Letters, Application Form QA, LinkedIn Messages, Interview Prep, Document Critique, Copilot Answer Rewriting.

3. **Ollama (Local / Cloud API)**:
   - *Driver*: `app/providers/ollama.py`, `app/providers/ollama_chat.py`, `app/services/research.py`
   - *Mechanism*: Direct HTTP chat completion (`http://localhost:11434/api/chat`). Local models use native schema grammar constraints (`format`) and `think: false`. Cloud models (`*-cloud`) include the schema in the system prompt.
   - *Tasks*: Real-time Copilot chat, Web Research Signal Extraction, Hook Faithfulness checking, optional offline Fit Scoring fallback.

---

## 2. Master Summary Table

| # | Action | Purpose | Prompt Template | Default Model | Execution Runtime | Est. Input Tokens (Typ) | Est. Output Tokens (Typ) |
|---|---|---|---|---|---|---|---|
| **1** | **Job Fit Scoring** | Evaluates fit across 5 dimensions + disqualifiers | `prompts/fit_score.md` (v6) | `gemini-3.5-flash-lite` | Google AI Studio REST | 4,200 | 550 |
| **2** | **Fit Confirmation** | Second opinion / verdict ("Ask Claude") | `fit_score.md` + `confirm_verdict.md` (v1) | `claude-sonnet-5-5` | `claude -p` CLI (fallback Gemma) | 4,500 | 650 |
| **3** | **CV Tailoring & Plan** | Adapts bullets, ranks items, drafts summary | `prompts/cv_generate.md` (v11) | `gemini-3.5-flash-lite` | Google AI Studio / `claude -p` | 6,500 | 1,400 |
| **4** | **CV Summary Rewrite** | Regenerates/edits summary sentences | `cv_generate.md` (`## summary` / `## revise`) | `gemini-3.5-flash-lite` | Google AI Studio / `claude -p` | 5,500 | 250 |
| **5** | **Cover Letter (Standard)** | Formal letter for direct web applications | `prompts/cover_letter.md` (`## system`, v8) | `claude-sonnet-5` | `claude -p` CLI | 4,800 | 380 |
| **6** | **Cover Letter (Form Box)** | Concise ATS text-box response | `cover_letter.md` (`## form`) | `claude-sonnet-5` | `claude -p` CLI | 4,200 | 280 |
| **7** | **Application Form QA** | Answers custom ATS application questions | `cover_letter.md` (`## answers`) | `claude-sonnet-5` | `claude -p` CLI | 4,500 | 350 |
| **8** | **Cold Email (Speculative)** | Introductory outreach citing company signals | `prompts/outreach.md` (`## system`, v14) | `gemini-3.5-flash-lite` | Google AI Studio / `claude -p` | 7,200 | 280 |
| **9** | **Cold Email (Applied)** | Honest follow-up for submitted applications | `outreach.md` (`## applied`) | `gemini-3.5-flash-lite` | Google AI Studio / `claude -p` | 6,200 | 240 |
| **10** | **Research Extraction** | Extracts signals from scraped company pages | `prompts/research.md` (v1) | `gemma4:31b-cloud` | Ollama HTTP (local fallback) | 3,800 / chunk | 450 / chunk |
| **11** | **Hook Faithfulness Check** | Validates email hook against cited signals | `prompts/hook_check.md` (v1) | `gemma4:31b-cloud` | Ollama HTTP (local fallback) | 650 | 120 |
| **12** | **LinkedIn Drafting** | Connection notes, follow-ups, InMails | `prompts/linkedin.md` (v5) | `claude-sonnet-5` | `claude -p` CLI | 4,200 | 130 |
| **13** | **Claim Verifier** | Zero-tolerance fact-checking against sources | `prompts/verify.md` (v7) | `claude-opus-5-5` | `claude -p` CLI | 5,800 | 850 |
| **14** | **Document Critique** | Reader-perspective weak point feedback | `prompts/critique.md` (v1) | `claude-sonnet-5` | `claude -p` CLI | 4,500 | 320 |
| **15** | **Interview Preparation** | Tailored pitch, STAR stories & likely Q&A | `prompts/interview_prep.md` (v1) | `claude-sonnet-5` | `claude -p` CLI | 5,200 | 1,200 |
| **16** | **Job Search Copilot Chat** | Interactive search & strategy assistant | `prompts/copilot.md` (`## system`, v2) | `gemma4:12b` | Local Ollama Stream | 4,800 | 350 |
| **17** | **Copilot Answer Rewrite** | Polishes Copilot message for human sending | `copilot.md` (`## rewrite`) | `claude-sonnet-5` | `claude -p` CLI | 5,000 | 200 |

---

## 3. Detailed Action Specifications

### 1. Job Fit Scoring

* **Used For**: Automated scoring of raw job listings against candidate profile and master experience. Evaluates 5 dimensions (Role Match, Skills Match, Seniority Fit, Location Eligibility, Language Requirements), checks explicit disqualifying flags (visa sponsorship, residency, nationality, etc.), and identifies core requirements.
* **Trigger / Location**: Discovery pipeline, batch scoring queue (`services/scoring.py`), or manual rescore (`POST /api/scoring/jobs/{id}/score`).
* **Prompt**:
  * **System Prompt**: `app/prompts/fit_score.md` (~2,430 tokens). Strict literal rubric, scoring weights, disqualifier rules.
  * **User Prompt**: Constructed via `scoring.render()`. Formatted candidate profile (headline, location, work authorization, target countries, languages, years experience, track info), candidate experience text, and job text (title, company, location, remote policy, description truncated to max 15,000 chars / ~3,750 tokens).
  * **Schema**: Inlined `FitAssessment` JSON Schema (~500 tokens).
* **Model & Runtime**:
  * **Default**: `gemini-3.5-flash-lite` (via Google AI Studio API, key pool).
  * **Alternates**: Ollama models (`qwen2.5:7b` local or `gemma4:31b-cloud`).
  * **Config**: Temperature = 0, thinking disabled (`think: false` / `minimal`).
* **Token Estimation**:
  * **Input Tokens**:
    * Min: ~3,200 tokens (short listing ~400 tokens)
    * Typical: ~4,200 tokens (average listing ~1,200 tokens)
    * Max: ~6,800 tokens (full 15,000 char listing ~3,750 tokens + large experience text)
  * **Output Tokens**:
    * Typical: ~500 – 650 tokens (5 dimension objects with score, reason, evidence; 6 flag checks; 2-4 core requirements; strengths; gaps; summary).

---

### 2. Job Fit Confirmation ("Ask Claude" / Second Opinion)

* **Used For**: Independent second opinion on a specific job, generating an explicit qualitative verdict (`apply`, `maybe`, `skip`) with short rationale for seniority, skills, location/visa, and language. Stored alongside the primary score without overwriting it.
* **Trigger / Location**: User click in Job Details panel via `POST /api/scoring/jobs/{id}/confirm` (`services/confirmation.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/fit_score.md` combined with `app/prompts/confirm_verdict.md` (~2,600 tokens).
  * **User Prompt**: Same as Fit Scoring (`scoring.render()`).
  * **Schema**: `ConfirmationAnswer` (`FitAssessment` extended with `Verdict` schema).
* **Model & Runtime**:
  * **Waterfall Order**:
    1. Primary: `claude-sonnet-5-5` via `claude -p` (headless CLI, subscription).
    2. Fallback: `gemma-4-31b-it` via Gemini API.
    3. User fallback: Manual copy-paste prompt for Gemini Pro web app.
* **Token Estimation**:
  * **Input Tokens**: ~3,500 – 6,500 tokens (Typical: ~4,500 tokens).
  * **Output Tokens**: ~550 – 800 tokens (Typical: ~650 tokens).

---

### 3. CV Tailoring & Plan Generation

* **Used For**: Synthesizes a tailored one-page CV plan for a specific job from the candidate's master experience pool. Selects relevant roles, adapts bullet points, prioritizes technical skills, selects projects, and writes grounded professional summaries.
* **Trigger / Location**: CV Studio "Tailor CV" button via `POST /api/cv/applications/{id}/generate` (`services/cv_service.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/cv_generate.md` (`## system`, v11, ~2,450 tokens). Strict grounding rules: only facts from pool, light adaptations, no LaTeX markup, fact citation tracking.
  * **User Prompt**: `claude_cv.user_message()`. Writing guide, layout constraints, style exemplar, facts (allowed years statements), job details, track emphasis, and full candidate experience pool in JSON.
  * **Schema**: `CVPlanDraft` (~600 tokens).
* **Model & Runtime**:
  * **Default**: `gemini-3.5-flash-lite` via Google AI Studio API (`gemini_generate.py`).
  * **Alternate / Override**: `claude-sonnet-5` via `claude -p` CLI (`use="claude"` button or settings).
* **Token Estimation**:
  * **Input Tokens**:
    * Min: ~4,800 tokens (small pool, short listing)
    * Typical: ~6,500 tokens (standard pool ~2,500 tokens, listing ~1,000 tokens)
    * Max: ~9,000 tokens (large pool with many bullets, projects, skills)
  * **Output Tokens**:
    * Typical: ~1,200 – 1,600 tokens (3-5 cited summary sentences, categorized skill arrays, 3-5 roles with 3-5 adapted bullets each, 2-3 projects with tags, education, certifications).

---

### 4. CV Summary Regeneration & Revision

* **Used For**: Targeted re-generation or interactive tweaking of only the CV summary (full version and tight/short version) without re-generating the entire CV. Used when grounding validation rejects a summary sentence, or when the user enters custom revision feedback.
* **Trigger / Location**: Automatic grounding recovery in `cv_service.py`, or user feedback via `POST /api/cv/versions/{id}/summary`.
* **Prompt**:
  * **System Prompt**: `app/prompts/cv_generate.md` (`## summary` section for rejected sentence recovery, or `## revise` for user feedback).
  * **User Prompt**: Current summary, user feedback, check issues, writing guide, facts, job, emphasis, and pool JSON.
  * **Schema**: `SummaryDraft` (`summary_sentences`, `summary_short_sentences`).
* **Model & Runtime**:
  * Same as CV Generator (`gemini-3.5-flash-lite` or `claude-sonnet-5`).
* **Token Estimation**:
  * **Input Tokens**: ~4,500 – 7,500 tokens (Typical: ~5,500 tokens).
  * **Output Tokens**: ~180 – 350 tokens (Typical: ~250 tokens; 4-5 total cited sentences).

---

### 5. Cover Letter Drafting (Standard Letter)

* **Used For**: Writes a complete, tailored cover letter (lettre de motivation) for a direct web application. Includes specific company interest, 1-2 concrete proof points from the approved CV, logistics/visa fit, and an interview ask.
* **Trigger / Location**: Cover Letter page "Generate letter" via `POST /api/letters/applications/{id}/generate` (`services/cover_letter.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/cover_letter.md` (`## system`, v8, ~2,498 tokens). Enforces structure, pool citations, tone, French/English rules, and bans clichés. Appends `## revise` or `## retry` as needed.
  * **User Prompt**: `letter_message()`. Target language, banned phrases, candidate facts (years, work authorization, location), job details, and approved CV items pool subset JSON.
  * **Schema**: `CoverLetterPlan` (paragraphs of cited `EmailSentence`s + `ask`).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI (`models.letter.model`, subscription only).
* **Token Estimation**:
  * **Input Tokens**: ~3,800 – 6,200 tokens (Typical: ~4,800 tokens).
  * **Output Tokens**: ~300 – 500 tokens (Typical: ~380 tokens; 2-3 structured paragraphs).

---

### 6. Cover Letter Form-Box Text

* **Used For**: Generates concise cover letter text formatted specifically for an ATS text field (e.g. "Why do you want to work here?"), stripped of formal letter headers, dates, and closing formulas.
* **Trigger / Location**: "Generate for form" via `POST /api/letters/applications/{id}/generate-form`.
* **Prompt**:
  * **System Prompt**: `app/prompts/cover_letter.md` (`## form` section, ~1,800 tokens).
  * **User Prompt**: Same as Standard Letter.
  * **Schema**: `CoverLetterPlan`.
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI.
* **Token Estimation**:
  * **Input Tokens**: ~3,500 – 5,500 tokens (Typical: ~4,200 tokens).
  * **Output Tokens**: ~200 – 350 tokens (Typical: ~280 tokens; 1-2 compact paragraphs).

---

### 7. Application Form Question Answering (Batch QA)

* **Used For**: Batch-answers custom application form questions (e.g. technical questions, behavioral queries, notice period, salary expectations) grounded strictly in the candidate's approved CV and profile while enforcing character limits.
* **Trigger / Location**: "Answer questions" button via `POST /api/letters/applications/{id}/answers/generate` (`services/answers.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/cover_letter.md` (`## answers` section, ~2,100 tokens). Appends `## answers_retry` on automated retry.
  * **User Prompt**: `answers_message()`. Rules, facts, indexed questions list (`[{id, question, char_limit}]`), job, and experience pool.
  * **Schema**: `AnswersPlan` (list of `AnswerDraft` with `question_id` and cited sentences).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI. Includes an automatic single-retry mechanism for any questions that exceed character limits or fail checks.
* **Token Estimation**:
  * **Input Tokens**: ~3,500 – 6,500 tokens (Typical: ~4,500 tokens).
  * **Output Tokens**: ~150 – 600 tokens (Typical: ~350 tokens for 2-4 questions).

---

### 8. Cold Outreach Email Generation (Speculative / Introduction)

* **Used For**: Drafts a personal introduction email to a decision-maker when no public application is being referenced. Pairs verified company signals into a hook, states an inferred team problem, proves competence using approved CV items, and makes a direct call ask.
* **Trigger / Location**: Outreach tab "Draft email" (Speculative mode) via `POST /api/outreach/applications/{id}/draft` (`services/outreach.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/outreach.md` (`## system`, v14, ~4,136 tokens). Very detailed guidance on signal usage, no casual assumptions, proof point framing, tone rules.
  * **User Prompt**: `claude_email.user_message()`. Rules, candidate facts, recipient contact, company signals JSON, job description (marked private), and approved CV items.
  * **Schema**: `IntroEmailPlan` (subject, greeting, hook with signal_ids, intro_focus, problem, proofs, ask).
* **Model & Runtime**:
  * **Default**: `gemini-3.5-flash-lite` (API) or `claude-sonnet-5` (`claude -p`).
* **Token Estimation**:
  * **Input Tokens**: ~5,800 – 9,500 tokens (Typical: ~7,200 tokens).
  * **Output Tokens**: ~220 – 380 tokens (Typical: ~280 tokens).

---

### 9. Cold Outreach Email Generation (Applied / Follow-up)

* **Used For**: Drafts an honest, professional follow-up email to a hiring manager or recruiter for an open role the candidate has applied (or is applying) for. Cites core requirements, addresses constraints transparently (visa/residency), and asks for CV review.
* **Trigger / Location**: Outreach tab "Draft email" (Applied mode) via `POST /api/outreach/applications/{id}/draft`.
* **Prompt**:
  * **System Prompt**: `app/prompts/outreach.md` (`## applied` section, ~3,200 tokens).
  * **User Prompt**: `claude_email.applied_message()`. Rules, facts, contact, style reference examples, optional signals, job description, and approved CV pool.
  * **Schema**: `AppliedEmailPlan` (role, greeting, opening, experience proofs, constraint, constraint_quote, signal, ask).
* **Model & Runtime**:
  * `gemini-3.5-flash-lite` (API) or `claude-sonnet-5` (`claude -p`).
* **Token Estimation**:
  * **Input Tokens**: ~5,000 – 8,000 tokens (Typical: ~6,200 tokens).
  * **Output Tokens**: ~180 – 320 tokens (Typical: ~240 tokens).

---

### 10. Company Research Signal Extraction

* **Used For**: Scrapes company web pages (about, products, news, careers) and recent news RSS/GDELT feeds, converting raw text into structured company signals with verbatim supporting quotes.
* **Trigger / Location**: Automatically before drafting speculative emails (`outreach.draft_with_research`) or on-demand via `POST /api/research/companies/{id}/run` (`services/research.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/research.md` (v1, ~424 tokens). Instructs model to extract up to 8 concrete signals with verbatim quotes.
  * **User Prompt**: `user_message(company, sources)`. Raw scraped text chunked into batches of up to 14,000 characters (~3,500 tokens).
  * **Schema**: `Extraction` (`signals`: list of `RawSignal` with type, fact, quote, url, title).
* **Model & Runtime**:
  * **Default**: `gemma4:31b-cloud` via Ollama HTTP API.
  * **Fallback**: Local `gemma4:12b` via Ollama if cloud limits are reached.
  * **Invocations**: 1 to 3 calls per company (one per 14k-character chunk).
* **Token Estimation** (per chunk):
  * **Input Tokens**: ~2,500 – 4,200 tokens (Typical: ~3,800 tokens).
  * **Output Tokens**: ~300 – 600 tokens (Typical: ~450 tokens; 4-8 extracted signals).

---

### 11. Hook Faithfulness Verification

* **Used For**: Evaluates the email's opening hook sentence against the exact company signals it references, ensuring the hook does not invent facts, merge disparate signals, or create unverified causal claims.
* **Trigger / Location**: Automatically called after draft generation and on manual edit/approval in `services/hook_check.py`.
* **Prompt**:
  * **System Prompt**: `app/prompts/hook_check.md` (v1, ~324 tokens).
  * **User Prompt**: `SIGNALS:\n...` and `HOOK:\n...`.
  * **Schema**: `HookReview` (`claims`: list of `HookClaim` with verdict `stated`, `causal`, `combined`, `not_stated`).
* **Model & Runtime**:
  * `gemma4:31b-cloud` via Ollama (fallback `gemma4:12b`).
* **Token Estimation**:
  * **Input Tokens**: ~450 – 850 tokens (Typical: ~650 tokens).
  * **Output Tokens**: ~80 – 180 tokens (Typical: ~120 tokens).

---

### 12. LinkedIn Message Drafting (Note, Follow-Up, InMail)

* **Used For**: Generates tailored LinkedIn outreach messages: connection request notes (strictly under 300 characters), application follow-ups, or InMails, styled specifically for the recipient persona (recruiter vs peer engineer vs leader).
* **Trigger / Location**: LinkedIn tracking tab via `POST /api/linkedin/outreach/{id}/draft` (`services/linkedin_track.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/linkedin.md` (`## system` + persona guidance + specific section: `## note`, `## followup`, `## inmail`, v5, ~1,566 tokens).
  * **User Prompt**: `user_message()`. Recipient persona details, candidate facts, job details, experience pool, and optional revision notes.
  * **Schema**: `LinkedInMessage` (subject, text, citations, signal_ids).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI (subscription only).
* **Token Estimation**:
  * **Input Tokens**: ~3,200 – 5,500 tokens (Typical: ~4,200 tokens).
  * **Output Tokens**: ~60 – 180 tokens (Typical: ~130 tokens; connection note is ≤ 300 chars / ~60 tokens).

---

### 13. Claim Verifier (Fact-Checking Pass)

* **Used For**: Independent, zero-tolerance fact-checking pass on all candidate texts (emails, cover letters, form answers, LinkedIn notes, interview prep). Splits the text into atomic claims and verifies each claim against named sources (pool items, CV, facts, company signals, job listing). Flags unsupported, exaggerated, causal, or merged claims.
* **Trigger / Location**: On document generation, before email sending gate, on approval, or on-demand via `services/verifier.py`.
* **Prompt**:
  * **System Prompt**: `app/prompts/verify.md` (v7, ~2,045 tokens). Exhaustive verification rubric, verdict definitions, and rewriting instruction for flagged claims.
  * **User Prompt**: `message(request)`. Passes KIND, the full final TEXT, and every available labelled SOURCE.
  * **Schema**: `VerifyPlan` (`claims`: list of `VerifyClaim` with sentence, claim, about, verdict, source_id, source_quote, reason, suggestion).
* **Model & Runtime**:
  * `claude-opus-5-5` via `claude -p` CLI (most capable reasoning model, subscription only).
* **Token Estimation**:
  * **Input Tokens**: ~4,200 – 8,500 tokens (Typical: ~5,800 tokens).
  * **Output Tokens**: ~500 – 1,600 tokens (Typical: ~850 tokens; 6-15 evaluated atomic claims with quotes and fixes).

---

### 14. Application Document Critique

* **Used For**: Reviews an application document (CV, cover letter, email, LinkedIn message) from the recipient's perspective and highlights up to 6 weak points (unbacked claims, weak opening, buried evidence, duties vs outcomes, vagueness, gaps) without rewriting it.
* **Trigger / Location**: "Critique" button on document editors via `POST /api/critique/{kind}/{id}` (`services/critique.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/critique.md` (v1, ~422 tokens). Prioritized critique rubric.
  * **User Prompt**: Document kind, full text, automated lexical checks (unbacked terms, dropped tools), job description, and experience pool JSON.
  * **Schema**: `CritiquePlan` (`issues`: list of `CritiqueIssue` with where, issue, why).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI.
* **Token Estimation**:
  * **Input Tokens**: ~3,500 – 6,000 tokens (Typical: ~4,500 tokens).
  * **Output Tokens**: ~200 – 450 tokens (Typical: ~320 tokens; up to 6 structured critique items).

---

### 15. Interview Preparation & STAR Stories

* **Used For**: Prepares the candidate for an interview for a specific job: drafts an elevator pitch ("tell me about yourself") connecting their background to the role, creates 3-4 STAR stories grounded in pool items, predicts 6-8 probing questions, and suggests 3-4 questions to ask the interviewer.
* **Trigger / Location**: "Prepare for interview" button in pipeline via `POST /api/interview/applications/{id}/prepare` (`services/interview_prep.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/interview_prep.md` (v1, ~781 tokens). STAR methodology, grounding rules, question design.
  * **User Prompt**: Rules, candidate facts, job description, and experience pool JSON.
  * **Schema**: `InterviewPrepPlan` (`pitch`, `stories`, `questions`, `ask_them`).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI.
* **Token Estimation**:
  * **Input Tokens**: ~4,000 – 7,000 tokens (Typical: ~5,200 tokens).
  * **Output Tokens**: ~900 – 1,800 tokens (Typical: ~1,200 tokens).

---

### 16. Job Search Copilot Chat

* **Used For**: Real-time conversational assistant in the sidebar. Helps the candidate brainstorm interview answers, compare CV against listings, understand skill gaps, formulate positioning, and draft translations.
* **Trigger / Location**: Copilot chat interface via `POST /api/copilot/threads/{id}/messages` (streamed) (`services/copilot.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/copilot.md` (`## system`, v2, ~678 tokens). Strict grounding rules: only candidate facts from CONTEXT, only job facts from listing.
  * **Context / User**: Full candidate profile, experience pool JSON, job listing (up to 7,000 chars), fit score with reasons, approved CV text, cover letter text, and past 12 messages of conversation history.
* **Model & Runtime**:
  * Local Ollama model `gemma4:12b` (streamed HTTP SSE, temperature 0.3, num_ctx 16384).
* **Token Estimation**:
  * **Input Tokens**: ~3,200 – 7,500 tokens (Typical: ~4,800 tokens; grows with thread history).
  * **Output Tokens**: ~150 – 700 tokens (Typical: ~350 tokens per conversational turn).

---

### 17. Copilot Answer Rewrite with Claude

* **Used For**: Rewrites a draft answer or message produced by the local Copilot model into high-polish, human-sending-ready text using Claude, stripping unbacked claims and clichés.
* **Trigger / Location**: "Rewrite with Claude" button under a Copilot assistant message via `POST /api/copilot/messages/{id}/rewrite` (`services/copilot.py`).
* **Prompt**:
  * **System Prompt**: `app/prompts/copilot.md` (`## rewrite` section, ~250 tokens). Strict instruction to output JSON only `{"text": "..."}`.
  * **User Prompt**: Original user question, original Copilot answer, and full context (job, pool, profile).
  * **Schema**: `RewriteOut` (`text`).
* **Model & Runtime**:
  * `claude-sonnet-5` via `claude -p` CLI.
* **Token Estimation**:
  * **Input Tokens**: ~3,500 – 7,500 tokens (Typical: ~5,000 tokens).
  * **Output Tokens**: ~100 – 350 tokens (Typical: ~200 tokens).

---

### 18. Evaluation Frameworks (Developer Tooling)

The project includes three offline evaluation harnesses used to benchmark prompts and models against test datasets:

1. **Fit Scoring Evaluation (`make eval` / `app/eval/run.py`)**:
   - Scores labeled jobs against reference ground truth to report agreement metrics.
   - *Model*: Configured FitScorer (`gemini-3.5-flash-lite` or `qwen2.5:7b`).
   - *Tokens per run*: ~4,200 input, ~550 output per labeled job.

2. **Email Regression Evaluation (`make eval-emails` / `app/eval/emails.py`)**:
   - Re-runs outreach prompt against reference examples (`data/eval/email_examples.json`) to detect regressions across prompt versions.
   - *Model*: Configured EmailDrafter (`gemini-3.5-flash-lite` or `claude-sonnet-5`).
   - *Tokens per run*: ~6,500 input, ~280 output per case.

3. **Verifier Regression Evaluation (`make eval-verifier` / `app/eval/verifier.py`)**:
   - Runs `must_pass` and `must_fail` test cases against the Claim Verifier.
   - *Model*: `claude-opus-5-5` via `claude -p`.
   - *Tokens per run*: ~5,800 input, ~850 output per test case.

---

### 19. External AI Workflow (Assisted Prompt Builder)

* **Location**: `app/services/external_ai.py`
* **Mechanism**: Generates a self-contained, sanitized prompt extracting relevant pool items, job listing, and rules. The user pastes this into web AI tools (ChatGPT, Claude web, Gemini Pro). When pasted back into Job Hunter v2, the text is run through the Claim Verifier (**Action 13**) for fact-checking.
* **Direct Token Usage**: 0 tokens executed by the app directly for generation; standard Claim Verifier tokens applied upon pasting.

---

## 4. Cumulative Token Consumption Profile (Per Job Pipeline)

To estimate the typical token footprint for processing a single job from discovery to full application:

| Step / Action | Model | Input Tokens | Output Tokens | Total Tokens |
|---|---|---:|---:|---:|
| 1. Fit Scoring | `gemini-3.5-flash-lite` | 4,200 | 550 | 4,750 |
| 2. Fit Confirmation ("Ask Claude") *(optional)* | `claude-sonnet-5-5` | 4,500 | 650 | 5,150 |
| 3. Tailored CV Generation | `gemini-3.5-flash-lite` | 6,500 | 1,400 | 7,900 |
| 4. Cover Letter Generation | `claude-sonnet-5` | 4,800 | 380 | 5,180 |
| 5. Cover Letter Claim Verification | `claude-opus-5-5` | 5,800 | 850 | 6,650 |
| 6. Company Research (2 chunks) *(if cold outreach)* | `gemma4:31b-cloud` | 7,600 | 900 | 8,500 |
| 7. Outreach Email Generation | `gemini-3.5-flash-lite` | 7,200 | 280 | 7,480 |
| 8. Hook Faithfulness Verification | `gemma4:31b-cloud` | 650 | 120 | 770 |
| 9. Email Claim Verification | `claude-opus-5-5` | 5,800 | 850 | 6,650 |
| 10. LinkedIn Outreach Note *(optional)* | `claude-sonnet-5` | 4,200 | 130 | 4,330 |
| 11. LinkedIn Claim Verification *(optional)* | `claude-opus-5-5` | 5,200 | 600 | 5,800 |
| 12. Interview Preparation *(optional)* | `claude-sonnet-5` | 5,200 | 1,200 | 6,400 |
| **Typical End-to-End Pipeline Total (All Steps)** | | **~61,650** | **~7,910** | **~69,560** |

*Note: In the default setup, Fit Scoring, CV Generation, and Email Drafting run on Google AI Studio's free tier; Research and Hook Check run on Ollama; and Cover Letters, LinkedIn, Interview Prep, and Claim Verification run on the user's flat-rate Anthropic Claude Code subscription.*
