from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillSource(BaseModel):
    type: Literal["local_directory", "local_repository"]
    path: str = Field(min_length=1)
    upstream_url: str | None = None
    upstream_ref: str | None = None
    snapshot_kind: str | None = None


class SkillLicense(BaseModel):
    spdx: str | None = None
    name: str | None = None
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



class CapabilityEvidence(BaseModel):
    capability: str
    confidence: Literal["high", "medium"] = "high"
    source_file: str
    matched_terms: list[str] = Field(default_factory=list)


class RuntimeEvidence(BaseModel):
    runtime: str
    source_file: str
    reason: str


class LicenseEvidence(BaseModel):
    source_file: str | None = None
    matched_identifiers: list[str] = Field(default_factory=list)


class SkillScanReport(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    skill_id: str
    source_path: str
    manifest_path: str
    documents_scanned: list[str] = Field(default_factory=list)
    capability_evidence: list[CapabilityEvidence] = Field(default_factory=list)
    runtime_evidence: list[RuntimeEvidence] = Field(default_factory=list)
    license_evidence: LicenseEvidence = Field(default_factory=LicenseEvidence)
    external_code_executed: bool = False
    capability_classification_performed: bool = True
    status: Literal["success"] = "success"



class SkillRegistryEntry(BaseModel):
    skill_id: str
    name: str
    manifest_path: str
    source: SkillSource
    license: SkillLicense = Field(default_factory=SkillLicense)
    capabilities: list[str] = Field(default_factory=list)
    runtime: list[str] = Field(default_factory=list)
    adapter_status: Literal["intake_only", "executable", "unsupported"] = "intake_only"


class SkillRegistry(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    entries: list[SkillRegistryEntry] = Field(default_factory=list)


class ResolutionCandidate(BaseModel):
    skill_id: str
    name: str
    adapter_status: Literal["intake_only", "executable", "unsupported"]
    manifest_path: str
    runtime: list[str] = Field(default_factory=list)
    license_status: Literal["detected", "unknown", "ambiguous"] = "unknown"
    license_spdx: str | None = None
    license_name: str | None = None


class CapabilityResolution(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    capability: str
    status: Literal["resolved", "candidate_only", "ambiguous", "unresolved"]
    selected_skill_id: str | None = None
    candidates: list[ResolutionCandidate] = Field(default_factory=list)
