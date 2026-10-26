# Batch workflow: 5-job demo, before and after (2026-10-26)

What was run: the real app (API + web) on a **scratch copy** of the real database (never the real file), with
`JOB_SOURCES=mock` (mock email drafter and mock claim verifier, no Gemini, APInex or Claude call), no send worker,
no scheduler, no keys, the usage log on. Five shortlisted jobs that already had **real stored CV drafts**
(Bloomwell, Kraaft, Capgemini and two Air Apps jobs) and a contact each; the other 13 shortlisted jobs were moved
back to New on the copy so the batch was exactly 5. The contacts were marked verified on the copy (the `V` step
per job is unchanged and not measured). Nothing was sent: the queue only started; its worker was off and
`send_log` has no new real send. The copy had `generation.auto_email` stored as **false** (your real value); it was
switched on in the copy to demo the new default, so **your real DB still has it off until you turn it on**
(Settings → Models → Automatic drafting).

Keystrokes were pressed through the browser extension: `g r`, `A` x5 (Review CVs) → `g o`, `A` x5 (Outreach
review) → `g a`, `j`, then `a` + `Enter` x5 (Applications, Ready).

## Result

| Per job | Before (typical path, from the audit's click map) | After (this demo) |
|---|---|---|
| CV approval | open the job's CV Studio (1 route change, 1–2 clicks), Approve click: 2–3 clicks | `A` on the list: **1 key**, no route change, next CV selected |
| Email | "Draft email" on the Job page (route change, wait about 22 s), open Outreach Review (route change), Approve (about 24 s verifier inside the click), "Add to queue" toast click: about 5 clicks, 2 route changes | drafted and verified in the background (all 5 showed "Verified" before opening), `A` approves **and queues**: **1 key**, no route change |
| Apply | `O` open listing (new tab), `A`, click the dialog's Mark applied: 3 | `A`, `Enter`: **2 keys** (the next job is selected; its listing opens with its CV when the setting is on, not exercised here, see below) |
| Total | about 10–11 clicks and 3 route changes | **4 keys**, and 3 route changes for the whole batch (Review CVs, Outreach, Applications), about 0.6 per job |
| Once per batch | "Start sending" every time the queue had emptied | none: the queue started itself on the first queued email (`queue_event`: idle → running, `auto_on_add`) |

Usage log of the run (`make usage-report`): `approve_cv` x5, `approve_email` x5, `queue_add` x5, `mark_applied` x5,
3 route changes, 0 s waiting on slow requests (no request over 500 ms).

## Limits of this demo

- One batch of 5, on a copy, with mock models: it shows clicks and screen switches, not how long a real draft or
  verification takes (those are in the audit: draft 22 s median, verifier 24 s median; now both happen before you
  look at the draft).
- "Open the next listing after Mark applied" was **switched off** on the copy: it downloads the CV (and letter)
  files and opens the company page in a new tab, which I did not do without your say-so. Enter-to-confirm and the
  automatic selection of the next job were verified; the new tab opens inside the confirm key press (a browser only
  allows that from a gesture), but test it once yourself.
- The PDF pane is blank in the automated browser in CV Studio and Review CVs alike (the same in the old page), so
  the PDF was not looked at here.
- Contacts (`V`), shortlisting (`S`) and the time on company sites are outside these numbers.
- The stored CVs still show the old "software engineer … 3 years of software engineering experience" warning: the
  code fix applies when a CV or its summary is generated again.
