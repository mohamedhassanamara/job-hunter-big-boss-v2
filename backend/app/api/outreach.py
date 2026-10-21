import threading
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import (
    Application,
    AppSetting,
    Company,
    Contact,
    CVVersion,
    ExperienceItem,
    Job,
    OutreachDraft,
    SendLog,
    SendQueue,
    SendQueueItem,
)
from app.models.base import utcnow
from app.models.enums import (
    CVStatus,
    DraftStatus,
    EventKind,
    QueueItemStatus,
    QueueStatus,
    Source,
    Stage,
)
from app.providers.base import SendFailed
from app.providers.registry import email_drafter, hook_checker, mailer
from app.providers.registry import researcher as research_provider
from app.schemas.outreach import (
    DraftContact,
    DraftOut,
    DraftPatch,
    DraftProgress,
    MentionIn,
    OutreachStep,
    QueueCounts,
    QueueItemOut,
    QueueOut,
    SendLogOut,
    SentManually,
)
from app.services import applied_check as ac
from app.services import contacts as contacts_svc
from app.services import get_contact, outreach, pipeline, send_queue, verifier
from app.services.views import contact_alert_fields, fit_brief, latest_fits

router = APIRouter(tags=["outreach"])


def _plan_sentences(d: OutreachDraft) -> list[dict[str, Any]]:
    """The generated sentences with their citations (for "where each sentence comes from"):
    an introduction's hook (from signals) and its proofs (from your pool)."""
    plan = (d.plan or {}).get("plan") or {}
    if (d.plan or {}).get("format") == "applied":
        opening = [{"text": plan["opening"], "citations": [], "about_job": True}] \
            if plan.get("opening") else []
        return opening + [{**x, "about_job": False} for x in plan.get("experience") or []]
    if (d.plan or {}).get("format") != "intro":
        return plan.get("sentences", [])
    hook = plan.get("hook") or {}
    out = [{"text": hook.get("text", ""), "citations": [], "about_job": True}] \
        if hook.get("text") else []
    return out + [{**p, "about_job": False} for p in plan.get("proofs") or []]


def _cited_signals(session: Session, d: OutreachDraft) -> list[dict[str, Any]]:
    """The signals the hook cites, with their source links (as they were when drafted)."""
    from app.models import CompanySignal

    plan = d.plan or {}
    ids = set(plan.get("signal_ids") or [])
    out = []
    for sig in plan.get("signals") or []:
        if sig.get("id") in ids:
            row = session.get(CompanySignal, sig["id"])
            out.append({**sig, "source_url": row.source_url if row else "",
                        "page_date": row.page_date.isoformat() if row and row.page_date
                        else None})
    return out


def _hook_check_out(check: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the editor shows: status, model and cost of the last hook check (not its log)."""
    if not check:
        return None
    calls = check.get("calls") or []
    return {"status": check.get("status"), "model": check.get("model"),
            "claims": check.get("claims") or [], "error": check.get("error"),
            "duration_ms": sum(c.get("duration_ms") or 0 for c in calls), "calls": len(calls)}


def _drafts_out(session: Session, drafts: list[OutreachDraft]) -> list[DraftOut]:
    if not drafts:
        return []
    apps = {
        a.id: a
        for a in session.exec(
            select(Application).where(col(Application.id).in_({d.application_id for d in drafts}))
        ).all()
    }
    jobs = {
        j.id: j
        for j in session.exec(
            select(Job).where(col(Job.id).in_({a.job_id for a in apps.values()}))
        ).all()
    }
    companies = {
        c.id: c
        for c in session.exec(
            select(Company).where(col(Company.id).in_({j.company_id for j in jobs.values()}))
        ).all()
    }
    contacts = {
        c.id: c
        for c in session.exec(
            select(Contact).where(col(Contact.id).in_({d.contact_id for d in drafts}))
        ).all()
    }
    cvs: dict[int, int] = {}
    for cv in session.exec(
        select(CVVersion).where(
            col(CVVersion.application_id).in_(apps.keys()), CVVersion.status == CVStatus.approved
        )
    ).all():
        cvs[cv.application_id] = cv.version
    fits = latest_fits(session, jobs.keys())
    ranking = contacts_svc.ranking_settings(session)
    cited = {c for d in drafts for s in _plan_sentences(d) for c in s.get("citations", [])}
    items = {i.id: i for i in session.exec(select(ExperienceItem).where(
        col(ExperienceItem.id).in_(cited))).all()} if cited else {}
    out = []
    for d in drafts:
        app = apps[d.application_id]
        job = jobs[app.job_id]
        c = contacts.get(d.contact_id) if d.contact_id else None
        out.append(
            DraftOut(
                id=d.id,
                application_id=app.id,
                job_id=job.id,
                job_title=job.title,
                company_name=companies[job.company_id].name,
                fit=fit_brief(fits.get(job.id)),
                contact=DraftContact(id=c.id, full_name=c.full_name, title=c.title, email=c.email,
                                     role_label=ranking.label(c.role_rank))
                if c
                else None,
                subject=d.subject,
                body=d.body,
                status=d.status,
                edited=d.edited,
                model=d.model,
                cv_version=cvs.get(app.id),
                created_at=d.created_at,
                updated_at=d.updated_at,
                cv_version_id=d.cv_version_id,
                sentences=_plan_sentences(d),
                citations={str(k): f"{v.title}{f' · {v.org}' if v.org else ''}"
                           for k, v in items.items()},
                violations=d.violations or [],
                attempts=(d.plan or {}).get("attempts", 1),
                prompt_version=d.prompt_version,
                duration_ms=d.duration_ms,
                full_body=outreach.full_body(session, d),
                test_sent_at=d.test_sent_at,
                sent_at=d.sent_at,
                generated_via=(d.plan or {}).get("via") or (
                    "claude -p" if d.model.startswith("claude") else "mock"),
                auth=(d.plan or {}).get("auth"),
                application_mention=(mention := None if (d.plan or {}).get("format") in (
                    "intro", "applied") else outreach.application_mention(session, app)),
                mention_included=bool(mention and mention in d.body),
                format=(d.plan or {}).get("format") or "reply",
                signals=_cited_signals(session, d),
                needs_signal=any(v.get("type") == "needs_signal" for v in d.violations or []),
                research_note=(d.plan or {}).get("research_note"),
                hook_check=_hook_check_out((d.plan or {}).get("hook_check")),
                name_source=(d.plan or {}).get("name_source"),
                **contact_alert_fields(session, app, c),
                verification=d.verification or {},
                verification_state=verifier.state(d.verification,
                                                  verifier.email_text(session, d)),
            )
        )
    return out


def _queue(session: Session) -> SendQueue:
    queue = session.exec(select(SendQueue)).first()
    if queue is None:
        queue = SendQueue()
        session.add(queue)
        session.flush()
    return queue


@router.get("/outreach/drafts", response_model=list[DraftOut])
def list_drafts(
    session: SessionDep,
    status: Literal["draft", "approved", "rejected", "queued", "sent", "all"] = "draft",
) -> list[DraftOut]:
    stmt = select(OutreachDraft).order_by(col(OutreachDraft.created_at).desc())
    if status == "approved":
        stmt = stmt.where(
            col(OutreachDraft.status).in_([DraftStatus.approved, DraftStatus.queued])
        )
    elif status != "all":
        stmt = stmt.where(OutreachDraft.status == status)
    return _drafts_out(session, list(session.exec(stmt).all()))


@router.get("/outreach/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, session: SessionDep) -> DraftOut:
    return _drafts_out(session, [get_or_404(session, OutreachDraft, draft_id, "Draft")])[0]


@router.patch("/outreach/drafts/{draft_id}", response_model=DraftOut)
def patch_draft(draft_id: int, body: DraftPatch, session: SessionDep) -> DraftOut:
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status not in (DraftStatus.draft, DraftStatus.rejected):
        raise HTTPException(409, "Only drafts under review can be edited")
    if body.subject is not None and body.subject != d.subject:
        d.subject, d.edited = body.subject, True
    if body.body is not None and body.body != d.body:
        d.body, d.edited = body.body, True
    if d.edited:
        d.violations = outreach.recheck(session, d)
    session.add(d)
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, session: SessionDep, workspace: WorkspaceDep) -> DraftOut:
    """Approve the email (job → Ready to send). Queuing it is the next, separate step. A draft
    with unresolved errors (grounding, names, banned phrases, length) can't be approved. A hook
    you edited is checked against the signals first (one model call)."""
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status != DraftStatus.draft:
        raise HTTPException(409, "Only drafts under review can be approved")
    try:  # the contact first: verified recently, still there
        get_contact.require_ready(session, get_or_404(session, Application, d.application_id))
    except get_contact.GetContactError as exc:
        raise HTTPException(409, str(exc)) from exc
    model, fallback = _research_models(session)
    outreach.ensure_hook_checked(session, d, hook_checker(
        mock=True if workspace == "demo" else None, model=model, fallback=fallback))
    session.add(d)
    session.commit()
    blocking = [v for v in d.violations or [] if v.get("severity") == "error"]
    if blocking:
        raise HTTPException(409, f"Fix {len(blocking)} problem(s) first: {blocking[0]['message']}")
    app = get_or_404(session, Application, d.application_id)
    contact = session.get(Contact, d.contact_id) if d.contact_id else None
    if contact is None or not contact.email:
        raise HTTPException(409, "The contact has no email address")
    from app.services import contact_check

    if alerts := contact_check.active(session, contact.id):
        raise HTTPException(409, f"{contact.full_name} may have left ({alerts[0].reason}, "
                            f"{alerts[0].source_title or alerts[0].source_url}): pick another "
                            "contact, or dismiss the warning once you've verified them")
    # Last: Claude checks every claim of the exact text against your sources (zero tolerance).
    try:
        verifier.require_email(session, d, verifier.for_workspace(session, workspace))
    except verifier.VerifyError as exc:
        session.commit()  # keep the verdicts: the review screen shows each claim
        raise HTTPException(409, str(exc)) from exc
    d.status = DraftStatus.approved
    session.add(d)
    from app.eval.emails import record

    record(session, d, "approved")  # the email regression set (make eval-emails)
    pipeline.log_event(session, app, EventKind.draft_approved, "Email draft approved")
    if app.stage == Stage.cv_ready:
        pipeline.transition(session, app, Stage.ready)  # an email is ready to send
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/verify", response_model=DraftOut)
def verify_draft(draft_id: int, session: SessionDep, workspace: WorkspaceDep) -> DraftOut:
    """Check every claim now (Claude), without approving: the verdicts show in the review."""
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    try:
        verifier.code_checks_first(d.violations)
    except verifier.VerifyError as exc:
        raise HTTPException(409, str(exc)) from exc
    verifier.verify_email(session, d, verifier.for_workspace(session, workspace))
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/queue", response_model=DraftOut)
def queue_draft(draft_id: int, session: SessionDep) -> DraftOut:
    """Add an approved email to the send queue (it goes out in its turn while the queue runs)."""
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status != DraftStatus.approved:
        raise HTTPException(409, "Only an approved email can be added to the queue")
    if not send_queue.enqueue(session, d):
        raise HTTPException(409, "The queue is full (20 waiting): add it when some have gone out")
    app = get_or_404(session, Application, d.application_id)
    position, _ = send_queue.position_and_eta(session, d.id)
    pipeline.log_event(session, app, EventKind.draft_approved,
                       f"Email added to the send queue (#{position})")
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/test-send", response_model=SendLogOut)
def test_send_draft(draft_id: int, session: SessionDep, engine: EngineDep,
                    workspace: WorkspaceDep) -> SendLogOut:
    """Send this exact email (CV attached) to your own address, subject "[TEST] …"."""
    get_or_404(session, OutreachDraft, draft_id, "Draft")
    try:
        m = _mailer(session, workspace)
        entry = outreach.test_send(engine, draft_id, m)
    except (outreach.OutreachError, SendFailed) as exc:
        raise HTTPException(422, str(exc)) from exc
    if entry.status != "sent":
        raise HTTPException(502, entry.error or "Sending failed")
    return SendLogOut.model_validate(entry, from_attributes=True)


def _mailer(session: Session, workspace: str):  # noqa: ANN202
    smtp = session.exec(select(AppSetting).where(AppSetting.key == "smtp")).first()
    cfg = smtp.value if smtp else {}
    return mailer(mock=True if workspace == "demo" else None, address=cfg.get("address", ""),
                  from_name=cfg.get("from_name", ""))


@router.post("/outreach/drafts/{draft_id}/mention-application", response_model=DraftOut)
def mention_application(draft_id: int, body: MentionIn, session: SessionDep) -> DraftOut:
    """Add or remove "I have also applied through your careers page on …" (fixed wording)."""
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status not in (DraftStatus.draft, DraftStatus.approved):
        raise HTTPException(409, "Only an email that isn't queued or sent can change")
    app = get_or_404(session, Application, d.application_id)
    if (d.plan or {}).get("format") == "applied":
        raise HTTPException(409, "This email already says you applied: no extra line needed")
    mention = outreach.application_mention(session, app)
    if mention is None:
        raise HTTPException(409, "Mark the web application as applied first")
    d.body = outreach.without_mention(d.body, mention)
    if body.include:
        d.body = outreach.with_mention(d.body, mention)
    d.violations = outreach.recheck(session, d)
    session.add(d)
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/reject", response_model=DraftOut)
def reject_draft(draft_id: int, session: SessionDep) -> DraftOut:
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status != DraftStatus.draft:
        raise HTTPException(409, "Only drafts under review can be rejected")
    d.status = DraftStatus.rejected
    session.add(d)
    from app.eval.emails import record

    record(session, d, "rejected")
    app = get_or_404(session, Application, d.application_id)
    pipeline.log_event(session, app, EventKind.note, "Email draft rejected")
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


@router.post("/outreach/drafts/{draft_id}/restore", response_model=DraftOut)
def restore_draft(draft_id: int, session: SessionDep) -> DraftOut:
    """Undo a rejection: move the draft back to review."""
    d = get_or_404(session, OutreachDraft, draft_id, "Draft")
    if d.status != DraftStatus.rejected:
        raise HTTPException(409, "Only rejected drafts can be restored")
    d.status = DraftStatus.draft
    session.add(d)
    app = get_or_404(session, Application, d.application_id)
    pipeline.log_event(session, app, EventKind.note, "Email draft restored")
    session.commit()
    session.refresh(d)
    return _drafts_out(session, [d])[0]


def _email_model(session: Session) -> str:
    models = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    model = (((models.value if models else {}).get("email") or {}).get("model")
             or "claude-sonnet-5")
    return "claude-sonnet-5" if model.startswith("claude-haiku") else model


def _research_models(session: Session) -> tuple[str, str | None]:
    models = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    cfg = (models.value if models else {}).get("research") or {}
    return cfg.get("model") or "gemma4:31b-cloud", cfg.get("fallback", "gemma4:12b")


# The draft step runs in the background (research can take a minute): one per job, polled.
_draft_runs: dict[tuple[str, int], dict[str, Any]] = {}
_draft_runs_lock = threading.Lock()


def draft_progress_state(workspace: str, app_id: int) -> dict[str, Any] | None:
    with _draft_runs_lock:
        state = _draft_runs.get((workspace, app_id))
        return dict(state) if state else None


@router.post("/applications/{app_id}/draft/generate", status_code=202,
             response_model=DraftProgress)
def generate_draft(app_id: int, session: SessionDep, engine: EngineDep,
                   workspace: WorkspaceDep, mode: str | None = None) -> DraftProgress:
    """The email draft step: research the company (fresh signals are reused), then Claude (your
    subscription) writes the introduction; the mock in the sandbox and tests. A job with a
    posting gets the application follow-up instead (no research); `?mode=speculative` asks for
    the introduction anyway, `?mode=applied` for the follow-up. Poll /draft/progress."""
    if mode not in (None, *outreach.EMAIL_MODES):
        raise HTTPException(422, f"mode must be one of {', '.join(outreach.EMAIL_MODES)}")
    get_or_404(session, Application, app_id, "Application")
    key = (workspace, app_id)
    with _draft_runs_lock:
        if (_draft_runs.get(key) or {}).get("status") == "running":
            raise HTTPException(409, "This email is already being drafted")
        _draft_runs[key] = {"status": "running", "phase": "starting", "done": 0, "total": 0,
                            "draft_id": None, "error": None}
    demo = workspace == "demo"
    drafter = email_drafter(mock=True if demo else None, model=_email_model(session))
    model, fallback = _research_models(session)
    researcher = research_provider(mock=True if demo else None, model=model, fallback=fallback)
    checker = hook_checker(mock=True if demo else None, model=model, fallback=fallback)

    def progress(phase: str, done: int, total: int) -> None:
        with _draft_runs_lock:
            _draft_runs[key].update(phase=phase, done=done, total=total)

    def work() -> None:
        try:
            draft = outreach.generate(engine, app_id, drafter, researcher=researcher,
                                      fetcher=_demo_fetcher() if demo else None,
                                      progress=progress, hook_checker=checker, mode=mode)
            with _draft_runs_lock:
                _draft_runs[key].update(status="done", phase="done", draft_id=draft.id)
        except Exception as exc:  # noqa: BLE001 (shown to the user)
            with _draft_runs_lock:
                _draft_runs[key].update(status="failed", error=str(exc)[:400])

    threading.Thread(target=work, name=f"draft-{app_id}", daemon=True).start()
    return DraftProgress(**draft_progress_state(workspace, app_id))


def _demo_fetcher():  # noqa: ANN202
    """The sandbox never fetches the web: sample pages for its sample companies."""
    from app.services.research import SampleFetcher

    return SampleFetcher()


@router.get("/applications/{app_id}/draft/progress", response_model=DraftProgress)
def draft_progress(app_id: int, workspace: WorkspaceDep) -> DraftProgress:
    state = draft_progress_state(workspace, app_id)
    if state is None:
        return DraftProgress(status="idle", phase="", done=0, total=0)
    return DraftProgress(**state)


@router.get("/applications/{app_id}/outreach", response_model=OutreachStep)
def outreach_step(app_id: int, session: SessionDep) -> OutreachStep:
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    contact = session.get(Contact, app.contact_id) if app.contact_id else None
    cv = outreach.approved_cv(session, app)
    draft = session.exec(select(OutreachDraft).where(
        OutreachDraft.application_id == app.id, OutreachDraft.status != DraftStatus.rejected)
        .order_by(col(OutreachDraft.id).desc())).first()
    position, eta = send_queue.position_and_eta(session, draft.id) if draft else (None, None)
    if draft and draft.status == DraftStatus.sent:
        step = "sent"
    elif draft and draft.status == DraftStatus.queued:
        step = "queued"
    elif draft and draft.status == DraftStatus.approved:
        step = "queue"
    elif draft and draft.status == DraftStatus.draft:
        step = "review"
    elif (contact_state := get_contact.state(session, app)) in ("get", "never"):
        step = "get_contact"
    elif contact_state == "verify":
        step = "verify_contact"
    elif cv is None:
        step = "cv"
    else:
        step = "draft"
    return OutreachStep(
        step=step, route=app.route, contact_tier=app.contact_tier,
        contact_search=session.get(Company, job.company_id).contact_search,
        has_contact=contact is not None,
        has_email=bool(contact and contact.email), cv_version=cv.version if cv else None,
        email_mode=outreach.email_mode(job), listing_chars=len(job.description or ""),
        listing_short=len(job.description or "") < ac.SNIPPET_CHARS,
        can_fetch_listing=job.source != Source.linkedin
        and "linkedin.com/" not in (job.url or "").lower(),
        draft=_drafts_out(session, [draft])[0] if draft else None, queue_position=position,
        queue_eta=eta, queue_status=send_queue.queue(session).status,
        sent_at=draft.sent_at if draft and draft.status == DraftStatus.sent else None,
        who_to_contact=contacts_svc.who_to_contact(session, job, session.get(Company,
                                                                             job.company_id))
        if contact is None else None)


@router.post("/applications/{app_id}/sent-manually", response_model=OutreachStep)
def sent_manually(app_id: int, body: SentManually, session: SessionDep) -> OutreachStep:
    """You sent the approved email yourself: recorded as sent (CV locked, job Sent)."""
    from app.services.tracking import _at

    app = get_or_404(session, Application, app_id, "Application")
    sent_on = date.fromisoformat(body.sent_on) if body.sent_on else None
    try:
        send_queue.sent_manually(session, app, _at(sent_on))
    except send_queue.QueueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return outreach_step(app_id, session)


@router.get("/outreach/send-log", response_model=list[SendLogOut])
def send_log(session: SessionDep, limit: int = 100) -> list[SendLogOut]:
    rows = session.exec(select(SendLog).order_by(col(SendLog.id).desc()).limit(limit)).all()
    return [SendLogOut.model_validate(r, from_attributes=True) for r in rows]


# ---------------------------------------------------------------------------------------- queue


def _queue_out(session: Session, queue: SendQueue) -> QueueOut:
    items = session.exec(
        select(SendQueueItem)
        .where(
            SendQueueItem.queue_id == queue.id,
            SendQueueItem.status != QueueItemStatus.cancelled,
        )
        .order_by(col(SendQueueItem.position))
    ).all()
    drafts = {
        d.id: d
        for d in _drafts_out(
            session,
            list(
                session.exec(
                    select(OutreachDraft).where(
                        col(OutreachDraft.id).in_([i.draft_id for i in items])
                    )
                ).all()
            ),
        )
    }
    # Pending items get projected send times: next_send_at, then +interval each.
    pending = [i for i in items if i.status == QueueItemStatus.pending]
    base = queue.next_send_at if queue.status == QueueStatus.running else None
    projected = {
        i.id: (base + timedelta(minutes=queue.interval_minutes * n)) if base else None
        for n, i in enumerate(pending)
    }
    out = []
    for i in items:
        d = drafts[i.draft_id]
        out.append(
            QueueItemOut(
                id=i.id,
                position=i.position,
                status=i.status,
                scheduled_at=projected.get(i.id, i.scheduled_at),
                sent_at=i.sent_at,
                error=i.error,
                attempts=i.attempts,
                draft_id=d.id,
                job_id=d.job_id,
                subject=d.subject,
                contact_name=d.contact.full_name if d.contact else None,
                contact_email=d.contact.email if d.contact else None,
                company_name=d.company_name,
            )
        )
    # Pending first (in send order), then history newest first.
    out.sort(key=lambda o: (o.status != "pending", o.position if o.status == "pending" else 0))
    history = sorted(
        (o for o in out if o.status != "pending"),
        key=lambda o: o.sent_at or o.scheduled_at or utcnow(),
        reverse=True,
    )
    out = [o for o in out if o.status == "pending"] + history
    return QueueOut(
        status=queue.status,
        interval_minutes=queue.interval_minutes,
        max_items=queue.max_items,
        next_send_at=queue.next_send_at if queue.status == QueueStatus.running else None,
        counts=QueueCounts(
            pending=len(pending),
            sent=sum(1 for i in items if i.status == QueueItemStatus.sent),
            failed=sum(1 for i in items if i.status == QueueItemStatus.failed),
            unknown=sum(1 for i in items if i.status == QueueItemStatus.unknown),
        ),
        items=out,
        test_sent=outreach.has_successful_test(session),
        own_address=outreach.own_address(session),
    )


@router.get("/queue", response_model=QueueOut)
def get_queue(session: SessionDep) -> QueueOut:
    return _queue_out(session, _queue(session))


@router.post("/queue/pause", response_model=QueueOut)
def pause_queue(session: SessionDep) -> QueueOut:
    queue = _queue(session)
    queue.status = QueueStatus.paused
    queue.next_send_at = None
    session.add(queue)
    session.commit()
    return _queue_out(session, queue)


@router.post("/queue/resume", response_model=QueueOut)
def resume_queue(session: SessionDep) -> QueueOut:
    """Start sending: one email per interval. Requires one successful test send first."""
    try:
        q = send_queue.resume(session)
    except send_queue.QueueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _queue_out(session, q)


@router.post("/queue/items/{item_id}/retry", response_model=QueueOut)
def retry_item(item_id: int, session: SessionDep) -> QueueOut:
    item = get_or_404(session, SendQueueItem, item_id, "Queue item")
    try:
        send_queue.retry(session, item)
    except send_queue.QueueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _queue_out(session, _queue(session))


@router.post("/queue/items/{item_id}/mark-sent", response_model=QueueOut)
def mark_item_sent(item_id: int, session: SessionDep) -> QueueOut:
    """An item with an unknown outcome that you found in Gmail's Sent folder."""
    item = get_or_404(session, SendQueueItem, item_id, "Queue item")
    try:
        send_queue.mark_sent(session, item)
    except send_queue.QueueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _queue_out(session, _queue(session))


@router.delete("/queue/items/{item_id}", response_model=QueueOut)
def remove_queue_item(item_id: int, session: SessionDep) -> QueueOut:
    """Take a pending email out of the queue; it stays approved (Ready to send)."""
    item = get_or_404(session, SendQueueItem, item_id, "Queue item")
    if item.status != QueueItemStatus.pending:
        raise HTTPException(409, "Only pending items can be removed")
    draft = get_or_404(session, OutreachDraft, item.draft_id)
    draft.status = DraftStatus.approved  # still approved: add it again whenever you like
    session.add(draft)
    session.delete(item)
    session.commit()
    return _queue_out(session, _queue(session))
