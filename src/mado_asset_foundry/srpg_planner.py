"""MAF-M1.6: deterministic, offline SRPG asset-needs planning.

A candidate is never a license clearance. This module never opens asset URLs,
fetches assets, executes third-party code, or changes the M0.9 intake gate.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .asset_sources import get_source, load_source_registry
from .io import write_json


Slug = str
Category = Literal["terrain", "character", "building", "equipment", "icon", "ui", "vfx", "sound"]
Priority = Literal["high", "medium", "low"]
Route = Literal["reference", "external", "original"]


class AssetNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: Category
    description: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=10000)
    priority: Priority = "medium"


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    need_id: str
    route: Route
    source_id: str | None = None
    url: str | None = None
    note: str = ""


class SRPGBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    project: str = Field(min_length=1)
    engine: Literal["godot", "web", "other"]
    needs: list[AssetNeed] = Field(min_length=1)
    candidates: list[Candidate] = Field(default_factory=list)


def _https_host(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port is not None):
        raise ValueError(f"Candidate URL must be standard HTTPS: {url}")
    return parsed.hostname.lower().rstrip(".")


def _within_hosts(host: str, hosts: list[str]) -> bool:
    return any(host == name or host.endswith("." + name) for name in hosts)


def plan_srpg_assets(
    brief_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    output_path: str | Path = "evidence/srpg-intelligence/plan.json",
    force: bool = False,
) -> tuple[dict[str, object], Path]:
    """Plan *work*, not usage rights. No inputs are executed or downloaded."""
    input_path = Path(brief_path)
    raw = input_path.read_bytes()
    try:
        brief = SRPGBrief.model_validate(yaml.safe_load(raw.decode("utf-8")))
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError("Invalid SRPG brief YAML") from exc

    need_ids = [need.need_id for need in brief.needs]
    candidate_ids = [candidate.candidate_id for candidate in brief.candidates]
    if len(need_ids) != len(set(need_ids)):
        raise ValueError("Duplicate SRPG need IDs")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Duplicate SRPG candidate IDs")

    registry = load_source_registry(registry_path)
    grouped: dict[str, list[dict[str, str | None]]] = {key: [] for key in need_ids}
    for candidate in brief.candidates:
        if candidate.need_id not in grouped:
            raise ValueError(f"Candidate references unknown need: {candidate.need_id}")
        if candidate.route == "reference":
            if not candidate.url or candidate.source_id is not None:
                raise ValueError("Reference candidate requires URL and no source_id")
            _https_host(candidate.url)
            status = "study_only"
            action = "study_reference_no_copy"
        elif candidate.route == "external":
            if not candidate.source_id or not candidate.url:
                raise ValueError("External candidate requires registered source_id and URL")
            source = get_source(registry, candidate.source_id)
            if source.discovery_mode != "manual":
                raise ValueError("External candidate requires a manual source")
            if not _within_hosts(_https_host(candidate.url), source.allowed_hosts):
                raise ValueError("Candidate URL does not match registered source hosts")
            status = "intake_required"
            action = "collect_original_creator_license_and_run_maf_asset_source_intake"
        else:
            if candidate.url is not None or candidate.source_id is not None:
                raise ValueError("Original generation candidate cannot claim external rights")
            status = "not_created"
            action = "produce_original_then_verify_and_review"
        grouped[candidate.need_id].append({
            "candidate_id": candidate.candidate_id,
            "route": candidate.route,
            "source_id": candidate.source_id,
            "url": candidate.url,
            "note": candidate.note,
            "status": status,
            "action": action,
        })

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    planned: list[dict[str, object]] = []
    for need in sorted(brief.needs, key=lambda n: (priority_rank[n.priority], n.need_id)):
        options = sorted(grouped[need.need_id], key=lambda c: str(c["candidate_id"]))
        routes = {candidate["route"] for candidate in options}
        if "original" in routes:
            next_action = "produce_original"
        elif "external" in routes:
            next_action = "verify_license_via_existing_asset_intake"
        elif "reference" in routes:
            next_action = "create_original_from_brief_not_copy"
        else:
            next_action = "find_licensed_source_or_create_original"
        planned.append({
            **need.model_dump(),
            "ready_quantity": 0,
            "unverified_quantity": need.quantity,
            "next_action": next_action,
            "candidates": options,
        })

    report: dict[str, object] = {
        "schema_version": "0.1",
        "project": brief.project,
        "engine": brief.engine,
        "brief_sha256": hashlib.sha256(raw).hexdigest(),
        "need_count": len(planned),
        "required_quantity": sum(n.quantity for n in brief.needs),
        "ready_quantity": 0,
        "needs": planned,
        "rights_verified": False,
        "publication_approved": False,
        "asset_copied": False,
        "network_accessed": False,
        "external_code_executed": False,
        "warnings": [
            "References and repository-level MIT badges are not per-asset rights.",
            "External assets must pass the existing M0.9 human-reviewed per-asset intake.",
            "Even M0.9 eligible status is not authorization to publish.",
        ],
    }

    destination = Path(output_path)
    if destination.exists() and not force:
        raise FileExistsError(f"SRPG plan already exists: {destination}")
    write_json(destination, report)
    return report, destination
