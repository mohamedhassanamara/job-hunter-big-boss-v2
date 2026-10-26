# Workflow time audit: Shortlist to Applied / Sent (2026-10-26)

Read-only analysis. Data comes from a SQLite online backup of `data/jobhunter.db` (taken 2026-10-26, the real DB was never written to). Screen latency was measured on a second copy with the FastAPI test client (no lifespan, so no workers, scheduler or queue; no network; model keys blanked). No Gemini/APInex calls, no discovery, no queue run. The click map comes from reading the code (frontend `router.tsx` and the screens, backend gates).

## 0. What the data can and cannot say

- 56 jobs were ever shortlisted; **32 went past Shortlisted** (CV approved or later); 20 have an Applied event (by method: company site 14, email 4, LinkedIn 3; 14 emails went through the queue).
- The data has **two real working days**, and they are not alike:
  - **2026-10-21**: mostly developing the email tool (job 4951 alone has 11 drafts). Not representative.
  - **2026-10-22 11:43 to 14:11**: the one clean batch (13 jobs shortlisted in 4 minutes). **All "batch" numbers below use this day**; "ALL" numbers are shown only where useful and are skewed by old jobs (a job shortlisted 09-28 and approved 10-22 gives a 24-day "gap").
  - 10-25 15:16 to 15:30: 17 more shortlisted; their CVs are drafted (system finished in about 1 min each) and are **waiting for you** (human wait, not yet closed). 10-24 contains a bulk close of 780 jobs, which I excluded from "actions".
- With so few jobs, medians are indicative, p90 is mostly one or two outliers.
- Event timestamps are the moment of the click that wrote the event. "Mark applied" is logged when you click it in the app, so company-site time and CV-review time cannot be separated from each other; `applied_at` is a date (12:00:00), not a time.

## 1. The flow as a dependency chain

```
Shortlist (human, 1 key)
  └─ auto CV draft (system, generation.auto_cv ON)  ──► CV Studio: review + Approve (human, no hotkey)
                                                          │
        ┌─────────────────────────────────────────────────┤
        │ ROUTE: web apply                               │ ROUTE: cold email / follow-up                       ROUTE: LinkedIn
        │ needs: approved CV                             │ needs: approved CV + verified contact (get_contact   needs: nothing hard (CV not required)
        │ Applications > Ready: `o` opens listing + CV   │   .require_ready) + posting + no live draft
        │ (new browser tab, apply by hand)               │ Draft (auto only if generation.auto_email, OFF)
        │ `a` Mark applied (dialog, confirm click)       │ → code checks → Approve (runs Claude verifier, ~24 s)
        │ = stage done                                   │ → Add to queue → Start sending (queue idle when empty)
        │                                                │ → 4–7 min random gap per email → send_gate → sent = done
```

Gates actually enforced in code (file:line from the click-map pass): approved CV (`services/outreach.py:346,429,871`), verified contact within `contacts.verify_days` (`services/get_contact.py:75-90`), contact has email, one draft at a time (lock), error-level checks block approval (`api/outreach.py:284`), `contact_alert` blocks, claim verifier (`api/outreach.py:297`), test send before the queue can start (`send_queue.py:153`), send gate re-checks hashes (`verifier.send_gate`). Web apply needs only the approved CV (`tracking.py:80-87`).

**Observed critical path:** the contact was never the last gate. On 10-22 the waterfall found and verified contacts for six jobs in 11:51 to 11:57 (found to verified about 10 s each); the email draft then waited 15 to 85 minutes for the **CV approval**, which is what actually triggers drafting (auto_email off, so you also clicked "Draft").

## 2. Click map (from the code)

Counting: a click is a click or keystroke; screen switch = react-router route change (tabs, `?job=` panels and dialogs are not switches).

### Shared prefix (Shortlist and CV)

| Step | Screen | Action | Who | Clicks |
|---|---|---|---|---|
| a | `/discover?job=` | Shortlist (`S`), auto-advances to next row | Human | 1 |
| b | system | `on_shortlisted` queues the CV draft (auto_cv) | System | 0 |
| c | `/jobs/:id/cv` (from Job header, Today card or sidebar) | Open the draft | Human | 1–2, 1 switch |
| d | CV Studio | Review PDF, Approve (no hotkey; disabled until one page and zero errors) | Human | 1 |
| e | system | stage becomes cv_ready; email queued only if auto_email; fit before/after job | System | 0 |

### Route 1: web apply

| Step | Screen | Action | Who | Clicks / tabs |
|---|---|---|---|---|
| 1 | `/applications?tab=ready` (`g a`) | go to Ready | Human | 1–2, 1 switch |
| 2 | Ready tab | `j/k` select | Human | 0–1 |
| 3 | Ready tab | `o`: opens listing in a **new tab** and downloads the CV (and letter) | Human | 1, +1 browser tab |
| 4 | company site | fill form, upload downloaded PDF, paste text | Human | not counted |
| 5–6 | back in app | `a`, then click Confirm in the dialog (no Enter-to-submit) | Human | 2 |

Minimum from Shortlist: about 7–8 clicks. Route changes: best 3 (Discover, CV Studio, Applications), typical 4–5. Per job inside a batch, Applications is a hub, so only the CV Studio visit is a per-job route change. Always 1 external tab.

### Route 2: cold email / follow-up

| Step | Screen | Action | Who | Clicks |
|---|---|---|---|---|
| A | `/outreach?tab=contacts` or Job page | get contact: waterfall "Find contact" (paid, one click) then verify (`V`); auto-advances | Human + system | 1–3 (more if manual) |
| B | Job page | "Draft email with AI" (needed because auto_email is OFF); wait ~22 s | Human, then system | 1 + 1 switch |
| C | `/outreach` Review | read, edit | Human | 1 switch |
| D | editor | "Send test to me": once ever | Human | 1 once |
| E | editor | Approve (`A`): runs the Claude verifier inside the click | Human; system inside click | 1 |
| F | toast or editor | "Add to queue" (short-lived toast; no hotkey, no "add all") | Human | 1 per email |
| G | `/outreach?tab=queue` | "Start sending" (queue goes idle every time it empties) | Human | 1 per batch |
| H | system | one email every 4–7 min (random), max 20 pending | System | 0 |

Minimum per email with contact imported, auto_email on, editor open: 3 clicks (`V`, `A`, Add to queue) + 1 per batch. Typical today (auto_email off): about 6–8 clicks and 5–6 route changes (Discover, Job, CV Studio, Job, Outreach Review, Queue).

### Route 3: LinkedIn

Entire flow stays on the Job page (`#linkedin`): Search on LinkedIn (new tab), Add person (about 3 clicks, paste the header), Draft note (1), **Check claims (1, manual, Copy and "I sent" stay disabled until done)**, Copy (1), send in LinkedIn tab, "I sent the request" (1). About 4–7 clicks per person, 2–3 route changes, 1–2 external tabs.

### Screen switches per job per route (best existing path / typical)

| Route | Best | Typical | External tabs |
|---|---|---|---|
| Web apply | 3 (1 per job once Applications is the hub) | 4–5 | 1 |
| Email | 4–5 (3 tab changes inside Outreach) | 6–7 | 0 (contact imported) to 1+ |
| LinkedIn | 2 | 3 | 1–2 |

## 3. Time per stage, system vs human

Batch = 2026-10-22 (13 jobs past Shortlisted; email n=9). All in minutes unless noted. "S" = system, "H" = human wait/work.

| Stage gap | n | median | p90 | Type | Notes |
|---|---|---|---|---|---|
| Shortlist to CV draft created | 13 | 0.7 | 1.5 | S | queue wait median 4 s, run median 10 s (`generation_task`, n=42) |
| CV draft created to CV approved | 13 | 49.9 | 87.7 | **H** | drafts sat while you worked job by job; includes regenerations |
| Shortlist to CV approved | 13 | 51.2 | 87.9 | H | |
| CV approved to email draft created | 9 | 2.2 | 2.4 | H trigger + S | you click Draft (auto_email off); gen median 22 s |
| Email draft created to approved | 9 | 3.0 | 13.2 | H + S | verifier median 24 s inside the Approve click |
| Email approved to queued | 9 | 0.0 | 1.9 | H | |
| Queued to sent | 9 | 42.0 | 77.3 | **S (queue)** | 4–7 min gaps, plus a 78 min idle stall (see section 6) |
| CV approved to applied (web/LinkedIn) | 4 | 6.5 | 13.2 | H (+ external site) | includes time on the company site |
| Shortlist to applied/sent, end to end | 12 | 51.0 | 99.0 | mixed | |

All-time numbers (n=32 past Shortlisted; skewed by old jobs): shortlist to CV approved median 65.6, p90 10,279 (stale shortlists left for days, one 24 days).

### System durations that are stored

| Thing | n | median | p90 | max |
|---|---|---|---|---|
| CV generation, all models (`cv_version.duration_ms`) | 85 | 19.2 s | 126.5 s | 143.8 s |
| – gemini-3.5-flash-lite | 52 | 10.7 s | 45.4 s | 105 s |
| – claude-sonnet-5 (Generate with Claude, 10-21 and earlier) | 31 | 104.9 s | 133.5 s | 143.8 s |
| – APInex minimax | 2 | 14.7 s | 15.0 s | 15.0 s |
| Background CV task wait in queue / run (`generation_task`) | 42 | 4.3 s / 10.2 s | 53.9 s / 42.7 s | 73.5 s / 105.5 s |
| Email draft generation (`outreach_draft.duration_ms`) | 46 | 22.4 s | 61.4 s | 222.7 s |
| Claude verifier, latest result per draft (`verification.duration_ms`) | 22 | 24.3 s | 30.0 s | 36.2 s |

### Where timing is NOT stored

- Time on each screen, clicks, spinner/wait time (nothing is logged, hence Part B).
- Contact step: `contact.found_at` / `verified_at` exist but are on the contact (shared between jobs, latest only); the waterfall runs are in `company_provider_run`, not tied to your clicks. For the 10-22 batch found to verified was about 10 s each.
- Verifier duration only for the **latest** verification of each draft; earlier attempts are overwritten.
- Failures: `generation_task.error`, `cv_version.error` and `outreach_draft.error` are **all empty**; HTTP 429/503/402 for CV/email are not persisted (only the current `apinex_status`). So "generation failed" cannot be counted from the DB.
- Queue state changes (paused / resumed / idle) are not logged; inferred below from item timestamps.
- Why a CV or draft was regenerated, and what was edited (only an `edited` flag).
- Time spent on the external company site or LinkedIn.

## 4. Friction counts

| Item | Count | Cost |
|---|---|---|
| Jobs with more than one CV version | 17 of 56 (32 extra versions) | each regen = 11 s (Gemini) to 105 s (Claude) of generation plus a re-review |
| CV versions carrying checker violations/warnings | 73 of 88 (most common: opening repeats another CV, 47; "software engineer" then "3 years of software engineering" repetition, 30; words your pool never says, about 15) | these feed the summary retry and regenerations |
| CV versions with overrides (edits in Studio) | 37 of 88 | human edit time not stored |
| Email drafts | 46 total: 14 sent, 2 approved, 30 "rejected" (superseded by a regeneration) | mostly 10-21 tool development; on 10-22 batch 4 rejected drafts across 14 |
| Drafts with code-check violations | 35 of 46 | |
| Claude verifier results | 14 passed, 8 failed, 24 not run | failed cost a regenerate or edit |
| Approved with the "Approve without verification" button | 6 of the 14 sent drafts (ids 27, 34, 35, 39, 41, 45; 4 never verified, 1 stale, 1 failed; each ignored 2 to 6 warnings) | the field defaults to `{}`, which is not a bypass; counting `IS NOT NULL` (as an earlier version of this report did) overstates it. Corrected 2026-10-26 |
| Edited before approval/send | 8 of the 16 approved/sent drafts (7 sent, 1 approved); 5 rejected ones were edited too | edit time not stored |
| Drafts per job | 1 draft: 6 jobs; 2: 5; 3: 1; 4: 2; 8: 1; 11: 1 | |
| Failed generations (429/503/402) | not stored | see section 3 |

## 5. Batches and sessions

Sessions split on a gap over 90 minutes; actions are the human events (stage changes, approvals, draft creation, applied, queue add, test send, LinkedIn link open).

| Session | Length | Actions | Idle gaps over 5 min | Sequencing |
|---|---|---|---|---|
| 10-21 13:41 to 16:32 | 171 min | 59 | 8, totalling 124 min | job by job (27 of 30 consecutive downstream actions on the same job); email tool development |
| 10-22 09:29 to 14:11 | 282 min | 199 | 13, totalling 147 min | shortlist stage-wise (13 in 4 min, 11:43 to 11:47), then job by job (41 of 67) |
| 10-23 22:25 to 22:47 | 22 min | 20 | 1 (8 min) | job by job (9 of 10) |
| 10-24 19:09 to 20:28 | 79 min | 786 (780 bulk closes) | 4 | 2 jobs |
| 10-25 14:17 to 15:30 | 73 min | 91 | 1 (59 min) | 17 shortlisted stage-wise; nothing downstream yet |

Reading the 10-22 batch: after shortlisting 13 jobs in 4 minutes, you went through them one at a time: approve CV, click Draft, approve email, add to queue (or open listing and mark applied), then the next job. Longest gaps (21 min, 26 min, 16 min) sit around company-site applications and queue/Resume. An idle gap in this log cannot distinguish "reading a draft", "on the company site" or "away", so it is an upper bound on waiting.

## 6. Queue

- 14 emails sent through the queue (plus 4 test sends): 12 on 10-22, 1 on 10-21, 1 on 10-23.
- **Gaps between sends while running: 4.6 to 7.1 min, median 5.5 min** (by design: random 4 to 7).
- Approved-to-sent: median 42 min on 10-22. That is **not** only the gap:
  - Items added 12:13 to 13:31 all waited for the same restart at **13:32**. The queue had emptied after the 11:40 send; `tick` sets it to `idle` when empty, and adding an item does not restart it, you have to press **Start sending** again. The first of these items waited **78.5 min**.
  - After the restart, 8 emails went out in 38 minutes (13:32 to 14:10).
  - Items 3 and 4 were queued 10-21 16:24 and 16:32 and sent 10-22 10:48 and 10:55 (about 18 h); a test send was needed first.
- The queue ran empty (idle) at least twice (after 11:40 and the last send of each day); pause/resume events are not logged, so this is inferred.
- Sends per day: 10-21: 1, 10-22: 12, 10-23: 1.
- Settings tour text says "one email every 15 minutes" while the code default is 4 to 7 minutes (stale text).

## 7. Screen latency (test client, copy of the real DB, ms)

Only endpoints over 500 ms are flagged; everything on the CV Studio, Job page, Outreach and Applications Ready paths is under 150 ms.

| Screen | Endpoint | Warm median | Worst | Note |
|---|---|---|---|---|
| Pipeline | `GET /applications` | 1,291 | 1,582 | returns **all 5,550 applications as 4.7 MB** JSON (no paging, includes new/closed) |
| Discover | `GET /jobs?limit=50` | 1,072 | 1,542 | 4.5 MB, `limit` is not honored here |
| Every screen (shell) | `GET /today` | 1,036 | 1,186 | |
| Every screen (shell) | `GET /scoring/status` | 848 | 923 | polled every 20 s (2 s while running), also in background tabs; counts over 10.5k fit_scores |
| Applications / Stats | `GET /stats` | 416 | 538 | |
| Contacts | `GET /companies?limit=50` | 353 | 483 | under 500 |
| Contacts | `GET /company-merges` | 409 | 451 | under 500 |
| Job page | `GET /jobs/{id}` | 30 | 147 | job 4951 |
| CV Studio | `GET /applications/{id}/cv` | 10 | 21 | |
| Outreach | drafts/queue/send-log | 6 to 31 | 36 | |

Not measured: the browser side (parsing 4.7 MB, rendering the board/table); real model calls. Latency is a minor cost compared with the minutes below (about 1 to 3 s per Pipeline/Discover load), but the `/scoring/status` poll every 20 s on every screen costs about 4 s of server time per minute.

## 8. Top 5 time sinks, per batch of 10 jobs

Estimated from the 10-22 batch (13 jobs, scaled to 10). The time attributed to an action is the gap before it in the human action log, so these are rough (plus or minus 30%) and overlap a little. "Elapsed" means calendar time, "human" means your time.

| Rank | Sink | Est. minutes per 10 jobs | Kind |
|---|---|---|---|
| 1 | Company-site applications (time before each "Mark applied": open listing, form, upload) at about 3.6 min each | about 36 human (for the 8 to 9 web-apply jobs, scale accordingly) | human, external tab |
| 2 | Queue: 4 to 7 min gaps and the idle stall: flushing 10 emails takes about 55 min elapsed; the stall added 78 min on 10-22 | about 55 elapsed (+ the stall); human cost is the return trip and the Start click, about 2 | system / elapsed |
| 3 | CV review and approve (about 2.0 min each) plus regenerations (17 of 56 jobs had extras; 32 extra versions) | about 20 to 30 human | human |
| 4 | Email: manual Draft click and route change, draft read/edit, verifier wait (about 24 s), approve, add to queue (1.5 + 1.0 + 0.7 min per job from the log; median draft to approved 3.0 min) | about 25 to 30 human per 10 emails | human + system inside clicks |
| 5 | Idle/blocked gaps over 5 min (13 gaps, 147 min on 10-22, partly overlapping #1) and per-job navigation | about 20 to 30 (not additive) | mixed |

Not on the list: Shortlist (0.3 min per job: about 3 min per batch), contacts (waterfall one click, about 10 s each in this batch), CV generation (system, about 10 s with Gemini; 105 s with Claude), screen latency.

## 9. Features that exist but are hard to find

1. `generation.auto_email` (Settings, "Automatic drafting"): the only way to remove the manual Draft click and its screen switch. Off by default and not mentioned in any flow screen.
2. "Add to queue" has no hotkey, and the toast after Approve is short; if missed you must open the Approved tab. No "add all". Today's "Cold emails" card also has it.
3. Applications Ready keys (`j/k`, `o` open listing+CV, `a` mark applied) are on that tab's help line only; the `?` dialog lacks `G A`, `G N`, `G I`, `G M`, `G L`.
4. Discover labels `1/2/3` are only in the tour.
5. "I sent it myself" (record an email you sent from Gmail) is a small ghost button at the queue step.
6. Pipeline drag-to-Ready starts the email draft (`?draft=1`): only described in SPEC.
7. The Start sending button is disabled until a test send exists; the pointer to "Send test to me" is a tooltip.
8. LinkedIn "Check claims" is a manual step; Copy and "I sent the request" are disabled until done, explained only by a tooltip.
9. Contacts-to-get panel keys `E`, `N`, `X` are not in its footer.
10. No hotkey at all for CV Studio Approve, Job page actions, Queue start, Mark-applied confirm.

## 10. Hypotheses vs the data

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Serial gates per job | **Supported** | Downstream actions in a session hit the same job 41 of 67 times (10-22), 27 of 30 (10-21), 9 of 10 (10-23). Email drafting waits for the last of CV approval/contact; here the CV approval was always last (contacts were ready 15 to 85 min before). System gates are fast (CV draft about 1 min after shortlist); the serial part is your approvals. |
| Waiting inside steps | **Partly supported** | Verifier about 24 s inside every Approve click, email generation 22 s median (p90 61 s), Claude CV regen 105 s, queue 4 to 7 min per email and an idle stall of 78 min. In total about 1 to 2 min per email job inside clicks, much smaller than the queue wait, which is elapsed rather than active time. Spinner time itself is not measured. |
| Per-job instead of per-stage work | **Supported** | Shortlisting is stage-wise (13 jobs in 4 min) and the contact waterfall was done stage-wise (6 jobs in 6 min), but CV approve, draft, approve and queue were done job by job. There is no multi-select, "approve and next" (CV Studio/Job page), "approve all" or "add all" anywhere. Only Discover, Outreach Review and Contacts auto-advance. |
| Switching between routes | **Weakly supported / not provable** | Click map: email typical path is 5 to 6 route changes, best 3 to 4; web apply 1 per job from Applications. But the log shows 1 to 3 min per action, and there is no per-screen timing, so the cost of switching is not measurable until Part B has data. |

## 11. Candidate improvements (options only, nothing implemented)

Estimated saving per 10-job batch of human minutes unless marked elapsed; rough.

| Option | Est. saving | Notes |
|---|---|---|
| Restart the queue automatically when an approved email is added (or "Add to queue" starts it once a test send exists) | about 2 human, up to about 78 elapsed in a bad batch | fixes the idle stall; keep the 4–7 min gap and the test-send rule |
| Turn on `generation.auto_email` (setting only) | 5 to 10 | removes the Draft click and route change, drafts appear while you review CVs |
| "Approve and next" plus a hotkey in CV Studio, with the next shortlisted CV opening | 5 to 10 | CV approval is the critical path and has no hotkey |
| "Add to queue" on Approve (setting) or a hotkey, and "Add all approved" | 5 to 7 | |
| Batch-oriented review page: CVs in a list with `j/k`, approve with a key, same as Outreach Review | 10 to 15 | combines the two items above for the biggest sink under your control |
| Reduce CV regenerations: auto-fix or downgrade the "opens like another CV" and "software engineer / 3 years" checks (47 and 30 hits) | 6 to 10 | needs a decision on the writing rules, not just code |
| Applications Ready: one key to copy cover letter/answers, Enter-to-confirm Mark applied, keep the listing tab ready | 3 to 8 | the external form time itself cannot be cut |
| LinkedIn: auto-run Check claims after Draft | about 1 per person | |
| Pagination or a server-side cap on `GET /applications` and `/jobs`, cache `/scoring/status` and `/today` counts | seconds per page load, about 4 s/min server time | not a time sink for you, but easy |
| Fix the queue tour text ("15 minutes" vs 4 to 7) and add Applications, LinkedIn, Interview, Motivation, Letters keys to the `?` dialog | discoverability | |

Mixed: the stage-wise helpers (batch approve, batch queue) conflict with the "I review everything before anything is sent" rule only if they skip the review; keeping approve a deliberate per-item key press with auto-advance keeps that rule.
