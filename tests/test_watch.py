"""The ChangeFilter change-detection logic behind Scale.watch."""

import pytest

from pydigi import ChangeFilter, Field
from test_reading import make_reading


def test_first_reading_always_reported():
    assert ChangeFilter.weight().changed(None, make_reading()) is True


def test_no_change_not_reported():
    a = make_reading(weight_net_kg=1.0)
    b = make_reading(weight_net_kg=1.0)
    assert ChangeFilter.weight().changed(a, b) is False


def test_weight_move_reported():
    a = make_reading(weight_net_kg=1.000)
    b = make_reading(weight_net_kg=1.005)
    assert ChangeFilter.weight().changed(a, b) is True


def test_min_delta_debounces_small_moves():
    f = ChangeFilter.weight(min_delta_kg=0.005)
    a = make_reading(weight_net_kg=1.000)
    assert f.changed(a, make_reading(weight_net_kg=1.003)) is False
    assert f.changed(a, make_reading(weight_net_kg=1.010)) is True


def test_none_transition_reported():
    a = make_reading(weight_net_kg=1.0)
    b = make_reading(weight_net_kg=None)  # went to overflow
    assert ChangeFilter.weight().changed(a, b) is True


def test_stable_only_ignores_unstable():
    f = ChangeFilter.weight(stable_only=True)
    a = make_reading(weight_net_kg=1.0, condition=0x42)   # stable
    b = make_reading(weight_net_kg=2.0, condition=0x40)   # not stable
    assert f.changed(a, b) is False


def test_default_filter_is_weight_only():
    # Same weight, only the zero-sign flag flips (the empty-pan case seen on
    # real hardware). The default (weight) filter must NOT report it.
    a = make_reading(weight_net_kg=0.0, condition=0x42)   # no zero sign
    b = make_reading(weight_net_kg=0.0, condition=0x43)   # zero sign set
    assert ChangeFilter.weight().changed(a, b) is False


def test_everything_filter_reports_flag_flip():
    a = make_reading(weight_net_kg=0.0, condition=0x42)
    b = make_reading(weight_net_kg=0.0, condition=0x43)
    assert ChangeFilter.everything().changed(a, b) is True


def test_tick_specific_fields():
    # Watch tare only: a tare change reports, a net-only change does not.
    f = ChangeFilter([Field.TARE])
    base = make_reading(weight_net_kg=1.0, weight_tare_kg=0.5)
    assert f.changed(base, make_reading(weight_net_kg=1.0, weight_tare_kg=0.7)) is True
    assert f.changed(base, make_reading(weight_net_kg=9.0, weight_tare_kg=0.5)) is False


def test_tick_multiple_fields():
    f = ChangeFilter([Field.NET, Field.UNIT_PRICE])
    base = make_reading(weight_net_kg=1.0, unit_price=2.0)
    assert f.changed(base, make_reading(weight_net_kg=1.0, unit_price=3.0)) is True   # price
    assert f.changed(base, make_reading(weight_net_kg=2.0, unit_price=2.0)) is True   # weight
    assert f.changed(base, make_reading(weight_net_kg=1.0, unit_price=2.0)) is False


def test_price_base_change_reported_when_ticked():
    from pydigi import PriceBase
    f = ChangeFilter([Field.PRICE_BASE])
    a = make_reading(price_base=PriceBase.PER_KG)
    b = make_reading(price_base=PriceBase.PER_LB)
    assert f.changed(a, b) is True


def test_min_delta_applies_to_tare_too():
    f = ChangeFilter([Field.TARE], min_delta_kg=0.01)
    base = make_reading(weight_tare_kg=0.500)
    assert f.changed(base, make_reading(weight_tare_kg=0.505)) is False
    assert f.changed(base, make_reading(weight_tare_kg=0.520)) is True


def test_filter_is_callable():
    f = ChangeFilter.weight()
    a = make_reading(weight_net_kg=1.0)
    b = make_reading(weight_net_kg=2.0)
    assert f(a, b) is True  # __call__ delegates to changed()


def test_unknown_field_rejected():
    with pytest.raises(ValueError):
        ChangeFilter(["not_a_field"])


def test_empty_filter_rejected():
    with pytest.raises(ValueError):
        ChangeFilter([])
