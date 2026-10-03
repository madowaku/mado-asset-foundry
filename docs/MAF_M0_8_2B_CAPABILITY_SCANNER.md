# MAF-M0.8.2b Capability Scanner

## Goal

Upgrade structural Skill intake into deterministic, evidence-backed classification without executing third-party code.

## Command

```bash
maf skill scan <local-skill-directory>
```

Default outputs:

```text
skills/manifests/<skill-id>.json
evidence/skill-scan/<skill-id>/report.json
```

If a structural intake manifest already exists at the same path, scanning requires `--force` to replace it.

## Capability contract

M0.8.2b reads only:

- SKILL.md
- README

for capability classification.

It does not scan executable script bodies for capability terms. A script named or commented with "sprite sheet" cannot create a capability by itself.

Initial taxonomy includes:

```text
background_remove
alpha_cleanup
trim_transparent_margin
padding_normalize
pixel_cleanup
palette_reduce
palette_lock
despeckle
grid_recover
frame_extract
frame_align
sprite_sheet_pack
animation_preview_gif
godot_export
unity_export
visual_qa
```

Every match stores:

- normalized capability
- confidence
- source file
- exact matched term

## Runtime discovery

Runtime evidence may come from:

- pyproject.toml
- requirements.txt
- environment.yml
- package.json
- script filename extensions
- explicit ffmpeg references
- explicit onnxruntime references
- ONNX model files

Supported normalized runtime names initially:

```text
python
node
ffmpeg
onnx_runtime
```

Detection never imports a Python module, launches a subprocess, installs a package, or executes external scripts.

## License discovery

M0.8.2b performs conservative text matching for:

- MIT
- Apache-2.0
- BSD-3-Clause
- GPL-3.0
- MPL-2.0

No confident match remains:

```text
status: unknown
spdx: null
```

Multiple matches remain:

```text
status: ambiguous
spdx: null
```

This classification is metadata evidence, not legal advice or redistribution permission.

## Synthetic fixture expectation

`sample-background-remover` should classify as:

```text
capabilities:
  background_remove
  alpha_cleanup

runtime:
  python
  onnx_runtime

license:
  MIT

adapter:
  intake_only
```

M0.8.2b does not make the Skill executable. Adapter execution begins in later M0.8.2 milestones.
