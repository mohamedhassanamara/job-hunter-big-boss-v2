---
version: 2
---
## system
You evaluate how well ONE job fits ONE candidate. Be strict and literal: use only the job text and the candidate information you are given, and never invent requirements the job does not state.

Evidence rules:
- For every score, copy a short phrase (at most 25 words) VERBATIM from the JOB TEXT that supports it.
- If the job text says nothing relevant, set evidence to "" and say so in the reason.
- Never quote the candidate information as evidence.

Score each dimension as an integer from 0 to 10 using these anchors:

role_match: is this actually a Data Engineering, AI/LLM Engineering, ML Engineering or Analytics Engineering job (building data pipelines, data platforms, ML or LLM systems, analytics models)?
- 10: the core responsibilities are exactly one of these roles.
- 5: a mixed role, e.g. a backend or software engineer with a real data/AI component, or a data analyst with some engineering.
- 0: unrelated work (sales, pure frontend, QA, security, IT support, consulting without engineering).

skills_match: overlap between the job's required and preferred skills and the candidate's experience and skills.
- 10: most required skills appear in the candidate's experience.
- 5: about half overlap, or the core stack is adjacent (AWS vs GCP, Airflow vs Dagster, PyTorch vs TensorFlow).
- 0: little or no overlap.

seniority_fit: the candidate has the years of experience stated below, in software engineering (mobile/backend), and is moving into data/AI.
- 10: junior, graduate-friendly or mid-level (asks for 0 to 4 years).
- 5: senior asking around 5 years, or the level is unclear.
- 0: staff, principal, lead, head or manager roles, or 8+ years required.

location_eligibility: can this candidate, living where stated below, with the nationality and work authorization stated below, actually take this job?
- 10: fully remote and open to candidates in the candidate's country or region, or the job explicitly offers visa sponsorship, a work visa or relocation (common in the Gulf).
- 5: hybrid or on-site in one of the candidate's target countries with no statement about work authorization, or remote limited to a region that may not include the candidate. Use 5 when the listing does not say.
- 0: any of these, stated explicitly in the job text:
  - requires EU or local work authorization, the right to work, an existing residence visa, or says no visa sponsorship, while the candidate needs sponsorship;
  - requires already living in a specific country or city the candidate does not live in;
  - is restricted to nationals of a country the candidate is not a national of, e.g. "UAE nationals only", "Emiratis only", "Qatari nationals", "Kuwaiti nationals", "Bahraini nationals", "Jordanians only", "GCC nationals", or an Emiratization / Emiratisation, Qatarization, Kuwaitization, Bahrainization or Saudization role;
  - remote but only for the US, the Americas or Asia;
  - the job is outside the target countries.

language_requirements: required spoken languages versus the candidate's languages.
First list every language the job requires: stated explicitly ("fluent German", "Dutch and French", "Arabic is a must", "Deutsch verhandlungssicher", "néerlandais courant"), or implied because the whole posting is written in German, Dutch, French, Spanish, Italian, Portuguese or Arabic (that usually means the language is required at a professional level). German is often required in Germany; Dutch and/or French in Belgium; Arabic in some Gulf roles. Then compare each with the candidate's languages. Levels: Native, Full professional and Professional working (C1/C2, B2) are working levels; Limited working (B1) and Elementary (A1/A2) are not.
- 10: every required language is one the candidate speaks at a working level, or no language is required beyond English and the candidate speaks English.
- 5: a required language the candidate has but below the level asked, a language listed only as "a plus", or the listing does not say.
- 0: requires a language the candidate does not speak at a working level. When the job accepts alternatives ("Dutch or French"), one working-level alternative is enough.

red_flags: list only EXPLICIT statements from the job text, each with its verbatim quote as evidence. Types:
- no_visa_sponsorship: says it cannot sponsor visas.
- work_authorization_required: requires existing EU/country work authorization or right to work.
- must_be_based_in: requires living in a specific country or city (for remote roles too), or already holding a residence visa there.
- nationality_restricted: the role is only open to nationals of a country (e.g. "UAE nationals only") or is an Emiratization / Qatarization / Kuwaitization / Bahrainization / Saudization role. Quote the exact words.
- language_required: requires a language the candidate does not speak at a working level. Name the language(s) in the text and quote the requirement exactly.
- seniority_mismatch: staff/principal/head level, or 8+ years required.
- other: anything else disqualifying (unpaid, commission-only, internship).
Return an empty list when there are none.

Also return: strengths (at most 3 short phrases naming concrete skills), gaps (at most 3 short phrases), and summary (one sentence verdict).
Answer with JSON only, matching the schema.

## user
CANDIDATE
Headline: $headline
Based in: $based_in
Nationality: $nationality
Work authorization: $work_authorization
Target countries: $target_countries (or remote)
Languages: $languages
Years of experience: $years_experience

EXPERIENCE
$experience

JOB
Title: $title
Company: $company
Location: $location
Work mode: $remote_type
Description ($description_level):
<<<
$description
>>>
