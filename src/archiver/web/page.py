"""The dashboard HTML (self-contained). Styled after the Nocturne design system:
a compact dark news station, populated entirely with real archive data."""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trump News Archive</title>
<!-- Inlined so the page never requests a file the app does not serve; a
     favicon 404 on every load is noise in the logs and in devtools. -->
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%239184d9'/%3E%3C/svg%3E">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<style>
  :root{
    color-scheme: dark;
    --bg:#161826;--surface:#232532;--surface2:#1c1e2b;--text:#e9e9ed;--accent:#9184d9;
    --divider:rgba(233,233,237,0.16);
    --n300:#cfd3e5;--n400:#b2b6ca;--n500:#9397ab;--n600:#75798c;--n800:#3f424d;--n900:#292b31;
    --a100:#f5f4ff;--a800:#423a6a;
    --radius-sm:4px;--radius-md:8px;
    --sp2:5.6px;--sp3:8.4px;--sp4:11.2px;--sp6:16.8px;--sp8:22.4px;
  }
  *{box-sizing:border-box}
  ::selection{background:color-mix(in srgb,var(--accent) 30%,transparent)}
  ::-webkit-scrollbar{width:8px;height:8px}
  ::-webkit-scrollbar-thumb{background:#3f424d;border-radius:8px}
  ::-webkit-scrollbar-track{background:transparent}
  @keyframes tickerScroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
  a{text-decoration:none;color:inherit}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:'Inter',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
  .muted{color:var(--n500)}
  .small{font-size:12px}
  .kicker{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--n500);margin-bottom:var(--sp3)}

  /* NAV */
  .nav{display:flex;align-items:center;gap:var(--sp6);padding:var(--sp3) var(--sp6);
    border-bottom:1px solid var(--divider);flex:none}
  .brand{display:flex;align-items:center;gap:8px;margin-right:var(--sp8)}
  .brand .mark{width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,var(--accent),var(--a800));flex:none}
  .brand .name{font-size:18px;font-weight:500;letter-spacing:-.01em}
  .tabs{display:flex;align-items:center;gap:var(--sp6);overflow-x:auto;min-width:0}
  .tab{font-size:14px;color:var(--n300);font-weight:500;padding:6px 2px;border-bottom:2px solid transparent;
    white-space:nowrap;cursor:pointer;background:none;border-top:none;border-left:none;border-right:none;font-family:inherit}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent)}
  .nav-right{margin-left:auto;display:flex;align-items:center;gap:var(--sp6);min-width:0}
  .live{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--n400);white-space:nowrap}
  .live .dot{width:7px;height:7px;border-radius:50%;background:#8fce6b;box-shadow:0 0 6px #8fce6b}
  .search{width:240px;min-height:34px;padding:6px 12px;font-size:13px;color:var(--text);
    background:var(--surface);border:1px solid var(--divider);border-radius:var(--radius-md);outline:none;font-family:inherit}
  .search:focus{border-color:var(--accent)}

  /* TICKER */
  .ticker{border-bottom:1px solid var(--divider);background:var(--surface2);overflow:hidden;flex:none;padding:7px 0}
  .ticker .row{display:flex;gap:36px;white-space:nowrap;width:max-content;animation:tickerScroll 60s linear infinite}
  .ticker:hover .row{animation-play-state:paused}
  .ticker .it{font-size:12px;display:inline-flex;gap:8px;align-items:baseline;padding:0 4px}
  .ticker .src{color:var(--accent);font-weight:600}
  .ticker .t{color:var(--n300)}

  /* GRID */
  .grid{flex:1;min-height:0;display:grid;grid-template-columns:250px minmax(0,1fr) 340px}
  .rail{flex:none;border-right:1px solid var(--divider);padding:var(--sp4);overflow-y:auto;min-height:0}
  .rail.right{border-right:none;border-left:1px solid var(--divider)}
  .center{min-width:0;overflow-y:auto;padding:var(--sp6)}
  .railtoggle{display:none}

  .srcrow{display:flex;align-items:center;justify-content:space-between;padding:7px 6px;border-radius:var(--radius-sm);cursor:pointer}
  .srcrow:hover{background:color-mix(in srgb,var(--text) 6%,transparent)}
  .srcrow.active{background:color-mix(in srgb,var(--accent) 14%,transparent)}
  .srcrow .nm{font-size:13px;font-weight:500}
  .srcrow .ct{font-size:12px;color:var(--n500)}
  .divider{height:1px;margin:var(--sp6) 0;background:linear-gradient(to right,transparent,var(--divider) 20px,var(--divider) calc(100% - 20px),transparent)}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{font-size:11px;padding:4px 10px;border-radius:20px;background:transparent;color:var(--n400);
    border:1px solid var(--divider);cursor:pointer;font-family:inherit}
  .chip:hover{border-color:var(--accent);color:var(--n300)}
  .chip.active{background:var(--a800);color:var(--a100);border-color:var(--accent)}

  .filterbar{display:flex;align-items:center;gap:8px;margin-bottom:var(--sp4);font-size:12px;color:var(--n400);flex-wrap:wrap;min-width:0}
  .filterbar .clear{color:var(--n500);font-size:11px;border:1px solid var(--divider);padding:2px 8px;border-radius:20px;cursor:pointer}
  .dates{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap;min-width:0}
  .dates input{background:var(--surface);color:var(--text);border:1px solid var(--divider);border-radius:var(--radius-md);
    padding:4px 8px;font-size:12px;font-family:inherit}

  .feed{display:flex;flex-direction:column;gap:var(--sp3)}
  .card{display:block;background:var(--surface2);border:1px solid transparent;border-radius:var(--radius-md);
    padding:var(--sp4);cursor:pointer}
  .card:hover{border-color:var(--divider)}
  .card.sel{background:var(--surface);border-color:var(--accent)}
  .card .meta{display:flex;align-items:center;gap:8px;margin-bottom:6px}
  .avatar{width:22px;height:22px;border-radius:6px;background:var(--n800);flex:none;display:flex;align-items:center;
    justify-content:center;font-size:9px;color:var(--n400);font-weight:700}
  .card .who{font-size:11px;color:var(--n500)}
  .badge{margin-left:auto;font-size:11px;padding:2px 9px;border-radius:20px;background:var(--a800);color:var(--a100);white-space:nowrap}

  /* SENTIMENT (FinBERT) */
  .sent{font-size:10px;letter-spacing:.05em;text-transform:uppercase;font-weight:600;white-space:nowrap;
    padding:2px 8px;border-radius:20px;border:1px solid transparent}
  .sent.positive{color:#a8dd8c;background:color-mix(in srgb,#8fce6b 15%,transparent);border-color:color-mix(in srgb,#8fce6b 40%,transparent)}
  .sent.negative{color:#f0a49e;background:color-mix(in srgb,#e0736d 15%,transparent);border-color:color-mix(in srgb,#e0736d 40%,transparent)}
  .sent.neutral{color:var(--n400);background:color-mix(in srgb,var(--text) 7%,transparent);border-color:var(--divider)}
  .sbar{display:flex;height:6px;border-radius:4px;overflow:hidden;background:var(--n900);margin:12px 0 10px}
  .sbar i{display:block;height:100%}
  .sbar .pos{background:#8fce6b}.sbar .neu{background:var(--n600)}.sbar .neg{background:#e0736d}
  .srow{display:flex;justify-content:space-between;align-items:baseline;font-size:11px;color:var(--n500);padding:2px 0}
  .srow b{color:var(--n300);font-weight:500;font-variant-numeric:tabular-nums}
  .smodel{margin-top:8px;padding-top:8px;border-top:1px solid var(--divider);font-size:10px;color:var(--n600)}

  /* PROVENANCE — publisher's words vs. machine paraphrase must never blur */
  .prov{font-size:9px;letter-spacing:.06em;text-transform:uppercase;font-weight:600;
    padding:2px 7px;border-radius:20px;border:1px solid transparent}
  .prov.pub{color:var(--n400);background:color-mix(in srgb,var(--text) 7%,transparent);border-color:var(--divider)}
  .prov.ai{color:#e8c98a;background:color-mix(in srgb,#e0b86d 14%,transparent);border-color:color-mix(in srgb,#e0b86d 40%,transparent)}
  .card .summary{margin-top:2px}
  .card .title{font-size:15px;font-weight:500;line-height:1.3;margin-bottom:4px}
  .card .summary{font-size:13px;color:var(--n400);line-height:1.45;
    display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden}
  .card .foot{display:flex;align-items:center;gap:10px;margin-top:8px}
  .card .link{font-size:11px;color:var(--accent)}
  .more{display:block;width:100%;margin:var(--sp6) 0 40px;padding:10px;background:var(--surface2);color:var(--text);
    border:1px solid var(--divider);border-radius:var(--radius-md);cursor:pointer;font-size:14px;font-family:inherit}
  .more:hover{border-color:var(--accent)}
  .empty{color:var(--n500);text-align:center;padding:60px 0}

  /* RIGHT PANEL */
  .panel{background:var(--surface);border-radius:var(--radius-md);padding:var(--sp4);margin-bottom:var(--sp4)}
  .panel .h{font-size:12px;color:var(--n500);margin-bottom:10px;display:flex;align-items:center;gap:8px}
  .soon{font-size:10px;letter-spacing:.04em;text-transform:uppercase;color:var(--accent);
    border:1px solid color-mix(in srgb,var(--accent) 50%,transparent);border-radius:20px;padding:1px 7px}
  .dd-title{font-size:16px;font-weight:500;line-height:1.3;margin-bottom:6px}
  .dd-body{font-size:13px;color:var(--n400);line-height:1.5;
    display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:10;line-clamp:10;overflow:hidden}
  .also a{display:block;font-size:13px;color:var(--text);padding:6px 0;border-bottom:1px solid var(--divider);line-height:1.35}
  .also a:hover{color:var(--accent)}

  /* IMPACT — a severity ladder, so the ramp reads as one scale. Kept on the
     left of the meta row while sentiment stays right: two colour-coded pills
     in the same place would be read as the same kind of thing. */
  .tier{display:inline-flex;align-items:center;gap:5px;font-size:10px;letter-spacing:.06em;
    text-transform:uppercase;font-weight:700;white-space:nowrap;padding:2px 8px;border-radius:20px;
    border:1px solid transparent}
  .tier i{width:6px;height:6px;border-radius:50%;flex:none;background:currentColor}
  .tier.critical{color:#ff6b6b;background:color-mix(in srgb,#ff6b6b 14%,transparent);border-color:color-mix(in srgb,#ff6b6b 45%,transparent)}
  .tier.high{color:#ffab5e;background:color-mix(in srgb,#ffab5e 14%,transparent);border-color:color-mix(in srgb,#ffab5e 42%,transparent)}
  .tier.notable{color:#9bb4e8;background:color-mix(in srgb,#9bb4e8 13%,transparent);border-color:color-mix(in srgb,#9bb4e8 38%,transparent)}
  .tier.routine{color:var(--n500);background:color-mix(in srgb,var(--text) 6%,transparent);border-color:var(--divider)}

  .topics{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
  .topic{font-size:10px;padding:2px 8px;border-radius:20px;background:color-mix(in srgb,var(--accent) 13%,transparent);
    color:#c3bbf0;border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);cursor:pointer;font-family:inherit}
  .topic:hover{border-color:var(--accent);color:var(--a100)}
  .ent{font-size:10px;padding:2px 8px;border-radius:20px;background:transparent;color:var(--n500);
    border:1px solid var(--divider)}
  .why{font-size:11px;color:var(--n600);margin-top:6px;font-style:italic}
  .tick{display:inline-flex;align-items:center;gap:5px;font-size:10px;padding:2px 8px;border-radius:20px;
    background:color-mix(in srgb,#6bc2a0 12%,transparent);color:#8fd8b8;
    border:1px solid color-mix(in srgb,#6bc2a0 34%,transparent);cursor:pointer;font-family:inherit;
    font-variant-numeric:tabular-nums}
  .tick:hover{border-color:#6bc2a0;color:#b7ead2}
  .tick .sym{font-weight:700;letter-spacing:.03em}
  .tick .mv{font-size:9px}
  .tick .mv.up{color:#8fce6b}.tick .mv.down{color:#e0736d}
  .chip .mv{margin-left:5px;font-size:10px;font-variant-numeric:tabular-nums}
  .chip .mv.up{color:#8fce6b}.chip .mv.down{color:#e0736d}

  .ibar{display:flex;flex-direction:column;gap:7px;margin:10px 0 4px}
  .icomp{display:grid;grid-template-columns:88px minmax(0,1fr) 34px;align-items:center;gap:8px;font-size:11px;color:var(--n500)}
  .icomp .track{height:5px;border-radius:4px;background:var(--n900);overflow:hidden}
  .icomp .fill{display:block;height:100%;background:var(--accent);border-radius:4px}
  .icomp b{color:var(--n300);font-weight:500;font-variant-numeric:tabular-nums;text-align:right}
  .icomp.unmeasured{opacity:.45}

  /* SORT + FILTER CONTROLS */
  .ctl{display:flex;align-items:center;gap:6px}
  .ctl label{font-size:11px;color:var(--n500);letter-spacing:.04em;text-transform:uppercase}
  .seg{display:inline-flex;border:1px solid var(--divider);border-radius:20px;overflow:hidden}
  .seg button{font-size:11px;padding:4px 11px;background:transparent;color:var(--n400);border:none;cursor:pointer;font-family:inherit}
  .seg button.active{background:var(--a800);color:var(--a100)}
  .seg button:not(.active):hover{color:var(--n300);background:color-mix(in srgb,var(--text) 6%,transparent)}

  /* Focus is never removed, only restyled — keyboard users need to see it. */
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:var(--radius-sm)}
  .card:focus-visible{outline-offset:-2px}

  /* LOADING — a shaped placeholder beats a spinner: the layout does not jump. */
  @keyframes shimmer{from{background-position:-320px 0}to{background-position:320px 0}}
  .skel{background:var(--surface2);border-radius:var(--radius-md);padding:var(--sp4);margin-bottom:var(--sp3)}
  .skel .ln{height:11px;border-radius:4px;margin-bottom:9px;
    background:linear-gradient(90deg,var(--n900) 0%,#32353f 50%,var(--n900) 100%);
    background-size:320px 100%;animation:shimmer 1.2s linear infinite}
  .skel .ln.s{width:38%}.skel .ln.m{width:82%}.skel .ln.l{width:64%}
  .empty h3{margin:0 0 6px;font-size:15px;font-weight:500;color:var(--n300)}
  .empty code{background:var(--n900);padding:1px 6px;border-radius:4px;font-size:12px}
  .kbd{font-size:10px;color:var(--n600);border:1px solid var(--divider);border-radius:4px;padding:1px 5px;font-family:inherit}

  /* RESPONSIVE — the page had no breakpoints at all, so a narrow window got a
     fixed 250+340px of chrome around a crushed feed. Columns now fold: the
     deep dive drops under the feed first, then the rail collapses behind a
     toggle and the whole page scrolls normally instead of trapping overflow. */
  @media (max-width:1200px){
    .grid{grid-template-columns:250px minmax(0,1fr)}
    .rail.right{grid-column:1 / -1;border-left:none;border-top:1px solid var(--divider);overflow:visible}
  }
  @media (max-width:860px){
    body{height:auto;overflow:auto}
    .grid{grid-template-columns:minmax(0,1fr);flex:none}
    .rail{border-right:none;border-bottom:1px solid var(--divider);overflow:visible}
    .rail.left{display:none}
    .rail.left.open{display:block}
    .rail.right{border-top:none}
    .center{overflow:visible;padding:var(--sp4)}
    .railtoggle{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-family:inherit;
      background:var(--surface);color:var(--n300);border:1px solid var(--divider);
      border-radius:20px;padding:5px 12px;cursor:pointer}
    .railtoggle.open{border-color:var(--accent);color:var(--a100)}
    .nav{flex-wrap:wrap;gap:var(--sp3) var(--sp4);padding:var(--sp3) var(--sp4)}
    .brand{margin-right:0}
    .nav-right{width:100%;margin-left:0;gap:var(--sp3)}
    .search{flex:1;width:auto;min-width:0}
    .tabs{order:3;width:100%;gap:var(--sp4)}
    .dates{margin-left:0;width:100%}
    .dates input{min-width:0;flex:1}
    .ctl{flex:1 1 auto;min-width:0}
    .filterbar{gap:6px}
    .card .title{font-size:14px}
    /* Last-resort guard: nothing should ever scroll the page sideways. */
    body,.grid,.center,.feed{max-width:100vw}
    .feed{overflow-x:hidden}
  }
  @media (max-width:520px){
    .ticker{display:none}
    .card .badge{margin-left:0}
    .card .meta{flex-wrap:wrap;gap:6px}
    .icomp{grid-template-columns:76px minmax(0,1fr) 30px}
  }
  @media (prefers-reduced-motion:reduce){
    .ticker .row{animation:none}
    .skel .ln{animation:none}
    *{transition:none!important}
  }
</style>
</head>
<body>
  <div class="nav">
    <div class="brand"><div class="mark"></div><div class="name">Trump News Archive</div></div>
    <div class="tabs" id="tabs"></div>
    <div class="nav-right">
      <button class="railtoggle" id="railtoggle" aria-expanded="false" aria-controls="leftrail">Filters</button>
      <div class="live"><span class="dot"></span><span id="livecount">loading…</span></div>
      <input class="search" id="q" placeholder="Search the archive…" autocomplete="off">
    </div>
  </div>

  <div class="ticker"><div class="row" id="ticker"></div></div>

  <div class="grid">
    <div class="rail left" id="leftrail">
      <div class="kicker">Impact</div>
      <div class="chips" id="tiers"></div>
      <div class="divider"></div>
      <div class="kicker">Topics</div>
      <div class="chips" id="topics"></div>
      <div class="divider"></div>
      <div class="kicker">Companies Trump named</div>
      <div class="chips" id="companies"></div>
      <div class="divider"></div>
      <div class="kicker">Sources</div>
      <div id="sources"></div>
      <div class="divider"></div>
      <div class="kicker">Trending Types</div>
      <div class="chips" id="kinds"></div>
      <div class="divider"></div>
      <div class="kicker">Sentiment</div>
      <div class="chips" id="sentiments"></div>
      <div class="divider"></div>
      <div class="kicker">Shortcuts</div>
      <div class="muted small" style="line-height:1.9">
        <span class="kbd">j</span> <span class="kbd">k</span> move ·
        <span class="kbd">↵</span> open original ·
        <span class="kbd">/</span> search
      </div>
      <div class="divider"></div>
      <div class="kicker">About</div>
      <div class="muted small">A local archive of first-party statements, official documents, and news coverage — one row per item, updated by scheduled ingests. Items are ranked by impact, scored from how authoritative the source is, what the item is about, and how committed its language is.</div>
    </div>

    <div class="center">
      <div class="filterbar" id="filterbar">
        <span id="filterlabel"></span>
        <div class="dates">
          <div class="ctl">
            <label id="sortlabel">Sort</label>
            <div class="seg" role="group" aria-labelledby="sortlabel">
              <button id="sort-recent" data-sort="recent" class="active">Newest</button>
              <button id="sort-impact" data-sort="impact">Top impact</button>
            </div>
          </div>
          <div class="ctl">
            <label for="since">From</label>
            <input type="date" id="since" aria-label="From date">
          </div>
          <div class="ctl">
            <label for="until">To</label>
            <input type="date" id="until" aria-label="To date">
          </div>
        </div>
      </div>
      <div class="feed" id="feed"></div>
    </div>

    <div class="rail right">
      <div class="kicker">Deep Dive</div>
      <div id="deepdive"><div class="muted small">Select an item to see details.</div></div>
    </div>
  </div>

<script>
const SOURCE_LABEL = {presidential_documents:'His Words',federal_register:'Official Actions',
  whitehouse:'White House',news:'In the News'};
const state = {source:'', kind:'', sentiment:'', topic:'', tier:'', ticker:'', sort:'recent', q:'', since:'', until:'',
               offset:0, limit:25, selectedId:null, items:[], loading:false};
const TIER_RANK = {critical:0, high:1, notable:2, routine:3};

const $ = id => document.getElementById(id);

// ── URL state ────────────────────────────────────────────────────────────────
// Filters live in the query string so a view can be bookmarked, shared, and
// walked back through with the browser's own Back button. Without this, "top
// impact, tariffs only" is a place you can reach but never link to.
const FILTER_KEYS = ['source','kind','sentiment','topic','tier','ticker','q','since','until'];
const URL_KEYS = FILTER_KEYS.concat(['sort']);

function readUrl(){
  const p = new URLSearchParams(location.search);
  URL_KEYS.forEach(k=>{ const v=p.get(k); if(v!=null) state[k]=v; });
  if(state.sort!=='impact' && state.sort!=='recent') state.sort='recent';
  if(state.q) $('q').value = state.q;
  if(state.since) $('since').value = state.since;
  if(state.until) $('until').value = state.until;
}

function writeUrl(){
  const p = new URLSearchParams();
  URL_KEYS.forEach(k=>{ if(state[k] && !(k==='sort' && state[k]==='recent')) p.set(k,state[k]); });
  const qs = p.toString();
  history.replaceState(null,'', qs ? '?'+qs : location.pathname);
}

function esc(s){const d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
function label(s){return SOURCE_LABEL[s]||s;}
function initials(s){return label(s).split(/\\s+/).map(w=>w[0]||'').join('').slice(0,2).toUpperCase();}
function fmtTime(iso){
  if(!iso) return '';
  const d=new Date(iso), s=(Date.now()-d.getTime())/1000;
  if(s<60) return 'just now';
  if(s<3600) return Math.floor(s/60)+'m ago';
  if(s<86400) return Math.floor(s/3600)+'h ago';
  if(s<604800) return Math.floor(s/86400)+'d ago';
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
}

async function loadFacets(){
  const d = await (await fetch('/api/facets')).json();
  $('livecount').textContent = d.total.toLocaleString() + ' items';
  // tabs
  const tabs = [{key:'',label:'All'}].concat(d.sources.map(s=>({key:s.key,label:label(s.key)})));
  $('tabs').innerHTML = tabs.map(t=>
    `<button class="tab${state.source===t.key?' active':''}" data-src="${esc(t.key)}">${esc(t.label)}</button>`).join('');
  $('tabs').querySelectorAll('.tab').forEach(b=>b.onclick=()=>{state.source=b.dataset.src;state.kind='';loadFeed(true);syncActive();});
  // sources rail
  $('sources').innerHTML = d.sources.map(s=>
    `<div class="srcrow${state.source===s.key?' active':''}" data-src="${esc(s.key)}">
       <span class="nm">${esc(label(s.key))}</span><span class="ct">${s.count}</span></div>`).join('');
  $('sources').querySelectorAll('.srcrow').forEach(r=>r.onclick=()=>{state.source=r.dataset.src;state.kind='';loadFeed(true);syncActive();});
  // trending kinds
  $('kinds').innerHTML = d.kinds.map(k=>
    `<button class="chip${state.kind===k.key?' active':''}" data-kind="${esc(k.key)}">${esc(k.key)} · ${k.count}</button>`).join('');
  $('kinds').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    state.kind = state.kind===c.dataset.kind ? '' : c.dataset.kind; loadFeed(true); syncActive();});
  // sentiment
  const sents = d.sentiments || [];
  $('sentiments').innerHTML = sents.length
    ? sents.map(s=>`<button class="chip${state.sentiment===s.key?' active':''}" data-sent="${esc(s.key)}"
        title="average polarity ${s.avg_compound>0?'+':''}${s.avg_compound}">${esc(s.key)} · ${s.count}</button>`).join('')
    : `<div class="muted small">Not scored yet — run <code>archiver score-sentiment</code>.</div>`;
  $('sentiments').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    state.sentiment = state.sentiment===c.dataset.sent ? '' : c.dataset.sent; loadFeed(true); syncActive();});
  // impact tiers
  const tiers = d.tiers || [];
  $('tiers').innerHTML = tiers.length
    ? tiers.map(t=>`<button class="chip tierchip${state.tier===t.key?' active':''}" data-tier="${esc(t.key)}"
        >${esc(t.key)} · ${t.count}</button>`).join('')
    : `<div class="muted small">Not ranked yet — run <code>archiver classify</code>.</div>`;
  $('tiers').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    state.tier = state.tier===c.dataset.tier ? '' : c.dataset.tier; loadFeed(true); syncActive();});
  // topics
  const topics = d.topics || [];
  TOPIC_LABELS = Object.fromEntries(topics.map(t=>[t.key,t.label]));
  $('topics').innerHTML = topics.length
    ? topics.map(t=>`<button class="chip${state.topic===t.key?' active':''}" data-topic="${esc(t.key)}"
        >${esc(t.label)} · ${t.count}</button>`).join('')
    : `<div class="muted small">No topics detected yet.</div>`;
  $('topics').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    state.topic = state.topic===c.dataset.topic ? '' : c.dataset.topic; loadFeed(true); syncActive();});
  // companies
  const comps = d.companies || [];
  COMPANY_NAMES = Object.fromEntries(comps.map(c=>[c.key,c.label]));
  $('companies').innerHTML = comps.length
    ? comps.map(c=>`<button class="chip${state.ticker===c.key?' active':''}" data-ticker="${esc(c.key)}"
        title="${esc(c.label)}">${esc(c.key)} · ${c.count} ${quoteBadge(c.quote)}</button>`).join('')
    : `<div class="muted small">None detected yet — run <code>archiver detect-stocks</code>.</div>`;
  $('companies').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    state.ticker = state.ticker===c.dataset.ticker ? '' : c.dataset.ticker; loadFeed(true); syncActive();});
}

let COMPANY_NAMES = {};
function companyName(t){return COMPANY_NAMES[t]||t;}

function quoteBadge(q){
  // Only rendered when the market refresh has actually run; a blank space here
  // means "no quote cached", never "flat".
  if(!q || !q.pct_change) return '';
  const dir = q.delta==='up' ? 'up' : (q.delta==='down' ? 'down' : '');
  return `<span class="mv ${dir}">${esc(q.pct_change)}</span>`;
}

function syncActive(){
  $('tabs').querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.src===state.source));
  $('sources').querySelectorAll('.srcrow').forEach(r=>r.classList.toggle('active', r.dataset.src===state.source));
  $('kinds').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.kind===state.kind));
  $('sentiments').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.sent===state.sentiment));
  $('tiers').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.tier===state.tier));
  $('topics').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.topic===state.topic));
  $('companies').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.ticker===state.ticker));
  $('sort-recent').classList.toggle('active', state.sort==='recent');
  $('sort-impact').classList.toggle('active', state.sort==='impact');
  const bits=[];
  if(state.source) bits.push('source: '+label(state.source));
  if(state.kind) bits.push('type: '+state.kind);
  if(state.sentiment) bits.push('sentiment: '+state.sentiment);
  if(state.tier) bits.push('impact: '+state.tier);
  if(state.topic) bits.push('topic: '+topicLabel(state.topic));
  if(state.ticker) bits.push('company: '+companyName(state.ticker));
  if(state.q) bits.push('“'+state.q+'”');
  $('filterlabel').innerHTML = bits.length
    ? 'Filtering by '+bits.map(b=>`<span style="color:var(--accent)">${esc(b)}</span>`).join(', ')
      +' <button class="clear" id="clear">clear all</button>'
    : 'Showing all items';
  const c=$('clear'); if(c) c.onclick=()=>{
    FILTER_KEYS.forEach(k=>state[k]='');
    $('q').value='';$('since').value='';$('until').value='';
    loadFeed(true);syncActive();};
  writeUrl();
}

let TOPIC_LABELS = {};
function topicLabel(k){return TOPIC_LABELS[k]||k;}

function sentPill(s){
  if(!s) return '';
  const pct = Math.round(s.score*100);
  return `<span class="sent ${esc(s.label)}" title="FinBERT · ${pct}% confidence · polarity ${s.compound>0?'+':''}${s.compound}">${esc(s.label)}</span>`;
}

function tierPill(im){
  if(!im) return '';
  return `<span class="tier ${esc(im.tier)}" title="impact ${im.score} — ${esc((im.reasons||[]).join(' · '))}"><i></i>${esc(im.tier)}</span>`;
}

function topicChips(topics){
  if(!topics || !topics.length) return '';
  return `${topics.slice(0,4).map(t=>
    `<button class="topic" data-topic="${esc(t.key)}" title="matched on “${esc(t.matched_term||t.key)}”">${esc(t.label)}</button>`
  ).join('')}`;
}

function tickerChips(stocks){
  if(!stocks || !stocks.length) return '';
  return stocks.map(c=>
    `<button class="tick" data-ticker="${esc(c.ticker)}" title="${esc(c.name)} — mentioned as “${esc(c.alias||c.ticker)}”"
      ><span class="sym">${esc(c.ticker)}</span></button>`).join('');
}

function card(it){
  // The publisher already names the outlet, so the kind badge would repeat it
  // verbatim on every news card; show the badge only when it says something new.
  const who = (it.source==='news' && it.publisher) ? it.publisher : label(it.source);
  const badge = (it.kind && it.kind !== who) ? `<span class="badge">${esc(it.kind)}</span>` : '';
  const summary = it.summary ? `<div class="summary">${esc(it.summary)}</div>` : '';
  const why = (it.impact && it.impact.reasons && it.impact.reasons.length)
    ? `<div class="why">${esc(it.impact.reasons.join(' · '))}</div>` : '';
  return `<div class="card${state.selectedId===it.id?' sel':''}" data-id="${esc(it.id)}" tabindex="0" role="button"
       aria-label="${esc(it.title)}">
    <div class="meta">
      ${tierPill(it.impact)}
      <div class="avatar">${esc(initials(it.source))}</div>
      <span class="who">${esc(who)} · ${esc(fmtTime(it.created_at))}</span>
      ${badge}
      ${sentPill(it.sentiment)}
    </div>
    <div class="title">${esc(it.title)}</div>
    ${summary}
    ${(it.topics&&it.topics.length)||(it.stocks&&it.stocks.length)
      ? `<div class="topics">${topicChips(it.topics)}${tickerChips(it.stocks)}</div>` : ''}
    ${why}
    <div class="foot">${it.url?`<a class="link" href="${esc(it.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Read original ↗</a>`:''}</div>
  </div>`;
}

function skeleton(n){
  return Array.from({length:n},()=>
    `<div class="skel"><div class="ln s"></div><div class="ln m"></div><div class="ln l"></div></div>`).join('');
}

function wireCards(){
  $('feed').querySelectorAll('.card').forEach(c=>{
    if(c.__w) return; c.__w=1;
    c.onclick=()=>select(c.dataset.id);
    c.onkeydown=e=>{
      if(e.key==='Enter'||e.key===' '){e.preventDefault();select(c.dataset.id);}
    };
    c.querySelectorAll('.topic').forEach(t=>t.onclick=e=>{
      e.stopPropagation();
      state.topic = state.topic===t.dataset.topic ? '' : t.dataset.topic;
      loadFeed(true); syncActive();
    });
    c.querySelectorAll('.tick').forEach(t=>t.onclick=e=>{
      e.stopPropagation();
      state.ticker = state.ticker===t.dataset.ticker ? '' : t.dataset.ticker;
      loadFeed(true); syncActive();
    });
  });
}

async function loadFeed(reset){
  if(state.loading) return;
  state.loading=true;
  if(reset){state.offset=0;state.items=[];$('feed').innerHTML=skeleton(5);}
  const p=new URLSearchParams({limit:state.limit,offset:state.offset,sort:state.sort});
  FILTER_KEYS.forEach(k=>{ if(state[k]) p.set(k, state[k]); });
  let d;
  try{
    d = await (await fetch('/api/statuses?'+p)).json();
  }catch(err){
    $('feed').innerHTML=`<div class="empty"><h3>Couldn't reach the archive</h3>
      <div class="muted small">The server may have stopped. Refresh to try again.</div></div>`;
    state.loading=false; return;
  }
  if(reset) $('feed').innerHTML='';
  const old=$('more'); if(old)old.remove();
  if(state.offset===0 && d.items.length===0){
    const filtered = state.source||state.kind||state.sentiment||state.topic||state.tier||state.q||state.since||state.until;
    $('feed').innerHTML = filtered
      ? `<div class="empty"><h3>No items match these filters</h3>
         <div class="muted small">Try removing one, or <button class="clear" id="emptyclear">clear all</button></div></div>`
      : `<div class="empty"><h3>The archive is empty</h3>
         <div class="muted small">Run an <code>archiver ingest-*</code> command to populate it.</div></div>`;
    const ec=$('emptyclear');
    if(ec) ec.onclick=()=>{
      FILTER_KEYS.forEach(k=>state[k]='');
      $('q').value='';$('since').value='';$('until').value='';
      loadFeed(true);syncActive();};
    state.loading=false; return;
  }
  state.items=state.items.concat(d.items);
  $('feed').insertAdjacentHTML('beforeend', d.items.map(card).join(''));
  wireCards();
  state.offset+=d.items.length;
  if(d.items.length===state.limit){
    $('feed').insertAdjacentHTML('beforeend',`<button class="more" id="more">Load more</button>`);
    $('more').onclick=()=>loadFeed(false);
  }
  // After a filter change the previous selection is usually gone from the feed.
  // Checking only for "nothing selected" left the deep dive showing an item the
  // list no longer contains, and keyboard navigation with no anchor to move from.
  const stillShown = state.items.some(x=>x.id===state.selectedId);
  if(!stillShown && state.items.length) select(state.items[0].id);
  state.loading=false;
}

function genSummaryPanel(g){
  if(!g) return '';
  return `<div class="panel">
      <div class="h">Condensed <span class="prov ai">AI-generated</span></div>
      <div class="dd-body">${esc(g.text)}</div>
      <div class="smodel">${esc(g.model)} · generated ${esc(fmtTime(g.generated_at))} · a paraphrase, not the publisher's words</div>
    </div>`;
}

function sentimentPanel(s){
  if(!s) return `<div class="panel">
      <div class="h">Sentiment <span class="soon">not scored</span></div>
      <div class="muted small">This item hasn't been scored. Run <code>archiver score-sentiment</code> to add a FinBERT reading.</div>
    </div>`;
  const pct = v => (v*100).toFixed(1)+'%';
  const sign = v => (v>0?'+':'')+v.toFixed(3);
  return `<div class="panel">
      <div class="h">Sentiment ${sentPill(s)}</div>
      <div class="sbar">
        <i class="pos" style="width:${s.positive*100}%"></i>
        <i class="neu" style="width:${s.neutral*100}%"></i>
        <i class="neg" style="width:${s.negative*100}%"></i>
      </div>
      <div class="srow"><span>Positive</span><b>${pct(s.positive)}</b></div>
      <div class="srow"><span>Neutral</span><b>${pct(s.neutral)}</b></div>
      <div class="srow"><span>Negative</span><b>${pct(s.negative)}</b></div>
      <div class="srow" style="margin-top:6px;padding-top:6px;border-top:1px solid var(--divider)">
        <span>Polarity</span><b>${sign(s.compound)}</b></div>
      <div class="smodel">${esc(s.model)} · scored ${esc(fmtTime(s.scored_at))}</div>
    </div>`;
}

function impactPanel(im, topics, entities, stocks){
  if(!im) return `<div class="panel">
      <div class="h">Impact <span class="soon">not ranked</span></div>
      <div class="muted small">This item hasn't been classified. Run <code>archiver classify</code> to score it.</div>
    </div>`;
  // Every component is shown, including the ones no pass has measured yet —
  // hiding them would make the score look more complete than it is.
  const comps = [
    ['Authority', im.authority, im.authority_label],
    ['Topic', im.topic, null],
    ['Actionability', im.actionability, null],
    ['Corroboration', im.corroboration, 'needs clustering'],
    ['Market', im.market_sensitivity, 'needs stock data'],
  ];
  const rows = comps.map(([name,v,note])=>{
    const un = (v===null||v===undefined);
    return `<div class="icomp${un?' unmeasured':''}" title="${esc(un?(note||'not measured yet'):(note||''))}">
      <span>${esc(name)}</span>
      <span class="track"><i class="fill" style="width:${un?0:Math.round(v*100)}%"></i></span>
      <b>${un?'—':v.toFixed(2)}</b></div>`;
  }).join('');
  const ents = (entities||[]).slice(0,8).map(e=>`<span class="ent">${esc(e.alias||e.key)}</span>`).join('');
  return `<div class="panel">
      <div class="h">Impact ${tierPill(im)}<span style="margin-left:auto;color:var(--n300);font-variant-numeric:tabular-nums">${im.score.toFixed(3)}</span></div>
      <div class="ibar">${rows}</div>
      ${topics && topics.length?`<div class="topics" style="margin-top:10px">${topics.map(t=>
        `<span class="topic" style="cursor:default" title="matched on “${esc(t.matched_term||'')}”">${esc(t.label)}</span>`).join('')}</div>`:''}
      ${ents?`<div class="topics" style="margin-top:6px">${ents}</div>`:''}
      ${(stocks&&stocks.length)?`<div class="topics" style="margin-top:8px">${
        stocks.map(c=>`<span class="tick" style="cursor:default" title="mentioned as “${esc(c.alias||'')}”"><span class="sym">${esc(c.ticker)}</span> ${esc(c.name)}</span>`).join('')
      }</div>`:''}
      <div class="smodel">weighted from the components above · unmeasured parts are excluded, not zeroed</div>
    </div>`;
}

function select(id){
  state.selectedId=id;
  $('feed').querySelectorAll('.card').forEach(c=>c.classList.toggle('sel',c.dataset.id===id));
  const it=state.items.find(x=>x.id===id); if(!it)return;
  const who=(it.source==='news'&&it.publisher)?it.publisher:label(it.source);
  const also=state.items.filter(x=>x.id!==id && x.source===it.source).slice(0,5);
  $('deepdive').innerHTML=`
    <div class="panel">
      <div class="dd-title">${esc(it.title)}</div>
      <div class="muted small">${esc(who)} · ${esc(fmtTime(it.created_at))} · ${esc(it.kind)}</div>
      ${it.url?`<div style="margin-top:10px"><a class="link" style="color:var(--accent);font-size:13px" href="${esc(it.url)}" target="_blank" rel="noopener">Read the original ↗</a></div>`:''}
    </div>
    ${impactPanel(it.impact, it.topics, it.entities, it.stocks)}
    ${it.summary ? `<div class="panel"><div class="h">Summary <span class="prov pub">publisher</span></div><div class="dd-body">${esc(it.summary)}</div></div>`:''}
    ${genSummaryPanel(it.generated_summary)}
    ${sentimentPanel(it.sentiment)}
    <div class="panel">
      <div class="h">More from ${esc(who==='In the News'?'the news':who)}</div>
      <div class="also">${also.length?also.map(a=>`<a data-id="${esc(a.id)}">${esc(a.title)}</a>`).join(''):'<div class="muted small">Nothing else loaded yet.</div>'}</div>
    </div>`;
  $('deepdive').querySelectorAll('.also a').forEach(a=>a.onclick=()=>select(a.dataset.id));
}

async function loadTicker(){
  const d=await (await fetch('/api/statuses?limit=18')).json();
  const one=d.items.map(it=>`<span class="it"><span class="src">${esc((it.source==='news'&&it.publisher)?it.publisher:label(it.source))}</span><span class="t">${esc(it.title)}</span></span>`).join('');
  $('ticker').innerHTML=one+one;
}

let t;
$('q').addEventListener('input',()=>{clearTimeout(t);t=setTimeout(()=>{state.q=$('q').value.trim();loadFeed(true);syncActive();},250);});
$('since').addEventListener('change',()=>{state.since=$('since').value;loadFeed(true);syncActive();});
$('until').addEventListener('change',()=>{state.until=$('until').value;loadFeed(true);syncActive();});

['sort-recent','sort-impact'].forEach(id=>$(id).addEventListener('click',()=>{
  if(state.sort===$(id).dataset.sort) return;
  state.sort=$(id).dataset.sort; loadFeed(true); syncActive();
}));

const rt=$('railtoggle');
rt.addEventListener('click',()=>{
  const open=$('leftrail').classList.toggle('open');
  rt.classList.toggle('open',open);
  rt.setAttribute('aria-expanded',String(open));
});

// Keyboard: j/k or arrows move through the feed, Enter opens the original,
// "/" jumps to search, Escape leaves it. Reading a ranked list is the whole
// point of the page, so it should not require the mouse.
function move(delta){
  if(!state.items.length) return;
  const i=state.items.findIndex(x=>x.id===state.selectedId);
  const next=Math.max(0,Math.min(state.items.length-1,(i<0?0:i+delta)));
  select(state.items[next].id);
  const el=$('feed').querySelector(`.card[data-id="${CSS.escape(state.items[next].id)}"]`);
  if(el) el.scrollIntoView({block:'nearest'});
}
document.addEventListener('keydown',e=>{
  const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
  if(e.key==='/' && !typing){e.preventDefault();$('q').focus();return;}
  if(e.key==='Escape' && typing){$('q').blur();return;}
  if(typing) return;
  if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();move(1);}
  else if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();move(-1);}
  else if(e.key==='Enter'){
    const it=state.items.find(x=>x.id===state.selectedId);
    if(it&&it.url) window.open(it.url,'_blank','noopener');
  }
});

window.addEventListener('popstate',()=>{
  URL_KEYS.forEach(k=>state[k]='');
  state.sort='recent';
  readUrl(); loadFeed(true); syncActive();
});

readUrl();
loadFacets().then(()=>{syncActive();loadFeed(true);});
loadTicker();
</script>
</body>
</html>
"""
