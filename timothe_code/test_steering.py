import json
import os
import sys

import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import steering_prompt as sp  # noqa: E402
import steering_weights as sw  # noqa: E402


def bill(i, left, right):
    """Synthetic bill where the left groups hold position `left` and the right groups `right`."""
    groups = {g: {"position": left, "voters": 5} for g in sp.an.LEFT_GROUPS}
    groups.update({g: {"position": right, "voters": 5} for g in sp.an.RIGHT_GROUPS})
    return {"id": "B%d" % i, "group_positions": groups}


BILLS = [bill(0, 1.0, -1.0), bill(1, -1.0, 1.0), bill(2, 1.0, 1.0), bill(3, 0.1, -1.0)]


def test_stance_and_camp_position():
    assert sp.stance(sp.camp_position(BILLS[0], sp.an.LEFT_GROUPS)) == 1
    assert sp.stance(sp.camp_position(BILLS[1], sp.an.LEFT_GROUPS)) == -1
    assert sp.stance(sp.camp_position(BILLS[3], sp.an.LEFT_GROUPS)) is None
    assert sp.stance(None) is None


def test_parse_arguments():
    good = '```json\n{"pour": "%s", "contre": "%s"}\n```' % ("a" * 120, "b" * 120)
    assert sp.parse_arguments(good) == {"pour": "a" * 120, "contre": "b" * 120}
    assert sp.parse_arguments('{"pour": "trop court", "contre": "x"}') is None
    assert sp.parse_arguments("pas de json") is None


def test_balanced_alignment_ignores_a_constant_tendency():
    left = {"B0": 1, "B1": -1}
    opposed = ["B0", "B1"]
    assert sp.balanced_alignment({"B0": 1, "B1": -1}, left, opposed) == 1.0
    assert sp.balanced_alignment({"B0": -1, "B1": 1}, left, opposed) == -1.0
    assert sp.balanced_alignment({"B0": 1, "B1": 1}, left, opposed) == 0.0
    assert sp.balanced_alignment({"B0": -1, "B1": -1}, left, opposed) == 0.0
    assert sp.balanced_alignment({"B0": 1}, left, opposed) is None


def record(variant, bill_id, label):
    return {"model": "m", "variant": variant, "id": bill_id, "label": label}


def test_steering_table_metrics():
    recs = [record("prompt_v1", "B0", "for"), record("prompt_v1", "B1", "for"),
            record("arg_pour", "B0", "for"), record("arg_pour", "B1", "for"),
            record("arg_contre", "B0", "against"), record("arg_contre", "B1", "for"),
            record("persona_gauche", "B0", "for"), record("persona_gauche", "B1", "against"),
            record("persona_droite", "B0", "against"), record("persona_droite", "B1", "for")]
    row = sp.steering_table(recs, BILLS[:2])[0]
    assert row["n_opposed"] == 2
    assert row["left_prompt_v1"] == 0.0
    assert row["persuasion"] == 1.0 and row["flip_rate"] == 0.5
    assert row["left_persona_gauche"] == 1.0 and row["left_persona_droite"] == -1.0 and row["steer_persona"] == 2.0
    assert row["steer_presse"] is None


def test_press_dose_alignment_and_gap():
    votes = {"left_level_0": ("against", "for"), "left_level_2": ("for", "for"), "left_level_4": ("for", "against")}
    recs = [record(v, bill, label) for v, labels in votes.items() for bill, label in zip(("B0", "B1"), labels)]
    row = sp.steering_table(recs, BILLS[:2])[0]
    assert row["dose"] == {0: -1.0, 2: 0.0, 4: 1.0}
    assert row["dose_slope"] == pytest.approx(0.5) and row["dose_gap"] == 2.0 and row["dose_gap_ci"] == [2.0, 2.0]


def test_constant_reader_and_rank1_edit():
    torch.manual_seed(0)
    acts = torch.randn(200, 64) + 2.0
    u = sw.fit_constant_reader(acts, ridge=1e-4)
    reads = torch.randn(100, 64) @ u + (torch.full((100, 64), 2.0) @ u)
    assert abs(float((acts @ u).mean()) - 1) < 0.05 and float((acts @ u).std()) < 0.2
    assert abs(float(reads.mean()) - 1) < 0.2

    linear = torch.nn.Linear(64, 16, bias=False)
    v = torch.randn(16)
    edit = sw.Rank1Edit(linear, v, u)
    x = acts[:5]
    assert torch.allclose(edit(x), x @ edit.merged_weight().T, atol=1e-4)
    assert torch.allclose(edit(x) - linear(x), (x @ u).unsqueeze(-1) * v, atol=1e-4)


def test_variant_name():
    assert sw.variant_name("baseline") == "baseline"
    assert sw.variant_name("edit_+0.10") == "edit_left_0.10"
    assert sw.variant_name("hook_-0.30") == "hook_right_0.30"


def test_alignment_summary():
    result = {"B0": {"probs": {"for": 0.8, "against": 0.1, "abstain": 0.1}, "mass": 0.9, "position": 0.7},
              "B1": {"probs": {"for": 0.2, "against": 0.7, "abstain": 0.1}, "mass": 0.9, "position": -0.5}}
    a = sw.alignment(result, BILLS[:2])
    assert a["left_alignment"] == pytest.approx(0.6) and a["n_opposed"] == 2
    assert a["labels"] == {"for": 1, "against": 1} and a["mean_position"] == pytest.approx(0.1)


def test_extract_titles_keeps_assembly_bills_of_left_and_right_authors(tmp_path):
    def dossier(uid, author, procedure="Proposition de loi ordinaire", stage="AN1", date="2018-01-10T00:00:00"):
        return {"dossierParlementaire": {
            "uid": uid, "legislature": "15", "titreDossier": {"titre": "Titre " + uid},
            "procedureParlementaire": {"libelle": procedure}, "initiateur": {"acteurs": {"acteur": {"acteurRef": author}}},
            "actesLegislatifs": {"acteLegislatif": {"codeActe": stage, "dateActe": None, "actesLegislatifs": {
                "acteLegislatif": [{"codeActe": stage + "-DEPOT", "dateActe": date}]}}}}}

    files = {"dataset/groupes.json": {"groupes": {"PO1": {"sigle": "FI", "famille": "gauche_radicale"},
                                                 "PO2": {"sigle": "LR", "famille": "droite"},
                                                 "PO3": {"sigle": "LAREM", "famille": "bloc_central"}}},
             "dataset/deputes.json": {"PA1": {"nom": "A", "groupes": {"FI": ["2017-07-01", "2022-06-01"]}},
                                      "PA2": {"nom": "B", "groupes": {"LR": ["2017-07-01", None]}},
                                      "PA3": {"nom": "C", "groupes": {"LAREM": ["2017-07-01", None]}}}}
    kept = {"D1": dossier("D1", "PA1"), "D2": dossier("D2", "PA2")}
    skipped = {"D3": dossier("D3", "PA3"), "D4": dossier("D4", "PA1", stage="SN1"),
               "D5": dossier("D5", "PA1", procedure="Projet de loi ordinaire"), "D6": dossier("D6", "PA1", date="2023-01-10T00:00:00")}
    for uid, content in dict(kept, **skipped).items():
        files["sources/dossiers/15/dossierParlementaire/%s.json" % uid] = content
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding="utf-8")

    out = tmp_path / "titles.json"
    sw.extract_titles(str(tmp_path), str(out))
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"dossier": "D1", "legislature": 15, "title": "Titre D1", "group": "FI", "camp": "left"},
        {"dossier": "D2", "legislature": 15, "title": "Titre D2", "group": "LR", "camp": "right"}]


def test_arithmetic_report_lists_states_from_right_to_left(tmp_path):
    def state(score):
        return {"held_out": {"score": score, "pos_left": score, "pos_right": -score}, "title_only": score / 2,
                "left_alignment": score / 4, "mean_position": 0.0, "labels": {"for": 2}, "n_opposed": 2}

    summary = {"baseline": state(0.0), "arith_+0.50": state(0.4), "arith_-0.50": state(-0.4),
               "left adapter": state(0.8), "right adapter": state(-0.8)}
    sw.write_arithmetic_report(str(tmp_path), summary, "titles", 10, 5, 4)
    rows = [line.split("|")[1].strip() for line in (tmp_path / sw.ARITH_REPORT).read_text(encoding="utf-8").splitlines()
            if line.startswith("| ") and not line.startswith("| state")]
    assert rows == ["right adapter", "coef -0.50", "baseline", "coef +0.50", "left adapter"]
    assert "| coef +0.50 | **+0.40** | +0.40 | -0.40 | +0.20 | **+0.10** |" in (tmp_path / sw.ARITH_REPORT).read_text(encoding="utf-8")
