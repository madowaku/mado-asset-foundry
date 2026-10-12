# MAF-M1.7.1 Anima Output Intake / Composition Fidelity QA

This milestone extends MAF-M1.7's operator-supplied **Anima + ComfyUI API-format img2img** workflow, without modifying existing M0.9 asset license / Godot / review / release gates.

## One-image-to-multiple-styles flow

1. Generate one composition PNG with ChatGPT (or another authorized source).
2. Prepare and queue the M1.7 run with explicitly supplied model ID, license review note, workflow API JSON, LoadImage node ID, KSampler node ID and 1–4 seeds. The existing M1.7 command must include **--live** to actually queue to a local ComfyUI server.
3. After ComfyUI finishes, collect **only** the queued prompt IDs recorded in that run:

    python -m mado_asset_foundry.composition_style_intake collect \
      runs/composition-style/scene-001 \
      --server http://127.0.0.1:8188

4. Open **runs/composition-style/scene-001/gallery.html** locally. Each candidate displays original composition, rendered candidate and raw pixel difference. Review all candidates manually.
5. Record a per-image, hash-bound decision:

    python -m mado_asset_foundry.composition_style_intake review \
      runs/composition-style/scene-001 \
      --candidate outputs/seed-11-00.png \
      --decision keep --reviewer "operator" \
      --note "Pose and character count verified by eye; review model rights separately."

These commands are additive. Existing MAF packaging, Godot and release approval flows remain **untouched**.

## What constitutes 'done'?

- History is fetched from the local ComfyUI server at GET /history/{prompt_id}, using only prompt IDs from the M1.7 queued evidence.
- Missing/incomplete history is **pending**, failed execution is **error**; only a successful completed history record with persisted PNG results from the queued SaveImage nodes may be rendered.
- If ComfyUI returns the original prompt graph, it must equal the SHA-bound graph that M1.7 submitted. Its presence/absence is separately recorded as history_graph_verified.
- Image bytes are read using GET /view?filename=...&subfolder=...&type=output. Temporary previews, unexpected image descriptors, path traversal, non-PNG data and oversized responses are rejected.
- Each candidate is stored in outputs/ with SHA-256. Each comparison sheet is stored in comparisons/ with SHA-256. The manifest stays in evidence.json. Completed items are hash-verified if collection is repeated.
- gallery.html is a **static, offline, local-only** read view. No CDN, server or external script is required. There is no auto-publish button.
- A 'keep' review creates an immutable reviews/seed-*.json record bound to the PNG and comparison hash. It is not a Godot import, packaging clearance, license grant, M0.9 review or release approval.

## Composition fidelity metrics: intentionally limited

The single metric composition_proxy_similarity (0..1) compares coarse normalized luminance and edge distribution. It is useful for flagging *large changes*, but is not calibrated for aesthetic quality, character count, anatomy, pose, line style or scene semantics. All candidates retain decision=needs_human_review regardless of their score. A score below 0.5 adds a large_visual_change_review flag. Aspect ratio changes are separately flagged.

Image sizes, difference sheets, source/workflow SHA-256, ComfyUI prompt IDs, model provenance and explicit license review notes make every run inspectable. These are evidence, **not an automated final QA pass**.

## Safety and limitations

- Loopback HTTP only, with proxies and redirects disabled for intake; never auto-install model weights/custom nodes.
- Bounded history (3 MB), image (20 MB), PNG dimension (8192 px), image count (max 8 per submitted seed), and M1.7 seed pilot count (max 4).
- No silent overwrite of previous images or human reviews. Symlinked run/output directories are refused.
- No live ComfyUI or real Anima inference happens in automated tests. Local fixtures simulate queued, pending, successful and failed ComfyUI histories.
- Collection expects local ComfyUI's classic /history/{prompt_id} and /view HTTP endpoints, consistent with official ComfyUI server API examples. A future revision can support the newer /api/jobs endpoint if necessary.
- Failed downloads may leave the affected job queued; no job is marked rendered unless its images and comparison panels have been written. Do not manually change evidence.json after queueing.
- The source composition itself needs an authorized use basis. Generative-model rights and image distribution conditions are separately reviewed, and a game-embedding allowance must not be mistaken for standalone pack redistribution permission.

## Tests

    pytest -q tests/test_composition_style.py tests/test_composition_style_intake.py

Existing full CI and real Godot workflows must still pass. Nothing in M1.7.1 changes their downstream release-gate behavior.

References:
- https://docs.comfy.org/development/comfyui-server/api-examples
- https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example.py
