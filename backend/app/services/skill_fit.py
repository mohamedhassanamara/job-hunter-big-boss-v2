"""Line fit of a job CV's flat skills block: 2 to 3 lines, the last one at least 75% full.

Each skill is an unbreakable `\\mbox`, so a line breaks only after ", ". The length is chosen
before the page is fitted, in three steps:

1. Metrics: one small LaTeX run per template (cached by the template's content hash, so editing
   or switching the template measures again) typesets every skill with the template's own
   preamble and skills-block markup, and writes the exact widths, the line width and the
   space glue to the log. No font files, kerning or ligatures are simulated.
2. Choice: TeX-style justified line breaking (minimum total demerits, tolerance 100 then 200)
   over those widths, for the target length first, then one more or one less, and so on. Skills
   are cut from the tail of the cut order (the plan's: filler first, JD matches last); if the
   JD matches alone are too long, the least relevant of them go too.
3. Check: `measure_block` reads the real PDF (PyMuPDF) and `fit_to_page` corrects at most twice.

No length that satisfies the rule: the caller keeps the grouped list.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.services.cv_render import CVDocument, CVProfile, CVTemplate, latex_escape, render_tex

MIN_LINES, MAX_LINES = 2, 3
MIN_LAST_FILL = 0.75
PT_TO_BP = 72 / 72.27  # TeX points to PDF points
AFTER_COMMA = 1.25  # \sfcode of "," is 1250: the glue after it stretches 1.25x, shrinks /1.25
METRICS_VERSION = "1"
CACHE_DIR = DATA_DIR / "cv" / ".skill_metrics"
_SKILLS_BLOCK = re.compile(
    r"\\BLOCK\{elif s\.key == 'skills'\}(?P<head>.*?)\\BLOCK\{if skills_flat\}"
    r".*?\\BLOCK\{endif\}(?P<tail>.*?)\\BLOCK\{elif ", re.S)
_DEFAULT_HEAD = ("\\begin{itemize}[leftmargin=0pt, label={}, itemsep=1.5pt, topsep=1pt]\n"
                 "\\small{\\item{\n")
_DEFAULT_TAIL = "}}\n\\end{itemize}\n"


@dataclass
class Metrics:
    linewidth: float = 0.0  # pt
    space: float = 0.0
    stretch: float = 0.0
    shrink: float = 0.0
    comma: float = 0.0
    widths: dict[str, float] = field(default_factory=dict)  # skill → width of its mbox (pt)
    rs_stretch: float = 0.0  # \rightskip's stretch (pt); with rs_fil it is infinite: ragged right
    rs_fil: bool = False


@dataclass
class Line:
    first: int
    last: int
    natural: float


# ------------------------------------------------------------------------------- metrics


def template_key(template: CVTemplate) -> str:
    h = hashlib.sha256(METRICS_VERSION.encode())
    for name in ("cv.tex.j2", "cv.config.yaml"):
        try:
            h.update((template.path / name).read_bytes())
        except OSError:
            h.update(name.encode())
    return h.hexdigest()[:16]


def supports_flat(template: CVTemplate) -> bool:
    try:
        return "skills_flat" in (template.path / "cv.tex.j2").read_text()
    except OSError:
        return False


def _block_markup(template: CVTemplate) -> tuple[str, str]:
    """The template's own markup around the skills text (list, size, braces), so the metrics are
    measured in the same context as the real block."""
    try:
        m = _SKILLS_BLOCK.search((template.path / "cv.tex.j2").read_text())
    except OSError:
        m = None
    if not m:
        return _DEFAULT_HEAD, _DEFAULT_TAIL
    head = "\n".join(ln for ln in m["head"].splitlines()
                     if "\\section" not in ln and "%---" not in ln) + "\n"
    return head, m["tail"].strip() + "\n"


def _pt(text: str) -> float:
    return float(text.strip().removesuffix("pt"))


def _measure_doc(template: CVTemplate, skills: list[str]) -> str:
    tex = render_tex(CVDocument(), CVProfile(full_name="Metrics"), template)
    preamble = tex.split("\\begin{document}")[0]
    head, tail = _block_markup(template)
    rows = "".join(f"\\m{{{i}}}{{{latex_escape(s)}}}\n" for i, s in enumerate(skills))
    return (preamble + "\\begin{document}\n\\newbox\\mb\n"
            "\\def\\m#1#2{\\setbox\\mb\\hbox{\\mbox{#2}}\\immediate\\write16{SKW|#1|\\the\\wd\\mb}}\n"
            + head + "\\setbox\\mb\\hbox{,}\\immediate\\write16{SP|\\the\\fontdimen2\\font|"
            "\\the\\fontdimen3\\font|\\the\\fontdimen4\\font|\\the\\wd\\mb|\\the\\linewidth}\n"
            "\\immediate\\write16{RS|\\the\\rightskip}\n"
            + rows + tail + "\\end{document}\n")


def _run_metrics(template: CVTemplate, skills: list[str]) -> dict[str, Any] | None:
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        return None
    with tempfile.TemporaryDirectory(prefix="jh-skillfit-") as tmp:
        (Path(tmp) / "m.tex").write_text(_measure_doc(template, skills))
        try:
            subprocess.run([latexmk, "-pdf", "-interaction=nonstopmode", "m.tex"], cwd=tmp,
                           capture_output=True, text=True, timeout=120)
            log = (Path(tmp) / "m.log").read_text(errors="replace")
        except (subprocess.TimeoutExpired, OSError):
            return None
    sp = re.search(r"^SP\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|\s]+)", log, re.M)
    widths = {int(i): _pt(w) for i, w in re.findall(r"^SKW\|(\d+)\|(\S+)", log, re.M)}
    if not sp or len(widths) != len(skills):
        return None
    space, stretch, shrink, comma, linewidth = (_pt(x) for x in sp.groups())
    rs = re.search(r"^RS\|(.*)$", log, re.M)
    plus = re.search(r"plus\s+([-\d.]+)\s*(pt|fil+)", rs.group(1)) if rs else None
    return {"space": space, "stretch": stretch, "shrink": shrink, "comma": comma,
            "linewidth": linewidth, "widths": {skills[i]: w for i, w in widths.items()},
            "rs_fil": bool(plus and plus.group(2).startswith("fil")),
            "rs_stretch": float(plus.group(1)) if plus and plus.group(2) == "pt" else 0.0}


def metrics_for(template: CVTemplate, skills: list[str],
                cache_dir: Path | None = None) -> Metrics | None:
    """Exact widths of `skills` in this template, measured once and cached by template content."""
    folder = cache_dir or CACHE_DIR
    path = folder / f"{template_key(template)}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    missing = [s for s in dict.fromkeys(skills) if s not in (data.get("widths") or {})]
    if missing or not data.get("linewidth"):
        fresh = _run_metrics(template, missing or skills[:1])
        if fresh is None:
            return None
        data = {**{k: fresh[k] for k in ("space", "stretch", "shrink", "comma", "linewidth",
                                         "rs_fil", "rs_stretch")},
                "widths": {**(data.get("widths") or {}), **fresh["widths"]}}
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=1))
        except OSError:
            pass  # the cache is an optimisation only
    return Metrics(data["linewidth"], data["space"], data["stretch"], data["shrink"],
                   data["comma"], {s: data["widths"][s] for s in skills},
                   data.get("rs_stretch", 0.0), bool(data.get("rs_fil")))


# ------------------------------------------------------------------------- line breaking


def _badness(natural: float, width: float, stretch: float, shrink: float,
             infinite: bool = False) -> float | None:
    """TeX's badness of a line, None when it cannot be set (too wide to shrink). `infinite`:
    the line has fil stretch (ragged right, the last line), so it is never loose."""
    if natural > width:
        if shrink <= 0 or natural - width > shrink:
            return None
        return min(10000.0, 100 * ((natural - width) / shrink) ** 3)
    if natural == width or infinite:
        return 0.0
    if stretch <= 0:
        return 10000.0
    return min(10000.0, 100 * ((width - natural) / stretch) ** 3)


def break_lines(widths: list[float], m: Metrics) -> list[Line] | None:
    """TeX's line breaking of `\\mbox{a}, \\mbox{b}, ...` (breaks only after a comma): minimum
    total demerits under the two tolerances, a later break winning a tie (tex.web's `<=`).
    Works for ragged-right (the usual CV templates) and justified text."""
    n = len(widths)
    if n == 0:
        return []
    unit = [w + (m.comma if i < n - 1 else 0.0) for i, w in enumerate(widths)]
    for tolerance in (100.0, 200.0):
        best: list[tuple[float, int] | None] = [None] * (n + 1)  # (demerits, previous break)
        best[0] = (0.0, -1)
        for end in range(1, n + 1):
            for start in range(end):
                if best[start] is None:
                    continue
                gaps = end - start - 1
                natural = sum(unit[start:end]) + gaps * m.space
                b = _badness(natural, m.linewidth, gaps * m.stretch * AFTER_COMMA + m.rs_stretch,
                             gaps * m.shrink / AFTER_COMMA,
                             infinite=m.rs_fil or end == n)
                if b is None or b > tolerance:
                    continue
                total = best[start][0] + (10 + b) ** 2
                if best[end] is None or total <= best[end][0]:
                    best[end] = (total, start)
        if best[n] is not None:
            lines: list[Line] = []
            end = n
            while end > 0:
                start = best[end][1]
                gaps = end - start - 1
                natural = sum(unit[start:end]) + gaps * m.space
                lines.append(Line(start, end - 1, min(natural, m.linewidth)))
                end = start
            return lines[::-1]
    return None


def satisfies(lines: list[Line] | None, linewidth: float) -> bool:
    return bool(lines) and MIN_LINES <= len(lines) <= MAX_LINES \
        and lines[-1].natural / linewidth >= MIN_LAST_FILL


# --------------------------------------------------------------------------------- choice


def candidates(total: int, target: int, floor: int) -> list[int]:
    """How many skills to cut (m), the target's own cut first, then one fewer, one more, ..."""
    start = max(0, total - target)
    order = [start]
    for step in range(1, total + 1):
        order += [start - step, start + step]
    return [m for m in order if 0 <= m <= total - max(1, floor)]


@dataclass
class Choice:
    skills: list[str]  # what prints, in display order
    cut: int  # how many were cut from the tail of the cut order
    lines: int
    last_fill: float


def choose(skills: list[str], cut_order: list[int], target: int, m: Metrics, *,
           floor: int = 1, rejected: set[int] | None = None) -> Choice | None:
    """The list to print for this template, or None when no length meets the rule."""
    usable = [i for i, s in enumerate(skills) if m.widths.get(s, m.linewidth + 1) <= m.linewidth]
    order = [i for i in cut_order if i in usable]
    for cut in candidates(len(usable), target, floor):
        if rejected and cut in rejected:
            continue
        dropped = set(order[:cut])
        kept = [i for i in usable if i not in dropped]
        lines = break_lines([m.widths[skills[i]] for i in kept], m)
        if satisfies(lines, m.linewidth):
            return Choice([skills[i] for i in kept], cut, len(lines or []),
                          round(lines[-1].natural / m.linewidth, 3))
    return None


# ---------------------------------------------------------------------------- real page


def measure_block(pdf_path: Path, template: CVTemplate, linewidth: float
                  ) -> tuple[int, float] | None:
    """(lines, last-line fill) of the skills block in the real PDF, None when it isn't found."""
    import pymupdf

    title = next((str(s.get("title") or "") for s in template.config.get("sections") or []
                  if s.get("key") == "skills"), "Skills")
    with pymupdf.open(pdf_path) as pdf:
        rows = []
        for block in pdf[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if text:
                    rows.append((line["bbox"], text, max(s["size"] for s in line["spans"])))
    rows.sort(key=lambda r: (round(r[0][1]), r[0][0]))
    heading = next((i for i, r in enumerate(rows)
                    if r[1].upper() == title.upper() and r[2] >= 10), None)
    if heading is None:
        return None
    body = []
    for bbox, text, size in rows[heading + 1:]:
        if size >= rows[heading][2] - 0.5:
            break
        body.append((bbox, text))
    if not body:
        return None
    last = body[-1][0]
    return len(body), round((last[2] - last[0]) / (linewidth * PT_TO_BP), 3)


def block_ok(measured: tuple[int, float] | None) -> bool:
    return measured is not None and MIN_LINES <= measured[0] <= MAX_LINES \
        and measured[1] >= MIN_LAST_FILL - 0.01  # a hair of tolerance for PDF text extents
