# MAF-M0.8.2j Effekseer VFX Skill Intake / Visual Review Bridge

## Goal

Connect the independently developed KanaWorks Effekseer VFX Skill to the existing MAF skill registry and its evidence conventions, **without replacing the M0.8.2h Effekseer AI or M0.8.2i Godot playback adapter**. This increment accepts *independently reviewed Godot filmstrip evidence* only if the pinned upstream verification and MAF's local consistency checks agree.

The bridge does not author particle effects, install dependencies, download binaries, launch Godot, submit reviews, or ship game assets.

## Pinned provenance

- Upstream: https://github.com/kanaworksai-hue/effekseer-vfx-skill
- Commit: d2f28031ac62014f00e04b416dfe1a7f3818593d
- Skill metadata: effekseer-vfx 0.1.1; independent vfx-review 0.1.0
- License: MIT for upstream source, with separate THIRD_PARTY_NOTICES.md
- Vendor: **none**. The fixture in fixtures/skills/effekseer-vfx-skill-snapshot is metadata-only. A user-provided local checkout at exactly the pinned revision is required.
- This upstream build path documents EffekseerCore 1.80.7 and EffekseerForGodot4 1.80.5.1, whereas MAF's historical independent authoring/playback probes target 1.80.6 and 1.80.7 respectively. Do not mix binary/plugin builds between them or assert compatibility merely because they share the same effekseer-ai base commit.

The adapter checks the actual Git HEAD, the required skill/reviewer/LICENSE/notices files and a clean status for the upstream Skill files. Unknown or dirty revisions fail closed.

## Integration boundary

~~~text
Operator-authored VFX brief / Python recipe (upstream)
       |   explicit user-installed toolchain, Windows x64 or macOS ARM64
       v
EffekseerCore build + Godot windowed capture (upstream)
       |
Independent reviewer with images only (upstream vfx-review)
       |
review-submit + full overview + effect-verify (upstream)
       |   MAF opt-in fixed-command execution
       v
MAF VFX Skill Review Bridge
    - pinned Git revision and clean scripts
    - effect-verify reports verified=true / issues=[]
    - the latest standard/default capture is complete
    - capture, review, overview match the same evidence ID
    - SHA-256 of capture images, extracted frames, overview pages
    - upstream review-rubric SHA-256 matches Skill checkout
    - reviewer ID, eight rubric scores (all >= 2) and ship verdict
    - review's observed frame labels exist in the captured frames
    - .efkefc source and .efk export present, recorded with hashes
       |
       v
review-bridge-report.json
    status=verified_visual OR hold_not_verified
    game_runtime_verified=false
    release_approved=false
~~~

The upstream effect-verify checks build receipts, changed source, stage, brief, captured image and reviewer freshness. MAF independently verifies its most security-critical visual evidence paths/hashes and cross-record bindings. Upstream uses a **host-attested** reviewer identity: the bridge cannot independently prove that the reviewer was genuinely isolated from the author. A reviewer needs to actually inspect the filmstrip as described by the upstream reviewer Skill.

## Prerequisites

Install Git, Python 3.11+, the pinned upstream Skill and the upstream's supported toolchain **manually**, after inspecting upstream instructions, license and downloads. The full authoring/build/render workflow requires Windows x64 or macOS ARM64; Linux is authoring-only and no Linux windowed Godot filmstrip capture has been verified. Real desktop Godot cannot generally be opened from Codex Cloud or a sandbox.

The operator must first complete upstream VFX creation, render review, independent review-submit, baseline overview, and run effect-verify successfully on the effect.

### Preparing a pinned checkout

~~~sh
git clone https://github.com/kanaworksai-hue/effekseer-vfx-skill.git
cd effekseer-vfx-skill
git checkout d2f28031ac62014f00e04b416dfe1a7f3818593d
git status --short
~~~

Running a first-time upstream setup script can download approximately 250 MB of runtimes/tooling, and upstream VFX init may download a Godot plugin. **This MAF bridge never invokes either command.** Only proceed with upstream installation after separately inspecting and approving the downloads.

### MAF adapter usage

Execute from mado-asset-foundry root, substituting actual local project and checkout paths. Use a *new* evidence output directory every run.

~~~sh
python -m mado_asset_foundry.cli skill vfx-skill-review-bridge \
  /path/to/godot-game \
  --effect-id VFX_Fire_Explosion \
  --skill-checkout /path/to/effekseer-vfx-skill \
  --output-dir runs/vfx-skill-review/fire-explosion-01 \
  --execute
~~~

On PowerShell run on one line or use backticks for line continuations. No implicit approval, alternate arbitrary commands, auto-download or overwrite is permitted.

Successful completion means **visual-review evidence received and inspected**, not game runtime correctness or final release approval. Keep the separately implemented MAF Godot import/playback QA, plugin compatibility checks, game-scene performance QA, and license-gated asset publishing distinct.

If upstream effect-verify reports verified=false, the CLI exits with status 2 and writes a **hold_not_verified** report. Upstream malformed output, unknown pinned revision, inconsistent receipts, tampered images, missing binaries and fake reviewer inputs stop without writing a success report.

## Scanning / discovery

~~~sh
python -m mado_asset_foundry.cli skill scan fixtures/skills/effekseer-vfx-skill-snapshot
~~~

The snapshot produces a capability candidate for vfx_visual_review but contains no third-party executable code.

## Tests

~~~sh
python -m pytest -q tests/test_effekseer_vfx_skill_bridge.py
python -m pytest -q
~~~

CI uses a mocked upstream command with synthetic PNG/artifact bytes to verify source trust, command allowlist, eight-score rubric, evidence cross-checks and failure cases. **CI does not install the upstream Skill or render a real VFX**, so full desktop dogfood remains a separate acceptance step.
