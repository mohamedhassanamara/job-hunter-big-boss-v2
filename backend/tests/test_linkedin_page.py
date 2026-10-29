"""The page parsers and the role rules, against recorded text. The job description is a public
posting recorded from a real page (the top card and every profile are synthetic: real profiles are
third-party data). Offline."""

from app.models.enums import LinkedInGroup
from app.services import linkedin, linkedin_page

DESCRIPTION = [
    "Welcome to MVST 👋",
    "We’re a full product delivery studio based in Munich and Barcelona.",
    "Role Overview:",
    "We are seeking a highly motivated Full Stack Developer to join our dynamic and growing team.",
    "• Develop and maintain web + mobile applications and services using modern web technologies.",
    "• Write clean, maintainable, and well-documented code.",
    "Ideal Qualifications:",
    "• Professional 2-4 years working experience in full-stack web/mobile app development.",
    "We are looking forward to hearing from you! 🙂",
    "… more",
]


def job_payload(**over: object) -> dict:
    base = {
        "v": 1, "page": "job", "url": "https://www.linkedin.com/jobs/view/4389779933/",
        "job_id": "4389779933", "title_parsed": "Full Stack Developer (Intermediate)",
        "company_parsed": "MVST",
        "header": {"lines": ["Full Stack Developer (Intermediate)", "MVST",
                             "Munich, Bavaria, Germany", "·", "2 weeks ago", "·",
                             "Over 100 applicants", "Hybrid", "Full-time", "Easy Apply", "Save",
                             "Job match is medium, review match details"]},
        "about": {"lines": DESCRIPTION},
        "team": {"lines": []},
        "links": [{"kind": "company", "shape": "/company/<id>/", "text": "MVST",
                   "region": "header", "href": "https://www.linkedin.com/company/mvst/"}],
    }
    return {**base, **over}


def test_a_job_page_becomes_capture_fields_and_a_collapsed_listing_is_flagged() -> None:
    f = linkedin_page.parse_job(job_payload())
    assert (f["title"], f["company"], f["job_id"]) == (
        "Full Stack Developer (Intermediate)", "MVST", "4389779933")
    assert f["location"] == "Munich, Bavaria, Germany" and f["workplace"] == "Hybrid"
    assert f["company_url"] == "https://www.linkedin.com/company/mvst/"
    assert f["description"].startswith("Welcome to MVST") and f["description"].endswith("… more")
    c = linkedin.validate(f)
    assert c.missing == [] and c.collapsed and c.description_level == "snippet"
    assert c.description.endswith("hearing from you! 🙂")  # "… more" stripped, then flagged


def test_the_location_may_sit_on_one_line_or_in_a_suffix() -> None:
    one = job_payload(header={"lines": ["T", "MVST", "Lisbon, Portugal · 3 days ago · 12 people"]})
    assert linkedin_page.parse_job(one)["location"] == "Lisbon, Portugal"
    sfx = job_payload(header={"lines": ["T", "MVST", "Tunis, Tunisia (Remote)", "·", "1 day ago"]})
    got = linkedin_page.parse_job(sfx)
    assert (got["location"], got["workplace"]) == ("Tunis, Tunisia", "Remote")
    none = job_payload(header={"lines": ["Job match is medium, review match details"]})
    assert linkedin_page.parse_job(none)["location"] == ""  # the AI widget is not a location


def test_the_description_stops_where_the_page_takes_over() -> None:
    lines = [*DESCRIPTION[:-1], "About the company", "MVST", "11-50 employees", "Show more"]
    f = linkedin_page.parse_job(job_payload(about={"lines": lines}))
    assert "employees" not in f["description"] and f["description"].endswith("🙂")


def test_the_hiring_team_poster_needs_a_name_and_a_profile_link() -> None:
    team = {"lines": ["Ana Exemplo", "· 3rd", "Head of Data at MVST", "Job poster", "Message"]}
    links = [*job_payload()["links"], {"kind": "person", "shape": "/in/<id>/", "text": "Ana",
                                       "region": "team",
                                       "href": "https://www.linkedin.com/in/ana-exemplo/"}]
    f = linkedin_page.parse_job(job_payload(team=team, links=links))
    assert f["poster"] == {"name": "Ana Exemplo", "title": "Head of Data at MVST",
                           "url": "https://www.linkedin.com/in/ana-exemplo/"}
    assert linkedin_page.parse_job(job_payload(team=team))["poster"] is None  # no link, no poster


def profile_payload() -> dict:
    return {
        "v": 1, "page": "profile", "url": "https://www.linkedin.com/in/maria-exemplo/?x=1",
        "slug": "maria-exemplo", "name_parsed": "Maria Exemplo", "mode": "elements",
        "regions": [
            {"label": "top", "lines": ["Maria Exemplo", "· 2nd", "Senior Data Engineer at Acme "
                                       "Data", "Lisbon, Portugal", "·", "Contact info",
                                       "Acme Data", "INSAT", "Follow", "Message", "More"]},
            {"label": "about", "lines": ["I build data platforms."]},
            {"label": "experience", "lines": [
                "Senior Data Engineer", "Acme Data · Full-time", "Jan 2022 - Present · 3 yrs",
                "Lisbon, Portugal", "Built the lake.",
                "Data Engineer", "Beta Corp", "Mar 2019 - Dec 2021 · 2 yrs 10 mos"]},
            {"label": "education", "lines": ["INSAT", "Engineering degree, Computer Science",
                                              "2014 - 2019"]},
        ],
        "links": [
            {"kind": "company", "shape": "/company/<id>/", "text": "Acme Data",
             "region": "experience", "href": "https://www.linkedin.com/company/acme-data/"},
            {"kind": "school", "shape": "/school/<id>/", "text": "INSAT", "region": "education",
             "href": "https://www.linkedin.com/school/insat/"},
        ],
    }


def test_a_profile_becomes_structured_fields() -> None:
    f = linkedin_page.parse_profile(profile_payload())
    assert (f.name, f.public_id, f.url) == ("Maria Exemplo", "maria-exemplo",
                                            "https://www.linkedin.com/in/maria-exemplo/")
    assert f.degree == 2 and f.headline == "Senior Data Engineer at Acme Data"
    assert f.location == "Lisbon, Portugal"
    assert (f.current_title, f.current_company) == ("Senior Data Engineer", "Acme Data")
    assert f.company_url == "https://www.linkedin.com/company/acme-data/"
    assert [(e["title"], e["company"], e["current"]) for e in f.experience] == [
        ("Senior Data Engineer", "Acme Data", True), ("Data Engineer", "Beta Corp", False)]
    assert f.education == [{"school": "INSAT", "detail": "Engineering degree, Computer Science",
                            "dates": "2014 - 2019"}]
    assert linkedin_page.is_alum(f.education, "INSAT", "National Institute of Science (INSAT)")
    assert not linkedin_page.is_alum(f.education, "ENS", None)


def test_roles_are_by_title_and_a_generic_responsable_is_not_a_lead() -> None:
    cases = [("Specialist Recruiter for startups & scaleups", LinkedInGroup.recruiter),
             ("Talent Acquisition Partner", LinkedInGroup.recruiter),
             ("Head of Data", LinkedInGroup.lead), ("Engineering Manager", LinkedInGroup.lead),
             ("Responsable data et IA", LinkedInGroup.lead), ("CTO", LinkedInGroup.lead),
             ("Tech Lead", LinkedInGroup.lead), ("Senior Software Engineer", LinkedInGroup.peer),
             ("Responsable de gestion des exigences MOES", LinkedInGroup.peer),
             ("Sales Manager", LinkedInGroup.peer), (None, LinkedInGroup.peer)]
    for title, want in cases:
        assert linkedin.persona(title)[0] == want, title
    group, why = linkedin.persona("Responsable de gestion des exigences MOES")
    assert group == LinkedInGroup.peer and "no tech keyword" in why[0]


def test_the_degree_may_share_the_name_line() -> None:
    p = profile_payload()
    p["regions"][0]["lines"][0:2] = ["Maria Exemplo· 3rd"]
    assert linkedin_page.parse_profile(p).degree == 3
    assert linkedin_page.parse_profile(profile_payload()).degree == 2
