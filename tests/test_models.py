"""Model factory (ScaleModel) and registry contract."""

import pytest

from pydigi import (
    ScaleModel,
    DigiDS781,
    Scale,
    TypeBProtocol,
    LoopbackTransport,
    register,
    get_model,
    available_models,
)


def test_ds781_is_a_scalemodel():
    assert issubclass(DigiDS781, ScaleModel)
    assert DigiDS781.name == "ds781"
    assert DigiDS781.protocol_class is TypeBProtocol
    assert DigiDS781.max_weight_kg == 30.0


def test_bind_returns_a_scale():
    scale = DigiDS781.bind(LoopbackTransport(b""))
    assert isinstance(scale, Scale)


def test_model_is_not_instantiable():
    # Models are factories used via classmethods; instances make no sense.
    with pytest.raises(TypeError):
        DigiDS781()


def test_bind_requires_protocol_class():
    class Incomplete(ScaleModel):
        name = "incomplete-not-registered"

    with pytest.raises(NotImplementedError):
        Incomplete.bind(LoopbackTransport(b""))


def test_register_rejects_nameless_model():
    class NoName(ScaleModel):
        protocol_class = TypeBProtocol

    with pytest.raises(ValueError):
        register(NoName)


def test_register_rejects_name_collision():
    class Impostor(ScaleModel):
        name = "ds781"  # already owned by DigiDS781
        protocol_class = TypeBProtocol

    with pytest.raises(ValueError):
        register(Impostor)


def test_register_is_idempotent_for_same_class():
    # Re-registering the identical class must not raise (module re-imports).
    register(DigiDS781)
    assert "ds781" in available_models()


def test_get_model_unknown_raises():
    with pytest.raises(KeyError):
        get_model("no-such-model")
