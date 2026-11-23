import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import steering_articles as sa  # noqa: E402
import vote_pipeline as vp  # noqa: E402

LONG = "Une phrase assez longue pour compter comme un paragraphe de l'article, sans aucun doute. "
PAGE = """<html><head><title>Titre de secours</title>
<meta property="og:site_name" content="L'Exemple">
<meta content="Le titre de l'article" property="og:title">
<meta property="article:published_time" content="2025-02-01T08:00:00+01:00">
<script>var p = "<p>%s</p>";</script></head><body>
<nav><p>%s</p></nav>
<article><p>Premier <b>paragraphe</b>. %s</p><p>court</p>
<p>Abonnez-vous pour lire la suite de cet article et soutenir notre journal ind&eacute;pendant.</p>
<p>Second paragraphe. %s</p></article></body></html>""" % (LONG, LONG, LONG * 4, LONG * 4)


def test_meta_tags_read_either_attribute_order_and_keep_apostrophes():
    tags = sa.meta_tags(PAGE)
    assert tags["og:site_name"] == "L'Exemple" and tags["og:title"] == "Le titre de l'article"
    assert tags["article:published_time"].startswith("2025-02-01")


def test_publication_date_falls_back_on_the_time_tag_then_the_url():
    assert sa.publication_date(PAGE, sa.meta_tags(PAGE), "https://x.fr/a") == "2025-02-01"
    assert sa.publication_date('<time class="d" datetime="2025-03-04T10:00">4 mars</time>', {}, "https://x.fr/a") == "2025-03-04"
    assert sa.publication_date("", {}, "https://x.fr/2025/09/29/titre/") == "2025-09-29"
    assert sa.publication_date("", {"date": "hier"}, "https://x.fr/a") is None


def test_paragraphs_keep_the_article_text_only():
    paras = sa.paragraphs(PAGE)
    assert len(paras) == 2 and paras[0].startswith("Premier paragraphe. ") and paras[1].startswith("Second paragraphe. ")


def test_excerpt_cuts_at_a_sentence_end_and_marks_the_cut():
    paras = ["Un. Deux. Trois.", "Quatre. Cinq. Six."]
    assert sa.excerpt(paras, 100) == "Un. Deux. Trois.\nQuatre. Cinq. Six."
    assert sa.excerpt(paras, 30) == "Un. Deux. Trois.\nQuatre. Cinq. " + sa.CUT_MARK
    assert sa.excerpt(paras, 16) == "Un. Deux. Trois. " + sa.CUT_MARK


def test_french_date():
    assert sa.french_date("2025-02-01") == "1er f\u00e9vrier 2025" and sa.french_date("2026-08-14") == "14 ao\u00fbt 2026"


def test_level_fields_mix_left_and_right_articles():
    rows = [{"side": side, "outlet": "%s%d" % (side, k), "url": "u-%s-%d" % (side, k), "date": "2025-02-01", "title": "T"}
            for side in sa.SIDES for k in range(5)]
    texts = {r["url"]: "texte" for r in rows}
    fields = sa.level_fields("B1", rows, texts)
    assert sorted(fields) == ["articles_%d" % level for level in range(5)]
    for level in range(5):
        block = fields["articles_%d" % level]
        assert block.count("] left") == level and block.count("] right") == 4 - level
        assert block.startswith("[1] ") and "[4] " in block and "1er f\u00e9vrier 2025" in block
    assert "left0" in fields["articles_1"] and "right4" not in fields["articles_0"]
    del texts["u-right-0"], texts["u-right-1"]
    assert sa.level_fields("B1", rows, texts) is None


def test_extra_fields_merge_the_local_file(tmp_path, monkeypatch):
    shared, local = tmp_path / "extra.json", tmp_path / "local.json"
    shared.write_text(json.dumps({"B1": {"arg_pour": "a"}, "B2": {"arg_pour": "b"}}), encoding="utf-8")
    local.write_text(json.dumps({"B1": {"articles_0": "c"}}), encoding="utf-8")
    monkeypatch.setattr(vp, "EXTRA_FIELDS_FILE", str(shared))
    monkeypatch.setattr(vp, "LOCAL_EXTRA_FIELDS_FILE", str(local))
    monkeypatch.setattr(vp, "_extra_fields", None)
    assert vp.extra_fields() == {"B1": {"arg_pour": "a", "articles_0": "c"}, "B2": {"arg_pour": "b"}}


def test_api_key_prefers_the_chosen_environment_variable(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="from-file"\n', encoding="utf-8")
    monkeypatch.setattr(vp, "API_KEY_ENV", "TEST_CHOSEN_KEY")
    monkeypatch.setattr(vp, "ENV_FILE", str(env_file))
    monkeypatch.setenv("TEST_CHOSEN_KEY", "chosen")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-environment")
    assert vp.api_key() == "chosen"
    monkeypatch.delenv("TEST_CHOSEN_KEY")
    assert vp.api_key() == "from-file"
    monkeypatch.setattr(vp, "ENV_FILE", str(tmp_path / "missing"))
    assert vp.api_key() == "from-environment"
