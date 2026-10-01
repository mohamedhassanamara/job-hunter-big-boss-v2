"""Sample data lives ONLY in the tour sandbox (data/demo.db). The real DB gets no fake data.

    python -m app.seed.seed               # rebuild the tour sandbox from fixtures
    python -m app.seed.seed --defaults    # real DB: add profile + settings if missing
    python -m app.seed.seed --erase-real  # real DB: erase everything but the defaults
"""

import argparse
import unicodedata
import zlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, delete, update
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401
from app.models import (
    Application,
    ApplicationEvent,
    ApplicationResponse,
    AppSetting,
    Company,
    Contact,
    CVVersion,
    ExperienceItem,
    FitScore,
    Interview,
    Job,
    OutreachDraft,
    SearchProfile,
    SendLog,
    SendQueue,
    SendQueueItem,
    SourceRun,
)
from app.models.base import utcnow
from app.models.enums import (
    DISCOVERY_SOURCES,
    ApplyMethod,
    CVStatus,
    DraftStatus,
    EventKind,
    InterviewOutcome,
    InterviewType,
    QueueItemStatus,
    QueueStatus,
    ResponseKind,
    RunStatus,
    Source,
    Stage,
)
from app.providers.mock import MockEmailDrafter
from app.providers.registry import cv_generator
from app.seed import fixtures as fx
from app.services.contacts import normalize_person, rank
from app.services.contacts import report as contacts_report
from app.services.cv_build import build_document, initial_state
from app.services.cv_check import check_plan
from app.services.cv_pool import load_pool
from app.services.cv_service import build_request
from app.services.dedupe import dedupe_key, normalize_company
from app.services.pipeline import stage_label
from app.services.roles import match_track, tracks_of, with_suggested_variants

SOURCE_NAMES = {
    "adzuna": "Adzuna",
    "remotive": "Remotive",
    "arbeitnow": "Arbeitnow",
    "boards": "Company job boards",
    "bayt": "Bayt",
    "wttj": "Welcome to the Jungle",
}
FORWARD = [Stage.new, Stage.shortlisted, Stage.cv_ready, Stage.ready, Stage.done, Stage.interview]


def _clear(session: Session) -> None:
    # application.applied_cv_version_id / applied_cover_letter_id ↔ their application_id is a
    # cycle: break it first, then children go before parents.
    session.exec(update(Application).values(applied_cv_version_id=None,  # type: ignore[call-overload]
                                            applied_cover_letter_id=None))  # type: ignore[call-overload]
    session.flush()
    for table in reversed(SQLModel.metadata.sorted_tables):
        session.exec(delete(table))  # type: ignore[call-overload]


def _stage_path(stage: Stage, close_reason: str | None) -> list[Stage]:
    if stage == Stage.closed:
        if close_reason == "dismissed":
            return [Stage.new, Stage.closed]
        return [*FORWARD[:5], Stage.closed]
    return FORWARD[: FORWARD.index(stage) + 1]


def seed(engine: Engine, *, empty: bool = False) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as s:
        _clear(s)

        tracks = with_suggested_variants(fx.SEARCH_PROFILE["tracks"])
        profile = SearchProfile(**{**fx.SEARCH_PROFILE, "tracks": tracks})
        s.add(profile)
        for key, value in fx.SETTINGS.items():
            if key == "profile":  # the sandbox gets a fictional candidate so CVs have a header
                value = {**value, **fx.SANDBOX_CANDIDATE}
            s.add(AppSetting(key=key, value=value))
        queue = SendQueue(status=QueueStatus.idle if empty else QueueStatus.paused)
        s.add(queue)
        s.flush()

        if empty:
            s.commit()
            return

        # Discovery runs: today (07:00-ish) and yesterday for every source.
        runs: dict[str, SourceRun] = {}
        for day_offset in (1, 0):
            for i, src in enumerate(DISCOVERY_SOURCES):
                started = (now - timedelta(days=day_offset)).replace(hour=5, minute=i * 2)
                failed = day_offset == 0 and src == Source.wttj
                run = SourceRun(
                    source=src,
                    profile_id=profile.id,
                    started_at=started,
                    finished_at=started + timedelta(seconds=40 + i * 7),
                    status=RunStatus.partial if failed else RunStatus.success,
                    fetched_count=[34, 12, 21, 18, 27, 40][i],
                    kept_count=[9, 3, 4, 6, 5, 7][i],
                    filtered_count=[25, 9, 17, 12, 22, 33][i],
                    new_count=[3, 2, 2, 1, 2, 3][i] if day_offset == 0 else [4, 1, 3, 2, 1, 2][i],
                    duplicate_count=[1, 0, 1, 0, 0, 1][i],
                    details={
                        "requests": [12, 1, 1, 1, 10, 8][i],
                        "reasons": {
                            reason: n
                            for reason, n in {
                                "title_no_role_match": [18, 7, 11, 9, 20, 30][i],
                                "location_outside:DE": [0, 0, 6, 0, 0, 0][i],
                                "title_excluded:intern": [7, 2, 0, 3, 2, 3][i],
                            }.items()
                            if n
                        },
                    },
                    error="Rate limited after page 3 (18 of ~30 listings fetched)"
                    if failed
                    else None,
                )
                s.add(run)
                runs[src] = run
        s.flush()

        companies: dict[str, Company] = {}
        for key, c in fx.COMPANIES.items():
            company = Company(
                name=c["name"],
                normalized_name=normalize_company(c["name"]),
                domain=c["domain"],
                website=f"https://{c['domain']}",
            )
            s.add(company)
            companies[key] = company
        s.flush()

        contacts: dict[str, list[Contact]] = {}
        for key, people in fx.CONTACTS.items():
            contacts[key] = []
            for full_name, title, source in people:
                first, last = full_name.split(" ", 1)
                slug = unicodedata.normalize("NFKD", f"{first}.{last}".lower().replace(" ", ""))
                slug = slug.encode("ascii", "ignore").decode()
                email = f"{slug}@{fx.COMPANIES[key]['domain']}"
                contact = Contact(
                    company_id=companies[key].id,
                    full_name=full_name,
                    first_name=first,
                    last_name=last,
                    normalized_name=normalize_person(full_name),
                    title=title,
                    role_rank=rank(title, fx.SETTINGS["contacts"]["role_ranking"])[0],
                    email=email,
                    email_normalized=email.lower(),
                    linkedin_url=f"https://linkedin.com/in/{slug.replace('.', '-')}",
                    source=source,
                    imported_batch="apollo-2026-09-01.csv" if source == "apollo_dump" else None,
                )
                s.add(contact)
                contacts[key].append(contact)
        s.flush()

        for i, item in enumerate(fx.EXPERIENCE):
            s.add(
                ExperienceItem(
                    **{
                        **item,
                        "start_date": date.fromisoformat(item["start_date"])
                        if item["start_date"]
                        else None,
                        "end_date": date.fromisoformat(item["end_date"])
                        if item["end_date"]
                        else None,
                    },
                    position=i,
                )
            )
        s.flush()

        jobs: dict[str, Job] = {}
        apps: dict[str, Application] = {}
        for jf in fx.JOBS:
            company = companies[jf.company]
            posted = now - timedelta(days=jf.posted_days_ago)
            discovered = posted + timedelta(hours=2)
            job = Job(
                source=jf.source,
                external_id=f"{jf.source}-{zlib.crc32(jf.key.encode()) % 10_000_000}",
                source_run_id=runs[jf.source].id,
                url=f"https://example.com/{jf.source}/jobs/{jf.key}",
                title=jf.title,
                company_id=company.id,
                location=jf.location,
                country=jf.country,
                remote_type=jf.remote,
                description=fx.job_description(jf, company.name),
                salary_text=jf.salary,
                posted_at=posted,
                discovered_at=discovered,
                dedupe_key=dedupe_key(company.name, jf.title, jf.country),
                duplicate_of_id=jobs[jf.duplicate_of].id if jf.duplicate_of else None,
            )
            hit = match_track(jf.title, tracks_of(profile))
            if hit:
                job.matched_track, job.matched_role = hit
            s.add(job)
            s.flush()
            jobs[jf.key] = job
            s.add(sample_fit(jf, job, company.name, profile.id, discovered, s))

            contact = contacts[jf.company][jf.contact] if jf.contact is not None else None
            stage = Stage(jf.stage)
            stage_changed = min(now - timedelta(days=jf.days_in_stage), now)
            stage_changed = max(stage_changed, discovered + timedelta(hours=1))
            application = Application(
                job_id=job.id,
                stage=stage,
                route=jf.route,
                contact_id=contact.id if contact else None,
                contact_tier=jf.tier,
                close_reason=jf.close_reason,
                notes=jf.notes,
                stage_changed_at=stage_changed,
                applied_at=None,
                created_at=discovered,
                updated_at=stage_changed,
            )
            s.add(application)
            s.flush()
            apps[jf.key] = application

            # Timeline: discovered → each stage along the path, spread evenly in time.
            s.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind=EventKind.discovered,
                    message=f"Discovered on {SOURCE_NAMES[jf.source]}"
                    + (f" · fit {jf.score}" if not jf.duplicate_of else " · flagged as duplicate"),
                    at=discovered,
                )
            )
            if contact:
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.contact_resolved,
                        message=f"Contact found: {contact.full_name} ({contact.title})",
                        payload={"tier": jf.tier},
                        at=discovered + timedelta(minutes=8),
                    )
                )
            path = _stage_path(stage, jf.close_reason)
            steps = list(zip(path, path[1:], strict=False))
            for n, (src, dst) in enumerate(steps, start=1):
                at = discovered + (stage_changed - discovered) * (n / len(steps))
                if dst == Stage.done:
                    application.applied_at = at
                    if company.contacted_at is None:
                        company.contacted_at = at
                message = f"Moved to {stage_label(dst)}"
                if dst == Stage.closed:
                    message = (
                        "Dismissed"
                        if jf.close_reason == "dismissed"
                        else f"Closed ({(jf.close_reason or '').replace('_', ' ')})"
                    )
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.stage_change,
                        from_stage=src,
                        to_stage=dst,
                        message=message,
                        at=at,
                    )
                )
            if jf.notes:
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.note,
                        message="Note updated",
                        at=stage_changed + timedelta(hours=1),
                    )
                )
        s.flush()

        # CVs: every application past `shortlisted` has an approved CV; one shortlisted job
        # has a draft waiting for review; Lumière has a superseded v1.
        gen = cv_generator(mock=True)
        pool = load_pool(s)
        for key, application in apps.items():
            job = jobs[key]
            path = _stage_path(Stage(application.stage), application.close_reason)
            needs_approved = Stage.cv_ready in path
            needs_draft = key == "quartzo-llm"
            if not (needs_approved or needs_draft):
                continue
            # Sample CVs from the sandbox pool via the mock generator; PDFs compile on first view.
            plan, issues = check_plan(gen.generate(build_request(s, application, pool)), pool)
            content = build_document(plan, pool, initial_state(plan)).model_dump()
            plan_data = {"plan": plan.model_dump(), "fit": initial_state(plan).to_dict()}
            base_at = application.stage_changed_at - timedelta(hours=3)
            versions: list[tuple[int, CVStatus]] = []
            if key == "lumiere-mlops":
                versions = [(1, CVStatus.superseded), (2, CVStatus.approved)]
            elif needs_approved:
                versions = [(1, CVStatus.approved)]
            else:
                versions = [(1, CVStatus.draft)]
            for version, status in versions:
                s.add(
                    CVVersion(
                        application_id=application.id,
                        version=version,
                        content=content,
                        plan=plan_data,
                        violations=issues,
                        tex=None,
                        pdf_path=None,
                        page_count=None,
                        status=status,
                        generator_model="claude-sonnet-5 (mock)",
                        created_at=base_at + timedelta(minutes=version * 20),
                        updated_at=base_at + timedelta(minutes=version * 20),
                    )
                )
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.cv_generated,
                        message=f"CV v{version} generated",
                        at=base_at + timedelta(minutes=version * 20),
                    )
                )
                if status == CVStatus.approved:
                    s.add(
                        ApplicationEvent(
                            application_id=application.id,
                            kind=EventKind.cv_approved,
                            message=f"CV v{version} approved",
                            at=base_at + timedelta(minutes=version * 20 + 15),
                        )
                    )

        # Outreach drafts + queue.
        plan = [
            ("sierra-gcp", DraftStatus.draft, None),
            ("lumiere-mlops", DraftStatus.rejected, None),
            ("lumiere-mlops", DraftStatus.draft, None),
            ("pixelfarm-ai", DraftStatus.queued, QueueItemStatus.pending),
            ("kelpie-staff", DraftStatus.queued, QueueItemStatus.pending),
            ("marea-stream", DraftStatus.sent, QueueItemStatus.sent),
            ("tessera-applied", DraftStatus.sent, QueueItemStatus.sent),
        ]
        position = 0
        for key, status, item_status in plan:
            application = apps[key]
            job = jobs[key]
            contact = s.get(Contact, application.contact_id)
            assert contact is not None
            subject, body = MockEmailDrafter.sample(job.title, companies[fx_company(key)].name,
                                                    contact.full_name.split(" ")[0])
            created = application.stage_changed_at - timedelta(hours=1)
            draft = OutreachDraft(
                application_id=application.id,
                contact_id=contact.id,
                subject=subject,
                body=body,
                status=status,
                model="claude-haiku-4-5 (mock)",
                edited=key == "kelpie-staff",
                created_at=created,
                updated_at=created,
            )
            if status == DraftStatus.rejected:
                draft.subject = f"Quick question about the {job.title} role"
                draft.created_at = draft.updated_at = created - timedelta(hours=5)
            s.add(draft)
            s.flush()
            s.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind=EventKind.draft_created,
                    message=f"Email draft created for {contact.full_name}",
                    at=draft.created_at,
                )
            )
            if item_status is not None:
                position += 1
                pending = item_status == QueueItemStatus.pending
                sent_at = application.applied_at if not pending else None
                s.add(
                    SendQueueItem(
                        queue_id=queue.id,
                        draft_id=draft.id,
                        position=position,
                        status=item_status,
                        scheduled_at=None if pending else sent_at,
                        sent_at=sent_at,
                    )
                )
                if not pending:
                    s.add(
                        ApplicationEvent(
                            application_id=application.id,
                            kind=EventKind.sent,
                            message=f"Email sent to {contact.email}",
                            at=(sent_at or now) + timedelta(minutes=1),
                        )
                    )
        _seed_tracking(s, apps, now)
        # Both routes: the email to Marea went out, and you applied on their site too.
        marea = apps["marea-stream"]
        if marea.applied_at is not None:
            marea.web_applied_at = marea.applied_at + timedelta(days=1)
            marea.web_method = ApplyMethod.company_site
            s.add(marea)
        _seed_letters(s, apps)
        _seed_signals(s, apps)
        _seed_contact_alert(s, apps)
        _seed_linkedin(s, apps)
        _seed_get_contact(s, apps, jobs, now)
        # The tour can start the send queue: a test send to yourself already went through.
        s.add(SendLog(kind="test", to="you@example.com", subject="[TEST] sample", status="sent",
                      at=now - timedelta(days=2)))
        s.flush()
        s.add(AppSetting(key="contacts_last_match", value=contacts_report(s)))
        s.commit()


def _seed_get_contact(s: Session, apps: dict[str, Application], jobs: dict[str, Job],
                      now: datetime) -> None:
    """The Get contact step in the sandbox: contacts you found are verified; imported contacts
    on jobs past the CV are verified a few days ago (their emails are drafted); shortlisted ones
    wait to be verified; to_get jobs have nobody yet."""
    from app.models import Contact

    s.flush()
    for application in apps.values():
        if application.contact_id is None:
            continue
        contact = s.get(Contact, application.contact_id)
        if contact.source != "apollo_dump":
            contact.verified_at, contact.verified_how = now - timedelta(days=3), "entered"
        elif application.stage not in (Stage.new, Stage.shortlisted):
            contact.verified_at, contact.verified_how = now - timedelta(days=5), "still_there"
        s.add(contact)


def fx_score(key: str) -> int:
    return next((j.score for j in fx.JOBS if j.key == key), 0)


def _seed_signals(s: Session, apps: dict[str, Application]) -> None:
    """Verified sample signals for one company with a contact (the Signals tour and a
    signal-based email in the sandbox). Sample text only; the sandbox never fetches the web."""
    from app.models import CompanySignal, ResearchRun

    s.flush()
    app = next((a for a in apps.values() if a.contact_id and a.stage != Stage.closed), None)
    if app is None:
        return
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    run = ResearchRun(company_id=company.id, trigger="draft", status="done", pages=4,
                      signals_kept=3, finished_at=utcnow(),
                      calls=[{"model": "mock-research", "prompt_version": "research/mock",
                              "outcome": "ok", "duration_ms": 0}])
    s.add(run)
    s.flush()
    site = f"https://{company.normalized_name.replace(' ', '')}.example"
    for kind, fact, path, selected in [
        ("customer_result", f"A regional carrier cut its planning time by 30% with "
         f"{company.name}.", "/clients", True),
        ("technical", f"{company.name} runs its routing engine on its own models, trained "
         "in-house.", "/platform", True),
        ("launch", f"{company.name} launched a real-time routing engine in 2026.", "/blog/launch",
         False),
    ]:
        s.add(CompanySignal(company_id=company.id, research_run_id=run.id, kind=kind, fact=fact,
                            quote=fact, source_url=site + path, verified=True,
                            selected=selected))
    company.research_refreshed_at = utcnow()
    s.add(company)


def _seed_contact_alert(s: Session, apps: dict[str, Application]) -> None:
    """A sample news page saying one sample contact left, scanned by the real contact check (the
    "Contact may have left" warning in the tour). Not the signals company: its email stays
    approvable."""
    from app.models import CompanyPage, Contact
    from app.services import contact_check

    s.flush()
    with_contact = [a for a in apps.values() if a.contact_id and a.stage != Stage.closed]
    researched = {s.get(Job, a.job_id).company_id for a in with_contact[:1]}
    app = next((a for a in with_contact if s.get(Job, a.job_id).company_id not in researched),
               None)
    if app is None:
        return
    job = s.get(Job, app.job_id)
    company, contact = s.get(Company, job.company_id), s.get(Contact, app.contact_id)
    s.add(CompanyPage(company_id=company.id, kind="contact_news",
                      url="https://news.example/leadership-changes",
                      title=f"Leadership changes at {company.name}",
                      text=f"{contact.full_name} has left {company.name} after four years. "
                           f"{company.name} is hiring a replacement.",
                      page_date=utcnow()))
    s.flush()
    contact_check.scan(s, company.id, [contact])


def _seed_linkedin(s: Session, apps: dict[str, Application]) -> None:
    """The LinkedIn messages tour: on the first job past New, a hiring-team person with a
    drafted note (mock drafter) and an alumni contact already requested. Sample data only."""
    from app.models.enums import LinkedInGroup, LinkedInStatus
    from app.providers.mock import MockLinkedInDrafter
    from app.services import linkedin_track as lt

    s.flush()
    app = next((a for a in apps.values() if a.stage in (Stage.shortlisted, Stage.cv_ready)), None)
    if app is None:
        return
    hire = lt.add(s, app, full_name="Morgan Sample", title="Head of Data",
                  linkedin_url="https://www.linkedin.com/in/morgan-sample/",
                  hiring_team=True)
    alum = lt.add(s, app, full_name="Robin Example", title="Data Engineer",
                  linkedin_url="https://www.linkedin.com/in/robin-example/",
                  group=LinkedInGroup.alumni)
    s.flush()
    request, ctx = lt._request(s, hire, "note")
    hire.note = lt._draft(MockLinkedInDrafter(), request, ctx)
    request, ctx = lt._request(s, alum, "note")
    alum.note = lt._draft(MockLinkedInDrafter(), request, ctx)
    lt.set_status(s, alum, LinkedInStatus.sent)
    s.add_all([hire, alum])


def _seed_letters(s: Session, apps: dict[str, Application]) -> None:
    """A draft cover letter and two answered questions on the first web-apply job that is ready
    to apply (Cover letter and Questions tours). Written by the mock; the PDF compiles on first
    view."""
    from app.models import ApplicationAnswer, CoverLetter
    from app.providers.base import AnswersRequest
    from app.providers.mock import MockLetterDrafter
    from app.services import cover_letter as cl
    from app.services import letter_check as lc

    s.flush()
    ready = [a for a in apps.values() if a.route == "web_apply" and a.web_applied_at is None
             and Stage(a.stage) in (Stage.cv_ready, Stage.ready) and cl.approved_cv(s, a)]
    if not ready:
        return
    app = ready[0]
    cv = cl.approved_cv(s, app)
    job = s.get(Job, app.job_id)
    drafter, pool = MockLetterDrafter(), load_pool(s)
    language = cl.resolve_language(s, app, job)
    request = cl.build_request(s, app, cv, pool, language)
    salutation = cl.default_salutation(s, app, language)
    letter = CoverLetter(application_id=app.id, version=1, language=language,
                         content=cl.content_from_plan(drafter.draft_letter(request), salutation),
                         cv_version_id=cv.id, generator_model="claude-sonnet-5 (mock)",
                         prompt_version=drafter.prompt_version)
    s.add(letter)
    s.flush()
    letter.text = cl.plain_text(s, letter)
    letter.violations = cl.check(s, letter, pool)
    s.add(letter)
    s.add(ApplicationEvent(application_id=app.id, kind=EventKind.letter_generated,
                           message=f"Cover letter v1 ({language}) written",
                           at=app.stage_changed_at + timedelta(minutes=30)))
    question = "Why do you want to join us?"
    form_plan = drafter.draft_form(cl.build_request(s, app, cv, pool, language, "form", question,
                                                    800))
    form = CoverLetter(application_id=app.id, version=1, language=language, format="form",
                       question=question, char_limit=800,
                       content=cl.content_from_plan(form_plan, ""), cv_version_id=cv.id,
                       generator_model="claude-sonnet-5 (mock)",
                       prompt_version=drafter.prompt_version)
    s.add(form)
    s.flush()
    form.text = cl.plain_text(s, form)
    form.violations = cl.check(s, form, pool)
    s.add(form)
    # A Copilot conversation on the same job (sample answer; the tour never calls a model).
    from app.models import CopilotMessage, CopilotThread

    thread = CopilotThread(application_id=app.id, title=job.title)
    s.add(thread)
    s.flush()
    s.add(CopilotMessage(thread_id=thread.id, role="user",
                         content="What should I highlight in the interview?"))
    s.add(CopilotMessage(thread_id=thread.id, role="assistant", model="mock-copilot",
                         content=(f"For {job.title}: lead with the project closest to the "
                                  "listing, explain what it changed, and be ready to discuss "
                                  "the gaps the fit score lists.")))
    questions = [{"id": 1, "question": "Why do you want to join us?", "char_limit": 400},
                 {"id": 2, "question": "Describe a data pipeline you built.", "char_limit": None}]
    ctx = cl.context(s, app, language, pool)
    plan = drafter.answer(AnswersRequest(job=request.job, candidate=request.candidate,
                                         pool=request.pool, questions=questions))
    for q, draft in zip(questions, plan.answers, strict=True):
        text = " ".join(x.text for x in draft.sentences)
        s.add(ApplicationAnswer(
            application_id=app.id, question=q["question"], char_limit=q["char_limit"],
            answer=text, language=language, position=q["id"],
            generator_model="claude-sonnet-5 (mock)",
            plan={"sentences": [x.model_dump() for x in draft.sentences]},
            violations=lc.check_answer(draft.sentences, text, q["char_limit"], ctx)))


def _seed_tracking(s: Session, apps: dict[str, Application], now: datetime) -> None:
    """Applied details (locked CV), a reply, interviews: enough for the Applications tour."""
    for application in apps.values():
        if application.applied_at is None:
            continue
        cv = s.exec(select(CVVersion).where(CVVersion.application_id == application.id,
                                            CVVersion.status == CVStatus.approved)).first()
        if cv is not None:
            cv.locked_at = application.applied_at
            s.add(cv)
            application.applied_cv_version_id = cv.id
        application.applied_method = (
            ApplyMethod.email if application.route == "cold_email" else ApplyMethod.company_site)
        if application.applied_method != ApplyMethod.email:
            application.web_applied_at = application.applied_at
            application.web_method = application.applied_method
        s.add(application)

    tessera = apps["tessera-applied"]
    assert tessera.applied_at is not None
    replied = tessera.applied_at + timedelta(days=2)
    s.add(ApplicationResponse(application_id=tessera.id, kind=ResponseKind.positive,
                              received_at=replied, notes="Nadia proposed a first call."))
    s.add(Interview(application_id=tessera.id, round=1, type=InterviewType.hr,
                    scheduled_at=tessera.stage_changed_at, outcome=InterviewOutcome.passed,
                    notes="Intro call with Nadia."))
    s.add(Interview(application_id=tessera.id, round=2, type=InterviewType.technical,
                    scheduled_at=(now + timedelta(days=3)).replace(hour=10, minute=0, second=0,
                                                                   microsecond=0),
                    notes="Live coding plus system design."))
    veloce = apps["veloce-bi"]
    if veloce.applied_at is not None:
        s.add(ApplicationResponse(application_id=veloce.id, kind=ResponseKind.rejection,
                                  received_at=veloce.stage_changed_at,
                                  notes="Position filled internally."))
    for a, message, at in [
        (tessera, "Positive reply received", replied),
        (tessera, "Interview round 1 (hr) logged", tessera.stage_changed_at),
        (tessera, "Interview round 2 (technical) logged", tessera.stage_changed_at),
    ]:
        kind = EventKind.response if "reply" in message else EventKind.interview
        s.add(ApplicationEvent(application_id=a.id, kind=kind, message=message, at=at))


_KEY_TO_COMPANY = {j.key: j.company for j in fx.JOBS}


def sample_fit(jf, job: Job, company: str, profile_id: int | None, at: datetime, s: Session):  # noqa: ANN001, ANN201
    """A realistic scored fit for the tour sandbox: sub-scores with reasons and evidence quoted
    from the (fixture) listing, sample red flags, computed exactly like the real scorer."""
    from app.providers.base import FitAssessment, RedFlag, SubScore
    from app.services import fit as fitsvc
    from app.services.scoring import load_context

    ctx = load_context(s)
    base = round(jf.score / 10)
    text = job.description
    quote = f"comfort with {jf.stack[0]} and {jf.stack[1]}"
    remote_line = fx.REMOTE_LINE[jf.remote]

    def sub(score: int, reason: str, evidence: str) -> SubScore:
        return SubScore(score=max(0, min(10, score)), reason=reason, evidence=evidence)

    flags = []
    good_to_know = jf.extra.get("good_to_know", "")
    if "sponsor" in good_to_know:
        sentence = next(p for p in good_to_know.split(". ") if "sponsor" in p)
        flags.append(RedFlag(type="no_visa_sponsorship", text="No visa sponsorship",
                             evidence=sentence.rstrip(".")))
    if "fluen" in good_to_know.lower():
        sentence = next(p for p in good_to_know.split(". ") if "luen" in p)
        flags.append(RedFlag(type="language_required", text="Requires a language you don't have",
                             evidence=sentence.rstrip(".")))
    senior = any(w in jf.title.lower() for w in ("staff", "lead", "principal"))
    needs_language = "fluen" in good_to_know.lower()
    assessment = FitAssessment(
        role_match=sub(base + 1, "The responsibilities are core data/AI engineering work.",
                       f"As our next {jf.title}"),
        skills_match=sub(base, jf.strengths[0] if jf.strengths else "Partial overlap.", quote),
        seniority_fit=sub(4 if senior else 8, "Staff/lead scope is above your level." if senior
                          else "Asks for a level that matches yours.",
                          "Several years of hands-on experience in a similar role"),
        location_eligibility=sub(9 if jf.remote == "remote" else 5,
                                 "Remote role." if jf.remote == "remote"
                                 else "On-site/hybrid; work authorization not stated.",
                                 remote_line.rstrip(".")),
        language_requirements=sub(2 if needs_language else 9,
                                  "Requires a language you don't have." if needs_language
                                  else "English is enough.",
                                  "Clear communication in English"),
        red_flags=flags,
        strengths=jf.strengths[:3],
        gaps=jf.gaps[:3],
        summary=jf.summary,
    )
    record = fitsvc.build_record(
        assessment, job_text=f"{job.title}\n{job.location}\n{text}",
        description_level=job.description_level, remote_type=job.remote_type, config=ctx.config,
    )
    content = fitsvc.content_hash(job.title, company, job.location, job.remote_type, text)
    return FitScore(
        job_id=job.id, profile_id=profile_id, model="qwen2.5:7b (sample)",
        prompt_version=ctx.prompt_version, content_hash=content,
        experience_version=ctx.experience_version,
        cache_key=fitsvc.cache_key(content, ctx.experience_version, "qwen2.5:7b (sample)",
                                   ctx.prompt_version),
        duration_ms=14_000 + (jf.score * 97) % 9000, created_at=at + timedelta(minutes=5),
        **record,
    )


def fx_company(job_key: str) -> str:
    return _KEY_TO_COMPANY[job_key]


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["embedded"] = True
    command.upgrade(cfg, "head")


def reset_sandbox() -> None:
    """Rebuild the tour sandbox (data/demo.db) from fixtures. Never touches the real DB."""
    from app.config import get_settings
    from app.db import demo_engine

    migrate(get_settings().demo_database_url)
    seed(demo_engine)


def ensure_defaults(engine: Engine) -> None:
    """Give a brand-new real workspace its search profile and settings, and add any setting keys
    introduced by newer versions (e.g. `scoring`). Never overwrites existing values or data."""
    with Session(engine) as s:
        if s.exec(select(SearchProfile)).first() is None:
            s.close()
            seed(engine, empty=True)
            return
        existing = {row.key for row in s.exec(select(AppSetting)).all()}
        missing = [k for k in fx.SETTINGS if k not in existing]
        for key in missing:
            s.add(AppSetting(key=key, value=fx.SETTINGS[key]))
        if missing:
            s.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sandbox", action="store_true", help="rebuild the tour sandbox (default)")
    group.add_argument("--erase-real", action="store_true",
                       help="ERASE the real workspace (keeps only profile + settings defaults)")
    group.add_argument("--defaults", action="store_true",
                       help="add profile + settings to the real DB if it has none")
    args = parser.parse_args()
    from app.db import engine

    if args.erase_real:
        seed(engine, empty=True)
        print("Real workspace erased (profile + settings defaults kept)")
    elif args.defaults:
        ensure_defaults(engine)
        print("Real workspace defaults ensured")
    else:
        reset_sandbox()
        print("Tour sandbox rebuilt (data/demo.db)")


if __name__ == "__main__":
    main()
