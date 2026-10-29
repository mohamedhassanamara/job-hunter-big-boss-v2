# Job Hunter capture extension

Saves the LinkedIn job or person you are viewing to your own Job Hunter app, only when you click. Full guide:
`docs/EXTENSION.md`. Design and gate results: `docs/LINKEDIN_EXTENSION_DESIGN.md`.

```bash
make extension        # type-check + build into extension/dist
```

Load it: `chrome://extensions` (or `edge://extensions`) → Developer mode → Load unpacked → `extension/dist`.
The manifest carries a fixed `key`, so the extension ID is always `chmdlkfgnkafhlghokcgggmddahnaoao`
(the backend's `EXTENSION_IDS` default).

1. In the app: Settings → LinkedIn → Browser extension → **Create token**.
2. Extension → Details → Extension options: paste the token, **Test connection**.
3. On a LinkedIn job or profile press the pill (**Save job** / **Save person**) or `Alt+Shift+S`.

Layout: `src/shared` (the thin extractor, reports), `src/content` (the pill and panel), `src/background`
(`api.ts` is the only file that touches the network: localhost, `/ext/*`, with the token), `src/options`
(pairing), `src/popup` (status and diagnostic copies).
Guard: `backend/tests/test_extension_guard.py`.
