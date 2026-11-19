# Daily pin roundups

Each file named `YYYY-MM-DD.md` in this folder becomes one item in the feed
(and a page at `daily/YYYY-MM-DD.html`). Files with any other name are ignored.

## Format

```markdown
---
title: Daily Disney Pin Roundup - November 19, 2026
summary: One or two sentences shown in feed readers that only display a snippet.
date: 2026-11-19T13:00:00Z
---

## New releases
- **Pin name** - where / when, price, edition size. [Source](https://example.com/post)

## Events and announcements
- ...

## From Instagram and social
- **@account**: what they showed or announced. [Post](https://www.instagram.com/p/...)

![optional image](https://example.com/image.jpg)
```

All front-matter fields are optional: the title defaults to
"Daily Disney Pin Roundup - <date>" and the date to noon UTC that day.

Supported Markdown: `#`/`##`/`###` headings, `-` bullet lists, `**bold**`,
`*italic*`, `[links](https://...)`, and an image on its own line.

## What goes in a roundup

The automatic sources (see `sources.json`) already cover the pin blogs, so the
roundup is for things they miss:

- Instagram: official and community pin accounts (e.g. @disneypinsblog,
  @disneypins, @wdwnewstoday, @disneystore, @dlp.pintrading, Disney Store /
  shopDisney release posts, artist and fantasy-pin accounts the reader follows)
- Reddit r/DisneyPins and pin-trading Facebook/Discord announcements that were
  made public
- Blogs that block automated feed readers (WDW News Today pin tag, AllEars,
  Disney Food Blog merchandise posts)
- shopDisney / Disney Store release calendars and restocks

Keep it to what is new in the last 24 hours, link every claim to its source,
and skip the day if there is nothing new rather than padding it.
