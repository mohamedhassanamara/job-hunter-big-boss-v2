# Design system

Job Hunter should feel like a calm, dense, fast workspace (Linear-like): neutral surfaces, one brand
hue, color reserved for *meaning* (stage, fit, status). Everything visual comes from the tokens below.

**Source of truth:** `frontend/src/styles/tokens.css` (raw values, light + dark) →
`frontend/src/styles/index.css` (`@theme inline` maps tokens to Tailwind utilities).
Tailwind's default color palette is disabled (`--color-*: initial`), so `bg-blue-500` does not
even compile, and `scripts/check-tokens.sh` (part of `make lint`) rejects palette classes and raw hex.

---

## 1. Color

All colors are OKLCH. Neutrals carry a faint cool tint (hue 270) so they sit well next to the brand hue.

### Neutrals and surfaces

| Token | Utility | Light | Dark | Use |
|---|---|---|---|---|
| `--bg` | `bg-bg` | `oklch(0.985 0.002 270)` | `oklch(0.165 0.005 270)` | App background (main area) |
| `--bg-subtle` | `bg-bg-subtle` | `oklch(0.972 0.003 270)` | `oklch(0.15 0.005 270)` | Sidebar, table headers, wells |
| `--surface` | `bg-surface` | `oklch(1 0 0)` | `oklch(0.195 0.006 270)` | Cards, panels, inputs |
| `--surface-raised` | `bg-surface-raised` | `oklch(1 0 0)` | `oklch(0.225 0.007 270)` | Popovers, dialogs, menus (with shadow) |
| `--surface-hover` | `bg-surface-hover` | `oklch(0.962 0.004 270)` | `oklch(0.245 0.007 270)` | Row/button hover |
| `--surface-selected` | `bg-surface-selected` | `oklch(0.948 0.018 275)` | `oklch(0.27 0.035 275)` | Selected row, active nav item |
| `--border` | `border-border` | `oklch(0.918 0.004 270)` | `oklch(0.275 0.007 270)` | Default hairlines |
| `--border-strong` | `border-border-strong` | `oklch(0.86 0.006 270)` | `oklch(0.35 0.009 270)` | Inputs, emphasized dividers |
| `--fg` | `text-fg` | `oklch(0.22 0.012 270)` | `oklch(0.955 0.004 270)` | Primary text |
| `--fg-muted` | `text-fg-muted` | `oklch(0.47 0.012 270)` | `oklch(0.73 0.01 270)` | Secondary text, labels |
| `--fg-subtle` | `text-fg-subtle` | `oklch(0.6 0.01 270)` | `oklch(0.58 0.01 270)` | Meta text, placeholders, icons |

### Brand (primary)

One indigo-violet hue (275). Used for the primary action, focus, links, and selection accents only.

| Token | Utility | Light | Dark |
|---|---|---|---|
| `--primary` | `bg-primary` / `text-primary` | `oklch(0.54 0.2 275)` | `oklch(0.67 0.17 275)` |
| `--primary-hover` | `bg-primary-hover` | `oklch(0.49 0.21 275)` | `oklch(0.72 0.16 275)` |
| `--primary-fg` | `text-primary-fg` | `oklch(0.99 0 0)` | `oklch(0.16 0.02 275)` |
| `--primary-subtle` | `bg-primary-subtle` | `oklch(0.955 0.03 275)` | `oklch(0.28 0.06 275)` |
| `--ring` | `ring-ring` | `oklch(0.6 0.18 275 / 0.45)` | `oklch(0.7 0.16 275 / 0.5)` |

### Feedback

Each has `-bg` (tint), `-fg` (text on tint / icon) and a solid base.

| Family | Hue | Meaning |
|---|---|---|
| `success` | 150 | Sent, approved, completed |
| `warning` | 75 | Needs attention, paused, lookup pending |
| `danger` | 25 | Errors, destructive actions, failed sends |
| `info` | 245 | Neutral notices, running |

### Tone families (internal building blocks)

Stage and fit tokens are built from eight tone families, each with `dot`, `bg`, `fg`, `border`:

| Tone | Hue / chroma | Light dot · bg · fg | Dark dot · bg · fg |
|---|---|---|---|
| slate | 260 / 0.03 | L .62 · .955 · .42 | L .68 · .27 · .82 |
| blue | 250 / 0.15 | L .6 · .955 · .44 | L .7 · .28 · .84 |
| violet | 295 / 0.16 | L .58 · .955 · .44 | L .7 · .28 · .84 |
| amber | 75 / 0.15 | L .72 · .962 · .47 | L .78 · .29 · .86 |
| teal | 185 / 0.11 | L .62 · .955 · .43 | L .72 · .27 · .84 |
| green | 150 / 0.15 | L .6 · .955 · .42 | L .72 · .27 · .84 |
| gray | – / 0 | L .66 · .955 · .47 | L .6 · .26 · .76 |
| red | 25 / 0.17 | L .6 · .955 · .47 | L .68 · .28 · .84 |

(Tint `bg` chroma is ~25% of the base in light and ~35% in dark.)

### Pipeline stage colors

| Stage | Label | Tone | Utilities |
|---|---|---|---|
| `new` | New | slate | `bg-stage-new-bg text-stage-new-fg`, dot `bg-stage-new-dot` |
| `shortlisted` | Shortlisted | blue | `…stage-shortlisted-…` |
| `cv_ready` | CV ready | violet | `…stage-cv_ready-…` |
| `ready` | Ready to send / Ready to apply | amber | `…stage-ready-…` |
| `done` | Sent / Applied | teal | `…stage-done-…` |
| `interview` | Interview | green | `…stage-interview-…` |
| `closed` | Closed | gray | `…stage-closed-…` |

Always render stages with `<StageBadge>`: a colored dot plus a label. Never color alone.

### Fit score bands

| Band | Range | Tone | Meaning |
|---|---|---|---|
| strong | ≥ 80 | green | Apply |
| good | 65–79 | teal | Worth a look |
| fair | 50–64 | amber | Stretch |
| weak | < 50 | gray | Probably skip. Deliberately **not red**, since a low fit is not an error |

Always render scores with `<FitBadge>`: the number in tabular figures inside a tinted pill, with the band name in the tooltip.

---

## 2. Typography

- **Family:** `Inter Variable` (bundled via `@fontsource-variable/inter`, no network fetch), with the system stack as fallback. Mono: `JetBrains Mono`, falling back to `ui-monospace`.
- Enable `font-feature-settings: "cv11", "ss01"`. Use `tabular-nums` for scores, counts, dates, and times.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `text-2xs` | 11 / 16 | 500 | Kbd hints, micro labels, column counts |
| `text-xs` | 12 / 16 | 400–500 | Meta, badges, table headers (uppercase is not used) |
| `text-sm` | 13 / 20 | 400 | **Default UI text**: rows, inputs, buttons |
| `text-base` | 14 / 22 | 400 | Reading text (descriptions, email bodies) |
| `text-md` | 16 / 24 | 600 | Panel titles, card titles |
| `text-lg` | 20 / 28 | 600 | Page titles |
| `text-xl` | 24 / 32 | 600 | Today greeting |
| `text-2xl` | 30 / 36 | 600 | Big numbers (stat cards) |

Headings use `tracking-tight` (−0.01em). Body text uses normal tracking.

## 3. Spacing and layout

- 4px base. The allowed steps are `1 (4) · 1.5 (6) · 2 (8) · 3 (12) · 4 (16) · 5 (20) · 6 (24) · 8 (32) · 12 (48) · 16 (64)`.
- Page padding: `px-6 py-5`. Card padding: `p-4`. Row height in dense lists: 36–40px (`h-9`/`h-10`); list rows with 2 lines: `py-2.5`.
- Sidebar is 232px (expanded) or 52px (collapsed). The top bar is 48px. The side panel (Discover) is 440px, or 380px under 1280px width.
- Minimum supported viewport is 1024px wide. Below 1280px the sidebar collapses to icons automatically.

## 4. Radius, elevation, motion

| Token | Value | Use |
|---|---|---|
| `rounded-sm` | 4px | Badges, kbd, checkboxes |
| `rounded-md` | 6px | Buttons, inputs, rows |
| `rounded-lg` | 8px | Cards, panels, kanban cards |
| `rounded-xl` | 12px | Dialogs, the command palette |

- `shadow-sm` is the resting state for cards in light mode (in dark mode, borders do the work). `shadow-lg` is for popovers, dialogs, and dragged cards.
- Motion: `duration-fast` (120ms) for hovers and toggles, `duration-base` (200ms) for panels and sheets. Easing is `ease-out`. Respect `prefers-reduced-motion`.

## 5. Components and rules

1. **Only tokens.** No hex, no Tailwind palette colors, and no arbitrary `[#…]` values in components.
2. **One primary button per view** (`variant="default"`). Everything else is `secondary`, `ghost`, or `outline`.
3. **Every data view has 4 states:** loading (skeleton shaped like the content, not spinners), empty (`<EmptyState>` with icon, one sentence, and **one next action**), error (`<ErrorState>` with a retry button), and populated.
4. **No dead ends.** Every screen links forward in the flow (e.g. CV approved → "Draft email" or "Mark ready to apply").
5. **Status = dot + label**, never color alone. Icons are Lucide, at 16px (`size-4`) in UI and 14px (`size-3.5`) inside badges, with a stroke width of 1.75.
6. **Keyboard first.** Every list view supports j/k and shows `<Kbd>` hints on hover or in tooltips. Destructive or dismiss actions offer undo in the toast instead of a confirmation dialog.
7. **Copy:** sentence case, short, verbs on buttons ("Shortlist", "Approve draft"). Use relative dates in lists and absolute dates in tooltips.
8. **Density:** 13px default text, generous whitespace *between* groups, tight *within* groups.
9. **Dark mode** is a first-class theme, not an afterthought. Check both themes for every screen.

## 6. Shared app components (`src/components/app/`)

`AppShell`, `Sidebar`, `TopBar`, `PageHeader` (title, description, actions slot), `EmptyState`,
`ErrorState`, `Skeleton*`, `FitBadge`, `StageBadge`, `SourceBadge`, `RemoteBadge`, `ContactTierBadge`,
`Kbd`, `SidePanel`, `StatCard`, `CommandPalette`, `ShortcutsDialog`, `ThemeToggle`.
New screens compose these. If a pattern appears twice, promote it here.
