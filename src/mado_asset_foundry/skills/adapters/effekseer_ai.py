from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from ...io import write_json
from .models import AdapterDefinition, AssetSkillJob, AssetSkillResult


EFFEKSEER_AI_PINNED_REF = "208922ef192220322c2a79e1243ed51ff7d2b7af"
EFFEKSEER_COMPATIBILITY_TARGET = "1.80.6"

EFFEKSEER_AI_DEFINITION = AdapterDefinition(
    adapter_id="effekseer-ai-local",
    skill_id="effekseer-ai-snapshot",
    capabilities=[
        "vfx_create",
        "vfx_runtime_export",
    ],
    execution_implemented=True,
    timeout_seconds=120,
    required_executables=["effekseer-ai", "dotnet"],
    required_env=["EFFEKSEER_AI_BIN_DIR"],
    required_env_files={
        "EFFEKSEER_AI_BIN_DIR": ["EffekseerCore.dll"],
    },
    notes=[
        "Runs a minimal local Effekseer effect lifecycle through effekseer-ai.",
        "Targets the upstream-verified Effekseer 1.80.6 Windows configuration.",
        "No Effekseer download, package installation, GUI automation, or network service is performed.",
    ],
)


Runner = Callable[
    [list[str], Path, dict[str, str], int],
    subprocess.CompletedProcess[str],
]


def _default_runner(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_nonempty(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} was not created as a non-empty file: {path}")


class EffekseerAILocalAdapter:
    definition = EFFEKSEER_AI_DEFINITION

    def __init__(
        self,
        *,
        cli_bin: str = "effekseer-ai",
        effekseer_bin_dir: str | Path,
        timeout_seconds: int | None = None,
        runner: Runner | None = None,
        platform_name: str | None = None,
    ) -> None:
        self.cli_bin = cli_bin
        self.effekseer_bin_dir = Path(effekseer_bin_dir)
        self.timeout_seconds = timeout_seconds or self.definition.timeout_seconds
        self.runner = runner or _default_runner
        self.platform_name = platform_name or platform.system()

    @classmethod
    def from_environment(cls) -> "EffekseerAILocalAdapter":
        bin_dir = os.environ.get("EFFEKSEER_AI_BIN_DIR")
        if not bin_dir:
            raise RuntimeError(
                "EFFEKSEER_AI_BIN_DIR is required for the Effekseer AI local adapter"
            )
        return cls(
            cli_bin=os.environ.get("EFFEKSEER_AI_CLI", "effekseer-ai"),
            effekseer_bin_dir=bin_dir,
        )

    def _resolve_cli(self) -> Path:
        direct = Path(self.cli_bin)
        if direct.is_file():
            return direct.resolve()
        located = shutil.which(self.cli_bin)
        if located:
            return Path(located).resolve()
        raise FileNotFoundError(f"effekseer-ai executable not found: {self.cli_bin}")

    def _validate_local_contract(self) -> dict[str, object]:
        if self.platform_name.lower() != "windows":
            raise RuntimeError(
                "Effekseer AI probe is supported only on Windows in M0.8.2h "
                f"(observed platform: {self.platform_name})"
            )
        if not self.effekseer_bin_dir.is_dir():
            raise FileNotFoundError(
                f"Effekseer Tool/bin directory not found: {self.effekseer_bin_dir}"
            )
        core_dll = self.effekseer_bin_dir / "EffekseerCore.dll"
        if not core_dll.is_file():
            raise FileNotFoundError(
                f"EffekseerCore.dll not found in Tool/bin: {core_dll}"
            )
        cli = self._resolve_cli()
        return {
            "compatibility_target": EFFEKSEER_COMPATIBILITY_TARGET,
            "platform": self.platform_name,
            "cli_path": str(cli),
            "cli_sha256": _sha256(cli),
            "core_dll_path": str(core_dll.resolve()),
            "core_dll_sha256": _sha256(core_dll),
            "core_dll_bytes": core_dll.stat().st_size,
        }

    def _invoke(
        self,
        *,
        step: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        evidence_dir: Path,
    ) -> dict[str, object]:
        step_dir = evidence_dir / "steps"
        step_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = step_dir / f"{step}.stdout.log"
        stderr_path = step_dir / f"{step}.stderr.log"
        record_path = step_dir / f"{step}.json"

        try:
            completed = self.runner(command, cwd, env, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = (
                exc.stdout.decode(errors="ignore")
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            )
            stderr = (
                exc.stderr.decode(errors="ignore")
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or "")
            )
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            write_json(
                record_path,
                {
                    "step": step,
                    "command": command,
                    "status": "timeout",
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            raise RuntimeError(
                f"effekseer-ai {step} timed out after {self.timeout_seconds} seconds"
            ) from exc

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

        parsed: object | None = None
        if stdout.strip():
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = None

        write_json(
            record_path,
            {
                "step": step,
                "command": command,
                "returncode": completed.returncode,
                "stdout_json": parsed,
            },
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"effekseer-ai {step} exited with code {completed.returncode}"
            )
        if parsed is None:
            raise RuntimeError(
                f"effekseer-ai {step} did not emit valid JSON on stdout"
            )
        if not isinstance(parsed, (dict, list)):
            raise RuntimeError(
                f"effekseer-ai {step} emitted an unexpected JSON value"
            )
        return {"stdout_json": parsed, "returncode": completed.returncode}

    def _failure_result(
        self,
        *,
        job: AssetSkillJob,
        evidence_dir: Path,
        message: str,
        executed_steps: int,
    ) -> AssetSkillResult:
        result = AssetSkillResult(
            skill_id=self.definition.skill_id,
            adapter_id=self.definition.adapter_id,
            capability=job.capability,
            status="failed",
            input_path=job.input_path,
            evidence_path=str(evidence_dir),
            message=message,
            metadata={
                "external_code_executed": executed_steps > 0,
                "executed_steps": executed_steps,
                "network_service_started": False,
            },
        )
        write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
        return result

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        if job.capability != "vfx_create":
            raise ValueError(
                "M0.8.2h live Effekseer AI adapter currently accepts only vfx_create jobs"
            )

        effect_name = str(job.options.get("effect_name", "MAF Spark Probe")).strip()
        if not effect_name or len(effect_name) > 80 or "\n" in effect_name or "\r" in effect_name:
            raise ValueError("effect_name must be 1-80 characters on one line")

        output_dir = Path(job.output_dir).resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(
                f"Effekseer effect probe output is not empty: {output_dir}"
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir = output_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        contract = self._validate_local_contract()
        cli = Path(str(contract["cli_path"]))
        source_path = output_dir / "effect.efkefc"
        runtime_path = output_dir / "effect.efk"

        env = os.environ.copy()
        env["EFFEKSEER_AI_BIN_DIR"] = str(self.effekseer_bin_dir.resolve())

        commands = {
            "new": [str(cli), "new", str(source_path)],
            "node-add": [
                str(cli),
                "node-add",
                str(source_path),
                "--name",
                effect_name,
            ],
            "export": [
                str(cli),
                "export",
                str(source_path),
                str(runtime_path),
            ],
        }

        write_json(
            evidence_dir / "job.json",
            {
                "skill_id": self.definition.skill_id,
                "adapter_id": self.definition.adapter_id,
                "capability": job.capability,
                "effect_name": effect_name,
                "output_dir": str(output_dir),
                "source_path": str(source_path),
                "runtime_path": str(runtime_path),
                "compatibility": contract,
                "effekseer_ai_upstream_ref": EFFEKSEER_AI_PINNED_REF,
                "commands": commands,
                "environment_contract": {
                    "EFFEKSEER_AI_BIN_DIR": str(self.effekseer_bin_dir.resolve()),
                },
                "external_code_execution_planned": True,
                "network_service_started": False,
            },
        )

        executed_steps = 0
        try:
            self._invoke(
                step="new",
                command=commands["new"],
                cwd=output_dir,
                env=env,
                evidence_dir=evidence_dir,
            )
            executed_steps += 1
            _require_nonempty(source_path, "Effekseer source effect")

            node = self._invoke(
                step="node-add",
                command=commands["node-add"],
                cwd=output_dir,
                env=env,
                evidence_dir=evidence_dir,
            )
            executed_steps += 1
            node_payload = node["stdout_json"]
            if not isinstance(node_payload, dict) or not str(
                node_payload.get("path", "")
            ).startswith("node/root/"):
                raise RuntimeError(
                    "effekseer-ai node-add did not return a child node path"
                )
            _require_nonempty(source_path, "Effekseer source effect")

            exported = self._invoke(
                step="export",
                command=commands["export"],
                cwd=output_dir,
                env=env,
                evidence_dir=evidence_dir,
            )
            executed_steps += 1
            export_payload = exported["stdout_json"]
            if not isinstance(export_payload, dict) or "path" not in export_payload:
                raise RuntimeError(
                    "effekseer-ai export did not return an output path"
                )
            _require_nonempty(runtime_path, "Effekseer runtime effect")
        except RuntimeError as exc:
            return self._failure_result(
                job=job,
                evidence_dir=evidence_dir,
                message=str(exc),
                executed_steps=max(executed_steps, 1),
            )

        result = AssetSkillResult(
            skill_id=self.definition.skill_id,
            adapter_id=self.definition.adapter_id,
            capability=job.capability,
            status="success",
            input_path=job.input_path,
            output_paths=[str(source_path), str(runtime_path)],
            evidence_path=str(evidence_dir),
            message="Effekseer AI local 1-effect probe completed",
            metadata={
                "external_code_executed": True,
                "executed_steps": executed_steps,
                "source_sha256": _sha256(source_path),
                "source_bytes": source_path.stat().st_size,
                "runtime_sha256": _sha256(runtime_path),
                "runtime_bytes": runtime_path.stat().st_size,
                "compatibility_target": EFFEKSEER_COMPATIBILITY_TARGET,
                "network_service_started": False,
            },
        )
        write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
        return result
