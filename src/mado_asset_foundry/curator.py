from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator

from .curation import apply_curation, summarize_run
from .io import load_run
from .models import CurationDecision


class CurationPatch(BaseModel):
    decision: CurationDecision | None = None
    favorite: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CurationPatch":
        if self.decision is None and self.favorite is None:
            raise ValueError("decision or favorite is required")
        return self


def _safe_run_dir(workspace: Path, run_id: str) -> Path:
    root = workspace.resolve()
    candidate = (root / run_id).resolve()
    if candidate.parent != root:
        raise HTTPException(status_code=400, detail="invalid run id")
    if not (candidate / "run.json").exists():
        raise HTTPException(status_code=404, detail="run not found")
    return candidate


def _image_path(run_dir: Path, asset_id: str) -> Path:
    raw = (run_dir / "raw").resolve()
    matches = [p for p in raw.glob(f"{asset_id}.*") if p.is_file()]
    if not matches:
        raise HTTPException(status_code=404, detail="asset image not found")
    image = matches[0].resolve()
    if image.parent != raw:
        raise HTTPException(status_code=400, detail="invalid asset path")
    return image


def create_app(workspace: str | Path = "runs") -> FastAPI:
    workspace_path = Path(workspace)
    ui_dir = Path(__file__).with_name("ui")
    app = FastAPI(title="MADO Asset Foundry Curator", version="0.2.0")
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(ui_dir / "curator.html")

    @app.get("/api/runs")
    def list_runs() -> dict[str, object]:
        runs: list[dict[str, object]] = []
        if workspace_path.exists():
            for run_path in sorted(workspace_path.glob("*/run.json"), reverse=True):
                try:
                    run = load_run(run_path)
                except Exception:
                    continue
                runs.append(
                    {
                        "run_id": run.run_id,
                        "recipe_id": run.recipe_id,
                        "model": run.model,
                        "requested_count": run.requested_count,
                        "summary": summarize_run(run),
                    }
                )
        return {"runs": runs}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        run_dir = _safe_run_dir(workspace_path, run_id)
        run = load_run(run_dir / "run.json")
        return {
            "run": run.model_dump(mode="json"),
            "summary": summarize_run(run),
        }

    @app.get("/api/runs/{run_id}/assets/{asset_id}/image")
    def get_asset_image(run_id: str, asset_id: str) -> FileResponse:
        run_dir = _safe_run_dir(workspace_path, run_id)
        return FileResponse(_image_path(run_dir, asset_id))

    @app.patch("/api/runs/{run_id}/assets/{asset_id}")
    def patch_asset(run_id: str, asset_id: str, patch: CurationPatch) -> dict[str, object]:
        run_dir = _safe_run_dir(workspace_path, run_id)
        try:
            run = apply_curation(
                run_dir,
                asset_id,
                decision=patch.decision,
                favorite=patch.favorite,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="asset not found") from None
        asset = next(item for item in run.assets if item.asset_id == asset_id)
        return {
            "asset": asset.model_dump(mode="json"),
            "summary": summarize_run(run),
        }

    return app


def serve_curator(
    workspace: str | Path = "runs",
    *,
    host: str = "127.0.0.1",
    port: int = 4173,
) -> None:
    import uvicorn

    uvicorn.run(create_app(workspace), host=host, port=port)


app = create_app()
