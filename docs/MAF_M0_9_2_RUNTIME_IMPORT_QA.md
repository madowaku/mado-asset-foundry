# MAF-M0.9.2 Godot Runtime Import QA / License Evidence Gate

## Objective

Re-check M0.9 license evidence and M0.9.1 compiled-asset integrity,
then invoke **real Godot 4.2+ headless import** and **ResourceLoader.load**
for every PNG as a Texture2D. Confirm successful loads and exact
dimensions. Capture reproducible runtime and process logs.

This is a **Godot resource-load QA gate**, not visual approval, IP
clearance, security isolation from the supplied Godot executable,
or permission to publish/redistribute any asset.

## Workflow

1. Create M0.9 eligible per-asset intake reports, with human-reviewed
   per-asset license evidence, using the M0.9 source-intake CLI.
2. Compile a PNG Godot project using the M0.9.1 bridge.
3. Run the explicit M0.9.2 runtime QA:

    maf asset-godot qa path/to/plan.json path/to/generated-project --godot-bin godot

   Use --output-root to change the evidence location, --timeout to
   bound each process (default 120 seconds), and --force only when
   intentionally replacing existing QA evidence.

The QA compares **every generated file** to a freshly recompiled
canonical project created from the original submissions and M0.9
reports. Source PNGs, local license files, creator, license,
attribution, source and URLs must agree with the original intake
evidence. Unknown or changed licenses, non-eligible submissions,
tampered CREDITS/manifest/PNG/project, extra files, and symlinks are
rejected **before invoking Godot**.

Only a newly built, strict-file-list temporary project is executed.
M0.9.2 does not execute scripts inside the supplied project.
It generates its own trusted verification SceneTree script and an
image-dimension manifest, runs the editor importer, then loads every
imported texture via Godot's ResourceLoader. The temporary directory
is removed after completion.

## Evidence

Default output:

    evidence/asset-godot-runtime/<project-id>/
      report.json
      version.stdout.txt
      version.stderr.txt
      import.stdout.txt
      import.stderr.txt
      verify.stdout.txt
      verify.stderr.txt

Failed runtime attempts are recorded. The report includes exact
commands, Godot version, subprocess return codes, loaded texture count,
per-asset SHA-256 and license identifiers, runtime JSON and failure
reason. The Godot project is left unchanged. The bridge never
downloads, installs Godot, or uses a paid API.

Return codes: 0 for confirmed success; 2 for a runtime failure;
1 for input/license/integrity error. Neither success nor failure
asserts a visually attractive render or publication rights.

## Verification

Tests use a fake Godot process for deterministic checks of failures,
version gate, subprocess logging and report handling. A separate
CI smoke job installs a fixed Godot 4.6.1 build and runs one
synthetic CC0 PNG through the **actual** Godot binary.
External marketplace assets are not used in CI.

Godot is operator-supplied in local runs. Never point this CLI at an
untrusted executable. The compiler does not alter the existing
product packaging/itch.io public-release gates.
