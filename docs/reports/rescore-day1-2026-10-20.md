# Rescore, day one (2026-10-20 17:47 UTC)

Prompt `fit_score/v6` on `gemini-3.5-flash-lite` (no thinking, native JSON schema), best stored score first, non-duplicate jobs only, two API keys (key 1 first). Read-only report from the database; raw top-50 snapshot taken before anything changed: `docs/reports/raw/rescore-day1/top50-before.json`.

## 1. Progress

- **Jobs rescored: 283** of 3,999 non-duplicate jobs (7%). Failed: 0. Queue: idle; 0 jobs still queued.
- Quota used today (this app's count): key 1 500/500 (exhausted); key 2 79/500 (ok); key 3 0/500 (ok). Quota resets at 2026-10-21T07:00:00+00:00.
- Model output: 8 of 8 answers valid as returned, 0 HTTP retries (503s), 0 minute-limit retries, 0 fallback switches; average 42.8 s per job with 4 in flight.

## 2. How scores changed (rescored jobs only)

- Mean change -11.4 points (median -10); up by 10+ on 0, down by 10+ on 153, within ±5 on 78 of 283. Because the order is best-first, these are the jobs that were already near the top: expect larger movement on the middle of the list in the next days.

## 3. Top 50 of Discover (New, best fit first): before vs now

**duplicates hidden**: 7 of the 50 are still in the top 50; 43 entered, 43 left. 38 of today's 50 are already scored by v6 (the rest still carry an old score until their turn).

**duplicates shown**: 19 of the 50 are still in the top 50; 31 entered, 31 left. 16 of today's 50 are already scored by v6 (the rest still carry an old score until their turn).

### Today's top 50 (duplicates hidden), with where each was before

| Now | Job | Score now | Rank before | Score before | Scored by |
|---|---|---|---|---|---|
| 1 | #1045 Python Developer - Fully Remote (Mercor) | 100 | 4 | 100 | v6 |
| 2 | #5241 Développeur / Développeuse web mobile (Temporis Experts & Cad) | 97 | new to top 50 | – | v6 |
| 3 | #889 Flutter Developer (Codeway) | 97 | new to top 50 | – | v6 |
| 4 | #899 Freelance Mobile App Developer (iOS / Android) (Mindrift) | 97 | new to top 50 | – | v6 |
| 5 | #890 Flutter Developer ID90602 (AgileEngine) | 97 | new to top 50 | – | v6 |
| 6 | #1366 Python Backend Developer (Remote) (Hire Feed) | 97 | 5 | 100 | v6 |
| 7 | #1622 Flutter developer for mobile apps (m/f/d) (Healy World GmbH) | 97 | new to top 50 | – | v6 |
| 8 | #897 Mobile Engineer (Flutter) (DL Remote) | 97 | new to top 50 | – | v6 |
| 9 | #3227 Data scientist NLP/Ingénieur IA H/F (CDI) (Free-Work) | 94 | 33 | 92 | v6 |
| 10 | #2783 Full-Stack AI Engineer: Build Data Pipelines & L (Mondelez International) | 94 | new to top 50 | – | v6 |
| 11 | #2480 CDI - GenAI Engineer (Matera) | 94 | new to top 50 | – | v6 |
| 12 | #218 Ai Engineer, Backend (Deel) | 94 | new to top 50 | – | v6 |
| 13 | #1036 Python Finance Developer (100% Remote Worldwide) (UBQ Group) | 94 | 1 | 100 | v6 |
| 14 | #2015 Junior AI Native Software Engineer (Accenture France) | 94 | new to top 50 | – | v6 |
| 15 | #138 Consultant·e Machine Learning & AI Engineer – Je (Wavestone) | 94 | new to top 50 | – | v6 |
| 16 | #776 Data Engineer (Synera) | 94 | new to top 50 | – | v6 |
| 17 | #4421 Remote Backend Engineer - Card Checkout (Python/ (Affirm) | 91 | new to top 50 | – | v6 |
| 18 | #4338 AI Prompt Engineer for LLM Automation & Insights (Capitole) | 91 | new to top 50 | – | v6 |
| 19 | #3233 Data scientist NLP/ingénieur informatique IA (IT (Mosofty) | 91 | 39 | 92 | v6 |
| 20 | #3224 SW Tool Developer - Python (Software) | 91 | new to top 50 | – | v6 |
| 21 | #2355 Data Ingénieur - Développement ETL - Services Fi (Sopra Steria) | 91 | new to top 50 | – | v6 |
| 22 | #212 AI Engineer (TomTom) | 91 | new to top 50 | – | v6 |
| 23 | #1808 Python Developer (Fast API / FinTech Project) (Resourceful Talent Gro) | 91 | new to top 50 | – | v6 |
| 24 | #165 Applied AI Engineer (Beamy) | 91 | new to top 50 | – | v6 |
| 25 | #1893 Python Finance Developer (100% Remote Worldwide) (UBQ Group) | 91 | 2 | 100 | v6 |
| 26 | #1451 Python Finance Developer (100% Remote Worldwide) (UBQ Group) | 91 | 3 | 100 | v6 |
| 27 | #2190 Ingénieur IA - Digitalisation des Services F/H (Thales) | 91 | new to top 50 | – | v6 |
| 28 | #48 Junior Data Engineer (Reverse Contact) | 91 | new to top 50 | – | v6 |
| 29 | #921 Backend developer (H/M/X) - (PYTHON-JAVA-C#) (Experis España) | 91 | new to top 50 | – | v6 |
| 30 | #380 AI Engineer / Python Developer - Freelance (Collective.work) | 91 | new to top 50 | – | v6 |
| 31 | #277 Production GenAI ML Engineer (Python) — NLP/LLM (Capitole) | 91 | new to top 50 | – | v6 |
| 32 | #1279 Python Developer (Fast API / FinTech Project) (Resourceful Talent Gro) | 91 | new to top 50 | – | v6 |
| 33 | #1057 Python Developer (Fast API / FinTech Project) (Resourceful Talent Gro) | 91 | new to top 50 | – | v6 |
| 34 | #1901 Python Developer (Fast API / FinTech Project) (Resourceful Talent Gro) | 91 | new to top 50 | – | v6 |
| 35 | #1471 Python Developer (Fast API / FinTech Project) (Resourceful Talent Gro) | 91 | new to top 50 | – | v6 |
| 36 | #2286 Backend Software Engineer (Navan) | 91 | new to top 50 | – | v6 |
| 37 | #2326 Backend Developer – Python/FastAPI - Perm (Confidential company) | 91 | new to top 50 | – | v6 |
| 38 | #1162 AI Engineer - LLM / RAG F/H (STEP UP) | 91 | new to top 50 | – | v6 |
| 39 | #4960 Full Stack Mobile Agentic Engineer (m/w/d) (GAIA) | 90 | new to top 50 | – | older |
| 40 | #4121 Data Engineer: Snowflake Migrations & Airflow Ex (AgileEngine) | 90 | new to top 50 | – | older |
| 41 | #4142 Analytics Engineer: Data Modeling & Product Inte (Creandum) | 90 | new to top 50 | – | older |
| 42 | #4938 MLOps Engineer (m/f/d) (Advantest Europe GmbH) | 90 | new to top 50 | – | older |
| 43 | #5004 Backend Software Engineer – Cloud (m/w/d) (Intercon Solutions Gmb) | 90 | new to top 50 | – | older |
| 44 | #5287 Ingénieur IA & Automatisation (F/H) (Groupe SII) | 90 | new to top 50 | – | older |
| 45 | #4902 AI Automation Engineer (m/f/d) (Orca Group) | 90 | new to top 50 | – | older |
| 46 | #4658 Ingénieur Data et IA H/F (Candidat Ars Auvergne ) | 90 | new to top 50 | – | older |
| 47 | #4909 Agentic AI Engineer (m/f/d) (Kuehne+Nagel) | 90 | new to top 50 | – | older |
| 48 | #4913 AI Engineer (m/w/d) (Trelleborg Group) | 90 | new to top 50 | – | older |
| 49 | #5099 AI & Data Engineer (NTT America) | 90 | new to top 50 | – | older |
| 50 | #4438 Java Developer AWS & Python (Knowmad Mood) | 90 | new to top 50 | – | older |

### Left the top 50

| Job | Score before | Now |
|---|---|---|
| #4203 Revenue Analytics Engineer - Remote (Affirm) | 97 | 88 (rescored) |
| #5122 AI Harness Engineer (100% Remote, Worldwide) (Tether Operations Limi) | 97 | 85 (rescored) |
| #754 ML Engineer (RemoteJobsOne) | 97 | 67 (rescored) |
| #393 ML Engineer (RemoteJobsOne) | 97 | 79 (rescored) |
| #3938 Full-Stack Engineer (Backend Leaning) - Creative A (ElevenLabs) | 94 | 79 (rescored) |
| #4123 Data Engineer ID94415 (AgileEngine) | 92 | 78 (rescored) |
| #4133 Data Engineer (Ai & Data) - Remote (Cmv Consultores) | 92 | 30 (rescored) |
| #4200 Analytics Engineer (Creandum) | 92 | 74 (rescored) |
| #5054 Java Software Developer - Laboratory Instruments ( (Bruker Corporation) | 92 | 80 (rescored) |
| #5057 Java Developer (m/w/d) - Konstanz, Berlin oder rem (SEITENBAU GmbH) | 92 | 69 (rescored) |
| #4899 R&D Engineer - AI Integration (m/f/d) (Advantest Europe GmbH) | 92 | 88 (rescored) |
| #4554 Ingénieur IA Ai Enginee H/F (Hardis Group) | 92 | 88 (rescored) |
| #4918 AI/ML Engineer (Melotech) | 92 | 85 (rescored) |
| #4982 AI Backend Developer (m/w/d) (Sopra Steria) | 92 | 57 (rescored) |
| #4467 Python Developer (Set Europa) | 92 | 85 (rescored) |
| #4469 Python Developer (Orbitant) | 92 | 86 (rescored) |
| #4568 Forward Deployed Engineer – IA Générative / Mistra (Klanik) | 92 | 83 (rescored) |
| #4437 Java Developer IA (100% teletrabajo) (Knowmad Mood) | 92 | 66 (rescored) |
| #4439 Software Developer Java | Python | Kubernetes | Re (Knowmad Mood) | 92 | 80 (rescored) |
| #5118 Satellit - AI Software Engineer Service (Satellit) | 92 | 83 (rescored) |
| #5276 Développeur(se) Python F/H (CGI) | 92 | 70 (rescored) |
| #5022 Backend Engineer (f/m/x) (lemon.markets) | 92 | 70 (rescored) |
| #4304 ML Engineer, Social Casino Games – End-to-End & ML (Gamblingcareers.Com) | 92 | 78 (rescored) |
| #5028 Java Backend Engineer Distributed Systems (m/w/d)  (Exclusive Associates) | 92 | 70 (rescored) |
| #4459 Software Developer Java SDD | 100% Remoto (Knowmad Mood) | 92 | 70 (rescored) |
| #5048 Full-Stack Engineer (Backend Focus) (m/f/d) (Aampere GmbH) | 92 | 67 (rescored) |
| #3108 AI Engineer Innovation F/H (MAIF) | 92 | 75 (rescored) |
| #4354 Mobile App software developer (iOS) (Global Incubator) | 92 | 79 (rescored) |
| #4355 Mobile App software developer (Android) (Global Incubator) | 92 | 82 (rescored) |
| #3021 Apprenti·e Data Engineer H/F (H3 Campus) | 92 | 80 (rescored) |
| #3115 AI Engineer Débutant en CDI - F/H (Ernst & Young) | 92 | 78 (rescored) |
| #2830 Java Backend Developer For Space Traffic Managemen (GMV) | 92 | 76 (rescored) |
| #2585 Ai & Data Engineer: Build Autonomous Agents & Rag  (Havas Media Group Spai) | 92 | 88 (rescored) |
| #2631 Marketing Analytics Engineer — MTA & DBT Data Mode (Seidor) | 92 | 80 (rescored) |
| #2892 Remote Python Backend Engineer – Cloud-Native & Sc (Hyqoo) | 92 | 86 (rescored) |
| #2603 Remote Analytics Engineer, Finance Data Platform (Affirm) | 92 | 86 (rescored) |
| #3211 Développeur Python IT Innovation (AI-Native Develo (Free-Work) | 92 | 85 (rescored) |
| #2643 Data Product Engineer: AI-Driven Analytics & Pipel (Trimble) | 92 | 80 (rescored) |
| #3124 Ai Engineer - CDI (Collective.work) | 92 | 72 (rescored) |
| #3217 Développeur Python IT Innovation (AI-Native Develo (AVANT GARDE IT) | 92 | 88 (rescored) |
| #3133 AI Engineer F/H (OUTSCALE) | 92 | 80 (rescored) |
| #2736 Data Engineer for ML Pipelines & Production (Insud Pharma) | 92 | 80 (rescored) |
| #4034 Backend Engineer - Mission Operations Services (Loft Orbital) | 92 | 80 (rescored) |

## 4. The missing-core cap

- **Jobs capped at the missing-core cap: 1** of 283 rescored (0.4%). Capped by a hard flag instead: 0. Jobs where the model listed at least one core requirement: 168.
- Core requirements by outcome: counted as missing 1, missing but on the "never cap on these alone" list 0, missing but named in your experience 1, covered 259.
- Hard flags among rescored jobs: none.

### The 20 most frequent missing core requirements (these caused caps)

| # | Requirement | Jobs capped |
|---|---|---|
| 1 | agentic workflows | 1 |

### Missing but exempt (the model said missing, the exemption list stopped the cap): tune the list with these

| Requirement | Times |
|---|---|
| none yet | 0 |

### Capped jobs with the biggest drop (stored score before → now)

| Job | Missing | Before | Now |
|---|---|---|---|
| #3889 Satellit - AI Software Engineer | agentic workflows | 92 | 60 |

## 5. Stopped at your request

The rescore was stopped after 283 jobs (the best-scored ones). The other 3,716 were cancelled and keep the score they had (those whose old 35 cap came from an unsupported flag were recomputed by the new flag rule, no model call). The Gemini quota is kept for **new** jobs: "Auto-score new jobs after discovery" is on and the model setting is `gemini-3.5-flash-lite` with prompt v6.

**Read the top of Discover with this in mind:** the 283 rescored jobs lost 11.4 points on average (153 of them 10 or more), because v6 is stricter than the old prompt (it asks for evidence, uses the full range 0-10, and caps jobs missing the role's core requirement). The jobs that were not rescored still carry the older, higher scores, so an old 90 and a new 90 do not mean the same. Comparing within one group is fair; across the two groups, the old ones look better than they are.
