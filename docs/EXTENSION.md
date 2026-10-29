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
- **A job** (its own page, or selected in the search results): press **Save job** (pill, bottom right) or
  `Alt+Shift+S`. It is saved and scored right away. If the page did not give a required field (title, company,
  description) nothing is saved and the panel asks for it. The panel lists warnings (collapsed listing "… more",
  no country, outside your target countries) and links to the job in the app.
- **A person**: press **Save person**. The panel shows who they are, their **role** (recruiter, team lead or
  peer, from their title, with the reason; click a chip to change it), an **alum** checkbox (your school, from
  your Experience pool), the company, and the job they will join (the best open job at that company). No job
  there: they are kept as a contact and join the next job you save at that company. A do-not-contact flag is
  shown, never overridden.
- If the page cannot be read, **Paste profile text instead** takes a copied profile header. **Details** shows what
  was read (anchor checks) and copies a redacted report or page structure.
- In the app: LinkedIn → **People captured** (role, alum, jobs; **Delete** removes the captured fields and keeps
  the contact).

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
