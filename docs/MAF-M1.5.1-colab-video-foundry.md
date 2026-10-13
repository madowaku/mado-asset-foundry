# MAF-M1.5.1 Colab Video Foundry / H3 Compatibility Gate

A no-download, no-install read-only compatibility and output-evidence adapter for the supplied MiniMax_H3.ipynb.

## Requirements read from notebook

| H3 profile | GPU VRAM | System RAM | Free disk |
| --- | ---: | ---: | ---: |
| int8 | 38 GiB | 60 GiB | 58 GiB |
| full | 75 GiB | 120 GiB | 120 GiB |

These thresholds come from the notebook configuration, not live benchmarking. A capacity pass does **not** prove execution, kernel/driver compatibility, access to paid A100 GPUs, or model license clearance.

## API

```python
from pathlib import Path
from mado_asset_foundry.colab_video_gate import probe_local_hardware, intake_h3_result

print(probe_local_hardware("int8"))
# After explicitly generating and downloading a video in Colab:
evidence = intake_h3_result(Path("result.mp4"), Path("runs/h3-intake-01"),
                            metadata=Path("settings.json"))
```

Requires an installed `ffprobe` for output intake. Writes `h3_intake_evidence.json` only after validation and will not overwrite an existing destination. Logs content hashes and media probe observations. No model downloads, third-party code execution, Colab authentication, tunnels, remote storage, automatic release permission, or GPU generation are performed.

Review model/geographical licensing and runtime region before generation. Generated media and source notebooks stay outside the repository. Video aesthetics and public release approval require separate human review.

## Follow-up

M1.5.2: opt-in Colab export manifest, durable storage bridge, and independently exercised GPU smoke test.
