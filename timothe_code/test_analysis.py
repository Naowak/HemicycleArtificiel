import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analysis as an  # noqa: E402


def bill(i, left_vote):
    """Synthetic bill: LFI-NFP MPs vote `left_vote`, RN MPs the opposite, 3 MPs each."""
    votes = [{"deputy_id": "L%d" % k, "name": "L%d" % k, "group": "LFI-NFP", "vote": left_vote} for k in range(3)]
    votes += [{"deputy_id": "R%d" % k, "name": "R%d" % k, "group": "RN", "vote": -left_vote} for k in range(3)]
    return {"id": "B%d" % i, "votes": votes, "result": {"minority_share": 0.5},
            "group_positions": {"LFI-NFP": {"position": float(left_vote), "voters": 3},
                                "RN": {"position": float(-left_vote), "voters": 3}}}


DPS = [bill(i, v) for i, v in enumerate([1, -1, 1, 1, -1, 1, -1, -1, 1, 1])]


def test_lr_index():
    assert an.lr_index(DPS[0]) == 2.0
    assert an.lr_index(DPS[1]) == -2.0


def test_bootstrap_perfect_and_constant():
    rng = np.random.default_rng(0)
    a = {d["id"]: d["group_positions"]["LFI-NFP"]["position"] for d in DPS}
    same = an.bootstrap(a, a, rng)
    assert same["corr"] == 1.0 and same["agree"] == 1.0 and same["corr_ci"][0] > 0.99
    const = an.bootstrap(a, {k: 1.0 for k in a}, rng)
    assert const["corr"] is None and const["agree"] is not None


def test_pca_orientation_and_projection():
    left = {d["id"]: d["group_positions"]["LFI-NFP"]["position"] for d in DPS}
    right = {d["id"]: -v for d, v in zip(DPS, left.values())}
    m = an.pca_map(DPS, {"LFI-NFP": left, "RN": right, "always for": {d["id"]: 1.0 for d in DPS}, "model": left})
    assert m["actors"]["LFI-NFP"][0] < 0 < m["actors"]["RN"][0]
    assert np.allclose(m["actors"]["model"], m["actors"]["LFI-NFP"])
    assert m["actors"]["always for"][1] >= 0
    assert abs(m["explained"][0] - 1.0) < 1e-9 and len(m["mps"]) == 6
