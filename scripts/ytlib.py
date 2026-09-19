"""Shared helpers for the playlist scraper."""
import json, os, subprocess

CACHE = os.environ.get("PL_CACHE", "_pl_cache")


def ytdlp(args):
    p = subprocess.run(["yt-dlp", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def flat_json(url, base):
    """Run yt-dlp --dump-single-json, return (data, error)."""
    rc, out, err = ytdlp([*base, "--dump-single-json", url])
    if not out.strip():
        return None, (err.strip()[-400:] or "no output")
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, f"bad json: {e}"


def channel_url(ch):
    if not ch.startswith("http"):
        ch = f"https://www.youtube.com/{ch.lstrip('/')}"
    return ch.rstrip("/")


def base_args(ns, approximate_date=True):
    """Common yt-dlp flags. approximate_date makes the tab/playlist listings
    carry upload dates (derived from YouTube's "3 weeks ago" labels, so recent
    items are day-accurate and older ones are rounded) at no extra request."""
    args = ["--flat-playlist", "--no-warnings", "--ignore-errors"]
    if approximate_date:
        args += ["--extractor-args", "youtubetab:approximate_date"]
    return args + auth_args(ns)


def auth_args(ns):
    if getattr(ns, "cookies_from_browser", None):
        return ["--cookies-from-browser", ns.cookies_from_browser]
    if getattr(ns, "cookies", None):
        return ["--cookies", ns.cookies]
    return []


def video_record(v):
    """Slim video record. duration/view_count come free in flat mode."""
    return {
        "id": v["id"],
        "title": v.get("title"),
        "duration": v.get("duration"),
        "view_count": v.get("view_count"),
        "upload_date": v.get("upload_date"),
    }


def playlist_record(pid, title, data):
    """Slim playlist record built from a --flat-playlist dump of one playlist."""
    vids = [video_record(v) for v in (data.get("entries") or []) if v.get("id")]
    return {
        "id": pid,
        "title": title or data.get("title") or pid,
        "url": f"https://www.youtube.com/playlist?list={pid}",
        "modified_date": data.get("modified_date"),
        "view_count": data.get("view_count"),
        "video_count": len(vids),
        "videos": vids,
    }


def cache_path(pid):
    return os.path.join(CACHE, f"{pid}.json")


def read_cache(pid):
    p = cache_path(pid)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(pid, data):
    os.makedirs(CACHE, exist_ok=True)
    with open(cache_path(pid), "w", encoding="utf-8") as f:
        json.dump(data, f)


def write_json_atomic(path, obj, indent=2):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)
