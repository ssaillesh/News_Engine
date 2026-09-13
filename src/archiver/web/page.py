"""The dashboard HTML (self-contained).

One reading column instead of three panes. Each story is a quiet row — headline,
source, and a single plain-language line saying what it means for markets — and
opens in place to show the detail. Every filter lives in one drawer, so the page
itself stays calm; the vocabulary ("headwind for Materials") is written for a
reader, not for the scoring code that produced it.
"""

from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trump News Archive</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%239184d9'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap">
<style>
  :root{
    color-scheme: dark;
    --bg:#101218; --surface:#161922; --raise:#1c1f2a; --hover:#1a1d27;
    --line:rgba(232,232,240,.08); --line-2:rgba(232,232,240,.14);
    --text:#e9e9ef; --soft:#c3c5d2; --muted:#9296a8; --faint:#676b7d;
    --accent:#9d91e3; --accent-ink:#f4f2ff; --accent-bg:rgba(157,145,227,.14);
    --head:#f3f3f7;
    --down:#ec8a82; --down-bg:rgba(236,138,130,.12);
    --up:#93d27f;   --up-bg:rgba(147,210,127,.12);
    --top:#ff7a72;  --top-bg:rgba(255,122,114,.12);
    --high:#f0ac62; --high-bg:rgba(240,172,98,.12);
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
    --col:760px; --r:10px;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.55;
    -webkit-font-smoothing:antialiased}
  a{color:inherit}
  button{font:inherit;color:inherit}
  ::selection{background:rgba(157,145,227,.3)}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}

  /* ── header ─────────────────────────────────────────────────────────────── */
  .top{position:sticky;top:0;z-index:20;background:rgba(16,18,24,.86);backdrop-filter:blur(14px);
    -webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
  .bar{max-width:1080px;margin:0 auto;padding:14px 20px;display:flex;align-items:center;gap:16px}
  .brand{display:flex;align-items:center;gap:10px;text-decoration:none;flex:none}
  .brand i{width:22px;height:22px;border-radius:6px;background:linear-gradient(140deg,#b3a8f0,#5b4fa8)}
  .brand span{font-family:var(--serif);font-size:19px;font-weight:500;letter-spacing:-.01em}
  .search{flex:1;max-width:420px;margin-left:auto;position:relative}
  .search input{width:100%;height:38px;padding:0 38px 0 14px;border-radius:999px;border:1px solid var(--line-2);
    background:var(--surface);color:var(--text);font:inherit;font-size:14px;outline:none}
  .search input::placeholder{color:var(--faint)}
  .search input:focus{border-color:var(--accent)}
  .search kbd{position:absolute;right:12px;top:50%;transform:translateY(-50%);font:500 11px var(--sans);
    color:var(--faint);border:1px solid var(--line-2);border-radius:5px;padding:1px 6px}
  .fbtn{flex:none;height:38px;padding:0 16px;border-radius:999px;border:1px solid var(--line-2);background:var(--surface);
    cursor:pointer;font-size:14px;display:inline-flex;align-items:center;gap:8px}
  .fbtn:hover{border-color:var(--accent)}
  .fbtn b{min-width:18px;height:18px;border-radius:9px;background:var(--accent);color:#16131f;font-size:11px;
    display:inline-flex;align-items:center;justify-content:center;padding:0 5px}

  .sub{max-width:var(--col);margin:0 auto;padding:18px 20px 6px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
  .seg{display:inline-flex;padding:3px;border-radius:999px;background:var(--surface);border:1px solid var(--line)}
  .seg button{border:0;background:transparent;padding:6px 14px;border-radius:999px;cursor:pointer;font-size:13px;color:var(--muted)}
  .seg button[aria-pressed="true"]{background:var(--raise);color:var(--text);box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
  .tabs{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tabs button{border:0;background:transparent;padding:6px 10px;border-radius:8px;cursor:pointer;font-size:13px;
    color:var(--muted);white-space:nowrap}
  .tabs button:hover{color:var(--text)}
  .tabs button[aria-pressed="true"]{color:var(--text);background:var(--accent-bg)}
  .count{margin-left:auto;font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}

  .pills{max-width:var(--col);margin:0 auto;padding:6px 20px 0;display:flex;flex-wrap:wrap;gap:6px}
  .pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line-2);background:var(--surface);
    border-radius:999px;padding:3px 6px 3px 11px;font-size:12px;color:var(--soft);cursor:pointer}
  .pill:hover{border-color:var(--accent)}
  .pill span{color:var(--faint)}
  .pill em{font-style:normal;width:16px;height:16px;border-radius:50%;display:inline-flex;align-items:center;
    justify-content:center;background:var(--raise);color:var(--muted);font-size:11px}
  .pill.clear{border-style:dashed;padding-right:11px;color:var(--muted)}

  /* ── feed ───────────────────────────────────────────────────────────────── */
  main{max-width:var(--col);margin:0 auto;padding:10px 20px 80px}
  .item{border-bottom:1px solid var(--line)}
  .item:first-child{border-top:0}
  .head{display:block;width:100%;text-align:left;border:0;background:transparent;cursor:pointer;
    padding:20px 14px;margin:0 -14px;border-radius:var(--r);width:calc(100% + 28px)}
  .head:hover{background:var(--hover)}
  .item.open .head{background:transparent}
  .meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px 8px;font-size:12px;color:var(--faint);margin-bottom:7px}
  .meta .dot{width:3px;height:3px;border-radius:50%;background:var(--faint);opacity:.7}
  .badge{font-size:11px;font-weight:600;letter-spacing:.02em;padding:2px 8px;border-radius:999px}
  .badge.critical{color:var(--top);background:var(--top-bg)}
  .badge.high{color:var(--high);background:var(--high-bg)}
  .headline{font-family:var(--serif);font-size:20px;line-height:1.3;font-weight:500;color:var(--head);margin:0;
    letter-spacing:-.005em;text-wrap:pretty}
  .mline{margin-top:9px;font-size:13px;color:var(--muted);display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px}
  .mline .dir{font-weight:500}
  .mline .dir.restrictive{color:var(--down)} .mline .dir.supportive{color:var(--up)} .mline .dir.mentioned{color:var(--soft)}
  .mline .etf,.tk{font-size:11px;font-weight:600;letter-spacing:.03em;color:var(--soft);background:var(--raise);
    padding:1px 6px;border-radius:5px;font-variant-numeric:tabular-nums}

  /* the opened story */
  .detail{display:grid;grid-template-rows:0fr;transition:grid-template-rows .28s ease}
  .item.open .detail{grid-template-rows:1fr}
  .detail > div{overflow:hidden}
  .inner{padding:2px 0 26px}
  .lede{font-family:var(--serif);font-size:17px;line-height:1.6;color:var(--soft);margin:0 0 22px;max-width:64ch}
  .full{margin:-12px 0 22px}
  .full summary{cursor:pointer;font-size:13px;color:var(--accent);list-style:none}
  .full summary::-webkit-details-marker{display:none}
  .full[open] summary{margin-bottom:12px}
  .lede.thin{font-family:var(--sans);font-size:13px;color:var(--faint);font-style:normal}
  .sec{margin:0 0 22px}
  .sec h3{margin:0 0 10px;font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
  .say{margin:0 0 12px;font-size:14px;color:var(--soft);max-width:64ch}
  .say b{font-weight:600}
  .say b.restrictive{color:var(--down)} .say b.supportive{color:var(--up)}
  .rows{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
  .row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--surface);padding:11px 14px}
  .row .n{font-size:14px;color:var(--text)}
  .row .s{font-size:12px;color:var(--faint);margin-top:1px}
  .row .r{text-align:right;font-variant-numeric:tabular-nums;font-size:13px;white-space:nowrap}
  .row button.link{border:0;background:none;padding:0;cursor:pointer;color:var(--accent);font-size:12px}
  .chg.up{color:var(--up)} .chg.down{color:var(--down)} .chg.flat{color:var(--faint)}
  .bars{display:grid;gap:9px;max-width:460px}
  .bar-row{display:grid;grid-template-columns:118px minmax(0,1fr) 36px;gap:12px;align-items:center;font-size:13px;color:var(--muted)}
  .track{height:4px;border-radius:4px;background:var(--raise);overflow:hidden}
  .track i{display:block;height:100%;border-radius:4px;background:var(--accent)}
  .bar-row b{font-weight:500;color:var(--soft);text-align:right;font-variant-numeric:tabular-nums}
  .bar-row.off{opacity:.45}
  .ctx{font-size:13px;color:var(--muted);line-height:1.8}
  .ctx span{color:var(--soft)}
  .actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:4px}
  .btn{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:999px;
    border:1px solid var(--line-2);background:var(--surface);text-decoration:none;font-size:13px;cursor:pointer}
  .btn:hover{border-color:var(--accent)}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:#16131f;font-weight:500}
  .btn.primary:hover{filter:brightness(1.07)}
  .note{font-size:12px;color:var(--faint)}

  /* ANALYSIS — the written breakdown, set apart from our own scoring below it */
  .brief{margin:0 0 26px;padding:20px 22px;border-radius:14px;background:var(--surface);border:1px solid var(--line)}
  .bhead{display:flex;align-items:center;gap:10px;margin-bottom:12px}
  .bhead h3{margin:0;font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
  .ai{font-size:11px;color:var(--accent);background:var(--accent-bg);border-radius:999px;padding:2px 8px}
  .bottom{font-family:var(--serif);font-size:19px;line-height:1.5;color:var(--head);margin:0 0 16px;max-width:62ch}
  .caveat{font-size:13px;color:var(--high);background:var(--high-bg);border-radius:8px;padding:8px 12px;margin:0 0 16px}
  .qa h4{margin:16px 0 4px;font-size:13px;font-weight:600;color:var(--text)}
  .qa p{margin:0;font-size:14px;line-height:1.65;color:var(--soft);max-width:66ch}
  .blist{display:grid;gap:10px;margin:8px 0 0}
  .bitem{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 10px;align-items:baseline}
  .bitem .t{font-size:14px;color:var(--text)}
  .bitem .e{grid-column:2;font-size:13px;color:var(--muted);line-height:1.55}
  .dirp{font-size:11px;font-weight:600;border-radius:999px;padding:1px 8px;white-space:nowrap}
  .dirp.positive{color:var(--up);background:var(--up-bg)} .dirp.negative{color:var(--down);background:var(--down-bg)}
  .dirp.mixed{color:var(--high);background:var(--high-bg)} .dirp.uncertain{color:var(--muted);background:var(--raise)}
  .bdates{margin:6px 0 0;padding-left:18px;font-size:13px;color:var(--soft);line-height:1.8}
  .bfoot{margin-top:18px;padding-top:12px;border-top:1px solid var(--line);font-size:12px;color:var(--faint)}
  .bwait{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--muted)}
  .spin{width:16px;height:16px;border-radius:50%;border:2px solid var(--raise);border-top-color:var(--accent);animation:rot .8s linear infinite;flex:none}
  @keyframes rot{to{transform:rotate(360deg)}}
  .brief .btn{margin-top:2px}
  .brief.quiet{background:transparent;border-style:dashed;padding:14px 18px}
  .more{display:block;margin:28px auto 0;height:38px;padding:0 20px;border-radius:999px;border:1px solid var(--line-2);
    background:var(--surface);cursor:pointer;font-size:14px}
  .more:hover{border-color:var(--accent)}
  .empty{padding:80px 0;text-align:center;color:var(--muted)}
  .empty h2{font-family:var(--serif);font-weight:500;font-size:22px;color:var(--text);margin:0 0 6px}
  .skel{padding:22px 0;border-bottom:1px solid var(--line)}
  .skel i{display:block;height:11px;border-radius:5px;margin:0 0 10px;
    background:linear-gradient(90deg,var(--surface),var(--raise),var(--surface));background-size:300% 100%;
    animation:sh 1.3s linear infinite}
  .skel i:nth-child(1){width:26%}.skel i:nth-child(2){width:88%;height:17px}.skel i:nth-child(3){width:44%;margin:0}
  @keyframes sh{from{background-position:100% 0}to{background-position:0 0}}

  /* ── filter drawer ──────────────────────────────────────────────────────── */
  .scrim{position:fixed;inset:0;background:rgba(6,7,10,.55);opacity:0;pointer-events:none;transition:opacity .2s;z-index:40}
  .scrim.on{opacity:1;pointer-events:auto}
  .drawer{position:fixed;top:0;right:0;bottom:0;width:min(400px,100vw);background:var(--surface);
    border-left:1px solid var(--line);z-index:50;transform:translateX(100%);transition:transform .25s ease;
    display:flex;flex-direction:column}
  .drawer.on{transform:none}
  .dhead{display:flex;align-items:center;justify-content:space-between;padding:18px 22px;border-bottom:1px solid var(--line)}
  .dhead h2{margin:0;font-family:var(--serif);font-weight:500;font-size:21px}
  .x{width:32px;height:32px;border-radius:50%;border:1px solid var(--line-2);background:transparent;cursor:pointer;font-size:16px;color:var(--muted)}
  .dbody{overflow-y:auto;padding:6px 22px 30px;flex:1}
  .grp{padding:18px 0;border-bottom:1px solid var(--line)}
  .grp:last-child{border-bottom:0}
  .grp h3{margin:0 0 4px;font-size:13px;font-weight:600}
  .grp p{margin:0 0 12px;font-size:12px;color:var(--faint)}
  .opts{display:flex;flex-wrap:wrap;gap:6px}
  .opt{border:1px solid var(--line-2);background:transparent;border-radius:999px;padding:5px 11px;font-size:12px;
    color:var(--soft);cursor:pointer;display:inline-flex;gap:6px;align-items:baseline}
  .opt:hover{border-color:var(--accent)}
  .opt small{color:var(--faint);font-size:11px;font-variant-numeric:tabular-nums}
  .opt[aria-pressed="true"]{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink)}
  .dates{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .dates label{font-size:11px;color:var(--faint);display:grid;gap:5px}
  .dates input{height:36px;border-radius:8px;border:1px solid var(--line-2);background:var(--bg);color:var(--text);padding:0 10px;font:inherit;font-size:13px}
  .guide dt{font-size:13px;font-weight:600;margin:12px 0 2px;color:var(--soft)}
  .guide dd{margin:0;font-size:12px;color:var(--muted);line-height:1.6}
  .dfoot{padding:14px 22px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}

  @media (max-width:640px){
    .bar{flex-wrap:wrap;padding:12px 16px;gap:10px}
    .search{order:3;max-width:none;flex-basis:100%;margin:0}
    .fbtn{margin-left:auto}
    .sub,.pills,main{padding-left:16px;padding-right:16px}
    .sub{gap:12px}
    .count{display:none}
    .headline{font-size:18px}
    .head{padding:18px 12px;margin:0 -12px;width:calc(100% + 24px)}
    .bar-row{grid-template-columns:96px minmax(0,1fr) 32px}
  }
  @media (prefers-reduced-motion:reduce){
    *{transition:none!important;animation:none!important}
  }
</style>
</head>
<body>

<header class="top">
  <div class="bar">
    <a class="brand" href="/"><i></i><span>Trump News Archive</span></a>
    <label class="search">
      <input id="q" type="search" placeholder="Search headlines" aria-label="Search headlines" autocomplete="off">
      <kbd>/</kbd>
    </label>
    <button class="fbtn" id="openFilters" aria-haspopup="dialog" aria-controls="drawer">Filters <b id="fcount" hidden>0</b></button>
  </div>
</header>

<div class="sub">
  <div class="seg" role="group" aria-label="Order">
    <button data-sort="recent" aria-pressed="true">Latest</button>
    <button data-sort="impact" aria-pressed="false">Top impact</button>
  </div>
  <nav class="tabs" id="tabs" aria-label="Source"></nav>
  <span class="count" id="count"></span>
</div>
<div class="pills" id="pills"></div>

<main id="feed" aria-live="polite"></main>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="dtitle" aria-hidden="true">
  <div class="dhead"><h2 id="dtitle">Filters</h2><button class="x" id="closeFilters" aria-label="Close filters">✕</button></div>
  <div class="dbody" id="dbody"></div>
  <div class="dfoot"><button class="btn" id="clearAll">Clear all</button><button class="btn primary" id="done">Show results</button></div>
</aside>

<script>
const SOURCE_LABEL = {federal_register:'Official actions', presidential_documents:'His words', whitehouse:'White House', news:'In the news'};
const TIER_LABEL   = {critical:'Top impact', high:'High impact', notable:'Moderate', routine:'Low'};
const TIER_ORDER   = ['critical','high','notable','routine'];
const DIR = {
  restrictive:{arrow:'▼', word:'Headwind for',  name:'Headwinds'},
  supportive: {arrow:'▲', word:'Tailwind for',  name:'Tailwinds'},
  mentioned:  {arrow:'•', word:'Touches',       name:'No clear direction'},
};
const FILTER_KEYS = ['source','kind','sentiment','topic','tier','ticker','sector','stance','q','since','until'];
const FILTER_NAME = {source:'Source', kind:'Type', sentiment:'Tone', topic:'Topic', tier:'Impact', ticker:'Company',
                     sector:'Sector', stance:'Direction', since:'From', until:'To'};

const state = {sort:'recent', offset:0, limit:30, items:[], open:null, loading:false};
FILTER_KEYS.forEach(k => state[k] = '');
let F = {sources:[], kinds:[], tiers:[], sectors:[], stances:[], companies:[], topics:[], sentiments:[], total:0};
let COMPANY = {}, SECTOR = {}, TOPIC = {};

const $ = id => document.getElementById(id);
const esc = s => { const d=document.createElement('div'); d.textContent = s==null ? '' : String(s); return d.innerHTML; };
const who = it => (it.source==='news' && it.publisher) ? it.publisher : (SOURCE_LABEL[it.source]||it.source);

function when(iso){
  if(!iso) return '';
  const d = new Date(iso.endsWith('Z')||iso.includes('+') ? iso : iso+'Z'), s = (Date.now()-d)/1000;
  if(s < 90) return 'just now';
  if(s < 3600) return Math.floor(s/60)+'m ago';
  if(s < 86400) return Math.floor(s/3600)+'h ago';
  if(s < 6*86400) return Math.floor(s/86400)+'d ago';
  const opts = {month:'short', day:'numeric'};
  if(d.getFullYear() !== new Date().getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString(undefined, opts);
}

function label(k, v){
  if(k==='source') return SOURCE_LABEL[v]||v;
  if(k==='tier') return TIER_LABEL[v]||v;
  if(k==='stance') return (DIR[v]||{}).name||v;
  if(k==='sector') return (SECTOR[v]||{}).label||v;
  if(k==='topic') return TOPIC[v]||v;
  if(k==='ticker') return v;
  return v;
}

// ── URL: every view is linkable and Back works ─────────────────────────────
function readUrl(){
  const p = new URLSearchParams(location.search);
  FILTER_KEYS.forEach(k => state[k] = p.get(k)||'');
  state.sort = p.get('sort')==='impact' ? 'impact' : 'recent';
  $('q').value = state.q;
}
function writeUrl(){
  const p = new URLSearchParams();
  FILTER_KEYS.forEach(k => { if(state[k]) p.set(k, state[k]); });
  if(state.sort==='impact') p.set('sort','impact');
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?'+qs : location.pathname);
}

// ── the one line that says what a story means for markets ──────────────────
function marketLine(it){
  const secs = it.sectors||[], stocks = it.stocks||[];
  if(!secs.length && !stocks.length) return '';
  const st = (it.impact && it.impact.stance) || 'mentioned', d = DIR[st];
  const names = secs.slice(0,2).map(s => `<span>${esc(s.label)} <span class="etf">${esc(s.etf||'')}</span></span>`).join('');
  const extra = secs.length > 2 ? ` <span>+${secs.length-2}</span>` : '';
  const tks = stocks.slice(0,4).map(s => `<span class="tk">${esc(s.ticker)}</span>`).join(' ');
  return `<div class="mline"><span class="dir ${st}">${d.arrow} ${d.word}</span>${names||''}${extra}${tks?' '+tks:''}</div>`;
}

function itemHTML(it){
  const t = it.impact && it.impact.tier;
  const badge = (t==='critical'||t==='high') ? `<span class="badge ${t}">${TIER_LABEL[t]}</span>` : '';
  const kind = it.kind && it.kind !== who(it) ? `<span>${esc(it.kind)}</span><i class="dot"></i>` : '';
  return `<article class="item" data-id="${esc(it.id)}">
    <button class="head" aria-expanded="false" aria-controls="d-${esc(it.id)}">
      <div class="meta">${badge}${kind}<span>${esc(who(it))}</span><i class="dot"></i><time>${esc(when(it.created_at))}</time></div>
      <h2 class="headline">${esc(it.title)}</h2>
      ${marketLine(it)}
    </button>
    <div class="detail" id="d-${esc(it.id)}"><div></div></div>
  </article>`;
}

// ── the opened story ───────────────────────────────────────────────────────
function detailHTML(it){
  const im = it.impact, secs = it.sectors||[], stocks = it.stocks||[];
  let lede;
  if(it.summary && it.summary.length > 700){
    const cut = it.summary.slice(0, 600).replace(/\s+\S*$/, '');
    lede = `<p class="lede excerpt">${esc(cut)}…</p>
      <details class="full"><summary>Read the full text</summary><p class="lede">${esc(it.summary)}</p></details>`;
  }
  else if(it.summary) lede = `<p class="lede">${esc(it.summary)}</p>`;
  else if(it.generated_summary) lede = `<p class="lede">${esc(it.generated_summary.text)}</p><p class="note" style="margin:-14px 0 22px">Machine summary — a paraphrase, not the publisher's words.</p>`;
  else lede = `<p class="lede thin">Only the headline is archived for this story. Open the original to read it in full.</p>`;

  // markets
  let mk;
  if(!secs.length && !stocks.length){
    mk = `<p class="say">No market angle detected — this reads as a political story rather than a market one.</p>`;
  } else {
    const st = (im && im.stance) || 'mentioned';
    const why = {
      restrictive:`<b class="restrictive">Headwind.</b> The language is restrictive — tariffs, bans, probes or penalties aimed at the areas below.`,
      supportive:`<b class="supportive">Tailwind.</b> The language is supportive — exemptions, approvals, investment or deregulation for the areas below.`,
      mentioned:`<b>No clear direction.</b> The story touches the areas below without clearly helping or hurting them.`,
    }[st];
    const secRows = secs.map(s => `<div class="row"><div><div class="n">${esc(s.label)}</div>
        <div class="s">${s.tickers&&s.tickers.length ? 'Watch: '+esc(s.tickers.slice(0,6).join(', ')) : 'Sector-wide'}${s.matched_term?' · mentions “'+esc(s.matched_term)+'”':''}</div></div>
        <div class="r"><span class="tk">${esc(s.etf||'')}</span></div></div>`).join('');
    const stockRows = stocks.map(s => {
      const c = COMPANY[s.ticker]||{}, q = c.quote||{};
      const dir = q.delta==='up' ? 'up' : q.delta==='down' ? 'down' : 'flat';
      const px = q.last_price ? `${esc(q.last_price)} <span class="chg ${dir}">${esc(q.pct_change||'')}</span>` : '<span class="note">no quote</span>';
      return `<div class="row"><div><div class="n"><span class="tk">${esc(s.ticker)}</span> ${esc(s.name)}</div>
        <div class="s">Named as “${esc(s.alias||s.ticker)}” · <button class="link" data-filter="ticker" data-value="${esc(s.ticker)}">More on ${esc(s.ticker)}</button></div></div>
        <div class="r">${px}</div></div>`;
    }).join('');
    mk = `<p class="say">${why}</p>
      ${secRows ? `<div class="rows" style="margin-bottom:${stockRows?'10px':'0'}">${secRows}</div>` : ''}
      ${stockRows ? `<div class="rows">${stockRows}</div>` : ''}`;
  }

  // ranking
  let rank = '';
  if(im){
    const parts = [
      ['Source authority', im.authority, im.authority_label],
      ['Policy topic', im.topic],
      ['Committed language', im.actionability],
      ['Market relevance', im.market_sensitivity],
      ['Outlets covering', im.corroboration, 'not measured yet'],
    ];
    const bars = parts.map(([n,v,hint]) => {
      const off = v==null;
      return `<div class="bar-row${off?' off':''}" title="${esc(off?(hint||'not measured yet'):(hint||''))}"><span>${n}</span>
        <span class="track"><i style="width:${off?0:Math.round(v*100)}%"></i></span><b>${off?'—':Math.round(v*100)}</b></div>`;
    }).join('');
    const reasons = (im.reasons||[]).length ? ` — ${esc(im.reasons.join(', ').toLowerCase())}` : '';
    rank = `<div class="sec"><h3>Why it ranks here</h3>
      <p class="say"><b>${TIER_LABEL[im.tier]||im.tier}</b>${reasons}.</p><div class="bars">${bars}</div></div>`;
  }

  // context
  const ctx = [];
  if((it.topics||[]).length) ctx.push(`Topics: <span>${esc(it.topics.map(t=>t.label).join(', '))}</span>`);
  if((it.entities||[]).length) ctx.push(`Mentions: <span>${esc(it.entities.slice(0,8).map(e=>e.alias||e.key).join(', '))}</span>`);
  if(it.sentiment) ctx.push(`Coverage tone: <span>${esc(it.sentiment.label)} (${Math.round(it.sentiment.score*100)}% confidence)</span>`);

  return `<div class="inner">
    ${lede}
    <div class="brief" data-brief hidden></div>
    <div class="sec"><h3>What it means for markets</h3>${mk}</div>
    ${rank}
    ${ctx.length ? `<div class="sec"><h3>Context</h3><div class="ctx">${ctx.join('<br>')}</div></div>` : ''}
    <div class="actions">
      ${it.url ? `<a class="btn primary" href="${esc(it.url)}" target="_blank" rel="noopener">Read the original ↗</a>` : ''}
      <span class="note">${esc(it.kind||'')}${it.kind?' · ':''}${esc(who(it))}</span>
    </div>
  </div>`;
}

function toggle(id, force){
  const el = document.querySelector(`.item[data-id="${CSS.escape(id)}"]`);
  if(!el) return;
  const willOpen = force!==undefined ? force : !el.classList.contains('open');
  if(state.open && state.open!==id){
    const prev = document.querySelector(`.item[data-id="${CSS.escape(state.open)}"]`);
    if(prev){ prev.classList.remove('open'); prev.querySelector('.head').setAttribute('aria-expanded','false'); }
  }
  const it = state.items.find(x => x.id===id);
  if(willOpen && it){
    const box = el.querySelector('.detail > div');
    if(!box.dataset.built){ box.innerHTML = detailHTML(it); box.dataset.built = '1'; wireDetail(box); loadBrief(it, box.querySelector('[data-brief]')); }
  }
  el.classList.toggle('open', willOpen);
  el.querySelector('.head').setAttribute('aria-expanded', String(willOpen));
  state.open = willOpen ? id : null;
  if(willOpen) setTimeout(() => el.scrollIntoView({block:'nearest', behavior:'smooth'}), 60);
}

const DIR_WORD = {positive:'Positive', negative:'Negative', mixed:'Mixed', uncertain:'Unclear'};

function writer(model){
  if(!model) return 'AI-written';
  if(model.startsWith('claude')) return 'Written by Claude';
  const tag = model.replace(/^ollama\//,'');
  return `Written by open model ${tag}`;
}

function briefHTML(d){
  const a = d.analysis;
  const para = (h, t) => t ? `<h4>${h}</h4><p>${esc(t)}</p>` : '';
  const items = list => (list||[]).map(x => `<div class="bitem"><span class="dirp ${esc(x.direction)}">${DIR_WORD[x.direction]||esc(x.direction)}</span>
      <span class="t">${esc(x.area)}</span><span class="e">${esc(x.explanation)}</span></div>`).join('');
  const companies = (a.companies||[]).map(c => {
    const tk = c.ticker ? (COMPANY[c.ticker]
      ? `<button class="tk" data-filter="ticker" data-value="${esc(c.ticker)}" style="border:0;cursor:pointer">${esc(c.ticker)}</button>`
      : `<span class="tk">${esc(c.ticker)}</span>`) : '';
    return `<div class="bitem"><span class="dirp ${esc(c.direction)}">${DIR_WORD[c.direction]||esc(c.direction)}</span>
      <span class="t">${esc(c.name)} ${tk}</span><span class="e">${esc(c.explanation)}</span></div>`;
  }).join('');
  const basis = {full_text:'Based on the full article', partial:'Based on part of the article', headline_only:'Based on the headline only'}[d.source_quality] || '';
  return `<div class="bhead"><h3>Analysis</h3><span class="ai">${esc(writer(d.model))}</span></div>
    <p class="bottom">${esc(a.bottom_line)}</p>
    ${d.source_quality==='headline_only' ? '<p class="caveat">The article itself couldn’t be read, so this is limited to what the headline and excerpt support.</p>' : ''}
    <div class="qa">
      ${para('What happened', a.what_happened)}
      ${para('Why it matters', a.why_it_matters)}
      ${para('How it moves the economy', a.how_it_impacts)}
      ${para('What’s being done', a.whats_being_done)}
      ${para('Trump’s position', a.trump_position)}
      ${(a.economic_effects||[]).length ? `<h4>Economic effects</h4><div class="blist">${items(a.economic_effects)}</div>` : ''}
      ${(a.sectors||[]).length ? `<h4>Sectors</h4><div class="blist">${items(a.sectors)}</div>` : ''}
      ${companies ? `<h4>Companies</h4><div class="blist">${companies}</div>` : ''}
      ${(a.key_dates||[]).length ? `<h4>Key dates</h4><ul class="bdates">${a.key_dates.map(k=>`<li>${esc(k)}</li>`).join('')}</ul>` : ''}
      ${para('Still unclear', a.open_questions)}
    </div>
    <div class="bfoot">${basis} · generated ${esc(when(d.generated_at))} · machine-written and can be wrong; check the original before acting on it</div>`;
}

async function loadBrief(it, el){
  if(!el) return;
  let d;
  try { d = await (await fetch('/api/analysis?id='+encodeURIComponent(it.id))).json(); }
  catch(e){ return; }
  if(d.status==='ready'){ el.hidden=false; el.classList.remove('quiet'); el.innerHTML = briefHTML(d); wireDetail(el); return; }
  if(!d.available){
    el.hidden=false; el.classList.add('quiet');
    el.innerHTML = '<span class="note">No detailed analysis for this story yet. New ones are written a few times a day for the latest stories that have full text.</span>';
    return;
  }
  if(d.auto) return generateBrief(it, el);
  el.hidden=false; el.classList.add('quiet');
  el.innerHTML = `<div class="bwait" style="justify-content:space-between;flex-wrap:wrap">
    <span>Get a detailed breakdown — what happened, why it matters, and who it affects.</span>
    <button class="btn primary" data-gen>Write analysis</button></div>`;
  el.querySelector('[data-gen]').onclick = () => generateBrief(it, el);
}

async function generateBrief(it, el){
  if(el.dataset.busy) return;
  el.dataset.busy = '1';
  el.hidden=false; el.classList.remove('quiet');
  el.innerHTML = `<div class="bhead"><h3>Analysis</h3><span class="ai">Written by Claude</span></div>
    <div class="bwait"><i class="spin"></i><span>Reading the story and writing the analysis. This usually takes under a minute.</span></div>`;
  try{
    const r = await fetch('/api/analysis?id='+encodeURIComponent(it.id), {method:'POST'});
    const d = await r.json();
    if(r.ok){ el.innerHTML = briefHTML(d); wireDetail(el); }
    else {
      const det = d.detail, msg = typeof det==='string' ? det : (det && det.message) || 'The analysis couldn’t be written.';
      const retry = det && det.retryable;
      el.classList.add('quiet');
      el.innerHTML = `<div class="bwait" style="justify-content:space-between;flex-wrap:wrap"><span>${esc(msg)}</span>
        ${retry ? '<button class="btn" data-gen>Try again</button>' : ''}</div>`;
      const b = el.querySelector('[data-gen]'); if(b) b.onclick = () => generateBrief(it, el);
    }
  } catch(e){
    el.classList.add('quiet');
    el.innerHTML = `<div class="bwait" style="justify-content:space-between"><span>Lost the connection while writing the analysis.</span><button class="btn" data-gen>Try again</button></div>`;
    el.querySelector('[data-gen]').onclick = () => generateBrief(it, el);
  } finally { delete el.dataset.busy; }
}

function wireDetail(box){
  box.querySelectorAll('[data-filter]').forEach(b => b.onclick = () => setFilter(b.dataset.filter, b.dataset.value));
}

// ── data ───────────────────────────────────────────────────────────────────
async function loadFacets(){
  try { F = await (await fetch('/api/facets')).json(); } catch(e){ return; }
  COMPANY = Object.fromEntries((F.companies||[]).map(c => [c.key, c]));
  SECTOR  = Object.fromEntries((F.sectors||[]).map(s => [s.key, s]));
  TOPIC   = Object.fromEntries((F.topics||[]).map(t => [t.key, t.label]));
  const tabs = [{key:'', label:'All'}].concat((F.sources||[]).map(s => ({key:s.key, label:SOURCE_LABEL[s.key]||s.key})));
  $('tabs').innerHTML = tabs.map(t => `<button data-source="${esc(t.key)}" aria-pressed="${state.source===t.key}">${esc(t.label)}</button>`).join('');
  $('tabs').querySelectorAll('button').forEach(b => b.onclick = () => setFilter('source', b.dataset.source, true));
  renderDrawer();
}

async function loadFeed(reset){
  if(state.loading) return;
  state.loading = true;
  if(reset){ state.offset=0; state.items=[]; state.open=null; $('feed').innerHTML = '<div class="skel"><i></i><i></i><i></i></div>'.repeat(5); }
  const p = new URLSearchParams({limit:state.limit, offset:state.offset, sort:state.sort});
  FILTER_KEYS.forEach(k => { if(state[k]) p.set(k, state[k]); });
  let d;
  try { d = await (await fetch('/api/statuses?'+p)).json(); }
  catch(e){
    $('feed').innerHTML = `<div class="empty"><h2>Couldn't reach the archive</h2><p>The server may have stopped. Refresh to try again.</p></div>`;
    state.loading = false; return;
  }
  if(reset) $('feed').innerHTML = '';
  const old = $('more'); if(old) old.remove();
  if(state.offset===0 && !d.items.length){
    const filtered = FILTER_KEYS.some(k => state[k]);
    $('feed').innerHTML = filtered
      ? `<div class="empty"><h2>Nothing matches these filters</h2><p>Remove one, or <button class="btn" id="emptyClear">clear all</button></p></div>`
      : `<div class="empty"><h2>The archive is empty</h2><p>Run an <code>archiver ingest-*</code> command to fill it.</p></div>`;
    const ec = $('emptyClear'); if(ec) ec.onclick = clearAll;
    state.loading = false; return;
  }
  state.items = state.items.concat(d.items);
  $('feed').insertAdjacentHTML('beforeend', d.items.map(itemHTML).join(''));
  $('feed').querySelectorAll('.item').forEach(el => {
    if(el.__w) return; el.__w = 1;
    el.querySelector('.head').onclick = () => toggle(el.dataset.id);
  });
  state.offset += d.items.length;
  if(d.items.length === state.limit){
    $('feed').insertAdjacentHTML('beforeend', '<button class="more" id="more">Show more</button>');
    $('more').onclick = () => loadFeed(false);
  }
  state.loading = false;
}

// ── filters ────────────────────────────────────────────────────────────────
function setFilter(k, v, exact){
  state[k] = (!exact && state[k]===v) ? '' : v;
  sync(); loadFeed(true);
}
function clearAll(){
  FILTER_KEYS.forEach(k => state[k] = '');
  $('q').value = '';
  sync(); loadFeed(true);
}

function sync(){
  document.querySelectorAll('.seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sort===state.sort)));
  $('tabs').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.source===state.source)));
  const active = FILTER_KEYS.filter(k => state[k] && k!=='q' && k!=='source');
  $('fcount').hidden = !active.length; $('fcount').textContent = active.length;
  $('pills').innerHTML = active.map(k =>
    `<button class="pill" data-k="${k}"><span>${FILTER_NAME[k]}</span>${esc(label(k,state[k]))}<em aria-hidden="true">✕</em></button>`).join('')
    + (active.length > 1 ? '<button class="pill clear" id="pillClear">Clear all</button>' : '');
  $('pills').querySelectorAll('.pill[data-k]').forEach(p => p.onclick = () => { state[p.dataset.k]=''; if(p.dataset.k==='since'||p.dataset.k==='until') renderDrawer(); sync(); loadFeed(true); });
  const pc = $('pillClear'); if(pc) pc.onclick = clearAll;
  const total = F.total ? F.total.toLocaleString()+' stories' : '';
  $('count').textContent = total;
  renderDrawerState();
  writeUrl();
}

function group(title, hint, key, options){
  if(!options.length) return '';
  return `<section class="grp"><h3>${title}</h3>${hint?`<p>${hint}</p>`:''}<div class="opts">${
    options.map(o => `<button class="opt" data-k="${key}" data-v="${esc(o.v)}" aria-pressed="${state[key]===o.v}">${esc(o.l)}${o.c!=null?` <small>${o.c}</small>`:''}</button>`).join('')
  }</div></section>`;
}

function renderDrawer(){
  const tiers = TIER_ORDER.map(t => (F.tiers||[]).find(x => x.key===t)).filter(Boolean);
  const stanceOrder = ['restrictive','supportive','mentioned'];
  const stances = stanceOrder.map(s => (F.stances||[]).find(x => x.key===s)).filter(Boolean);
  $('dbody').innerHTML =
    group('Impact', 'How much a story is likely to matter.', 'tier', tiers.map(t => ({v:t.key, l:TIER_LABEL[t.key], c:t.count})))
  + group('Market direction', 'Whether the action helps or hurts the sectors it names.', 'stance', stances.map(s => ({v:s.key, l:DIR[s.key].name, c:s.count})))
  + group('Sector', 'The part of the market a story touches.', 'sector', (F.sectors||[]).map(s => ({v:s.key, l:`${s.label} · ${s.etf}`, c:s.count})))
  + group('Companies named', null, 'ticker', (F.companies||[]).map(c => ({v:c.key, l:`${c.key} ${c.label}`, c:c.count})))
  + group('Policy topic', null, 'topic', (F.topics||[]).map(t => ({v:t.key, l:t.label, c:t.count})))
  + group('Document type', null, 'kind', (F.kinds||[]).slice(0,12).map(k => ({v:k.key, l:k.key, c:k.count})))
  + `<section class="grp"><h3>Dates</h3><div class="dates">
       <label>From<input type="date" id="since" value="${esc(state.since)}"></label>
       <label>To<input type="date" id="until" value="${esc(state.until)}"></label></div></section>
     <section class="grp guide"><h3>How to read this</h3><dl>
       <dt>Top impact / High impact</dt><dd>Ranked from how authoritative the source is (a signed executive order outranks a news report), what it's about, and how committed the language is — "signed, effective October 1" beats "reportedly considering".</dd>
       <dt>Headwind / Tailwind</dt><dd>Direction for the sectors named, not tone of voice. Tariffs, bans and probes are headwinds; exemptions, approvals and deregulation are tailwinds.</dd>
       <dt>Sector and ETF</dt><dd>The part of the market a story touches, with a fund that tracks it. Read from the policy wording, so it works even when no company is named.</dd>
       <dt>Coverage tone</dt><dd>A language model's read of how a news article is written. Only news articles are scored; its absence is not a judgement.</dd>
     </dl></section>`;
  $('dbody').querySelectorAll('.opt').forEach(b => b.onclick = () => setFilter(b.dataset.k, b.dataset.v));
  $('since').onchange = e => { state.since = e.target.value; sync(); loadFeed(true); };
  $('until').onchange = e => { state.until = e.target.value; sync(); loadFeed(true); };
}
function renderDrawerState(){
  $('dbody').querySelectorAll('.opt').forEach(b => b.setAttribute('aria-pressed', String(state[b.dataset.k]===b.dataset.v)));
}

let lastFocus = null;
function openDrawer(){
  lastFocus = document.activeElement;
  $('drawer').classList.add('on'); $('scrim').classList.add('on');
  $('drawer').setAttribute('aria-hidden','false');
  setTimeout(() => $('closeFilters').focus(), 50);
}
function closeDrawer(){
  $('drawer').classList.remove('on'); $('scrim').classList.remove('on');
  $('drawer').setAttribute('aria-hidden','true');
  if(lastFocus) lastFocus.focus();
}

// ── events ─────────────────────────────────────────────────────────────────
document.querySelectorAll('.seg button').forEach(b => b.onclick = () => { if(state.sort!==b.dataset.sort){ state.sort=b.dataset.sort; sync(); loadFeed(true);} });
$('openFilters').onclick = openDrawer;
$('closeFilters').onclick = closeDrawer;
$('scrim').onclick = closeDrawer;
$('done').onclick = closeDrawer;
$('clearAll').onclick = clearAll;

let qt;
$('q').addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { state.q = $('q').value.trim(); sync(); loadFeed(true); }, 280); });

// j/k move between stories, Enter opens one, o opens the original, / searches.
function heads(){ return [...document.querySelectorAll('.item .head')]; }
document.addEventListener('keydown', e => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if(e.key==='Escape'){
    if($('drawer').classList.contains('on')) return closeDrawer();
    if(typing) return document.activeElement.blur();
    if(state.open) return toggle(state.open, false);
  }
  if(typing || $('drawer').classList.contains('on')) return;
  if(e.key==='/'){ e.preventDefault(); $('q').focus(); return; }
  if(e.key==='j' || e.key==='k'){
    e.preventDefault();
    const h = heads(); if(!h.length) return;
    const i = h.indexOf(document.activeElement);
    const n = e.key==='j' ? Math.min(h.length-1, i+1) : Math.max(0, i<0 ? 0 : i-1);
    h[n].focus(); h[n].scrollIntoView({block:'nearest'});
  }
  if(e.key==='o'){
    const id = state.open || (document.activeElement.closest && document.activeElement.closest('.item') || {}).dataset?.id;
    const it = state.items.find(x => x.id===id);
    if(it && it.url) window.open(it.url, '_blank', 'noopener');
  }
});

window.addEventListener('popstate', () => { readUrl(); sync(); loadFeed(true); });

readUrl();
loadFacets().then(() => { sync(); loadFeed(true); });
</script>
</body>
</html>
"""
