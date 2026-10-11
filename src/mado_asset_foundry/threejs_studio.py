"""MAF-M1.4: offline ThreeJS Assets Studio WorldPlan and export evidence bridge.

No account access, downloads, Studio automation, license promotion, or publishing.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .io import write_json


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Placement(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    kind: str = Field(min_length=1, max_length=80)
    asset_hint: str = Field(min_length=1, max_length=100)
    x: float = Field(allow_inf_nan=False, ge=-100000, le=100000)
    z: float = Field(allow_inf_nan=False, ge=-100000, le=100000)
    rotation: float = Field(default=0, allow_inf_nan=False, ge=-math.tau, le=math.tau)


class Plan(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=120)
    placements: list[Placement] = Field(min_length=1, max_length=2048)


class CatalogAsset(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=100)
    tier: Literal["free", "premium"]
    entitled: bool


class CatalogSnapshot(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    assets: list[CatalogAsset] = Field(max_length=5000)


class LicenseRecord(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,119}$")
    asset_url: str
    license_label: str = Field(min_length=1, max_length=120)
    evidence_file: str
    reviewed_by_human: bool = False
    game_embedding_allowed: bool = False
    standalone_redistribution_allowed: Literal[False] = False

    @field_validator("asset_url")
    @classmethod
    def official_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme != "https" or url.hostname not in
                {"threejsassets.com", "www.threejsassets.com"}
                or url.username or url.password or url.port is not None):
            raise ValueError("asset_url must be an official HTTPS ThreeJS Assets URL")
        return value


class LicenseLedger(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    assets: list[LicenseRecord] = Field(max_length=5000)


def _load(path: Path, *, max_bytes: int = 2_000_000) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or symlinked input: {path}")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"Input exceeds {max_bytes} bytes: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid JSON/YAML: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_unique(items: list, field: str) -> None:
    keys = [getattr(item, field) for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate {field}")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def compile_worldplan(
    plan_path: str | Path,
    *,
    catalog_path: str | Path | None = None,
    output_root: str | Path = "runs/threejs-studio",
) -> tuple[dict, Path]:
    """Compile schema v1, with advisory exact-slug catalog coverage only."""
    source = Path(plan_path)
    plan = Plan.model_validate(_load(source))
    _ensure_unique(plan.placements, "id")
    catalog = CatalogSnapshot.model_validate(_load(Path(catalog_path))) if catalog_path else None
    if catalog:
        _ensure_unique(catalog.assets, "slug")
    by_slug = {_slug(asset.slug): asset for asset in catalog.assets} if catalog else {}
    out = Path(output_root) / plan.plan_id
    if out.exists() or out.is_symlink():
        raise FileExistsError(f"Output already exists: {out}")

    matches = []
    for p in plan.placements:
        match = by_slug.get(_slug(p.asset_hint))
        matches.append({
            "id": p.id, "asset_hint": p.asset_hint,
            "candidate_slug": match.slug if match else None,
            "catalog_claimed_entitled": match.entitled if match else None,
            "coverage": "candidate" if match and match.entitled else "unverified",
        })
    world = {
        "schemaVersion": 1,
        "name": plan.name,
        "placements": [
            {"id": p.id, "kind": p.kind, "assetHint": p.asset_hint,
             "x": p.x, "z": p.z, "rotation": p.rotation}
            for p in plan.placements
        ],
    }
    report = {
        "schema_version": "0.1", "plan_id": plan.plan_id,
        "status": "awaiting_studio_seed", "placement_count": len(plan.placements),
        "candidate_count": sum(m["coverage"] == "candidate" for m in matches),
        "unverified_count": sum(m["coverage"] == "unverified" for m in matches),
        "matches": matches, "source_plan_sha256": _sha256(source),
        "catalog_snapshot_sha256": _sha256(Path(catalog_path)) if catalog else None,
        "studio_seed_verified": False, "godot_runtime_verified": False,
        "license_approved": False, "publication_approved": False,
        "asset_pack_redistribution_approved": False,
        "network_accessed": False, "external_code_executed": False,
        "notes": "Catalog matches are hints, not live ownership, license or Studio placement proof.",
    }
    # Serialize fully before creating files. Never overwrite an existing run.
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "worldplan.json", world)
    report["worldplan_sha256"] = _sha256(out / "worldplan.json")
    write_json(out / "report.json", report)
    return report, out


def _safe_local(base: Path, name: str) -> Path:
    rel = Path(name)
    if not name or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Evidence filename must stay within its ledger directory")
    cur = base
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError("Symlinked evidence is forbidden")
    path = cur.resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError(f"Missing evidence file: {name}")
    return path


def _glb_check(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("GLB is missing or symlinked")
    size = path.stat().st_size
    if not 20 <= size <= 512 * 1024 * 1024:
        raise ValueError("GLB outside size bounds")
    with path.open("rb") as fh:
        header = fh.read(20)
    magic, version, declared = struct.unpack("<4sII", header[:12])
    if magic != b"glTF" or version != 2 or declared != size:
        raise ValueError("Invalid GLB v2 magic/version/length")
    chunk_length, chunk_type = struct.unpack("<I4s", header[12:20])
    if chunk_type != b"JSON" or chunk_length > size - 20 or chunk_length % 4:
        raise ValueError("Invalid GLB JSON chunk")
    return {"sha256": _sha256(path), "size_bytes": size,
            "format": "glb2_header_checked_only"}


def verify_studio_export(
    run_dir: str | Path, *, map_data: str | Path, glb: str | Path,
    license_ledger: str | Path | None = None,
) -> tuple[dict, Path]:
    """Offline evidence check. Never executes Godot or grants redistribution."""
    folder = Path(run_dir)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Missing or symlinked worldplan run")
    out = folder / "studio-export-evidence.json"
    if out.exists() or out.is_symlink():
        raise FileExistsError(f"Export evidence already exists: {out}")
    report = _load(folder / "report.json")
    worldpath = folder / "worldplan.json"
    world = _load(worldpath)
    if report.get("plan_id") != folder.name or report.get("worldplan_sha256") != _sha256(worldpath):
        raise ValueError("WorldPlan run evidence changed")
    if world.get("schemaVersion") != 1 or not isinstance(world.get("placements"), list):
        raise ValueError("Invalid source WorldPlan")
    map_path = Path(map_data)
    manifest = _load(map_path, max_bytes=8_000_000)
    if manifest.get("format") != "mapproj" or manifest.get("version") != 1:
        raise ValueError("Expected Studio mapproj version 1 export")
    placed = manifest.get("placements")
    if not isinstance(placed, list):
        raise ValueError("Missing Studio placements")
    by_id = {}
    for item in placed:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Studio placements must contain stable IDs")
        if item["id"] in by_id:
            raise ValueError("Duplicate Studio placement id")
        if (not isinstance(item.get("x"), (int, float)) or isinstance(item.get("x"), bool)
                or not math.isfinite(item["x"]) or
                not isinstance(item.get("z"), (int, float)) or isinstance(item.get("z"), bool)
                or not math.isfinite(item["z"])):
            raise ValueError("Non-finite Studio placement")
        ref = item.get("assetRef")
        if not isinstance(ref, dict) or ref.get("source") not in ("site", "local"):
            raise ValueError("Missing Studio assetRef")
        if ref["source"] == "site" and (not isinstance(ref.get("slug"), str) or not ref["slug"]):
            raise ValueError("Studio site assetRef requires slug")
        if ref["source"] == "local" and (not isinstance(ref.get("projectId"), str)
                                         or not ref["projectId"]):
            raise ValueError("Studio local assetRef requires projectId")
        yaw = item.get("ry", 0)
        if not isinstance(yaw, (float, int)) or isinstance(yaw, bool) or not math.isfinite(yaw):
            raise ValueError("Invalid Studio rotation")
        by_id[item["id"]] = item
    expected = {p["id"]: p for p in world["placements"]}
    missing = sorted(set(expected) - set(by_id))
    extra = sorted(set(by_id) - set(expected))
    mismatched = sorted(k for k in expected.keys() & by_id.keys()
                        if abs(expected[k]["x"] - by_id[k]["x"]) > 1e-5
                        or abs(expected[k]["z"] - by_id[k]["z"]) > 1e-5
                        or abs(expected[k]["rotation"] - by_id[k].get("ry", 0)) > 1e-5)
    glb_info = _glb_check(Path(glb))
    license_results = []
    if license_ledger is not None:
        ledger_path = Path(license_ledger)
        ledger = LicenseLedger.model_validate(_load(ledger_path))
        _ensure_unique(ledger.assets, "slug")
        for item in ledger.assets:
            evidence = _safe_local(ledger_path.parent, item.evidence_file)
            license_results.append({"slug": item.slug, "evidence_sha256": _sha256(evidence),
                                    "declared_human_review": item.reviewed_by_human,
                                    "declared_game_embedding_allowed": item.game_embedding_allowed})
    site_slugs = {item["assetRef"].get("slug") for item in by_id.values()
                  if item["assetRef"]["source"] == "site"}
    local_refs = [k for k, item in by_id.items() if item["assetRef"]["source"] == "local"]
    ledger_ok = license_ledger is not None and not local_refs and site_slugs <= {
        item["slug"] for item in license_results
        if item["declared_human_review"] and item["declared_game_embedding_allowed"]
    }
    structural = not (missing or extra or mismatched)
    status = "awaiting_godot_runtime_and_visual_qa" if structural and ledger_ok else "blocked_for_review"
    result = {
        "schema_version": "0.1", "plan_id": folder.name, "status": status,
        "structural_match": structural, "missing_ids": missing, "extra_ids": extra,
        "local_assets_requiring_separate_rights_review": sorted(local_refs),
        "mismatched_transform_ids": mismatched,
        "glb": glb_info, "mapproj_sha256": _sha256(map_path),
        "worldplan_sha256": report["worldplan_sha256"],
        "license_ledger_sha256": _sha256(Path(license_ledger)) if license_ledger else None,
        "license_records": license_results, "operator_declared_rights_complete": bool(ledger_ok),
        "godot_runtime_verified": False, "visual_approved": False,
        "publication_approved": False, "asset_pack_redistribution_approved": False,
        "network_accessed": False, "external_code_executed": False,
        "notes": "GLB header only, not full glTF validation. Human declarations are not legal or release clearance.",
    }
    write_json(out, result)
    return result, out
