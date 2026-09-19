#!/usr/bin/env python3
"""Full crawl: every playlist on a channel + the videos in each.

Slow (one request per playlist). Use update_playlists.py for daily refreshes.
Responses are cached in _pl_cache/ so re-runs are cheap.

  python scripts/build_playlists.py @sipslive
  python scripts/build_playlists.py @sipslive --cookies-from-browser firefox
"""
import argparse, datetime, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ytlib import (base_args, channel_url, flat_json, playlist_record,
                   read_cache, write_cache, write_json_atomic)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel", help="@handle, channel URL, or UC... id")
    ap.add_argument("--cookies-from-browser")
    ap.add_argument("--cookies")
    ap.add_argument("-o", "--output", default="data/channel_playlists.json")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    ap.add_argument("--sleep", type=float, default=0.4)
    a = ap.parse_args()

    ch = channel_url(a.channel)
    base = base_args(a)

    print(f"[1/2] listing playlists on {ch}/playlists ...", flush=True)
    tab, err = flat_json(f"{ch}/playlists", base)
    if tab is None:
        sys.exit(f"failed to list playlists: {err}")
    pls = [e for e in (tab.get("entries") or []) if e.get("id")]
    print(f"      found {len(pls)} playlists", flush=True)

    records, failed = [], []
    print("[2/2] expanding each playlist ...", flush=True)
    for i, pl in enumerate(pls, 1):
        pid = pl["id"]
        data = None if a.refresh else read_cache(pid)
        if data is None:
            data, err = flat_json(f"https://www.youtube.com/playlist?list={pid}", base)
            if data is None:
                print(f"  !! {i}/{len(pls)} {pid} FAILED: {err}", flush=True)
                failed.append({"id": pid, "title": pl.get("title"), "error": err})
                continue
            write_cache(pid, data)
            time.sleep(a.sleep)
        rec = playlist_record(pid, pl.get("title"), data)
        records.append(rec)
        print(f"  {i}/{len(pls)}  {rec['video_count']:4d} vids  {rec['title']}", flush=True)

    out = {
        "channel": tab.get("channel") or tab.get("uploader"),
        "channel_id": tab.get("channel_id") or tab.get("id"),
        "channel_url": tab.get("channel_url") or ch,
        "updated_at": datetime.datetime.now(datetime.timezone.utc)
                              .isoformat(timespec="seconds"),
        "playlist_count": len(records),
        "playlists": records,
    }
    if failed:
        out["failed"] = failed
    write_json_atomic(a.output, out)

    tot = sum(p["video_count"] for p in records)
    uniq = len({v["id"] for p in records for v in p["videos"]})
    print(f"\nwrote {a.output}: {len(records)} playlists, {tot} entries, "
          f"{uniq} unique videos, {len(failed)} failed")


if __name__ == "__main__":
    main()
