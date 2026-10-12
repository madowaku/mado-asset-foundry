# MAF-M1.7 Composition-to-Style Foundry / Anima ComfyUI Bridge

Initial integration provides a **filesystem-first, explicit img2img pilot** (1-4 seeds), offline compile, and opt-in local ComfyUI queueing. It does **not** assume any particular Anima custom node or sampler graph.

## Setup

1. Install ComfyUI and the Anima model **separately** following upstream guidance. No downloads, third-party execution, or model license acceptance happen in MAF.
2. In ComfyUI build a *working* Anima img2img workflow. Export **API-format JSON** (not the editor UI graph).
3. Identify the LoadImage node ID with its `image` input and a sampler node ID with `seed` and `denoise` inputs. Include a SaveImage node. Only those fields are patched; all other model-specific settings stay exactly as exported.
4. Save a PNG composition image, e.g. from ChatGPT.

## Preflight, no network

```bash
python -m mado_asset_foundry.composition_style \
  compositions/scene.png workflows/anima-img2img-api.json \
  runs/composition-style/scene-001 --image-node 12 --sampler-node 27 \
  --model-id 'Anima (local checkpoint/version)' \
  --license-review 'Manual review required before game use' \
  --denoise 0.35 --seeds 11,22,33
```

Inspect `evidence.json` and each `workflows/seed-*.json`; no image is generated offline. IDs 12/27 are **examples**, not guaranteed node IDs.

## Opt-in execution

Run the same command with `--live --server http://127.0.0.1:8188`. This uploads the source PNG and queues each graph to loopback ComfyUI. Evidence records acknowledged `prompt_id` values, **not render success**. Use ComfyUI history/UI to obtain finished images, then conduct visual review, model-use/license checks and existing MAF QA before asset packaging. M1.7 deliberately does not automatically promote or publish outputs.

## Safeguards and known limits

- Source and workflow are snapshotted; source hash, workflow hash, model provenance note, node settings, seed and per-graph hash are saved.
- No overwrite, no automatic model download, no model execution during tests, no image generation in dry mode.
- Only plain HTTP loopback ComfyUI endpoint is permitted. Use the trusted local ComfyUI instance; it may have third-party nodes with arbitrary execution.
- Denoise is model/workflow dependent; 0.35 is a starting point, **not** a guaranteed composition-preservation score.
- The first increment covers *queue and audit*, not result download, pose preservation metrics, inpainting masks, gallery review, or asset-release promotion. Those need their own evidence and human gates.
- Anima weights and output rights must be assessed separately for specific versions, intended commercial use and distribution type. Recording notes is not legal clearance.
