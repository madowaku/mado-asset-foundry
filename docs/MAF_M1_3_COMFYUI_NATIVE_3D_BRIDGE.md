# MAF-M1.3 ComfyUI Native 3D Foundry Bridge

## Purpose

Acquire one local 3D asset candidate from ComfyUI native Trellis2/Pixal3D
without changing the earlier 2D curation, license, Godot, or release gates.

This milestone implements an explicit, local-only production probe, not
an automatic 3D marketplace pipeline. The result is a candidate GLB awaiting
human rights review, real Godot import, topology/PBR inspection, and visual QA.

## Required preparation (manual)

1. Install/upgrade local ComfyUI with native Trellis2 / Pixal3D nodes, and
   install the model weights referenced by the chosen official workflow
   manually. MAF does not clone, download or install anything.
2. Open a native image-to-3D workflow in ComfyUI, pick the model and test
   that it saves a real GLB with SaveGLB. Do not use Save3DAdvanced or an
   OBJ output for this bridge.
3. Use File > Export Workflow (API) and save its JSON to a local path.
   The normal editor JSON (with nodes/links/positions) is not supported.
4. Save an appropriately licensed or original source image locally.
5. Start ComfyUI on a loopback-only address such as 127.0.0.1:8188. Do
   not expose the ComfyUI HTTP API to a public interface.

Useful official references:

- https://blog.comfy.org/p/trellis2-and-pixal3d-are-now-native
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/3d_pixal3d_trellis2_image_to_model.json
- https://docs.comfy.org/development/api-development/workflow-api-format
- https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_save_3d.py

## Commands

Inspect without network requests or GPU work:

    maf comfy3d plan ./concept.png --workflow ./native3d-api.json

When ready, submit one explicit local probe:

    maf comfy3d probe ./concept.png --workflow ./native3d-api.json --live

Advanced examples:

    maf comfy3d plan ./concept.png --workflow ./native3d-api.json --image-node 20 --save-node 42
    maf comfy3d probe ./concept.png --workflow ./native3d-api.json --image-node 20 --save-node 42 --server http://127.0.0.1:8188 --run-id concept-001 --live

If several LoadImage or SaveGLB nodes are present, select one explicitly.
The bridge replaces only the selected LoadImage.image and
SaveGLB.filename_prefix, preserving the rest of the trusted API graph.

No ComfyUI installation, checkpoint download, restart, remote account,
AI subscription, API key, or Godot executable is required by the bridge.
A GPU and the proper pre-installed weights are needed to actually run
the selected model, and compute/electricity/storage are not free.

## Result

    runs/comfy3d-probes/<run-id>/
      inputs/
        source.png                      # or .jpg/.webp
        workflow-api.json               # original API export
        submitted-prompt.json           # exact mutated graph
      asset.glb                         # only after structural validation
      evidence.json                     # always retained after remote errors

Evidence contains:

- Input/workflow/submitted graph SHA-256 hashes
- Selected image/save node IDs and native model family
- ComfyUI prompt ID and SaveGLB filename/subfolder/type
- Downloaded GLB SHA-256, file size, coarse mesh/material/texture counts
- Explicit no license approval, no Godot QA, no visual QA, no publication
- Failure and prompt ID whenever the remote server fails or times out

Possible status values: failed or awaiting_3d_qa. The latter proves only
that one GLB was downloaded and passed a lightweight GLB 2.0 envelope check.
It is not proof of manifold topology, rigging, PBR material quality,
correct origin/scale, Godot import, commercial rights or visual acceptability.

The HTTP client rejects non-loopback hosts, TLS-to-public, auth/query paths,
proxy use, redirects, unsafe output paths and non-GLB SaveGLB responses.
Input images are at most 25 MiB; GLB downloads at most 100 MiB. A run
directory is never overwritten. A timed-out prompt may continue processing
on the local ComfyUI server; MAF does not cancel existing ComfyUI work.

## What is not automated

- ComfyUI model installation or model hash/version verification
- Web workflow retrieval, arbitrary code execution, or dependency downloads
- Feeding a GLB directly into the 2D PNG M0.9 intake/attribution pipeline
- Automatically promoting a 3D asset to the existing Cockpit release gallery
- Godot runtime import, GPU renderer screenshot, topology/PBR QA or legal review
- Asset Vault sync, selling or publishing

These are separate proposed follow-ups for MAF-M1.3.x. In particular, the
M0.9.x Godot bridge is PNG-specific and must not be bypassed by renaming
a GLB or claiming this candidate satisfies the original 2D gates.

## Offline acceptance

    pytest -q tests/test_comfy3d.py
    pytest -q

The test suite uses an in-process fake ComfyUI transport only, synthetic
original images and GLB bytes. A real GPU probe remains operator-triggered
via --live and is not run by CI.
