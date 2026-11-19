#!/usr/bin/env python3
"""Print the preview image (og:image / twitter:image) for each URL given.

Used by the daily roundup job to find a picture for each bullet:
    python3.12 scripts/og_image.py https://example.com/post [more urls]
Prints "<url> <image-url>" per line, with "-" when no image was found.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_feed import og_image  # noqa: E402

for url in sys.argv[1:]:
    if url.startswith(("http://", "https://")):
        print(url, og_image(url) or "-")
