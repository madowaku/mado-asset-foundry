from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..io import write_json
from .intake import inspect_skill
from .models import SkillLicense
from .scanner import scan_skill


_TEXT_LIMIT = 2_000_000
_LICENSE_PATTERNS: dict[str, tuple[str, ...]] = {
    "MIT": ("mit license", "permission is hereby granted"),
    "Apache-2.0": ("apache license", "version 2.0"),
    "BSD-3-Clause": (
        "redistribution and use in source and binary forms",
        "neither the name",
    ),
    "GPL-3.0": ("gnu general public license", "version 3"),
    "MPL-2.0": ("mozilla public license", "version 2.0"),
}
_MCP_CONFIGS = (
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
)
_TOOL_TERMS: dict[str, tuple[str, ...]] = {
    "ffmpeg": ("ffmpeg",),
    "blender": ("blender",),
}
_SAFETY_TERMS: dict[str, tuple[str, ...]] = {
    "ownership_required": ("only mod games the user owns",),
    "offline_or_controlled_server_only": ("stay in single-player/offline",),
    "no_anticheat_or_drm_bypass": (
        "never bypass anti-cheat, drm or ownership checks",
    ),
    "no_game_file_redistribution": ("don't ship game files",),
    "backup_before_mutation": ("back up first",),
    "human_confirmation_for_machine_changes": ("ask before installing",),
}


class PackMember(BaseModel):
    skill_id: str
    relative_path: str
    capabilities: list[str] = Field(default_factory=list)
    runtime: list[str] = Field(default_factory=list)
    manifest_path: str
    report_path: str
    decision: Literal["adapter_required", "out_of_scope"]


class PackCliEntrypoint(BaseModel):
    name: str
    target: str
    source_file: str = "pyproject.toml"


class PackMcpServer(BaseModel):
    name: str
    url: str | None = None
    source_file: str


class PackDependencyEvidence(BaseModel):
    dependency: str
    kind: Literal["python_package", "tool", "service"]
    source_file: str
    matched_term: str


class PackSafetyEvidence(BaseModel):
    constraint: str
    source_file: str
    matched_term: str


class SkillPackReport(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    pack_id: str
    source_path: str
    upstream_url: str | None = None
    upstream_ref: str | None = None
    snapshot_kind: str | None = None
    discovered_skills: list[str] = Field(default_factory=list)
    candidate_skills: list[str] = Field(default_factory=list)
    members: list[PackMember] = Field(default_factory=list)
    license: SkillLicense = Field(default_factory=SkillLicense)
    cli_entrypoints: list[PackCliEntrypoint] = Field(default_factory=list)
    mcp_servers: list[PackMcpServer] = Field(default_factory=list)
    dependencies: list[PackDependencyEvidence] = Field(default_factory=list)
    safety_constraints: list[PackSafetyEvidence] = Field(default_factory=list)
    external_code_executed: bool = False
    capability_classification_performed: bool = True
    status: Literal["success"] = "success"


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > _TEXT_LIMIT:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("could not derive a valid pack_id")
    return slug


def _load_snapshot_metadata(source: Path) -> dict[str, object]:
    path = source / "SNAPSHOT.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not parse snapshot metadata: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Snapshot metadata must be an object: {path}")
    return data


def discover_skill_directories(source_path: str | Path) -> list[Path]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Skill pack source not found: {source}")
    if not source.is_dir():
        raise ValueError(f"Skill pack source must be a directory: {source}")

    skills_root = source / "skills"
    if not skills_root.is_dir():
        raise ValueError(f"Skill pack has no skills directory: {skills_root}")

    directories = {
        path.parent
        for path in skills_root.rglob("SKILL.md")
        if path.is_file()
    }
    return sorted(
        directories,
        key=lambda path: path.relative_to(source).as_posix(),
    )


def _scan_repo_license(source: Path) -> SkillLicense:
    license_path = next(
        (
            source / name
            for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
            if (source / name).is_file()
        ),
        None,
    )
    if license_path is None:
        return SkillLicense(status="unknown")

    text = _read_text(license_path).lower()
    matched = [
        spdx
        for spdx, patterns in _LICENSE_PATTERNS.items()
        if all(pattern in text for pattern in patterns)
    ]
    relative = license_path.relative_to(source).as_posix()
    if len(matched) == 1:
        return SkillLicense(spdx=matched[0], source_file=relative, status="detected")
    if len(matched) > 1:
        return SkillLicense(source_file=relative, status="ambiguous")
    return SkillLicense(source_file=relative, status="unknown")


def _scan_cli_entrypoints(source: Path) -> list[PackCliEntrypoint]:
    path = source / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not parse pyproject metadata: {path}") from exc

    scripts = data.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [
        PackCliEntrypoint(name=str(name), target=str(target))
        for name, target in sorted(scripts.items())
    ]


def _scan_mcp_servers(source: Path) -> list[PackMcpServer]:
    servers: list[PackMcpServer] = []
    seen: set[tuple[str, str | None]] = set()

    for relative in _MCP_CONFIGS:
        path = source / relative
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        mapping = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(mapping, dict):
            continue
        for name, config in sorted(mapping.items()):
            url = config.get("url") if isinstance(config, dict) else None
            key = (str(name), str(url) if url is not None else None)
            if key in seen:
                continue
            seen.add(key)
            servers.append(
                PackMcpServer(
                    name=str(name),
                    url=str(url) if url is not None else None,
                    source_file=relative,
                )
            )
    return servers


def _skill_documents(source: Path) -> list[Path]:
    return sorted(
        (path for path in (source / "skills").rglob("SKILL.md") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix(),
    )


def _scan_dependencies(
    source: Path,
    mcp_servers: list[PackMcpServer],
) -> list[PackDependencyEvidence]:
    evidence: list[PackDependencyEvidence] = []
    seen: set[tuple[str, str]] = set()

    pyproject = source / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not parse pyproject metadata: {pyproject}") from exc
        dependencies = data.get("project", {}).get("dependencies", [])
        if isinstance(dependencies, list):
            for raw in dependencies:
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", str(raw))
                if not match:
                    continue
                name = match.group(1).lower().replace("_", "-")
                key = ("python_package", name)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    PackDependencyEvidence(
                        dependency=name,
                        kind="python_package",
                        source_file="pyproject.toml",
                        matched_term=str(raw),
                    )
                )

    documents = [
        (path.relative_to(source).as_posix(), _read_text(path).lower())
        for path in _skill_documents(source)
    ]
    for tool, terms in _TOOL_TERMS.items():
        found = False
        for source_file, text in documents:
            for term in terms:
                if term in text:
                    key = ("tool", tool)
                    if key not in seen:
                        seen.add(key)
                        evidence.append(
                            PackDependencyEvidence(
                                dependency=tool,
                                kind="tool",
                                source_file=source_file,
                                matched_term=term,
                            )
                        )
                    found = True
                    break
            if found:
                break

    for server in mcp_servers:
        key = ("service", server.name)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            PackDependencyEvidence(
                dependency=server.name,
                kind="service",
                source_file=server.source_file,
                matched_term=server.url or server.name,
            )
        )

    return evidence


def _scan_safety(source: Path) -> list[PackSafetyEvidence]:
    documents = [
        (path.relative_to(source).as_posix(), _read_text(path).lower())
        for path in _skill_documents(source)
    ]
    evidence: list[PackSafetyEvidence] = []
    for constraint, terms in _SAFETY_TERMS.items():
        matched = False
        for source_file, text in documents:
            for term in terms:
                if term in text:
                    evidence.append(
                        PackSafetyEvidence(
                            constraint=constraint,
                            source_file=source_file,
                            matched_term=term,
                        )
                    )
                    matched = True
                    break
            if matched:
                break
    return evidence


def scan_skill_pack(
    source_path: str | Path,
    *,
    manifest_dir: str | Path = "skills/manifests",
    evidence_dir: str | Path = "evidence/skill-pack-scan",
    force: bool = False,
) -> tuple[SkillPackReport, Path]:
    source = Path(source_path)
    skill_dirs = discover_skill_directories(source)
    if not skill_dirs:
        raise ValueError(f"No SKILL.md files found under: {source / 'skills'}")

    snapshot = _load_snapshot_metadata(source)
    pack_id = _slugify(str(snapshot.get("pack_id") or source.name))
    member_manifest_dir = Path(manifest_dir) / pack_id
    member_evidence_dir = Path(evidence_dir) / pack_id / "members"
    pack_report_path = Path(evidence_dir) / pack_id / "pack-report.json"

    prepared: list[tuple[Path, str]] = []
    for skill_dir in skill_dirs:
        manifest, _ = inspect_skill(skill_dir)
        prepared.append((skill_dir, manifest.skill_id))

    targets = [pack_report_path]
    for _, skill_id in prepared:
        targets.extend(
            [
                member_manifest_dir / f"{skill_id}.json",
                member_evidence_dir / skill_id / "report.json",
            ]
        )
    if not force:
        existing = next((target for target in targets if target.exists()), None)
        if existing is not None:
            raise FileExistsError(
                f"Skill pack scan output already exists: {existing}; use --force to replace it"
            )

    members: list[PackMember] = []
    for skill_dir, _ in prepared:
        manifest, manifest_path, report_path = scan_skill(
            skill_dir,
            manifest_dir=member_manifest_dir,
            evidence_dir=member_evidence_dir,
            force=force,
        )
        decision: Literal["adapter_required", "out_of_scope"] = (
            "adapter_required" if manifest.capabilities else "out_of_scope"
        )
        members.append(
            PackMember(
                skill_id=manifest.skill_id,
                relative_path=skill_dir.relative_to(source).as_posix(),
                capabilities=manifest.capabilities,
                runtime=manifest.runtime,
                manifest_path=str(manifest_path),
                report_path=str(report_path),
                decision=decision,
            )
        )

    mcp_servers = _scan_mcp_servers(source)
    report = SkillPackReport(
        pack_id=pack_id,
        source_path=str(source_path),
        upstream_url=str(snapshot.get("upstream_url")) if snapshot.get("upstream_url") else None,
        upstream_ref=str(snapshot.get("upstream_ref")) if snapshot.get("upstream_ref") else None,
        snapshot_kind=str(snapshot.get("snapshot_kind")) if snapshot.get("snapshot_kind") else None,
        discovered_skills=[member.skill_id for member in members],
        candidate_skills=[
            member.skill_id
            for member in members
            if member.decision == "adapter_required"
        ],
        members=members,
        license=_scan_repo_license(source),
        cli_entrypoints=_scan_cli_entrypoints(source),
        mcp_servers=mcp_servers,
        dependencies=_scan_dependencies(source, mcp_servers),
        safety_constraints=_scan_safety(source),
    )
    write_json(pack_report_path, report.model_dump(mode="json"))
    return report, pack_report_path
