# Playlist Browser

A searchable, sortable index of a YouTube channel's playlists and videos —
because the YouTube channel page is not one.

- **Site:** `site/` — static, no build step, no dependencies.
- **Data:** `data/channel_playlists.json` — the canonical snapshot (committed,
  so the daily job can diff against it).
- **History:** `data/changelog.jsonl` — one line per run: new playlists, new
  videos per playlist, and uploads not in any playlist yet.

## How the scraping works

`yt-dlp --flat-playlist` on a `/playlists` URL stops one level early: you get
the playlists but never descend into them. So it's two passes — list the tab,
then flat-dump each playlist by ID.

A full crawl is one request per playlist. The daily job avoids that: the
playlists tab is ordered **most-recently-updated first**, so it rescans the top
slice and keeps walking down only while changes keep turning up. Playlist IDs
never seen before are always rescanned, wherever they appear. That's ~30
requests a day instead of 539.

`--extractor-args youtubetab:approximate_date` gets upload dates out of the
listing for free. They come from YouTube's relative labels ("3 weeks ago"), so
recent uploads are day-accurate and older ones are rounded.

## Commands

```bash
# one-time full crawl (slow; responses cached in _pl_cache/)
python scripts/build_playlists.py @sipslive

# daily incremental refresh
python scripts/update_playlists.py @sipslive

# regenerate the compact file the site reads
python scripts/build_site_data.py

# preview locally
python -m http.server 8765 --directory site
```

Unlisted playlists are invisible to a logged-out scrape. To include them, add
`--cookies-from-browser firefox` (this only works locally — CI has no cookies).

## Setup

1. Push to GitHub.
2. **Settings → Pages → Source: GitHub Actions.**
3. Optional: **Settings → Variables → Actions** → `CHANNEL` to point at a
   different channel (defaults to `@sipslive`).

The workflow runs daily at 05:17 UTC, commits any changed data, and deploys.
Run it by hand from the Actions tab; tick **full** to force a complete rescan.
