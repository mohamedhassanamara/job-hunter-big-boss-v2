# The LinkedIn capture extension

A Manifest V3 extension (Chrome or Edge) that saves the **one job or profile you are viewing** to your own
Job Hunter app. It never visits LinkedIn by itself, and the app never requests linkedin.com.

## Install and pair
1. `make extension`, then `chrome://extensions` → Developer mode → Load unpacked → `extension/dist`.
2. Run the app (`make dev`). Settings → LinkedIn → Browser extension → **Create token** (shown once).
3. Extension options (extension card → Details): paste the token → **Test connection**.
   The app address defaults to `http://localhost:8000` (backend) and `http://localhost:5173` (web).
   Only `http://localhost` / `http://127.0.0.1` are accepted.

## Use
Open a job or profile. The button shows what the page is: **Save job** or **Save profile** (elsewhere it is dimmed). One click (or `Alt+Shift+S`) saves; there is no review screen.
- **Job** (its own page, or selected in the search results): saved and scored at once. The card shows what was saved and where each field came from, and flags anything that looks misread. If the page did not give a required field (title, company, description) nothing is saved and the panel asks for just that.
- **Profile**: saved with their role (recruiter, team lead or peer, from their title; click a chip to change it right there), an alum flag (your school, from your Experience pool) and the best open job at their company. No job there: they wait and join the next job you save at that company. A do-not-contact flag is shown, never overridden. If the company cannot be read, the panel asks for it.
- **Undo** appears when this click created the item (within 15 minutes, before you worked on it): a job is dismissed, a person removed.
- If a page cannot be read, **Paste profile text instead** works. **Details** shows what was read and copies a redacted report.
- In the app, **LinkedIn → LinkedIn Jobs / LinkedIn Profiles** list what you saved, flagged items first ("Needs review", with the reasons; "Looks right" clears it). New jobs wait there instead of Discover, and captured people are not in the company contact list, until you act (the "Include LinkedIn" switch in Discover and the "show them" link in Contacts bring them back).

## What it reads, and what leaves the page
- Reads only on your click or the shortcut; no timers, observers, clicks, scrolling or requests to LinkedIn.
- Sends only: the job's title, company, location lines, description and hiring-team poster; for a person, the
  top card, About, Experience and Education text (never the feed, interests or other people). It goes to your
  app on this computer. The server parses it and stores the parsed fields; **raw lines are never stored**.
- Permissions: `storage` and `https://www.linkedin.com/*`. The token lives in `chrome.storage.local`, is read
  only by the background worker and the options page, never by the page script.
- If LinkedIn changes its layout, the panel's Details row shows which anchors failed; the paste box always works.

## Developing
`backend/tests/test_extension_guard.py` (what the sources may not do), `test_ext_api.py`, `test_ext_people.py`,
`test_linkedin_page.py` (parsers on recorded text), `test_migration_0038.py`.
