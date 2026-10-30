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

TEMPLATE = db.ROOT / "fontfind" / "report_template.html"


def price_from(pricing: dict | None) -> str:
    """Smallest published tier as a short label, e.g. 'EUR 327 · solo'."""
    tiers = [t for t in (pricing or {}).get("tiers") or [] if any(ch.isdigit() for ch in str(t.get("price", "")))]
    if not tiers:
        return ""
    first = tiers[0]
    return f"{pricing.get('currency', '')} {first.get('price', '')}".strip() + f" · {first.get('employees', '')}"


def build() -> str:
    foundries = [f for f in db.load() if f.get("qualifies") != "no"]
    rank = {q: i for i, q in enumerate(db.QUALIFIES_ORDER)}
    foundries.sort(key=lambda f: (rank.get(f.get("qualifies", "unknown"), 99), f["name"].lower()))
    rows = []
    for f in foundries:
        v = f.get("verified") or {}
        info = f.get("info") or {}
        rows.append({
            "name": f["name"],
            "website": f.get("website", ""),
            "qualifies": f.get("qualifies", "unknown"),
            "metric": LABELS["pricing_metric"].get(f.get("pricing_metric", "unknown"), "?"),
            "logo": LABELS["logo"].get(f.get("logo", "unknown"), "?"),
            "logo_raw": f.get("logo", "unknown"),
            "all_media": LABELS["all_media"].get(f.get("all_media", "unknown"), "?"),
            "media_raw": f.get("all_media", "unknown"),
            "summary": " ".join(str(f.get("summary", "")).split()),
            "todo": " ".join(str(f.get("todo", "")).split()),
            "pricing": f.get("pricing"),
            "price": price_from(f.get("pricing")),
            "evidence": f.get("evidence") or [],
            "license_urls": f.get("license_urls") or [],
            "verified": f"{v.get('date', '?')} ({v.get('method', '?')})",
            "image": info.get("image", ""),
            "description": info.get("description", ""),
            "typefaces": info.get("typefaces") or [],
            "country": info.get("country", ""),
            "founded": info.get("founded", ""),
        })
    ruled_out = {"curated:no", "not-company-size", "no-license-page"}
    dir_rows = [r for r in crawl.directory_rows() if r["status"] not in ruled_out]

    def js(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str).replace("</", "<\\/")

    page = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__COUNT__", str(len(rows)))
        .replace("__DIRCOUNT__", str(len(dir_rows)))
        .replace("__DATA__", js(rows))
        .replace("__DIRECTORY__", js(dir_rows))
        .replace("__QLABELS__", js(LABELS["qualifies"]))
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
