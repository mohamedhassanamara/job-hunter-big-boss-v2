"""Versioned prompt files (app/prompts/<name>.md).

Format: YAML-ish front matter with `version: N`, then `## system` and `## user` sections. The user
section is a string.Template ($placeholders). Any change to the body must bump `version`, and
prompts/versions.json must record the new body hash (a unit test enforces it).
"""

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    system: str
    user: Template
    body_hash: str

    @property
    def version_id(self) -> str:
        return f"{self.name}/v{self.version}"

    def render(self, **values: object) -> str:
        return self.user.substitute({k: str(v) for k, v in values.items()})


def body_hash(body: str) -> str:
    return hashlib.sha256(body.strip().encode()).hexdigest()[:16]


@lru_cache
def load_prompt(name: str) -> Prompt:
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    match = _FRONT.match(text)
    if not match:
        raise ValueError(f"{name}.md: missing front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    version = int(meta["version"].strip())
    body = match.group(2)
    sections = re.split(r"^## (system|user)\s*$", body, flags=re.M)
    parts = {sections[i]: sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    return Prompt(
        name=name,
        version=version,
        system=parts["system"],
        user=Template(parts["user"]),
        body_hash=body_hash(body),
    )


def registered_hashes() -> dict[str, dict[str, str]]:
    return json.loads((PROMPTS_DIR / "versions.json").read_text())
