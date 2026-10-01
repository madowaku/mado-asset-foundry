from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .io import load_recipe, write_json
from .models import GodotFixtureReport, ProductCompileReport


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_packaging_report(run_dir: Path) -> ProductCompileReport:
    path = run_dir / "packaging" / "report.json"
    if not path.exists():
        raise FileNotFoundError("packaging/report.json is missing; run maf package first")
    return ProductCompileReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _resolve_report_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    if path.exists():
        return path
    candidate = run_dir / path
    if candidate.exists():
        return candidate
    return path


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content.rstrip() + "\n")


def _resolve_godot_binary(value: str) -> str:
    direct = Path(value)
    if direct.exists():
        return str(direct.resolve())
    located = shutil.which(value)
    if located:
        return located
    raise FileNotFoundError(f"Godot executable not found: {value}")


def _run_command(args: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def build_godot_fixture(
    run_dir: str | Path,
    *,
    force: bool = False,
    godot_bin: str | None = None,
) -> GodotFixtureReport:
    directory = Path(run_dir)
    recipe = load_recipe(directory / "recipe.yaml")
    if recipe.product is None:
        raise ValueError("recipe.product is required")

    product = recipe.product
    package_report = _load_packaging_report(directory)
    if package_report.product_id != product.product_id or package_report.version != product.version:
        raise ValueError("packaging report product does not match recipe product")

    package_dir = _resolve_report_path(directory, package_report.product_dir)
    if not package_dir.exists():
        raise FileNotFoundError("compiled product directory is missing")

    product_manifest_path = package_dir / "MANIFEST.json"
    if not product_manifest_path.exists():
        raise FileNotFoundError("compiled product MANIFEST.json is missing")
    product_manifest = json.loads(product_manifest_path.read_text(encoding="utf-8"))

    asset_entries = product_manifest.get("assets", [])
    if not isinstance(asset_entries, list) or not asset_entries:
        raise ValueError("compiled product manifest has no assets")
    expected_size = (recipe.output.width, recipe.output.height)

    bundle_name = f"{product.product_id}-{product.version}"
    fixture_parent = directory / "godot"
    fixture_dir = fixture_parent / bundle_name
    temp_dir = fixture_parent / f".{bundle_name}.tmp"

    if fixture_dir.exists() and not force:
        raise FileExistsError("Godot fixture already exists; use --force to replace it")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    assets_dir = temp_dir / "assets"
    evidence_dir = temp_dir / "evidence"
    assets_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)

    fixture_assets: list[dict[str, object]] = []
    try:
        for entry in asset_entries:
            if not isinstance(entry, dict):
                raise ValueError("compiled product manifest contains an invalid asset entry")
            relative_name = str(entry.get("filename", ""))
            source = package_dir / relative_name
            if not source.exists():
                raise FileNotFoundError(f"packaged asset is missing: {relative_name}")

            digest = _sha256(source)
            if digest != entry.get("sha256"):
                raise ValueError(f"packaged asset SHA-256 mismatch: {relative_name}")

            with Image.open(source) as opened:
                if opened.format != "PNG":
                    raise ValueError(f"packaged asset is not PNG: {relative_name}")
                if opened.size != expected_size:
                    raise ValueError(
                        f"packaged asset has wrong dimensions: {relative_name} {opened.size} != {expected_size}"
                    )

            filename = Path(relative_name).name
            destination = assets_dir / filename
            shutil.copyfile(source, destination)
            fixture_assets.append(
                {
                    "asset_id": entry.get("asset_id"),
                    "subject": entry.get("subject"),
                    "filename": filename,
                    "sha256": digest,
                }
            )

        fixture_manifest = {
            "schema_version": "0.1",
            "source_run": package_report.run_id,
            "source_product": f"{product.product_id}@{product.version}",
            "expected_width": expected_size[0],
            "expected_height": expected_size[1],
            "columns": min(8, len(fixture_assets)),
            "asset_count": len(fixture_assets),
            "assets": fixture_assets,
        }
        write_json(temp_dir / "asset_manifest.json", fixture_manifest)

        project_godot = """; Generated by MADO Asset Foundry MAF-M0.7
config_version=5

[application]

config/name="MADO Asset Foundry Dogfood"
run/main_scene="res://icon_gallery.tscn"

[display]

window/size/viewport_width=960
window/size/viewport_height=540
window/size/window_width_override=960
window/size/window_height_override=540
window/stretch/mode="canvas_items"

[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
textures/canvas_textures/default_texture_filter=0
"""
        _write_text(temp_dir / "project.godot", project_godot)

        scene = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://icon_gallery.gd" id="1_gallery"]

[node name="IconGallery" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1_gallery")
"""
        _write_text(temp_dir / "icon_gallery.tscn", scene)

        gallery_script = """extends Control

const MANIFEST_PATH := "res://asset_manifest.json"

func _ready() -> void:
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST_PATH))
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid asset_manifest.json")
        return

    var assets: Array = parsed.get("assets", [])
    var root_box := VBoxContainer.new()
    root_box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root_box.add_theme_constant_override("separation", 10)
    add_child(root_box)

    var title := Label.new()
    title.text = "MADO Asset Foundry · Godot Dogfood · %d assets" % assets.size()
    root_box.add_child(title)

    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    root_box.add_child(scroll)

    var grid := GridContainer.new()
    grid.columns = int(parsed.get("columns", 8))
    grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    grid.add_theme_constant_override("h_separation", 8)
    grid.add_theme_constant_override("v_separation", 8)
    scroll.add_child(grid)

    var loaded_count := 0
    for entry in assets:
        var filename := str(entry.get("filename", ""))
        var texture := load("res://assets/" + filename) as Texture2D
        var card := VBoxContainer.new()
        card.custom_minimum_size = Vector2(108, 124)

        var icon := TextureRect.new()
        icon.custom_minimum_size = Vector2(96, 96)
        icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
        icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
        icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
        icon.texture = texture
        card.add_child(icon)

        var label := Label.new()
        label.text = str(entry.get("asset_id", filename))
        label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        label.clip_text = true
        card.add_child(label)
        grid.add_child(card)

        if texture != null:
            loaded_count += 1

    var footer := Label.new()
    footer.text = "%d / %d textures loaded · F12 saves evidence/gallery.png" % [loaded_count, assets.size()]
    root_box.add_child(footer)


func _unhandled_key_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and event.keycode == KEY_F12:
        await RenderingServer.frame_post_draw
        DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://evidence"))
        var image := get_viewport().get_texture().get_image()
        var error := image.save_png("res://evidence/gallery.png")
        if error == OK:
            print("Saved res://evidence/gallery.png")
        else:
            push_error("Failed to save gallery screenshot: %s" % error)
"""
        _write_text(temp_dir / "icon_gallery.gd", gallery_script)

        verifier_script = """extends SceneTree

const MANIFEST_PATH := "res://asset_manifest.json"
const REPORT_PATH := "res://evidence/import-report.json"

func _init() -> void:
    var report := {
        "status": "passed",
        "asset_count": 0,
        "loaded_count": 0,
        "errors": []
    }

    var parsed = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST_PATH))
    if typeof(parsed) != TYPE_DICTIONARY:
        report["status"] = "failed"
        report["errors"].append("invalid_manifest")
        _finish(report, 1)
        return

    var expected_width := int(parsed.get("expected_width", 0))
    var expected_height := int(parsed.get("expected_height", 0))
    var assets: Array = parsed.get("assets", [])
    report["asset_count"] = assets.size()

    for entry in assets:
        var filename := str(entry.get("filename", ""))
        var resource_path := "res://assets/" + filename
        var texture := load(resource_path) as Texture2D
        if texture == null:
            report["errors"].append("load_failed:" + filename)
            continue
        if texture.get_width() != expected_width or texture.get_height() != expected_height:
            report["errors"].append(
                "size_mismatch:%s:%dx%d" % [filename, texture.get_width(), texture.get_height()]
            )
            continue
        report["loaded_count"] += 1

    if report["errors"].size() > 0 or report["loaded_count"] != report["asset_count"]:
        report["status"] = "failed"
        _finish(report, 1)
        return

    _finish(report, 0)


func _finish(report: Dictionary, exit_code: int) -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://evidence"))
    var file := FileAccess.open(REPORT_PATH, FileAccess.WRITE)
    if file != null:
        file.store_string(JSON.stringify(report, "\t"))
        file.close()
    print(JSON.stringify(report))
    quit(exit_code)
"""
        _write_text(temp_dir / "verify.gd", verifier_script)

        fixture_readme = f"""# Godot Dogfood Fixture

Source product: {product.product_id}@{product.version}
Assets: {len(fixture_assets)}
Expected texture size: {expected_size[0]}x{expected_size[1]}

## Open visually

Open this folder in Godot 4.x and run the main scene.

Press F12 while the gallery is running to save:

`res://evidence/gallery.png`

## Headless verification

```
godot --headless --path . --import
godot --headless --path . --script res://verify.gd
```

The verifier writes `evidence/import-report.json`.

This fixture consumes the files from the compiled product package, not MAF's internal refined directory.
"""
        _write_text(temp_dir / "README.md", fixture_readme)

        verification_status = "not_run"
        godot_binary: str | None = None
        godot_version: str | None = None

        if godot_bin is not None:
            godot_binary = _resolve_godot_binary(godot_bin)
            version_result = _run_command([godot_binary, "--version"], cwd=temp_dir, timeout=30)
            godot_version = (version_result.stdout or version_result.stderr).strip().splitlines()[0] if (
                version_result.stdout or version_result.stderr
            ) else "unknown"

            import_result = _run_command(
                [godot_binary, "--headless", "--path", ".", "--import"],
                cwd=temp_dir,
            )
            _write_text(
                evidence_dir / "godot-import.log",
                f"exit_code={import_result.returncode}\nSTDOUT\n{import_result.stdout}\nSTDERR\n{import_result.stderr}",
            )

            verify_result = _run_command(
                [godot_binary, "--headless", "--path", ".", "--script", "res://verify.gd"],
                cwd=temp_dir,
            )
            _write_text(
                evidence_dir / "godot-verify.log",
                f"exit_code={verify_result.returncode}\nSTDOUT\n{verify_result.stdout}\nSTDERR\n{verify_result.stderr}",
            )
            verification_status = "passed" if import_result.returncode == 0 and verify_result.returncode == 0 else "failed"

        if force and fixture_dir.exists():
            shutil.rmtree(fixture_dir)
        temp_dir.rename(fixture_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    import_report = fixture_dir / "evidence" / "import-report.json"
    gallery_capture = fixture_dir / "evidence" / "gallery.png"
    report = GodotFixtureReport(
        run_id=package_report.run_id,
        recipe_id=package_report.recipe_id,
        product_id=product.product_id,
        version=product.version,
        asset_count=len(fixture_assets),
        fixture_dir=str(fixture_dir),
        project_path=str(fixture_dir / "project.godot"),
        manifest_path=str(fixture_dir / "asset_manifest.json"),
        verification_status=verification_status,
        godot_binary=godot_binary,
        godot_version=godot_version,
        import_report_path=str(import_report) if import_report.exists() else None,
        gallery_capture_path=str(gallery_capture) if gallery_capture.exists() else None,
    )
    write_json(fixture_parent / "report.json", report.model_dump(mode="json"))
    return report
