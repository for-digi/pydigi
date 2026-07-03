"""The ScaleReading data model and its derived properties."""

from pydigi import ScaleReading, StatusFlag, WeightConditionFlag, PriceBase


def make_reading(status=0x42, condition=0x42, **overrides):
    defaults = dict(
        status_flag=StatusFlag(status),
        weight_condition_flag=WeightConditionFlag(condition),
        weight_net_kg=1.0,
        weight_tare_kg=0.5,
        unit_price=2.0,
        total_price=2.0,
        price_base=PriceBase.PER_KG,
        raw_hex="",
    )
    defaults.update(overrides)
    return ScaleReading(**defaults)


def test_derived_booleans_follow_flags():
    r = make_reading(status=0x42, condition=0x43)  # NET; ZERO+STABLE
    assert r.is_net
    assert r.is_stable
    assert r.is_zero
    assert not r.is_negative


def test_overflow_flags():
    r = make_reading(condition=0x48)  # bit3 overflow
    assert r.weight_overflow
    assert not r.weight_underflow
    r = make_reading(condition=0x50)  # bit4 underflow
    assert r.weight_underflow


def test_reading_is_frozen():
    r = make_reading()
    try:
        r.weight_net_kg = 9.9
    except Exception as exc:  # FrozenInstanceError subclasses AttributeError
        assert "assign" in str(exc).lower() or "frozen" in type(exc).__name__.lower()
    else:
        raise AssertionError("ScaleReading should be immutable")


def test_as_dict_is_json_friendly():
    import json

    r = make_reading(weight_net_kg=None)
    d = r.as_dict()
    assert d["weight_net_kg"] is None
    assert d["price_base"] == "$/kg"
    # must round-trip through json without custom encoders
    assert json.loads(json.dumps(d))["is_stable"] == r.is_stable


def test_str_handles_none_values():
    r = make_reading(weight_net_kg=None, unit_price=None)
    text = str(r)
    assert "--" in text  # None rendered as placeholder, not a crash


def test_price_base_str():
    assert str(PriceBase.PER_LB) == "$/lb"
