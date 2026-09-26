from app.services.geo import country_from_text, region_allows
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


def test_region_allows() -> None:
    targets = {"ES", "PT", "FR", "IT"}
    assert region_allows("Worldwide", targets) == (True, None)
    assert region_allows("Europe", targets)[0]
    assert region_allows("Spain, Portugal", targets) == (True, "ES")
    assert region_allows("USA", targets) == (False, "US")
    assert region_allows("Germany", targets) == (False, "DE")
    assert region_allows("", targets) == (True, None)
    assert region_allows("USA (remote)", targets) == (False, "US")
    assert region_allows("USA, UTC-5", targets) == (False, "US")
    assert region_allows("USA or Europe", targets)[0]
    assert region_allows("CET +/- 2h", targets)[0]
