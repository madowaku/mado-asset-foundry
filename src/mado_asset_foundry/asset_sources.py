"""MAF-M0.9: offline, evidence-first asset source intake.

This module does not retrieve assets, execute external code, or grant publishing rights.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .io import write_json


class AssetSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    homepage: str
    allowed_hosts: list[str] = Field(default_factory=list)
    discovery_mode: Literal["manual", "local"]
    redistribution_policy: Literal["evidence_required", "review", "blocked"] = "review"
    license_hint: str = "per-asset verification required"
    terms_url: str | None = None
    notes: str = ""


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    sources: list[AssetSource]


class AssetSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    source_id: str
    title: str = Field(min_length=1)
    creator: str = Field(min_length=1)
    local_file: str = Field(min_length=1)
    asset_url: str | None = None
    license_spdx: str = Field(min_length=1)
    license_evidence_url: str | None = None
    license_evidence_file: str | None = None
    attribution: str | None = None
    reviewed_by_human: bool = False
    use_case: Literal["game_embedding", "asset_pack_redistribution"]
    commercial: bool = True


def bundled_registry_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "asset_sources.json"


def load_source_registry(path: str | Path | None = None) -> SourceRegistry:
    source = Path(path) if path is not None else bundled_registry_path()
    if not source.is_file():
        raise FileNotFoundError(f"Asset source registry not found: {source}")
    try:
        registry = SourceRegistry.model_validate(
            json.loads(source.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid asset source registry: {source}") from exc
    ids = [item.source_id for item in registry.sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate asset source IDs")
    for item in registry.sources:
        if item.discovery_mode == "manual" and not item.allowed_hosts:
            raise ValueError(f"No allowed hosts for source {item.source_id}")
    return registry


def get_source(registry: SourceRegistry, source_id: str) -> AssetSource:
    for source in registry.sources:
        if source.source_id == source_id:
            return source
    raise ValueError(f"Unknown asset source: {source_id}")


def _https_host(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port is not None):
        raise ValueError(f"Expected a standard HTTPS URL: {url}")
    return parsed.hostname.lower().rstrip(".")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


def _local_file(base: Path, raw: str) -> Path:
    if Path(raw).is_absolute():
        raise ValueError("Local file must be relative to its submission directory")
    path = base / raw
    if path.is_symlink():
        raise ValueError(f"Symlink is not allowed for intake: {raw}")
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f"Local file escapes submission directory: {raw}")
    if not resolved.is_file():
        raise FileNotFoundError(f"Intake file not found: {raw}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_submission(
    manifest: AssetSubmission,
    source: AssetSource,
    *,
    has_evidence: bool,
) -> tuple[str, list[str], list[str]]:
    """Classify intake only, never assert legal clearance or publication approval."""
    blocked: list[str] = []
    review: list[str] = []
    warnings: list[str] = []

    if not has_evidence:
        review.append("Missing per-asset license evidence")
    if not manifest.reviewed_by_human:
        review.append("A human must verify the asset-specific license and rights")

    license_id = manifest.license_spdx.upper().strip()
    if "NC" in license_id and manifest.commercial:
        blocked.append("Noncommercial license cannot pass a commercial-use intake")
    elif license_id == "CC0-1.0":
        pass
    elif license_id in {"CC-BY-3.0", "CC-BY-4.0"}:
        if not manifest.attribution or not manifest.attribution.strip():
            review.append("CC BY requires an attribution statement")
        if manifest.use_case == "asset_pack_redistribution":
            review.append("Standalone asset redistribution requires separate review")
    elif license_id in {"CC-BY-SA-3.0", "CC-BY-SA-4.0", "GPL-2.0-ONLY",
                        "GPL-3.0-ONLY", "OGA-BY-3.0"}:
        review.append("Share-alike or special-license obligations require manual review")
    else:
        review.append(f"License {manifest.license_spdx} is not auto-eligible")

    if source.redistribution_policy == "blocked":
        if manifest.use_case == "asset_pack_redistribution":
            blocked.append(f"{source.name} source policy blocks standalone redistribution")
        else:
            review.append(f"{source.name} rights require individual review")
    elif source.redistribution_policy == "review":
        review.append(f"{source.name} source policy requires manual review")

    warnings.append("Intake eligibility is not publication approval or a legal opinion")
    if blocked:
        return "blocked", sorted(set(blocked + review)), warnings
    if review:
        return "needs_review", sorted(set(review)), warnings
    return "eligible", [], warnings


def intake_asset(
    manifest_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    output_root: str | Path = "evidence/asset-intake",
    force: bool = False,
) -> tuple[dict[str, object], Path]:
    """Hash a supplied local asset and emit immutable-source evidence, with no network access."""
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Asset submission not found: {path}")
    try:
        submission = AssetSubmission.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError(f"Invalid asset submission: {path}") from exc

    registry = load_source_registry(registry_path)
    source = get_source(registry, submission.source_id)
    if source.discovery_mode == "manual":
        if not submission.asset_url:
            raise ValueError("External asset submission requires asset_url")
        if not _host_allowed(_https_host(submission.asset_url), source.allowed_hosts):
            raise ValueError("Asset URL does not match source's registered hosts")
        if submission.license_evidence_url and not _host_allowed(
            _https_host(submission.license_evidence_url), source.allowed_hosts
        ):
            raise ValueError("License evidence URL must be on the asset source site")
    elif submission.asset_url:
        _https_host(submission.asset_url)
    if submission.license_evidence_url:
        _https_host(submission.license_evidence_url)

    asset_file = _local_file(path.parent, submission.local_file)
    if asset_file.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Asset is over the 512 MiB M0.9 intake limit")
    license_evidence_hash = None
    if submission.license_evidence_file:
        license_file = _local_file(path.parent, submission.license_evidence_file)
        license_evidence_hash = _sha256(license_file)

    report_path = Path(output_root) / submission.asset_id / "report.json"
    if report_path.exists() and not force:
        raise FileExistsError(f"Intake evidence already exists: {report_path}")

    has_evidence = bool(submission.license_evidence_url or license_evidence_hash)
    status, reasons, warnings = evaluate_submission(
        submission, source, has_evidence=has_evidence
    )
    report: dict[str, object] = {
        "schema_version": "0.1",
        "asset_id": submission.asset_id,
        "title": submission.title,
        "source_id": source.source_id,
        "source_homepage": source.homepage,
        "asset_url": submission.asset_url,
        "source_discovery_mode": source.discovery_mode,
        "local_file": submission.local_file,
        "sha256": _sha256(asset_file),
        "size_bytes": asset_file.stat().st_size,
        "creator": submission.creator,
        "license_spdx": submission.license_spdx,
        "license_evidence_url": submission.license_evidence_url,
        "license_evidence_file": submission.license_evidence_file,
        "license_evidence_sha256": license_evidence_hash,
        "attribution": submission.attribution,
        "reviewed_by_human": submission.reviewed_by_human,
        "use_case": submission.use_case,
        "commercial": submission.commercial,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "publication_approved": False,
        "network_accessed": False,
        "external_code_executed": False,
        "asset_copied": False,
    }
    write_json(report_path, report)
    return report, report_path
