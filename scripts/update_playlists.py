#!/usr/bin/env python3
"""Incremental refresh of data/channel_playlists.json.

The channel /playlists tab is ordered most-recently-updated first, so we rescan
the top slice rather than every playlist, walking further down only while
changes keep turning up. Playlist IDs we've never seen are always rescanned,
wherever they sit in the order.

Defaults assume a handful of uploads a day: a quiet day costs 5 playlist
fetches, and a busy one automatically walks further, since every change resets
the unchanged-streak. Adding a video to a playlist bumps it to the top of the
tab, so activity cannot hide below the window - but a hand-reordered old
playlist can, which is what the monthly --full run is for.

  python scripts/update_playlists.py @sipslive
  python scripts/update_playlists.py @sipslive --cookies-from-browser firefox
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ytlib import (add_pacing_args, base_args, channel_url, flat_json,
                   maybe_pause, nap, playlist_record, write_cache,
                   write_json_atomic, ytdlp)

CHANGELOG = "data/changelog.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel")
    ap.add_argument("--cookies-from-browser")
    ap.add_argument("--cookies")
    ap.add_argument("-s", "--snapshot", default="data/channel_playlists.json")
    ap.add_argument("--min-scan", type=int, default=5,
                    help="always rescan at least this many top playlists")
    ap.add_argument("--stop-after", type=int, default=5,
                    help="stop once this many consecutive playlists are unchanged")
    ap.add_argument("--max-scan", type=int, default=150, help="hard cap on rescans")
    ap.add_argument("--recent-uploads", type=int, default=50)
    ap.add_argument("--upload-tabs", default="videos",
                    help="channel tabs to check for playlist-less uploads")
    ap.add_argument("--full", action="store_true", help="rescan every playlist")
    ap.add_argument("--dry-run", action="store_true")
    add_pacing_args(ap)
    a = ap.parse_args()

    ch = channel_url(a.channel)
    base = base_args(a)

    if not os.path.exists(a.snapshot):
        sys.exit(f"{a.snapshot} not found - run build_playlists.py first")
    with open(a.snapshot, encoding="utf-8") as f:
        snap = json.load(f)
    old = {p["id"]: p for p in snap["playlists"]}

    # --- 1. the playlists tab (cheap: a handful of API pages) ----------------
    print("[1/3] listing playlists tab ...", flush=True)
    tab, err = flat_json(f"{ch}/playlists", base)
    if tab is None:
        sys.exit(f"failed to list playlists tab: {err}")
    order = [e for e in (tab.get("entries") or []) if e.get("id")]
    live_ids = [e["id"] for e in order]
    live_set = set(live_ids)
    print(f"      {len(order)} on the tab, {len(old)} in snapshot", flush=True)

    new_ids = {i for i in live_ids if i not in old}
    removed_ids = [i for i in old if i not in live_set]

    # --- 2. decide what to rescan --------------------------------------------
    forced = set(range(min(a.min_scan, len(order))))
    forced |= {i for i, e in enumerate(order) if e["id"] in new_ids}

    print(f"[2/3] rescanning (min {a.min_scan}, stop after {a.stop_after} "
          f"unchanged, cap {a.max_scan}) ...", flush=True)

    changes, fresh = [], {}
    streak = scanned = 0
    for i, e in enumerate(order):
        if scanned >= a.max_scan:
            break
        if not a.full and i not in forced and streak >= a.stop_after:
            continue

        pid = e["id"]
        data, err = flat_json(f"https://www.youtube.com/playlist?list={pid}", base)
        scanned += 1
        maybe_pause(scanned, a)
        nap(a.sleep)
        if data is None:
            print(f"  !! {pid} failed: {err}", flush=True)
            continue
        write_cache(pid, data)

        rec = playlist_record(pid, e.get("title"), data)
        fresh[pid] = rec

        prev = old.get(pid)
        prev_ids = {v["id"] for v in prev["videos"]} if prev else set()
        cur_ids = {v["id"] for v in rec["videos"]}
        added = [v for v in rec["videos"] if v["id"] not in prev_ids]
        gone = [v for v in (prev["videos"] if prev else []) if v["id"] not in cur_ids]

        if prev is None or added or gone:
            streak = 0
            changes.append({
                "playlist_id": pid,
                "playlist_title": rec["title"],
                "playlist_url": rec["url"],
                "is_new_playlist": prev is None,
                "added": added,
                "removed": gone,
            })
            tag = "NEW PLAYLIST" if prev is None else f"+{len(added)} -{len(gone)}"
            print(f"  [{i:3d}] {tag:12s} {rec['title']}", flush=True)
        else:
            streak += 1

    print(f"      rescanned {scanned}", flush=True)

    # --- 3. recent uploads, to catch videos in no playlist yet ---------------
    tabs = [t.strip() for t in a.upload_tabs.split(",") if t.strip()]
    print(f"[3/3] checking {a.recent_uploads} recent uploads from {tabs} ...", flush=True)
    recent = []
    for tab_name in tabs:
        rc, out, _ = ytdlp([*base, "--playlist-end", str(a.recent_uploads),
                            "--print", "%(id)s\t%(title)s", f"{ch}/{tab_name}"])
        for line in out.splitlines():
            vid, _, t = line.partition("\t")
            if vid.strip():
                recent.append({"id": vid.strip(), "title": t.strip(), "tab": tab_name})

    merged = dict(old)
    merged.update(fresh)
    for pid in removed_ids:
        merged.pop(pid, None)
    placed = {v["id"] for p in merged.values() for v in p["videos"]}
    orphans = [v for v in recent if v["id"] not in placed]

    # --- write ---------------------------------------------------------------
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ordered = [merged[i] for i in live_ids if i in merged]
    snap_out = {
        "channel": snap.get("channel"),
        "channel_id": snap.get("channel_id"),
        "channel_url": snap.get("channel_url"),
        "updated_at": stamp,
        "playlist_count": len(ordered),
        "playlists": ordered,
    }
    report = {
        "checked_at": stamp,
        "playlists_on_tab": len(order),
        "playlists_rescanned": scanned,
        "new_playlists": [c for c in changes if c["is_new_playlist"]],
        "updated_playlists": [c for c in changes if not c["is_new_playlist"]],
        "removed_playlist_ids": removed_ids,
        "new_videos_not_in_any_playlist": orphans,
    }

    if not a.dry_run:
        write_json_atomic(a.snapshot, snap_out)
        os.makedirs(os.path.dirname(CHANGELOG), exist_ok=True)
        with open(CHANGELOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")

    n_added = sum(len(c["added"]) for c in changes)
    print("\n" + "=" * 60)
    print(f"{stamp}  {snap.get('channel')}")
    print(f"  playlists: {len(ordered)} ({len(new_ids)} new, {len(removed_ids)} gone)"
          f"   rescanned {scanned}")
    print(f"  new videos in playlists: {n_added}")
    for c in changes:
        if not c["added"] and not c["removed"]:
            continue
        print(f"\n  {'NEW ' if c['is_new_playlist'] else ''}{c['playlist_title']}")
        for v in c["added"]:
            print(f"      + {v['id']}  {v['title']}")
        for v in c["removed"]:
            print(f"      - {v['id']}  {v['title']}")
    if orphans:
        print(f"\n  recent uploads in NO playlist ({len(orphans)}):")
        for v in orphans:
            print(f"      ? {v['id']}  {v['title']}")
    if a.dry_run:
        print("\n  (dry run - nothing written)")
    print("=" * 60)

    # so CI can tell whether anything moved
    if os.environ.get("GITHUB_OUTPUT"):
        changed = bool(changes or removed_ids)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
            f.write(f"new_videos={n_added}\n")
            f.write(f"new_playlists={len(new_ids)}\n")


if __name__ == "__main__":
    main()
