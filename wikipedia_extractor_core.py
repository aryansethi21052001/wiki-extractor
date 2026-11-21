import os
import re
import requests
from datetime import datetime
from urllib.parse import quote
from bs4 import BeautifulSoup


# ===========================================================================
# Constants
# ===========================================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

WIKI_BASE = "https://en.wikipedia.org/wiki/"

SKIP_SECTIONS = (
    "references", "notes", "footnotes", "citations", "sources",
    "external links", "see also", "further reading", "bibliography",
)

SKIP_CLASSES = (
    "infobox", "sidebar", "navbox", "vertical-navbox",
    "metadata", "ambox", "hatnote", "reflist",
    "mw-references-wrap", "navbox-inner", "navbox-styles",
    "mw-collapsible", "toc", "toccolours",
)


# ===========================================================================
# Main class: Wikipedia Article Extractor
# ===========================================================================

class WikipediaExtractor:
    """
    Represents one Wikipedia article.

    Each instance holds one article's page, link, and title, and can
    fetch the article, list its sections, and extract a section's content.
    """

    def __init__(self, query):
        self.error = None
        self.query = query
        self.url = ""
        self.soup = None
        self.title = None
        self._fetch()

    def _fetch(self):
        """Download the article and store its title, URL, and page content."""
        title = to_title(self.query)
        slug = re.sub(r"\s+", "_", title.strip())
        url = f"{WIKI_BASE}{quote(slug, safe='')}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return
            self.error = f"[NETWORK ERROR] {exc}"
            return
        except requests.exceptions.RequestException as exc:
            self.error = f"[NETWORK ERROR] {exc}"
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find("h1", id="firstHeading") is None:
            return
        if soup.find("div", class_="noarticletext") is not None:
            return

        h1 = soup.find("h1", id="firstHeading")
        main = h1.find("span", class_="mw-page-title-main")
        self.title = main.get_text(strip=True) if main else h1.get_text(strip=True)
        self.soup = soup
        self.url = resp.url

    def section_titles(self):
        """
        Return the article's section names as a list.

        The first item is always 'About', which refers to the intro
        paragraph(s) before the first heading. The rest are the article's
        main section headings, in the order they appear on the page.
        """
        body = self.soup.find("div", class_="mw-body-content")
        if body is None:
            return ["About"]
        titles = ["About"]
        for h2 in body.find_all("h2"):
            text = self._clean_heading(h2)
            if not text:
                continue
            if text.lower() in SKIP_SECTIONS:
                continue
            titles.append(text)
        return titles

    def extract(self, heading_text):
        """
        Extract one section and return it as a dict with 'title' and
        'blocks' keys. Each block is either a paragraph, a list, or a
        table.
        """
        if heading_text == "About":
            return self._extract_lead()

        body = self.soup.find("div", class_="mw-body-content")
        if body is None:
            return {"title": heading_text, "blocks": []}

        target_h2 = None
        for h2 in body.find_all("h2"):
            if self._clean_heading(h2) == heading_text:
                target_h2 = h2
                break
        if target_h2 is None:
            return {"title": heading_text, "blocks": []}

        return {"title": heading_text,
                "blocks": self._walk_until_next_h2(target_h2)}

    def _extract_lead(self):
        """Extract the intro paragraphs that come before the first heading."""
        body = self.soup.find("div", class_="mw-body-content")
        if body is None:
            return {"title": "About", "blocks": []}
        parser_output = body.find("div", class_="mw-parser-output")
        if parser_output is None:
            return {"title": "About", "blocks": []}
        return {"title": "About",
                "blocks": self._walk_until_next_h2(parser_output)}

    @staticmethod
    def _walk_until_next_h2(start_el):
        """
        Read everything from `start_el` up to the next section heading,
        and return the content as a list of blocks.
        """
        blocks = []
        for el in start_el.find_all_next():
            if el.name == "h2":
                break
            if el.name in ("p", "ul", "ol", "table"):
                if any(p.name in ("p", "ul", "ol", "table")
                       for p in el.parents if p.name != "[document]"):
                    continue
                if _in_skipped_container(el):
                    continue
                blocks.extend(_blocks_from_element(el))
            elif el.name in ("h3", "h4"):
                if _in_skipped_container(el):
                    continue
                _strip_inline_refs(el)
                text = el.get_text(" ", strip=True)
                if text:
                    blocks.append({"type": "subheading", "text": text})
        return blocks

    @staticmethod
    def _clean_heading(h2):
        """Return a section heading's text without the '[edit]' link."""
        for edit in h2.find_all("span", class_="mw-editsection"):
            edit.decompose()
        return h2.get_text(strip=True)


# ===========================================================================
# Stateless helpers
# ===========================================================================

def to_title(topic):
    """
    Turn whatever the user typed into Wikipedia title case.

    Each word is lowercased, then the first letter is capitalised.
    Letters after an apostrophe or hyphen are capitalised too.
    """
    def fix_word(w):
        w = w.lower()
        return re.sub(
            r"(^|['\-])([a-z])",
            lambda m: m.group(1) + m.group(2).upper(),
            w,
        )
    return " ".join(fix_word(w) for w in topic.split() if w)

def safe_filename(title):
    """Turn an article title into a safe filename (without the extension)."""
    stem = re.sub(r"[^\w\- ]", "", title).strip()
    stem = re.sub(r"\s+", "_", stem)
    return stem[:80] or "wikipedia_article"

def _strip_inline_refs(el):
    """Remove the small '[1]'-style citation markers from a content block."""
    for sup in el.find_all("sup"):
        classes = sup.get("class") or []
        if "mw-ref" in classes or "noprint" in classes:
            sup.decompose()
            continue
        if re.fullmatch(r"\[\d+\]", sup.get_text(strip=True)):
            sup.decompose()

def _in_skipped_container(el):
    """Return True if `el` is inside a part of the page we want to ignore."""
    for parent in el.parents:
        if parent.name == "[document]":
            break
        classes = parent.get("class") or []
        if any(c in SKIP_CLASSES for c in classes):
            return True
    return False

def _blocks_from_element(el):
    """Turn one page element (paragraph, list, or table) into content blocks."""
    classes = el.get("class") or []
    if any(c in SKIP_CLASSES for c in classes):
        return []

    _strip_inline_refs(el)
    blocks = []

    if el.name == "p":
        text = el.get_text(" ", strip=True)
        if text:
            blocks.append({"type": "paragraph", "text": text})
    elif el.name in ("ul", "ol"):
        items = [li.get_text(" ", strip=True)
                 for li in el.find_all("li", recursive=False)]
        items = [i for i in items if i]
        if items:
            blocks.append({"type": "list", "ordered": el.name == "ol",
                           "items": items})
    elif el.name == "table":
        rows = []
        for tr in el.find_all("tr"):
            cells = [c.get_text(" ", strip=True)
                     for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if rows:
            blocks.append({"type": "table", "rows": rows})
    return blocks

def numbered_filename(filename, taken_filenames):
    """
    Return a filename that is not in `taken_filenames`, by appending
    " (2)", " (3)", etc. before the extension.

    `taken_filenames` is any container supporting ``in`` (list, set).
    """
    if filename not in taken_filenames:
        return filename
    base, ext = os.path.splitext(filename)
    n = 2
    while True:
        candidate = f"{base} ({n}){ext}"
        if candidate not in taken_filenames:
            return candidate
        n += 1

def format_txt(article_title, article_url, sections):
    """
    Format the extracted sections as a single string.

    Returns the full document text with the same header and section
    formatting used by the original file-writing flow.
    """
    lines = []
    lines.append("=" * 70)
    lines.append(article_title)
    lines.append("=" * 70)
    lines.append(f"Source   : {article_url}")
    lines.append(f"Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("License  : Content from Wikipedia, CC BY-SA 4.0")
    lines.append("           https://creativecommons.org/licenses/by-sa/4.0/")
    lines.append("")

    for i, sec in enumerate(sections, start=1):
        lines.append("-" * 70)
        lines.append(f"{i}. {sec['title']}")
        lines.append("-" * 70)
        lines.append("")
        if not sec["blocks"]:
            lines.append("(no extractable content)")
            lines.append("")
            continue
        for block in sec["blocks"]:
            if block["type"] == "paragraph":
                lines.append(block["text"])
                lines.append("")
            elif block["type"] == "subheading":
                lines.append(f"### {block['text']}")
                lines.append("")
            elif block["type"] == "list":
                for n, item in enumerate(block["items"], start=1):
                    marker = f"{n}." if block["ordered"] else "-"
                    lines.append(f"  {marker} {item}")
                lines.append("")
            elif block["type"] == "table":
                for row in block["rows"]:
                    lines.append("  | " + " | ".join(row) + " |")
                lines.append("")

    lines.append("=" * 70)
    lines.append("End of document")
    lines.append("=" * 70)
    return "\n".join(lines) + "\n"