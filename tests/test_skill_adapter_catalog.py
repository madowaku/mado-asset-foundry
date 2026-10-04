from mado_asset_foundry.skills.adapters.catalog import (
    get_adapter_definition,
    has_execution_adapter,
)


def test_triposr_contract_is_registered_and_executable() -> None:
    definition = get_adapter_definition("triposr-snapshot")
    assert definition is not None
    assert definition.adapter_id == "triposr-local"
    assert definition.execution_implemented is True
    assert has_execution_adapter("triposr-snapshot") is True
    assert "image_to_mesh" in definition.capabilities


def test_sf3d_contract_is_registered_but_not_executable() -> None:
    definition = get_adapter_definition("stable-fast-3d-snapshot")
    assert definition is not None
    assert definition.execution_implemented is False
    assert "uv_unwrap" in definition.capabilities
    assert "glb_export" in definition.capabilities



def test_effekseer_ai_contract_is_registered_and_executable() -> None:
    definition = get_adapter_definition("effekseer-ai-snapshot")
    assert definition is not None
    assert definition.adapter_id == "effekseer-ai-local"
    assert definition.execution_implemented is True
    assert has_execution_adapter("effekseer-ai-snapshot") is True
    assert definition.capabilities == ["vfx_create", "vfx_runtime_export"]



def test_effekseer_godot_contract_is_registered_and_executable() -> None:
    definition = get_adapter_definition("effekseer-godot4-snapshot")
    assert definition is not None
    assert definition.adapter_id == "effekseer-godot4-local"
    assert definition.execution_implemented is True
    assert has_execution_adapter("effekseer-godot4-snapshot") is True
    assert definition.capabilities == ["vfx_runtime_playback", "godot_vfx_playback"]
