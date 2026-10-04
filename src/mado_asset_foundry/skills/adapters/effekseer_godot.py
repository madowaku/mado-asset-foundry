from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from ...io import write_json
from .models import AdapterDefinition, AssetSkillJob, AssetSkillResult


EFFEKSEER_GODOT_VERSION = "1.80.7"
EFFEKSEER_GODOT_PINNED_REF = "8706d2917c2487efac3a4943c16a10dfcfc5b127"
EFFEKSEER_GODOT_RELEASE_ASSET = "EffekseerForGodot4-180_7.zip"
EFFEKSEER_GODOT_RELEASE_SHA256 = (
    "581e02b4ad773df39674c6c5d57bc6c132adf6fe38ae60a75bf230f251d56fef"
)
EFFEKSEER_AUTHORING_VERSION = "1.80.6"

EFFEKSEER_GODOT_DEFINITION = AdapterDefinition(
    adapter_id="effekseer-godot4-local",
    skill_id="effekseer-godot4-snapshot",
    capabilities=["vfx_runtime_playback", "godot_vfx_playback"],
    execution_implemented=True,
    timeout_seconds=180,
    required_env=["EFFEKSEER_GODOT_PLUGIN_ARCHIVE", "GODOT_BIN"],
    notes=[
        "Uses the official EffekseerForGodot4 1.80.7 release archive.",
        "Godot imports .efkefc through the official importer and verifies runtime playback with EffekseerEmitter3D.is_playing().",
        "The source effect is authored/exported by the M0.8.2h Effekseer 1.80.6 pipeline; the 1.80.6 -> 1.80.7 version delta is explicit evidence.",
        "No plugin, Godot binary, or dependency is downloaded or installed automatically.",
    ],
)


Runner = Callable[
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


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def _resolve_binary(value: str) -> Path:
    direct = Path(value)
    if direct.is_file():
        return direct.resolve()
    located = shutil.which(value)
    if located:
        return Path(located).resolve()
    raise FileNotFoundError(f"Godot executable not found: {value}")


def _safe_zip_parts(name: str) -> tuple[str, ...]:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    parts = pure.parts
    if (
        pure.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
    ):
        raise ValueError(f"Unsafe plugin archive member: {name}")
    return parts


def _extract_verified_addon(
    archive: Path,
    destination: Path,
    *,
    expected_sha256: str,
) -> dict[str, object]:
    if not archive.is_file():
        raise FileNotFoundError(f"EffekseerForGodot4 archive not found: {archive}")
    observed_sha256 = _sha256(archive)
    if observed_sha256.lower() != expected_sha256.lower():
        raise ValueError(
            "EffekseerForGodot4 archive SHA-256 mismatch: "
            f"expected {expected_sha256}, observed {observed_sha256}"
        )

    with zipfile.ZipFile(archive) as bundle:
        names = [info.filename for info in bundle.infolist() if not info.is_dir()]
        for name in names:
            _safe_zip_parts(name)

        plugin_candidates = [
            name
            for name in names
            if name.replace("\\", "/").endswith("addons/effekseer/plugin.cfg")
        ]
        if len(plugin_candidates) != 1:
            raise ValueError(
                "Official plugin archive must contain exactly one addons/effekseer/plugin.cfg"
            )

        plugin_member = plugin_candidates[0].replace("\\", "/")
        addon_prefix = plugin_member[: -len("plugin.cfg")]
        destination.mkdir(parents=True, exist_ok=True)

        extracted = 0
        for info in bundle.infolist():
            normalized = info.filename.replace("\\", "/")
            if info.is_dir() or not normalized.startswith(addon_prefix):
                continue
            relative = normalized[len(addon_prefix) :]
            if not relative:
                continue
            relative_parts = _safe_zip_parts(relative)
            target = destination.joinpath(*relative_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted += 1

    plugin_cfg = destination / "plugin.cfg"
    gdextension = destination / "effekseer.gdextension"
    windows_dll = destination / "bin" / "windows" / "libeffekseer.x86_64.dll"
    for required in (plugin_cfg, gdextension, windows_dll):
        if not required.is_file() or required.stat().st_size <= 0:
            raise ValueError(f"EffekseerForGodot4 release is missing required file: {required}")

    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        plugin_cfg.read_text(encoding="utf-8", errors="ignore"),
        flags=re.MULTILINE,
    )
    version = match.group(1) if match else None
    if version != EFFEKSEER_GODOT_VERSION:
        raise ValueError(
            f"Unexpected EffekseerForGodot4 plugin version: {version or 'unknown'}"
        )

    return {
        "release_asset": archive.name,
        "release_sha256": observed_sha256,
        "release_version": version,
        "pinned_ref": EFFEKSEER_GODOT_PINNED_REF,
        "extracted_files": extracted,
        "plugin_cfg_sha256": _sha256(plugin_cfg),
        "gdextension_sha256": _sha256(gdextension),
        "windows_x86_64_dll_sha256": _sha256(windows_dll),
        "windows_x86_64_dll_bytes": windows_dll.stat().st_size,
    }


def _load_source_probe(effect_run: Path) -> dict[str, object]:
    source = effect_run / "effect.efkefc"
    runtime = effect_run / "effect.efk"
    result_path = effect_run / "evidence" / "result.json"
    for path in (source, runtime, result_path):
        if not path.is_file():
            raise FileNotFoundError(f"M0.8.2h effect probe artifact missing: {path}")
    if source.stat().st_size <= 0 or runtime.stat().st_size <= 0:
        raise ValueError("M0.8.2h effect outputs must be non-empty")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "success":
        raise ValueError("M0.8.2h effect probe did not finish successfully")
    if result.get("adapter_id") != "effekseer-ai-local":
        raise ValueError("Effect run was not produced by effekseer-ai-local")

    metadata = result.get("metadata") or {}
    source_sha = _sha256(source)
    runtime_sha = _sha256(runtime)
    if metadata.get("source_sha256") != source_sha:
        raise ValueError("effect.efkefc SHA-256 does not match M0.8.2h evidence")
    if metadata.get("runtime_sha256") != runtime_sha:
        raise ValueError("effect.efk SHA-256 does not match M0.8.2h evidence")

    return {
        "source_path": source,
        "runtime_path": runtime,
        "source_sha256": source_sha,
        "source_bytes": source.stat().st_size,
        "runtime_sha256": runtime_sha,
        "runtime_bytes": runtime.stat().st_size,
        "source_evidence": result_path,
    }


def _parse_godot_version(text: str) -> tuple[int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


class EffekseerGodotLocalAdapter:
    definition = EFFEKSEER_GODOT_DEFINITION

    def __init__(
        self,
        *,
        plugin_archive: str | Path,
        godot_bin: str = "godot",
        timeout_seconds: int | None = None,
        runner: Runner | None = None,
        platform_name: str | None = None,
        expected_archive_sha256: str = EFFEKSEER_GODOT_RELEASE_SHA256,
    ) -> None:
        self.plugin_archive = Path(plugin_archive)
        self.godot_bin = godot_bin
        self.timeout_seconds = timeout_seconds or self.definition.timeout_seconds
        self.runner = runner or _default_runner
        self.platform_name = platform_name or platform.system()
        self.expected_archive_sha256 = expected_archive_sha256

    @classmethod
    def from_environment(cls) -> "EffekseerGodotLocalAdapter":
        archive = os.environ.get("EFFEKSEER_GODOT_PLUGIN_ARCHIVE")
        godot = os.environ.get("GODOT_BIN")
        if not archive or not godot:
            raise RuntimeError(
                "EFFEKSEER_GODOT_PLUGIN_ARCHIVE and GODOT_BIN are required "
                "for the Effekseer Godot adapter"
            )
        return cls(plugin_archive=archive, godot_bin=godot)

    def _invoke(
        self,
        *,
        step: str,
        command: list[str],
        cwd: Path,
        evidence_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        logs = evidence_dir / "steps"
        logs.mkdir(parents=True, exist_ok=True)
        stdout_path = logs / f"{step}.stdout.log"
        stderr_path = logs / f"{step}.stderr.log"
        record_path = logs / f"{step}.json"

        try:
            completed = self.runner(command, cwd, self.timeout_seconds)
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
            _write_text(stdout_path, stdout)
            _write_text(stderr_path, stderr)
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
                f"Godot {step} timed out after {self.timeout_seconds} seconds"
            ) from exc

        _write_text(stdout_path, completed.stdout or "")
        _write_text(stderr_path, completed.stderr or "")
        write_json(
            record_path,
            {
                "step": step,
                "command": command,
                "returncode": completed.returncode,
            },
        )
        return completed

    def _failure(
        self,
        *,
        job: AssetSkillJob,
        evidence_dir: Path,
        message: str,
        external_code_executed: bool,
        metadata: dict[str, object] | None = None,
    ) -> AssetSkillResult:
        details = {
            "external_code_executed": external_code_executed,
            "network_service_started": False,
            "visual_quality_approved": False,
        }
        if metadata:
            details.update(metadata)
        result = AssetSkillResult(
            skill_id=self.definition.skill_id,
            adapter_id=self.definition.adapter_id,
            capability=job.capability,
            status="failed",
            input_path=job.input_path,
            evidence_path=str(evidence_dir),
            message=message,
            metadata=details,
        )
        write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
        return result

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        if job.capability != "godot_vfx_playback":
            raise ValueError(
                "M0.8.2i Effekseer Godot adapter accepts only godot_vfx_playback jobs"
            )
        if self.platform_name.lower() != "windows":
            raise RuntimeError(
                "M0.8.2i playback uses the Windows x86_64 plugin release "
                f"(observed platform: {self.platform_name})"
            )

        effect_run = Path(job.input_path).resolve()
        source = _load_source_probe(effect_run)
        godot = _resolve_binary(self.godot_bin)

        output_dir = Path(job.output_dir).resolve()
        force = bool(job.options.get("force", False))
        if output_dir.exists():
            if not force and any(output_dir.iterdir()):
                raise FileExistsError(
                    f"Godot VFX dogfood output is not empty: {output_dir}"
                )
            if force:
                shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir = output_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        addon_dir = output_dir / "addons" / "effekseer"
        plugin = _extract_verified_addon(
            self.plugin_archive,
            addon_dir,
            expected_sha256=self.expected_archive_sha256,
        )

        effects_dir = output_dir / "effects"
        effects_dir.mkdir()
        source_copy = effects_dir / "effect.efkefc"
        runtime_copy = effects_dir / "effect.efk"
        shutil.copyfile(Path(source["source_path"]), source_copy)
        shutil.copyfile(Path(source["runtime_path"]), runtime_copy)

        project = """; Generated by MADO Asset Foundry MAF-M0.8.2i
config_version=5

[application]

config/name="MAF Effekseer Playback Dogfood"
run/main_scene="res://playback.tscn"

[display]

window/size/viewport_width=640
window/size/viewport_height=360

[editor_plugins]

enabled=PackedStringArray("res://addons/effekseer/plugin.cfg")

[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""
        _write_text(output_dir / "project.godot", project)

        scene = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://playback.gd" id="1_playback"]

[node name="PlaybackProbe" type="Node3D"]
script = ExtResource("1_playback")
"""
        _write_text(output_dir / "playback.tscn", scene)

        playback = """extends Node3D

const EFFECT_PATH := "res://effects/effect.efkefc"
const REPORT_PATH := "res://evidence/runtime-report.json"

func _ready() -> void:
    var report := {
        "status": "failed",
        "effect_path": EFFECT_PATH,
        "effect_loaded": false,
        "effect_class": "",
        "emitter_class_exists": ClassDB.class_exists("EffekseerEmitter3D"),
        "play_called": false,
        "is_playing": false,
        "errors": []
    }

    if not report["emitter_class_exists"]:
        report["errors"].append("missing_class:EffekseerEmitter3D")
        _finish(report, 1)
        return

    var effect = load(EFFECT_PATH)
    if effect == null:
        report["errors"].append("effect_load_failed")
        _finish(report, 1)
        return

    report["effect_loaded"] = true
    report["effect_class"] = effect.get_class()
    if report["effect_class"] != "EffekseerEffect":
        report["errors"].append("unexpected_effect_class:" + report["effect_class"])
        _finish(report, 1)
        return

    var emitter = ClassDB.instantiate("EffekseerEmitter3D")
    if emitter == null:
        report["errors"].append("emitter_instantiate_failed")
        _finish(report, 1)
        return

    add_child(emitter)
    emitter.set("autoplay", false)
    emitter.set("effect", effect)
    await get_tree().process_frame
    emitter.call("play")
    report["play_called"] = true
    await get_tree().process_frame
    await get_tree().process_frame
    report["is_playing"] = bool(emitter.call("is_playing"))

    if not report["is_playing"]:
        report["errors"].append("emitter_not_playing")
        emitter.call("stop")
        _finish(report, 1)
        return

    report["status"] = "passed"
    emitter.call("stop")
    _finish(report, 0)


func _finish(report: Dictionary, exit_code: int) -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://evidence"))
    var file := FileAccess.open(REPORT_PATH, FileAccess.WRITE)
    if file != null:
        file.store_string(JSON.stringify(report, "\t"))
        file.close()
    print(JSON.stringify(report))
    get_tree().quit(exit_code)
"""
        _write_text(output_dir / "playback.gd", playback)

        commands = {
            "version": [str(godot), "--version"],
            "import": [str(godot), "--headless", "--path", ".", "--import"],
            "playback": [str(godot), "--headless", "--path", "."],
        }
        write_json(
            evidence_dir / "job.json",
            {
                "skill_id": self.definition.skill_id,
                "adapter_id": self.definition.adapter_id,
                "capability": job.capability,
                "effect_run": str(effect_run),
                "effect_source": {
                    "path": str(source["source_path"]),
                    "sha256": source["source_sha256"],
                    "bytes": source["source_bytes"],
                    "authoring_version": EFFEKSEER_AUTHORING_VERSION,
                },
                "effect_runtime_export": {
                    "path": str(source["runtime_path"]),
                    "sha256": source["runtime_sha256"],
                    "bytes": source["runtime_bytes"],
                },
                "plugin": plugin,
                "version_delta": {
                    "effect_authoring": EFFEKSEER_AUTHORING_VERSION,
                    "godot_plugin": EFFEKSEER_GODOT_VERSION,
                    "policy": "explicit_cross_patch_playback_probe",
                },
                "godot_binary": str(godot),
                "commands": commands,
                "network_service_started": False,
                "visual_quality_approved": False,
            },
        )

        external_code_executed = False
        version_result = self._invoke(
            step="version",
            command=commands["version"],
            cwd=output_dir,
            evidence_dir=evidence_dir,
        )
        external_code_executed = True
        if version_result.returncode != 0:
            return self._failure(
                job=job,
                evidence_dir=evidence_dir,
                message=f"Godot --version exited with code {version_result.returncode}",
                external_code_executed=True,
            )
        version_text = (version_result.stdout or version_result.stderr or "").strip()
        parsed_version = _parse_godot_version(version_text)
        if parsed_version is None or parsed_version < (4, 2):
            return self._failure(
                job=job,
                evidence_dir=evidence_dir,
                message=f"EffekseerForGodot4 requires Godot 4.2+; observed {version_text or 'unknown'}",
                external_code_executed=True,
                metadata={"godot_version": version_text or "unknown"},
            )

        import_result = self._invoke(
            step="import",
            command=commands["import"],
            cwd=output_dir,
            evidence_dir=evidence_dir,
        )
        if import_result.returncode != 0:
            return self._failure(
                job=job,
                evidence_dir=evidence_dir,
                message=f"Godot import exited with code {import_result.returncode}",
                external_code_executed=True,
                metadata={"godot_version": version_text},
            )

        playback_result = self._invoke(
            step="playback",
            command=commands["playback"],
            cwd=output_dir,
            evidence_dir=evidence_dir,
        )
        runtime_report_path = evidence_dir / "runtime-report.json"
        runtime_report: dict[str, object] | None = None
        if runtime_report_path.is_file():
            try:
                loaded = json.loads(runtime_report_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    runtime_report = loaded
            except json.JSONDecodeError:
                runtime_report = None

        playback_passed = (
            playback_result.returncode == 0
            and runtime_report is not None
            and runtime_report.get("status") == "passed"
            and runtime_report.get("effect_loaded") is True
            and runtime_report.get("effect_class") == "EffekseerEffect"
            and runtime_report.get("emitter_class_exists") is True
            and runtime_report.get("play_called") is True
            and runtime_report.get("is_playing") is True
        )
        if not playback_passed:
            return self._failure(
                job=job,
                evidence_dir=evidence_dir,
                message="Godot runtime playback evidence did not satisfy the M0.8.2i contract",
                external_code_executed=True,
                metadata={
                    "godot_version": version_text,
                    "runtime_report_path": str(runtime_report_path),
                    "runtime_report": runtime_report or {},
                    "playback_exit_code": playback_result.returncode,
                },
            )

        result = AssetSkillResult(
            skill_id=self.definition.skill_id,
            adapter_id=self.definition.adapter_id,
            capability=job.capability,
            status="success",
            input_path=job.input_path,
            output_paths=[
                str(output_dir / "project.godot"),
                str(source_copy),
                str(runtime_copy),
                str(runtime_report_path),
            ],
            evidence_path=str(evidence_dir),
            message="Effekseer Godot runtime playback evidence passed",
            metadata={
                "external_code_executed": True,
                "network_service_started": False,
                "visual_quality_approved": False,
                "godot_version": version_text,
                "plugin_version": EFFEKSEER_GODOT_VERSION,
                "plugin_archive_sha256": plugin["release_sha256"],
                "plugin_pinned_ref": EFFEKSEER_GODOT_PINNED_REF,
                "effect_authoring_version": EFFEKSEER_AUTHORING_VERSION,
                "effect_source_sha256": source["source_sha256"],
                "effect_runtime_sha256": source["runtime_sha256"],
                "runtime_report_path": str(runtime_report_path),
                "playback_verified": True,
            },
        )
        write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
        return result
