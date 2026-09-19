#!/usr/bin/env python3
"""Turn data/channel_playlists.json into a compact site/data.json.

Columnar + de-duplicated: each video is stored once and playlists reference it
by index, which is what keeps 5k videos across 539 playlists to a few hundred KB.

  python scripts/build_site_data.py
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", default="data/channel_playlists.json")
    ap.add_argument("-o", "--output", default="site/data.json")
    a = ap.parse_args()

    with open(a.input, encoding="utf-8") as f:
        snap = json.load(f)

    idx = {}          # video id -> index
    videos = []       # [id, title, duration, views, yyyymmdd]
    playlists = []    # [id, title, modified_date, views, [video indexes]]

    for p in snap["playlists"]:
        refs = []
        for v in p["videos"]:
            vid = v["id"]
            if vid not in idx:
                idx[vid] = len(videos)
                try:
                    day = int(v.get("upload_date") or 0)
                except (TypeError, ValueError):
                    day = 0
                videos.append([vid, v.get("title") or "",
                               v.get("duration") or 0, v.get("view_count") or 0, day])
            refs.append(idx[vid])
        playlists.append([p["id"], p.get("title") or "",
                          p.get("modified_date") or "", p.get("view_count") or 0, refs])

    out = {
        "channel": snap.get("channel"),
        "channel_url": snap.get("channel_url"),
        "updated_at": snap.get("updated_at"),
        "v": videos,
        "p": playlists,
    }

    os.makedirs(os.path.dirname(a.output) or ".", exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(a.output) / 1024
    print(f"wrote {a.output}: {len(videos)} videos, {len(playlists)} playlists, "
          f"{kb:.0f} KB")


if __name__ == "__main__":
    main()
