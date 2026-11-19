#!/usr/bin/env python3
"""Build the Disney Pin News RSS feed.

Pulls every source in sources.json, keeps pin-related items, merges them with
the hand-written daily summaries in daily/*.md, stores a rolling archive in
data/items.json and writes docs/feed.xml plus a small docs/index.html.

Standard library only, so it runs the same locally and in GitHub Actions.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sources.json"
ARCHIVE = ROOT / "data" / "items.json"
DAILY_DIR = ROOT / "daily"
OUT_DIR = ROOT / "docs"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130 Safari/537.36 DisneyPinNewsFeed/1.0")
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------- helpers
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", s or ""))).strip()


def excerpt(s: str, n: int = 320) -> str:
    t = strip_html(s)
    return t if len(t) <= n else t[: n].rsplit(" ", 1)[0] + "…"


def norm_link(u: str) -> str:
    u = re.sub(r"[?#].*$", "", (u or "").strip())
    return u.rstrip("/").replace("http://", "https://").replace("://www.", "://")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


OG_RE = [
    re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:url|twitter:image)["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|og:image:url|twitter:image)["\']', re.I),
]


def og_image(url: str) -> str:
    """Return the page's og:image / twitter:image URL, or "" if none or unreachable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=15) as r:
            head = r.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    for rx in OG_RE:
        m = rx.search(head)
        if m and m.group(1).startswith("http"):
            return html.unescape(m.group(1))
    return ""


def text_of(el, path: str) -> str:
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


# ---------------------------------------------------------------- parsing
def parse_feed(raw: bytes, source: str) -> list[dict]:
    root = ET.fromstring(raw)
    items: list[dict] = []
    if root.tag.endswith("feed"):  # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            body = text_of(e, "atom:content") or text_of(e, "atom:summary")
            items.append({
                "title": html.unescape(text_of(e, "atom:title")),
                "link": link,
                "date": text_of(e, "atom:published") or text_of(e, "atom:updated"),
                "body": body,
                "image": "",
                "source": source,
            })
    else:  # RSS 2.0
        for e in root.iter("item"):
            body = text_of(e, "content:encoded") or text_of(e, "description")
            image = ""
            for tag in ("media:content", "media:thumbnail"):
                m = e.find(tag, NS)  # Elements without children are falsy, so no `or` chaining
                if m is not None and m.get("url"):
                    image = m.get("url")
                    break
            enc = e.find("enclosure")
            if not image and enc is not None and (enc.get("type") or "").startswith("image"):
                image = enc.get("url", "")
            cats = " ".join((c.text or "") for c in e.findall("category"))
            items.append({
                "title": html.unescape(text_of(e, "title")),
                "link": text_of(e, "link"),
                "date": text_of(e, "pubDate") or text_of(e, "dc:date"),
                "body": body,
                "image": image,
                "categories": cats,
                "source": source,
            })
    return items


def finish_item(it: dict) -> dict | None:
    d = parse_date(it.get("date"))
    if not it.get("title") or not it.get("link") or d is None:
        return None
    image = it.get("image") or ""
    if not image:
        m = IMG_RE.search(it.get("body") or "")
        image = m.group(1) if m else ""
    return {
        "id": norm_link(it["link"]),
        "title": it["title"].strip(),
        "link": it["link"].strip(),
        "date": d.isoformat(),
        "summary": excerpt(it.get("body") or ""),
        "image": image,
        "source": it["source"],
        "kind": "article",
    }


# ---------------------------------------------------------------- daily summaries
def md_inline(s: str) -> str:
    s = html.escape(s, quote=False)
    # inline images (used at the start of roundup bullets) render as a picture above the text
    s = re.sub(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)\s*",
               r'<img src="\2" alt="\1" style="max-width:100%;max-height:360px;display:block;margin:6px 0"/>', s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", s)
    return s


def md_to_html(md: str) -> str:
    """Tiny Markdown subset: headings, bullet lists, images, links, bold, italics, paragraphs."""
    out, para, in_list = [], [], False

    def flush():
        nonlocal para
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para = []

    for line in md.splitlines():
        s = line.strip()
        img = re.fullmatch(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)", s)
        if not s:
            flush()
            if in_list:
                out.append("</ul>"); in_list = False
            continue
        if img:
            flush()
            out.append(f'<p><img src="{html.escape(img.group(2))}" alt="{html.escape(img.group(1))}"/></p>')
        elif s.startswith("#"):
            flush()
            if in_list:
                out.append("</ul>"); in_list = False
            level = min(len(s) - len(s.lstrip("#")) + 1, 4)
            out.append(f"<h{level}>{md_inline(s.lstrip('#').strip())}</h{level}>")
        elif re.match(r"[-*] ", s):
            flush()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + md_inline(s[2:]) + "</li>")
        else:
            para.append(s)
    flush()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def load_daily(site_url: str) -> list[dict]:
    items = []
    for p in sorted(DAILY_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md")):
        text = p.read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            _, fm, body = text.split("---", 2)
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
        day = p.stem
        published = parse_date(meta.get("date")) or datetime.fromisoformat(day + "T12:00:00+00:00")
        nice = datetime.fromisoformat(day).strftime("%B %-d, %Y")
        body_html = md_to_html(body)
        m = IMG_RE.search(body_html)
        items.append({
            "id": f"daily-{day}",
            "title": meta.get("title") or f"Daily Disney Pin Roundup - {nice}",
            "link": f"{site_url}daily/{day}.html" if site_url else "",
            "date": published.isoformat(),
            "summary": meta.get("summary") or excerpt(body_html),
            "html": body_html,
            "image": m.group(1) if m else "",
            "source": "Daily Roundup",
            "kind": "daily",
        })
    return items


# ---------------------------------------------------------------- output
def rss(cfg: dict, items: list[dict], site_url: str) -> str:
    f = cfg["feed"]
    ET.register_namespace("atom", NS["atom"])
    ET.register_namespace("content", NS["content"])
    ET.register_namespace("media", NS["media"])
    root = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(root, "channel")
    ET.SubElement(ch, "title").text = f["title"]
    ET.SubElement(ch, "link").text = site_url or "https://disneypinsblog.com/"
    ET.SubElement(ch, "description").text = f["description"]
    ET.SubElement(ch, "language").text = f.get("language", "en-us")
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(now_utc())
    ET.SubElement(ch, "ttl").text = "60"
    if site_url:
        ET.SubElement(ch, f"{{{NS['atom']}}}link",
                      {"href": site_url + "feed.xml", "rel": "self", "type": "application/rss+xml"})
    for it in items:
        e = ET.SubElement(ch, "item")
        ET.SubElement(e, "title").text = (
            it["title"] if it["kind"] == "daily" else f"{it['title']} ({it['source']})")
        if it.get("link"):
            ET.SubElement(e, "link").text = it["link"]
        ET.SubElement(e, "guid", {"isPermaLink": "false"}).text = it["id"]
        ET.SubElement(e, "pubDate").text = format_datetime(datetime.fromisoformat(it["date"]))
        ET.SubElement(e, "category").text = it["source"]
        desc = ""
        if it.get("image"):
            desc += f'<p><img src="{html.escape(it["image"])}" alt=""/></p>'
        if it["kind"] == "daily":
            desc += it["html"]
        else:
            desc += f"<p>{html.escape(it['summary'])}</p>"
            desc += f'<p>Source: <a href="{html.escape(it["link"])}">{html.escape(it["source"])}</a></p>'
        ET.SubElement(e, "description").text = desc
        if it.get("image"):
            ET.SubElement(e, f"{{{NS['media']}}}content", {"url": it["image"], "medium": "image"})
            ET.SubElement(e, f"{{{NS['media']}}}thumbnail", {"url": it["image"]})
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


PAGE_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#6b6b73;--card:#fff;--line:#e6e3dc;--accent:#2f4fb3}
@media (prefers-color-scheme:dark){:root{--bg:#141417;--fg:#ececf0;--muted:#a0a0aa;--card:#1d1d22;--line:#2e2e35;--accent:#8fa8ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px}h1{margin:0 0 4px}a{color:var(--accent)}
.sub{color:var(--muted);margin:0 0 20px}.item{display:flex;gap:14px;padding:14px 0;border-top:1px solid var(--line)}
.item img{width:88px;height:88px;object-fit:cover;border-radius:8px;flex:none;background:var(--line)}
.meta{color:var(--muted);font-size:13px}.item h2{font-size:17px;margin:0 0 4px}.item p{margin:4px 0 0;font-size:14px}
.daily{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
article img{max-width:100%;height:auto;border-radius:8px}
"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title>'
            f'<link rel="alternate" type="application/rss+xml" title="Disney Pin News" href="feed.xml">'
            f"<style>{PAGE_CSS}</style></head><body><main>{body}</main></body></html>\n")


def write_site(cfg: dict, items: list[dict], site_url: str) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "feed.xml").write_text(rss(cfg, items, site_url), encoding="utf-8")
    rows = []
    for it in items[:100]:
        d = datetime.fromisoformat(it["date"]).strftime("%b %-d, %Y")
        img = f'<img src="{html.escape(it["image"])}" alt="" loading="lazy">' if it.get("image") else ""
        link = it.get("link") or "#"
        rows.append(
            f'<div class="item{" daily" if it["kind"] == "daily" else ""}">{img}<div>'
            f'<div class="meta">{html.escape(it["source"])} · {d}</div>'
            f'<h2><a href="{html.escape(link)}">{html.escape(it["title"])}</a></h2>'
            f'<p>{html.escape(it["summary"])}</p></div></div>')
    head = (f'<h1>{html.escape(cfg["feed"]["title"])}</h1>'
            f'<p class="sub">{html.escape(cfg["feed"]["description"])} '
            f'Subscribe: <a href="feed.xml">RSS feed</a></p>')
    (OUT_DIR / "index.html").write_text(page(cfg["feed"]["title"], head + "".join(rows)), encoding="utf-8")
    ddir = OUT_DIR / "daily"
    ddir.mkdir(exist_ok=True)
    for it in items:
        if it["kind"] == "daily":
            day = it["id"].removeprefix("daily-")
            body = (f'<p class="meta"><a href="../index.html">Disney Pin News</a></p>'
                    f'<h1>{html.escape(it["title"])}</h1><article>{it["html"]}</article>')
            (ddir / f"{day}.html").write_text(page(it["title"], body), encoding="utf-8")


# ---------------------------------------------------------------- main
def main() -> int:
    cfg = json.loads(CONFIG.read_text())
    site_url = (cfg["feed"].get("site_url") or "").rstrip("/")
    site_url = site_url + "/" if site_url else ""
    kw = re.compile(cfg["keyword_filter"], re.I)

    archive: dict[str, dict] = {}
    if ARCHIVE.exists():
        archive = {it["id"]: it for it in json.loads(ARCHIVE.read_text())}

    failures = 0
    for src in cfg["sources"]:
        try:
            raw_items = parse_feed(fetch(src["url"]), src["name"])
        except Exception as exc:  # one bad source must not break the feed
            failures += 1
            print(f"  ! {src['name']}: {exc}", file=sys.stderr)
            continue
        kept = 0
        for raw in raw_items:
            if src.get("filter"):
                hay = " ".join([raw.get("title", ""), raw.get("categories", ""),
                                strip_html(raw.get("body", ""))[:600]])
                if not kw.search(raw.get("title", "")) and not kw.search(raw.get("categories", "")):
                    # body-only matches are noisy (e.g. "pin" in unrelated text); require a strong hit
                    if len(kw.findall(hay)) < 2:
                        continue
            it = finish_item(raw)
            if it and it["id"] not in archive:
                archive[it["id"]] = it
                kept += 1
            elif it:
                # refresh text, but keep the original date and any image already found
                archive[it["id"]].update({k: v for k, v in it.items()
                                          if k != "date" and not (k == "image" and not v)})
        print(f"  {src['name']}: {len(raw_items)} items, {kept} new")

    # de-duplicate the same story syndicated under slightly different URLs by title
    seen_titles: set[str] = set()
    cutoff = now_utc() - timedelta(days=cfg["feed"].get("archive_days", 90))
    articles = []
    for it in sorted(archive.values(), key=lambda x: x["date"], reverse=True):
        key = re.sub(r"\W+", "", it["title"].lower())
        if key in seen_titles or datetime.fromisoformat(it["date"]) < cutoff:
            continue
        seen_titles.add(key)
        articles.append(it)

    # Articles whose feed carries no picture (e.g. Laughing Place): use the page's og:image.
    # Each article is looked up once; image_checked stops repeat fetches on later runs.
    lookups = 0
    for it in articles:
        if it.get("image") or it.get("image_checked") or lookups >= 60:
            continue
        it["image"] = og_image(it["link"])
        it["image_checked"] = True
        lookups += 1
    if lookups:
        print(f"  og:image lookups: {lookups}, found {sum(1 for it in articles if it.get('image'))}/{len(articles)} with images")

    ARCHIVE.parent.mkdir(exist_ok=True)
    ARCHIVE.write_text(json.dumps(articles, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    daily = load_daily(site_url)
    items = sorted(articles + daily, key=lambda x: x["date"], reverse=True)
    items = items[: cfg["feed"].get("max_items_in_feed", 150)]
    write_site(cfg, items, site_url)
    print(f"Wrote {len(items)} items ({len(daily)} daily roundups); {failures} source(s) failed.")
    return 1 if failures == len(cfg["sources"]) else 0


if __name__ == "__main__":
    sys.exit(main())
