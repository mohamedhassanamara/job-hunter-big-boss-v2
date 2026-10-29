# Job Hunter capture extension (Phase 2a skeleton)

Reads the LinkedIn page you are viewing, only when you click. Design: `docs/LINKEDIN_EXTENSION_DESIGN.md`.

**This build saves and sends nothing.** It runs the anchor check (§2.8) and copies redacted reports so the
Phase 2a gate can be judged before any capture logic exists.

```bash
make extension        # type-check + build into extension/dist
```

Load it: `chrome://extensions` (or `edge://extensions`) → Developer mode → Load unpacked → `extension/dist`.
The manifest carries a fixed `key`, so the extension ID is always `chmdlkfgnkafhlghokcgggmddahnaoao`.

- The pill (bottom right of every linkedin.com page) runs **Check job page / Check profile**; `Alt+Shift+S` does the same.
- **Copy report**: the anchors and the region lines, redacted to lengths unless you tick "Include page text".
- **Copy page structure**: a redacted skeleton of `<main>` (tags, roles, link shapes, text lengths; no class is read).
- Guard: `backend/tests/test_extension_guard.py` (no timers/observers/clicks/scrolling/network/innerHTML/class reads; permissions `storage` + `https://www.linkedin.com/*` only).
