# MAF-M1.7.2a Real ComfyUI Bake-off / Manga Visual Evidence

## Scope

This is a **real-workstation execution bridge** for MAF-M1.7.2. It submits operator-reviewed **ComfyUI Save (API Format)** workflows to a localhost-only ComfyUI server and records actual returned PNG files and hashes. The bridge itself does **not** install ComfyUI, download weights, fetch LoRAs, execute live GPU work in CI, issue a release decision, or supersede the existing MAF ImageProvider, license and curation gates.

The CI fake-server test validates transport and evidence plumbing, **not image quality or GPU availability**.

**Source references**:
- [OpenMOSS/MOSS-Image official ComfyUI README](https://github.com/OpenMOSS/MOSS-Image/blob/main/comfyui/README.md)
- [Official API workflow](https://github.com/OpenMOSS/MOSS-Image/blob/main/comfyui/moss-image/example_workflows/moss-image-api.json)
- [ComfyUI server API routes](https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx)

## Windows operator setup

1. Start an existing **trusted** ComfyUI server listening on `127.0.0.1:8188`. Confirm `http://127.0.0.1:8188/system_stats` works. Do not expose it to the LAN, and do not run foreign node code without review.
2. Install the official local MOSS custom nodes via approved manual installation. Download the **MOSS-Image-Base** and **MOSS-Image-SFT** model directories yourself, review their licenses and keep their checkpoint identity (SHA-256/version/commit) in your run notes. The official loader expects `transformer/`, `text_encoder/`, `tokenizer/`, and `vae/` beneath each local model directory.
3. Download the upstream `moss-image-api.json` example from the link above, then create separate reviewed API workflows for Base and SFT. For SFT+LoRA, insert a connected built-in `LoraLoader` with approved compatible weights into the sampler's **MODEL** path, save **API Format**, and record LoRA SHA-256, strength, ownership/consent and licensing. LoRA presence is checked structurally; human review must still verify it was active. If no compatible LoRA exists, **stop and record blocked** rather than pretending it ran.
4. Create a separate native API-format Anima workflow, using its actual nodes, sampler and model files. Note that the Anima settings may differ. Never force MOSS-specific sampler settings onto it without confirming compatibility.
5. Copy `fixtures/moss-comfy-bakeoff.example.json` to a folder outside Git along with all four API workflows. Set each `arms.*.workflow` relative to the config file, adjust `bindings` and `save_node` to actual node IDs, and set only known scalar `overrides`. The example Anima binding IDs are placeholders and **must** be adapted. Use forward slashes in Windows paths (e.g. `C:/models/MOSS-Image-Base`).
6. Activate MAF's Python 3.11+ environment and install project dependencies. The workflow runner uses Python stdlib for HTTP and Pillow for PNG verification.

## Commands (run from repository checkout)

```powershell
python -m mado_asset_foundry.comfy_manga_bakeoff preflight C:/maf-private/bakeoff/config.json
python -m mado_asset_foundry.comfy_manga_bakeoff run C:/maf-private/bakeoff/config.json --output runs/moss-comfy-001 --url http://127.0.0.1:8188 --timeout 1200 --live
python -m mado_asset_foundry.comfy_manga_bakeoff gallery runs/moss-comfy-001/report.json --output runs/moss-comfy-001/gallery.html
python -m mado_asset_foundry.comfy_manga_bakeoff scorecard runs/moss-comfy-001/report.json --output runs/moss-comfy-001/scorecard.json
# Human reviewer fills reviewer, per-image scores and N/A explanations in scorecard.json
python -m mado_asset_foundry.comfy_manga_bakeoff validate-review runs/moss-comfy-001/report.json runs/moss-comfy-001/scorecard.json
```

No `--live` means no queue submission. Live runs refuse to overwrite existing folders. They intentionally run **sequentially** to reduce VRAM contention. Current CLI does **not** interrupt previously submitted prompts on timeout. After a timeout, inspect the ComfyUI queue/history manually before starting another run.

## Evidence and methodology

The runner enforces all four arms per case and refuses to call ComfyUI when the plan is invalid. Before queueing, it checks `/object_info` for every workflow node class and stores `/system_stats`. Each job uses `POST /prompt`, polls `GET /history/{prompt_id}`, then fetches the unique saved `output` image via `GET /view`. It rejects missing/extra outputs, image format or dimension mismatches, and non-local endpoints. No automatic remote access, external image URLs or silent retry.

`report.json` stores the input config SHA-256, individual source workflow SHA-256, patched workflow SHA-256, prompt ID, elapsed submission-to-output duration, **sampled aggregate GPU memory-used values if NVIDIA-SMI exists**, PNG SHA-256, and case/model IDs. Sampled memory is **not precise peak VRAM for the job** and may include other GPU processes. The runner never claims image-quality success based on a zero process exit code.

`gallery.html` is an offline, no-CDN four-arm image comparison. All referenced PNG hashes are verified before rendering. It is **not an automatic aesthetic, text accuracy or copyright assessment**. The SHA-bound `scorecard.json` requires a named human reviewer, 1–5 values or explained N/A for every sample, and tamper-free source PNGs. A successful `validate-review` records only that review data was supplied; it does not grant quality, rights or release approval.

Use the following blinded human review scores, 1..5 for each image (or N/A with explicit reason):
- Japanese title and glyph exactness, including vertical order
- Panel reading order and frame layout adherence
- Character identity across frames
- Artifact severity, readability and overall usability
- bbox placement fidelity (when spatial layout was used)
- LoRA benefit relative to SFT at the same prompt and seed

**Never promote based only on matched seed:** sampler/model internals differ between Anima and MOSS, so a shared seed is an experimental identifier, not evidence of pixel-identical noise. Quantitative repeatability also needs additional seeds and controlled software/hardware provenance. Record exact ComfyUI and custom-node git SHAs, model weight hashes, LoRA strength, GPU, drivers, temperature/VRAM and settings separately in an operator ledger.

## Quality gates

- **Infrastructure green:** CI synthetic API mocks pass; live server can resolve the installed nodes.
- **Capture complete:** required four-arm case outputs each have verified image dimensions and SHA-256, with no failed/partial job.
- **Visual assessment pending:** human scores have not yet been recorded in this code stage.
- **Promotion blocked:** never equate this benchmark with game-ready, licensed, or redistributable assets. Continue existing MAF human review/license/Godot evidence gates.

## Isolation and maintenance

Use the existing ignored `runs/` directory for generated data, prompts and images, and keep operator paths/private rights evidence outside Git. Workflows are a user-authorized execution boundary and may call arbitrary local custom nodes: never accept an untrusted workflow or custom node installation.

The M1.7.2a branch stacks on M1.7.2 PR #22 so upstream changes remain reviewable separately. Merge #22 first, then rebase/retarget this PR onto main.
