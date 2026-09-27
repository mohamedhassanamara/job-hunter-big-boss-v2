"""CV template registry: built-in templates (templates/) and user-added ones (data/templates/).

A template is selectable only once it compiled to exactly one page with the fictional sample
content (app/services/cv_sample.py). Validation results are cached per template file hash in
data/templates/.validation.json, so a changed file is re-validated automatically.
"""

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import jinja2
import yaml

from app.services import cv_render
from app.services.cv_render import USER_TEMPLATES, compile_tex, load_template, render_tex
from app.services.cv_sample import SAMPLE_DOCUMENT, SAMPLE_PROFILE

VALIDATION_FILE = USER_TEMPLATES / ".validation.json"
PREVIEW_DIR = USER_TEMPLATES / ".previews"
SECTION_KEYS = {"summary", "skills", "experience", "projects", "certifications", "education",
                "volunteering"}


@dataclass
class TemplateStatus:
    name: str
    description: str
    paper: str
    builtin: bool
    valid: bool
    pages: int | None
    error: str | None
    hash: str


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    for f in ("cv.tex.j2", "cv.config.yaml"):
        h.update((path / f).read_bytes())
    return h.hexdigest()[:16]


def _cache() -> dict[str, Any]:
    try:
        return json.loads(VALIDATION_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    VALIDATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_FILE.write_text(json.dumps(cache, indent=1))


def check_config(config: Any) -> list[str]:
    errors = []
    if not isinstance(config, dict):
        return ["cv.config.yaml must be a mapping"]
    if config.get("paper", "letter") not in cv_render.PAPER_CLASS:
        errors.append("paper must be letter or a4")
    sections = config.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty list of {key, title}")
    else:
        for s in sections:
            if not isinstance(s, dict) or s.get("key") not in SECTION_KEYS:
                errors.append(f"unknown section {s!r} (allowed: {', '.join(sorted(SECTION_KEYS))})")
    return errors


def validate(name: str, *, force: bool = False) -> TemplateStatus:
    template = load_template(name)
    digest = _hash(template.path)
    cache = _cache()
    cached = cache.get(name)
    if cached and cached.get("hash") == digest and not force:
        return TemplateStatus(**cached)
    errors = check_config(template.config)
    pages = None
    if not errors:
        try:
            tex = render_tex(SAMPLE_DOCUMENT, SAMPLE_PROFILE, template)
        except jinja2.TemplateError as exc:
            errors.append(f"Template error: {exc}")
        else:
            result = compile_tex(tex, PREVIEW_DIR / name, "sample")
            pages = result.pages or None
            if not result.ok:
                errors.append(f"LaTeX: {result.error}")
            elif result.pages != 1:
                errors.append(f"Sample content must fit one page (got {result.pages})")
    status = TemplateStatus(
        name=name, description=str(template.config.get("description") or ""),
        paper=template.paper, builtin=template.builtin, valid=not errors, pages=pages,
        error="; ".join(errors) or None, hash=digest,
    )
    cache[name] = asdict(status)
    _save_cache(cache)
    return status


def list_templates() -> list[TemplateStatus]:
    return [validate(path.name) for path, _ in cv_render.template_dirs()]


def preview_pdf(name: str) -> Path | None:
    validate(name)
    path = PREVIEW_DIR / name / "sample.pdf"
    return path if path.exists() else None


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "template"


def add_template(name: str, tex: str, config_text: str) -> TemplateStatus:
    """Save a user template to data/templates/<slug>/ and validate it (kept even when invalid,
    so the user sees why; it can't be selected until it validates)."""
    slug = slugify(name)
    if (cv_render.BUILTIN_TEMPLATES / slug).exists():
        raise ValueError(f"'{slug}' is a built-in template name")
    try:
        config = yaml.safe_load(config_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"cv.config.yaml is not valid YAML: {exc}") from exc
    if errors := check_config(config):
        raise ValueError("; ".join(errors))
    if r"\begin{document}" not in tex:
        raise ValueError("cv.tex.j2 must be a full LaTeX document")
    target = USER_TEMPLATES / slug
    target.mkdir(parents=True, exist_ok=True)
    (target / "cv.tex.j2").write_text(tex)
    (target / "cv.config.yaml").write_text(config_text)
    return validate(slug, force=True)


def delete_template(name: str) -> None:
    template = load_template(name)
    if template.builtin:
        raise ValueError("Built-in templates can't be deleted")
    shutil.rmtree(template.path)
    cache = _cache()
    cache.pop(name, None)
    _save_cache(cache)
