import pytest

from app.services.geo import country_from_text, remote_allows
from app.services.text import html_to_text


def test_html_to_text_keeps_structure() -> None:
    html = """<div><p><strong>About us</strong></p><p>We build&nbsp;data  platforms.</p>
    <h3>What you'll do</h3><ul><li>Build <b>pipelines</b></li><li>Own &amp; operate</li></ul>
    <script>track()</script><p>Salary: 60k.</p></div>"""
    assert html_to_text(html) == (
        "## About us\n\nWe build data platforms.\n\n## What you'll do\n\n"
        "- Build pipelines\n- Own & operate\n\nSalary: 60k."
    )


def test_html_to_text_plain_text_and_inline_bullets() -> None:
    assert html_to_text("Intro line\n• one\n• two") == "Intro line\n\n- one\n- two"
    assert html_to_text("<p>• first</p><p>• second</p>") == "- first\n- second"
    assert html_to_text(None) == ""
    escaped = "&lt;p&gt;Hi &amp;amp; bye&lt;/p&gt;&lt;ul&gt;&lt;li&gt;x&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(escaped) == "Hi & bye\n\n- x"
    assert "<" not in html_to_text("<p>a <span>b</span></p><br/>")


def test_country_from_text() -> None:
    assert country_from_text("Barcelona, Spain") == "ES"
    assert country_from_text("Lisboa") == "PT"
    assert country_from_text("Milano, Lombardia") == "IT"
    assert country_from_text("Île-de-France, Paris") == "FR"
    assert country_from_text("Köln") == "DE"
    assert country_from_text("Somewhere unknown") is None


def test_gulf_and_belgium_locations() -> None:
    assert country_from_text("Dubai, United Arab Emirates") == "AE"
    assert country_from_text("Abu Dhabi") == "AE"
    assert country_from_text("Doha") == "QA"
    assert country_from_text("Manama, Bahrain") == "BH"
    assert country_from_text("Kuwait City") == "KW"
    assert country_from_text("Amman, Jordan") == "JO"
    assert country_from_text("Leuven") == "BE"


TARGETS = {"FR", "ES", "IT", "PT", "DE", "BE", "AE", "QA", "BH", "KW", "JO"}


@pytest.mark.parametrize(
    ("text", "anywhere", "europe", "targets"),
    [
        ("Worldwide", True, True, True),
        ("", True, True, True),  # unknown region: shown, the scorer judges it
        ("Europe", True, True, True),
        ("CET +/- 2h", True, True, True),
        ("Spain, Portugal", True, True, True),
        ("Netherlands", True, True, False),  # European, not a target
        ("Middle East", True, False, True),
        ("GCC", True, False, True),
        ("Dubai, UAE", True, False, True),
        ("Saudi Arabia", True, False, False),  # EMEA, not European, not a target
        ("USA", False, False, False),  # US-only remote is never eligible
        ("USA (remote)", False, False, False),
        ("USA, UTC-5", False, False, False),
        ("Americas", False, False, False),
        ("US time zones", False, False, False),
        ("USA or Europe", True, True, True),
        ("APAC", False, False, False),
    ],
)
def test_remote_scopes(text: str, anywhere: bool, europe: bool, targets: bool) -> None:
    got = [remote_allows(text, None, TARGETS, s)[0] for s in ("anywhere", "europe", "targets")]
    assert got == [anywhere, europe, targets]


def test_remote_falls_back_to_job_country() -> None:
    assert remote_allows(None, "US", TARGETS, "anywhere") == (False, "US")
    assert remote_allows(None, "DE", TARGETS, "targets") == (True, None)
    assert remote_allows(None, None, TARGETS, "targets") == (True, None)
