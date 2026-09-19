/* Playlist browser. Vanilla JS, no build step.
   data.json is columnar:
     v: [id, title, duration, views, yyyymmdd]
     p: [id, title, modifiedDate, views, [videoIndex...]]            */

const $ = (s) => document.querySelector(s);

let VIDEOS = [], PLAYLISTS = [];
let videoPlaylists = [];           // video index -> [playlist index...]
let state = { view: "playlists", q: "", pl: null, sort: "date", dir: -1 };
let current = [];

/* ---------- formatting ---------- */
const pad = (n) => String(n).padStart(2, "0");

function fmtDur(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
function fmtViews(n) {
  if (!n) return "";
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return Math.round(n / 1e3) + "K";
  return String(n);
}
const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(d) {
  d = Number(d);
  if (!d || d < 19000000) return "";
  const y = Math.floor(d / 10000), m = Math.floor(d / 100) % 100, day = d % 100;
  return `${day} ${MON[m - 1] || "?"} ${y}`;
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
/* highlight every search term in a title */
function mark(text, terms) {
  let out = esc(text);
  if (!terms.length) return out;
  const re = new RegExp("(" + terms.map((t) =>
    t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
  return out.replace(re, "<mark>$1</mark>");
}

/* ---------- search ---------- */
const terms = () => state.q.toLowerCase().split(/\s+/).filter(Boolean);

function matches(haystack, ts) {
  for (const t of ts) if (!haystack.includes(t)) return false;
  return true;
}

/* ---------- table definitions ---------- */
const COLS = {
  videos: [
    { key: "idx",   label: "#",        cls: "idx",       sortable: false },
    { key: "title", label: "Title" },
    { key: "date",  label: "Uploaded", cls: "num" },
    { key: "dur",   label: "Length",   cls: "num" },
    { key: "views", label: "Views",    cls: "num hide-sm" },
  ],
  playlists: [
    { key: "idx",   label: "#",        cls: "idx",       sortable: false },
    { key: "thumb", label: "",         cls: "thumbcol",  sortable: false },
    { key: "title", label: "Playlist" },
    { key: "count", label: "Videos",   cls: "num" },
    { key: "dur",   label: "Length",   cls: "num hide-sm" },
    { key: "date",  label: "Updated",  cls: "num" },
  ],
};

/* ---------- filtering + sorting ---------- */
function computeVideos() {
  const ts = terms();
  const pool = state.pl !== null ? PLAYLISTS[state.pl][4] : VIDEOS.map((_, i) => i);
  const seen = new Set();
  const out = [];
  for (const i of pool) {
    if (seen.has(i)) continue;
    seen.add(i);
    if (ts.length && !matches(VIDEOS[i][1].toLowerCase(), ts)) continue;
    out.push(i);
  }
  const d = state.dir;
  const cmp = {
    title: (a, b) => VIDEOS[a][1].localeCompare(VIDEOS[b][1]) * d,
    dur:   (a, b) => (VIDEOS[a][2] - VIDEOS[b][2]) * d,
    views: (a, b) => (VIDEOS[a][3] - VIDEOS[b][3]) * d,
    date:  (a, b) => (VIDEOS[a][4] - VIDEOS[b][4]) * d,
  }[state.sort];
  if (cmp) out.sort(cmp);
  return out;
}

function playlistDur(p) {
  let t = 0;
  for (const i of p[4]) t += VIDEOS[i][2];
  return t;
}

function computePlaylists() {
  const ts = terms();
  const out = [];
  PLAYLISTS.forEach((p, i) => {
    if (ts.length && !matches(p[1].toLowerCase(), ts)) return;
    out.push(i);
  });
  const d = state.dir;
  const cmp = {
    title: (a, b) => PLAYLISTS[a][1].localeCompare(PLAYLISTS[b][1]) * d,
    count: (a, b) => (PLAYLISTS[a][4].length - PLAYLISTS[b][4].length) * d,
    views: (a, b) => (PLAYLISTS[a][3] - PLAYLISTS[b][3]) * d,
    date:  (a, b) => (Number(PLAYLISTS[a][2] || 0) - Number(PLAYLISTS[b][2] || 0)) * d,
    dur:   (a, b) => (playlistDur(PLAYLISTS[a]) - playlistDur(PLAYLISTS[b])) * d,
  }[state.sort];
  if (cmp) out.sort(cmp);
  return out;
}

/* ---------- rendering ---------- */
function renderHead() {
  const cols = COLS[state.view];
  $("#head").innerHTML = cols.map((c) => {
    if (c.sortable === false) return `<th class="${c.cls || ""}"></th>`;
    const on = state.sort === c.key;
    return `<th class="${c.cls || ""}${on ? " sorted" : ""}" data-sort="${c.key}">` +
           `${c.label}<span class="arrow">${on && state.dir > 0 ? "▲" : "▼"}</span></th>`;
  }).join("");
  $("#head").querySelectorAll("th[data-sort]").forEach((th) => {
    th.onclick = () => {
      const k = th.dataset.sort;
      // text sorts default A->Z, numbers default high->low
      if (state.sort === k) state.dir = -state.dir;
      else { state.sort = k; state.dir = k === "title" ? 1 : -1; }
      refresh();
    };
  });
}

function videoRow(i, n, ts) {
  const v = VIDEOS[i];
  const pls = videoPlaylists[i] || [];
  const chips = state.pl !== null ? "" :
    `<div class="pls">` + (pls.length
      ? pls.slice(0, 4).map((pi) =>
          `<button class="pl" data-pl="${pi}" title="${esc(PLAYLISTS[pi][1])}">${esc(PLAYLISTS[pi][1])}</button>`).join("") +
        (pls.length > 4 ? `<button class="pl none">+${pls.length - 4} more</button>` : "")
      : `<button class="pl none">no playlist</button>`) + `</div>`;
  const meta = [fmtDate(v[4]), fmtDur(v[2]), fmtViews(v[3]) && fmtViews(v[3]) + " views"]
    .filter(Boolean).join(" · ");
  return `<tr>
    <td class="idx">${n}</td>
    <td><a class="title" href="https://www.youtube.com/watch?v=${v[0]}" target="_blank"
           rel="noopener">${mark(v[1], ts)}</a>
        <div class="meta">${meta}</div>${chips}</td>
    <td class="num">${fmtDate(v[4])}</td>
    <td class="num">${fmtDur(v[2])}</td>
    <td class="num hide-sm">${fmtViews(v[3])}</td>
  </tr>`;
}

/* a playlist's thumbnail is just its first video's - derive it instead of
   storing signed sqp urls, which are longer and can expire */
function thumb(p) {
  if (!p[4].length) return `<div class="ph"></div>`;
  const vid = VIDEOS[p[4][0]][0];
  return `<img class="thumb" loading="lazy" decoding="async" width="120" height="68"
               src="https://i.ytimg.com/vi/${vid}/mqdefault.jpg" alt=""
               onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'ph'}))">`;
}

function playlistRow(i, n, ts) {
  const p = PLAYLISTS[i];
  const meta = [`${p[4].length} video${p[4].length === 1 ? "" : "s"}`,
                fmtDur(playlistDur(p)), fmtDate(p[2]) && "updated " + fmtDate(p[2])]
    .filter(Boolean).join(" · ");
  return `<tr>
    <td class="idx">${n}</td>
    <td class="thumbcol"><a href="https://www.youtube.com/playlist?list=${p[0]}"
        target="_blank" rel="noopener">${thumb(p)}</a></td>
    <td><a class="title" href="https://www.youtube.com/playlist?list=${p[0]}" target="_blank"
           rel="noopener">${mark(p[1], ts)}</a>
        <div class="meta">${meta}</div>
        <div class="pls"><button class="pl" data-pl="${i}">show ${p[4].length} videos</button></div></td>
    <td class="num">${p[4].length}</td>
    <td class="num hide-sm">${fmtDur(playlistDur(p))}</td>
    <td class="num">${fmtDate(p[2])}</td>
  </tr>`;
}

function renderRows() {
  const ts = terms();
  const fn = state.view === "videos" ? videoRow : playlistRow;
  let html = "";
  for (let n = 0; n < current.length; n++) html += fn(current[n], n + 1, ts);
  $("#rows").innerHTML = html;
}

function refresh() {
  current = state.view === "videos" ? computeVideos() : computePlaylists();
  renderHead();
  renderRows();

  const noun = state.view === "videos" ? "video" : "playlist";
  $("#count").textContent =
    `${current.length.toLocaleString()} ${noun}${current.length === 1 ? "" : "s"}` +
    (state.q || state.pl !== null ? " matching" : "");
  $("#empty").hidden = current.length > 0;

  const f = $("#filterBar");
  if (state.pl !== null) {
    f.hidden = false;
    $("#filterName").textContent = PLAYLISTS[state.pl][1];
    $("#filterYT").href = `https://www.youtube.com/playlist?list=${PLAYLISTS[state.pl][0]}`;
  } else f.hidden = true;

  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === state.view));
  syncHash();
}

/* ---------- url state ---------- */
let hashLock = false;
function syncHash() {
  if (hashLock) return;
  const p = new URLSearchParams();
  if (state.view !== "playlists") p.set("view", state.view);
  if (state.q) p.set("q", state.q);
  if (state.pl !== null) p.set("pl", PLAYLISTS[state.pl][0]);
  const h = p.toString();
  history.replaceState(null, "", h ? "#" + h : location.pathname);
}
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.view = p.get("view") === "videos" ? "videos" : "playlists";
  state.q = p.get("q") || "";
  const plid = p.get("pl");
  state.pl = plid ? PLAYLISTS.findIndex((x) => x[0] === plid) : -1;
  if (state.pl < 0) state.pl = null;
  $("#search").value = state.q;
}

/* ---------- events ---------- */
function setView(v) {
  if (state.view === v) return;
  state.view = v;
  state.sort = v === "videos" ? "date" : "date";
  state.dir = -1;
  if (v === "playlists") state.pl = null;
  refresh();
}

function wire() {
  let t;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    const val = e.target.value;
    t = setTimeout(() => {
      const q = val.trim();
      if (q === state.q) return;
      state.q = q;
      refresh();
      if (window.scrollY > 200) window.scrollTo({ top: 0 });
    }, 110);
  });

  document.querySelectorAll(".tab").forEach((b) =>
    b.addEventListener("click", () => setView(b.dataset.view)));

  $("#clearFilter").addEventListener("click", () => { state.pl = null; refresh(); });

  // playlist chips (delegated - rows are re-created constantly)
  $("#rows").addEventListener("click", (e) => {
    const b = e.target.closest("button.pl");
    if (!b || !b.dataset.pl) return;
    state.pl = Number(b.dataset.pl);
    state.view = "videos";
    state.sort = "date"; state.dir = -1;
    refresh();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== $("#search")) {
      e.preventDefault(); $("#search").focus(); $("#search").select();
    } else if (e.key === "Escape") {
      if ($("#search").value) { $("#search").value = ""; state.q = ""; refresh(); }
      else if (state.pl !== null) { state.pl = null; refresh(); }
    }
  });

  window.addEventListener("hashchange", () => {
    hashLock = true; readHash(); refresh(); hashLock = false;
  });
}

/* ---------- boot ---------- */
fetch("data.json", { cache: "no-cache" })  // revalidate: the daily job rewrites it
  .then((r) => {
    if (!r.ok) throw new Error(`data.json: ${r.status}`);
    return r.json();
  })
  .then((d) => {
    VIDEOS = d.v;
    PLAYLISTS = d.p;

    videoPlaylists = VIDEOS.map(() => []);
    PLAYLISTS.forEach((p, pi) => {
      for (const vi of p[4]) videoPlaylists[vi].push(pi);
    });

    document.title = `${d.channel} - Playlist Browser`;
    $("#channelName").textContent = d.channel || "Playlist Browser";
    $("#channelLink").href = d.channel_url || "https://www.youtube.com";

    const totalDur = VIDEOS.reduce((s, v) => s + v[2], 0);
    const days = Math.round(totalDur / 86400);
    $("#stats").textContent =
      `${VIDEOS.length.toLocaleString()} videos · ` +
      `${PLAYLISTS.length.toLocaleString()} playlists · ${days} days of footage`;

    if (d.updated_at) {
      $("#updated").textContent =
        "Updated " + new Date(d.updated_at).toLocaleString(undefined,
          { dateStyle: "medium", timeStyle: "short" });
    }

    readHash();
    wire();
    refresh();
  })
  .catch((err) => {
    $("#count").textContent = "Could not load data.json - " + err.message;
  });
