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
never seen before are always rescanned, wherever they appear.

Defaults (`--min-scan 5`, `--stop-after 5`) assume a few uploads a day: a quiet
day is 5 playlist fetches, ~10 requests total instead of 539. A busy day walks
further on its own, because every change resets the unchanged-streak. Adding a
video to a playlist bumps that playlist to the top of the tab, so activity
cannot hide below the window — a hand-reordered *old* playlist can, which is
what the monthly `--full` run catches.

`--extractor-args youtubetab:approximate_date` gets upload dates out of the
listing for free. They come from YouTube's relative labels ("3 weeks ago"), so
recent uploads are day-accurate and older ones are rounded.

## Rate limiting

Nothing waits on these scripts, so they are paced to stay well clear of
YouTube's limits rather than to finish fast.

yt-dlp does the work it is better placed to do — `--sleep-requests` spaces its
own paginated API calls, and `--retry-sleep http:exp=5:300` /
`--retry-sleep extractor:exp=5:300` back off *inside* an extraction, which an
outer retry cannot. (`--sleep-interval` is download-only and does nothing
here, since we never download.)

On top of that the scripts add a jittered pause between playlists
(`--sleep`, default 2.5s), a longer breather every N playlists
(`--pause-every` / `--pause-for`, default 45s every 50), and an outer retry
for when yt-dlp gives up entirely. Responses that look like throttling — 429,
"Sign in to confirm you're not a bot", 403 — get a 4x longer cool-off than an
ordinary error.

CI runs slower still (`--sleep 5 --sleep-requests 2.5`, 120s every 20),
because Actions runners share datacenter IPs that YouTube throttles much more
aggressively than a home connection. If the scheduled job starts failing with
bot checks, that is why — lower the rate further, or run the refresh locally
and let CI only deploy.

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
