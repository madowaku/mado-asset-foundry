from pathlib import Path

from mado_asset_foundry.skills.adapters.models import AdapterDefinition
from mado_asset_foundry.skills.adapters.preflight import preflight_entry, preflight_skill
from mado_asset_foundry.skills.models import SkillLicense, SkillRegistry, SkillRegistryEntry, SkillSource


class FakeProbe:
    def __init__(
        self,
        *,
        executables: set[str] | None = None,
        modules: set[str] | None = None,
        env: set[str] | None = None,
        files: set[str] | None = None,
    ) -> None:
        self.executables = executables or set()
        self.modules = modules or set()
        self.env = env or set()
        self.files = files or set()

    def executable(self, name: str) -> bool:
        return name in self.executables

    def python_module(self, name: str) -> bool:
        return name in self.modules

    def environment(self, name: str) -> bool:
        return name in self.env

    def source_file(self, source_root: Path, relative: str) -> bool:
        return relative in self.files


def entry(tmp_path: Path) -> SkillRegistryEntry:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return SkillRegistryEntry(
        skill_id="sample-adapter",
        name="Sample Adapter",
        manifest_path=str(tmp_path / "sample.json"),
        source=SkillSource(type="local_directory", path=str(source)),
        license=SkillLicense(spdx="MIT", source_file="LICENSE", status="detected"),
        capabilities=["background_remove", "alpha_cleanup"],
        runtime=["python"],
        adapter_status="intake_only",
    )


def definition(*, implemented: bool) -> AdapterDefinition:
    return AdapterDefinition(
        adapter_id="sample-local",
        skill_id="sample-adapter",
        capabilities=["background_remove"],
        execution_implemented=implemented,
        required_executables=["python"],
        required_python_modules=["sample_module"],
        required_env=["SAMPLE_TOKEN"],
        required_source_files=["run.py"],
    )


def test_preflight_ready_requires_implemented_execution_and_all_checks(tmp_path: Path) -> None:
    report = preflight_entry(
        entry(tmp_path),
        definition=definition(implemented=True),
        probe=FakeProbe(
            executables={"python"},
            modules={"sample_module"},
            env={"SAMPLE_TOKEN"},
            files={"run.py"},
        ),
    )

    assert report.status == "ready"
    assert report.promotion_eligible is True
    assert report.external_code_executed is False
    assert all(check.status == "pass" for check in report.checks)


def test_preflight_contract_only_never_promotes(tmp_path: Path) -> None:
    report = preflight_entry(
        entry(tmp_path),
        definition=definition(implemented=False),
        probe=FakeProbe(
            executables={"python"},
            modules={"sample_module"},
            env={"SAMPLE_TOKEN"},
            files={"run.py"},
        ),
    )

    assert report.status == "contract_only"
    assert report.promotion_eligible is False
    assert any(
        check.check_id == "execution_implemented" and check.status == "warn"
        for check in report.checks
    )


def test_preflight_blocks_missing_dependencies(tmp_path: Path) -> None:
    report = preflight_entry(
        entry(tmp_path),
        definition=definition(implemented=True),
        probe=FakeProbe(executables={"python"}),
    )

    assert report.status == "blocked"
    assert report.promotion_eligible is False
    failed = {check.check_id for check in report.checks if check.status == "fail"}
    assert {
        "python_module:sample_module",
        "env:SAMPLE_TOKEN",
        "source_file:run.py",
    } <= failed


def test_preflight_blocks_capability_mismatch(tmp_path: Path) -> None:
    bad = definition(implemented=True)
    bad.capabilities = ["image_to_mesh"]

    report = preflight_entry(
        entry(tmp_path),
        definition=bad,
        probe=FakeProbe(
            executables={"python"},
            modules={"sample_module"},
            env={"SAMPLE_TOKEN"},
            files={"run.py"},
        ),
    )

    assert report.status == "blocked"
    assert any(
        check.check_id == "capability_contract" and check.status == "fail"
        for check in report.checks
    )


def test_preflight_blocks_unknown_license(tmp_path: Path) -> None:
    candidate = entry(tmp_path)
    candidate.license = SkillLicense(status="unknown")

    report = preflight_entry(
        candidate,
        definition=definition(implemented=True),
        probe=FakeProbe(
            executables={"python"},
            modules={"sample_module"},
            env={"SAMPLE_TOKEN"},
            files={"run.py"},
        ),
    )

    assert report.status == "blocked"
    assert any(
        check.check_id == "license_metadata" and check.status == "fail"
        for check in report.checks
    )


def test_preflight_unregistered_skill_is_not_executable(tmp_path: Path) -> None:
    report = preflight_entry(entry(tmp_path), definition=None, probe=FakeProbe())
    assert report.status == "unregistered"
    assert report.promotion_eligible is False


def test_preflight_writes_evidence_without_execution(tmp_path: Path) -> None:
    candidate = entry(tmp_path)
    registry = SkillRegistry(entries=[candidate])
    report, report_path = preflight_skill(
        registry,
        candidate.skill_id,
        evidence_dir=tmp_path / "evidence",
        definition=definition(implemented=False),
        probe=FakeProbe(
            executables={"python"},
            modules={"sample_module"},
            env={"SAMPLE_TOKEN"},
            files={"run.py"},
        ),
    )

    assert report_path.exists()
    assert report.external_code_executed is False
