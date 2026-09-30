from app.models.enums import Stage
from app.services.dedupe import dedupe_key, normalize_company
from app.services.pipeline import can_transition, stage_label
from app.services.views import fit_band


def test_normalize_company_strips_legal_suffixes() -> None:
    assert normalize_company("Nimbus Analytics S.L.") == "nimbus analytics"
    assert normalize_company("Lumière Énergie SAS") == "lumiere energie"


def test_dedupe_key_ignores_gender_markers() -> None:
    a = dedupe_key("Nimbus Analytics S.L.", "Senior Data Engineer (m/f/d)", "ES")
    b = dedupe_key("Nimbus Analytics", "Senior Data Engineer", "es")
    assert a == b


def test_transitions() -> None:
    assert can_transition(Stage.new, Stage.shortlisted)
    assert not can_transition(Stage.new, Stage.done)
    assert can_transition(Stage.closed, Stage.new)


def test_stage_labels_depend_on_the_tracks() -> None:
    from app.services.tracks import Tracks

    assert stage_label("ready") == "Ready to apply"
    assert stage_label("ready", Tracks("ready", "approved")) == "Ready to send"
    assert stage_label("done", Tracks("applied", "contact")) == "Applied"
    assert stage_label("done", Tracks("ready", "sent")) == "Emailed"
    assert stage_label("done", Tracks("applied", "sent")) == "Applied + emailed"


def test_fit_bands() -> None:
    assert [fit_band(s) for s in (95, 80, 79, 65, 64, 50, 49)] == [
        "strong", "strong", "good", "good", "fair", "fair", "weak",
    ]
