from evaluation.diagnose_ragas_factual import (
    clean_for_judge, contextual_reference, make_checks,
)


def test_clean_citations_and_markdown():
    assert clean_for_judge("**₹2,25,458\u202fcrore**【S1】【S8】") == "₹2,25,458 crore"


def test_contextual_short_reference():
    assert (contextual_reference(
        "What was TCS consolidated revenue from operations in FY 2022-23?",
        "₹225,458 crore."
    ) == "TCS consolidated revenue from operations in FY 2022-23 was ₹225,458 crore.")


def test_contextual_reference_profit():
    assert (contextual_reference(
        "What was TCS consolidated profit for the year in FY 2022-23?",
        "₹42,303 crore."
    ) == "TCS consolidated profit for the year in FY 2022-23 was ₹42,303 crore.")


def test_long_reference_is_unmodified():
    text = "TCS cited cost optimisation and vendor consolidation."
    assert contextual_reference("What did TCS highlight?", text) == text


def test_make_checks_identity_is_exact():
    row = {"id": "Q01", "question": "What was TCS revenue in FY 2022-23?",
           "answer": "TCS revenue was **₹2,25,458 crore**【S1】", "reference": "₹225,458 crore."}
    checks = make_checks(row, ["identity", "contextualized"])
    assert checks[0]["response"] == checks[0]["reference"]
    assert checks[1]["reference"] == "TCS revenue in FY 2022-23 was ₹225,458 crore."
    assert checks[1]["response"] == "TCS revenue was ₹2,25,458 crore"
