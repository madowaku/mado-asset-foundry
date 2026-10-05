from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ...io import write_json


class CraftingAppSpec(BaseModel):
    app_id: str
    display_name: str
    cli_executable: str
    desktop_executable: str
    upstream_url: str
    upstream_ref: str
    license: str = "MIT OR Apache-2.0"
    maturity: str
    maf_capabilities: list[str] = Field(default_factory=list)
    agent_interfaces: list[str] = Field(default_factory=list)
    probe_args: list[str] = Field(default_factory=lambda: ["--help"])
    mcp_args: list[str] = Field(default_factory=lambda: ["mcp"])
    mcp_transport: Literal["stdio"] = "stdio"
    notes: list[str] = Field(default_factory=list)


class CraftingAppsIntakeReport(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    probe_id: str = "crafting-apps-agent-native"
    apps: list[CraftingAppSpec] = Field(default_factory=list)
    external_code_executed: bool = False
    mcp_servers_started: bool = False


class CraftingAppProbeResult(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    app_id: str
    display_name: str
    status: Literal["success", "failed"]
    executable_path: str
    executable_sha256: str
    upstream_url: str
    upstream_ref: str
    probe_command: list[str] = Field(default_factory=list)
    returncode: int
    stdout_path: str
    stderr_path: str
    mcp_descriptor_path: str | None = None
    external_code_executed: bool = True
    mcp_server_started: bool = False
    network_service_started: bool = False
    message: str


# Immutable upstream refs captured for the MAF-M0.8.3 intake on 2026-10-05.
# They are evidence pins, not an instruction to clone or execute upstream source.
CRAFTING_APP_SPECS: dict[str, CraftingAppSpec] = {
    "photocraft": CraftingAppSpec(
        app_id="photocraft",
        display_name="PhotoCraft",
        cli_executable="photocraft-cli",
        desktop_executable="photocraft",
        upstream_url="https://github.com/storytold/photocraft",
        upstream_ref="ff53be714db50b8b190381eb0a9ec2b1ffab6715",
        maturity="early_alpha",
        maf_capabilities=["image_edit"],
        agent_interfaces=["headless_cli", "json_control", "mcp_stdio"],
        notes=[
            "Official README documents headless run/batch workflows and 'photocraft-cli mcp'.",
            "M0.8.3 probes only the CLI executable; it does not start the MCP server.",
        ],
    ),
    "vectorcraft": CraftingAppSpec(
        app_id="vectorcraft",
        display_name="VectorCraft",
        cli_executable="vectorcraft-cli",
        desktop_executable="vectorcraft",
        upstream_url="https://github.com/storytold/vectorcraft",
        upstream_ref="4b956422c9f0ddec90d3a345d78e17432ddc1826",
        maturity="in_development",
        maf_capabilities=["image_edit"],
        agent_interfaces=["headless_cli", "json_control", "mcp_stdio"],
        notes=[
            "Official README documents headless run/export workflows and 'vectorcraft-cli mcp'.",
            "Vector-specific MAF capability taxonomy is intentionally deferred to a later milestone.",
        ],
    ),
    "effectcraft": CraftingAppSpec(
        app_id="effectcraft",
        display_name="EffectCraft",
        cli_executable="effectcraft-cli",
        desktop_executable="effectcraft",
        upstream_url="https://github.com/storytold/effectcraft",
        upstream_ref="c90fd35ff894e7c0854cd0ec12b79d9d38d98ee9",
        maturity="young_active_development",
        maf_capabilities=["vfx_create", "vfx_edit"],
        agent_interfaces=["headless_cli", "json_control", "mcp_stdio"],
        notes=[
            "Official README documents command/render workflows and 'effectcraft-cli mcp'.",
            "M0.8.3 does not bridge to a running GUI and does not start a network listener.",
        ],
    ),
}


ProbeRunner = Callable[
    [list[str], Path, int],
    subprocess.CompletedProcess[str],
]


def _default_runner(
    command: list[str],
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
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


def get_crafting_app_spec(app_id: str) -> CraftingAppSpec:
    try:
        return CRAFTING_APP_SPECS[app_id]
    except KeyError as exc:
        known = ", ".join(sorted(CRAFTING_APP_SPECS))
        raise ValueError(
            f"Unknown Crafting App: {app_id}. Expected one of: {known}"
        ) from exc


def write_crafting_apps_intake(
    *,
    output_path: str | Path = "evidence/crafting-apps-intake/report.json",
    force: bool = False,
) -> tuple[CraftingAppsIntakeReport, Path]:
    target = Path(output_path)
    if target.exists() and not force:
        raise FileExistsError(
            f"Crafting Apps intake evidence already exists: {target}; use --force to replace it"
        )

    report = CraftingAppsIntakeReport(
        apps=[
            CRAFTING_APP_SPECS[app_id]
            for app_id in sorted(CRAFTING_APP_SPECS)
        ],
    )
    write_json(target, report.model_dump(mode="json"))
    return report, target


class CraftingAppMcpAdapter:
    """Safe local intake adapter for agent-native Crafting Apps.

    M0.8.3 deliberately stops before the long-lived MCP handshake. It proves
    that an explicitly selected local CLI can start and answer --help, hashes
    that executable, and materializes the stdio MCP launch descriptor that a
    later milestone can hand to a real MCP client.
    """

    def __init__(
        self,
        app_id: str,
        *,
        cli_bin: str | None = None,
        timeout_seconds: int = 15,
        runner: ProbeRunner | None = None,
    ) -> None:
        self.spec = get_crafting_app_spec(app_id)
        self.cli_bin = cli_bin or self.spec.cli_executable
        self.timeout_seconds = timeout_seconds
        self.runner = runner or _default_runner

    def _resolve_cli(self) -> Path:
        direct = Path(self.cli_bin)
        if direct.is_file():
            return direct.resolve()
        located = shutil.which(self.cli_bin)
        if located:
            return Path(located).resolve()
        raise FileNotFoundError(
            f"{self.spec.display_name} CLI executable not found: {self.cli_bin}"
        )

    def probe(self, output_dir: str | Path) -> CraftingAppProbeResult:
        target = Path(output_dir).resolve()
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(
                f"Crafting App probe output is not empty: {target}"
            )
        target.mkdir(parents=True, exist_ok=True)
        evidence_dir = target / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        cli = self._resolve_cli()
        command = [str(cli), *self.spec.probe_args]
        stdout_path = evidence_dir / "probe.stdout.log"
        stderr_path = evidence_dir / "probe.stderr.log"

        write_json(
            evidence_dir / "job.json",
            {
                "schema_version": "0.1",
                "app": self.spec.model_dump(mode="json"),
                "resolved_executable": str(cli),
                "executable_sha256": _sha256(cli),
                "probe_command": command,
                "planned_mcp": {
                    "transport": self.spec.mcp_transport,
                    "command": str(cli),
                    "args": self.spec.mcp_args,
                },
                "external_code_execution_planned": True,
                "mcp_server_start_planned": False,
                "network_service_start_planned": False,
            },
        )

        try:
            completed = self.runner(command, target, self.timeout_seconds)
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
            result = CraftingAppProbeResult(
                app_id=self.spec.app_id,
                display_name=self.spec.display_name,
                status="failed",
                executable_path=str(cli),
                executable_sha256=_sha256(cli),
                upstream_url=self.spec.upstream_url,
                upstream_ref=self.spec.upstream_ref,
                probe_command=command,
                returncode=-1,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                message=(
                    f"{self.spec.display_name} CLI probe timed out after "
                    f"{self.timeout_seconds} seconds"
                ),
            )
            write_json(
                evidence_dir / "result.json",
                result.model_dump(mode="json"),
            )
            return result

        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")

        descriptor_path: Path | None = None
        if completed.returncode == 0:
            descriptor_path = evidence_dir / "mcp-server.json"
            write_json(
                descriptor_path,
                {
                    "schema_version": "0.1",
                    "server_id": f"crafting-apps.{self.spec.app_id}",
                    "transport": self.spec.mcp_transport,
                    "command": str(cli),
                    "args": self.spec.mcp_args,
                    "executable_sha256": _sha256(cli),
                    "upstream_url": self.spec.upstream_url,
                    "upstream_ref": self.spec.upstream_ref,
                    "verified_by": {
                        "kind": "cli_help_probe",
                        "command": command,
                        "returncode": completed.returncode,
                    },
                    "server_started": False,
                },
            )

        status: Literal["success", "failed"] = (
            "success" if completed.returncode == 0 else "failed"
        )
        message = (
            f"{self.spec.display_name} CLI probe completed; MCP descriptor materialized"
            if status == "success"
            else (
                f"{self.spec.display_name} CLI probe exited with code "
                f"{completed.returncode}; MCP descriptor was not materialized"
            )
        )
        result = CraftingAppProbeResult(
            app_id=self.spec.app_id,
            display_name=self.spec.display_name,
            status=status,
            executable_path=str(cli),
            executable_sha256=_sha256(cli),
            upstream_url=self.spec.upstream_url,
            upstream_ref=self.spec.upstream_ref,
            probe_command=command,
            returncode=completed.returncode,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            mcp_descriptor_path=(
                str(descriptor_path) if descriptor_path is not None else None
            ),
            message=message,
        )
        write_json(
            evidence_dir / "result.json",
            result.model_dump(mode="json"),
        )
        return result
