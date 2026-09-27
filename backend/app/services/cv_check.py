"""No-fabrication checks on a CV plan, in code. Violations are stored on the CV version and shown
in CV Studio; the structural ones are also repaired (unknown ids dropped, omitted roles restored).

- every referenced item id exists (with the right kind) and every bullet index is a real fact
- every number in a reworded bullet appears exactly in its source fact
- every skill shown exists in the pool (skill groups or item tags)
- tech-looking words in bullets/summary that appear nowhere in the pool are flagged
- every role is present with at least one bullet (never a gap in the timeline)
"""

import re
from typing import Any

from app.providers.base import CVPlan, PlanBullet, PlanEntry
from app.services.cv_pool import Pool, norm

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*(?:\s?%|\+|[kKmM]\b|x\b)?")
# Tech-looking tokens: acronyms and mixed-case words (AWS, PySpark, GoRouter, YOLOv8, C#)...
_TECHY = re.compile(r"(?<![\w-])(?:[A-Z]{2,}[a-z0-9]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]*|"
                    r"[A-Za-z]+\d+[A-Za-z0-9]*|[A-Za-z]+#|[A-Za-z]+\+\+)(?![\w-])")
# ...plus well-known tools written in plain lowercase or capitalised.
_TOOLS = {
    "kubernetes", "docker", "terraform", "react", "angular", "vue", "django", "flask", "spring",
    "kafka", "spark", "hadoop", "airflow", "dbt", "snowflake", "bigquery", "redshift",
    "databricks", "tableau", "pytorch", "tensorflow", "keras", "pandas", "numpy", "scala",
    "golang", "rust", "kotlin", "swift", "java", "javascript", "typescript", "python",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "azure", "gcp",
    "aws", "flutter", "dart", "fastapi", "graphql", "jenkins", "ansible", "langchain",
    "llamaindex", "huggingface", "mlflow", "kubeflow", "sagemaker", "firebase", "supabase",
}
_NOT_TOOLS = {"i", "ai", "api", "apis", "ui", "ux", "it", "ok", "etl", "elt", "ci", "cd"}


def numbers(text: str) -> list[str]:
    return [re.sub(r"\s", "", n) for n in _NUMBER.findall(text)]


def violation(kind: str, message: str, where: str, severity: str = "warning") -> dict[str, str]:
    return {"type": kind, "severity": severity, "message": message, "where": where}


def check_bullet(bullet: PlanBullet, source: str, where: str) -> list[dict[str, str]]:
    source_numbers = {n.lower() for n in numbers(source)}
    source_digits = {re.sub(r"[^\d]", "", n) for n in source_numbers}
    out = []
    for n in numbers(bullet.text):
        if n.lower() not in source_numbers and re.sub(r"[^\d]", "", n) not in source_digits:
            out.append(violation("number", f"“{n}” isn't in the source fact", where, "error"))
    return out


def new_tools(text: str, vocabulary: set[str]) -> list[str]:
    candidates = set(_TECHY.findall(text))
    candidates |= {w for w in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]*", text)
                   if w.lower() in _TOOLS}
    return sorted(c for c in candidates
                  if norm(c) not in vocabulary and c.lower() not in _NOT_TOOLS and norm(c))


def check_plan(plan: CVPlan, pool: Pool) -> tuple[CVPlan, list[dict[str, Any]]]:
    """Returns the repaired plan and every violation found."""
    issues: list[dict[str, Any]] = []
    vocab = pool.vocabulary()

    def entries(items: list[PlanEntry], kind: str, label: str) -> list[PlanEntry]:
        kept = []
        for e in items:
            item = pool.get(e.item_id, kind)
            if item is None:
                issues.append(violation("unknown_item", f"Unknown {label} id {e.item_id}: dropped",
                                        label, "error"))
                continue
            facts = pool.facts(item)
            good = []
            for b in e.bullets:
                where = f"{item.title}: bullet {b.source_index}"
                if not 0 <= b.source_index < len(facts):
                    issues.append(violation("unknown_fact", "Bullet doesn't match a source fact:"
                                            " dropped", where, "error"))
                    continue
                issues.extend(check_bullet(b, facts[b.source_index], where))
                if tools := new_tools(b.text, vocab):
                    issues.append(violation("new_tool", f"Not in your experience: "
                                            f"{', '.join(tools)}", where))
                good.append(b)
            kept.append(e.model_copy(update={"bullets": sorted(good, key=lambda x: x.priority)}))
        return kept

    roles = entries(plan.roles, "job", "role")
    present = {e.item_id for e in roles}
    for item in pool.of("job"):  # never a gap in the timeline
        if item.id not in present:
            facts = pool.facts(item)
            roles.append(PlanEntry(item_id=item.id, relevance=1, bullets=[
                PlanBullet(source_index=n, text=f, priority=n + 1) for n, f in enumerate(facts)]))
            issues.append(violation("restored_role", "The generator left this role out: "
                                    "restored with its original bullets", item.title))
    for e in roles:
        item = pool.get(e.item_id)
        if item is not None and not e.bullets and pool.facts(item):
            e.bullets.append(PlanBullet(source_index=0, text=pool.facts(item)[0], priority=1))
    order = {item.id: n for n, item in enumerate(pool.of("job"))}
    roles.sort(key=lambda e: order.get(e.item_id, 999))  # timeline order, not relevance

    projects = [p for p in entries(plan.projects, "project", "project")]
    for p in projects:
        item = pool.get(p.item_id)
        tags = {norm(t) for t in (item.tags if item else [])}
        extra = [s for s in p.stack if norm(s) not in tags and norm(s) not in pool.skill_terms()]
        if extra:
            issues.append(violation("new_skill", f"Stack not in this project's tags: "
                                    f"{', '.join(extra)}", item.title if item else "project"))

    skills = []
    terms = pool.skill_terms()
    for group in plan.skills:
        item = pool.get(group.item_id, "skill")
        if item is None:
            issues.append(violation("unknown_item", f"Unknown skill group {group.item_id}: dropped",
                                    "skills", "error"))
            continue
        unknown = [s for s in group.items if norm(s) not in terms]
        if unknown:
            issues.append(violation("new_skill", f"Not in your skills: {', '.join(unknown)} "
                                    "(removed)", item.title, "error"))
        skills.append(group.model_copy(update={
            "items": [s for s in group.items if norm(s) in terms]}))

    for text, where in ((plan.summary, "summary"), (plan.summary_short, "short summary")):
        pool_numbers = {n.lower() for n in numbers(pool.all_text())}
        for n in numbers(text):
            if n.lower() not in pool_numbers:
                issues.append(violation("number", f"“{n}” isn't anywhere in your experience",
                                        where, "error"))
        if tools := new_tools(text, vocab):
            issues.append(violation("new_tool", f"Not in your experience: {', '.join(tools)}",
                                    where))

    certs = [i for i in plan.certification_ids if pool.get(i, "certification")]
    education = [i for i in plan.education_ids if pool.get(i, "education")]
    if not education and pool.of("education"):
        education = [i.id for i in pool.of("education")]  # never hide education silently
    volunteering = entries(plan.volunteering, "volunteering", "volunteering")
    repaired = plan.model_copy(update={
        "roles": roles, "projects": projects, "skills": skills, "certification_ids": certs,
        "education_ids": education, "volunteering": volunteering,
    })
    return repaired, issues
