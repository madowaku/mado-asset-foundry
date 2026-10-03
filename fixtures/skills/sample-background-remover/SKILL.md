# Sample Background Remover

Synthetic fixture used by MADO Asset Foundry tests.

This fixture describes a background-removal Skill but M0.8.2a must not infer
or execute that capability yet.


## Capabilities

This Skill performs background removal using foreground segmentation and emits a transparent cutout.
It also applies alpha mask cleanup and edge cleanup for transparent PNG assets.

## Runtime

The implementation uses Python and ONNX Runtime.
