import json

from app.training.scrub import Scrubber, strip_ids

TEXT = (
    "Priya Raman\npriya.raman@gmail.com | +91 98765 43210 | Bengaluru, Karnataka\n"
    "https://www.linkedin.com/in/priyaraman and github.com/priyaraman/\n"
    "Contact Raman at 098-765-43210 or recruiter@acme.io. Worked 2019 - 2021 2022.\n"
    "Priya built Kafka pipelines in Bengaluru."
)
GOLD = {
    "contact": {
        "name": "Priya Raman",
        "email": "priya.raman@gmail.com",
        "phone": "+91 98765 43210",
        "location": "Bengaluru, Karnataka",
        "links": ["https://www.linkedin.com/in/priyaraman", "github.com/priyaraman/"],
    },
    "summary": "Priya builds pipelines",
    "id": "abc",
}


def scrubber(seed="s"):
    c = GOLD["contact"]
    return Scrubber(
        seed, [c["name"]], [c["email"]], [c["phone"]], c["links"], [c["location"]]
    )


def test_pii_removed_from_text_and_gold_and_bytes():
    s = scrubber()
    out = s.text(TEXT)
    gold = s.obj(strip_ids(GOLD))
    blob = (out + json.dumps(gold)).lower()
    for leak in (
        "priya", "raman", "gmail", "98765", "43210", "linkedin.com/in", "priyaraman",
        "bengaluru", "karnataka", "recruiter@acme", "acme.io",
    ):  # fmt: skip
        assert leak not in blob, leak
    assert "id" not in gold
    assert "Kafka pipelines" in out and "2019 - 2021 2022" in out  # content kept


def test_consistent_between_text_and_gold():
    s = scrubber()
    out, gold = s.text(TEXT), s.obj(GOLD)
    c = gold["contact"]
    for value in (c["name"], c["email"], c["phone"], c["location"], c["links"][0]):
        assert value in out, value
    assert c["name"].split()[0] in out


def test_deterministic_per_seed_and_different_across_seeds():
    assert scrubber("a").text(TEXT) == scrubber("a").text(TEXT)
    assert scrubber("a").text(TEXT) != scrubber("b").text(TEXT)


def test_generic_patterns_without_known_values():
    s = Scrubber("x")
    out = s.text("mail me@corp.com call +1 (415) 555-0100 see https://x.io/p?q=1.")
    assert "me@corp.com" not in out and "555" not in out and "x.io" not in out
    assert out.endswith(".")  # trailing punctuation preserved
    assert s.text("me@corp.com") == s.text("me@corp.com")
