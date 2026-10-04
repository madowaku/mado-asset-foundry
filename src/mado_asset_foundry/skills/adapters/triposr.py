from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ...io import write_json
from .models import AdapterDefinition, AssetSkillJob, AssetSkillResult


TRIPOSR_PINNED_REF = "107cefdc244c39106fa830359024f6a2f1c78871"

TRIPOSR_DEFINITION = AdapterDefinition(
    adapter_id="triposr-local",
    skill_id="triposr-snapshot",
    capabilities=[
        "model3d_generate",
        "image_to_mesh",
        "mesh_texture_bake",
    ],
    execution_implemented=True,
    timeout_seconds=900,
    required_executables=["python"],
    required_env=["TRIPOSR_HOME", "TRIPOSR_MODEL_PATH"],
    required_source_files=["run.py", "tsr/system.py", "requirements.txt"],
    source_env="TRIPOSR_HOME",
    required_env_files={
        "TRIPOSR_MODEL_PATH": ["config.yaml", "model.ckpt"],
    },
    notes=[
        "Runs exactly one local image through a pinned local TripoSR checkout.",
        "Model path must be local; implicit Hugging Face model download is not allowed.",
        "No dependency installation or repository cloning is performed.",
    ],
)


Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess[str]]


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


def _read_git_head(source_root: Path) -> str | None:
    git_dir = source_root / ".git"
    if not git_dir.is_dir():
        return None
    head_path = git_dir / "HEAD"
    if not head_path.is_file():
        return None
    head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
    if len(head) == 40 and all(char in "0123456789abcdefABCDEF" for char in head):
        return head.lower()
    if not head.startswith("ref: "):
        return None
    relative = head[5:].strip()
    ref_path = git_dir / relative
    if ref_path.is_file():
        value = ref_path.read_text(encoding="utf-8", errors="ignore").strip()
        if len(value) == 40:
            return value.lower()
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("#") or line.startswith("^") or " " not in line:
                continue
            value, name = line.split(" ", 1)
            if name.strip() == relative and len(value) == 40:
                return value.lower()
    return None


def _validate_input_image(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Input image not found: {path}")
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Input is not a decodable image: {path}") from exc


def _prepare_transparent_input(
    input_path: Path,
    prepared_path: Path,
    *,
    foreground_ratio: float,
) -> dict[str, object]:
    with Image.open(input_path) as source:
        rgba = source.convert("RGBA")

    alpha = rgba.getchannel("A")
    minimum_alpha, maximum_alpha = alpha.getextrema()
    if minimum_alpha == 255:
        raise ValueError(
            "Local-only TripoSR probe requires an input with real alpha transparency; "
            "opaque inputs would invoke upstream rembg and may require an external model download"
        )
    bbox = alpha.getbbox()
    if bbox is None or maximum_alpha == 0:
        raise ValueError("Input image contains no visible foreground pixels")

    foreground = rgba.crop(bbox)
    size = max(foreground.size)
    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    square.paste(
        foreground,
        ((size - foreground.width) // 2, (size - foreground.height) // 2),
        foreground,
    )

    canvas_size = max(size, int(round(size / foreground_ratio)))
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(
        square,
        ((canvas_size - size) // 2, (canvas_size - size) // 2),
        square,
    )

    gray = Image.new("RGBA", canvas.size, (128, 128, 128, 255))
    prepared = Image.alpha_composite(gray, canvas).convert("RGB")
    prepared_path.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(prepared_path, format="PNG")
    return {
        "input_mode": "RGBA",
        "alpha_min": minimum_alpha,
        "alpha_max": maximum_alpha,
        "foreground_bbox": list(bbox),
        "prepared_size": list(prepared.size),
        "prepared_sha256": _sha256(prepared_path),
    }


def _validate_mesh(path: Path, model_format: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"TripoSR did not produce a non-empty mesh: {path}")
    if model_format == "glb":
        data = path.read_bytes()[:12]
        if len(data) < 12 or data[:4] != b"glTF":
            raise RuntimeError(f"TripoSR output is not a valid GLB header: {path}")
        version = int.from_bytes(data[4:8], "little")
        if version != 2:
            raise RuntimeError(f"Unsupported GLB version {version}: {path}")
    elif model_format == "obj":
        text = path.read_text(encoding="utf-8", errors="ignore")
        has_vertex = any(line.startswith("v ") for line in text.splitlines())
        has_face = any(line.startswith("f ") for line in text.splitlines())
        if not (has_vertex and has_face):
            raise RuntimeError(f"TripoSR OBJ lacks vertex/face records: {path}")
    else:
        raise ValueError(f"Unsupported TripoSR model format: {model_format}")


class TripoSRLocalAdapter:
    definition = TRIPOSR_DEFINITION

    def __init__(
        self,
        *,
        source_root: str | Path,
        model_path: str | Path,
        python_bin: str = "python",
        timeout_seconds: int | None = None,
        runner: Runner | None = None,
        expected_ref: str = TRIPOSR_PINNED_REF,
    ) -> None:
        self.source_root = Path(source_root)
        self.model_path = Path(model_path)
        self.python_bin = python_bin
        self.timeout_seconds = timeout_seconds or self.definition.timeout_seconds
        self.runner = runner or _default_runner
        self.expected_ref = expected_ref

    @classmethod
    def from_environment(cls) -> "TripoSRLocalAdapter":
        source = os.environ.get("TRIPOSR_HOME")
        model = os.environ.get("TRIPOSR_MODEL_PATH")
        if not source or not model:
            raise RuntimeError(
                "TRIPOSR_HOME and TRIPOSR_MODEL_PATH are required for the local TripoSR adapter"
            )
        return cls(
            source_root=source,
            model_path=model,
            python_bin=os.environ.get("TRIPOSR_PYTHON", "python"),
        )

    def _resolve_python(self) -> str:
        direct = Path(self.python_bin)
        if direct.is_file():
            return str(direct.resolve())
        located = shutil.which(self.python_bin)
        if located:
            return located
        raise FileNotFoundError(f"TripoSR Python executable not found: {self.python_bin}")

    def _validate_local_contract(self, *, allow_unpinned_source: bool) -> dict[str, object]:
        if not self.source_root.is_dir():
            raise FileNotFoundError(f"TripoSR source directory not found: {self.source_root}")
        for relative in ("run.py", "tsr/system.py", "requirements.txt"):
            if not (self.source_root / relative).is_file():
                raise FileNotFoundError(f"TripoSR source file missing: {relative}")
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"TripoSR model directory not found: {self.model_path}")
        for relative in ("config.yaml", "model.ckpt"):
            if not (self.model_path / relative).is_file():
                raise FileNotFoundError(f"TripoSR model file missing: {relative}")

        observed_ref = _read_git_head(self.source_root)
        if not allow_unpinned_source and observed_ref != self.expected_ref:
            raise RuntimeError(
                "TripoSR checkout is not pinned to the expected commit: "
                f"expected {self.expected_ref}, observed {observed_ref or 'unknown'}"
            )

        return {
            "expected_ref": self.expected_ref,
            "observed_ref": observed_ref,
            "source_pinned": observed_ref == self.expected_ref,
            "run_py_sha256": _sha256(self.source_root / "run.py"),
            "model_config_sha256": _sha256(self.model_path / "config.yaml"),
            "model_checkpoint_bytes": (self.model_path / "model.ckpt").stat().st_size,
        }

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        if job.capability not in self.definition.capabilities:
            raise ValueError(
                f"TripoSR adapter does not support capability: {job.capability}"
            )

        input_path = Path(job.input_path).resolve()
        output_dir = Path(job.output_dir).resolve()
        _validate_input_image(input_path)

        model_format = str(job.options.get("model_format", "glb")).lower()
        bake_texture = bool(job.options.get("bake_texture", False))
        allow_unpinned = bool(job.options.get("allow_unpinned_source", False))
        mc_resolution = int(job.options.get("mc_resolution", 256))
        texture_resolution = int(job.options.get("texture_resolution", 2048))
        foreground_ratio = float(job.options.get("foreground_ratio", 0.85))

        if model_format not in {"glb", "obj"}:
            raise ValueError("model_format must be glb or obj")
        if bake_texture and model_format != "obj":
            raise ValueError(
                "TripoSR texture baking is restricted to OBJ in MAF because upstream xatlas.export is the bake path"
            )
        if not 32 <= mc_resolution <= 512:
            raise ValueError("mc_resolution must be between 32 and 512")
        if not 0.1 <= foreground_ratio <= 1.0:
            raise ValueError("foreground_ratio must be between 0.1 and 1.0")

        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(f"TripoSR probe output is not empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir = output_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        contract = self._validate_local_contract(
            allow_unpinned_source=allow_unpinned,
        )
        python = self._resolve_python()
        prepared_input = evidence_dir / "prepared-input.png"
        input_preparation = _prepare_transparent_input(
            input_path,
            prepared_input,
            foreground_ratio=foreground_ratio,
        )

        command = [
            python,
            str((self.source_root / "run.py").resolve()),
            str(prepared_input),
            "--output-dir",
            str(output_dir),
            "--pretrained-model-name-or-path",
            str(self.model_path.resolve()),
            "--model-save-format",
            model_format,
            "--mc-resolution",
            str(mc_resolution),
            "--foreground-ratio",
            str(foreground_ratio),
            "--no-remove-bg",
        ]
        if bake_texture:
            command.extend(
                [
                    "--bake-texture",
                    "--texture-resolution",
                    str(texture_resolution),
                ]
            )

        job_record = {
            "skill_id": self.definition.skill_id,
            "adapter_id": self.definition.adapter_id,
            "capability": job.capability,
            "input_path": str(input_path),
            "input_sha256": _sha256(input_path),
            "source_root": str(self.source_root.resolve()),
            "model_path": str(self.model_path.resolve()),
            "model_format": model_format,
            "bake_texture": bake_texture,
            "mc_resolution": mc_resolution,
            "texture_resolution": texture_resolution,
            "foreground_ratio": foreground_ratio,
            "network_model_download_allowed": False,
            "rembg_invoked": False,
            "input_preparation": input_preparation,
            "external_code_executed": True,
            "contract": contract,
            "command": command,
        }
        write_json(evidence_dir / "job.json", job_record)

        try:
            completed = self.runner(command, self.source_root, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="ignore") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="ignore") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            (evidence_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (evidence_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            result = AssetSkillResult(
                skill_id=self.definition.skill_id,
                adapter_id=self.definition.adapter_id,
                capability=job.capability,
                status="failed",
                input_path=str(input_path),
                evidence_path=str(evidence_dir),
                message=f"TripoSR timed out after {self.timeout_seconds} seconds",
                metadata={"external_code_executed": True},
            )
            write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
            return result

        (evidence_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
        (evidence_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")

        if completed.returncode != 0:
            result = AssetSkillResult(
                skill_id=self.definition.skill_id,
                adapter_id=self.definition.adapter_id,
                capability=job.capability,
                status="failed",
                input_path=str(input_path),
                evidence_path=str(evidence_dir),
                message=f"TripoSR exited with code {completed.returncode}",
                metadata={
                    "external_code_executed": True,
                    "returncode": completed.returncode,
                },
            )
            write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
            return result

        mesh_path = output_dir / "0" / f"mesh.{model_format}"
        try:
            _validate_mesh(mesh_path, model_format)
        except (RuntimeError, ValueError) as exc:
            result = AssetSkillResult(
                skill_id=self.definition.skill_id,
                adapter_id=self.definition.adapter_id,
                capability=job.capability,
                status="failed",
                input_path=str(input_path),
                evidence_path=str(evidence_dir),
                message=str(exc),
                metadata={
                    "external_code_executed": True,
                    "returncode": completed.returncode,
                },
            )
            write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
            return result

        output_paths = [str(mesh_path)]
        texture_path = output_dir / "0" / "texture.png"
        if bake_texture and texture_path.is_file():
            output_paths.append(str(texture_path))

        result = AssetSkillResult(
            skill_id=self.definition.skill_id,
            adapter_id=self.definition.adapter_id,
            capability=job.capability,
            status="success",
            input_path=str(input_path),
            output_paths=output_paths,
            evidence_path=str(evidence_dir),
            message="TripoSR local 1-asset probe completed",
            metadata={
                "external_code_executed": True,
                "returncode": completed.returncode,
                "mesh_sha256": _sha256(mesh_path),
                "mesh_bytes": mesh_path.stat().st_size,
                "source_pinned": contract["source_pinned"],
                "observed_ref": contract["observed_ref"],
                "network_model_download_allowed": False,
                "rembg_invoked": False,
                "prepared_input_sha256": input_preparation["prepared_sha256"],
            },
        )
        write_json(evidence_dir / "result.json", result.model_dump(mode="json"))
        return result
