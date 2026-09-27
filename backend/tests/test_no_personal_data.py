"""Personal data lives only in the database (Settings, Experience). Templates, template configs
and source code must never contain it. The personal tokens are read from the style reference
(templates/reference/cv.tex, which holds example content), so this test itself names nobody."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (ROOT / "templates/reference/cv.tex").read_text()


def personal_tokens() -> set[str]:
    ref = REFERENCE
    tokens: set[str] = set()
    name = re.search(r"\\textcolor\{primaryColor\}\{([^}]+)\}", ref).group(1)
    tokens.add(name)
    tokens |= {part for part in name.split() if len(part) >= 4}
    tokens |= set(re.findall(r"mailto:([^}]+)\}", ref))
    tokens |= set(re.findall(r"\\faIcon\{phone\}\s*(\+?\d{6,})", ref))
    for url in re.findall(r"\\href\{(https?://[^}]+)\}", ref):
        tokens.add(url.rstrip("/").rsplit("/", 1)[-1])  # handles and credential ids
    # Employers: the 3rd argument of each \resumeSubheading in the experience section.
    experience = ref.split(r"\section{Professional Experience}")[1].split(r"\section{")[0]
    tokens |= set(re.findall(r"\\resumeSubheading\s*\{[^}]*\}\{[^}]*\}\s*\{([^}]+)\}", experience))
    tokens |= set(re.findall(r"\\resumeProjectHeading\s*\{\\textbf\{([^}]+)\}", ref))
    tokens |= {t.strip(",") for t in re.findall(r"``([^']+)''", ref)}  # product names
    tokens |= set(re.findall(r"ID: ([A-Z0-9]{8,})", ref))
    return {t for t in tokens if len(t) >= 4}


def scanned_files() -> list[Path]:
    files = [p for p in (ROOT / "templates").glob("*/*")
             if p.parent.name != "reference" and p.suffix in (".j2", ".yaml", ".yml")]
    for base, patterns in (("backend/app", ["**/*.py", "**/*.md", "**/*.json"]),
                           ("backend/scripts", ["*.py"]), ("backend/alembic", ["**/*.py"]),
                           ("frontend/src", ["**/*.ts", "**/*.tsx"])):
        for pattern in patterns:
            files += list((ROOT / base).glob(pattern))
    return [f for f in files if "__pycache__" not in f.parts]


def test_reference_yields_personal_tokens() -> None:
    tokens = personal_tokens()
    assert len(tokens) >= 8  # name, email, phone, handles, employers, projects, ids


def test_no_personal_data_in_templates_configs_or_source() -> None:
    patterns = {t: re.compile(rf"(?<![\w@.]){re.escape(t)}(?![\w@])", re.I)
                for t in personal_tokens()}
    offenders = []
    for path in scanned_files():
        text = path.read_text(errors="ignore")
        for token, pattern in patterns.items():
            if pattern.search(text):
                offenders.append(f"{path.relative_to(ROOT)}: {token!r}")
    assert not offenders, "Personal data found:\n" + "\n".join(offenders)
