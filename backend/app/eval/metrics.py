"""Pure evaluation metrics: agreement between fit scores and the user's Good/Maybe/No labels."""

from dataclasses import dataclass

LABELS = ("good", "maybe", "no")
ORDINAL = {"no": 0, "maybe": 1, "good": 2}


def bucket(score: int | None, good: int = 70, maybe: int = 45) -> str:
    if score is None:
        return "failed"
    return "good" if score >= good else "maybe" if score >= maybe else "no"


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx * vy), 3)


@dataclass
class Item:
    job_id: int
    title: str
    company: str
    label: str
    score: int | None
    seconds: float | None
    sub_scores: dict
    summary: str
    red_flags: list
    confidence: str
    error: str | None = None


def summarize(items: list[Item], good: int = 70, maybe: int = 45) -> dict:
    scored = [i for i in items if i.score is not None]
    confusion = {lab: {pred: 0 for pred in (*LABELS, "failed")} for lab in LABELS}
    for i in items:
        confusion[i.label][bucket(i.score, good, maybe)] += 1
    correct = sum(confusion[lab][lab] for lab in LABELS)
    means = {
        lab: round(sum(i.score for i in scored if i.label == lab) / n, 1)
        if (n := sum(1 for i in scored if i.label == lab))
        else None
        for lab in LABELS
    }

    def badness(i: Item) -> float:
        # distance between label and predicted bucket, then how extreme the score is
        pred = bucket(i.score, good, maybe)
        dist = abs(ORDINAL[i.label] - ORDINAL[pred])
        extremity = (100 - i.score) if i.label == "good" else i.score if i.label == "no" else 0
        return dist * 1000 + extremity

    worst = sorted(
        (i for i in scored if bucket(i.score, good, maybe) != i.label), key=badness, reverse=True
    )[:10]
    secs = sorted(i.seconds for i in items if i.seconds is not None)
    return {
        "n": len(items),
        "labels": {lab: sum(1 for i in items if i.label == lab) for lab in LABELS},
        "failed": len(items) - len(scored),
        "accuracy": round(correct / len(items), 3) if items else None,
        "spearman": spearman([float(i.score) for i in scored],
                             [float(ORDINAL[i.label]) for i in scored]),
        "mean_score": means,
        "confusion": confusion,
        "worst": [i.job_id for i in worst],
        "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None,
        "p90_seconds": round(secs[int(0.9 * (len(secs) - 1))], 1) if secs else None,
    }
