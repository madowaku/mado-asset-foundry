"""Local, integrity-bound, per-asset human visual assessments for MAF Cockpit.

These are *draft observations*, not permission to publish, not a substitute
for upstream license review, and not the final M0.9.3 release review gate.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .asset_sources import _sha256

class VisualDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["pass", "rework", "reject"]
    reviewer: str = Field(min_length=3, max_length=120)
    note: str = Field(default="", max_length=1000)

    @field_validator("reviewer", "note")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("reviewer")
    @classmethod
    def reviewer_not_blank(cls, value: str) -> str:
        if len(value) < 3:
            raise ValueError("A human reviewer is required")
        return value

    @model_validator(mode="after")
    def rationale_for_failure(self) -> "VisualDecision":
        if self.decision != "pass" and len(self.note) < 5:
            raise ValueError("Rework/reject needs a meaningful explanation")
        return self


def _review_dir(folder: Path) -> Path:
    if folder.is_symlink():
        raise ValueError("Symlinked flow folder is not allowed")
    result = folder / "review"
    if result.is_symlink():
        raise ValueError("Symlinked review directory is not allowed")
    return result


def _empty_sheet(flow: dict) -> dict:
    return {
        "schema_version": "0.1",
        "flow_id": flow["flow_id"],
        "screenshot_sha256": flow["screenshot_sha256"],
        "credits_sha256": flow["credits_sha256"],
        "manifest_sha256": flow["manifest_sha256"],
        "decisions": {},
    }


def load_sheet(folder: Path, flow: dict) -> dict:
    location = _review_dir(folder) / "visual-decisions.json"
    if location.is_symlink():
        raise ValueError("Symlinked review evidence is not allowed")
    if not location.exists():
        return _empty_sheet(flow)
    attestation = _review_dir(folder) / "human-attestation.json"
    if attestation.is_symlink():
        raise ValueError("Symlinked human attestation is not allowed")
    if attestation.is_file():
        saved_attestation = json.loads(attestation.read_text(encoding="utf-8"))
        expected_hash = saved_attestation.get("visual_review_sha256")
        if not isinstance(expected_hash, str) or _sha256(location) != expected_hash:
            raise ValueError("Signed visual assessment evidence has been modified")
    data = json.loads(location.read_text(encoding="utf-8"))
    expected = _empty_sheet(flow)
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items() if k != "decisions"):
        raise ValueError("Visual review is bound to an older screenshot, credits or manifest")
    if not isinstance(data.get("decisions"), dict):
        raise ValueError("Invalid visual review evidence")
    assets = {v["asset_id"]: v["sha256"] for v in flow["assets"]}
    if not set(data["decisions"]).issubset(assets):
        raise ValueError("Unknown asset in visual review evidence")
    for asset_id, record in data["decisions"].items():
        if not isinstance(record, dict) or record.get("asset_sha256") != assets[asset_id]:
            raise ValueError("Visual assessment has stale asset evidence")
        VisualDecision.model_validate({
            "decision": record.get("decision"),
            "reviewer": record.get("reviewer"),
            "note": record.get("note", ""),
        })
    return data


def inspect_visual(folder: Path, flow: dict) -> dict:
    sheet = load_sheet(folder, flow)
    assessments = sheet["decisions"]
    total = len(flow["assets"])
    counts = {
        key: sum(item["decision"] == key for item in assessments.values())
        for key in ("pass", "rework", "reject")
    }
    pending = total - len(assessments)
    return {
        "total": total,
        "reviewed": len(assessments),
        "pending": pending,
        "passed": counts["pass"],
        "rework": counts["rework"],
        "rejected": counts["reject"],
        "ready_for_final_review": pending == 0 and counts["pass"] == total and total > 0,
        "decisions": assessments,
    }


def record_visual(folder: Path, flow: dict, asset_id: str, incoming: VisualDecision) -> dict:
    if (folder / "review" / "release-check.json").exists():
        raise ValueError("Final human review is already recorded")
    lookup = {item["asset_id"]: item["sha256"] for item in flow["assets"]}
    if asset_id not in lookup:
        raise KeyError(asset_id)
    sheet = load_sheet(folder, flow)
    record = incoming.model_dump(mode="json")
    record["asset_sha256"] = lookup[asset_id]
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    sheet["decisions"][asset_id] = record
    directory = _review_dir(folder)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "visual-decisions.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         prefix=".visual-", suffix=".tmp",
                                         dir=directory, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(sheet, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        if path.is_symlink():
            raise ValueError("Symlinked review evidence is not allowed")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return inspect_visual(folder, flow)
