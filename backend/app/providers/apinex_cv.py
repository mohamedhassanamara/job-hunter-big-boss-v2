"""Two-pass CV generator using APInex (free/minimax-m3.1-flash).

Pass 1 (Planner): Fast structural selection of roles, projects, and skills.
Pass 2 (Polisher): High-quality 2-sentence summary and lightly adapted bullet points.
"""

import json
import logging
import time
from typing import Any

from app.providers.apinex_client import DEFAULT_MODEL, APInexClient
from app.providers.apinex_models import reject_non_apinex
from app.providers.base import (
    CVGenerationFailed,
    CVPlan,
    CVPlanDraft,
    CVRequest,
    PlanBullet,
    PlanExtra,
    PlanEntry,
    PlanProject,
    PlanSkillGroup,
    SummaryDraft,
    SummarySentence,
    plan_from_draft,
)
from app.providers.gemini_generate import GenerationFailed
from app.services import cv_rules

log = logging.getLogger("jobhunter.apinex_cv")


class APInexCVGenerator:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: APInexClient | None = None,
    ):
        reject_non_apinex(model)
        self.model = model
        self.client = client or APInexClient(model=model)
        self.prompt_version = "cv_generate_2pass/v1"
        self.last_cost_usd: float | None = 0.0
        self.last_duration_ms: int | None = None

    def generate(self, request: CVRequest) -> CVPlan:
        started = time.monotonic()
        try:
            planner_selection = self._run_pass1_planner(request)
            plan_draft = self._run_pass2_polisher(request, planner_selection)
            self.last_duration_ms = int((time.monotonic() - started) * 1000)
            return plan_from_draft(plan_draft)
        except Exception as exc:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)
            if isinstance(exc, CVGenerationFailed):
                raise
            log.exception("APInex 2-pass CV generation failed: %s", exc)
            raise GenerationFailed(f"CV generation failed on {self.model}: {exc}") from exc

    def _run_pass1_planner(self, request: CVRequest) -> dict[str, Any]:
        """Pass 1: Fast structural selection of roles, projects, and skills."""
        system_prompt = (
            "You are an expert CV structure and selection planner.\n"
            "Select the best roles, projects, and skills for the target job from the candidate's pool.\n\n"
            "CRITICAL RULES:\n"
            "1. \"selected_roles\": Include EVERY professional role from the pool (never drop a role: timeline continuity is mandatory). "
            "For each role, list the \"fact_indices\" (zero-based integers corresponding to the role's facts in the pool) of the ESSENTIAL facts only, ordered by relevance to the job: at most 5 for the current role, 4 for a role over a year, 3 for any other.\n"
            "2. \"selected_projects\": Select the 1 to 3 most relevant projects from the pool (if the pool contains projects, select at least 1). For each, list 2 to 4 \"fact_indices\".\n"
            "3. \"selected_skills\": Select up to 4 skill groups from the pool that best match the job. Under each group, select up to 8 skills copied VERBATIM from the pool's skills list.\n"
            "4. \"ratings\": rate how relevant to THIS job every OTHER item is, 0 (irrelevant) to 10 (as relevant as an essential): every role fact you did not list in fact_indices, every project you did not select (\"fact_index\": null) and every fact of a selected project you did not list. Rate honestly; a rating never changes the text.\n\n"
            "Return valid JSON matching this exact structure:\n"
            "{\n"
            "  \"selected_roles\": [\n"
            "    {\"id\": <role_id>, \"fact_indices\": [0, 1, 2, 3]}\n"
            "  ],\n"
            "  \"selected_projects\": [\n"
            "    {\"id\": <project_id>, \"fact_indices\": [0, 1, 2]}\n"
            "  ],\n"
            "  \"selected_skills\": [\n"
            "    {\"category\": \"<group_title>\", \"skills\": [\"<skill1>\", \"<skill2>\"]}\n"
            "  ],\n"
            "  \"ratings\": [\n"
            "    {\"kind\": \"role\" or \"project\", \"id\": <item_id>, \"fact_index\": <int or null>, \"relevance\": 0-10}\n"
            "  ]\n"
            "}"
        )

        pool_roles = request.pool.get("roles", [])
        pool_projects = request.pool.get("projects", [])
        pool_skills = request.pool.get("skill_groups", [])

        user_prompt = (
            f"TARGET JOB:\n{json.dumps(request.job, ensure_ascii=False, indent=1)}\n\n"
            f"EMPHASIS FOR THIS TRACK:\n{json.dumps(request.emphasis, ensure_ascii=False)}\n\n"
            f"RAW EXPERIENCE POOL:\n"
            f"Roles: {json.dumps(pool_roles, ensure_ascii=False, indent=1)}\n"
            f"Projects: {json.dumps(pool_projects, ensure_ascii=False, indent=1)}\n"
            f"Skill Groups: {json.dumps(pool_skills, ensure_ascii=False, indent=1)}\n"
        )

        res = self.client.complete_sync(system_prompt, user_prompt, model=self.model)

        # Normalize and ensure timeline continuity
        selected_roles = res.get("selected_roles") or []
        role_map = {r.get("id"): r for r in selected_roles if isinstance(r, dict)}
        normalized_roles = []
        for pool_role in pool_roles:
            rid = pool_role.get("id")
            facts = pool_role.get("facts", {})
            max_idx = len(facts)
            indices = []
            if rid in role_map and isinstance(role_map[rid].get("fact_indices"), list):
                indices = [int(i) for i in role_map[rid]["fact_indices"] if isinstance(i, (int, str)) and str(i).isdigit() and int(i) < max_idx]
            indices = list(dict.fromkeys(indices))
            if not indices and max_idx:  # a role is never empty: its first fact
                indices = [0]
            normalized_roles.append({"id": rid, "fact_indices": indices})

        selected_projects = res.get("selected_projects") or []
        proj_pool_map = {p.get("id"): p for p in pool_projects}
        normalized_projects = []
        for p in selected_projects:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if pid in proj_pool_map:
                facts = proj_pool_map[pid].get("facts", {})
                indices = [int(i) for i in p.get("fact_indices", []) if isinstance(i, (int, str)) and str(i).isdigit() and int(i) < len(facts)]
                if len(indices) >= 2:
                    normalized_projects.append({"id": pid, "fact_indices": indices[:4]})
        normalized_projects = normalized_projects[:3]

        selected_skills = res.get("selected_skills") or []
        skill_pool_map = {s.get("category", "").lower(): s for s in pool_skills}
        normalized_skills = []
        for sg in selected_skills:
            if not isinstance(sg, dict):
                continue
            cat = sg.get("category", "")
            match = skill_pool_map.get(cat.lower())
            if match:
                valid_items = [item for item in sg.get("skills", []) if item in match.get("skills", [])]
                normalized_skills.append({"id": match["id"], "category": match["category"], "skills": valid_items[:8]})

        return {
            "selected_roles": normalized_roles,
            "selected_projects": normalized_projects,
            "selected_skills": normalized_skills[:4],
            "extras": self._extras(res.get("ratings"), pool_roles, pool_projects,
                                   normalized_roles, normalized_projects),
        }

    @staticmethod
    def _extras(ratings: Any, pool_roles: list[dict[str, Any]],
                pool_projects: list[dict[str, Any]], roles: list[dict[str, Any]],
                projects: list[dict[str, Any]]) -> list[PlanExtra]:
        """Every pool bullet and project the plan does not use, with the model's 0-10 rating
        (0 when it didn't rate one: it is tried last). Only real ids and fact indices."""
        rated: dict[tuple[str, int, int | None], int] = {}
        for r in ratings if isinstance(ratings, list) else []:
            try:
                kind, rid = str(r["kind"]), int(r["id"])
                idx = None if r.get("fact_index") is None else int(r["fact_index"])
                rated[(kind, rid, idx)] = max(0, min(10, int(round(float(r["relevance"])))))
            except (KeyError, TypeError, ValueError):
                continue
        used_roles = {r["id"]: set(r["fact_indices"]) for r in roles}
        used_projects = {p["id"]: set(p["fact_indices"]) for p in projects}
        extras: list[PlanExtra] = []
        for role in pool_roles:
            for k in sorted(int(k) for k in role.get("facts", {}) if str(k).isdigit()):
                if k not in used_roles.get(role["id"], set()):
                    extras.append(PlanExtra(kind="role", item_id=role["id"], source_index=k,
                                            relevance=rated.get(("role", role["id"], k), 0)))
        for proj in pool_projects:
            pid = proj["id"]
            if pid not in used_projects:
                extras.append(PlanExtra(kind="project", item_id=pid, source_index=None,
                                        relevance=rated.get(("project", pid, None), 0)))
                continue
            for k in sorted(int(k) for k in proj.get("facts", {}) if str(k).isdigit()):
                if k not in used_projects[pid]:
                    extras.append(PlanExtra(kind="project", item_id=pid, source_index=k,
                                            relevance=rated.get(("project", pid, k), 0)))
        return extras

    def _run_pass2_polisher(self, request: CVRequest, planner: dict[str, Any]) -> CVPlanDraft:
        """Pass 2: Generate polished summary and lightly adapt bullet points."""
        pool_roles = {r["id"]: r for r in request.pool.get("roles", [])}
        pool_projects = {p["id"]: p for p in request.pool.get("projects", [])}
        banned_phrases = cv_rules.banned(cv_rules.DEFAULT_STRUCTURE)
        banned_str = "; ".join(banned_phrases)

        # Assemble selected facts for prompt
        polisher_input = {
            "roles": [],
            "projects": [],
            "skills": planner["selected_skills"],
        }
        for r in planner["selected_roles"]:
            rid = r["id"]
            if rid in pool_roles:
                p_role = pool_roles[rid]
                facts = p_role.get("facts", {})
                polisher_input["roles"].append({
                    "id": rid,
                    "title": p_role.get("title"),
                    "org": p_role.get("org"),
                    "facts": {str(i): facts[str(i)] for i in r["fact_indices"] if str(i) in facts},
                })
        for p in planner["selected_projects"]:
            pid = p["id"]
            if pid in pool_projects:
                p_proj = pool_projects[pid]
                facts = p_proj.get("facts", {})
                polisher_input["projects"].append({
                    "id": pid,
                    "title": p_proj.get("title"),
                    "tags": p_proj.get("tags", []),
                    "facts": {str(i): facts[str(i)] for i in p["fact_indices"] if str(i) in facts},
                })

        system_prompt = (
            "You are an expert CV copywriter and polisher.\n"
            "Produce the final JSON content for the tailored CV adhering strictly to these rules:\n\n"
            "1. SUMMARY (summary_sentences):\n"
            "   - Exactly 2 complete sentences, totaling ~45-48 words.\n"
            "   - Sentence 1: state who the candidate is, aligned to the target job track, with total professional years ONLY from FACTS (e.g. \"3 years of software engineering experience\").\n"
            "   - Sentence 2: describe concrete systems built from the pool items. Must have a grammatical subject without \"I\" (e.g. \"Recent work includes...\", \"Projects include...\"). Never start with bare verbs like \"Built...\" or \"Delivered...\".\n"
            f"   - ZERO use of banned phrases: {banned_str}.\n"
            "   - No numbers repeated from the bullets, no certifications, no tool enumerations.\n"
            "   - Each sentence must cite the pool item IDs it is based on in \"citations\".\n"
            "   - Provide \"summary_short_sentences\": 1 sentence, ~20 words, also cited.\n\n"
            "2. BULLETS (roles & projects):\n"
            "   - Lightly adapt each bullet for the target job: strong action verbs, impact-driven, concise phrasing.\n"
            "   - HARD GROUNDING: Length must stay within ±15% of the original fact. Keep ALL numbers, tools, and named products from the original fact. Never invent tools or numbers.\n"
            "   - Each bullet must include: source_index (int), text (str), priority (int, 1 = most relevant), strength (int, 1-5; 5=impact/metrics, 3=built system, 1=generic).\n"
            "   - \"relevance\" (int 1-10) for every role and project.\n"
            "   - \"stack\": up to 5 relevant tags for each project.\n\n"
            "Return valid JSON matching this schema:\n"
            "{\n"
            "  \"summary_sentences\": [{\"text\": \"...\", \"citations\": [...]}, {\"text\": \"...\", \"citations\": [...]}],\n"
            "  \"summary_short_sentences\": [{\"text\": \"...\", \"citations\": [...]}],\n"
            "  \"roles\": [\n"
            "    {\"item_id\": <id>, \"relevance\": 10, \"bullets\": [{\"source_index\": 0, \"text\": \"...\", \"priority\": 1, \"strength\": 5}]}\n"
            "  ],\n"
            "  \"projects\": [\n"
            "    {\"item_id\": <id>, \"relevance\": 8, \"stack\": [...], \"bullets\": [{\"source_index\": 0, \"text\": \"...\", \"priority\": 1, \"strength\": 5}]}\n"
            "  ],\n"
            "  \"skills\": [{\"item_id\": <id>, \"items\": [...]}]\n"
            "}"
        )

        user_prompt = (
            f"TARGET JOB:\n{json.dumps(request.job, ensure_ascii=False, indent=1)}\n\n"
            f"FACTS (allowed years claims):\n{json.dumps(request.facts, ensure_ascii=False)}\n\n"
            f"WRITING GUIDE:\n{request.guide}\n\n"
            f"SELECTED EXPERIENCE TO POLISH:\n{json.dumps(polisher_input, ensure_ascii=False, indent=1)}\n"
        )

        res = self.client.complete_sync(system_prompt, user_prompt, model=self.model)

        # Assemble into CVPlanDraft
        summary_sentences = [
            SummarySentence(text=s.get("text", "").strip(), citations=s.get("citations", []))
            for s in res.get("summary_sentences", []) if isinstance(s, dict) and s.get("text")
        ]
        short_sentences = [
            SummarySentence(text=s.get("text", "").strip(), citations=s.get("citations", []))
            for s in res.get("summary_short_sentences", []) if isinstance(s, dict) and s.get("text")
        ]
        # No summary is left empty-handed here and never replaced by a snippet: the caller
        # (cv_service.ground_summary) asks once more, then fails with a message and Retry.
        if not short_sentences:
            short_sentences = summary_sentences[:1]

        roles_out = []
        res_roles_map = {r.get("item_id"): r for r in res.get("roles", []) if isinstance(r, dict)}
        for p_role in planner["selected_roles"]:
            rid = p_role["id"]
            orig_role = pool_roles.get(rid, {})
            orig_facts = orig_role.get("facts", {})
            r_entry = res_roles_map.get(rid, {})
            relevance = max(1, min(10, int(r_entry.get("relevance", 9))))
            bullets_out = []
            seen_indices = set()
            for b in r_entry.get("bullets", []):
                if not isinstance(b, dict):
                    continue
                s_idx = b.get("source_index")
                if s_idx is not None and str(s_idx) in orig_facts:
                    text = b.get("text") or orig_facts[str(s_idx)]
                    bullets_out.append(PlanBullet(
                        source_index=int(s_idx),
                        text=text.strip(),
                        priority=int(b.get("priority", len(bullets_out) + 1)),
                        strength=int(b.get("strength", 3)),
                    ))
                    seen_indices.add(int(s_idx))
            # Fallback for any unpolished facts
            for s_idx in p_role["fact_indices"]:
                if s_idx not in seen_indices and str(s_idx) in orig_facts:
                    bullets_out.append(PlanBullet(
                        source_index=s_idx,
                        text=orig_facts[str(s_idx)],
                        priority=len(bullets_out) + 1,
                        strength=3,
                    ))
            roles_out.append(PlanEntry(item_id=rid, relevance=relevance, bullets=bullets_out))

        projects_out = []
        res_proj_map = {p.get("item_id"): p for p in res.get("projects", []) if isinstance(p, dict)}
        for p_proj in planner["selected_projects"]:
            pid = p_proj["id"]
            orig_proj = pool_projects.get(pid, {})
            orig_facts = orig_proj.get("facts", {})
            p_entry = res_proj_map.get(pid, {})
            relevance = max(1, min(10, int(p_entry.get("relevance", 8))))
            stack = p_entry.get("stack") or orig_proj.get("tags", [])[:5]
            bullets_out = []
            seen_indices = set()
            for b in p_entry.get("bullets", []):
                if not isinstance(b, dict):
                    continue
                s_idx = b.get("source_index")
                if s_idx is not None and str(s_idx) in orig_facts:
                    text = b.get("text") or orig_facts[str(s_idx)]
                    bullets_out.append(PlanBullet(
                        source_index=int(s_idx),
                        text=text.strip(),
                        priority=int(b.get("priority", len(bullets_out) + 1)),
                        strength=int(b.get("strength", 5)),
                    ))
                    seen_indices.add(int(s_idx))
            for s_idx in p_proj["fact_indices"]:
                if s_idx not in seen_indices and str(s_idx) in orig_facts:
                    bullets_out.append(PlanBullet(
                        source_index=s_idx,
                        text=orig_facts[str(s_idx)],
                        priority=len(bullets_out) + 1,
                        strength=5,
                    ))
            projects_out.append(PlanProject(item_id=pid, relevance=relevance, stack=stack, bullets=bullets_out))

        skills_out = []
        for sg in planner["selected_skills"]:
            skills_out.append(PlanSkillGroup(item_id=sg["id"], items=sg["skills"]))

        cert_ids = [c["id"] for c in request.pool.get("certifications", [])]
        edu_ids = [e["id"] for e in request.pool.get("education", [])]

        return CVPlanDraft(
            summary_sentences=summary_sentences,
            summary_short_sentences=short_sentences,
            skills=skills_out,
            roles=roles_out,
            projects=projects_out,
            certification_ids=cert_ids,
            education_ids=edu_ids,
            volunteering=[],
            extras=planner.get("extras", []),
        )

    def generate_summary(
        self, request: CVRequest, feedback: str, current: str = "", user_feedback: str = ""
    ) -> SummaryDraft:
        """Retry / revise summary on the APInex model."""
        banned_phrases = cv_rules.banned(cv_rules.DEFAULT_STRUCTURE)
        system_prompt = (
            "Rewrite ONLY the CV summary for the target job adhering to these rules:\n"
            "1. Exactly 2 complete sentences, totaling ~45-48 words.\n"
            "2. Sentence 1: professional role + professional track years strictly using allowed years from FACTS.\n"
            "3. Sentence 2: concrete systems built from the cited pool items. Must have a grammatical subject without \"I\" (e.g. \"Recent work includes...\"). Never start with bare verbs like \"Built...\".\n"
            f"4. Zero banned phrases: {'; '.join(banned_phrases)}.\n"
            "5. Cite the pool item IDs in \"citations\".\n"
            "6. Provide \"summary_short_sentences\" (1 sentence, ~20 words, cited).\n\n"
            "Return JSON matching: {\"summary_sentences\": [{\"text\": \"...\", \"citations\": [...]}], \"summary_short_sentences\": [{\"text\": \"...\", \"citations\": [...]}]}"
        )
        user_prompt = (
            (f"CURRENT SUMMARY:\n{current}\n\n" if current else "")
            + (f"FEEDBACK:\n{user_feedback}\n\n" if user_feedback else "")
            + (f"CHECK PROBLEMS TO FIX:\n{feedback}\n\n" if feedback else "")
            + f"TARGET JOB:\n{json.dumps(request.job, ensure_ascii=False)}\n\n"
            f"FACTS:\n{json.dumps(request.facts, ensure_ascii=False)}\n\n"
            f"WRITING GUIDE:\n{request.guide}\n"
        )
        try:
            res = self.client.complete_sync(system_prompt, user_prompt, model=self.model)
        except Exception as exc:
            raise GenerationFailed(f"Summary generation failed on {self.model}: {exc}") from exc
        sentences = [
            SummarySentence(text=s.get("text", "").strip(), citations=s.get("citations", []))
            for s in res.get("summary_sentences", []) if isinstance(s, dict) and s.get("text")
        ]
        short = [
            SummarySentence(text=s.get("text", "").strip(), citations=s.get("citations", []))
            for s in res.get("summary_short_sentences", []) if isinstance(s, dict) and s.get("text")
        ]
        if not sentences:
            raise GenerationFailed(
                f"{self.model} returned no summary. Retry, or generate with Claude.")
        if not short:
            short = sentences[:1]
        return SummaryDraft(summary_sentences=sentences, summary_short_sentences=short)
