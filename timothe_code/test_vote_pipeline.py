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
    ("", None),
    (None, None),
])
def test_parse_vote(text, label):
    assert vp.parse_vote(text) == label


def test_build_messages_uses_variant_and_text():
    with open(vp.PROMPTS_FILE, encoding="utf-8") as f:
        prompts = json.load(f)
    dp = {"text_content": {"title": "proposition de loi visant \u00e0 tester", "voted_text": "Article 1er\nX."}}
    plain = vp.build_messages(dp, "neutre", prompts)
    sim = vp.build_messages(dp, "simulation", prompts)
    assert len(plain) == 1 and plain[0]["role"] == "user"
    assert "Proposition de loi visant \u00e0 tester" in plain[0]["content"] and "Article 1er\nX." in plain[0]["content"]
    assert sim[0]["role"] == "system" and len(sim) == 2
    assert "ABSTENTION" not in vp.build_messages(dp, "binaire", prompts)[0]["content"]
