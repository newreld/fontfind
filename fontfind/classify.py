"""Heuristic classification of license text.

This does not decide anything on its own. It finds sentences that hint at how a
foundry prices its licenses and how it treats logo use, so a human can confirm
them quickly and fill in the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# What the price scales with.
METRIC_PATTERNS = {
    "company_size": [
        r"company[\s-]size",
        r"business size",
        r"size of (?:the |your )?(?:company|organi[sz]ation|business)",
        r"(?:number|total) of (?:employees|people|staff|personnel)",
        r"\bheadcount\b",
        r"\bup to \d[\d,.]* (?:employees|people|staff)\b",
        r"\bemployees\b",
    ],
    "seats": [
        r"\bworkstations?\b",
        r"number of (?:computers|users|seats|devices|installations)",
        r"\bper (?:user|seat|computer|device)\b",
        r"\b\d+\s*(?:users|computers|seats|desktops)\b",
    ],
    "traffic": [
        r"page ?views",
        r"(?:monthly|unique) (?:unique )?visitors",
        r"monthly active users",
        r"\bMAU\b",
        r"\bdownloads\b",
        r"\bimpressions\b",
    ],
}

LOGO = r"(?:logos?|logotypes?|wordmarks?|word[\s-]marks?|trade ?marks?)"

# "No extra fee for logos" must not be read as a paid logo add-on.
NO_EXTRA_FEE = re.compile(r"(?:no|without|free of) (?:extra|additional|separate)", re.I)

LOGO_PATTERNS = {
    "separate": [
        rf"{LOGO} licen[cs]e",
        rf"licen[cs]e for (?:each|every|a|the) {LOGO}",
        rf"{LOGO}.{{0,60}}(?:add-on|additional fee|separate(?:ly)?|extra|surcharge)",
        rf"(?:add-on|additional fee|separate(?:ly)?|extra|surcharge).{{0,60}}{LOGO}",
    ],
    "restricted": [
        rf"(?:may|must|can)\s?not (?:be )?(?:use[d]?|include).{{0,80}}{LOGO}",
        rf"{LOGO}.{{0,60}}(?:not (?:permitted|allowed)|prohibited|forbidden)",
        rf"not .{{0,20}}register.{{0,40}}trade ?mark",
    ],
    "included": [
        rf"{LOGO}.{{0,80}}(?:included|covered|permitted|allowed)",
        rf"(?:includ\w*|cover\w*|permit\w*|allow\w*).{{0,80}}{LOGO}",
        rf"(?:use|create|design)\w* .{{0,40}}{LOGO}",
    ],
}

# Signals that one license spans every medium.
ALL_MEDIA_PATTERNS = [
    r"all[\s-]in[\s-]one",
    r"all (?:types of )?media",
    r"one licen[cs]e (?:for|covers)",
    r"single licen[cs]e",
    r"\bunlimited use\b",
    r"(?:desktop|print).{0,40}web.{0,40}app",
]

# Web use is part of the license (not a separate web/pageview product).
WEB_PATTERN = re.compile(r"\bweb ?(?:site|fonts?|sites|pages?)?\b|\bwebfonts?\b|\bwoff2?\b|\bonline\b", re.I)

_COMPILED = {
    "metric": {k: [re.compile(p, re.I) for p in v] for k, v in METRIC_PATTERNS.items()},
    "logo": {k: [re.compile(p, re.I) for p in v] for k, v in LOGO_PATTERNS.items()},
    "all_media": [re.compile(p, re.I) for p in ALL_MEDIA_PATTERNS],
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
MAX_EVIDENCE = 4


@dataclass
class Result:
    metric_scores: dict[str, int] = field(default_factory=dict)
    logo_scores: dict[str, int] = field(default_factory=dict)
    all_media_hits: int = 0
    web_hits: int = 0
    evidence: dict[str, list[str]] = field(default_factory=dict)

    def metric(self) -> str:
        scores = {k: v for k, v in self.metric_scores.items() if v}
        if not scores:
            return "unknown"
        cs = scores.get("company_size", 0)
        other = max((v for k, v in scores.items() if k != "company_size"), default=0)
        if cs and cs >= 2 * other:
            return "company_size"
        if cs and other:
            return "mixed"
        return max(scores, key=scores.get)

    def logo(self) -> str:
        s = self.logo_scores
        if not any(s.values()):
            return "unknown"
        # A dedicated logo license or a restriction outweighs generic
        # "logos are allowed" wording, which often describes that very license.
        if s.get("separate"):
            return "separate"
        if s.get("restricted") and s.get("restricted", 0) >= s.get("included", 0):
            return "restricted"
        return "included"

    def suggestion(self) -> str:
        metric, logo = self.metric(), self.logo()
        if metric in ("seats", "traffic"):
            return "no"
        if metric == "company_size" and logo == "included":
            return "likely" if self.all_media_hits and self.web_hits else "partial"
        if metric in ("company_size", "mixed"):
            return "partial"
        return "unknown"

    def as_dict(self) -> dict:
        return {
            "suggested_metric": self.metric(),
            "suggested_logo": self.logo(),
            "suggested_qualifies": self.suggestion(),
            "metric_scores": {k: v for k, v in self.metric_scores.items() if v},
            "logo_scores": {k: v for k, v in self.logo_scores.items() if v},
            "all_media_hits": self.all_media_hits,
            "web_hits": self.web_hits,
            "evidence": {k: v for k, v in self.evidence.items() if v},
        }


def sentences(text: str) -> list[str]:
    out = []
    for s in _SENTENCE_SPLIT.split(text):
        s = " ".join(s.split())
        if 15 <= len(s) <= 600:
            out.append(s)
    return out


def _add(result: Result, key: str, sentence: str) -> None:
    bucket = result.evidence.setdefault(key, [])
    if sentence not in bucket and len(bucket) < MAX_EVIDENCE:
        bucket.append(sentence)


def classify(text: str) -> Result:
    r = Result()
    for s in sentences(text):
        for name, patterns in _COMPILED["metric"].items():
            if any(p.search(s) for p in patterns):
                r.metric_scores[name] = r.metric_scores.get(name, 0) + 1
                _add(r, f"metric:{name}", s)
        if re.search(LOGO, s, re.I):
            # Count each sentence once, under the most specific category.
            if any(p.search(s) for p in _COMPILED["logo"]["restricted"]):
                name = "restricted"
            elif NO_EXTRA_FEE.search(s):
                name = "included"
            else:
                name = next(
                    (n for n in ("separate", "included") if any(p.search(s) for p in _COMPILED["logo"][n])),
                    None,
                )
            if name:
                r.logo_scores[name] = r.logo_scores.get(name, 0) + 1
                _add(r, f"logo:{name}", s)
        if WEB_PATTERN.search(s):
            r.web_hits += 1
        if any(p.search(s) for p in _COMPILED["all_media"]):
            r.all_media_hits += 1
            _add(r, "all_media", s)
    return r
