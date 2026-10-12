# KanaWorks Effekseer VFX Skill (metadata-only snapshot)

This is an evidence-only catalog entry pinned to kanaworksai-hue/effekseer-vfx-skill. It is not an installed Skill, and contains no copied executable Python scripts.

## Capabilities
The upstream provides independent VFX review and Godot filmstrip visual review. Its effect-verify review gate checks capture, independent rubric report and library overview. Authoring, Effekseer Core build, Godot render and export remain separately gated.

## Runtime
Python 3.11+ supports authoring. Windows x64 and macOS ARM64 support build and rendering with .NET 9, EffekseerCore 1.80.7, Godot 4 and EffekseerForGodot4 1.80.5.1; Linux build and Godot windowed rendering are not verified. User must install tooling manually. MAF executes only effect-verify when explicitly permitted.

## Rights
The external Skill is MIT but its embedded effekseer-ai and downloaded Effekseer, .NET, Godot plugin, image textures and codecs have their own terms. See the upstream THIRD_PARTY_NOTICES.md. No external executable or content is bundled.
