# MAF-M0.8.2c Universal Modder Intake Fixture

## Goal

Prove that MAF can inspect a real multi-Skill OSS package without executing third-party code.

The fixture is derived from:

- upstream: `rehan-remade/universal-modder`
- commit: `15d6f9d5fbd32de9b1884f29ddec3be9133bd912`
- upstream version at that commit: `0.2.0`
- license: MIT

The checked-in fixture is intentionally a **curated text snapshot**, not a vendored copy of Universal
Modder. It preserves the structure and phrases needed for discovery/classification while excluding
executable modules, PowerShell helpers, game examples, generated assets, credentials, and binaries.

## Command

```bash
maf skill scan-pack fixtures/skills/universal-modder-snapshot
```

Default outputs:

```text
skills/manifests/universal-modder/<skill-id>.json
evidence/skill-pack-scan/universal-modder/members/<skill-id>/report.json
evidence/skill-pack-scan/universal-modder/pack-report.json
```

## What M0.8.2c proves

The pack scanner:

1. discovers every `skills/**/SKILL.md`;
2. runs the existing M0.8.2b deterministic classifier per Skill;
3. records which Skills expose MAF-relevant asset capabilities;
4. detects root `pyproject.toml` CLI entrypoints;
5. detects MCP server declarations from JSON MCP configs;
6. records Python packages, explicit external tools, and MCP services;
7. extracts explicit safety constraints from Skill text;
8. detects the repository-level license;
9. classifies capability-bearing Skills as `adapter_required`;
10. executes no external code.

For the pinned Universal Modder snapshot, 10 Skills are discovered and the initial MAF adapter candidates
are:

```text
asset-pipeline
fal-assets
showcase-video
```

The remaining Skills are retained as evidence but marked `out_of_scope` for the MAF asset adapter layer.

## Safety boundary

M0.8.2c reads text only. It does not install the upstream package, import its Python modules, execute the
`um` CLI, contact fal/MCP services, launch games, drive input devices, or inspect/modify local game files.

Execution belongs to a later adapter milestone after explicit capability and policy gates.
