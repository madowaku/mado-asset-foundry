from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillSource(BaseModel):
    type: Literal["local_directory", "local_repository"]
    path: str = Field(min_length=1)


class SkillLicense(BaseModel):
    spdx: str | None = None
    source_file: str | None = None
    status: Literal["detected", "unknown", "ambiguous"] = "unknown"


class SkillEntrypoints(BaseModel):
    skill_md: str | None = None
    readme: str | None = None
    scripts: list[str] = Field(default_factory=list)
    metadata_files: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    skill_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    version: str | None = None
    source: SkillSource
    license: SkillLicense = Field(default_factory=SkillLicense)
    entrypoints: SkillEntrypoints = Field(default_factory=SkillEntrypoints)
    capabilities: list[str] = Field(default_factory=list)
    runtime: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    adapter_status: Literal["intake_only", "executable", "unsupported"] = "intake_only"
    notes: list[str] = Field(default_factory=list)


class SkillIntakeReport(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    skill_id: str
    source_path: str
    manifest_path: str
    discovered_files: list[str] = Field(default_factory=list)
    external_code_executed: bool = False
    capability_classification_performed: bool = False
    status: Literal["success"] = "success"
