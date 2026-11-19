# Disney Pin News feed

Public RSS feed: https://illuminations82.github.io/disney-pin-news/feed.xml
Web view: https://illuminations82.github.io/disney-pin-news/

- `sources.json` - feeds pulled automatically. `"filter": true` keeps only items matching `keyword_filter` (for general Disney news sites).
- `daily/YYYY-MM-DD.md` - hand-curated daily roundups (Instagram, Reddit, blogs that block bots). See `daily/README.md`.
- `scripts/build_feed.py` - builds `docs/feed.xml`, `docs/index.html` and keeps a 90-day archive in `data/items.json`. Standard library only.
- `.github/workflows/build-feed.yml` - rebuilds every 2 hours and whenever a roundup or source change is pushed. GitHub Pages serves `docs/`.

Build locally (needs a Python with a working `xml.parsers.expat`, e.g. `python3.12`):

    python3.12 scripts/build_feed.py
