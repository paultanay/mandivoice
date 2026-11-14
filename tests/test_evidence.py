from app.evidence import contains_verbatim_quote


def test_evidence_matching_normalizes_case_and_whitespace():
    assert contains_verbatim_quote("  PRICE   ₹40  ", "item price ₹40 today")


def test_evidence_matching_rejects_blank_and_missing_quotes():
    assert not contains_verbatim_quote("   ", "some transcript")
    assert not contains_verbatim_quote("₹50", "item price ₹40")
