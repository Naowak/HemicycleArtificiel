import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vote_pipeline as vp  # noqa: E402


@pytest.mark.parametrize("text, label", [
    ("VOTE : POUR\nCe texte am\u00e9liore...", "for"),
    ("**VOTE : CONTRE**\nParce que...", "against"),
    ("Vote: abstention. Je suis partag\u00e9.", "abstain"),
    ("POUR. Le texte prot\u00e8ge...", "for"),
    ("Je ne peux pas exprimer d'opinion politique.", None),
    ("Je vais appr\u00e9cier le texte.\n\nPOUR \u2014 Le texte renforce...", "for"),
    ("Je ne peux pas voter, mais voici mon avis : **ABSTENTION**.", "abstain"),
    ("Pour \u00e9valuer ce texte, je pense qu'il faut voter contre.", None),
    ("Pour\nLe texte est utile.", "for"),
    ("", None),
    (None, None),
])
def test_parse_vote(text, label):
    assert vp.parse_vote(text) == label


def test_build_messages_uses_variant_and_text():
    with open(vp.PROMPTS_FILE, encoding="utf-8") as f:
        prompts = json.load(f)
    dp = {"date": "2025-01-01", "theme": None, "vote_title": "v",
          "text_content": {"title": "proposition de loi visant \u00e0 tester", "voted_text": "Article 1er\nX.",
                           "author": {"type": "government", "name": None, "group": None}}}
    plain = vp.build_messages(dp, "neutre", prompts)
    sim = vp.build_messages(dp, "simulation", prompts)
    assert len(plain) == 1 and plain[0]["role"] == "user"
    assert "Proposition de loi visant \u00e0 tester" in plain[0]["content"] and "Article 1er\nX." in plain[0]["content"]
    assert sim[0]["role"] == "system" and len(sim) == 2
    assert "ABSTENTION" not in vp.build_messages(dp, "binaire", prompts)[0]["content"]


DP = {"date": "2025-01-01", "theme": "logement", "vote_title": "l'ensemble ...",
      "text_content": {"title": "proposition de loi x", "voted_text": "Article 1er", "expose_motifs": None,
                       "author": {"type": "deputy", "name": "A B", "group": "SOC"}}}
PROMPTS = {"template": "{title}|{voted_text}|{question}",
           "variants": {"a": {"system": None, "question": "Q?"},
                        "b": {"template": "{title} par {author_label}, {author_group}{expose_motifs}", "system": "S {theme}",
                              "question": "", "enabled": False}}}


def test_variant_template_and_fields():
    assert vp.build_messages(DP, "a", PROMPTS) == [{"role": "user", "content": "Proposition de loi x|Article 1er|Q?"}]
    assert vp.build_messages(DP, "b", PROMPTS) == [
        {"role": "system", "content": "S logement"},
        {"role": "user", "content": "Proposition de loi x par un d\u00e9put\u00e9 du groupe SOC, SOC"}]
    assert vp.enabled_variants(PROMPTS) == ["a"]


def test_unknown_placeholder_is_explained():
    bad = {"template": "{titre}", "variants": {"a": {"system": None, "question": ""}}}
    with pytest.raises(KeyError, match="available"):
        vp.build_messages(DP, "a", bad)


def test_prompt_hash_follows_the_wording():
    m1 = vp.build_messages(DP, "a", PROMPTS)
    m2 = vp.build_messages(DP, "a", dict(PROMPTS, template="{title}|{question}"))
    assert vp.prompt_hash(m1) == vp.prompt_hash(vp.build_messages(DP, "a", PROMPTS)) != vp.prompt_hash(m2)


def test_select_datapoints_filters_and_ids(monkeypatch):
    all_dps = vp.ds.load()
    monkeypatch.setattr(vp, "DIVISIVE_ONLY", False)
    monkeypatch.setattr(vp, "MAX_TEXT_CHARS", None)
    assert len(vp.select_datapoints()) == len(all_dps)
    monkeypatch.setattr(vp, "MAX_TEXT_CHARS", 30000)
    assert all(d["text_content"]["voted_text_chars"] <= 30000 for d in vp.select_datapoints())
    monkeypatch.setattr(vp, "DIVISIVE_ONLY", True)
    assert all(d["result"]["minority_share"] >= 0.05 for d in vp.select_datapoints())
    picked = vp.select_datapoints(keys=["2", all_dps[4]["id"]])
    assert [d["id"] for d in picked] == [all_dps[1]["id"], all_dps[4]["id"]]


def test_extra_fields_and_missing_field(monkeypatch):
    monkeypatch.setattr(vp, "_extra_fields", {"B1": {"arg_pour": "A+", "edito_gauche": "E"}, "B2": {"arg_pour": "A2"}})
    prompts = {"template": "{title}|{arg_pour}", "variants": {"a": {"system": None, "question": ""},
                                                              "b": {"template": "{edito_gauche}", "system": None, "question": ""}}}
    b1, b2 = dict(DP, id="B1"), dict(DP, id="B2")
    assert vp.build_messages(b1, "a", prompts)[0]["content"] == "Proposition de loi x|A+"
    assert vp.build_messages(b1, "b", prompts)[0]["content"] == "E"
    with pytest.raises(vp.MissingField):
        vp.build_messages(b2, "b", prompts)
