"""Filling the Get contact form from a pasted block (nothing is saved by parsing)."""

import pytest

from app.services.contact_paste import parse

APOLLO = """Marie Dupont
Directrice Générale at Zaion
Paris, Île-de-France, France
Verified
marie.dupont@zaion.ai
+33 1 23 45 67 89
linkedin.com/in/marie-dupont-8a1b2c/
Add to sequence"""

LINKEDIN = """Franck Garel
 · 2nd
CTO chez Nomadia
Paris, Île-de-France, France · Contact info
500+ connections
Message
More"""

SIGNATURE = """Bien cordialement,
Grégoire Gaillac
Founder & CEO | MP DATA
greg.g@gmail.com / gregoire.gaillac@mpdata.fr"""


@pytest.mark.parametrize(("text", "expected"), [
    (APOLLO, {"full_name": "Marie Dupont", "title": "Directrice Générale", "company": "Zaion",
              "email": "marie.dupont@zaion.ai",
              "linkedin_url": "https://www.linkedin.com/in/marie-dupont-8a1b2c"}),
    (LINKEDIN, {"full_name": "Franck Garel", "title": "CTO", "company": "Nomadia", "email": None,
                "linkedin_url": None}),
    (SIGNATURE, {"full_name": "Grégoire Gaillac", "title": "Founder & CEO",
                 "company": "MP DATA", "email": "gregoire.gaillac@mpdata.fr"}),
])
def test_blocks_from_the_extension_linkedin_and_a_signature(text: str, expected: dict) -> None:
    got = parse(text).dict()
    assert {k: got[k] for k in expected} == expected


def test_a_work_email_wins_over_a_personal_one_and_a_bare_email_gives_a_name() -> None:
    assert "kept gregoire.gaillac@mpdata.fr" in parse(SIGNATURE).notes[0]
    only = parse("jean.martin@acme.fr")
    assert only.full_name == "Jean Martin" and "guessed" in only.notes[0]


def test_the_endpoint_saves_nothing(client) -> None:  # noqa: ANN001
    r = client.post("/api/contacts/parse", json={"text": APOLLO})
    assert r.status_code == 200 and r.json()["email"] == "marie.dupont@zaion.ai"
