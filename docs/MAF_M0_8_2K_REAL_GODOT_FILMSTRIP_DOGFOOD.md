# MAF-M0.8.2k Real Godot Filmstrip Dogfood / Visual Evidence Promotion Gate

## Purpose

Extends M0.8.2j from passive verified evidence intake to **operator-approved EffekseerCore builds and real Godot windowed filmstrip capture** followed by **independent assessment and visual-evidence-only promotion**.

This is a runnable local execution path, not a pre-rendered screenshot mock. It requires Windows x64 or macOS ARM64 with the user-installed KanaWorks toolchain and a Godot Forward+ window on the logged-in desktop. MAF does not download, install or alter the pinned toolchain. The historical MAF M0.8.2h authoring bridge and M0.8.2i Godot plugin use different Effekseer versions; no automatic mixing occurs.

## Phase A: Capture and handoff

The capture CLI requires two explicit flags: --execute --allow-window. It invokes these upstream commands in order:

1. doctor: requires build and render available, plus an initialized workspace
2. brief-validate ID and lint --ids ID
3. build --ids ID, never a full-library-pruning build
4. review --ids ID --note NOTE, opening a windowed Godot rendering session
5. Validate original screenshots with SHA-256 and Pillow PNG decoding; require actual frame-zero baseline, 60 FPS, consistent dimensions, minimum three frames, and visible pixel changes
6. review-handoff ID: create an independent-review prompt bound to this capture

The immutable MAF capture-dogfood.json receipt reports awaiting_independent_review, never ship/release approved. The operator must provide a separate reviewer with the captured filmstrip. Neither MAF nor the author fabricates review scores.

## Phase B: Independent review and promotion

A separate session follows the pinned upstream vfx-review Skill to inspect actual frames and write an eight-criterion report. The user submits it through upstream review-submit, then runs full vfx overview (without --ids) and effect-verify ID.

The promote CLI requires --execute --license-reviewed and the original capture manifest. It rechecks unchanged capture source and PNG hashes, invokes the existing M0.8.2j effect-verify adapter and requires the *same* evidence ID to match across capture, reviewer and overview. The reviewer scores must all be at least 2 and verdict ship. The resulting visual-promotion.json and visual-proof/ folder archive the original filmstrip, overview PNGs and the frames the reviewer actually saw.

The result is **visual_evidence_promoted**, not a shipping decision. game_runtime_verified, device_performance_verified, and release_approved remain false. Independent reviewer isolation is host-attested, not cryptographically guaranteed.

## Windows quickstart

Get the latest mado-asset-foundry and a separate pinned upstream checkout at:

https://github.com/kanaworksai-hue/effekseer-vfx-skill
Commit d2f28031ac62014f00e04b416dfe1a7f3818593d

Manually examine licenses and THIRD_PARTY_NOTICES before running upstream setup, which can download around 250 MB. After upstream vfx init and creating a real VFX_Hit_Spark recipe and brief:

~~~powershell
python -m mado_asset_foundry.cli skill vfx-filmstrip-capture C:\Dev\MyGame --effect-id VFX_Hit_Spark --skill-checkout C:\Tools\effekseer-vfx-skill --output-dir .\runs\vfx-dogfood\hit-01 --execute --allow-window
~~~

Read the generated reviewer_handoff path and ask a different agent/session to review the actual images and submit its own report. Then, using the upstream vfx.cmd launcher:

~~~powershell
C:\Tools\effekseer-vfx-skill\skills\effekseer-vfx\scripts\vfx.cmd --project C:\Dev\MyGame review-submit <evidence_id> <report.json> --reviewer reviewer-session-02
C:\Tools\effekseer-vfx-skill\skills\effekseer-vfx\scripts\vfx.cmd --project C:\Dev\MyGame overview
C:\Tools\effekseer-vfx-skill\skills\effekseer-vfx\scripts\vfx.cmd --project C:\Dev\MyGame effect-verify VFX_Hit_Spark
~~~

After separately checking source and media rights:

~~~powershell
python -m mado_asset_foundry.cli skill vfx-filmstrip-promote .\runs\vfx-dogfood\hit-01\capture-dogfood.json --skill-checkout C:\Tools\effekseer-vfx-skill --output-dir .\runs\vfx-promoted\hit-01 --execute --license-reviewed
~~~

Use new output directory names for subsequent rounds; existing evidence is never overwritten.

## Evidence gates and limits

- The upstream source must have exactly the pinned Git revision with a clean Skill tree.
- Doctor render=true by itself does not prove that Godot rendered anything. Actual PNG images with changing pixels are mandatory.
- Screenshots, raw frame hashes, captured metadata, independent review, overview and effect ID must be consistent.
- No reviewer submission is manufactured; no unreviewed capture can be promoted.
- Release approval, Godot scene integration, runtime import/device performance, GPU overdraw and third-party asset rights require separate steps.
- Ordinary CI covers this bridge using Pillow-generated valid PNGs and simulated upstream commands. Its existing real-Godot gallery workflow is not proof of KanaWorks native Effekseer playback. Full local end-to-end dogfood still must be run on a configured desktop.

## Automated tests

~~~sh
python -m pytest -q tests/test_effekseer_vfx_dogfood.py
python -m pytest -q
~~~
