from __future__ import annotations

import json
from pathlib import Path

from ..io import write_json
from .models import (
    CapabilityResolution,
    ResolutionCandidate,
    SkillManifest,
    SkillRegistry,
    SkillRegistryEntry,
)


def _load_manifest(path: Path) -> SkillManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SkillManifest.model_validate(data)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid Skill manifest: {path}") from exc


def build_registry(
    manifest_dir: str | Path = "skills/manifests",
    *,
    output_path: str | Path = "skills/registry.json",
    force: bool = False,
) -> tuple[SkillRegistry, Path]:
    source = Path(manifest_dir)
    if not source.exists():
        raise FileNotFoundError(f"Skill manifest directory not found: {source}")
    if not source.is_dir():
        raise ValueError(f"Skill manifest path must be a directory: {source}")

    output = Path(output_path)
    if output.exists() and not force:
        raise FileExistsError(f"Skill registry already exists: {output}; use --force to replace it")

    manifests: list[tuple[Path, SkillManifest]] = []
    for path in sorted(source.rglob("*.json"), key=lambda item: item.as_posix()):
        if path.resolve() == output.resolve():
            continue
        manifests.append((path, _load_manifest(path)))

    seen: dict[str, Path] = {}
    entries: list[SkillRegistryEntry] = []
    for path, manifest in manifests:
        previous = seen.get(manifest.skill_id)
        if previous is not None:
            raise ValueError(
                f"Duplicate skill_id '{manifest.skill_id}' in {previous} and {path}"
            )
        seen[manifest.skill_id] = path
        entries.append(
            SkillRegistryEntry(
                skill_id=manifest.skill_id,
                name=manifest.name,
                manifest_path=str(path),
                source=manifest.source,
                license=manifest.license,
                capabilities=list(manifest.capabilities),
                runtime=list(manifest.runtime),
                adapter_status=manifest.adapter_status,
            )
        )

    entries.sort(key=lambda entry: entry.skill_id)
    registry = SkillRegistry(entries=entries)
    write_json(output, registry.model_dump(mode="json"))
    return registry, output


def load_registry(path: str | Path = "skills/registry.json") -> SkillRegistry:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Skill registry not found: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return SkillRegistry.model_validate(data)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid Skill registry: {source}") from exc


def get_registry_entry(
    registry: SkillRegistry,
    skill_id: str,
) -> SkillRegistryEntry:
    for entry in registry.entries:
        if entry.skill_id == skill_id:
            return entry
    raise KeyError(skill_id)


def resolve_capability(
    registry: SkillRegistry,
    capability: str,
) -> CapabilityResolution:
    matching = [
        entry
        for entry in registry.entries
        if capability in entry.capabilities
    ]

    rank = {"executable": 0, "intake_only": 1, "unsupported": 2}
    matching.sort(key=lambda entry: (rank[entry.adapter_status], entry.skill_id))

    candidates = [
        ResolutionCandidate(
            skill_id=entry.skill_id,
            name=entry.name,
            adapter_status=entry.adapter_status,
            manifest_path=entry.manifest_path,
            runtime=list(entry.runtime),
            license_status=entry.license.status,
            license_spdx=entry.license.spdx,
            license_name=entry.license.name,
        )
        for entry in matching
    ]

    executable = [entry for entry in matching if entry.adapter_status == "executable"]
    intake_only = [entry for entry in matching if entry.adapter_status == "intake_only"]

    if len(executable) == 1:
        return CapabilityResolution(
            capability=capability,
            status="resolved",
            selected_skill_id=executable[0].skill_id,
            candidates=candidates,
        )
    if len(executable) > 1:
        return CapabilityResolution(
            capability=capability,
            status="ambiguous",
            candidates=candidates,
        )
    if intake_only:
        return CapabilityResolution(
            capability=capability,
            status="candidate_only",
            candidates=candidates,
        )
    return CapabilityResolution(
        capability=capability,
        status="unresolved",
        candidates=candidates,
    )
