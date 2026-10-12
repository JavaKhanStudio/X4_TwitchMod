"""A tiny self-contained status dashboard for the companion.

Serves one HTML page on localhost that polls a JSON status endpoint — no GUI
toolkit, no external assets, stdlib only, cross-platform. Runs in a daemon
thread so it never blocks the asyncio bridge.

    Dashboard(status, port).start()  ->  http://127.0.0.1:<port>/
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .catalog import catalog_view
from .status import Status

log = logging.getLogger("dashboard")

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>X4 ⇄ Twitch Companion</title>
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<style>
  :root{--bg:#0e0f1a;--card:#181a2b;--line:#272a42;--txt:#e7e9f5;--dim:#9aa0c3;
        --tw:#9146ff;--ok:#37d67a;--warn:#f5a623;--bad:#ec5b5b;--cmd:#56b6ff;--out:#c678dd}
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#1b1d33,#0e0f1a);
       color:var(--txt);font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:880px;margin:0 auto;padding:22px}
  header{display:flex;align-items:center;gap:12px;margin-bottom:18px}
  header h1{font-size:18px;margin:0;font-weight:650;letter-spacing:.2px;display:flex;align-items:center;gap:10px}
  header h1 img{width:30px;height:30px}
  header .sp{flex:1}
  .pill{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:999px;
        background:var(--card);border:1px solid var(--line);font-weight:600;font-size:13px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--dim);box-shadow:0 0 0 0 rgba(0,0,0,0)}
  .dot.on{background:var(--ok);animation:pulse 1.8s infinite}
  .dot.off{background:var(--bad)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(55,214,122,.5)}70%{box-shadow:0 0 0 7px rgba(55,214,122,0)}100%{box-shadow:0 0 0 0 rgba(55,214,122,0)}}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
  .card h2{margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);font-weight:700}
  .row{display:flex;justify-content:space-between;gap:10px;padding:4px 0}
  .row .k{color:var(--dim)}
  .row .v{font-weight:600;text-align:right;word-break:break-all}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:4px}
  .stat{background:#11132099;border:1px solid var(--line);border-radius:10px;padding:10px;text-align:center}
  .stat b{display:block;font-size:22px;font-weight:700}
  .stat span{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
  .feed{grid-column:1/-1}
  .feed ul{list-style:none;margin:0;padding:0;max-height:300px;overflow:auto}
  .feed li{display:flex;gap:10px;align-items:baseline;padding:7px 4px;border-top:1px solid var(--line)}
  .feed li:first-child{border-top:0}
  .feed .t{color:var(--dim);font-variant-numeric:tabular-nums;font-size:12px;min-width:62px}
  .feed .b{font-size:10px;font-weight:800;text-transform:uppercase;padding:1px 6px;border-radius:6px;letter-spacing:.05em}
  .b.in{background:#9146ff22;color:#b794ff}.b.cmd{background:#56b6ff22;color:var(--cmd)}
  .b.out{background:#c678dd22;color:var(--out)}.b.sys{background:#9aa0c322;color:var(--dim)}
  .b.err{background:#ec5b5b22;color:var(--bad)}
  .feed .x{flex:1}
  footer{color:var(--dim);font-size:12px;text-align:center;margin-top:16px}
  .err{color:var(--bad)}
  .steps{margin:0 0 10px;padding-left:20px;color:var(--dim);font-size:13px}
  .steps li{margin:5px 0}
  .steps ul.sub{margin:5px 0;padding-left:18px}
  .steps ul.sub li{margin:2px 0}
  .note{background:#9146ff14;border:1px solid #9146ff44;border-radius:9px;padding:9px 12px;
    font-size:12.5px;color:#cbb6ff;margin:0 0 14px}
  .hint{background:#f5a62314;border:1px solid #f5a62355;border-radius:9px;padding:8px 11px;
    font-size:12px;line-height:1.45;color:#f5c877;margin:8px 0 2px}
  .hint b{color:#ffd68a}
  .steps code{background:#0e0f1a;border:1px solid var(--line);border-radius:5px;padding:1px 5px;color:#8cd0ff}
  .steps a{color:#8cd0ff}
  .form{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
  .form .field{display:flex;flex-direction:column;gap:3px;flex:1;min-width:150px}
  .form .field>span{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;font-weight:600}
  .form input{background:#0e0f1a;border:1px solid var(--line);color:var(--txt);border-radius:8px;
    padding:8px 10px;font-size:13px;width:100%}
  .form input:focus{outline:2px solid var(--tw);outline-offset:0}
  .form button{background:var(--tw);color:#fff;border:0;border-radius:8px;padding:9px 16px;font-weight:700;cursor:pointer}
  .form button:hover{filter:brightness(1.1)}
  .dim{color:var(--dim);font-size:12px}
  .copy{background:#9146ff22;border:1px solid #9146ff55;color:#cbb6ff;border-radius:6px;
    padding:1px 8px;font-size:11px;cursor:pointer;vertical-align:middle}
  .copy:hover{background:#9146ff33}
  #setup h2{color:var(--tw)}
  .rbtn{background:var(--card);border:1px solid var(--line);color:var(--dim);border-radius:999px;
    padding:6px 13px;font-weight:600;font-size:13px;cursor:pointer}
  .rbtn:hover:not(:disabled){color:var(--txt);border-color:var(--tw)}
  .rbtn:disabled{opacity:.55;cursor:default}
  .form button.alt{background:#2a2d47}
  .form button.danger{background:var(--bad)}
  .vtab{width:100%;border-collapse:collapse;font-size:13px}
  .vtab th{text-align:left;color:var(--dim);font-weight:700;font-size:11px;text-transform:uppercase;
    letter-spacing:.06em;padding:6px 8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--card)}
  .vtab td{padding:6px 8px;border-bottom:1px solid var(--line)}
  .vtab tr:last-child td{border-bottom:0}
  .vtab .num{font-variant-numeric:tabular-nums;text-align:right}
  .vtab .banned{color:var(--bad);font-weight:700}
  .vtab .pick{cursor:pointer;color:var(--cmd)}
  .vtab .pick:hover{text-decoration:underline}
  .vwrap{overflow:auto;max-height:260px;margin-top:8px}
  .chk{display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;
    margin:12px 0 2px;user-select:none;font-weight:600}
  .chk input{width:16px;height:16px;accent-color:var(--tw);cursor:pointer}
  .chk .dim{font-weight:400}
  @media(max-width:680px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
  <header>
    <h1><img src="/icon.svg" alt="">X4 ⇄ Twitch Companion</h1><div class="sp"></div>
    <button id="restart" class="rbtn" title="Restart the companion process (reloads the page when it's back)">⟳ Restart</button>
    <div class="pill"><span id="big" class="dot"></span><span id="bigt">connecting…</span></div>
  </header>
  <div class="card" id="setup" style="margin-bottom:14px;display:none">
    <h2>① Connect to Twitch</h2>
    <ol class="steps">
      <li><b>Create your own Twitch app</b> (free, ~1 min) at
        <a href="https://dev.twitch.tv/console/apps/create" target="_blank" rel="noopener">dev.twitch.tv/console</a>
        → <i>Register Your Application</i>:
        <ul class="sub">
          <li>Name: anything (e.g. <i>My X4 Companion</i>)</li>
          <li>OAuth Redirect URL: <code>http://localhost:17563</code>
            <button type="button" class="copy" data-copy="http://localhost:17563">copy</button> (exactly this)</li>
          <li>Category: <i>Application Integration</i></li>
          <li>Client Type: <i>Confidential</i></li>
        </ul></li>
      <li>On the app's page: copy the <b>Client ID</b>, click <i>New Secret</i>, copy the <b>Client Secret</b>.</li>
      <li>Paste both below + your channel login, click <b>Connect</b>. A browser opens to authorize —
        approve, and you're live. <span class="dim">(One time; remembered &amp; auto-refreshed.)</span></li>
    </ol>
    <p class="note">💡 Use <b>your own app</b> (above), not a token-generator site — that's what lets the
      connection refresh itself so it never expires mid-stream.</p>
    <div class="form">
      <label class="field"><span>Client ID</span>
        <input id="cid" placeholder="paste from your app page" autocomplete="off"></label>
      <label class="field"><span>Client Secret</span>
        <input id="csecret" type="password" placeholder="click “New Secret”" autocomplete="off"></label>
      <label class="field"><span>Channel</span>
        <input id="chan" placeholder="your twitch login" autocomplete="off"></label>
      <button id="connect">Connect to Twitch</button>
      <span id="cstate" class="dim" role="status" aria-live="polite"></span>
    </div>
  </div>
  <div class="grid">
    <div class="card"><h2>Twitch</h2>
      <div class="row"><span class="k">Source</span><span class="v" id="source">—</span></div>
      <div class="row"><span class="k">Channel</span><span class="v" id="channel">—</span></div>
      <div class="row"><span class="k">State</span><span class="v"><span id="srcdot" class="dot"></span> <span id="srcstate">—</span></span></div>
      <div class="row"><span class="k">Bot</span><span class="v">
        <a href="https://www.twitch.tv/signup" target="_blank" rel="noopener" style="color:#8cd0ff;text-decoration:none">🤖 create a bot account →</a></span></div>
    </div>
    <div class="card"><h2>X4 (game)</h2>
      <div class="row"><span class="k">Link</span><span class="v"><span id="x4dot" class="dot"></span> <span id="x4state">—</span></span></div>
      <div id="x4hint" class="hint" style="display:none">⚠️ <b>Not linked?</b> In X4 open <b>Settings → Extensions</b>, then:
        <b>①</b> enable <i>Twitch Integration</i> &amp; <i>Mod Support APIs</i> ·
        <b>②</b> turn <b>Protected UI Mode OFF</b> (required to load the pipe) ·
        <b>③</b> restart X4 and load a save. The link turns green automatically.</div>
      <div class="row"><span class="k">Socket</span><span class="v" id="socket" style="font-size:12px">—</span></div>
      <div class="row"><span class="k">Uptime</span><span class="v" id="uptime">—</span></div>
    </div>
    <div class="card" style="grid-column:1/-1"><h2>Throughput</h2>
      <div class="stats">
        <div class="stat"><b id="ein">0</b><span>events in</span></div>
        <div class="stat"><b id="cmd">0</b><span>commands</span></div>
        <div class="stat"><b id="out">0</b><span>say → chat</span></div>
      </div>
    </div>
    <div class="card" id="econcard" style="grid-column:1/-1;display:none"><h2>Economy ·
      <a href="/catalog" style="color:var(--cmd);text-decoration:none">browse catalog →</a></h2>
      <div class="stats">
        <div class="stat"><b id="ev">0</b><span>viewers</span></div>
        <div class="stat"><b id="ecoins">0</b><span>coins in circ.</span></div>
        <div class="stat"><b id="eawarded">0</b><span>coins awarded</span></div>
      </div>
    </div>
    <div class="card" id="admincard" style="grid-column:1/-1;display:none"><h2>Moderation</h2>
      <div class="form">
        <label class="field"><span>Viewer</span>
          <input id="advuser" placeholder="twitch login (or click one below)" autocomplete="off"></label>
        <label class="field" style="flex:0 0 120px;min-width:100px"><span>Coins</span>
          <input id="advamt" type="number" value="1000" step="100" autocomplete="off"></label>
        <button id="adgive">Give</button>
        <button id="adgiveall" class="alt">Give all</button>
        <button id="adban" class="danger">Block</button>
        <button id="adunban" class="alt">Unblock</button>
      </div>
      <p id="adstate" class="dim" role="status" aria-live="polite" style="margin:8px 0 0">give coins to a viewer, or block/unblock them.</p>
      <div><label class="chk"><input type="checkbox" id="cdtoggle"> Disable cooldowns
        <span class="dim">— testing: fire actions with no wait</span></label></div>
      <div><label class="chk"><input type="checkbox" id="capstoggle"> Disable purchase limits
        <span class="dim">— testing: no per-window caps (“too many … try later”)</span></label></div>
      <div><label class="chk"><input type="checkbox" id="crisistoggle"> Accept crisis level
        <span class="dim">— off: nobody can buy a tier-3 Doom event (Xenon Armada), and
        !armada does nothing. On: chat can end your save. Resets when the companion
        restarts.</span></label></div>
      <div><label class="chk"><input type="checkbox" id="ownertoggle"> Stations go to the player
        <span class="dim">— off: chat builds for the Twitch Allies. A viewer can override
        either way per buy (“!buy wharf argon prime player”).</span></label></div>
      <div class="vwrap"><table class="vtab">
        <thead><tr><th>Viewer</th><th class="num">Coins</th><th class="num">Karma</th><th>Status</th><th>Adopted ship</th></tr></thead>
        <tbody id="vbody"><tr><td colspan="5" class="dim">no viewers yet</td></tr></tbody>
      </table></div>
    </div>
    <div class="card">
      <h2>Adoption record</h2>
      <div class="vwrap"><table class="vtab">
        <thead><tr><th>When</th><th>Viewer</th><th>Ship</th><th>Event</th></tr></thead>
        <tbody id="ahbody"><tr><td colspan="4" class="dim">no adoptions recorded yet</td></tr></tbody>
      </table></div>
    </div>
    <div class="card feed"><h2>Activity</h2><ul id="feed"><li><span class="x" style="color:var(--dim)">waiting for events…</span></li></ul></div>
  </div>
  <footer id="foot">polling…</footer>
</div>
<script>
const $=id=>document.getElementById(id);
function fmtUp(s){const h=s/3600|0,m=s%3600/60|0,x=s%60;return h+':'+String(m).padStart(2,'0')+':'+String(x).padStart(2,'0')}
function fmtT(ts){const d=new Date(ts*1000);return d.toLocaleTimeString([], {hour12:false})}
function esc(t){return (t??'').toString().replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
// Touch the DOM ONLY when a value changes — polling must not re-write unchanged
// nodes, or it wipes text selection (you can't copy) and churns the page.
function dot(el,on){const c='dot '+(on?'on':'off'); if(el.className!==c) el.className=c;}
function txt(el,v){v=''+v; if(el.textContent!==v) el.textContent=v;}
function html(el,v){if(el.__h!==v){el.__h=v; el.innerHTML=v;}}
function disp(el,show){const d=show?'':'none'; if(el.style.display!==d) el.style.display=d;}
async function tick(){
  try{
    const s=await (await fetch('/api/status',{cache:'no-store'})).json();
    const live=s.x4_connected&&s.source_running;
    dot($('big'),live); txt($('bigt'),live?'LIVE':(s.source_running?'waiting for X4':'idle'));
    txt($('source'),s.source||'—'); txt($('channel'),s.channel||'(not set)');
    const tw=s.twitch||{};
    if(s.source==='twitch'){
      if(tw.connected){ disp($('setup'),false); dot($('srcdot'),true); txt($('srcstate'),'connected: '+(tw.login||'?')); }
      else { disp($('setup'),true); dot($('srcdot'),!!tw.connecting);
        txt($('srcstate'),tw.connecting?'authorizing…':'not connected');
        if(!$('cid').value&&tw.client_id) $('cid').value=tw.client_id;
        if(!$('chan').value&&tw.channel) $('chan').value=tw.channel;
        const sp=tw.has_secret?'saved ✓ — leave blank to keep':'click “New Secret”';
        if($('csecret').placeholder!==sp) $('csecret').placeholder=sp;
        $('csecret').dataset.saved=tw.has_secret?'1':'';
        if(document.activeElement&&document.activeElement.id==='cstate'){}
        else html($('cstate'),tw.connecting?'authorizing… <b>check your browser</b>':(tw.error?('<span class="err">'+esc(tw.error)+'</span>'):'')); }
    } else { disp($('setup'),false); dot($('srcdot'),s.source_running); txt($('srcstate'),s.source_running?'running':'stopped'); }
    dot($('x4dot'),s.x4_connected); txt($('x4state'),s.x4_connected?'linked':'waiting');
    disp($('x4hint'),!s.x4_connected);
    txt($('socket'),s.socket_path||'—'); txt($('uptime'),fmtUp(s.uptime_s));
    txt($('ein'),s.events_in); txt($('cmd'),s.commands_fired); txt($('out'),s.actions_out);
    const e=s.econ||{};
    if(e&&Object.keys(e).length){ disp($('econcard'),true); txt($('ev'),e.viewers??0);
      txt($('ecoins'),e.coins_in_circulation??0); txt($('eawarded'),e.coins_awarded_total??0);
      const first=$('admincard').style.display==='none'; disp($('admincard'),true);
      // load the viewer table on first reveal, then refresh it every ~5s so balances track awards
      if(first||(_vt++%5===0)){ loadViewers(); loadAdoptions(); } }
    // reflect the live testing flags (checkbox checked == that limiter disabled)
    const fl=s.flags||{};
    const syncChk=(id,val)=>{ if(val===undefined) return; const want=val===false; const el=$(id);
      if(el && document.activeElement!==el && el.checked!==want) el.checked=want; };
    syncChk('cdtoggle', fl.cooldowns_enabled);
    syncChk('capstoggle', fl.caps_enabled);
    // these two are NOT disable-switches: checked == the flag is true
    const syncOn=(id,val)=>{ if(val===undefined) return; const el=$(id), want=val===true;
      if(el && document.activeElement!==el && el.checked!==want) el.checked=want; };
    syncOn('ownertoggle', fl.stations_to_player);
    syncOn('crisistoggle', fl.crisis_enabled);
    if(s.recent&&s.recent.length){
      html($('feed'),s.recent.map(r=>`<li><span class="t">${fmtT(r.ts)}</span><span class="b ${r.dir}">${r.dir}</span><span class="x">${esc(r.text)}</span></li>`).join('')); }
    html($('foot'),s.last_error?('<span class="err">last error: '+esc(s.last_error)+'</span>'):'connected to companion · refreshing every 1s');
  }catch(e){ txt($('bigt'),'companion offline'); dot($('big'),false); html($('foot'),'cannot reach companion (is it running?)'); }
}
// copy buttons (e.g. the redirect URL) — copying while polling is otherwise fiddly
document.querySelectorAll('.copy').forEach(btn=>btn.onclick=()=>{
  navigator.clipboard&&navigator.clipboard.writeText(btn.dataset.copy||'');
  const o=btn.textContent; btn.textContent='copied!'; setTimeout(()=>{btn.textContent=o;},1200);
});
const cbtn=$('connect');
if(cbtn) cbtn.onclick=async()=>{
  const b={client_id:$('cid').value.trim(),client_secret:$('csecret').value.trim(),channel:$('chan').value.trim()};
  const needSecret=$('csecret').dataset.saved!=='1';
  if(!b.client_id||(needSecret&&!b.client_secret)){
    html($('cstate'),'<span class="err">'+(needSecret?'Client ID and Secret are':'Client ID is')+' required</span>');return;}
  html($('cstate'),'starting… <b>a browser window will open to authorize</b>');
  try{ await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}); }
  catch(e){ html($('cstate'),'<span class="err">could not reach companion</span>'); }
};
// --- Moderation panel: give coins / block viewers ---
let _vt=0;
async function admin(payload){
  try{ const r=await fetch('/api/admin',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)}); return await r.json(); }
  catch(e){ return {ok:false,error:'cannot reach companion'}; }
}
// One viewer's adopted ship(s) for the moderation table. Kept terse: the column has
// to stay readable next to coins and karma, so it is id + type + the one number that
// matters (hull, or the rebuild price when the ship is a wreck).
function shipCell(ships){
  if(!ships||!ships.length) return '<span class="dim">—</span>';
  return ships.map(s=>{
    if(s.state==='destroyed') return '<span class="banned">'+esc(s.idcode+' '+s.label)
      +' destroyed'+(s.killer?' by '+esc(s.killer):'')+'</span>'
      +'<span class="dim"> · rebuild '+s.rebuild+'c</span>';
    if(s.state==='missing') return esc(s.idcode+' '+s.label)+'<span class="dim"> · not in the latest fleet list</span>';
    const cond=(s.hull>=0?' · hull '+s.hull+'%':'')+(s.sector?' · '+esc(s.sector):'');
    return esc(s.idcode+' '+s.label)+'<span class="dim">'+cond+'</span>';
  }).join('<br>');
}
async function loadViewers(){
  let d; try{ d=await (await fetch('/api/viewers',{cache:'no-store'})).json(); }catch(e){ return; }
  if(!d||!d.viewers) return;
  const rows=d.viewers.map(v=>'<tr><td class="pick" data-u="'+esc(v.username)+'">'+esc(v.username)+'</td>'
    +'<td class="num">'+v.coins+'</td><td class="num">'+v.karma+'%</td><td>'
    +(v.banned?'<span class="banned">blocked</span>':(v.mod?'mod':v.sub?'sub':v.vip?'vip':'—'))+'</td>'
    +'<td>'+shipCell(v.ships)+'</td></tr>').join('');
  html($('vbody'),rows||'<tr><td colspan="5" class="dim">no viewers yet</td></tr>');
  document.querySelectorAll('#vbody .pick').forEach(td=>td.onclick=()=>{$('advuser').value=td.dataset.u;});
}
async function loadAdoptions(){
  let d; try{ d=await (await fetch('/api/adoptions',{cache:'no-store'})).json(); }catch(e){ return; }
  if(!d||!d.ok) return;
  const hist=(d.history||[]).slice(0,60).map(h=>'<tr><td class="dim">'
    +esc(new Date((h.at||0)*1000).toLocaleString())+'</td><td>'+esc(h.user)
    +'</td><td>'+esc((h.idcode||'')+' '+(h.label||''))+'</td><td>'+esc(h.event)
    +(h.killer?' by '+esc(h.killer):'')+(h.was?' (was '+esc(h.was)+')':'')+'</td></tr>').join('');
  html($('ahbody'),hist||'<tr><td colspan="4" class="dim">no adoptions recorded yet</td></tr>');
}
(function wireAdmin(){
  const st=m=>html($('adstate'),m);
  const usr=()=>$('advuser').value.trim().replace(/^@/,'');
  const amt=()=>parseInt($('advamt').value,10)||0;
  const need=()=>{ if(usr())return false; st('<span class="err">enter a viewer name first</span>'); return true; };
  const run=async(p,okmsg)=>{ const r=await admin(p);
    st(r.ok?okmsg(r):('<span class="err">'+esc(r.error||'failed')+'</span>')); loadViewers(); };
  const g=id=>$(id); if(!g('adgive')) return;
  g('adgive').onclick=()=>{ if(need())return; run({action:'give',user:usr(),amount:amt()},
    r=>'✓ '+esc(r.user)+' now has '+r.coins+' coins'); };
  g('adgiveall').onclick=()=>run({action:'giveall',amount:amt()},
    r=>'✓ gave '+r.amount+' coins to '+r.count+' viewers');
  g('adban').onclick=()=>{ if(need())return; run({action:'ban',user:usr()},
    r=>'🚫 '+esc(r.user)+' is blocked'); };
  g('adunban').onclick=()=>{ if(need())return; run({action:'unban',user:usr()},
    r=>'✓ '+esc(r.user)+' is unblocked'); };
  // testing checkboxes: checked => that limiter disabled
  const toggle=(el,action,onmsg,offmsg,key)=>{ if(!el) return;
    el.onchange=async()=>{ const r=await admin({action,value:!el.checked});
      if(!r.ok){ st('<span class="err">'+esc(r.error||'failed')+'</span>'); el.checked=!el.checked; }
      else st(r[key]?onmsg:offmsg); }; };
  toggle(g('cdtoggle'),'cooldowns','cooldowns re-enabled','⚡ cooldowns disabled — fire away','cooldowns_enabled');
  toggle(g('capstoggle'),'caps','purchase limits re-enabled','⚡ purchase limits disabled — spam away','caps_enabled');
  // Station ownership reads the other way round (checked == ON), so it can't use
  // toggle(), which sends value:!checked for the two disable-switches.
  { const el=g('ownertoggle'); if(el) el.onchange=async()=>{
      const r=await admin({action:'stationowner',value:el.checked});
      if(!r.ok){ st('<span class="err">'+esc(r.error||'failed')+'</span>'); el.checked=!el.checked; }
      else st(r.stations_to_player?'🏗 stations now go to the PLAYER'
                                   :'stations now go to the Twitch Allies'); }; }
  // Crisis level: same checked==ON shape, plus a confirm on the way UP only. Turning
  // it back off must never be the click that asks a question.
  { const el=g('crisistoggle'); if(el) el.onchange=async()=>{
      if(el.checked && !confirm('Accept crisis level?\\n\\nViewers will be able to buy the '
         + 'Xenon Armada (a Xenon I + 21 escorts). Nothing cleans them up, and this can '
         + 'cost you the save.')){ el.checked=false; return; }
      const r=await admin({action:'crisis',value:el.checked});
      if(!r.ok){ st('<span class="err">'+esc(r.error||'failed')+'</span>'); el.checked=!el.checked; }
      else st(r.crisis_enabled?'☠ CRISIS LEVEL ACCEPTED — chat can buy Doom events'
                              :'crisis events are off'); }; }
})();
// --- Restart button: bounce the companion, then reload once it's back ---
const rbtn=$('restart');
if(rbtn) rbtn.onclick=async()=>{
  if(!confirm('Restart the companion? Twitch + X4 links briefly drop and reconnect.')) return;
  rbtn.disabled=true; rbtn.textContent='restarting…';
  html($('foot'),'restarting companion…');
  try{ await fetch('/api/restart',{method:'POST'}); }catch(e){}
  // The old process is shutting down; wait for the fresh one to bind, then reload
  // (a reload also pulls the new page if the code changed). Poll after a short grace.
  let tries=0;
  setTimeout(function poll(){
    fetch('/api/status',{cache:'no-store'})
      .then(()=>location.reload())
      .catch(()=>{ if(++tries>40){ location.reload(); } else { setTimeout(poll,500); } });
  },1500);
};
tick(); setInterval(tick,1000);
</script></body></html>"""


# The catalog/roadmap page is a real file so the SAME page can be published on
# GitHub Pages (with the exported catalog.json) and served live here. Read per
# request: it is tiny, and edits show on refresh during dev.
_CATALOG_HTML = Path(__file__).resolve().parents[2] / "docs" / "catalog" / "index.html"


# The project's mark (the board's icon, chosen on r7), served for the favicon and
# the page headers. The published catalog carries its own copy next to its page.
_ICON_SVG = Path(__file__).resolve().parents[2] / "icon.svg"


def _catalog_page() -> bytes:
    try:
        return _CATALOG_HTML.read_bytes()
    except OSError:
        return (b"<h1>catalog page not found</h1><p>expected at docs/catalog/index.html "
                b"in the repo; the data is still at /api/catalog?all=1</p>")


class _Handler(BaseHTTPRequestHandler):
    status: Status = None  # type: ignore[assignment]
    on_connect = None       # callable(dict) -> None
    on_disconnect = None    # callable() -> None
    on_admin = None         # callable(dict) -> dict  (give coins / block viewers)
    on_restart = None       # callable() -> None      (restart the companion process)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/status"):
            self._send(200, json.dumps(self.status.snapshot()).encode(), "application/json")
        elif self.path.startswith("/api/catalog"):
            # ?all=1 -> the full roadmap (every status, disabled included); default
            # stays the viewer-facing enabled-only projection.
            full = "all=1" in self.path
            self._send(200, json.dumps(catalog_view(enabled_only=not full)).encode(),
                       "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/viewers"):
            # The admin panel's viewer table (username, coins, karma, banned).
            result = self.on_admin({"action": "list"}) if self.on_admin else {"ok": False}
            self._send(200, json.dumps(result).encode(), "application/json")
        elif self.path.startswith("/api/adoptions"):
            # Who has adopted what, and the full record of every adoption ever.
            result = self.on_admin({"action": "adoptions"}) if self.on_admin else {"ok": False}
            self._send(200, json.dumps(result).encode(), "application/json")
        elif self.path.endswith("/icon.svg"):
            # Before /catalog: the catalog page asks for it relative to itself, and
            # /catalog/icon.svg would otherwise be answered with the page.
            try:
                self._send(200, _ICON_SVG.read_bytes(), "image/svg+xml")
            except OSError:
                self._send(404, b"not found", "text/plain")
        elif self.path.startswith("/catalog"):
            self._send(200, _catalog_page(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        if self.path.startswith("/api/connect"):
            if self.on_connect:
                self.on_connect(body)   # type: ignore[misc]
            self._send(200, b'{"ok":true}', "application/json")
        elif self.path.startswith("/api/disconnect"):
            if self.on_disconnect:
                self.on_disconnect()    # type: ignore[misc]
            self._send(200, b'{"ok":true}', "application/json")
        elif self.path.startswith("/api/admin"):
            # give coins / give-all / block / unblock a viewer
            result = self.on_admin(body) if self.on_admin else {"ok": False, "error": "economy is off"}
            self._send(200, json.dumps(result).encode(), "application/json")
        elif self.path.startswith("/api/restart"):
            # Ack FIRST, then trigger the restart — on_restart only schedules the
            # shutdown on the loop, so this response still goes out cleanly.
            ok = self.on_restart is not None
            self._send(200, json.dumps({"ok": ok}).encode(), "application/json")
            if ok:
                self.on_restart()   # type: ignore[misc]
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:  # silence access logs
        return


class Dashboard:
    def __init__(self, status: Status, port: int = 17564, host: str = "127.0.0.1",
                 on_connect=None, on_disconnect=None, on_admin=None, on_restart=None) -> None:
        self.status = status
        self.host = host
        self.port = port
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_admin = on_admin
        self.on_restart = on_restart
        self._srv: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> "Dashboard":
        handler = type("Handler", (_Handler,), {
            "status": self.status,
            "on_connect": staticmethod(self.on_connect) if self.on_connect else None,
            "on_disconnect": staticmethod(self.on_disconnect) if self.on_disconnect else None,
            "on_admin": staticmethod(self.on_admin) if self.on_admin else None,
            "on_restart": staticmethod(self.on_restart) if self.on_restart else None,
        })
        try:
            self._srv = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as e:
            log.warning("dashboard could not bind %s:%d (%s) — continuing without it",
                        self.host, self.port, e)
            return self
        threading.Thread(target=self._srv.serve_forever, name="dashboard", daemon=True).start()
        log.info("dashboard at %s", self.url)
        return self

    def stop(self) -> None:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv.server_close()   # release the port so a restart can rebind it
            self._srv = None
