import json
from pathlib import Path

from mado_asset_foundry.io import load_recipe, load_run, write_json
from mado_asset_foundry.models import CurationDecision
from mado_asset_foundry.production import (
    advance_production,
    plan_production,
    refresh_production_status,
    start_production,
)
from mado_asset_foundry.providers.base import GeneratedImage, ImageGenerationRequest


class FakeProvider:
    name = "fixture"

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        self.requests.append(request)
        request_index = len(self.requests)
        return [
            GeneratedImage(
                content=f"fake-{request_index}-{index}".encode(),
                provider_metadata={
                    "request_id": f"req_{request_index}",
                    "usage": {"input_tokens": 5, "output_tokens": 100, "total_tokens": 105},
                },
            )
            for index in range(request.count)
        ]


def test_production_plan_uses_small_stages() -> None:
    plan = plan_production("fixtures/forest-alchemy-production.yaml")
    assert plan["probe_count"] == 1
    assert plan["pilot_count"] == 6
    assert plan["production_count"] == 12
    assert plan["max_live_count"] == 12
    assert plan["target_count"] == 6


def test_production_start_defaults_to_dry_plan(tmp_path: Path) -> None:
    provider = FakeProvider()
    report, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="probe",
        live=False,
        run_id="probe-plan",
        provider=provider,
    )
    assert report.status == "planned"
    assert report.live is False
    assert provider.requests == []
    assert load_run(run_dir / "run.json").dry_run is True


def test_live_pilot_records_usage_and_waits_for_curation(tmp_path: Path) -> None:
    provider = FakeProvider()
    report, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="pilot",
        live=True,
        run_id="pilot-live",
        provider=provider,
    )
    assert report.requested_count == 6
    assert report.status == "awaiting_curation"
    assert report.usage["output_tokens"] == 600
    assert len(provider.requests) == 6
    assert [request.count for request in provider.requests] == [1, 1, 1, 1, 1, 1]

    requests = json.loads((run_dir / "requests.json").read_text())
    assert len(requests) == 6
    assert [row["subject"] for row in requests] == [
        "red healing potion",
        "blue mana potion",
        "glowing forest mushroom",
        "bundled medicinal herbs",
        "brass alchemy mortar and pestle",
        "corked reagent bottle",
    ]


def test_refresh_status_counts_human_decisions(tmp_path: Path) -> None:
    provider = FakeProvider()
    _, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="pilot",
        live=True,
        run_id="pilot-status",
        provider=provider,
    )
    run = load_run(run_dir / "run.json")
    run.assets[0].curation_decision = CurationDecision.KEEP
    run.assets[1].curation_decision = CurationDecision.REJECT
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    report = refresh_production_status(run_dir)
    assert report.reviewed_count == 2
    assert report.keep_count == 1
    assert report.status == "awaiting_curation"



def test_pilot_cannot_advance_into_product_pipeline(tmp_path: Path) -> None:
    provider = FakeProvider()
    _, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="pilot",
        live=True,
        run_id="pilot-no-advance",
        provider=provider,
    )
    run = load_run(run_dir / "run.json")
    for asset in run.assets:
        asset.curation_decision = CurationDecision.KEEP
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    report = advance_production(run_dir)
    assert report.status == "blocked"
    assert "only_production_stage_can_advance" in report.blockers


def test_production_requires_exact_keep_target(tmp_path: Path) -> None:
    provider = FakeProvider()
    _, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="production",
        live=True,
        run_id="production-wrong-keep",
        provider=provider,
    )
    run = load_run(run_dir / "run.json")
    for index, asset in enumerate(run.assets):
        asset.curation_decision = CurationDecision.KEEP if index < 5 else CurationDecision.REJECT
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    report = advance_production(run_dir)
    assert report.status == "blocked"
    assert any(blocker.startswith("keep_count_must_equal_target:5!=6") for blocker in report.blockers)



def test_refresh_status_becomes_ready_after_full_curation(tmp_path: Path) -> None:
    provider = FakeProvider()
    _, run_dir = start_production(
        "fixtures/forest-alchemy-production.yaml",
        workspace=tmp_path,
        stage="production",
        live=True,
        run_id="production-ready",
        provider=provider,
    )
    run = load_run(run_dir / "run.json")
    for index, asset in enumerate(run.assets):
        asset.curation_decision = CurationDecision.KEEP if index < 6 else CurationDecision.REJECT
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    report = refresh_production_status(run_dir)
    assert report.status == "ready_to_advance"
    assert report.reviewed_count == 12
    assert report.keep_count == 6
