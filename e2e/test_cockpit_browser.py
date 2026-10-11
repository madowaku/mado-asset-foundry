"""MAF-M1.2 true Chromium browser E2E for production and human QA.

The browser drives M1.1 HTML/JS via a real loopback Uvicorn server.
Only original synthetic test PNGs are used; Godot-dependent operations
are faked here (the existing real-Godot CI jobs remain mandatory).
"""
from __future__ import annotations

import io
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
import yaml
from PIL import Image, ImageChops, ImageDraw, ImageStat
from playwright.sync_api import Page, TimeoutError as BrowserTimeout, expect, sync_playwright
from e2e.visual_goldens import compare_golden

import mado_asset_foundry.asset_flow as flow
from mado_asset_foundry.asset_sources import _sha256
from mado_asset_foundry.attribution_bridge import BridgePlan, _read_object
from mado_asset_foundry.cockpit import create_app
from mado_asset_foundry.io import write_json
from mado_asset_foundry.visual_gallery import _evidence_entries

ROOT = Path(__file__).resolve().parent
BASELINE = json.loads((ROOT / "baselines" / "cockpit_layout.json").read_text(encoding="utf-8"))
ARTIFACTS = Path("runs/browser-e2e")


def _recipe(root: Path) -> Path:
    source_root = root / "recipes"
    images = source_root / "inputs"
    source_root.mkdir(parents=True)
    submissions: list[str] = []
    for asset_id, color in (("ember", (245, 125, 75, 255)), ("moss", (90, 201, 148, 255))):
        directory = images / asset_id
        directory.mkdir(parents=True)
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((3, 3, 29, 29), fill=color)
        img.save(directory / "icon.png")
        (directory / "LICENSE.txt").write_text(
            "Synthetic MADO original image dedicated CC0-1.0.", encoding="utf-8"
        )
        (directory / "submission.yaml").write_text(yaml.safe_dump({
            "asset_id": asset_id, "source_id": "local",
            "title": f"{asset_id.capitalize()} synthetic icon",
            "creator": "MADO test fixture", "local_file": "icon.png",
            "license_spdx": "CC0-1.0",
            "license_evidence_file": "LICENSE.txt",
            "reviewed_by_human": True, "use_case": "game_embedding",
        }), encoding="utf-8")
        submissions.append(f"inputs/{asset_id}/submission.yaml")
    (source_root / "demo.yaml").write_text(yaml.safe_dump({
        "flow_id": "browser-demo", "submissions": submissions,
    }), encoding="utf-8")
    return source_root


@pytest.fixture
def running_cockpit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes = _recipe(tmp_path)
    workspace = tmp_path / "runs"

    def runtime(plan_path, project_dir, *, godot_bin, output_root, timeout):
        folder = Path(output_root) / "browser-demo"
        folder.mkdir(parents=True)
        report = {"status": "passed", "godot_version": "4.6.1.synthetic"}
        write_json(folder / "report.json", report)
        return report, folder

    def gallery(plan_path, project_dir, *, godot_bin, output_root, timeout, virtual_display):
        plan_path = Path(plan_path)
        project_dir = Path(project_dir)
        folder = Path(output_root) / "browser-demo"
        folder.mkdir(parents=True)
        preview = Image.new("RGB", (960, 540), (16, 30, 42))
        draw = ImageDraw.Draw(preview)
        draw.rectangle((60, 80, 380, 380), fill=(45, 70, 88))
        draw.ellipse((100, 100, 340, 340), fill=(245, 125, 75))
        draw.rectangle((520, 80, 860, 380), fill=(45, 70, 88))
        draw.ellipse((570, 120, 815, 365), fill=(90, 201, 148))
        preview.save(folder / "gallery.png")
        (folder / "CREDITS.md").write_bytes((project_dir / "CREDITS.md").read_bytes())
        plan = BridgePlan.model_validate(_read_object(plan_path))
        manifest = _read_object(project_dir / "asset_manifest.json")
        report = {
            "status": "captured", "project_id": plan.project_id,
            "screenshot_sha256": _sha256(folder / "gallery.png"),
            "credits_sha256": _sha256(folder / "CREDITS.md"),
            "manifest_sha256": _sha256(project_dir / "asset_manifest.json"),
            "assets": _evidence_entries(plan, plan_path, manifest),
        }
        write_json(folder / "report.json", report)
        return report, folder

    monkeypatch.setattr(flow, "verify_godot_import", runtime)
    monkeypatch.setattr(flow, "render_gallery", gallery)

    app = create_app(workspace, recipes=recipes, godot_bin="fixture-godot")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", access_log=False
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        if not thread.is_alive():
            raise RuntimeError("Uvicorn browser test server exited unexpectedly")
        time.sleep(0.05)
    assert server.started, "Local Cockpit did not start"
    try:
        yield f"http://127.0.0.1:{port}", workspace
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            yield browser
        finally:
            browser.close()


def _page(browser, size: str):
    width, height = BASELINE[size]["viewport"]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=1, reduced_motion="reduce", locale="ja-JP",
    )
    page = context.new_page()
    page.set_default_timeout(15000)
    page.on("dialog", lambda dialog: dialog.accept())
    return context, page


def _ready(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    expect(page.locator("#runTotal")).to_have_text("0")
    expect(page.locator("#recipeSelect option")).to_have_count(2)
    page.locator("#recipeSelect").select_option("demo.yaml")


def _assert_layout(page: Page, size: str, *, stage: str) -> dict:
    expected = BASELINE[size]
    actual = page.evaluate("""() => {
        const box = selector => document.querySelector(selector).getBoundingClientRect();
        const columns = selector => getComputedStyle(document.querySelector(selector))
            .gridTemplateColumns.trim().split(/\\s+/).length;
        return {
            viewport: [window.innerWidth, window.innerHeight],
            documentWidth: document.documentElement.scrollWidth,
            heroHeight: Math.round(box('.hero').height),
            sidebarWidth: Math.round(box('.sidebar').width),
            sidebarPosition: getComputedStyle(document.querySelector('.sidebar')).position,
            kpiColumns: columns('.kpis'),
            inspectionColumns: document.querySelector("#detailArea").hidden ? 0 : columns('.inspection-grid'),
            heroVisible: box('.hero').width > 0 && box('.hero').height > 0,
            reviewPanelWidth: Math.round(box('.review-workspace').width),
            assetPanelWidth: Math.round(box('.asset-panel').width)
        };
    }""")
    assert actual["viewport"] == expected["viewport"]
    assert actual["documentWidth"] <= expected["viewport"][0] + expected["maxHorizontalOverflow"]
    assert expected["heroHeight"][0] <= actual["heroHeight"] <= expected["heroHeight"][1]
    assert expected["sidebarWidth"][0] <= actual["sidebarWidth"] <= expected["sidebarWidth"][1]
    assert actual["sidebarPosition"] == expected["sidebarPosition"]
    assert actual["kpiColumns"] == expected["kpiColumns"]
    if stage != "empty":
        assert actual["inspectionColumns"] == expected["inspectionColumns"]
    assert actual["heroVisible"]
    assert actual["reviewPanelWidth"] >= expected["minReviewPanelWidth"]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"geometry-{size}-{stage}.json").write_text(
        json.dumps(actual, indent=2) + "\n", encoding="utf-8"
    )
    return actual


def _screenshot(page: Page, name: str) -> bytes:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    data = page.screenshot(
        path=str(ARTIFACTS / f"{name}.png"), animations="disabled", full_page=True
    )
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "PNG"
        assert image.width >= 375 and image.height > 500
        assert max(ImageStat.Stat(image.convert("RGB")).stddev) >= 12, "Blank/monochrome page"
    baseline = "desktop-empty" if name == "desktop-empty-repeat" else name
    compare_golden(baseline, data, destination=ARTIFACTS / "visual-delta" / name)
    return data


def _pixel_stability(first: bytes, second: bytes, *, threshold: float = 0.005) -> None:
    """Compare two independent identical-page captures, not a transient generated baseline."""
    a = Image.open(io.BytesIO(first)).convert("RGB")
    b = Image.open(io.BytesIO(second)).convert("RGB")
    assert a.size == b.size
    changes = ImageChops.difference(a, b).convert("L")
    changed = sum(changes.histogram()[17:])
    changed_fraction = changed / (a.width * a.height)
    assert changed_fraction <= threshold, f"Non-deterministic screenshot pixels: {changed_fraction:.3%}"


def _run(page: Page) -> None:
    page.locator("#launchButton").click()
    expect(page.locator("#jobBox")).to_be_visible()
    expect(page.locator("#jobTitle")).to_have_text("完成！", timeout=30000)
    expect(page.locator("#stageCount")).to_have_text("5 / 5 stages")
    expect(page.locator("#stageList li")).to_have_count(5)
    assert all("DONE" in value for value in page.locator("#stageList li strong").all_text_contents())
    expect(page.locator("#galleryImage")).to_be_visible()
    expect(page.locator(".asset-card")).to_have_count(2)
    expect(page.locator("#reviewButton")).to_be_disabled()


def test_desktop_browser_full_journey(browser, running_cockpit):
    url, workspace = running_cockpit
    context, page = _page(browser, "desktop")
    try:
        _ready(page, url)
        _assert_layout(page, "desktop", stage="empty")
        first = _screenshot(page, "desktop-empty")
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#runTotal")).to_have_text("0")
        page.locator("#recipeSelect").select_option("demo.yaml")
        second = _screenshot(page, "desktop-empty-repeat")
        _pixel_stability(first, second)

        page.locator("#recipeSelect").select_option("demo.yaml")
        _run(page)
        _assert_layout(page, "desktop", stage="gallery")
        _screenshot(page, "desktop-gallery-pending")
        page.locator("#visualReviewer").fill("Human Browser QA")
        page.locator(".asset-card").filter(has_text="Ember synthetic icon").locator("select").select_option("pass")
        page.locator(".asset-card").filter(has_text="Ember synthetic icon").get_by_role("button", name="判定を保存").click()
        expect(page.locator("#visualSummary")).to_contain_text("Pass: 1")
        expect(page.locator("#visualSummary")).to_contain_text("Pending: 1")
        moss = page.locator(".asset-card").filter(has_text="Moss synthetic icon")
        moss.locator("select").select_option("rework")
        moss.locator("textarea").fill("Edges need alignment before approval")
        moss.get_by_role("button", name="判定を保存").click()
        expect(page.locator("#visualSummary")).to_contain_text("Rework: 1")
        expect(page.locator("#reviewButton")).to_be_disabled()
        _screenshot(page, "desktop-rework")
        page.locator("#visualFilter").select_option("rework")
        expect(page.locator(".asset-card")).to_have_count(1)
        page.locator("#visualFilter").select_option("all")
        moss = page.locator(".asset-card").filter(has_text="Moss synthetic icon")
        moss.locator("select").select_option("pass")
        moss.locator("textarea").fill("Checked revised icon edges")
        moss.get_by_role("button", name="判定を保存").click()
        expect(page.locator("#visualSummary")).to_contain_text("Pass: 2")
        expect(page.locator("#reviewButton")).to_be_enabled()
        page.locator("#reviewNotes").fill("I inspected both images, attribution and source license evidence.")
        page.locator("#visualCheck").check()
        page.locator("#creditsCheck").check()
        page.locator("#rightsCheck").check()
        page.locator("#reviewButton").click()
        expect(page.locator("#reviewMessage")).to_contain_text("公開は", timeout=12000)
        expect(page.locator("#reviewEvidence")).to_have_text("✓ PASSED")
        expect(page.locator("#reviewButton")).to_be_disabled()
        _screenshot(page, "desktop-reviewed")
        sheet = workspace / "browser-demo" / "review" / "visual-decisions.json"
        signed = workspace / "browser-demo" / "review" / "human-attestation.json"
        assert signed.is_file() and sheet.is_file()
        assert _read_object(signed)["visual_review_sha256"] == _sha256(sheet)
        assert _read_object(workspace / "browser-demo" / "review" / "release-check.json")["publication_approved"] is False
    finally:
        context.close()


def test_mobile_responsive_and_review_filter(browser, running_cockpit):
    url, workspace = running_cockpit
    context, page = _page(browser, "mobile")
    try:
        _ready(page, url)
        _assert_layout(page, "mobile", stage="empty")
        _screenshot(page, "mobile-empty")
        _run(page)
        _assert_layout(page, "mobile", stage="gallery")
        _screenshot(page, "mobile-gallery-pending")
        page.locator("#visualFilter").select_option("pending")
        expect(page.locator(".asset-card")).to_have_count(2)
        page.locator("#visualFilter").select_option("reject")
        expect(page.locator(".asset-card")).to_have_count(0)
        page.locator("#visualFilter").select_option("all")
        page.locator("#visualReviewer").fill("Mobile Tester")
        first = page.locator(".asset-card").first
        first.locator("select").select_option("reject")
        first.locator("textarea").fill("The small crop looks blurry")
        first.get_by_role("button", name="判定を保存").click()
        expect(page.locator("#visualSummary")).to_contain_text("Reject: 1")
        expect(page.locator("#reviewButton")).to_be_disabled()
        _assert_layout(page, "mobile", stage="rejected")
        _screenshot(page, "mobile-rejected")
    finally:
        context.close()
