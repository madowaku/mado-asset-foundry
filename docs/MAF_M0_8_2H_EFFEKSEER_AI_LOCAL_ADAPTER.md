# MAF-M0.8.2h Effekseer AI Local Adapter / 1-Effect Probe

## Goal

Promote the metadata-only `effekseer-ai` candidate into one explicitly registered local VFX runner and prove exactly one structural effect lifecycle.

## Upstream contract

Pinned bridge source:

```text
laodeng000/effekseer-ai
208922ef192220322c2a79e1243ed51ff7d2b7af
MIT
```

The pinned bridge documents this verified configuration:

```text
Windows 10+
Effekseer 1.80.6
Python 3.11+
.NET 9.x
Python.NET 3.x
```

MAF records **1.80.6 as the compatibility target**. M0.8.2h does not claim that a DLL version can be proven from its filename alone.

## Execution contract

```text
new <effect.efkefc>
node-add <effect.efkefc> --name <name>
export <effect.efkefc> <effect.efk>
```

Each command must:

- exit with code 0
- emit valid JSON stdout
- preserve stderr
- produce the expected local file before the next stage

The node-add response must include a `node/root/<index>` path.

## Local boundary

The operator supplies:

```text
--effekseer-ai-bin <explicit executable/path>
--source-root <pinned effekseer-ai checkout>
--effekseer-bin-dir <official Effekseer Tool/bin>
```

The source checkout must resolve to `208922ef192220322c2a79e1243ed51ff7d2b7af`. The Tool/bin directory must contain `EffekseerCore.dll`.

MAF does not:

- scan drives for Effekseer
- download an Effekseer distribution
- install effekseer-ai
- install .NET
- launch the Effekseer GUI
- launch the MCP server
- open a network listener

## Command

```powershell
python -m mado_asset_foundry.cli skill vfx-effect-probe `
  --effekseer-ai-bin C:\Tools\effekseer-ai\.venv\Scripts\effekseer-ai.exe `
  --source-root C:\Tools\effekseer-ai `
  --effekseer-bin-dir C:\Tools\Effekseer1806\Tool\bin `
  --name "MAF Spark Probe"
```

## Evidence

```text
runs/vfx-effect-probes/<run-id>/
  effect.efkefc
  effect.efk
  evidence/
    job.json
    result.json
    steps/
      new.json
      new.stdout.log
      new.stderr.log
      node-add.json
      node-add.stdout.log
      node-add.stderr.log
      export.json
      export.stdout.log
      export.stderr.log
```

The job evidence also records the expected/observed effekseer-ai Git ref and hashes of its pyproject/CLI source. The final result records hashes and sizes for both source and runtime effect files.

## Scope boundary

M0.8.2h proves **document creation and runtime export**, not visual quality.

The next acceptance layer should load `.efk` through the official Godot 4 plugin and capture runtime playback evidence.
