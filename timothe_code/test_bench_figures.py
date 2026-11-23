import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bench_figures as bf  # noqa: E402
from test_steering import BILLS  # noqa: E402


def answers(model, bill, labels):
    return [{"model": model, "id": bill, "label": label, "sample": k} for k, label in enumerate(labels)]


def test_vote_shares_count_unreadable_answers_apart():
    shares = bf.vote_shares(answers("m", "B0", ["for", "for", "against", None]))["m"]
    assert shares == {"for": 0.5, "abstain": 0.0, "against": 0.25, None: 0.25}


def test_stability_uses_only_bills_with_every_answer():
    records = (answers("m", "B0", ["for", "for", "for"]) + answers("m", "B1", ["for", "against", "abstain"])
               + answers("m", "B2", ["for", "abstain", "for"]) + answers("m", "B3", ["against", "for"]))
    assert bf.stability(records, 3)["m"] == {"same": pytest.approx(1 / 3), "both": pytest.approx(1 / 3), "n": 3}


def test_approval_by_camp_keeps_opposed_bills_only():
    assert bf.opposed_bills(BILLS) == {"B0": 1, "B1": -1}  # B2: both camps for; B3: the left has no clear stance
    records = (answers("m", "B0", ["for", "for", "against", "abstain"]) + answers("m", "B1", ["for", "against"])
               + answers("m", "B2", ["against"]))
    assert bf.approval_by_camp(records, BILLS)["m"] == {"left": 0.5, "right": 0.5}
