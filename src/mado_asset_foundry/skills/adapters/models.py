from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AdapterDefinition(BaseModel):
    adapter_id: str
    skill_id: str
    capabilities: list[str] = Field(default_factory=list)
    execution_implemented: bool = False
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    required_executables: list[str] = Field(default_factory=list)
    required_python_modules: list[str] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)
    required_source_files: list[str] = Field(default_factory=list)
    source_env: str | None = None
    required_env_files: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class AssetSkillJob(BaseModel):
    capability: str
    input_path: str
    output_dir: str
    options: dict[str, object] = Field(default_factory=dict)


class AssetSkillResult(BaseModel):
    skill_id: str
    adapter_id: str
    capability: str
    status: Literal["success", "failed", "skipped"]
    input_path: str
    output_paths: list[str] = Field(default_factory=list)
    evidence_path: str | None = None
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class PreflightCheck(BaseModel):
    check_id: str
    status: Literal["pass", "fail", "warn"]
    detail: str


class SkillPreflightReport(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    skill_id: str
    adapter_id: str | None = None
    status: Literal["ready", "blocked", "contract_only", "unregistered"]
    execution_implemented: bool = False
    promotion_eligible: bool = False
    checks: list[PreflightCheck] = Field(default_factory=list)
    external_code_executed: bool = False
