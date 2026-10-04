from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Protocol

from ...io import write_json
from ..models import SkillRegistry, SkillRegistryEntry
from ..registry import get_registry_entry
from .catalog import ADAPTER_DEFINITIONS
from .models import AdapterDefinition, PreflightCheck, SkillPreflightReport


class DependencyProbe(Protocol):
    def executable(self, name: str) -> bool:
        ...

    def python_module(self, name: str) -> bool:
        ...

    def environment(self, name: str) -> bool:
        ...

    def source_file(self, source_root: Path, relative: str) -> bool:
        ...


class SystemDependencyProbe:
    def executable(self, name: str) -> bool:
        return shutil.which(name) is not None

    def python_module(self, name: str) -> bool:
        return importlib.util.find_spec(name) is not None

    def environment(self, name: str) -> bool:
        return bool(os.environ.get(name))

    def source_file(self, source_root: Path, relative: str) -> bool:
        return (source_root / relative).is_file()


def _check(
    checks: list[PreflightCheck],
    check_id: str,
    ok: bool,
    success: str,
    failure: str,
) -> None:
    checks.append(
        PreflightCheck(
            check_id=check_id,
            status="pass" if ok else "fail",
            detail=success if ok else failure,
        )
    )


def _license_ok(entry: SkillRegistryEntry) -> bool:
    return entry.license.status == "detected" and bool(
        entry.license.spdx or entry.license.name
    )


def preflight_entry(
    entry: SkillRegistryEntry,
    *,
    definition: AdapterDefinition | None = None,
    probe: DependencyProbe | None = None,
) -> SkillPreflightReport:
    definition = definition or ADAPTER_DEFINITIONS.get(entry.skill_id)
    if definition is None:
        return SkillPreflightReport(
            skill_id=entry.skill_id,
            status="unregistered",
            checks=[
                PreflightCheck(
                    check_id="adapter_registered",
                    status="fail",
                    detail="No explicit MAF adapter definition is registered for this Skill.",
                )
            ],
        )

    checker = probe or SystemDependencyProbe()
    checks: list[PreflightCheck] = []

    _check(
        checks,
        "adapter_skill_id",
        definition.skill_id == entry.skill_id,
        "Adapter definition targets this Skill.",
        f"Adapter targets {definition.skill_id}, not {entry.skill_id}.",
    )

    missing_capabilities = sorted(
        set(definition.capabilities) - set(entry.capabilities)
    )
    _check(
        checks,
        "capability_contract",
        not missing_capabilities,
        "Adapter capabilities are declared by the scanned Skill manifest.",
        "Adapter declares capabilities absent from the Skill manifest: "
        + ", ".join(missing_capabilities),
    )

    _check(
        checks,
        "license_metadata",
        _license_ok(entry),
        f"License metadata detected: {entry.license.spdx or entry.license.name}.",
        "License is unknown/ambiguous or has no normalized identifier/name.",
    )

    source_root = Path(entry.source.path)
    _check(
        checks,
        "source_root",
        source_root.is_dir(),
        f"Skill source directory exists: {source_root}.",
        f"Skill source directory is missing: {source_root}.",
    )

    for executable in definition.required_executables:
        _check(
            checks,
            f"executable:{executable}",
            checker.executable(executable),
            f"Executable found: {executable}.",
            f"Required executable not found: {executable}.",
        )

    for module in definition.required_python_modules:
        _check(
            checks,
            f"python_module:{module}",
            checker.python_module(module),
            f"Python module is discoverable: {module}.",
            f"Required Python module is not discoverable: {module}.",
        )

    for name in definition.required_env:
        _check(
            checks,
            f"env:{name}",
            checker.environment(name),
            f"Required environment variable is present: {name}.",
            f"Required environment variable is missing: {name}.",
        )

    for relative in definition.required_source_files:
        _check(
            checks,
            f"source_file:{relative}",
            checker.source_file(source_root, relative),
            f"Required source file exists: {relative}.",
            f"Required source file is missing: {relative}.",
        )

    contract_failed = any(check.status == "fail" for check in checks)
    if contract_failed:
        status = "blocked"
    elif not definition.execution_implemented:
        status = "contract_only"
        checks.append(
            PreflightCheck(
                check_id="execution_implemented",
                status="warn",
                detail="Adapter execution is not implemented yet; promotion is not allowed.",
            )
        )
    else:
        status = "ready"
        checks.append(
            PreflightCheck(
                check_id="execution_implemented",
                status="pass",
                detail="Adapter execution is implemented.",
            )
        )

    return SkillPreflightReport(
        skill_id=entry.skill_id,
        adapter_id=definition.adapter_id,
        status=status,
        execution_implemented=definition.execution_implemented,
        promotion_eligible=status == "ready",
        checks=checks,
    )


def preflight_skill(
    registry: SkillRegistry,
    skill_id: str,
    *,
    evidence_dir: str | Path = "evidence/skill-preflight",
    force: bool = False,
    definition: AdapterDefinition | None = None,
    probe: DependencyProbe | None = None,
) -> tuple[SkillPreflightReport, Path]:
    try:
        entry = get_registry_entry(registry, skill_id)
    except KeyError as exc:
        raise ValueError(f"Skill not found in registry: {skill_id}") from exc

    report = preflight_entry(entry, definition=definition, probe=probe)
    report_path = Path(evidence_dir) / skill_id / "report.json"
    if report_path.exists() and not force:
        raise FileExistsError(
            f"Skill preflight evidence already exists: {report_path}; use --force to replace it"
        )
    write_json(report_path, report.model_dump(mode="json"))
    return report, report_path
