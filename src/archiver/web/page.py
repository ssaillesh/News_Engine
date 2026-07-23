"""The dashboard HTML (self-contained). Styled after the Nocturne design system:
a compact dark news station, populated entirely with real archive data."""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trump News Archive</title>
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
  .tabs{display:flex;align-items:center;gap:var(--sp6);overflow-x:auto}
  .tab{font-size:14px;color:var(--n300);font-weight:500;padding:6px 2px;border-bottom:2px solid transparent;
    white-space:nowrap;cursor:pointer;background:none;border-top:none;border-left:none;border-right:none;font-family:inherit}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent)}
  .nav-right{margin-left:auto;display:flex;align-items:center;gap:var(--sp6)}
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
  .grid{flex:1;min-height:0;display:flex}
  .rail{width:250px;flex:none;border-right:1px solid var(--divider);padding:var(--sp4);overflow-y:auto}
  .rail.right{width:340px;border-right:none;border-left:1px solid var(--divider)}
  .center{flex:1;min-width:0;overflow-y:auto;padding:var(--sp6)}

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

  .filterbar{display:flex;align-items:center;gap:8px;margin-bottom:var(--sp4);font-size:12px;color:var(--n400);flex-wrap:wrap}
  .filterbar .clear{color:var(--n500);font-size:11px;border:1px solid var(--divider);padding:2px 8px;border-radius:20px;cursor:pointer}
  .dates{display:flex;gap:8px;margin-left:auto}
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
</style>
</head>
<body>
  <div class="nav">
    <div class="brand"><div class="mark"></div><div class="name">Trump News Archive</div></div>
    <div class="tabs" id="tabs"></div>
    <div class="nav-right">
      <div class="live"><span class="dot"></span><span id="livecount">loading…</span></div>
      <input class="search" id="q" placeholder="Search the archive…" autocomplete="off">
    </div>
  </div>

  <div class="ticker"><div class="row" id="ticker"></div></div>

  <div class="grid">
    <div class="rail">
      <div class="kicker">Sources</div>
      <div id="sources"></div>
      <div class="divider"></div>
      <div class="kicker">Trending Types</div>
      <div class="chips" id="kinds"></div>
      <div class="divider"></div>
      <div class="kicker">Sentiment</div>
      <div class="chips" id="sentiments"></div>
      <div class="divider"></div>
      <div class="kicker">About</div>
      <div class="muted small">A local archive of first-party statements, official documents, and news coverage — one row per item, updated by scheduled ingests. Coverage is scored with FinBERT.</div>
    </div>

    <div class="center">
      <div class="filterbar" id="filterbar">
        <span id="filterlabel"></span>
        <div class="dates">
          <input type="date" id="since" title="From date" aria-label="From date">
          <input type="date" id="until" title="To date" aria-label="To date">
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
const state = {source:'', kind:'', sentiment:'', q:'', since:'', until:'', offset:0, limit:25, selectedId:null, items:[]};

const $ = id => document.getElementById(id);
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
}

function syncActive(){
  $('tabs').querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.src===state.source));
  $('sources').querySelectorAll('.srcrow').forEach(r=>r.classList.toggle('active', r.dataset.src===state.source));
  $('kinds').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.kind===state.kind));
  $('sentiments').querySelectorAll('.chip').forEach(c=>c.classList.toggle('active', c.dataset.sent===state.sentiment));
  const bits=[];
  if(state.source) bits.push('source: '+label(state.source));
  if(state.kind) bits.push('type: '+state.kind);
  if(state.sentiment) bits.push('sentiment: '+state.sentiment);
  if(state.q) bits.push('“'+state.q+'”');
  $('filterlabel').innerHTML = bits.length
    ? 'Filtering by '+bits.map(b=>`<span style="color:var(--accent)">${esc(b)}</span>`).join(', ')
      +' <span class="clear" id="clear">clear</span>'
    : 'Showing all items';
  const c=$('clear'); if(c) c.onclick=()=>{state.source='';state.kind='';state.sentiment='';state.q='';$('q').value='';loadFeed(true);syncActive();};
}

function sentPill(s){
  if(!s) return '';
  const pct = Math.round(s.score*100);
  return `<span class="sent ${esc(s.label)}" title="FinBERT · ${pct}% confidence · polarity ${s.compound>0?'+':''}${s.compound}">${esc(s.label)}</span>`;
}

function card(it){
  const who = (it.source==='news' && it.publisher) ? it.publisher : label(it.source);
  const summary = it.summary ? `<div class="summary">${esc(it.summary)}</div>` : '';
  return `<div class="card${state.selectedId===it.id?' sel':''}" data-id="${esc(it.id)}">
    <div class="meta">
      <div class="avatar">${esc(initials(it.source))}</div>
      <span class="who">${esc(who)} · ${esc(fmtTime(it.created_at))}</span>
      <span class="badge">${esc(it.kind)}</span>
      ${sentPill(it.sentiment)}
    </div>
    <div class="title">${esc(it.title)}</div>
    ${summary}
    <div class="foot">${it.url?`<a class="link" href="${esc(it.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Read original ↗</a>`:''}</div>
  </div>`;
}

async function loadFeed(reset){
  if(reset){state.offset=0;state.items=[];$('feed').innerHTML='';}
  const p=new URLSearchParams({limit:state.limit,offset:state.offset});
  if(state.source)p.set('source',state.source);
  if(state.kind)p.set('kind',state.kind);
  if(state.sentiment)p.set('sentiment',state.sentiment);
  if(state.q)p.set('q',state.q);
  if(state.since)p.set('since',state.since);
  if(state.until)p.set('until',state.until);
  const d=await (await fetch('/api/statuses?'+p)).json();
  const old=$('more'); if(old)old.remove();
  if(state.offset===0 && d.items.length===0){
    $('feed').innerHTML=`<div class="empty">No items match. Try clearing filters, or run an <code>archiver ingest-*</code> command.</div>`;
    return;
  }
  state.items=state.items.concat(d.items);
  $('feed').insertAdjacentHTML('beforeend', d.items.map(card).join(''));
  $('feed').querySelectorAll('.card').forEach(c=>{if(!c.__w){c.__w=1;c.onclick=()=>select(c.dataset.id);}});
  state.offset+=d.items.length;
  if(d.items.length===state.limit){
    $('feed').insertAdjacentHTML('beforeend',`<button class="more" id="more">Load more</button>`);
    $('more').onclick=()=>loadFeed(false);
  }
  if(!state.selectedId && state.items.length) select(state.items[0].id);
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
$('since').addEventListener('change',()=>{state.since=$('since').value;loadFeed(true);});
$('until').addEventListener('change',()=>{state.until=$('until').value;loadFeed(true);});

loadFacets().then(()=>{syncActive();loadFeed(true);});
loadTicker();
</script>
</body>
</html>
"""
