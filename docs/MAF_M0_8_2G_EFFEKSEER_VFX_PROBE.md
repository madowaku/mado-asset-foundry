# MAF-M0.8.2g Effekseer Intake / VFX Capability Probe

## Goal

Add VFX as a first-class MAF capability family without executing or vendoring any external VFX software.

## Pinned evidence sources

```text
effekseer/Effekseer
82b37081a302b9f9eff0bf14dc6c845fca8c3c54
MIT
role: authoring/runtime

laodeng000/effekseer-ai
208922ef192220322c2a79e1243ed51ff7d2b7af
MIT
role: Python CLI + MCP authoring bridge
verified upstream configuration: Effekseer 1.80.6, Windows, Python 3.11+, .NET 9

effekseer/EffekseerForGodot4
8706d2917c2487efac3a4943c16a10dfcfc5b127
MIT
role: Godot 4 runtime playback
```

The official Effekseer README explicitly warns that master is the development branch. The MAF snapshot is therefore evidence-only.

## VFX taxonomy

```text
vfx_create
vfx_edit
vfx_runtime_export
vfx_runtime_playback
vfx_resource_import
vfx_mcp_authoring
godot_vfx_playback
```

Provider names are not capability names.

## Probe command

```powershell
maf skill vfx-probe
```

Default outputs:

```text
skills/manifests/vfx/*.json

evidence/vfx-capability-probe/
  members/
    <skill-id>/report.json
  report.json
```

The combined report lists each Skill role, pinned upstream ref, normalized license/runtime, capabilities, and a capability-to-candidate map.

## Expected separation

```text
vfx_create
  Effekseer
  effekseer-ai

vfx_mcp_authoring
  effekseer-ai

godot_vfx_playback
  EffekseerForGodot4
```

All remain intake-only candidates. M0.8.2g does not register an executable VFX adapter.

## Safety

- no Effekseer GUI launch
- no EffekseerCore.dll load
- no MCP server launch
- no Godot plugin execution
- no cloning/installing/downloading
- no generated effect files
- no external code execution
