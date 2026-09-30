"""Dated BIS LIMS metadata snapshots; never a live recognition or fee verdict."""

from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

from backend.catalogue import ROOT, standard_identity

DEFAULT_LABS_PATH = ROOT / "data" / "reference" / "bis_directories" / "laboratories.json.gz"


@lru_cache(maxsize=2)
def _load_cached(path: str, mtime: int) -> tuple[list[dict], list[dict]]:
    del mtime
    source = Path(path)
    if not source.exists():
        return [], []
    raw = json.loads(gzip.decompress(source.read_bytes()))
    labs, capabilities = raw["laboratories"], raw["capabilities"]
    if not isinstance(labs, list) or not isinstance(capabilities, list):
        raise ValueError("Malformed laboratory snapshot")
    lab_ids = {lab["id"] for lab in labs}
    if len(lab_ids) != len(labs) or any(scope["laboratory_id"] not in lab_ids for scope in capabilities):
        raise ValueError("Laboratory snapshot has duplicate or missing identities")
    return labs, capabilities


def load_laboratories(path: Path = DEFAULT_LABS_PATH) -> tuple[list[dict], list[dict]]:
    return _load_cached(str(path), path.stat().st_mtime_ns if path.exists() else 0)


def search_laboratories(query: str, laboratories: list[dict], capabilities: list[dict]) -> list[dict]:
    """Page by distinct lab; include only genuinely matching scopes for IS searches."""
    needle = " ".join(query.casefold().split())
    tokens = [token for token in re.split(r"[^\w]+", needle) if token and token != "is"]
    identity = standard_identity(query)
    scopes_by_lab: dict[str, list[dict]] = {}
    for scope in capabilities:
        scopes_by_lab.setdefault(scope["laboratory_id"], []).append(scope)
    found: list[dict] = []
    for lab in laboratories:
        lab_scopes = scopes_by_lab.get(lab["id"], [])
        lab_text = " ".join(str(lab.get(field) or "") for field in ("name", "code", "location", "state")).casefold()
        lab_match = bool(tokens) and all(token in lab_text for token in tokens)
        matched_scopes = [scope for scope in lab_scopes if (
            not needle or (identity and standard_identity(scope["standard_identifier"]).startswith(identity))
            or all(token in " ".join(str(scope.get(field) or "") for field in
                                  ("standard_identifier", "product_title", "grade_type")).casefold()
                   for token in tokens)
        )]
        if not needle or lab_match or matched_scopes:
            found.append({"laboratory": lab, "capabilities": lab_scopes if lab_match else matched_scopes})
    if not needle:
        found.sort(key=lambda item: (not bool(item["capabilities"]), item["laboratory"]["name"].casefold()))
    else:
        found.sort(key=lambda item: (not bool(item["capabilities"]), item["laboratory"]["name"].casefold()))
    return found


def laboratory_metadata(laboratories: list[dict], capabilities: list[dict]) -> dict:
    return {
        "laboratory_count": len(laboratories),
        "capability_count": len(capabilities),
        "last_updated": max((lab["retrieved_at"] for lab in laboratories), default=None),
        "coverage_note": "Dated BIS LIMS metadata snapshot; verify current recognition, scope and quotation with BIS LIMS and the laboratory.",
    }
