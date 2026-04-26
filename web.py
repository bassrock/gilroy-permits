import os
import sqlite3
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template_string, jsonify, abort

app = Flask(__name__)
DB_PATH = os.environ.get("DB_PATH", "/data/permits.db")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_KW_COLORS = {
    "solar":    "#f59e0b",
    "fiber":    "#3b82f6",
    "frontier": "#8b5cf6",
}

def _kw_color(kw: str) -> str:
    return _KW_COLORS.get(kw.lower(), "#6b7280")

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
    {% for kw, color in keywords %}
    <option value="{{ kw }}">{{ kw }}</option>
    {% endfor %}
  </select>
  <label><input type="checkbox" id="newonly" onchange="go()"> New (last 7 days)</label>
</div>
<div class="wrap">
<table id="tbl">
  <thead><tr>
    <th>Permit #</th><th>Type</th><th>Status</th><th>Address</th>
    <th>Apply Date</th><th>Keyword</th><th>First Seen</th>
  </tr></thead>
  <tbody>
  {% for p in permits %}
  <tr data-kw="{{ p['keyword'] }}" data-new="{{ 'y' if p['is_new'] else 'n' }}">
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
  let n=0;
  document.querySelectorAll('#tbl tbody tr').forEach(r=>{
    const ok=(!txt||r.textContent.toLowerCase().includes(txt))&&(!kw||r.dataset.kw===kw)&&(!no||r.dataset.new==='y');
    r.classList.toggle('hidden',!ok); if(ok)n++;
  });
  document.getElementById('vis').textContent=n;
}
</script>
</body></html>"""


@app.route("/")
def index():
    cutoff = _new_cutoff()
    conn = _db()
    permits = conn.execute(
        "SELECT *, (first_seen >= ?) AS is_new FROM permits ORDER BY first_seen DESC, apply_date DESC",
        (cutoff,),
    ).fetchall()
    keywords = [(r[0], _kw_color(r[0])) for r in conn.execute(
        "SELECT DISTINCT keyword FROM permits ORDER BY keyword"
    ).fetchall()]
    row = conn.execute("SELECT ran_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    last_run = row[0][:16].replace("T", " ") if row else "never"
    conn.close()
    return render_template_string(
        _LIST_HTML, permits=permits, keywords=keywords,
        total=len(permits), last_run=last_run, kw_color=_kw_color,
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
</body></html>"""


@app.route("/permit/<case_id>")
def detail(case_id):
    conn = _db()
    p = conn.execute("SELECT * FROM permits WHERE case_id=?", (case_id,)).fetchone()
    conn.close()
    if not p:
        abort(404)
    return render_template_string(_DETAIL_HTML, p=p, kw_color=_kw_color, active="")


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

function getColor(kw){ return KW_COLORS[kw.toLowerCase()] || '#6b7280'; }

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
  m._kw = p.keyword.toLowerCase();
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
  const k = kw.toLowerCase();
  if(hiddenKws.has(k)){ hiddenKws.delete(k); el.style.opacity='1'; }
  else { hiddenKws.add(k); el.style.opacity='.35'; }
  applySearch();
}
</script>
</body></html>"""


@app.route("/map")
def map_view():
    from flask import request as req
    highlight = req.args.get("highlight", "")
    conn = _db()
    keywords = [(r[0], _kw_color(r[0])) for r in conn.execute(
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
