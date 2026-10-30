"""Render the database as a static, filterable HTML page (docs/index.html)."""

from __future__ import annotations

import json

from fontfind import crawl, db

OUT = db.ROOT / "docs" / "index.html"

LABELS = {
    "qualifies": {
        "yes": "Match", "likely": "Likely", "partial": "Partial", "no": "No", "unknown": "Unknown",
    },
    "logo": {
        "included": "Included",
        "included_small_only": "Included (small cos.)",
        "separate_size_based": "Extra, by company size",
        "separate": "Extra",
        "restricted": "Restricted",
        "unknown": "?",
    },
    "pricing_metric": {
        "company_size": "Company size", "mixed": "Mixed", "seats": "Seats/devices",
        "traffic": "Traffic", "unknown": "?",
    },
    "all_media": {"yes": "Yes", "partial": "Partial", "no": "No", "unknown": "?"},
}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FontFind Licenses</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e4e4e4; --yes:#1f7a3d; --likely:#5a8f1f;
  --partial:#a86b00; --no:#a33; --unknown:#777; --chip:#f2f2f2; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#141414; --fg:#eee;
  --muted:#9a9a9a; --line:#2c2c2c; --yes:#5fcf85; --likely:#a5d65a; --partial:#e6a640; --no:#ef7a7a;
  --unknown:#aaa; --chip:#222; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ margin:0 0 4px; font-size:24px; }}
p.lede {{ color:var(--muted); margin:0 0 20px; }}
.filters {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
.filters button {{ border:1px solid var(--line); background:var(--chip); color:var(--fg); border-radius:999px;
  padding:4px 12px; cursor:pointer; font:inherit; }}
.filters button[aria-pressed="true"] {{ background:var(--fg); color:var(--bg); }}
.card {{ border-top:1px solid var(--line); padding:14px 0; }}
.card h2 {{ font-size:17px; margin:0; display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
.card h2 a {{ color:inherit; }}
.badge {{ font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
.q-yes {{ color:var(--yes); }} .q-likely {{ color:var(--likely); }} .q-partial {{ color:var(--partial); }}
.q-no {{ color:var(--no); }} .q-unknown {{ color:var(--unknown); }}
dl {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:4px 16px; margin:8px 0; }}
dt {{ color:var(--muted); font-size:12px; }} dd {{ margin:0; }}
.summary {{ margin:6px 0; }}
details {{ color:var(--muted); font-size:13px; }}
details li {{ margin:4px 0; }} details a {{ color:inherit; word-break:break-all; }}
.meta {{ color:var(--muted); font-size:12px; }}
.dirhead {{ margin-top:40px; }}
#dirq {{ width:100%; max-width:360px; padding:6px 10px; margin-bottom:12px; font:inherit; }}
.row {{ display:flex; gap:12px; border-top:1px solid var(--line); padding:4px 0; font-size:13px; }}
.row a {{ flex:1; color:inherit; overflow:hidden; text-overflow:ellipsis; }} .row span {{ color:var(--muted); }}
</style>
</head>
<body>
<main>
<h1>Company-size font licenses</h1>
<p class="lede">Foundries that price by company size, and whether logo use is in the license.
Checked {count} foundries. Always read the current EULA before buying.</p>
<div class="filters" id="filters"></div>
<div id="list"></div>
<h2 class="dirhead">Directory: all {dircount} foundries found</h2>
<p class="lede">Every foundry collected automatically and how far it got. "Candidate" means the license
text mentions company-size pricing and is waiting for review.</p>
<input id="dirq" type="search" placeholder="Search foundries" aria-label="Search directory">
<div id="dir"></div>
</main>
<script>
const DATA = {data};
const DIR = {directory};
const ORDER = ["yes","likely","partial","unknown","no"];
const QL = {qlabels};
let active = new Set(["yes","likely","partial"]);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
function render() {{
  const f = document.getElementById("filters");
  f.innerHTML = ORDER.map(q => `<button data-q="${{q}}" aria-pressed="${{active.has(q)}}">${{QL[q]}} (${{DATA.filter(d=>d.qualifies===q).length}})</button>`).join("");
  f.querySelectorAll("button").forEach(b => b.onclick = () => {{
    const q = b.dataset.q; active.has(q) ? active.delete(q) : active.add(q); render(); }});
  document.getElementById("list").innerHTML = DATA.filter(d => active.has(d.qualifies)).map(d => `
    <div class="card">
      <h2><a href="${{esc(d.website)}}" target="_blank" rel="noopener">${{esc(d.name)}}</a>
        <span class="badge q-${{d.qualifies}}">${{esc(QL[d.qualifies])}}</span></h2>
      <dl><div><dt>Priced by</dt><dd>${{esc(d.metric)}}</dd></div>
          <div><dt>Logo</dt><dd>${{esc(d.logo)}}</dd></div>
          <div><dt>All media in one license</dt><dd>${{esc(d.all_media)}}</dd></div></dl>
      <p class="summary">${{esc(d.summary)}}</p>
      ${{d.pricing ? `<p class="meta">Prices${{d.pricing.currency ? " (" + esc(d.pricing.currency) + ")" : ""}}: ${{
        (d.pricing.tiers || []).map(t => `${{esc(t.employees)}} staff: ${{esc(t.price)}}`).join(" · ") || esc(d.pricing.note)
      }}${{d.pricing.tiers && d.pricing.note ? ` — ${{esc(d.pricing.note)}}` : ""}}${{d.pricing.source ? ` (<a href="${{esc(d.pricing.source)}}" target="_blank" rel="noopener">source</a>)` : ""}}</p>` : ""}}
      ${{d.todo ? `<p class="meta">To confirm: ${{esc(d.todo)}}</p>` : ""}}
      <details><summary>Evidence &amp; sources</summary><ul>
        ${{d.evidence.map(e => `<li>${{esc(e.claim)}} — <a href="${{esc(e.source)}}" target="_blank" rel="noopener">${{esc(e.source)}}</a></li>`).join("")}}
        ${{d.license_urls.map(u => `<li>License page: <a href="${{esc(u)}}" target="_blank" rel="noopener">${{esc(u)}}</a></li>`).join("")}}
      </ul></details>
      <p class="meta">Verified ${{esc(d.verified)}}</p>
    </div>`).join("");
}}
render();
function renderDir() {{
  const q = document.getElementById("dirq").value.toLowerCase();
  const rows = DIR.filter(d => !q || d.name.toLowerCase().includes(q) || d.website.toLowerCase().includes(q)).slice(0, 400);
  document.getElementById("dir").innerHTML = rows.map(d =>
    `<div class="row"><a href="${{esc(d.website || "#")}}" target="_blank" rel="noopener">${{esc(d.name)}}</a><span>${{esc(d.status)}}</span></div>`).join("");
}}
document.getElementById("dirq").oninput = renderDir;
renderDir();
</script>
</body>
</html>
"""


def build() -> str:
    foundries = db.load()
    rank = {q: i for i, q in enumerate(db.QUALIFIES_ORDER)}
    foundries.sort(key=lambda f: (rank.get(f.get("qualifies", "unknown"), 99), f["name"].lower()))
    rows = []
    for f in foundries:
        v = f.get("verified") or {}
        rows.append({
            "name": f["name"],
            "website": f.get("website", ""),
            "qualifies": f.get("qualifies", "unknown"),
            "metric": LABELS["pricing_metric"].get(f.get("pricing_metric", "unknown"), "?"),
            "logo": LABELS["logo"].get(f.get("logo", "unknown"), "?"),
            "all_media": LABELS["all_media"].get(f.get("all_media", "unknown"), "?"),
            "summary": " ".join(str(f.get("summary", "")).split()),
            "todo": f.get("todo", ""),
            "pricing": f.get("pricing"),
            "evidence": f.get("evidence") or [],
            "license_urls": f.get("license_urls") or [],
            "verified": f"{v.get('date', '?')} ({v.get('method', '?')})",
        })
    dir_rows = crawl.directory_rows()
    data = json.dumps(rows, ensure_ascii=False, default=str).replace("</", "<\\/")
    page = PAGE.format(
        count=len(rows),
        dircount=len(dir_rows),
        directory=json.dumps(dir_rows, ensure_ascii=False).replace("</", "<\\/"),
        data=data,
        qlabels=json.dumps(LABELS["qualifies"]),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    return str(OUT)


def table(qualifies: set[str] | None = None) -> str:
    """Plain-text table for the terminal."""
    rank = {q: i for i, q in enumerate(db.QUALIFIES_ORDER)}
    rows = sorted(db.load(), key=lambda f: (rank.get(f.get("qualifies"), 99), f["name"].lower()))
    lines = [f"{'Foundry':28} {'Match':8} {'Priced by':14} {'Logo':24} All media"]
    for f in rows:
        if qualifies and f.get("qualifies") not in qualifies:
            continue
        lines.append(
            f"{f['name'][:28]:28} {f.get('qualifies', '?'):8} "
            f"{LABELS['pricing_metric'].get(f.get('pricing_metric'), '?'):14} "
            f"{LABELS['logo'].get(f.get('logo'), '?'):24} "
            f"{LABELS['all_media'].get(f.get('all_media'), '?')}"
        )
    return "\n".join(lines)
