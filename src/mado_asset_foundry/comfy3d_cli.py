"""CLI entrypoints for MAF-M1.3 ComfyUI native 3D probes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import typer

from .comfy3d import Comfy3DClient, plan_comfy3d, run_comfy3d

comfy3d_app = typer.Typer(help="Local ComfyUI Trellis2 / Pixal3D bridge (no auto-publishing)")


@comfy3d_app.command("plan")
def plan(
    image: Path = typer.Argument(..., help="Local source PNG/JPEG/WEBP."),
    workflow: Path = typer.Option(..., "--workflow", help="ComfyUI Export Workflow (API) JSON."),
    image_node: str | None = typer.Option(None, "--image-node"),
    save_node: str | None = typer.Option(None, "--save-node"),
) -> None:
    """Validate input and API graph without contacting ComfyUI."""
    try:
        report = plan_comfy3d(
            image, workflow, image_node=image_node, save_node=save_node
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"Comfy3D planning blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


@comfy3d_app.command("probe")
def probe(
    image: Path = typer.Argument(..., help="Local source image."),
    workflow: Path = typer.Option(..., "--workflow", help="Export Workflow (API) JSON."),
    live: bool = typer.Option(False, "--live", help="Required: send one real job to local ComfyUI."),
    server: str = typer.Option("http://127.0.0.1:8188", "--server"),
    workspace: Path = typer.Option(Path("runs/comfy3d-probes"), "--workspace"),
    run_id: str | None = typer.Option(None, "--run-id"),
    image_node: str | None = typer.Option(None, "--image-node"),
    save_node: str | None = typer.Option(None, "--save-node"),
    timeout: int = typer.Option(900, "--timeout", min=1, max=3600),
) -> None:
    """Submit exactly one job. Success means GLB acquired, NOT production-approved."""
    if not live:
        typer.echo("Live Comfy3D execution requires --live; use maf comfy3d plan first.", err=True)
        raise typer.Exit(code=1)
    selected_id = run_id or ("comfy3d-" + uuid4().hex[:12])
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", selected_id):
        typer.echo("Run ID must be a lowercase slug (1 to 64 chars).", err=True)
        raise typer.Exit(code=1)
    try:
        client = Comfy3DClient(server)
        report, directory = run_comfy3d(
            image, workflow, output_dir=workspace / selected_id,
            client=client, image_node=image_node, save_node=save_node,
            timeout_seconds=timeout,
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"Comfy3D probe blocked before execution: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Run: {directory}")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"Evidence: {directory / 'evidence.json'}")
    if report["asset_paths"]:
        typer.echo(f"GLB: {directory / report['asset_paths'][0]}")
    if report["failure"]:
        typer.echo(f"Failure: {report['failure']}", err=True)
        raise typer.Exit(code=2)


@comfy3d_app.command("glb-inspect")
def glb_inspect(
    probe_run: Path = typer.Argument(..., help="Completed M1.3 probe directory."),
    require_textures: bool = typer.Option(
        False, "--require-textures", help="Require base color and metallic-roughness maps."
    ),
) -> None:
    """Offline GLB/PBR preflight; does not start Godot or approve publication."""
    from .glb_godot_qa import inspect_probe

    try:
        report = inspect_probe(probe_run, require_textures=require_textures)
    except (OSError, ValueError) as exc:
        typer.echo(f"GLB inspection blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


@comfy3d_app.command("godot-qa")
def glb_godot_qa(
    probe_run: Path = typer.Argument(..., help="Completed M1.3 ComfyUI probe directory."),
    godot_bin: str = typer.Option(..., "--godot-bin", help="Explicit Godot 4.2+ binary."),
    workspace: Path = typer.Option(Path("runs/comfy3d-godot-qa"), "--workspace"),
    run_id: str | None = typer.Option(None, "--run-id"),
    require_textures: bool = typer.Option(False, "--require-textures"),
    timeout: int = typer.Option(120, "--timeout", min=1, max=600),
) -> None:
    """Actually import GLB with Godot in an isolated MAF-authored project."""
    from .glb_godot_qa import verify_glb_godot

    try:
        report, directory = verify_glb_godot(
            probe_run, godot_bin=godot_bin, workspace=workspace,
            run_id=run_id, require_textures=require_textures, timeout=timeout,
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"Godot GLB QA preflight blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Run: {directory}")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"Evidence: {directory / 'report.json'}")
    typer.echo("Visual and rights review: STILL REQUIRED")
    if report["status"] != "awaiting_visual_review":
        typer.echo(f"Failure: {report['failure']}", err=True)
        raise typer.Exit(code=2)
