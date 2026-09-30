"""Studio: every CV and cover letter (PDF and form text) across jobs, with filters."""

from app.db import engine
from app.services import cover_letter as cl
from tests.test_cover_letter import QUESTION, Script, good_plan, web_job  # noqa: F401 (fixture)


def test_studio_lists_cvs_and_both_letter_formats(web_job: dict, client) -> None:  # noqa: F811, ANN001
    pdf = cl.approve(engine, cl.generate(engine, web_job["app"], Script(good_plan(web_job))).id)
    form = cl.generate(engine, web_job["app"], Script(good_plan(web_job, form=True)),
                       fmt="form", question=QUESTION, char_limit=900)
    body = client.get(f"/api/studio/documents?q={web_job['company']}").json()
    kinds = {(d["kind"], d["id"]) for d in body["items"]}
    assert {("cv", web_job["cv"]), ("pdf", pdf.id), ("form", form.id)} <= kinds
    assert body["counts"]["cv"] >= 1 and body["counts"]["form"] >= 1
    only_forms = client.get(f"/api/studio/documents?kind=form&q={web_job['company']}").json()
    assert [d["id"] for d in only_forms["items"]] == [form.id]
    assert only_forms["items"][0]["detail"].endswith("/900 characters")
    approved = client.get("/api/studio/documents?status=approved").json()["items"]
    assert ("pdf", pdf.id) in {(d["kind"], d["id"]) for d in approved}
    assert client.get("/api/studio/documents?kind=nope").status_code == 422
