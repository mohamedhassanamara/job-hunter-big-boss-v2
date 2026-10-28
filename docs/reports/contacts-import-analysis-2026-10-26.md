# Contacts import analysis (2026-10-26)

Phase 1, read-only. Run on a SQLite backup copy of `data/jobhunter.db` (real DB untouched: same mtime and size before and after). No provider or model calls, no network, no discovery, nothing sent. Script: `backend/scripts/analyze_contacts_import.py` (refuses the real DB path, opens the copy `mode=ro`). Counts only; at most 3 masked examples per file.

## Headline

- 25,224 rows in 8 files become **8,927 truly new contacts with a usable email** (plus 152 new people with no usable email).
- Most of what the "old" files hold is already in the DB: 12,324 unique rows match existing contacts (11,812 identical). Only the Wejdi list (7,928), France-Akram (623) and New Germany (373) add real new people. New France adds none.
- **Value for your open jobs is small: 38 new contacts at 31 companies with open jobs, giving a first contact to 46 open jobs** (of 3,450 open jobs, 2,947 have no contact yet). None of the 46 is past the New stage. The other 8,496 new contacts are at 8,382 companies you have no job for (a pool for later, not for today's jobs).
- Apollo's `Email Status` is `User Managed` on 92% of rows (it says nothing about deliverability). 1,184 rows say `Potentially Invalid`, so every imported email must stay unverified.

## 1. Files

All eight are Apollo exports with the same ~54 columns, comma-delimited, UTF-8 (no BOM, no bad bytes). The existing importer maps 7 of its 8 fields from them; `full_name` is unmapped everywhere (it uses First + Last Name, which is fine). Unmapped by the importer and ignored today: Email Status, Seniority, Departments, # Employees, Country, City, Industry, Company Linkedin Url, Do Not Call, Stage, Lists, Last Contacted, phones, Keywords, Tech, social URLs and others (about 45 columns). `Wejdi` has no `Address` column and calls `Tech` `Technologies`. Country, size and Company LinkedIn URL are usable for matching and for the size-aware ranking. The existing importer never reads them.

| File | Rows | Mappable | Usable email | No email | Role / free / invalid / Apollo-invalid | Dup (in file / across) | Unique | Match existing | New valid |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| new france.csv | 227 | 227 | 227 | 0 | 0 / 0 / 0 / 0 | 0 / 0 | 227 | 227 | 0 |
| new germany.csv | 610 | 610 | 610 | 0 | 0 / 0 / 0 / 0 | 4 / 226 | 380 | 7 | 373 |
| old canada.csv | 785 | 785 | 784 | 0 | 0 / 0 / 0 / 1 | 0 / 0 | 785 | 785 | 0 |
| old france akram.csv | 1,920 | 1,920 | 1,896 | 24 | 0 / 0 / 0 / 0 | 0 / 1,087 | 833 | 186 | 623 |
| old germany.csv | 1,955 | 1,955 | 1,953 | 0 | 1 / 0 / 0 / 1 | 0 / 1 | 1,954 | 1,952 | 2 |
| old spain.csv | 716 | 716 | 716 | 0 | 0 / 0 / 0 / 0 | 0 / 1 | 715 | 715 | 0 |
| old wejdi list.csv | 10,326 | 10,325 | 10,184 | 131 | 6 / 0 / 1 / 3 | 0 / 854 | 9,471 | 1,415 | 7,928 |
| old wissem list.csv | 8,685 | 8,685 | 8,670 | 0 | 5 / 1 / 0 / 9 | 0 / 1,647 | 7,038 | 7,037 | 1 |
| **Total** | **25,224** | 25,223 | 25,040 | 155 | 12 / 1 / 1 / 14 | 4 / 3,816 | 21,403 | 12,324 | 8,927 |

Files are processed new-first, then old; the first file to carry a person wins. Masked examples: new france.csv: j***@s***.fr, s***@t***.com, p***@p***.com; new germany.csv: m***@h***.com, l***@k***.pro, c***@p***.com; old canada.csv: k***@i***.ai, a***@m***.ca, s***@e***.com; old france akram.csv: m***@p***.fr, n***@p***.io, h***@q***.com; old germany.csv: l***@m***.info, d***@b***.com, p***@f***.com; old spain.csv: a***@k***.com, m***@v***.com, a***@t***.com; old wejdi list.csv: n***@d***.de, d***@b***.id, o***@h***.de; old wissem list.csv: j***@2***.art, d***@r***.eu, a***@w***.it.

## 2. Funnel

| Step | Rows |
|---|---:|
| Rows in 8 files | 25,224 |
| Mappable (company and name or email) | 25,223 |
| Valid and usable email (format ok, not role-based, not free-mail, not Apollo invalid / do-not-mail) | 25,040 |
| Unique after dedupe across files (email, LinkedIn URL, company + name) | 21,233 |
| Not already in your DB, not excluded | 8,927 |
| At a company that has an open job | 38 |
| Gives an open job its first contact | 46 jobs (31 companies) |

Duplicates removed: 3,816 across files (the same person in several lists) and 4 inside a file. 825 of those are the same person with a different email between the new files (first file's email kept; see Conflicts).

Rows lost before "valid": 1 unmappable (no company), 155 no email, 12 role-based (info@, contact@...), 1 free-mail, 1 invalid format, 14 Apollo `invalid`/`do_not_mail`.

## 3. Match against your current data

| Match type | Count |
|---|---:|
| Identical (same person, same email, same title and company) | 11,812 |
| Different title only | 14 |
| Newer company (same person, different company) | 24 |
| **Conflict: same person, different email** | 474 |

Matched by email 11,850, by company + name 474. LinkedIn URL matches are folded into those (existing contacts rarely store one).

Excluded: contacts you marked left 1 (of 1 in the DB), already emailed or drafted 3 (DB has 18 contacts with a draft/LinkedIn note and 15 sent-to addresses), Apollo `Do Not Call` 0 (flag is set on no row). Contacts you verified: 19 in the DB, 2 of them appear in the files. **The app has no do-not-contact list or setting** (searched code, docs and settings): nothing to exclude on that front, and nothing prevents re-importing someone who asked not to be contacted. See decisions.

`Last Contacted` is set on 4,531 rows (mostly the old, already-imported files); only 328 of the new contacts have it. That is Apollo's own sequence history, not yours.

## 4. Companies

- 18,918 distinct companies in the files: **10,536 already in your DB**, **8,382 new**.
- New contacts by company state: at an existing company 431, at a new company 8,496 (of which 47 sit at a flagged ambiguous company, see below).
- Local PDL file (no network) on the 8,382 new companies: 7,539 found by name; the CSV domain matches PDL for 6,264 and disagrees for 1,180 (informational: those are the ones to check before trusting a domain).
- Ambiguous (never auto-merged): 56 similar-name pairs ({'similar_name': 56}). No same-name-different-domain case and no domain/LinkedIn collision was found. Examples (company names, not people):

| CSV name | Your DB name | Similarity | Contacts |
|---|---|---:|---:|
| Catchr | catchHR | 0.92 | 2 |
| Synpulse | Synpulse8 | 0.94 | 2 |
| AdVaes | advades GmbH | 0.92 | 2 |
| Fairw.ai | FairAI | 0.92 | 3 |
| GlobalM | Global M | 0.93 | 1 |
| polyperception.io | PolyPerception | 0.93 | 2 |
| Les Filles et Les Garçons de la Tech | Les Filles & Les Garçons de la Tech | 0.96 | 2 |
| ekino | Ekinox | 0.91 | 1 |
| Alteis Groupe | Altersis Groupe | 0.93 | 1 |
| FruitfulAI AG | Fruitful AI | 0.95 | 6 |
| Datali | DATALIS | 0.92 | 1 |
| DataStore AG | DataStories® | 0.9 | 2 |
| Team-iT | Teamit | 0.92 | 1 |
| Avelon AG | Avelion Group | 0.92 | 1 |
| RoboMat | Roboat | 0.92 | 1 |
| INVIVOO | Invivo | 0.92 | 1 |
| modeso | Modeo | 0.91 | 1 |
| Streamlink | Streamline | 0.9 | 1 |
| BigFilter | BigFilter.ai | 0.9 | 2 |
| Connect-i | Connect AI | 0.95 | 1 |
| Fractal | fractl | 0.92 | 1 |
| Palm.ai | palma.ai | 0.92 | 1 |
| conveo GmbH | Convo | 0.91 | 2 |
| Microamp Solutions | Micro Solutions | 0.91 | 2 |
| WaltR | Walter | 0.91 | 1 |
| explAIn | explai | 0.92 | 1 |
| Gravitas AI | Gravia AI | 0.9 | 1 |
| Start Srl | STARTX | 0.91 | 1 |
| Infinity, Inc. | INFINIT | 0.93 | 1 |
| UNIVER | Univers | 0.92 | 1 |
| UNIVER | Univere | 0.92 | 1 |
| consultex IT GmbH | Consult IT | 0.91 | 1 |
| Inforca | Infora GmbH | 0.92 | 1 |
| Future Proof | Futureproof | 0.96 | 1 |
| flair | Flaire | 0.91 | 1 |
| Bloomo | Bloom Group | 0.91 | 1 |
| starke AG | Stark | 0.91 | 1 |
| Software Solutions | Software Solutions AI | 0.92 | 1 |
| Ensemble AI | Ensemble IP | 0.91 | 2 |
| SmartLab Solutions GmbH | SMART-Solutions | 0.91 | 1 |

## 5. What is useful

- Title quality of the 8,927 new contacts: 7,988 fine, 920 vague (only words like Manager, Director, Senior), 7 empty, 12 junk.
- Size (Apollo # Employees): 8,173 under 200, 136 at 200+, 618 unknown. Top countries: France 2,345, Germany 1,694, United States 1,228, Spain 1,089, Italy 832, United Kingdom 452, Ireland 214, Canada 145. About 15% are in the United States or Canada, outside your target regions.
- By role at companies with open jobs (38 contacts): Founder / CEO 19, CTO 10, HR / Talent 7, Tech Lead 1, (unranked) 1. Engineering manager: 0, VP/Head of Engineering: 0.

Open jobs that would get a first contact: **46**, all in stage New.

| Track | Jobs |
|---|---:|
| Data/AI | 31 |
| Backend | 14 |
| Mobile | 1 |

| Country | Jobs |
|---|---:|
| FR | 27 |
| DE | 15 |
| ES | 4 |

Today's open jobs (not closed, not duplicate, passing the location filters): 503 of 3,450 have a contact. The app's own Contacts report counts a wider set (4,648 applications: 637 with a contact, 3,955 to get, 56 none), so its numbers differ.

### Top 30 jobs by fit that gain a contact

The best new contact per job by your ranking and company size (size is unknown for most of these, so the large-company order applies: HR first).

| # | Job | Company | Fit | Contact title | Why it ranks |
|---:|---|---|---:|---|---|
| 1 | #2267 Développeur PYTHON Confirmé H/F (FR, Backend) | Itrust | 87 | Founding Partner / CEO / CISO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 2 | #3140 JINTO - AI Engineer / Ingénieur IA (FR, Data/AI) | Kiiro | 80 | Chief Technology Officer - Associate | CTO; large/unknown-size company (size unknown) -> position 3 |
| 3 | #3052 Data Engineer F/H (FR, Data/AI) | PLURASKILLS | 78 | Chargée des Ressources Humaines | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 4 | #976 Backend Software Engineer (ES, Backend) | Alea | 78 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 5 | #454 Analytics Engineer (H/F) (IT) (FR, Data/AI) | Cherry Pick | 76 | Chief Freelance Officer | unranked title; not in the ranking order |
| 6 | #5011 Senior Backend Engineer, Platform (DE, Backend) | Apaleo | 74 | Founder & CTO | CTO; large/unknown-size company (size unknown) -> position 3 |
| 7 | #330 Data Engineer Sénior / Architecte Data Junior F/H @Conseil (FR, Data/AI) | Externatic | 74 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 8 | #3513 Data Platform Engineer – Financial Systems (m/w/d) - J24769 (DE, Data/AI) | Exclusive Associates | 74 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 9 | #2020 AI-Native Software Engineer - CDI Paris - Theodo (FR, Data/AI) | Theodo | 73 | Talent Acquisition & Employer Branding | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 10 | #4558 AI Engineer Google Cloud (FR, Data/AI) | Pyl.tech | 72 | CTO & Fondateur | CTO; large/unknown-size company (size unknown) -> position 3 |
| 11 | #4660 Ingénieur Data Senior (H/F) (FR, Data/AI) | Externatic | 72 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 12 | #4021 Machine Learning Engineer / Data Scientist (F/H) (FR, Data/AI) | Scorp-io | 72 | Co-fondateur & CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 13 | #1697 Backend Developer C# (m/w/d) - J1655 (DE, Backend) | Exclusive Associates | 72 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 14 | #2021 Software Engineer Fullstack AI-Modernisation - CDI Paris - Theodo (FR, Data/AI) | Theodo | 70 | Talent Acquisition & Employer Branding | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 15 | #2178 Ingénieur·e des données de spectrométrie de masse (H/F) (FR, Data/AI) | CEA | 70 | Ressources humaines | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 16 | #366 AI Engineer Synthèse de Données F/H (FR, Data/AI) | Soors | 69 | Chargée de Ressources Humaines | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 17 | #3143 AI Engineer F/H (FR, Data/AI) | BREAKERS CONSULTING | 68 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 18 | #684 Data Platform Engineer (Analytics Systems) (m/w/d) - J24769 (DE, Data/AI) | Exclusive Associates | 68 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 19 | #3503 SAP Data Platform Engineer (m/w/d) - J38664 (DE, Data/AI) | Exclusive Associates | 68 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 20 | #3747 C# Backend Engineer (m/w/d) - J12536 (DE, Backend) | Exclusive Associates | 68 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 21 | #3779 Backend Engineer C# (m/w/d) - J32912 (DE, Backend) | Exclusive Associates | 68 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 22 | #1717 Backend Developer SAP & Financial Systems (m/w/d) - J36809 (DE, Backend) | Exclusive Associates | 66 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 23 | #2176 Ingénieur IA (FR, Data/AI) | Kiiro | 65 | Chief Technology Officer - Associate | CTO; large/unknown-size company (size unknown) -> position 3 |
| 24 | #4541 Business Data Analyst / Analytics Engineer – PySpark / Databricks F/H (CDI) (FR, Data/AI) | FELPS GROUP | 65 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 25 | #3526 Data Platform Engineer (m/w/d) - J2003 (DE, Data/AI) | Exclusive Associates | 64 | CEO | Founder / CEO; large/unknown-size company (size unknown) -> position 7 |
| 26 | #2004 LLM Powered Software Engineer - CDI Paris - Theodo (FR, Data/AI) | Theodo | 60 | Talent Acquisition & Employer Branding | HR / Talent; large/unknown-size company (size unknown) -> position 1 |
| 27 | #2173 Data Engineer / Ingénieur.e - Confirmé.e (FR, Data/AI) | Kiiro | 60 | Chief Technology Officer - Associate | CTO; large/unknown-size company (size unknown) -> position 3 |
| 28 | #1977 Senior Data Engineer (FR, Data/AI) | GitGuardian | 60 | Chief Technology Officer | CTO; large/unknown-size company (size unknown) -> position 3 |
| 29 | #2074 Senior Software Engineer (backend, Django) - NHI team (FR, Backend) | GitGuardian | 60 | Chief Technology Officer | CTO; large/unknown-size company (size unknown) -> position 3 |
| 30 | #2075 Senior Software Engineer (Backend) (FR, Backend) | GitGuardian | 60 | Chief Technology Officer | CTO; large/unknown-size company (size unknown) -> position 3 |

## 6. Conflicts to decide

1. **Same person, different email: 474 vs your DB, plus 825 between the new files.** Mostly the old Wissem (293), Germany (75), Wejdi (58), Canada (29) files. Apollo may have refreshed the address, or you may hold a guess. Default: keep your email, store the file's as an alternate for review, never overwrite a verified or hand-edited contact.
2. **Newer company: 24** (the person changed employer). Default: keep the contact where it is and record the new company as an alternate.
3. **Different title: 14.** Default: fill only when your title is empty, otherwise ignore.
4. **Role-based and free-mail addresses** (13 rows): Default: skip the email, keep nothing without a personal address.
5. **People with no usable email** (152 new): Default: do not import now (nothing to send to; they would fill Get contact with dead entries). Decide if you want them as name-only contacts.
6. **Do-not-contact:** none exists. Default: add a simple check against contacts you marked left and anyone already emailed (done here); consider a real list before the import.
7. **Apollo `Potentially Invalid` (1,184 rows overall) and `Catch-all` (63):** Default: import as unverified with the Apollo status kept in the note, since the waterfall treats catch-all as unusable.

## 7. Risks

- The importer's name+company dedupe will merge people at companies whose normalized names collide (e.g. "Catchr" vs "catchHR"). The 56 near-names are listed above and are held out of the open-job counts only if they are new companies; none are auto-merged.
- `Company.domain` from the CSV would be written onto new companies without a check. 1,180 new companies disagree with PDL on domain.
- 8,496 of the new contacts belong to companies you have no job for. Importing them adds ~8,400 company rows and inflates company and contact counts; do you want them at all now?
- The importer stamps every contact `source=apollo_dump` with only `imported_batch`. It has no source file, import date or alternate-email storage; the requested "From <file>, imported <date>" line and alternates need a migration (new columns plus a `contact_alternate` table).
- `already_imported` compares file hashes. The old files differ from the ones imported before (names and hashes changed), so re-running them is not blocked; fill-only logic is what protects you.
- Apollo `Last Contacted` (4,531 rows) means someone emailed these people from Apollo; treat as a soft warning, not an exclusion.
- Email deliverability is unknown for nearly all rows. Nothing may be drafted before you verify the contact in Get contact (existing rule).

## 8. Recommended import plan (defaults, say which to change)

1. Migration first: add `source_file`, `imported_at`, `email_status` to `contact`, and a `contact_alternate` table (email, title, company, file, date, status). Run it on a copy.
2. Import only the 8,927 new valid contacts (not the 152 with no usable email, not role/free-mail/Apollo-invalid, not left/emailed). Option B (recommended if you want a lean DB): import only the 38 at open-job companies now and keep the rest in the CSVs.
3. Existing contacts: fill-only (title, LinkedIn URL when empty). Email conflicts and newer-company cases go to `contact_alternate`; verified or edited contacts and contacts marked left are never touched.
4. Every contact: note "From <file>, imported <date>", emails marked unverified (`verification_status` empty, `verified_at` empty), never `verified`.
5. New companies: created with name and CSV domain (flagged unconfirmed); the 56 similar names are created separately and listed for your review.
6. Batches of 500 with progress (`contact_import` row per file). Back up first, dry run on a copy and show counts, then the real DB after your go.
7. Matching for OPEN jobs only (`contacts.resolve_many` on open applications), report jobs with a contact before and after by track and country. No rescoring, no generation, no provider calls.
8. Expected result: contacts +8,927 (13,249 → ~22,176); open jobs with a contact +46 (503 → ~549 of 3,450 in the open-job set), none past New.

Open question for you: given the low payoff for today's jobs, import all 8,927 or only the 38 at open-job companies? Also whether to add a do-not-contact list first.
