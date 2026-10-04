from __future__ import annotations

from typing import Protocol

from .models import AdapterDefinition, AssetSkillJob, AssetSkillResult


class AssetSkillAdapter(Protocol):
    """Execution contract for explicitly supported external Skill adapters."""

    definition: AdapterDefinition

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        ...
