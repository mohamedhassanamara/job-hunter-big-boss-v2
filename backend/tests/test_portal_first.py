"""Portal first: an email about a job with a posting is drafted, approved and queued only after
the application went in through the company site, a job board or LinkedIn."""

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import Application, Job, OutreachDraft
from app.models.enums import ApplyMethod
from app.services import outreach, send_queue
from tests.test_outreach import fresh_queue, job_ready, unapply  # noqa: F401


def set_method(app_id: int, method: ApplyMethod | None) -> None:
    with Session(engine) as s:
        app = s.get(Application, app_id)
        app.web_method = method
        s.add(app)
        s.commit()


def test_the_gate_names_the_missing_step(job_ready: dict) -> None:  # noqa: F811
    unapply(job_ready["app"])
    with Session(engine) as s:
        assert "Apply through the portal first" in outreach.applied_gate(
            s, s.get(Application, job_ready["app"]))


@pytest.mark.parametrize("method", [ApplyMethod.company_site, ApplyMethod.job_board,
                                    ApplyMethod.linkedin])
def test_a_portal_application_opens_the_gate(job_ready: dict, method: ApplyMethod) -> None:  # noqa: F811
    set_method(job_ready["app"], method)
    with Session(engine) as s:
        assert outreach.applied_gate(s, s.get(Application, job_ready["app"])) is None


@pytest.mark.parametrize("method", [ApplyMethod.email, ApplyMethod.other])
def test_an_email_or_other_application_keeps_it_closed(job_ready: dict,  # noqa: F811
                                                       method: ApplyMethod) -> None:
    set_method(job_ready["app"], method)
    with Session(engine) as s:
        assert outreach.applied_gate(s, s.get(Application, job_ready["app"]))


def test_drafting_is_blocked_before_applying(job_ready: dict) -> None:  # noqa: F811
    unapply(job_ready["app"])
    from app.providers.mock import MockEmailDrafter

    with pytest.raises(outreach.OutreachError, match="portal first"):
        outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())


def test_a_posting_less_job_has_no_gate(job_ready: dict) -> None:  # noqa: F811
    unapply(job_ready["app"])
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        job = s.get(Job, app.job_id)
        job.description, job.url, job.apply_url = "", None, None
        assert outreach.applied_gate(s, app, job) is None
        s.rollback()


def test_queueing_an_applied_format_draft_needs_the_gate(
        job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    from app.providers.mock import MockEmailDrafter

    draft = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())
    unapply(job_ready["app"])  # the application was un-marked afterwards
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft.id)
        with pytest.raises(send_queue.QueueError, match="portal first"):
            send_queue.enqueue(s, d)
        assert send_queue.legacy_reason(s, d) and "portal first" in send_queue.legacy_reason(s, d)
