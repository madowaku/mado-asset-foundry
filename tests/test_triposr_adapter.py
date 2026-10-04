import subprocess
from pathlib import Path

import pytest
from PIL import Image

from mado_asset_foundry.skills.adapters.models import AssetSkillJob
from mado_asset_foundry.skills.adapters.triposr import (
    TRIPOSR_PINNED_REF,
    TripoSRLocalAdapter,
)


def make_source(root: Path, *, ref: str = TRIPOSR_PINNED_REF) -> Path:
    (root / "tsr").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text(ref + "\n", encoding="utf-8")
    (root / "run.py").write_text("# synthetic TripoSR runner\n", encoding="utf-8")
    (root / "tsr" / "system.py").write_text("# synthetic system\n", encoding="utf-8")
    (root / "requirements.txt").write_text("torch\n", encoding="utf-8")
    return root


def make_model(root: Path) -> Path:
    root.mkdir()
    (root / "config.yaml").write_text("model: fixture\n", encoding="utf-8")
    (root / "model.ckpt").write_bytes(b"fixture-model")
    return root


def make_input(path: Path) -> Path:
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(path)
    return path


def make_glb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"glTF" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little")
    )


def test_triposr_probe_runs_one_local_asset_without_model_download(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr")
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")
    calls: list[list[str]] = []

    def runner(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output_dir = Path(command[command.index("--output-dir") + 1])
        make_glb(output_dir / "0" / "mesh.glb")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    adapter = TripoSRLocalAdapter(
        source_root=source,
        model_path=model,
        python_bin="python",
        runner=runner,
    )
    adapter._resolve_python = lambda: "python"  # type: ignore[method-assign]
    output = tmp_path / "probe"
    result = adapter.run(
        AssetSkillJob(
            capability="image_to_mesh",
            input_path=str(input_path),
            output_dir=str(output),
        )
    )

    assert result.status == "success"
    assert len(calls) == 1
    command = calls[0]
    assert command[command.index("--pretrained-model-name-or-path") + 1] == str(model.resolve())
    assert "stabilityai/TripoSR" not in command
    assert result.metadata["source_pinned"] is True
    assert result.metadata["network_model_download_allowed"] is False
    assert (output / "evidence" / "job.json").exists()
    assert (output / "evidence" / "stdout.log").exists()
    assert (output / "evidence" / "result.json").exists()


def test_triposr_probe_blocks_unpinned_checkout_by_default(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr", ref="0" * 40)
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")
    adapter = TripoSRLocalAdapter(
        source_root=source,
        model_path=model,
        runner=lambda command, cwd, timeout: subprocess.CompletedProcess(command, 0, "", ""),
    )
    with pytest.raises(RuntimeError, match="not pinned"):
        adapter.run(
            AssetSkillJob(
                capability="image_to_mesh",
                input_path=str(input_path),
                output_dir=str(tmp_path / "probe"),
            )
        )


def test_triposr_probe_can_explicitly_allow_unpinned_source(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr", ref="0" * 40)
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")

    def runner(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        output_dir = Path(command[command.index("--output-dir") + 1])
        make_glb(output_dir / "0" / "mesh.glb")
        return subprocess.CompletedProcess(command, 0, "", "")

    adapter = TripoSRLocalAdapter(source_root=source, model_path=model, runner=runner)
    adapter._resolve_python = lambda: "python"  # type: ignore[method-assign]
    result = adapter.run(
        AssetSkillJob(
            capability="image_to_mesh",
            input_path=str(input_path),
            output_dir=str(tmp_path / "probe"),
            options={"allow_unpinned_source": True},
        )
    )
    assert result.status == "success"
    assert result.metadata["source_pinned"] is False


def test_triposr_probe_preserves_failure_evidence(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr")
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")
    adapter = TripoSRLocalAdapter(
        source_root=source,
        model_path=model,
        runner=lambda command, cwd, timeout: subprocess.CompletedProcess(
            command, 7, "partial", "boom"
        ),
    )
    adapter._resolve_python = lambda: "python"  # type: ignore[method-assign]
    output = tmp_path / "probe"
    result = adapter.run(
        AssetSkillJob(
            capability="image_to_mesh",
            input_path=str(input_path),
            output_dir=str(output),
        )
    )
    assert result.status == "failed"
    assert "code 7" in result.message
    assert (output / "evidence" / "stdout.log").read_text(encoding="utf-8") == "partial"
    assert (output / "evidence" / "stderr.log").read_text(encoding="utf-8") == "boom"
    assert (output / "evidence" / "result.json").exists()


def test_triposr_zero_exit_without_mesh_is_failure(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr")
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")
    adapter = TripoSRLocalAdapter(
        source_root=source,
        model_path=model,
        runner=lambda command, cwd, timeout: subprocess.CompletedProcess(command, 0, "ok", ""),
    )
    adapter._resolve_python = lambda: "python"  # type: ignore[method-assign]
    result = adapter.run(
        AssetSkillJob(
            capability="image_to_mesh",
            input_path=str(input_path),
            output_dir=str(tmp_path / "probe"),
        )
    )
    assert result.status == "failed"
    assert "non-empty mesh" in result.message


def test_texture_bake_requires_obj(tmp_path: Path) -> None:
    source = make_source(tmp_path / "triposr")
    model = make_model(tmp_path / "model")
    input_path = make_input(tmp_path / "input.png")
    adapter = TripoSRLocalAdapter(source_root=source, model_path=model)
    with pytest.raises(ValueError, match="restricted to OBJ"):
        adapter.run(
            AssetSkillJob(
                capability="mesh_texture_bake",
                input_path=str(input_path),
                output_dir=str(tmp_path / "probe"),
                options={"model_format": "glb", "bake_texture": True},
            )
        )
