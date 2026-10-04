# MAF-M0.8.2f TripoSR Local Adapter / 1-Asset Probe

## Goal

Execute exactly one local image through an explicitly provided local TripoSR checkout and local model directory, while preserving enough evidence to audit or reproduce the probe.

## Pinned upstream

```text
VAST-AI-Research/TripoSR
107cefdc244c39106fa830359024f6a2f1c78871
```

The pinned upstream `run.py` supports image input, output directory, a pretrained-model path/ID, OBJ or GLB output, marching-cubes resolution, foreground ratio, and optional texture baking.

Its model loader calls Hugging Face when the pretrained-model argument is not a local directory. MAF therefore requires and passes a local model directory.

## Command

```powershell
maf skill probe triposr-snapshot \
  --input .\asset.png \
  --source-root C:\Tools\TripoSR \
  --model-path C:\Models\TripoSR \
  --python-bin C:\Tools\TripoSR\.venv\Scripts\python.exe \
  --format glb
```

Exactly one image is accepted.

## Local-only guard

MAF requires:

```text
<source-root>/run.py
<source-root>/tsr/system.py
<source-root>/requirements.txt
<model-path>/config.yaml
<model-path>/model.ckpt
```

and always passes:

```text
--pretrained-model-name-or-path <local model-path>
```

MAF does not clone repositories, install dependencies, download weights, or authenticate.

## Source pinning

By default the local Git checkout must resolve to the pinned commit. An explicit `--allow-unpinned-source` exists for experimentation and is recorded in evidence.

## Output validation

Default output is GLB with vertex colors. Texture baking follows the upstream xatlas path and MAF currently restricts that mode to OBJ.

A successful GLB must contain a GLB v2 header. A successful OBJ must contain vertex and face records. Exit code 0 without a valid non-empty mesh is failure.

## Evidence

```text
runs/skill-probes/<run-id>/
  0/
    mesh.glb
  evidence/
    job.json
    stdout.log
    stderr.log
    result.json
```

Evidence includes input SHA-256, expected/observed source ref, run.py SHA-256, model config SHA-256, model checkpoint byte size, exact command, stdout/stderr, output SHA-256, output size, and final status.

## Transparent inputs

The pinned upstream TripoSR `remove_background` helper detects RGBA input with real transparency and skips rembg. MAF keeps this upstream preprocessing path enabled so transparent MAF assets stay transparent through preprocessing.

## Test boundary

Tests use synthetic local source/model fixtures and fake subprocess runners. They never execute TripoSR, download weights, or access the network.
