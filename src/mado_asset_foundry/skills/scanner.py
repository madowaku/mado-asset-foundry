from __future__ import annotations

from pathlib import Path

from ..io import write_json
from .intake import inspect_skill
from .models import (
    CapabilityEvidence,
    LicenseEvidence,
    RuntimeEvidence,
    SkillLicense,
    SkillManifest,
    SkillScanReport,
)
from .taxonomy import CAPABILITY_IO, CAPABILITY_TERMS


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


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > _TEXT_LIMIT:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _document_paths(source: Path, manifest: SkillManifest) -> list[Path]:
    paths: list[Path] = []
    for relative in (manifest.entrypoints.skill_md, manifest.entrypoints.readme):
        if relative:
            path = source / relative
            if path.is_file():
                paths.append(path)
    return paths


def _scan_capabilities(
    source: Path,
    manifest: SkillManifest,
) -> tuple[list[str], list[CapabilityEvidence]]:
    matches: dict[str, list[CapabilityEvidence]] = {}

    for document in _document_paths(source, manifest):
        text = _read_text(document).lower()
        relative = document.relative_to(source).as_posix()
        for capability, terms in CAPABILITY_TERMS.items():
            matched = sorted({term for term in terms if term in text})
            if matched:
                matches.setdefault(capability, []).append(
                    CapabilityEvidence(
                        capability=capability,
                        confidence="high",
                        source_file=relative,
                        matched_terms=matched,
                    )
                )

    capabilities = [capability for capability in CAPABILITY_TERMS if capability in matches]
    evidence = [
        item
        for capability in capabilities
        for item in matches[capability]
    ]
    return capabilities, evidence


def _scan_runtime(
    source: Path,
    manifest: SkillManifest,
) -> tuple[list[str], list[RuntimeEvidence]]:
    evidence: list[RuntimeEvidence] = []
    seen: set[tuple[str, str, str]] = set()

    def add(runtime: str, source_file: str, reason: str) -> None:
        key = (runtime, source_file, reason)
        if key in seen:
            return
        seen.add(key)
        evidence.append(RuntimeEvidence(runtime=runtime, source_file=source_file, reason=reason))

    metadata = set(manifest.entrypoints.metadata_files)
    if {"pyproject.toml", "requirements.txt", "environment.yml"} & metadata:
        source_file = next(
            name for name in ("pyproject.toml", "requirements.txt", "environment.yml")
            if name in metadata
        )
        add("python", source_file, "Python dependency metadata detected")

    if "package.json" in metadata:
        add("node", "package.json", "Node package metadata detected")

    for relative in manifest.entrypoints.scripts:
        suffix = Path(relative).suffix.lower()
        if suffix == ".py":
            add("python", relative, "Python script detected")
        elif suffix in {".js", ".mjs", ".cjs", ".ts"}:
            add("node", relative, "Node/TypeScript script detected")

    searchable: list[tuple[str, str]] = []
    for document in _document_paths(source, manifest):
        searchable.append((document.relative_to(source).as_posix(), _read_text(document).lower()))
    for relative in manifest.entrypoints.metadata_files:
        path = source / relative
        if path.is_file():
            searchable.append((relative, _read_text(path).lower()))

    for source_file, text in searchable:
        if "ffmpeg" in text:
            add("ffmpeg", source_file, "ffmpeg reference detected")
        if "onnxruntime" in text or "onnx runtime" in text:
            add("onnx_runtime", source_file, "ONNX Runtime reference detected")

    for path in source.rglob("*.onnx"):
        if path.is_file():
            add("onnx_runtime", path.relative_to(source).as_posix(), "ONNX model file detected")

    runtimes: list[str] = []
    for item in evidence:
        if item.runtime not in runtimes:
            runtimes.append(item.runtime)
    return runtimes, evidence


def _scan_license(source: Path, manifest: SkillManifest) -> tuple[SkillLicense, LicenseEvidence]:
    source_file = manifest.license.source_file
    if not source_file:
        return SkillLicense(status="unknown"), LicenseEvidence()

    path = source / source_file
    text = _read_text(path).lower()
    if "stability ai community license agreement" in text:
        return (
            SkillLicense(
                name="Stability AI Community License",
                source_file=source_file,
                status="detected",
            ),
            LicenseEvidence(
                source_file=source_file,
                matched_identifiers=["Stability AI Community License"],
            ),
        )

    matched: list[str] = []
    for spdx, patterns in _LICENSE_PATTERNS.items():
        if all(pattern in text for pattern in patterns):
            matched.append(spdx)

    if len(matched) == 1:
        return (
            SkillLicense(spdx=matched[0], source_file=source_file, status="detected"),
            LicenseEvidence(source_file=source_file, matched_identifiers=matched),
        )
    if len(matched) > 1:
        return (
            SkillLicense(spdx=None, source_file=source_file, status="ambiguous"),
            LicenseEvidence(source_file=source_file, matched_identifiers=matched),
        )
    return (
        SkillLicense(spdx=None, source_file=source_file, status="unknown"),
        LicenseEvidence(source_file=source_file, matched_identifiers=[]),
    )


def _derive_io(capabilities: list[str]) -> tuple[list[str], list[str]]:
    inputs: list[str] = []
    outputs: list[str] = []
    for capability in capabilities:
        profile = CAPABILITY_IO.get(capability)
        if not profile:
            continue
        for value in profile[0]:
            if value not in inputs:
                inputs.append(value)
        for value in profile[1]:
            if value not in outputs:
                outputs.append(value)
    return inputs, outputs


def scan_skill(
    source_path: str | Path,
    *,
    manifest_dir: str | Path = "skills/manifests",
    evidence_dir: str | Path = "evidence/skill-scan",
    force: bool = False,
) -> tuple[SkillManifest, Path, Path]:
    manifest, _ = inspect_skill(source_path)
    source = Path(source_path)

    capabilities, capability_evidence = _scan_capabilities(source, manifest)
    runtime, runtime_evidence = _scan_runtime(source, manifest)
    license_info, license_evidence = _scan_license(source, manifest)
    inputs, outputs = _derive_io(capabilities)

    manifest.capabilities = capabilities
    manifest.runtime = runtime
    manifest.inputs = inputs
    manifest.outputs = outputs
    manifest.license = license_info
    manifest.notes = [
        "M0.8.2b deterministic capability scan completed.",
        "Capabilities are inferred only from explicit terms in SKILL.md/README.",
        "Runtime discovery uses metadata, script extensions, and explicit tool references.",
        "No external code was executed during scanning.",
    ]

    manifest_path = Path(manifest_dir) / f"{manifest.skill_id}.json"
    report_path = Path(evidence_dir) / manifest.skill_id / "report.json"
    for target in (manifest_path, report_path):
        if target.exists() and not force:
            raise FileExistsError(
                f"Skill scan output already exists: {target}; use --force to replace it"
            )

    write_json(manifest_path, manifest.model_dump(mode="json"))
    report = SkillScanReport(
        skill_id=manifest.skill_id,
        source_path=str(source_path),
        manifest_path=str(manifest_path),
        documents_scanned=[
            path.relative_to(source).as_posix()
            for path in _document_paths(source, manifest)
        ],
        capability_evidence=capability_evidence,
        runtime_evidence=runtime_evidence,
        license_evidence=license_evidence,
    )
    write_json(report_path, report.model_dump(mode="json"))
    return manifest, manifest_path, report_path
