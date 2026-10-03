# MAF-M0.8.2a Skill Intake Skeleton

## Goal

Establish the read-only boundary between MADO Asset Foundry and local external OSS Skill directories.

M0.8.2a deliberately does **not** classify capabilities and does **not** execute external code.

## CLI

```bash
maf skill intake <local-skill-directory>
maf skill validate <manifest.json>
```

Example:

```bash
maf skill intake fixtures/skills/sample-background-remover
```

Default outputs:

```text
skills/manifests/<skill-id>.json
evidence/skill-intake/<skill-id>/report.json
```

Generated manifests and intake evidence are ignored by Git by default.

## Structural discovery

The skeleton discovers:

- SKILL.md
- README
- LICENSE/COPYING
- scripts/
- pyproject.toml
- requirements.txt
- package.json
- environment.yml
- Dockerfile

Discovery is descriptive only.

The following remain empty in M0.8.2a:

```json
{
  "capabilities": [],
  "runtime": [],
  "inputs": [],
  "outputs": [],
  "adapter_status": "intake_only"
}
```

M0.8.2b owns capability and runtime classification.

## Safety contract

- Intake is read-only.
- No subprocess is launched.
- No Python/Node script from the external Skill is imported or executed.
- No dependency is installed.
- No network access is required.
- Existing manifest/evidence files are not overwritten without --force.
- License files are only detected structurally; SPDX interpretation is deferred.

## Acceptance criteria

- normalized Skill Manifest models exist
- `maf skill` CLI namespace exists
- local directory intake works
- synthetic Skill fixture is discoverable
- structural files are recorded
- manifest status is intake_only
- capability classification is explicitly false in evidence
- external_code_executed is false in evidence
- duplicate output requires --force
- tests require no network and execute no external Skill code
