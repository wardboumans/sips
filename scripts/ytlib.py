"""Shared helpers for the playlist scraper."""
import datetime, json, os, random, subprocess, sys, time

CACHE = os.environ.get("PL_CACHE", "_pl_cache")

# stderr fragments that mean "you are going too fast", not "this playlist is broken"
THROTTLE_SIGNS = (
    "429", "too many requests", "rate limit", "rate-limit",
    "sign in to confirm", "not a bot", "temporarily blocked",
    "unusual traffic", "http error 403", "failed to extract any player response",
)


def is_throttled(err):
    e = (err or "").lower()
    return any(s in e for s in THROTTLE_SIGNS)


def nap(seconds, jitter=0.35, why=None):
    """Sleep with jitter. Uniform delays look like a bot; jittered ones don't,
    and it keeps many playlists from landing on the same cadence."""
    if seconds <= 0:
        return
    d = seconds * (1 + random.uniform(-jitter, jitter))
    if why:
        print(f"      ... sleeping {d:.0f}s ({why})", flush=True)
    time.sleep(d)


def ytdlp(args):
    p = subprocess.run(["yt-dlp", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def flat_json(url, base, retries=3, backoff=60):
    """Run yt-dlp --dump-single-json, return (data, error).

    Outer retry layer. yt-dlp already backs off inside an extraction (see
    base_args); this catches the case where it gives up and exits, and gives
    throttling a much longer cool-off than an ordinary failure - hammering a
    429 is how you earn a multi-hour block instead of a multi-minute one.
    """
    err = "no attempt"
    for attempt in range(retries):
        rc, out, e = ytdlp([*base, "--dump-single-json", url])
        if out.strip():
            try:
                return json.loads(out), None
            except json.JSONDecodeError as ex:
                err = f"bad json: {ex}"
        else:
            err = (e or "").strip()[-400:] or "no output"

        if attempt == retries - 1:
            break
        throttled = is_throttled(err)
        wait = backoff * (4 ** attempt) if throttled else backoff * (2 ** attempt)
        nap(wait, why=("throttled, backing off" if throttled else
                       f"retry {attempt + 2}/{retries}"))
    return None, err


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
    # Let yt-dlp pace and retry itself where it can - it backs off *within* an
    # extraction, which an outer retry cannot do.
    #   --sleep-requests   spaces its own API calls (a long playlist paginates)
    #   --retry-sleep      exponential 5s -> 300s cap, for HTTP and extractor
    # (--sleep-interval is download-only, so it does nothing for us here.)
    rq = getattr(ns, "sleep_requests", None)
    if rq:
        args += ["--sleep-requests", str(rq)]
    args += [
        "--retries", "10",
        "--extractor-retries", "5",
        "--retry-sleep", "http:exp=5:300",
        "--retry-sleep", "extractor:exp=5:300",
    ]
    return args + auth_args(ns)


def add_pacing_args(ap, sleep=2.5, sleep_requests=1.0,
                    pause_every=50, pause_for=45):
    """Shared rate-limit knobs. Defaults are deliberately unhurried - a full
    crawl is a background job, and a block costs far more than the wait."""
    ap.add_argument("--sleep", type=float, default=sleep,
                    help="seconds between playlists (jittered)")
    ap.add_argument("--sleep-requests", type=float, default=sleep_requests,
                    help="seconds between yt-dlp's own HTTP requests")
    ap.add_argument("--pause-every", type=int, default=pause_every,
                    help="take a longer break every N playlists (0 disables)")
    ap.add_argument("--pause-for", type=float, default=pause_for,
                    help="how long that longer break is")


def maybe_pause(n, ns):
    """Longer breather every --pause-every playlists."""
    if ns.pause_every and n and n % ns.pause_every == 0:
        nap(ns.pause_for, why=f"breather after {n} playlists")


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
        "upload_date": upload_day(v),
    }


def upload_day(v):
    """YYYYMMDD for an entry.

    --dump-single-json carries `timestamp` but not `upload_date`: that one is
    a derived field yt-dlp only materialises for output templates (--print).
    So derive it, and fall back to the key in case a future version emits it.
    """
    day = v.get("upload_date")
    if day:
        return str(day)
    ts = v.get("timestamp") or v.get("release_timestamp")
    if not ts:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            ts, datetime.timezone.utc).strftime("%Y%m%d")
    except (OSError, OverflowError, ValueError):
        return None


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
