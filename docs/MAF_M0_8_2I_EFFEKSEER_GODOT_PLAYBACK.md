# MAF-M0.8.2i Effekseer Godot Runtime Dogfood / Playback Evidence

## Goal

Promote the Godot-side Effekseer candidate from metadata-only capability evidence to one real runtime playback path.

```text
M0.8.2h effect.efkefc + effect.efk
        |
        v
official EffekseerForGodot4 1.80.7 release
        |
        v
Godot importer -> EffekseerEffect
        |
        v
EffekseerEmitter3D.play()
        |
        v
is_playing() == true
        |
        v
runtime-report.json + command logs + hashes
```

## Version boundary

The effect authoring bridge is verified against Effekseer 1.80.6.

The official EffekseerForGodot4 releases do not include 1.80.6. The release sequence around that point is 1.80.5.1 -> 1.80.7.

M0.8.2i therefore makes the cross-patch probe explicit rather than silently claiming matching versions:

```text
authoring target: 1.80.6
Godot plugin:     1.80.7
plugin tag/ref:   1.80.7 / 8706d2917c2487efac3a4943c16a10dfcfc5b127
```

## Plugin provenance

Required official release asset:

```text
EffekseerForGodot4-180_7.zip
SHA-256:
581e02b4ad773df39674c6c5d57bc6c132adf6fe38ae60a75bf230f251d56fef
```

The archive is verified before Godot is executed. Extraction rejects absolute paths and path traversal.

Required addon files include:

```text
addons/effekseer/plugin.cfg
addons/effekseer/effekseer.gdextension
addons/effekseer/bin/windows/libeffekseer.x86_64.dll
```

## Import boundary

The official `EffekseerEffectImportPlugin.gd` recognizes `.efkefc`.

Therefore the M0.8.2h pair is used as follows:

```text
effect.efkefc -> actual Godot import/playback input
effect.efk    -> preserved runtime-export evidence/hash
```

MAF does not falsely report the `.efk` as the imported source.

## Runtime acceptance

The generated playback scene uses runtime reflection so the GDScript parser does not assume the extension is available before Godot loads it.

Acceptance requires:

1. Godot version 4.2+
2. `ClassDB.class_exists("EffekseerEmitter3D")`
3. `load("res://effects/effect.efkefc")` succeeds
4. the loaded class is `EffekseerEffect`
5. an `EffekseerEmitter3D` instance is created
6. the effect is assigned
7. `play()` is called
8. after runtime frames, `is_playing()` is true

## Evidence

```text
runs/vfx-godot-playback/<run-id>/
  project.godot
  playback.tscn
  playback.gd
  effects/
    effect.efkefc
    effect.efk
  addons/
    effekseer/
      ...
  evidence/
    job.json
    result.json
    runtime-report.json
    steps/
      version.json
      version.stdout.log
      version.stderr.log
      import.json
      import.stdout.log
      import.stderr.log
      playback.json
      playback.stdout.log
      playback.stderr.log
```

## Command

```powershell
python -m mado_asset_foundry.cli skill vfx-godot-dogfood `
  .\runs\vfx-effect-probes\<effect-run> `
  --plugin-archive C:\Tools\EffekseerForGodot4-180_7.zip `
  --godot-bin C:\path\to\godot.exe
```

## Scope boundary

This milestone proves that the official runtime can import the generated effect source and start playback.

It does not claim that the structural probe is visually useful or attractive. Visual VFX recipe authoring and rendered-frame QA remain a later milestone.
