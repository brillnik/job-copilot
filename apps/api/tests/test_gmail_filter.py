from app.core.config import settings
from app.services.email_filter import (
    Candidate,
    domain_matches_company,
    is_ats_domain,
    prefilter,
    subject_names_role,
)

ATS = settings.gmail_ats_domains


def cand(company="Acme Technologies Inc", title="Senior Backend Engineer", i="1"):
    return Candidate(f"c{i}", f"j{i}", company, title, "applied")


def run(domain, subject="Hello", snippet="", cands=None):
    return prefilter(
        sender_domain=domain,
        subject=subject,
        snippet=snippet,
        candidates=cands if cands is not None else [cand()],
        ats_domains=ATS,
    )


def test_domain_matches_company_ignoring_suffixes_and_subdomains():
    assert domain_matches_company("acme.com", "Acme Technologies Inc")
    assert domain_matches_company("mail.acme.io", "Acme")
    assert domain_matches_company("careers.acme.com", "ACME Pvt. Ltd.")
    assert domain_matches_company("brightpath.com", "Bright Path")
    assert not domain_matches_company("gmail.com", "Gmail")
    assert not domain_matches_company("other.com", "Acme")
    assert not domain_matches_company("ab.com", "Ab")  # too short to trust


def test_company_domain_passes_and_picks_the_card():
    r = run("acme.com")
    assert r.passes and r.reason == "company" and r.candidate.job_id == "j1"


def test_unrelated_sender_is_filtered_out():
    assert not run("newsletter.example.org", subject="Weekly digest").passes
    assert not run("gmail.com", subject="Lunch?").passes


def test_ats_domain_passes_but_needs_a_company_mention_to_pick_a_card():
    assert is_ats_domain("us.greenhouse-mail.io", ATS)
    assert is_ats_domain("hire.lever.co", ATS)
    assert not is_ats_domain("notgreenhouse.io", ATS)
    r = run("greenhouse-mail.io", subject="Update on your application")
    assert r.passes and r.reason == "ats" and r.candidate is None
    r = run(
        "greenhouse-mail.io", snippet="Thanks for applying to Acme Technologies Inc"
    )
    assert r.passes and r.candidate.job_id == "j1"


def test_subject_naming_an_applied_role_passes():
    assert subject_names_role(
        "Interview: Senior Backend Engineer role", "Senior Backend Engineer"
    )
    assert not subject_names_role("Engineer", "Engineer")  # too generic to count
    r = run("randomrecruiter.com", subject="Senior Backend Engineer - next steps")
    assert r.passes and r.reason == "role" and r.candidate.job_id == "j1"


def test_two_applications_at_one_company_are_not_guessed():
    cands = [cand(i="1"), cand(title="Data Scientist Lead", i="2")]
    assert run("acme.com", cands=cands).candidate is None
    r = run("acme.com", subject="About the Data Scientist Lead role", cands=cands)
    assert r.candidate.job_id == "j2"


def test_no_candidates_nothing_passes_except_ats():
    assert not run("acme.com", cands=[]).passes
    assert run("ashbyhq.com", cands=[]).passes
