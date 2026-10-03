from __future__ import annotations

import json
import re
from pathlib import Path

from ..io import write_json
from .models import SkillEntrypoints, SkillIntakeReport, SkillLicense, SkillManifest, SkillSource


_README_NAMES = ("README.md", "README.txt", "README")
_LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
_METADATA_NAMES = ("pyproject.toml", "requirements.txt", "package.json", "environment.yml", "Dockerfile")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("could not derive a valid skill_id from source directory")
    return slug


def _first_existing(source: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = source / name
        if candidate.is_file():
            return candidate
    lower_names = {name.lower() for name in names}
    for candidate in sorted(source.iterdir(), key=lambda path: path.name.lower()):
        if candidate.is_file() and candidate.name.lower() in lower_names:
            return candidate
    return None


def _display_name(source: Path, skill_md: Path | None, readme: Path | None) -> str:
    for document in (skill_md, readme):
        if document is None:
            continue
        try:
            for raw_line in document.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    if title:
                        return title
        except UnicodeDecodeError:
            continue
    return source.name.replace("-", " ").replace("_", " ").strip().title() or source.name


def _relative(path: Path, source: Path) -> str:
    return path.relative_to(source).as_posix()


def _discover_scripts(source: Path) -> list[str]:
    scripts_dir = source / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [
        _relative(path, source)
        for path in sorted(scripts_dir.rglob("*"))
        if path.is_file()
    ]


def inspect_skill(source_path: str | Path) -> tuple[SkillManifest, list[str]]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Skill source not found: {source}")
    if not source.is_dir():
        raise ValueError(f"Skill source must be a directory: {source}")

    skill_md = _first_existing(source, ("SKILL.md",))
    readme = _first_existing(source, _README_NAMES)
    license_file = _first_existing(source, _LICENSE_NAMES)
    metadata_files = [
        name for name in _METADATA_NAMES if (source / name).is_file()
    ]
    scripts = _discover_scripts(source)

    discovered: list[str] = []
    for candidate in (skill_md, readme, license_file):
        if candidate is not None:
            discovered.append(_relative(candidate, source))
    discovered.extend(metadata_files)
    discovered.extend(scripts)
    discovered = sorted(set(discovered))

    source_type = "local_repository" if (source / ".git").exists() else "local_directory"
    manifest = SkillManifest(
        skill_id=_slugify(source.name),
        name=_display_name(source, skill_md, readme),
        source=SkillSource(type=source_type, path=str(source)),
        license=SkillLicense(
            source_file=_relative(license_file, source) if license_file else None,
            status="detected" if license_file else "unknown",
        ),
        entrypoints=SkillEntrypoints(
            skill_md=_relative(skill_md, source) if skill_md else None,
            readme=_relative(readme, source) if readme else None,
            scripts=scripts,
            metadata_files=metadata_files,
        ),
        capabilities=[],
        runtime=[],
        inputs=[],
        outputs=[],
        adapter_status="intake_only",
        notes=[
            "M0.8.2a structural intake only.",
            "Capability classification is intentionally deferred to M0.8.2b.",
            "No external code was executed during intake.",
        ],
    )
    return manifest, discovered


def intake_skill(
    source_path: str | Path,
    *,
    manifest_dir: str | Path = "skills/manifests",
    evidence_dir: str | Path = "evidence/skill-intake",
    force: bool = False,
) -> tuple[SkillManifest, Path, Path]:
    manifest, discovered = inspect_skill(source_path)

    manifest_path = Path(manifest_dir) / f"{manifest.skill_id}.json"
    report_path = Path(evidence_dir) / manifest.skill_id / "report.json"

    for target in (manifest_path, report_path):
        if target.exists() and not force:
            raise FileExistsError(f"Skill intake output already exists: {target}; use --force to replace it")

    write_json(manifest_path, manifest.model_dump(mode="json"))
    report = SkillIntakeReport(
        skill_id=manifest.skill_id,
        source_path=str(source_path),
        manifest_path=str(manifest_path),
        discovered_files=discovered,
    )
    write_json(report_path, report.model_dump(mode="json"))
    return manifest, manifest_path, report_path


def load_skill_manifest(path: str | Path) -> SkillManifest:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Skill manifest not found: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return SkillManifest.model_validate(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not parse Skill manifest: {source}") from exc
