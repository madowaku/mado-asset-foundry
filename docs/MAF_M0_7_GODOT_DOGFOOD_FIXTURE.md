# MAF-M0.7 Godot Dogfood Fixture

## Goal

Prove that the actual files produced by M0.5 can be imported and used in a Godot project.

The fixture consumes the compiled product's `assets/` directory. It does not bypass the product by reading MAF's internal `refined/` files.

## Why this matters

A PNG can pass filesystem QA and still fail the real consumer path because of packaging mistakes, path errors, import failures, or unexpected dimensions.

M0.7 adds a downstream game-engine gate:

```text
Product Compiler
      ↓
packaged assets/*.png
      ↓
Godot fixture
      ↓
Godot import
      ↓
Texture2D resource load
      ↓
dimension verification
      ↓
visual gallery
```

Godot imports supported images placed in the project folder as resources. The official CLI also provides `--import`, which waits for resources to import and exits. A command-line script can extend `SceneTree` and run with `--script`.

## Command

Generate the fixture without requiring Godot:

```bash
maf godot-fixture runs/<run-id>
```

If Godot is installed:

```bash
maf godot-fixture runs/<run-id> --force --godot-bin godot
```

On Windows, `--godot-bin` can also point directly to the Godot executable.

## Output

```text
runs/<run-id>/
  godot/
    report.json
    forest-alchemy-icons-0.1.0/
      project.godot
      icon_gallery.tscn
      icon_gallery.gd
      verify.gd
      asset_manifest.json
      assets/
      evidence/
        godot-import.log
        godot-verify.log
        import-report.json
        gallery.png          # after pressing F12 in the running gallery
```

## Pixel-art handling

The gallery sets `CanvasItem.TEXTURE_FILTER_NEAREST` on each TextureRect. Godot documents nearest filtering as the mode that reads the nearest pixel, suitable for a crisp pixel-art look. Godot's image import documentation also recommends lossless compression for pixel art.

## Runtime verifier

`verify.gd`:

- extends `SceneTree`
- loads every packaged PNG through Godot's resource loader
- requires every resource to be a `Texture2D`
- checks the expected width and height
- writes `evidence/import-report.json`
- exits non-zero on any failure

## Visual evidence

Run the main scene in Godot. The generated gallery displays every packaged icon in a grid.

Press F12 to save:

```text
evidence/gallery.png
```

## Acceptance criteria

- fixture consumes packaged product assets
- packaged SHA-256 is verified before copying
- all fixture assets are exact recipe dimensions
- generated Godot project has a runnable icon gallery
- nearest-neighbor filtering is explicit
- headless import can be invoked from the MAF command
- runtime verifier checks all textures through Godot ResourceLoader
- verifier evidence is saved
- visual gallery screenshot can be captured from Godot
- existing fixture is not overwritten without `--force`
