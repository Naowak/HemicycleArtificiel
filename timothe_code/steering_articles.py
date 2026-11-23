"""Real press articles for the prompt steering experiment (docs/timothe_steering.md).

steering_articles.json lists, for each bill, articles of left-leaning and right-leaning outlets that defend
the position their camp took on the bill. `build` downloads them, keeps a short excerpt of each and writes
the placeholders {articles_0} ... {articles_4}: four articles, of which 0 to 4 come from the left-leaning
outlets. The texts stay out of git (copyright); only the list of links is versioned.

    python timothe_code/steering_articles.py check <url>   # what would be kept of one article
    python timothe_code/steering_articles.py build         # -> extra_fields_local.json
"""

import argparse
import html
import json
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vote_pipeline as vp  # noqa: E402

ARTICLES_FILE = os.path.join(vp.HERE, "steering_articles.json")
TEXTS_FILE = os.path.join(vp.HERE, "steering_articles_text.json")
N_ARTICLES = 4
SIDES = ("left", "right")
MAX_ARTICLE_CHARS = 1500
MIN_ARTICLE_CHARS = 500
MIN_PARAGRAPH_CHARS = 60
CUT_MARK = "[...]"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
FETCH_TIMEOUT_S = 30
MONTHS = ("janvier", "f\u00e9vrier", "mars", "avril", "mai", "juin", "juillet", "ao\u00fbt", "septembre", "octobre",
          "novembre", "d\u00e9cembre")

META_TAG_RE = re.compile(r"(?i)<meta\b[^>]*>")
ATTRIBUTE_RE = re.compile(r"""([a-zA-Z:-]+)\s*=\s*(["'])(.*?)\2""", re.S)
DATE_TAGS = ("article:published_time", "og:article:published_time", "date", "dc.date", "dc.date.issued", "parsely-pub-date")
TIME_TAG_RE = re.compile(r"""(?i)<time\b[^>]*\bdatetime=["'](\d{4}-\d{2}-\d{2})""")
URL_DATE_RE = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/")
NOT_TEXT_RE = re.compile(r"(?is)<(script|style|nav|footer|aside|figure|form|noscript)\b.*?</\1>")
ARTICLE_RE = re.compile(r"(?is)<article\b.*?</article>")
PARAGRAPH_RE = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")
BODY_RE = re.compile(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"')
SITE_NOTICE_RE = re.compile(r"(?i)vous devez \u00eatre connect|abonnez-vous|aux abonn\u00e9s|d\u00e9j\u00e0 abonn\u00e9|newsletter|cookies")
BLOCKED_RE = re.compile(r"(?i)just a moment|attention required|access denied")  # anti-bot pages
DATE_RE = re.compile(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})')


def fetch_html(url):
    out = subprocess.run(["curl", "-sL", "--compressed", "--max-time", str(FETCH_TIMEOUT_S), "-A", USER_AGENT, url],
                         capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")


def meta_tags(page):
    """{property or name: content} of the <meta> tags of a page; the first tag of each kind wins."""
    out = {}
    for tag in META_TAG_RE.findall(page):
        attrs = {name.lower(): value for name, _, value in ATTRIBUTE_RE.findall(tag)}
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            out.setdefault(key.lower(), html.unescape(attrs["content"]).strip())
    return out


def clean(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", "", fragment))).strip()


def paragraphs(page):
    """Paragraphs of the article in a page: the structured-data body when it is longer, else the <p> tags."""
    stripped = NOT_TEXT_RE.sub(" ", page)
    blocks = ARTICLE_RE.findall(stripped)
    found = []
    for block in ([max(blocks, key=len)] if blocks else []) + [stripped]:
        found = []
        for raw in PARAGRAPH_RE.findall(block):
            text = clean(raw)
            if len(text) >= MIN_PARAGRAPH_CHARS and text not in found and not SITE_NOTICE_RE.search(text):
                found.append(text)
        if sum(map(len, found)) >= MIN_ARTICLE_CHARS:
            break
    body = BODY_RE.search(page)
    if body:
        try:
            lines = [clean(line) for line in json.loads('"%s"' % body.group(1)).split("\n")]
        except ValueError:
            lines = []
        lines = [line for line in lines if line]
        if sum(map(len, lines)) > sum(map(len, found)):
            return lines
    return found


def excerpt(paras, max_chars=MAX_ARTICLE_CHARS):
    """The start of an article, up to max_chars and cut at a sentence end, with a mark when the article goes on."""
    kept, total = [], 0
    for p in paras:
        if total + len(p) > max_chars:
            cut = p[:max_chars - total]
            end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
            if end > 0:
                kept.append(cut[:end + 1])
            break
        kept.append(p)
        total += len(p)
    text = "\n".join(kept)
    return text if sum(map(len, kept)) == sum(map(len, paras)) else (text + " " + CUT_MARK).strip()


def publication_date(page, tags, url):
    """YYYY-MM-DD from the page's metadata, else its first <time> tag, else a date in the URL, else None."""
    for tag in DATE_TAGS:
        if re.match(r"\d{4}-\d{2}-\d{2}", tags.get(tag) or ""):
            return tags[tag][:10]
    found = DATE_RE.search(page) or TIME_TAG_RE.search(page)
    if found:
        return found.group(1)
    in_url = URL_DATE_RE.search(url)
    return "-".join(in_url.groups()) if in_url else None


def read_article(url):
    page = fetch_html(url)
    tags = meta_tags(page)
    title = tags.get("og:title") or clean((re.search(r"(?is)<title[^>]*>(.*?)</title>", page) or [None, ""])[1])
    return {"outlet": tags.get("og:site_name") or re.sub(r"^www\.", "", url.split("/")[2]), "title": title,
            "date": publication_date(page, tags, url),
            "text": "" if BLOCKED_RE.search(title) else excerpt(paragraphs(page))}


def french_date(iso):
    year, month, day = (int(x) for x in iso.split("-"))
    return "%d%s %s %d" % (day, "er" if day == 1 else "", MONTHS[month - 1], year)


def article_block(number, row, text):
    head = "[%d] %s" % (number, row["outlet"]) + (", " + french_date(row["date"]) if row.get("date") else "")
    return "%s\n%s\n%s" % (head, row["title"], text)


def level_fields(bill_id, rows, texts):
    """{"articles_0" ... "articles_4"}: four articles, `level` of them from the left-leaning outlets.

    Each side's articles are used in the order of the file, so a level adds one left article to the previous
    one and drops one right article. None when a side has fewer than four usable articles.
    """
    by_side = {side: [r for r in rows if r["side"] == side and r["url"] in texts][:N_ARTICLES] for side in SIDES}
    if any(len(v) < N_ARTICLES for v in by_side.values()):
        return None
    fields = {}
    for level in range(N_ARTICLES + 1):
        chosen = by_side["left"][:level] + by_side["right"][:N_ARTICLES - level]
        random.Random("%s-%d" % (bill_id, level)).shuffle(chosen)
        fields["articles_%d" % level] = "\n\n".join(article_block(i + 1, r, texts[r["url"]]) for i, r in enumerate(chosen))
    return fields


def build():
    with open(ARTICLES_FILE, encoding="utf-8") as f:
        articles = json.load(f)
    texts = {}
    if os.path.exists(TEXTS_FILE):
        with open(TEXTS_FILE, encoding="utf-8") as f:
            texts = json.load(f)
    for rows in articles.values():
        for row in rows:
            if row["url"] not in texts:
                text = read_article(row["url"])["text"]
                if len(text) >= MIN_ARTICLE_CHARS:
                    texts[row["url"]] = text
                else:
                    print("unusable (%d characters): %s" % (len(text), row["url"]))
    with open(TEXTS_FILE, "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False, indent=1)
    fields = {}
    for bill_id, rows in articles.items():
        levels = level_fields(bill_id, rows, texts)
        if levels:
            fields[bill_id] = levels
        else:
            print("skipped, fewer than %d usable articles on a side: %s" % (N_ARTICLES, bill_id))
    with open(vp.LOCAL_EXTRA_FIELDS_FILE, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=1)
    print("%d bills with articles written to %s" % (len(fields), vp.LOCAL_EXTRA_FIELDS_FILE))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["check", "build"])
    parser.add_argument("url", nargs="?")
    args = parser.parse_args()
    if args.step == "build":
        build()
    else:
        a = read_article(args.url)
        print("outlet: %s | date: %s | kept characters: %d%s\ntitle: %s\n\n%s" % (
            a["outlet"], a["date"], len(a["text"]), "" if len(a["text"]) >= MIN_ARTICLE_CHARS else " (UNUSABLE: too short)",
            a["title"], a["text"]))


if __name__ == "__main__":
    main()
