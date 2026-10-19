# MAF-M1.7.2 MOSS-Image Layout & Manga LoRA Bake-off

## Status and scope
Offline adapter/benchmark scaffold, not a completed GPU bake-off. Existing MAF ImageProvider, Anima (if added on another branch), curation, license and human review gates remain untouched. There is NO automatic download, model/plugin installation, GPU inference, LoRA training, third-party code execution, or publication.

Upstream: https://github.com/OpenMOSS/MOSS-Image (verify model-weight and LoRA licenses independently before use). Official MOSS layout format has `summary`, `items`, `bbox_coord_space: abs_centralized`, and `bbox_format: yxyx`. All boxes use **pixel positions relative to canvas center**, not normalized coordinates. Japanese vertical writing and comic panel control are experimental quality hypotheses, not upstream guarantees.

## Protocol

Four arms: `moss-base`, `moss-sft`, `moss-sft-lora`, `anima`. Use identical prompt intent, canvas, seeds (where engines support it), step budget and fixed hardware. Record any settings that cannot be standardized in an operator-owned ledger. For LoRA, record identifier, source, license, base-model compatibility, weights hash, strength and training consent. Do not redistribute weights in this repository.

Cases: (1) Japanese vertical headline/text accuracy; (2) 4-panel comic reading order and border consistency; (3) character identity across 3 panels; (4) object/text bbox adherence; (5) freeform style/picture quality baseline. Evaluate text exactness, spatial IoU, character identity, legibility, artifact rate, runtime and peak VRAM. Use human-blinded side-by-side assessment with explicit scores and reviewer evidence. OCR/embedding-based metrics are supplementary and must not be presented as a human quality verdict.

**Pass gates:** all four arms represented for each required case, valid provenance/hash evidence, human scorecards, no missing license or consent evidence, and no regression of MAF downstream gates. For metrics where the test is inapplicable, record N/A with rationale; never silently count N/A as pass. No production promotion on synthetic fixtures alone.

## Layout

```bash
python -m mado_asset_foundry.moss_bakeoff layout fixtures/moss-layout-example.json > layout.json
```

`bbox_xyxy` is [left, top, right, bottom] in canvas pixels. The compiler converts to upstream `[y_min, x_min, y_max, x_max]`, preserving Japanese text via UTF-8 and `ensure_ascii=False`. Copy JSON to MOSS positive prompt and set the same dimensions in ComfyUI; the core MAF pipeline remains unchanged.

## Offline evidence

```bash
python -m mado_asset_foundry.moss_bakeoff evidence manifest.json --root /path/to/operator/outputs > review.json
```

Manifest shape: `{"cases":[{"id":"ja-text","seed":42,"width":1024,"height":1024,"samples":[{"model":"moss-base","path":"base.png"}]}]}`. Paths are relative to the explicitly supplied output root. PNGs are checked for correct size and hashed. No subjective quality claims are made. Full paired completion requires all four models for each case. Output is JSON printed to stdout so the operator can persist it outside Git. Review and legal approval are **always false** in this stage. Keep outputs, LoRA and generated images under local ignored paths rather than committing to Git.

## Next step for real bake-off
Explicitly provision a locally licensed MOSS checkpoint, ComfyUI workflow, Anima comparison pipeline and compatible LoRA; record actual inference settings and device/VRAM measurements. This scaffold intentionally does not pretend those GPU experiments were run.
