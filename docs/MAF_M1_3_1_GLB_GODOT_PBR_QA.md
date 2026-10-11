# MAF-M1.3.1 GLB Godot Import / PBR QA Gate

## Scope and dependency

This is a stacked follow-up to **MAF-M1.3 PR #12**, which introduces
one-candidate ComfyUI Trellis2/Pixal3D GLB acquisition. It does not create a
third-party execution path, re-use the M0.9.x PNG-only importer, or grant a
commercial license.

The new gate produces inspectable evidence for two distinct checks:

1. Deterministic, GPU-free inspection of GLB 2.0 binary structure, embedded
   buffer/image references, triangle surface/accessor bounds, core glTF PBR
   material factors and optional texture links.
2. Actual Godot 4.2+ headless importer and ResourceLoader scene instantiation,
   plus observed MeshInstance3D vertex/surface counts and material properties.

It does **not** capture a rendered screenshot or rate appearance. Import and
PBR-structure success end at awaiting_visual_review. Human license/visual
review is still required, and asset-pack redistribution/publication remain
blocked.

## Commands

Begin with a finished M1.3 run:

    maf comfy3d probe ./concept.png --workflow ./native3d-api.json --live

Check the GLB and PBR *without Godot*:

    maf comfy3d glb-inspect runs/comfy3d-probes/<run-id>

Demand embedded base color and metallic-roughness texture maps (optional,
intentionally stricter than ordinary glTF PBR):

    maf comfy3d glb-inspect runs/comfy3d-probes/<run-id> --require-textures

Run one real Godot import and mesh/material inspection (no model download):

    maf comfy3d godot-qa runs/comfy3d-probes/<run-id> --godot-bin godot

Windows users may supply an explicit absolute path to Godot 4.2+:

    maf comfy3d godot-qa runs/comfy3d-probes/<run-id> --godot-bin C:\Tools\Godot_v4.6.1-stable_win64_console.exe

The engine may be installed manually or made available on PATH; MAF never
downloads or silently locates one across the operator's filesystem.

## Artifacts

    runs/comfy3d-godot-qa/<run-id>/
      report.json
      version.stdout.txt
      version.stderr.txt
      import.stdout.txt
      import.stderr.txt
      verify.stdout.txt
      verify.stderr.txt
      godot-runtime.json          # only if real verifier report was valid

The immutable snapshot source is the original M1.3 run, whose input image,
workflow, submitted API graph and GLB SHA-256 are rechecked before launching
Godot. MAF copies only the validated GLB into a temporary freshly generated
Godot project with MAF-authored script; it does not run user-provided project
scripts, plugins, extensions or asset installers. The canonical project is
removed after the QA run, and previous reports are never overwritten.

A valid GLB may have materials with constant color, metallic and roughness
factors rather than texture maps. Thus the default inspector warns about
missing optional maps while --require-textures blocks them. Nonexistent or
out-of-range material references, out-of-bounds BIN/views/accessors, invalid
PBR factors, unembedded assets and non-triangle primitives are blocked.

These tests prove format integrity and imported material presence only, not
semantic correctness of PBR textures, tangent-space normal quality,
UV continuity, photorealism, manifold topology, collision quality,
skeletal animation, face count suitability, rights clearance or release readiness.

## Test acceptance

Offline fixture:

    pytest -q tests/test_glb_godot_qa.py

Real engine (only runs when Godot is installed):

    pytest -q tests/test_glb_godot_qa_real_godot.py

Full baseline regression:

    pytest -q

GitHub Actions real-godot-linux runs the synthetic original GLB through a
real Godot 4.6.1 binary. The offline test suite mocks Godot subprocesses and
never starts ComfyUI or requests model downloads.

## Next milestone

MAF-M1.3.2 can add a graphical, GPU-enabled 3D turntable gallery with
measured frame captures and hash-bound human visual review. Even a perfect
turntable does not automatically authorize publication or standalone resale.

Official references:

- https://docs.godotengine.org/en/4.6/classes/class_basematerial3d.html
- https://docs.godotengine.org/en/4.6/classes/class_resourceimporterscene.html
- https://docs.godotengine.org/en/4.6/tutorials/editor/command_line_tutorial.html
