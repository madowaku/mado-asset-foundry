# MAF-M0.9.3 Visual Gallery QA / Attribution Release Gate

## Contract

Compile a deterministic visual review artifact **using an actual Godot renderer**,
then require an explicit human decision tied to the preview and attribution
hashes. No marketplace publishing, standalone asset pack release,
Godot editor plugin execution, or license permission inference is performed.

This milestone is intentionally limited to **1-8 game-embedding PNG assets**
per gallery. It inherits M0.9 asset-level evidence and M0.9.1 canonical
Godot project generation, and re-runs M0.9.2 real Godot ResourceLoader QA
before rendering. Unknown/changed license evidence, assets, source reports,
CREDITS, manifest, or unexpected project files fail before rendering.
Only a new trusted Godot script executes in a sanitized temporary project.

A rendered screenshot is checked for PNG format, 960x540 dimensions and
non-uniform image content. This is **capture integrity**, not aesthetic
quality or proof that every image is visually acceptable. Human review is
always necessary.

## Commands

Run from project root with M0.9-M0.9.2 inputs already prepared:

\`\`\`bash
maf asset-godot gallery path/to/plan.json path/to/project --godot-bin godot
maf asset-godot gallery path/to/plan.json path/to/project --godot-bin godot --virtual-display
maf asset-godot release-check path/to/plan.json path/to/project evidence/asset-gallery/<project-id>
\`\`\`

The optional \`--virtual-display\` flag uses an explicitly installed
\`xvfb-run\` on Linux. **Do not use Godot's \`--headless\` option to assert
visual screenshot QA**, since it does not guarantee an actual display
renderer. The CLI never downloads Godot, assets, or Xvfb.

Generated files:

\`\`\`text
evidence/asset-gallery/<project-id>/
  report.json
  CREDITS.md
  gallery.png
  gallery.stdout.txt
  gallery.stderr.txt
\`\`\`

The report includes the Godot version, command, image SHA-256, image
dimensions, rough image variance, asset hashes, intake report hash,
local license evidence hash, and required review status.
Failed render attempts preserve a report and stdout/stderr when available.
Missing or invalid rights block **before** launching the capture.

## Human review

Prepare a separate JSON file **after visually inspecting gallery.png and CREDITS.md**:

\`\`\`json
{
  "schema_version": "0.1",
  "project_id": "my-game",
  "reviewer": "human-reviewer",
  "screenshot_sha256": "<sha256 from report.json>",
  "credits_sha256": "<sha256 from report.json>",
  "manifest_sha256": "<sha256 from report.json>",
  "visual_approved": true,
  "attribution_approved": true,
  "rights_approved_for_game_embedding": true,
  "notes": "I reviewed the rendered gallery, credits and per-asset rights."
}
\`\`\`

Then:

\`\`\`bash
maf asset-godot release-check path/to/plan.json path/to/project \
  evidence/asset-gallery/<project-id> --review human-review.json \
  --output evidence/asset-gallery/<project-id>/release-check.json
\`\`\`

The gate reconstructs the canonical project and revalidates all source
hashes and license evidence, the gallery screenshot hash, the credits
hash, and the asset manifest hash. A missing/negative/stale human
attestation yields \`human_review_required\` (exit code 2). Successful
attestation yields \`human_release_review_passed\` (exit 0), but **does not
set publication_approved true, upload or publish**. MAF's separate
product/itch.io legal and marketplace gates remain mandatory. Human
acknowledgement isn't a substitute for actual use rights.

Any failed preflight input validation returns code 1. Rendering
failures return code 2 and preserve runtime/capture evidence.
Existing gallery and review outputs are not silently overwritten.
