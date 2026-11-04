"""Load and save the YAML foundry database."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "foundries.yaml"

QUALIFIES_ORDER = ["yes", "likely", "partial", "unknown", "no"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load(path: Path = DB_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or {}
    foundries = data.get("foundries", [])
    # YAML 1.1 reads a bare yes/no as a boolean; hand edits often leave them unquoted.
    for f in foundries:
        for key in ("qualifies", "all_media"):
            if isinstance(f.get(key), bool):
                f[key] = "yes" if f[key] else "no"
    return foundries


class _Dumper(yaml.SafeDumper):
    # Indent list items under their key, like the hand-written file.
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def save(foundries: list[dict], path: Path = DB_PATH) -> None:
    # Keep the explanatory header comment at the top of the file.
    header = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                header.append(line)
            else:
                break
    body = yaml.dump(
        {"foundries": foundries},
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=88,
    )
    body = body.replace("\n  - name:", "\n\n  - name:").replace("foundries:\n\n", "foundries:\n", 1)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(header) + ("\n" if header else "") + body, encoding="utf-8")
    tmp.replace(path)


def find(foundries: list[dict], name: str) -> dict | None:
    slug = slugify(name)
    for f in foundries:
        if slugify(f["name"]) == slug:
            return f
    return None
