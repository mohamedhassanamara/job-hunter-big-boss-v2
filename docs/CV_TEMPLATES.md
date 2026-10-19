# CV templates: the contract

A CV template defines **style only**: layout, fonts, colours, spacing, how a section looks. It contains
no content. Content comes from your data:

- the **header** from Settings → Candidate
- **everything else** from the Experience pool, chosen per job by the generator and checked in code

Filled fields appear. Empty ones are omitted cleanly, with no leftover icon, label, separator or section title.

## Files

A template is a folder with two files:

```
templates/<name>/cv.tex.j2        built-in (in the repo)
templates/<name>/cv.config.yaml
data/templates/<name>/...         added from Settings → Templates (local, not in git)
```

`templates/reference/cv.tex` is the style reference the default template was built from. It holds example
content and is never used to generate a CV.

A template can be selected only after it compiles with **fictional sample data** (`app/services/cv_sample.py`)
to **exactly one page**. Results are cached per file hash, so editing a file re-validates it.

## Jinja syntax (LaTeX-safe)

| Syntax | Meaning |
|---|---|
| `\VAR{expr}` | Output a value. **Auto-escaped** for LaTeX: `\ & % $ # _ { } ^ ~ < > \|`; `~` renders as `$\sim$`; straight `"…"` becomes ``` ``…'' ``` |
| `\VAR{expr\|raw}` | Output already-LaTeX text (macro output). Never use it on user data |
| `\VAR{expr\|url}` | A URL for `\href{}`: adds `https://` if missing, escapes only `%` and `#` |
| `\BLOCK{for x in xs}…\BLOCK{endfor}` | Statements (`if`, `for`, `set`, `macro`) |
| `\#{ … }` | Comment. It ends at the first `}`, so don't write braces inside it |

Undefined variables are errors (`StrictUndefined`).

## Variables

| Variable | Shape | Notes |
|---|---|---|
| `paper_class` | `letterpaper` \| `a4paper` | From `paper` in the config. Use it as `\VAR{paper_class\|raw}` in `\documentclass` and `geometry` |
| `profile` | `{full_name, location, phone, email, links[]}` | Settings → Candidate. Only `full_name` is guaranteed |
| `header_lines` | `[[{icon, label, url}]]` | Only the filled header items, grouped into lines: line 1 = location, phone, email; line 2 = links. Empty lines are dropped. Join items with your separator only inside a line (`loop.last`) |
| `sections` | `[{key, title}]` | Config order, **only the non-empty sections**. Loop over it and dispatch on `key` |
| `summary` | `str` | |
| `skills` | `[{category, items[]}]` | Categories in the generator's order; empty ones removed |
| `roles` | `[{title, org, location, start, end, bullets[]}]` | Every job in the pool, newest first. Each has ≥1 bullet when the pool has facts. `start` / `end` are like `Sep 2025` / `Present`, and either may be empty |
| `projects` | `[{name, stack[], label, bullets[]}]` | `stack` is capped at `max_stack_items`; `label` is e.g. "Personal project" |
| `certifications` | `[{name, issuer, credential_id, url}]` | Any field except `name` may be empty |
| `education` | `[{school, degree, location, start, end}]` | |
| `volunteering` | same shape as `roles` | Only when the generator selects it |

## Config (`cv.config.yaml`)

```yaml
name: Default
description: One column, small caps section titles…
paper: letter            # letter | a4
sections:                # order + titles; unknown keys are rejected
  - {key: summary, title: Summary}
  - {key: skills, title: Technical Skills}
  - {key: experience, title: Professional Experience}
  - {key: projects, title: Projects}
  - {key: certifications, title: Certifications}
  - {key: education, title: Education}
  - {key: volunteering, title: Volunteering & Leadership}
icons:                   # Font Awesome 5 names (or whatever your template's icon macro takes)
  location: map-marker-alt
  phone: phone
  email: envelope
  links: {linkedin: linkedin, github: github, portfolio: globe, other: link}
min_fill: 0.92           # the fit loop's "full page" threshold (0-1)
max_bullets_per_role: 5
max_stack_items: 6
```

Leaving a section key out of `sections` hides that section in this template.

## How a CV is produced

1. **Generate (one Claude call).** `claude -p` with our own system prompt (`app/prompts/cv_generate.md`), no tools, and `--json-schema`. It returns a **plan**: pool ids, bullets (your text or a light adaptation) ranked by priority, skill selection and order (verbatim from the pool), summary and short summary. It never returns titles, companies, dates or LaTeX.
2. **Check (in code, `services/cv_check.py`):**
   - Unknown ids and facts are dropped.
   - Adapted bullets (`services/bullet_tailor.py`): every number, tool and named product of the original stays, nothing new, length ±15%, most words kept; then the Claude verifier compares each adapted bullet with its original. Any failure restores the original text.
   - Numbers must match their source fact.
   - Skills must exist in the pool.
   - Unknown tools are flagged.
   - Every role is kept with ≥1 bullet.
   - Violations are shown in CV Studio.
3. **Fit (in code, `services/cv_build.py`, ≤ 4 passes, no model call):** render, compile with `latexmk`, and measure with PyMuPDF.
   - Overflow: drop low-value bullets, then projects, then use the short summary.
   - Underfill: add bullets and projects.
   - The fullest one-page result is kept.
4. **Edit in CV Studio:** force in/out, edit text, switch template. Each change re-fits without calling Claude.

## Cover letter (`cover_letter.tex.j2`)

A template can also render cover letters: `templates/<name>/cover_letter.tex.j2`, enabled by
`cover_letter: {enabled: true}` in `cv.config.yaml`. Without the file, the template renders CVs only and the
Cover letter studio says so. Style only, like the CV: the preamble, colour and header block are copied from
`cv.tex.j2`, so the two documents look like one set (T1 fonts, `babel` in the letter's language, justified body).

| Variable | Meaning |
|---|---|
| `paper_class`, `babel` | Raw: `letterpaper`/`a4paper`, `french`/`english` |
| `profile`, `header_lines` | Same as the CV (the header block must stay identical) |
| `place_date` | "Tunis, le 30 septembre 2026" / "30 September 2026" |
| `company`, `attention` | Recipient block ("À l'attention de …" / "Attn: …" when there's a contact) |
| `subject` | "Objet : candidature au poste de …" / "Application for the … position" |
| `salutation`, `paragraphs[]`, `closing` | The letter; the ask ends the last paragraph |

The letter must compile to one page (a longer letter is flagged, never cut).

## Tests that guard this

- `tests/test_cv_render.py`:
  - style golden test: the default template plus a reference-like fixture renders **pixel-identical** to the reference
  - escaping
  - optional header fields
  - link counts
  - empty sections
  - paper size
- `tests/test_cover_letter.py`: the letter template shares the CV's header block byte for byte and compiles to one page.
- `tests/test_no_personal_data.py`: personal tokens are derived from the reference. It fails if any appear in templates, configs or source code.
