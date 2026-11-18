"""Bonus: the Inspect AI port agrees with the pydantic-evals graders.

Run: python -m pytest -q -m student -o addopts= tests/test_bonus_inspect.py
Skipped when inspect-ai is not installed (it is not in the lab's requirements; see requirements-bonus.txt).
"""
import pytest

pytest.importorskip("inspect_ai")
pytestmark = pytest.mark.student

REAL_REPLIES = [
    "Dạ, LogiX đã hoàn 35.000đ cho đơn O-107.",
    "LogiX đã hoàn phí 120.000đ cho đơn O-515 của anh/chị ạ.",
    "Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.",
    "Dạ, anh/chị vui lòng cho LogiX xin mã đơn hàng để kiểm tra ạ.",
    "hoàn 35000 VND, về trong 3–5 ngày",
    "35,000 vnđ",
    "1.234.567đ",
    "hoàn 35.000đ và 5.000đ",
]


@pytest.mark.parametrize("text", REAL_REPLIES)
def test_bonus_amount_parsers_agree(text):
    from bonus.inspect_port import money_in
    from lab9.graders import reply_amounts

    assert money_in(text) == sum(reply_amounts(text))


def test_bonus_inspect_matches_pydantic_on_seeded_regression():
    from bonus.compare import compare
    from lab9.eval import load_spec

    n, trials, diffs, aggs = compare("seeded_regression", load_spec())
    assert trials == 70 and n == 210
    assert diffs == []
    assert aggs["reply_matches_ledger"] == (0.7857, 0.7857)
