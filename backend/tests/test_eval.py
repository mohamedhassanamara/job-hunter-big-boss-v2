from sqlmodel import Session, select

from app.db import engine
from app.eval.metrics import Item, bucket, spearman, summarize
from app.eval.run import run_eval
from app.models import Job
from app.providers.mock import MockFitScorer


def item(label: str, score: int | None) -> Item:
    return Item(1, "t", "c", label, score, 1.0, {}, "", [], "high")


def test_bucket_and_spearman() -> None:
    assert [bucket(s) for s in (90, 70, 69, 45, 44, None)] == [
        "good", "good", "maybe", "maybe", "no", "failed"]
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert spearman([10, 20, 30], [0, 0, 1]) is not None  # ties handled
    assert spearman([1, 2], [1, 2]) is None  # too few points


def test_summarize_confusion_and_worst() -> None:
    items = [item("good", 85), item("good", 20), item("maybe", 55), item("no", 90), item("no", 10),
             item("maybe", None)]
    for n, i in enumerate(items):
        i.job_id = n
    s = summarize(items)
    assert s["n"] == 6 and s["failed"] == 1
    assert s["confusion"]["good"]["good"] == 1 and s["confusion"]["good"]["no"] == 1
    assert s["accuracy"] == round(3 / 6, 3)
    assert s["worst"][:2] == [3, 1]  # "no" scored 90, then "good" scored 20


def test_run_eval_writes_report(seeded: None, tmp_path) -> None:
    with Session(engine) as s:
        jobs = s.exec(select(Job)).all()[:6]
        for j, label in zip(jobs, ["good", "good", "maybe", "maybe", "no", "no"], strict=True):
            j.user_label = label
            s.add(j)
        s.commit()
    report, path = run_eval(engine, MockFitScorer(), out_dir=tmp_path, echo=False)
    assert report["summary"]["n"] == 6
    assert report["meta"]["prompt_version"].startswith("fit_score/v")
    text = path.read_text()
    assert "Bucket accuracy" in text and "Confusion" in text
    _, second = run_eval(engine, MockFitScorer(), out_dir=tmp_path, echo=False)
    assert "vs previous" in second.read_text()
