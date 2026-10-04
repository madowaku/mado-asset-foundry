# MAF-M0.8.2d Registry / Resolver

## Goal

Turn scanned Skill manifests into one deterministic local capability catalog and resolve requested MAF capabilities without confusing discovery with executability.

## Commands

```bash
maf skill registry build skills/manifests
maf skill list
maf skill show <skill-id>
maf skill resolve <capability>
```

The registry recursively includes nested manifests, including manifests produced by multi-Skill pack scans.

## Resolver states

```text
resolved
  exactly one executable adapter exists

ambiguous
  more than one executable adapter exists

candidate_only
  matching Skills exist, but they are intake_only

unresolved
  no executable or intake-only candidate exists
```

M0.8.2d never selects an intake-only Skill as an execution provider.

## Determinism

- registry entries are sorted by skill_id
- duplicate skill_id values fail the build
- resolver candidates sort by adapter status and skill_id
- multiple executable candidates are ambiguous rather than arbitrarily ranked

## 3D preparation

The provider-independent taxonomy now includes:

```text
image_to_mesh
mesh_texture_bake
uv_unwrap
material_predict
image_delight
mesh_decimate
mesh_repair
mesh_qa
glb_export
```

These contracts are intended to support future TripoSR, Stable Fast 3D, Blender, or other adapters without baking provider names into MAF Recipes.

A synthetic `sample-image-to-3d` fixture proves the scanner can classify this family without importing or running a 3D model.
