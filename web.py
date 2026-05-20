import os
import sqlite3
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template_string, jsonify, abort, request

from checker import (
    add_search_term, delete_search_term, get_search_terms, update_search_term,
)

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", "/data/permits.db")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _kw_color_map(conn=None) -> dict:
    own = conn is None
    if own:
        conn = _db()
    try:
        return {r["term"]: r["color"] for r in conn.execute(
            "SELECT term, color FROM search_terms"
        ).fetchall()}
    finally:
        if own:
            conn.close()

def _kw_color_fn(colors: dict):
    return lambda kw: colors.get(kw or "", "#6b7280")

def _db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _new_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

_NAV = """
<nav>
  <a href="/" class="{% if active=='list' %}active{% endif %}">&#9776; List</a>
  <a href="/map" class="{% if active=='map' %}active{% endif %}">&#9906; Map</a>
  <a href="/keywords" class="{% if active=='keywords' %}active{% endif %}">&#9873; Keywords</a>
  <a href="/settings" class="{% if active=='settings' %}active{% endif %}">&#9881; Settings</a>
  <a href="https://gilroyca-energovweb.tylerhost.net/apps/SelfService#/search?m=1&fm=2&ps=10&pn=1&em=true"
     target="_blank">&#8599; Gilroy Portal</a>
</nav>
"""

_BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#f3f4f6;color:#1f2937}
nav{background:#1e40af;padding:.6rem 1.5rem;display:flex;gap:1.5rem;align-items:center}
nav a{color:#bfdbfe;text-decoration:none;font-size:.875rem;font-weight:500;padding:.25rem .1rem;border-bottom:2px solid transparent}
nav a.active,nav a:hover{color:#fff;border-bottom-color:#60a5fa}
.page{padding:1.5rem}
h1{font-size:1.4rem;font-weight:700;margin-bottom:.25rem}
.meta{color:#6b7280;font-size:.85rem;margin-bottom:1.25rem}
.meta a{color:#2563eb;text-decoration:none}
.meta a:hover{text-decoration:underline}
"""

# ---------------------------------------------------------------------------
# List page
# ---------------------------------------------------------------------------

_LIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gilroy Permits</title>
<style>
""" + _BASE_CSS + """
.controls{display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;margin-bottom:1rem}
input[type=text],select{padding:.375rem .625rem;border:1px solid #d1d5db;border-radius:.375rem;font-size:.875rem;background:#fff}
input[type=text]:focus,select:focus{border-color:#2563eb;outline:none;box-shadow:0 0 0 2px #dbeafe}
label{display:flex;align-items:center;gap:.35rem;font-size:.875rem;cursor:pointer;user-select:none}
.wrap{background:#fff;border-radius:.5rem;box-shadow:0 1px 3px rgba(0,0,0,.1);overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:.85rem}
thead th{background:#1e40af;color:#fff;padding:.6rem 1rem;text-align:left;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
tbody td{padding:.55rem 1rem;border-bottom:1px solid #f3f4f6;vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:#eff6ff}
.badge{display:inline-block;background:#16a34a;color:#fff;font-size:.65rem;font-weight:700;padding:.1rem .45rem;border-radius:9999px;vertical-align:middle;margin-left:.3rem}
.kw-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.3rem;vertical-align:middle}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.hidden{display:none}
.desc{color:#6b7280;font-size:.78rem;margin-top:.25rem;line-height:1.4}
.star{background:none;border:0;font-size:1.1rem;line-height:1;cursor:pointer;color:#d1d5db;padding:.1rem .25rem}
.star.on{color:#f59e0b}
.star:hover{color:#f59e0b}
.star-col{width:32px}
</style>
</head>
<body>
""" + _NAV + """
<div class="page">
<h1>Gilroy Building Permits</h1>
<p class="meta">
  <span id="vis">{{ total }}</span> of {{ total }} permits &nbsp;·&nbsp;
  Last check: {{ last_run }}
</p>
<div class="controls">
  <input type="text" id="filter" placeholder="Search…" oninput="go()">
  <select id="kw" onchange="go()">
    <option value="">All keywords</option>
    {% for kw in keywords %}
    <option value="{{ kw['term'] }}">{{ kw['term'] }}{% if not kw['enabled'] %} (disabled){% endif %}</option>
    {% endfor %}
  </select>
  <label><input type="checkbox" id="newonly" onchange="go()"> New (last 7 days)</label>
  <label><input type="checkbox" id="favonly" onchange="go()"> &#9733; Favorites only</label>
</div>
<div class="wrap">
<table id="tbl">
  <thead><tr>
    <th class="star-col"></th>
    <th>Permit #</th><th>Type</th><th>Status</th><th>Address</th>
    <th>Apply Date</th><th>Keyword</th><th>First Seen</th>
  </tr></thead>
  <tbody>
  {% for p in permits %}
  <tr data-kw="{{ p['keyword'] }}" data-new="{{ 'y' if p['is_new'] else 'n' }}" data-fav="{{ 'y' if p['favorite'] else 'n' }}" data-cid="{{ p['case_id'] }}">
    <td class="star-col">
      <button class="star {% if p['favorite'] %}on{% endif %}" title="Favorite" onclick="toggleFav(this)">{% if p['favorite'] %}&#9733;{% else %}&#9734;{% endif %}</button>
    </td>
    <td>
      <a href="/permit/{{ p['case_id'] }}">{{ p['case_number'] }}</a>
      {% if p['is_new'] %}<span class="badge">NEW</span>{% endif %}
    </td>
    <td>{{ p['case_type'] or '' }}</td>
    <td>{{ p['status'] or '' }}</td>
    <td>
      {{ p['address'] or '' }}
      {% if p['description'] %}<div class="desc">{{ p['description'][:200] }}{% if p['description']|length > 200 %}…{% endif %}</div>{% endif %}
    </td>
    <td>{{ p['apply_date'] or '' }}</td>
    <td>
      <span class="kw-dot" style="background:{{ kw_color(p['keyword']) }}"></span>{{ p['keyword'] }}
    </td>
    <td>{{ (p['first_seen'] or '')[:16] }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
</div>
<script>
function go(){
  const txt=document.getElementById('filter').value.toLowerCase();
  const kw=document.getElementById('kw').value;
  const no=document.getElementById('newonly').checked;
  const fo=document.getElementById('favonly').checked;
  let n=0;
  document.querySelectorAll('#tbl tbody tr').forEach(r=>{
    const ok=(!txt||r.textContent.toLowerCase().includes(txt))
           &&(!kw||r.dataset.kw===kw)
           &&(!no||r.dataset.new==='y')
           &&(!fo||r.dataset.fav==='y');
    r.classList.toggle('hidden',!ok); if(ok)n++;
  });
  document.getElementById('vis').textContent=n;
}
async function toggleFav(btn){
  const row = btn.closest('tr');
  const cid = row.dataset.cid;
  const on = btn.classList.contains('on');
  const method = on ? 'DELETE' : 'PUT';
  const r = await fetch('/api/permits/' + encodeURIComponent(cid) + '/favorite', {method});
  if(!r.ok) return;
  btn.classList.toggle('on');
  btn.innerHTML = btn.classList.contains('on') ? '&#9733;' : '&#9734;';
  row.dataset.fav = btn.classList.contains('on') ? 'y' : 'n';
  go();
}
</script>
</body></html>"""


@app.route("/")
def index():
    cutoff = _new_cutoff()
    conn = _db()
    permits = conn.execute(
        "SELECT *, (first_seen >= ?) AS is_new FROM permits "
        "ORDER BY favorite DESC, first_seen DESC, apply_date DESC",
        (cutoff,),
    ).fetchall()
    colors = _kw_color_map(conn)
    # Dropdown lists every search term, enabled first
    keywords = [dict(r) for r in conn.execute(
        "SELECT term, enabled FROM search_terms ORDER BY enabled DESC, term ASC"
    ).fetchall()]
    row = conn.execute("SELECT ran_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    last_run = row[0][:16].replace("T", " ") if row else "never"
    conn.close()
    return render_template_string(
        _LIST_HTML, permits=permits, keywords=keywords,
        total=len(permits), last_run=last_run, kw_color=_kw_color_fn(colors),
        active="list",
    )


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------

_DETAIL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ p['case_number'] }} — Gilroy Permits</title>
<style>
""" + _BASE_CSS + """
.card{background:#fff;border-radius:.5rem;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:1.5rem;max-width:860px}
.card h2{font-size:1.2rem;margin-bottom:1rem;display:flex;align-items:center;gap:.6rem}
.badge-status{font-size:.75rem;font-weight:600;padding:.2rem .6rem;border-radius:9999px;background:#e5e7eb;color:#374151}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem 2rem;margin-bottom:1.25rem}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
.field label{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#9ca3af}
.field p{font-size:.9rem;margin-top:.15rem;color:#1f2937}
.desc-box{background:#f9fafb;border:1px solid #e5e7eb;border-radius:.375rem;padding:.75rem 1rem;font-size:.875rem;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:#374151;margin-top:.5rem}
.actions{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1.25rem}
.btn{display:inline-block;padding:.4rem .9rem;border-radius:.375rem;font-size:.85rem;font-weight:500;text-decoration:none}
.btn-primary{background:#2563eb;color:#fff}
.btn-secondary{background:#e5e7eb;color:#374151}
.btn:hover{opacity:.85}
.kw-pill{display:inline-block;padding:.2rem .6rem;border-radius:9999px;font-size:.75rem;font-weight:600;color:#fff}
</style>
</head>
<body>
""" + _NAV + """
<div class="page">
<p class="meta" style="margin-bottom:.75rem">
  <a href="/">&larr; Back to list</a>
</p>
<div class="card">
  <h2>
    <button id="star" class="star {% if p['favorite'] %}on{% endif %}" title="Favorite" onclick="toggleFav()" style="background:none;border:0;font-size:1.4rem;cursor:pointer;color:{% if p['favorite'] %}#f59e0b{% else %}#d1d5db{% endif %};padding:0">{% if p['favorite'] %}&#9733;{% else %}&#9734;{% endif %}</button>
    {{ p['case_number'] }}
    <span class="badge-status">{{ p['status'] or 'Unknown' }}</span>
    <span class="kw-pill" style="background:{{ kw_color(p['keyword']) }}">{{ p['keyword'] }}</span>
  </h2>
  <div class="grid">
    <div class="field"><label>Type</label><p>{{ p['case_type'] or '—' }}</p></div>
    <div class="field"><label>Address</label><p>{{ p['address'] or '—' }}</p></div>
    <div class="field"><label>Apply Date</label><p>{{ p['apply_date'] or '—' }}</p></div>
    <div class="field"><label>Issue Date</label><p>{{ p['issue_date'] or '—' }}</p></div>
    <div class="field"><label>First Seen</label><p>{{ (p['first_seen'] or '')[:16].replace('T',' ') }}</p></div>
    {% if p['lat'] and p['lat'] != 0 %}
    <div class="field"><label>Coordinates</label><p>{{ '%.5f'|format(p['lat']) }}, {{ '%.5f'|format(p['lng']) }}</p></div>
    {% endif %}
  </div>
  {% if p['description'] %}
  <div class="field"><label>Description</label><div class="desc-box">{{ p['description'] }}</div></div>
  {% endif %}
  <div class="actions">
    <a class="btn btn-primary"
       href="https://gilroyca-energovweb.tylerhost.net/apps/SelfService#/search?m=1&fm=2&ps=10&pn=1&em=true&st={{ p['case_number'] }}"
       target="_blank">View on Gilroy Portal ↗</a>
    {% if p['address'] %}
    <a class="btn btn-secondary"
       href="https://www.google.com/maps/search/?api=1&query={{ p['address'] | urlencode }}"
       target="_blank">Open in Google Maps ↗</a>
    {% endif %}
    {% if p['lat'] and p['lat'] != 0 %}
    <a class="btn btn-secondary" href="/map?highlight={{ p['case_id'] }}">Show on Map</a>
    {% endif %}
  </div>
</div>
</div>
<script>
const CID = "{{ p['case_id'] }}";
async function toggleFav(){
  const btn = document.getElementById('star');
  const on = btn.classList.contains('on');
  const r = await fetch('/api/permits/' + encodeURIComponent(CID) + '/favorite',
    {method: on ? 'DELETE' : 'PUT'});
  if(!r.ok) return;
  btn.classList.toggle('on');
  const nowOn = btn.classList.contains('on');
  btn.innerHTML = nowOn ? '&#9733;' : '&#9734;';
  btn.style.color = nowOn ? '#f59e0b' : '#d1d5db';
}
</script>
</body></html>"""


@app.route("/permit/<case_id>")
def detail(case_id):
    conn = _db()
    p = conn.execute("SELECT * FROM permits WHERE case_id=?", (case_id,)).fetchone()
    colors = _kw_color_map(conn)
    conn.close()
    if not p:
        abort(404)
    return render_template_string(_DETAIL_HTML, p=p, kw_color=_kw_color_fn(colors), active="")


# ---------------------------------------------------------------------------
# Map page
# ---------------------------------------------------------------------------

_MAP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gilroy Permits Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
""" + _BASE_CSS + """
#map{height:calc(100vh - 44px);width:100%}
#controls{position:absolute;top:56px;right:12px;z-index:1000;background:#fff;border-radius:.5rem;
          box-shadow:0 2px 8px rgba(0,0,0,.15);padding:.75rem 1rem;min-width:200px;font-size:.85rem}
#controls h3{font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin-bottom:.6rem}
.legend-row{display:flex;align-items:center;gap:.5rem;margin:.3rem 0;cursor:pointer;user-select:none}
.legend-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
#status{margin-top:.75rem;padding-top:.75rem;border-top:1px solid #e5e7eb;color:#6b7280;font-size:.75rem}
select,input[type=text]{width:100%;margin-top:.4rem;padding:.3rem .5rem;border:1px solid #d1d5db;border-radius:.3rem;font-size:.8rem}
</style>
</head>
<body>
""" + _NAV + """
<div id="controls">
  <h3>Keywords</h3>
  {% for kw, color in keywords %}
  <div class="legend-row" onclick="toggleKw('{{ kw }}',this)">
    <span class="legend-dot" style="background:{{ color }}"></span>
    <span>{{ kw }}</span>
  </div>
  {% endfor %}
  <input type="text" id="search" placeholder="Filter by address / #…" oninput="applySearch()">
  <div id="status">Loading…</div>
</div>
<div id="map"></div>
<script>
const HIGHLIGHT = "{{ highlight }}";
const KW_COLORS = {{ kw_colors | tojson }};

const map = L.map('map').setView([37.0058, -121.5683], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);

let allMarkers = [];
let hiddenKws = new Set();

function getColor(kw){ return KW_COLORS[kw] || '#6b7280'; }

function makeMarker(p){
  const m = L.circleMarker([p.lat, p.lng], {
    radius: 7,
    color: getColor(p.keyword),
    fillColor: getColor(p.keyword),
    fillOpacity: 0.75,
    weight: 1.5,
  }).bindPopup(
    `<b><a href="/permit/${p.case_id}" target="_blank">${p.case_number}</a></b><br>` +
    `<span style="color:#6b7280;font-size:.8rem">${p.case_type || ''}</span><br>` +
    `${p.address || ''}<br>` +
    `<span style="color:#6b7280;font-size:.75rem">Applied: ${p.apply_date || '—'}</span>`,
    {maxWidth: 280}
  );
  m._kw = p.keyword;
  m._text = (p.case_number + ' ' + p.address + ' ' + p.case_type).toLowerCase();
  m._cid = p.case_id;
  return m;
}

fetch('/api/permits.json')
  .then(r => r.json())
  .then(data => {
    const layer = L.layerGroup().addTo(map);
    let highlighted = null;
    data.forEach(p => {
      const m = makeMarker(p);
      allMarkers.push(m);
      layer.addLayer(m);
      if (p.case_id === HIGHLIGHT) highlighted = m;
    });
    document.getElementById('status').textContent =
      data.length + ' geocoded of {{ total }} total';
    if (highlighted) {
      map.setView(highlighted.getLatLng(), 16);
      highlighted.openPopup();
    } else if (data.length) {
      const lats = data.map(p=>p.lat), lngs = data.map(p=>p.lng);
      map.fitBounds([[Math.min(...lats),Math.min(...lngs)],[Math.max(...lats),Math.max(...lngs)]],
        {padding:[40,40]});
    }
    applySearch();
  });

function applySearch(){
  const txt = document.getElementById('search').value.toLowerCase();
  allMarkers.forEach(m => {
    const visible = !hiddenKws.has(m._kw) && (!txt || m._text.includes(txt));
    visible ? m.addTo(map) : map.removeLayer(m);
  });
}

function toggleKw(kw, el){
  if(hiddenKws.has(kw)){ hiddenKws.delete(kw); el.style.opacity='1'; }
  else { hiddenKws.add(kw); el.style.opacity='.35'; }
  applySearch();
}
</script>
</body></html>"""


@app.route("/map")
def map_view():
    highlight = request.args.get("highlight", "")
    conn = _db()
    colors = _kw_color_map(conn)
    keywords = [(r[0], colors.get(r[0], "#6b7280")) for r in conn.execute(
        "SELECT DISTINCT keyword FROM permits ORDER BY keyword"
    ).fetchall()]
    total = conn.execute("SELECT count(*) FROM permits").fetchone()[0]
    conn.close()
    kw_colors = {kw: color for kw, color in keywords}
    return render_template_string(
        _MAP_HTML, keywords=keywords, kw_colors=kw_colors,
        total=total, highlight=highlight, active="map",
    )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/permits.json")
def permits_json():
    conn = _db()
    rows = conn.execute(
        "SELECT case_id, case_number, case_type, status, address, apply_date, keyword, lat, lng "
        "FROM permits WHERE lat IS NOT NULL AND lat != 0 AND lng IS NOT NULL AND lng != 0"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Keywords management page + API
# ---------------------------------------------------------------------------

_KEYWORDS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Keywords — Gilroy Permits</title>
<style>
""" + _BASE_CSS + """
.card{background:#fff;border-radius:.5rem;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:1.25rem;max-width:720px;margin-bottom:1rem}
.card h2{font-size:1rem;font-weight:700;margin-bottom:.75rem;color:#374151}
form.add{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
form.add input[type=text]{flex:1;min-width:180px;padding:.45rem .7rem;border:1px solid #d1d5db;border-radius:.375rem;font-size:.9rem}
form.add input[type=text]:focus{border-color:#2563eb;outline:none;box-shadow:0 0 0 2px #dbeafe}
button{padding:.45rem 1rem;border:0;border-radius:.375rem;font-size:.875rem;font-weight:500;cursor:pointer}
button.primary{background:#2563eb;color:#fff}
button.primary:hover{background:#1d4ed8}
button.ghost{background:transparent;color:#dc2626;padding:.2rem .5rem}
button.ghost:hover{background:#fee2e2;border-radius:.25rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;padding:.4rem .25rem;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;border-bottom:1px solid #e5e7eb}
td{padding:.55rem .25rem;border-bottom:1px solid #f3f4f6;vertical-align:middle}
.dot{display:inline-block;width:14px;height:14px;border-radius:50%;vertical-align:middle;margin-right:.5rem}
.toggle{position:relative;display:inline-block;width:36px;height:20px}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;background:#cbd5e1;border-radius:9999px;transition:.15s;cursor:pointer}
.slider:before{content:'';position:absolute;height:14px;width:14px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.15s}
.toggle input:checked + .slider{background:#16a34a}
.toggle input:checked + .slider:before{transform:translateX(16px)}
.muted{color:#9ca3af}
.err{color:#dc2626;font-size:.85rem;margin-left:.5rem}
.hint{color:#6b7280;font-size:.8rem;margin-top:.4rem}
</style>
</head>
<body>
""" + _NAV + """
<div class="page">
<h1>Search Keywords</h1>
<p class="meta">Add or remove the keywords the daily checker searches the Gilroy portal for.</p>

<div class="card">
  <h2>Add keyword</h2>
  <form class="add" onsubmit="addTerm(event)">
    <input type="text" id="term" placeholder="e.g. Kern Ave" required maxlength="120">
    <label><input type="checkbox" id="exact"> Exact match</label>
    <button class="primary" type="submit">Add</button>
    <span id="err" class="err"></span>
  </form>
  <p class="hint">New keywords take effect on the next daily check (or click <a href="#" onclick="runNow(event)">Run check now</a>).</p>
</div>

<div class="card">
  <h2>Current keywords</h2>
  <table>
    <thead><tr><th></th><th>Term</th><th>Enabled</th><th>Exact</th><th>Added</th><th></th></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>
</div>
<script>
async function load(){
  const r = await fetch('/api/keywords');
  const data = await r.json();
  const tb = document.getElementById('tbody');
  tb.innerHTML = '';
  if(!data.length){
    tb.innerHTML = '<tr><td colspan="5" class="muted">No keywords yet — add one above.</td></tr>';
    return;
  }
  for(const t of data){
    const tr = document.createElement('tr');
    const term = escapeAttr(t.term);
    tr.innerHTML = `
      <td><span class="dot" style="background:${t.color}"></span></td>
      <td>${escapeHtml(t.term)}</td>
      <td>
        <label class="toggle">
          <input type="checkbox" ${t.enabled? 'checked':''} onchange="patchField('${term}','enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </td>
      <td>
        <label class="toggle">
          <input type="checkbox" ${t.exact_match? 'checked':''} onchange="patchField('${term}','exact_match', this.checked)">
          <span class="slider"></span>
        </label>
      </td>
      <td class="muted">${(t.created_at||'').slice(0,10)}</td>
      <td style="text-align:right">
        <button class="ghost" onclick="del('${term}')">Delete</button>
      </td>`;
    tb.appendChild(tr);
  }
}
function escapeHtml(s){return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function escapeAttr(s){return s.replace(/['\\\\]/g, c => '\\\\'+c)}

async function addTerm(e){
  e.preventDefault();
  const input = document.getElementById('term');
  const exact = document.getElementById('exact');
  const err = document.getElementById('err');
  err.textContent = '';
  const term = input.value.trim();
  if(!term) return;
  const r = await fetch('/api/keywords', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({term, exact_match: exact.checked})
  });
  if(!r.ok){
    const j = await r.json().catch(()=>({error:r.statusText}));
    err.textContent = j.error || 'Failed';
    return;
  }
  input.value = '';
  exact.checked = false;
  load();
}

async function patchField(term, field, value){
  await fetch('/api/keywords/' + encodeURIComponent(term), {
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({[field]: value})
  });
}

async function del(term){
  const c = await fetch('/api/keywords/' + encodeURIComponent(term) + '/permit-count').then(r=>r.json());
  const count = c.count || 0;
  let cascade = false;
  if(count > 0){
    const choice = prompt(
      `Keyword "${term}" has ${count} associated permit(s).\n\n` +
      `Type DELETE to remove the keyword only (permits stay in the DB).\n` +
      `Type PURGE to remove the keyword AND all ${count} permit(s).\n` +
      `Anything else cancels.`
    );
    if(choice === 'PURGE'){ cascade = true; }
    else if(choice !== 'DELETE'){ return; }
  } else {
    if(!confirm(`Delete keyword "${term}"?`)) return;
  }
  const url = '/api/keywords/' + encodeURIComponent(term) + (cascade ? '?cascade=1' : '');
  const r = await fetch(url, {method:'DELETE'});
  if(r.ok){
    const j = await r.json().catch(()=>({}));
    if(cascade) alert(`Removed ${j.deleted_permits ?? count} permit(s).`);
    load();
  }
}

async function runNow(e){
  e.preventDefault();
  e.target.textContent = 'Running…';
  const r = await fetch('/api/run-check', {method:'POST'});
  const j = await r.json().catch(()=>({}));
  e.target.textContent = r.ok ? `Done — ${j.new_found ?? 0} new` : 'Failed';
}

load();
</script>
</body></html>"""


@app.route("/keywords")
def keywords_view():
    return render_template_string(_KEYWORDS_HTML, active="keywords")


@app.route("/api/keywords", methods=["GET", "POST"])
def keywords_api():
    if request.method == "GET":
        return jsonify(get_search_terms(enabled_only=False))
    body = request.get_json(silent=True) or {}
    term = (body.get("term") or "").strip()
    if not term:
        return jsonify({"error": "term required"}), 400
    try:
        row = add_search_term(
            term, color=body.get("color"),
            exact_match=bool(body.get("exact_match")),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(row), 201


@app.route("/api/keywords/<path:term>", methods=["PATCH", "DELETE"])
def keyword_item_api(term):
    try:
        if request.method == "DELETE":
            cascade = request.args.get("cascade") in ("1", "true", "yes")
            removed = delete_search_term(term, cascade_permits=cascade)
            return jsonify({"deleted_permits": removed}), 200
        body = request.get_json(silent=True) or {}
        update_search_term(
            term,
            enabled=body.get("enabled") if "enabled" in body else None,
            color=body.get("color"),
            exact_match=body.get("exact_match") if "exact_match" in body else None,
        )
        return ("", 204)
    except KeyError:
        return jsonify({"error": f"unknown term: {term}"}), 404


@app.route("/api/keywords/<path:term>/permit-count")
def keyword_permit_count(term):
    conn = _db()
    n = conn.execute("SELECT COUNT(*) FROM permits WHERE keyword = ?", (term,)).fetchone()[0]
    conn.close()
    return jsonify({"term": term, "count": n})


@app.route("/api/run-check", methods=["POST"])
def run_check_api():
    from checker import run_check
    new_found = run_check()
    return jsonify({"new_found": new_found})


# ---------------------------------------------------------------------------
# Settings page + API
# ---------------------------------------------------------------------------

_SETTINGS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Settings — Gilroy Permits</title>
<style>
""" + _BASE_CSS + """
.card{background:#fff;border-radius:.5rem;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:1.5rem;max-width:680px;margin-bottom:1rem}
.card h2{font-size:1rem;font-weight:700;margin-bottom:.75rem;color:#374151}
.row{display:grid;grid-template-columns:140px 1fr;gap:.5rem 1rem;align-items:center;margin-bottom:.6rem}
.row label{font-size:.85rem;color:#374151}
.row input[type=text], .row input[type=password], .row input[type=number]{
  width:100%;padding:.4rem .6rem;border:1px solid #d1d5db;border-radius:.375rem;font-size:.9rem
}
.row input:focus{border-color:#2563eb;outline:none;box-shadow:0 0 0 2px #dbeafe}
.checks{display:flex;gap:1.25rem;flex-wrap:wrap;margin:.5rem 0 1rem 140px}
.checks label{display:flex;gap:.4rem;align-items:center;font-size:.85rem;cursor:pointer}
.actions{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-top:.75rem}
button{padding:.45rem 1rem;border:0;border-radius:.375rem;font-size:.875rem;font-weight:500;cursor:pointer}
button.primary{background:#2563eb;color:#fff}
button.secondary{background:#e5e7eb;color:#374151}
button.primary:hover{background:#1d4ed8}
button.secondary:hover{background:#d1d5db}
#status{font-size:.85rem}
#status.ok{color:#16a34a}
#status.err{color:#dc2626}
.hint{color:#6b7280;font-size:.8rem;margin-top:.4rem}
.warn{color:#92400e;background:#fef3c7;border:1px solid #fde68a;border-radius:.375rem;padding:.5rem .75rem;font-size:.8rem;margin-top:.5rem}
</style>
</head>
<body>
""" + _NAV + """
<div class="page">
<h1>Settings</h1>
<p class="meta">Configure SMTP for alerts on favorited permits. Emails fire after each run-check if any starred permit has a field change.</p>

<div class="card">
  <h2>SMTP / email alerts</h2>
  <form onsubmit="save(event)">
    <div class="row"><label>Host</label><input type="text" id="host" placeholder="smtp.example.com"></div>
    <div class="row"><label>Port</label><input type="number" id="port" value="587" min="1" max="65535"></div>
    <div class="row"><label>Username</label><input type="text" id="username" autocomplete="off"></div>
    <div class="row"><label>Password</label><input type="password" id="password" autocomplete="new-password" placeholder="(unchanged)"></div>
    <div class="checks">
      <label><input type="checkbox" id="use_tls"> STARTTLS</label>
      <label><input type="checkbox" id="use_ssl"> SSL (implicit)</label>
    </div>
    <div class="row"><label>From</label><input type="text" id="from_addr" placeholder="permits@example.com"></div>
    <div class="row"><label>To</label><input type="text" id="to_addr" placeholder="you@example.com"></div>
    <div class="row"><label>Base URL</label><input type="text" id="base_url" placeholder="http://192.168.6.57:5001"></div>
    <div class="checks">
      <label><input type="checkbox" id="enabled"> Alerts enabled</label>
    </div>
    <div class="actions">
      <button class="primary" type="submit">Save</button>
      <button class="secondary" type="button" onclick="test()">Send test email</button>
      <span id="status"></span>
    </div>
    <p class="hint">Base URL is used to build clickable links in the alert emails.</p>
    <p class="warn">Password is stored in plaintext in the SQLite DB on the host volume. Acceptable for a home-network single-user setup; not for shared infra.</p>
  </form>
</div>
</div>
<script>
async function load(){
  const r = await fetch('/api/settings');
  const s = await r.json();
  for(const k of ['host','port','username','password','from_addr','to_addr','base_url']){
    document.getElementById(k).value = s[k] ?? '';
  }
  for(const k of ['use_tls','use_ssl','enabled']){
    document.getElementById(k).checked = !!s[k];
  }
}
function val(id){ return document.getElementById(id).value; }
function chk(id){ return document.getElementById(id).checked; }
function setStatus(msg, ok){
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = ok ? 'ok' : 'err';
  setTimeout(()=>{ el.textContent=''; el.className=''; }, 5000);
}
async function save(e){
  e.preventDefault();
  const body = {
    host: val('host'), port: parseInt(val('port'))||587,
    username: val('username'),
    password: val('password') || '***',  // *** means keep existing
    use_tls: chk('use_tls'), use_ssl: chk('use_ssl'),
    from_addr: val('from_addr'), to_addr: val('to_addr'),
    base_url: val('base_url'), enabled: chk('enabled'),
  };
  const r = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(r.ok){ setStatus('Saved', true); document.getElementById('password').value=''; load(); }
  else { const j = await r.json().catch(()=>({})); setStatus(j.error || 'Save failed', false); }
}
async function test(){
  setStatus('Sending…', true);
  const r = await fetch('/api/settings/test', {method:'POST'});
  const j = await r.json().catch(()=>({}));
  if(r.ok && j.ok){ setStatus('Sent — check your inbox', true); }
  else { setStatus('Failed: ' + (j.error || r.statusText), false); }
}
load();
</script>
</body></html>"""


@app.route("/settings")
def settings_view():
    return render_template_string(_SETTINGS_HTML, active="settings")


@app.route("/api/settings", methods=["GET", "PUT"])
def settings_api():
    from alerts import get_smtp_settings_safe, save_smtp_settings
    if request.method == "GET":
        return jsonify(get_smtp_settings_safe())
    body = request.get_json(silent=True) or {}
    try:
        save_smtp_settings(**body)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(get_smtp_settings_safe())


@app.route("/api/settings/test", methods=["POST"])
def settings_test_api():
    from alerts import send_test
    try:
        send_test()
        return jsonify({"ok": True})
    except Exception as exc:
        log_msg = f"{type(exc).__name__}: {exc}"
        return jsonify({"ok": False, "error": log_msg}), 500


@app.route("/api/permits/<case_id>/favorite", methods=["PUT", "DELETE"])
def permit_favorite_api(case_id):
    fav = 1 if request.method == "PUT" else 0
    conn = _db()
    cur = conn.execute("UPDATE permits SET favorite = ? WHERE case_id = ?", (fav, case_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": f"unknown permit: {case_id}"}), 404
    return jsonify({"case_id": case_id, "favorite": bool(fav)})


@app.route("/api/stats.json")
def stats_json():
    conn = _db()
    total = conn.execute("SELECT count(*) FROM permits").fetchone()[0]
    geocoded = conn.execute(
        "SELECT count(*) FROM permits WHERE lat IS NOT NULL AND lat != 0"
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT count(*) FROM permits WHERE lat IS NULL AND address IS NOT NULL AND address != ''"
    ).fetchone()[0]
    by_kw = {r[0]: r[1] for r in conn.execute(
        "SELECT keyword, count(*) FROM permits GROUP BY keyword"
    ).fetchall()}
    last_run = conn.execute("SELECT ran_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return jsonify({
        "total": total,
        "geocoded": geocoded,
        "geocode_pending": pending,
        "by_keyword": by_kw,
        "last_run": last_run[0] if last_run else None,
    })
