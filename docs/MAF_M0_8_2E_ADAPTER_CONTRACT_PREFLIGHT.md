# MAF-M0.8.2e Adapter Contract / Preflight

## Goal

Introduce the explicit execution boundary required before an external Skill can become a runnable MAF implementation.

Discovery, capability scanning, and registry membership are not sufficient to make a Skill executable.

## Adapter contract

Every future executable adapter implements:

```python
class AssetSkillAdapter(Protocol):
    definition: AdapterDefinition

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        ...
```

The contract owns:

- adapter identity
- target Skill identity
- supported MAF capabilities
- timeout
- required executables
- required Python modules
- required environment variables
- required source files
- execution implementation status

## Preflight

```bash
maf skill preflight <skill-id>
```

Preflight performs observation only.

It does not:

- import third-party Python packages
- execute third-party scripts
- install dependencies
- download weights
- clone repositories
- authenticate to services
- mutate the Skill source

Python packages are checked with module discovery only. Executables are checked with PATH discovery.

## Status contract

```text
unregistered
  no explicit MAF adapter definition exists

blocked
  capability/license/source/dependency contract failed

contract_only
  all observable contract checks pass, but run() is not implemented

ready
  all checks pass, adapter execution is implemented, and a real MAF runner is registered
```

Only `ready` sets `promotion_eligible=true`.

The boolean `execution_implemented` declaration is not sufficient by itself. MAF also requires a concrete runner factory in the adapter catalog, preventing a manifest/definition typo from promoting a non-existent execution path.

M0.8.2e intentionally does not automatically rewrite a Skill manifest from `intake_only` to `executable`.

## 3D adapter contracts

TripoSR and Stable Fast 3D receive explicit adapter definitions, but both remain:

```text
execution_implemented: false
promotion_eligible: false
```

Their definitions establish the future capability and dependency boundary without pretending that the real model runner has been integrated.
