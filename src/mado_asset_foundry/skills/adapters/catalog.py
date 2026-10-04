from __future__ import annotations

from .models import AdapterDefinition


ADAPTER_DEFINITIONS: dict[str, AdapterDefinition] = {
    "triposr-snapshot": AdapterDefinition(
        adapter_id="triposr-local",
        skill_id="triposr-snapshot",
        capabilities=[
            "model3d_generate",
            "image_to_mesh",
            "mesh_texture_bake",
        ],
        execution_implemented=False,
        timeout_seconds=900,
        required_executables=["python"],
        required_python_modules=["torch"],
        notes=[
            "Contract/preflight definition only; no TripoSR execution adapter is implemented yet.",
            "A future executable adapter must use a real pinned checkout, not the metadata-only fixture.",
        ],
    ),
    "stable-fast-3d-snapshot": AdapterDefinition(
        adapter_id="stable-fast-3d-local",
        skill_id="stable-fast-3d-snapshot",
        capabilities=[
            "model3d_generate",
            "image_to_mesh",
            "mesh_texture_bake",
            "uv_unwrap",
            "material_predict",
            "image_delight",
            "glb_export",
        ],
        execution_implemented=False,
        timeout_seconds=900,
        required_executables=["python"],
        required_python_modules=["torch"],
        notes=[
            "Contract/preflight definition only; no Stable Fast 3D execution adapter is implemented yet.",
            "Model access/login requirements will be enforced by the future executable adapter.",
        ],
    ),
}


def get_adapter_definition(skill_id: str) -> AdapterDefinition | None:
    return ADAPTER_DEFINITIONS.get(skill_id)
