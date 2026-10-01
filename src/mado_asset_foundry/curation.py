from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .io import load_run, write_json
from .models import AssetRecord, AssetState, CurationDecision, FoundryRun


def state_for_decision(decision: CurationDecision) -> AssetState:
    return {
        CurationDecision.UNREVIEWED: AssetState.GENERATED,
        CurationDecision.REJECT: AssetState.REJECTED,
        CurationDecision.MAYBE: AssetState.REVIEW_PENDING,
        CurationDecision.KEEP: AssetState.SELECTED,
    }[decision]


def summarize_run(run: FoundryRun) -> dict[str, int]:
    counts = {decision.value: 0 for decision in CurationDecision}
    favorites = 0
    for asset in run.assets:
        counts[asset.curation_decision.value] += 1
        favorites += int(asset.favorite)
    counts["favorite"] = favorites
    counts["total"] = len(run.assets)
    counts["reviewed"] = len(run.assets) - counts[CurationDecision.UNREVIEWED.value]
    return counts


def _asset_metadata_path(run_dir: Path, asset: AssetRecord) -> Path:
    canonical = run_dir / "metadata" / f"{asset.asset_id}.json"
    if canonical.exists() or asset.metadata_path is None:
        return canonical

    recorded = Path(asset.metadata_path)
    if recorded.is_absolute() and recorded.exists():
        return recorded
    if recorded.exists():
        return recorded
    return canonical


def apply_curation(
    run_dir: str | Path,
    asset_id: str,
    *,
    decision: CurationDecision | None = None,
    favorite: bool | None = None,
) -> FoundryRun:
    directory = Path(run_dir)
    run_path = directory / "run.json"
    run = load_run(run_path)

    asset = next((item for item in run.assets if item.asset_id == asset_id), None)
    if asset is None:
        raise KeyError(asset_id)
    if decision is None and favorite is None:
        raise ValueError("decision or favorite is required")

    if decision is not None:
        asset.curation_decision = decision
        asset.state = state_for_decision(decision)
    if favorite is not None:
        asset.favorite = favorite

    updated_at = datetime.now(timezone.utc).isoformat()
    metadata_path = _asset_metadata_path(directory, asset)
    metadata: dict[str, object] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "asset_id": asset.asset_id,
            "curation_decision": asset.curation_decision.value,
            "favorite": asset.favorite,
            "curation_updated_at": updated_at,
        }
    )
    write_json(metadata_path, metadata)
    asset.metadata_path = str(metadata_path)
    write_json(run_path, run.model_dump(mode="json"))
    return run
