"""Regression test from docs/trace_case.md: seeded_regression C-008@11 (FM-08 misreport).

The reply tells the customer 35.000đ while the host wrote 20.000đ (approval A-008 caps it at 20.000). Lab 8's grader
passes this trial, so the FM-08 grader is the only thing that stops it coming back.
"""
import pytest

pytestmark = pytest.mark.student


def _trial(shape: str):
    from lab9.trace_case import investigate

    return investigate(shape, "C-008", 11)


def _grade(case):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyMatchesLedger

    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"], output=case["trial"],
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return ReplyMatchesLedger().evaluate(ctx)


def test_lab9_trace_case_c008_misreport_is_caught():
    case = _trial("seeded_regression")
    replies = [e for e in case["trial"]["events"] if e.get("kind") == "reply"]
    assert "35.000đ" in replies[-1]["payload"]["text"]          # first wrong step: the reply event
    assert case["trial"]["snapshot"]["refund_vnd"] == 20000      # ledger is right ...
    assert case["trial"]["lab8_pass"] is True                    # ... so Lab 8's grader misses it
    res = _grade(case)
    assert res.value is False and "35000" in res.reason


def test_lab9_trace_case_c008_fixed_reports_the_ledger():
    case = _trial("fixed")
    assert case["trial"]["lab8_pass"] is True
    assert _grade(case).value is True
