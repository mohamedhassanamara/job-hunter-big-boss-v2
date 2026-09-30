"""CV rendering: a template (style only) + a CVDocument (content) + the candidate profile (header)
→ escaped LaTeX → PDF, measured with PyMuPDF (page count, how full the page is).

Templates live in `templates/<name>/` (built in) or `data/templates/<name>/` (added by the user):
`cv.tex.j2` + `cv.config.yaml`. The contract is documented in docs/CV_TEMPLATES.md.
Jinja uses LaTeX-safe delimiters: \\VAR{...} (auto-escaped), \\BLOCK{...}, \\#{...}.
"""

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml
from pydantic import BaseModel

from app.config import DATA_DIR

ROOT = Path(__file__).resolve().parents[3]
BUILTIN_TEMPLATES = ROOT / "templates"
USER_TEMPLATES = DATA_DIR / "templates"
COMPILE_TIMEOUT = 90
PAPER_CLASS = {"letter": "letterpaper", "a4": "a4paper"}

# ------------------------------------------------------------------------------------ content


class CVRole(BaseModel):
    item_id: int | None = None
    title: str = ""
    org: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = []


class CVProject(BaseModel):
    item_id: int | None = None
    name: str = ""
    stack: list[str] = []
    label: str = ""
    bullets: list[str] = []


class CVSkillGroup(BaseModel):
    category: str
    items: list[str] = []


class CVCertification(BaseModel):
    item_id: int | None = None
    name: str = ""
    issuer: str = ""
    credential_id: str = ""
    url: str = ""


class CVEducation(BaseModel):
    item_id: int | None = None
    school: str = ""
    degree: str = ""
    location: str = ""
    start: str = ""
    end: str = ""


class CVDocument(BaseModel):
    """Everything the body of a CV shows. Built from the experience pool (never from a template)."""

    summary: str = ""
    skills: list[CVSkillGroup] = []
    roles: list[CVRole] = []
    projects: list[CVProject] = []
    certifications: list[CVCertification] = []
    education: list[CVEducation] = []
    volunteering: list[CVRole] = []


class CVLink(BaseModel):
    type: str = "other"  # linkedin | github | portfolio | other
    label: str = ""
    url: str = ""


class CVProfile(BaseModel):
    """The header, from Settings → Candidate. Only full_name is required."""

    full_name: str
    location: str = ""
    phone: str = ""
    email: str = ""
    links: list[CVLink] = []


# ----------------------------------------------------------------------------------- escaping


class Raw(str):
    """Already-LaTeX text (macro output, paper option): not escaped again."""


_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "^": r"\^{}", "~": r"$\sim$", "<": r"\textless{}",
    ">": r"\textgreater{}", "|": r"\textbar{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _ESCAPES))
_OPEN_QUOTE = re.compile(r'(^|[\s(\[{])"')


def latex_escape(value: Any) -> str:
    """Plain text → LaTeX. Straight double quotes become ``…'' (OT1 has no straight quote)."""
    if value is None:
        return ""
    if isinstance(value, Raw):
        return value
    text = _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group(0)], str(value))
    text = _OPEN_QUOTE.sub(lambda m: m.group(1) + "``", text)
    return text.replace('"', "''")


def latex_url(value: Any) -> Raw:
    """URL for \\href: only characters that break the argument are escaped."""
    text = str(value or "").strip()
    if text and not re.match(r"^[a-z][a-z0-9+.-]*:", text, re.I):
        text = f"https://{text}"
    return Raw(text.replace("\\", "/").replace("%", r"\%").replace("#", r"\#")
               .replace("{", "%7B").replace("}", "%7D"))


def _raw(value: Any) -> Raw:
    return Raw(str(value))


def jinja_env(template_dir: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        block_start_string=r"\BLOCK{", block_end_string="}",
        variable_start_string=r"\VAR{", variable_end_string="}",
        comment_start_string=r"\#{", comment_end_string="}",
        trim_blocks=True, lstrip_blocks=True, autoescape=False,
        keep_trailing_newline=True, undefined=jinja2.StrictUndefined,
        finalize=latex_escape,
    )
    env.filters["raw"] = _raw
    env.filters["url"] = latex_url
    return env


# ---------------------------------------------------------------------------------- templates


@dataclass
class CVTemplate:
    name: str
    path: Path
    config: dict[str, Any]
    builtin: bool = True

    @property
    def paper(self) -> str:
        return str(self.config.get("paper") or "letter")

    @property
    def min_fill(self) -> float:
        return float(self.config.get("min_fill") or 0.92)


def template_dirs() -> list[tuple[Path, bool]]:
    out = []
    for base, builtin in ((BUILTIN_TEMPLATES, True), (USER_TEMPLATES, False)):
        if base.exists():
            out += [(d, builtin) for d in sorted(base.iterdir())
                    if (d / "cv.tex.j2").exists() and (d / "cv.config.yaml").exists()]
    return out


def load_template(name: str) -> CVTemplate:
    for path, builtin in template_dirs():
        if path.name == name:
            config = yaml.safe_load((path / "cv.config.yaml").read_text()) or {}
            return CVTemplate(name=name, path=path, config=config, builtin=builtin)
    raise KeyError(f"CV template '{name}' not found")


# ------------------------------------------------------------------------------------ context


def header_lines(profile: CVProfile, config: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Two header lines (contact, links) with only the filled items; empty lines dropped."""
    icons = config.get("icons") or {}
    link_icons = icons.get("links") or {}
    contact = []
    if profile.location.strip():
        contact.append({"icon": icons.get("location", "map-marker-alt"),
                        "label": profile.location.strip(), "url": ""})
    if profile.phone.strip():
        contact.append({"icon": icons.get("phone", "phone"), "label": profile.phone.strip(),
                        "url": ""})
    if profile.email.strip():
        contact.append({"icon": icons.get("email", "envelope"), "label": profile.email.strip(),
                        "url": f"mailto:{profile.email.strip()}"})
    links = [
        {"icon": link_icons.get(link.type, link_icons.get("other", "link")),
         "label": link.label.strip() or _display_url(link.url), "url": link.url.strip()}
        for link in profile.links if link.url.strip()
    ]
    return [line for line in (contact, links) if line]


def _display_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/")


def _non_empty(doc: CVDocument, key: str) -> bool:
    value = getattr(doc, key, None)
    if key == "summary":
        return bool((value or "").strip())
    if key == "skills":
        return any(g.items for g in value or [])
    return bool(value)


def build_context(doc: CVDocument, profile: CVProfile, template: CVTemplate) -> dict[str, Any]:
    config = template.config
    experience_key = {"experience": "roles"}
    sections = []
    for section in config.get("sections") or []:
        key = section["key"]
        if _non_empty(doc, experience_key.get(key, key)):
            sections.append({"key": key, "title": section.get("title") or key.title()})
    return {
        "paper_class": Raw(PAPER_CLASS.get(template.paper, "letterpaper")),
        "profile": profile.model_dump(),
        "header_lines": header_lines(profile, config),
        "sections": sections,
        "summary": doc.summary.strip(),
        "skills": [g.model_dump() for g in doc.skills if g.items],
        "roles": [r.model_dump() for r in doc.roles],
        "projects": [p.model_dump() for p in doc.projects],
        "certifications": [c.model_dump() for c in doc.certifications],
        "education": [e.model_dump() for e in doc.education],
        "volunteering": [v.model_dump() for v in doc.volunteering],
    }


def render_tex(doc: CVDocument, profile: CVProfile, template: CVTemplate) -> str:
    env = jinja_env(template.path)
    tex = env.get_template("cv.tex.j2").render(**build_context(doc, profile, template))
    return re.sub(r"\n{3,}", "\n\n", tex)


# ------------------------------------------------------------------------------ cover letter

LETTER_FILE = "cover_letter.tex.j2"
BABEL = {"fr": "french", "en": "english"}


class LetterDocument(BaseModel):
    """What a cover letter template renders (all content; the template is style only)."""

    language: str = "en"
    place_date: str = ""
    company: str = ""
    attention: str = ""
    subject: str = ""
    salutation: str = ""
    paragraphs: list[str] = []
    closing: str = ""


def has_letter(template: CVTemplate) -> bool:
    enabled = (template.config.get("cover_letter") or {}).get("enabled", True)
    return bool(enabled) and (template.path / LETTER_FILE).exists()


def _letter_text(value: str) -> str:
    """Narrow no-break spaces (French typography) aren't in the T1 font: use a normal one."""
    return value.replace("\u202f", "\u00a0").strip()


def render_letter_tex(doc: LetterDocument, profile: CVProfile, template: CVTemplate) -> str:
    env = jinja_env(template.path)
    context = {
        "paper_class": Raw(PAPER_CLASS.get(template.paper, "letterpaper")),
        "babel": Raw(BABEL.get(doc.language, "english")),
        "profile": profile.model_dump(),
        "header_lines": header_lines(profile, template.config),
        "place_date": _letter_text(doc.place_date),
        "company": _letter_text(doc.company),
        "attention": _letter_text(doc.attention),
        "subject": _letter_text(doc.subject),
        "salutation": _letter_text(doc.salutation),
        "paragraphs": [_letter_text(p) for p in doc.paragraphs if p.strip()],
        "closing": _letter_text(doc.closing),
    }
    tex = env.get_template(LETTER_FILE).render(**context)
    return re.sub(r"\n{3,}", "\n\n", tex)


# ---------------------------------------------------------------------------------- compiling


@dataclass
class CompileResult:
    ok: bool
    pdf_path: Path | None = None
    pages: int = 0
    fill: float = 0.0  # how full the LAST page is (0-1)
    error: str | None = None
    log_tail: str = ""
    warnings: list[str] = field(default_factory=list)


def measure_pdf(pdf_path: Path) -> tuple[int, float]:
    """(page count, fill of the last page). Fill = lowest text line relative to the text area,
    where the text area is estimated from the first page's top margin (margins are symmetric in
    CV templates)."""
    import pymupdf

    with pymupdf.open(pdf_path) as pdf:
        pages = pdf.page_count
        if not pages:
            return 0, 0.0
        first_top = min((b[1] for b in pdf[0].get_text("blocks")), default=0.0)
        last = pdf[pages - 1]
        bottom = max((b[3] for b in last.get_text("blocks")), default=0.0)
        height = last.rect.height
        usable = max(1.0, height - 2 * first_top)
        return pages, max(0.0, min(1.0, (bottom - first_top) / usable))


def compile_tex(tex: str, out_dir: Path, name: str = "cv") -> CompileResult:
    """latexmk -pdf in a temp dir; the PDF (and .tex) are copied into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        return CompileResult(False, error="latexmk not found: install TeX Live (MacTeX)")
    with tempfile.TemporaryDirectory(prefix="jh-cv-") as tmp:
        src = Path(tmp) / f"{name}.tex"
        src.write_text(tex)
        try:
            proc = subprocess.run(
                [latexmk, "-pdf", "-interaction=nonstopmode", "-halt-on-error", src.name],
                cwd=tmp, capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(False, error=f"LaTeX timed out after {COMPILE_TIMEOUT}s")
        log_path = Path(tmp) / f"{name}.log"
        log = log_path.read_text(errors="replace") if log_path.exists() else proc.stdout
        pdf = Path(tmp) / f"{name}.pdf"
        (out_dir / f"{name}.tex").write_text(tex)
        if proc.returncode != 0 or not pdf.exists():
            error = next((ln for ln in log.splitlines() if ln.startswith("!")), "LaTeX failed")
            return CompileResult(False, error=error, log_tail=log[-3000:])
        target = out_dir / f"{name}.pdf"
        shutil.copyfile(pdf, target)
        pages, fill = measure_pdf(target)
        warnings = sorted({ln.strip() for ln in log.splitlines()
                           if "Overfull \\hbox" in ln})[:10]
        return CompileResult(True, target, pages, fill, log_tail=log[-1500:], warnings=warnings)
