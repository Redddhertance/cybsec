# stages 5 & 8 - regex pii scrub + reversible un-redact.
# ner (stage 6) needs the spacy model + gets covered by the pipeline test when the model's
# there. here we just do the deterministic regex layer + the RedactionMap round-trip, no
# model needed.

from gateway.redaction import RedactionMap
from gateway.stages.pii_regex import scrub_regex


def test_email_and_phone_redacted():
    rmap = RedactionMap()
    out = scrub_regex("Email me at jane.doe@example.com or call 555-123-4567", rmap)
    assert "jane.doe@example.com" not in out
    assert "[EMAIL_1]" in out
    assert "[PHONE_1]" in out


def test_repeated_value_reuses_placeholder():
    rmap = RedactionMap()
    out = scrub_regex("a@b.com and again a@b.com", rmap)
    assert out.count("[EMAIL_1]") == 2
    assert rmap.total == 1


def test_unredact_roundtrip():
    rmap = RedactionMap()
    original = "Contact: jane.doe@example.com, ssn 123-45-6789"
    scrubbed = scrub_regex(original, rmap)
    assert "jane.doe@example.com" not in scrubbed
    assert rmap.unredact(scrubbed) == original


def test_unredact_handles_double_digit_indices():
    rmap = RedactionMap()
    text = " ".join(f"user{i}@x.com" for i in range(12))
    scrubbed = scrub_regex(text, rmap)
    # [EMAIL_1] mustnt corrupt [EMAIL_10..12] on the way back
    assert rmap.unredact(scrubbed) == text


def test_redaction_counts_by_type():
    rmap = RedactionMap()
    scrub_regex("a@b.com c@d.com 555-123-4567", rmap)
    counts = rmap.counts_by_type()
    assert counts["EMAIL"] == 2
    assert counts["PHONE"] == 1
