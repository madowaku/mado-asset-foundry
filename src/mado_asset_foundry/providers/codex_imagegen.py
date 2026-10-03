from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .base import GeneratedImage, ImageGenerationRequest


Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess[str]]


def _default_runner(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class CodexImageGenProvider:
    """Bridge Codex built-in image generation into the MAF provider contract."""

    name = "codex-imagegen"

    def __init__(
        self,
        *,
        codex_model: str = "gpt-6-luna",
        codex_binary: str = "codex",
        timeout_seconds: int = 420,
        runner: Runner | None = None,
    ) -> None:
        self.codex_model = codex_model
        self.codex_binary = codex_binary
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _default_runner

    def _resolve_binary(self) -> str:
        direct = Path(self.codex_binary)
        if direct.exists():
            return str(direct.resolve())
        located = shutil.which(self.codex_binary)
        if located:
            return located
        raise FileNotFoundError(
            f"Codex CLI was not found: {self.codex_binary}. "
            "Install/sign in to Codex or set generation.codex_binary."
        )

    def check_installation(self) -> dict[str, str]:
        binary = self._resolve_binary()
        result = self._runner([binary, "--version"], Path.cwd(), 30)
        if result.returncode != 0:
            raise RuntimeError(
                f"Codex CLI version check failed with exit code {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        version_lines = (result.stdout or result.stderr).strip().splitlines()
        return {
            "binary": binary,
            "version": version_lines[0] if version_lines else "unknown",
            "codex_model": self.codex_model,
            "image_model": "gpt-image-2",
        }

    def _compile_prompt(self, request: ImageGenerationRequest, output_name: str) -> str:
        background = (
            "The background must be genuinely transparent with an alpha channel."
            if request.background == "transparent"
            else "Use the requested non-transparent background treatment."
        )
        return f"""$imagegen
Generate exactly one production source image for MADO Asset Foundry.

Image brief:
{request.prompt}

Hard output requirements:
- Use Codex built-in image generation. The rendering model is gpt-image-2.
- Generate exactly one image, not a contact sheet or multiple variants.
- Requested canvas size: {request.size}.
- Requested quality intent: {request.quality}.
- {background}
- Output must be PNG.
- Save or copy the final generated PNG to exactly: {output_name}
- The file must be inside the current working directory.
- Do not post-process, resize, crop, quantize, or add text after generation.
- Do not modify any other files.

After the PNG exists at that exact path, reply with only:
SAVED {output_name}
"""

    @staticmethod
    def _find_output(workspace: Path, expected: Path) -> Path:
        if expected.exists():
            return expected
        candidates = sorted(path for path in workspace.rglob("*.png") if path.is_file())
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise RuntimeError("Codex ImageGen completed without materializing a PNG file")
        raise RuntimeError(
            f"Codex ImageGen produced {len(candidates)} PNG files; expected exactly one"
        )

    @staticmethod
    def _validate_png(path: Path) -> None:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise RuntimeError("Codex ImageGen output is not PNG")
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise RuntimeError(
                f"Codex ImageGen output could not be decoded as PNG: {exc}"
            ) from exc

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        if request.model != "gpt-image-2":
            raise ValueError("codex-imagegen bridge requires request.model='gpt-image-2'")
        if request.output_format != "png":
            raise ValueError("codex-imagegen bridge currently supports PNG output only")

        binary = self._resolve_binary()
        generated: list[GeneratedImage] = []

        for index in range(request.count):
            with tempfile.TemporaryDirectory(prefix="maf-codex-imagegen-") as temp:
                workspace = Path(temp)
                output_name = f"maf-output-{index + 1:02d}.png"
                expected = workspace / output_name
                prompt = self._compile_prompt(request, output_name)
                command = [
                    binary,
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "workspace-write",
                    "--model",
                    self.codex_model,
                    "-C",
                    str(workspace),
                    prompt,
                ]
                try:
                    result = self._runner(command, workspace, self.timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"Codex ImageGen timed out after {self.timeout_seconds} seconds"
                    ) from exc

                if result.returncode != 0:
                    detail = (result.stderr or result.stdout).strip()
                    raise RuntimeError(
                        f"Codex ImageGen failed with exit code {result.returncode}: "
                        f"{detail[-2000:]}"
                    )

                output = self._find_output(workspace, expected)
                self._validate_png(output)
                generated.append(
                    GeneratedImage(
                        content=output.read_bytes(),
                        revised_prompt=None,
                        provider_metadata={
                            "image_model": "gpt-image-2",
                            "codex_model": self.codex_model,
                            "usage_scope": "codex_general_usage",
                            "codex_exit_code": result.returncode,
                            "codex_final_message": (result.stdout or "").strip()[-1000:],
                        },
                    )
                )

        return generated
