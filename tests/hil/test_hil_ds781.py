"""Hardware-in-the-loop tests for a real DIGI DS-781 (roadmap #4).

These talk to a physical scale and walk the operator through manual steps. They
are **skipped** unless a port is provided, so the normal suite stays
hardware-free.

Run them with::

    PYDIGI_HIL_PORT=/dev/ttyUSB0 .virtualenv/bin/python -m pytest tests/hil -s

``-s`` is required so the prompts reach your terminal. Add ``-v`` to see the IDs.

Test catalogue (each prints its ``HIL-NN`` id as a banner):

    HIL-01  connect + read           scale answers ENQ with a parseable frame
    HIL-02  empty pan                 clean zero reads ~0
    HIL-03  reference weight          a known weight reads back within tolerance
    HIL-04  tare workflow             tare a container, added goods read as net
    HIL-05  total-price consistency   total == net x unit price (needs a PLU)
    HIL-06  continuous load           stream() tracks a continuously varied load
    HIL-07  change watch              watch() fires once per distinct settled weight
    HIL-08  unit-price change         reprogramming the price shows up (opt-in)

IMPORTANT: the tests share one physical scale, and pytest may run them in any
order. So **every test begins by resetting the scale to a known baseline** and
never assumes what a previous test left on the pan.

Reference any test in conversation by its id (e.g. "HIL-05 skipped") or its
pytest node id (``tests/hil/test_hil_ds781.py::test_05_total_price_consistency``).

Environment knobs:
    PYDIGI_HIL_PORT              serial device of the scale (required to run)
    PYDIGI_HIL_BAUD             baud rate (default 9600)
    PYDIGI_HIL_REF_KG           mass of your reference weight (default 0.100)
    PYDIGI_HIL_TOLERANCE_KG     accepted weight error (default 0.02 = 20 g)
    PYDIGI_HIL_STREAM_COUNT     readings for HIL-06 (default 20)
    PYDIGI_HIL_TEST_PRICE_CHANGE  1/true/yes/on to also run HIL-08 (reprograms
                                  the unit price)
"""

import os

import pytest

from pydigi import DigiDS781, PriceBase, ChangeFilter


def _env_flag(name):
    """True only for genuine truthy values, so FOO=0 / FOO=false mean off."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


HIL_PORT = os.environ.get("PYDIGI_HIL_PORT")
HIL_BAUD = int(os.environ.get("PYDIGI_HIL_BAUD", "9600"))
REF_KG = float(os.environ.get("PYDIGI_HIL_REF_KG", "0.100"))
TOLERANCE_KG = float(os.environ.get("PYDIGI_HIL_TOLERANCE_KG", "0.02"))
STREAM_COUNT = int(os.environ.get("PYDIGI_HIL_STREAM_COUNT", "20"))
RUN_PRICE_CHANGE = _env_flag("PYDIGI_HIL_TEST_PRICE_CHANGE")

_KG_PER_LB = 0.45359237
_REF_G = REF_KG * 1000

pytestmark = pytest.mark.skipif(
    not HIL_PORT,
    reason="set PYDIGI_HIL_PORT (and run with -s) to exercise real hardware",
)


def _banner(test_id, title):
    """Print the test's id so runs and prompts are easy to reference."""
    print("\n========== %s: %s ==========" % (test_id, title))


def _prompt(message):
    """Ask the operator to do something and wait for Enter."""
    input("\n>>> %s — then press Enter... " % message)


def _prompt_baseline():
    """Return the scale to a clean, un-tared zero before a test starts."""
    _prompt("Remove EVERYTHING from the pan and cancel any tare "
            "(press ZERO/CLEAR) so the display reads a clean zero")


def _read_stable(scale, tries=50):
    """Poll until the scale reports a stable reading (or give up)."""
    reading = None
    for _ in range(tries):
        reading = scale.read()
        if reading.is_stable:
            return reading
    return reading  # last one, even if never settled


def _expected_total(reading):
    """Total price the scale *should* show, from net weight and unit price.

    Accounts for the price base. Returns None if either operand is missing.
    """
    net, unit, base = reading.weight_net_kg, reading.unit_price, reading.price_base
    if net is None or unit is None:
        return None
    if base is PriceBase.PER_KG:
        return net * unit
    if base is PriceBase.PER_100G:
        return net * 10.0 * unit
    if base is PriceBase.PER_LB:
        return (net / _KG_PER_LB) * unit
    if base is PriceBase.PER_QUARTER_LB:
        return (net / (_KG_PER_LB / 4.0)) * unit
    return None


@pytest.fixture
def scale():
    with DigiDS781.open(HIL_PORT, baudrate=HIL_BAUD) as connected:
        yield connected


def test_01_connect_and_read(scale):
    """HIL-01: the scale answers ENQ with a parseable frame."""
    _banner("HIL-01", "connect + read")
    reading = scale.read()
    print("Initial reading:", reading)
    assert reading.raw_hex, "expected a raw frame from the scale"


def test_02_empty_pan_reads_near_zero(scale):
    """HIL-02: a clean, un-tared pan reads ~0."""
    _banner("HIL-02", "empty pan reads ~0")
    _prompt_baseline()
    reading = _read_stable(scale)
    print("Empty-pan reading:", reading)
    assert reading.weight_gross_kg is not None
    assert abs(reading.weight_gross_kg) <= TOLERANCE_KG, (
        "empty pan should read ~0, got %.3f kg" % reading.weight_gross_kg
    )


def test_03_reference_weight(scale):
    """HIL-03: a known weight placed directly on the pan reads back correctly."""
    _banner("HIL-03", "reference weight")
    _prompt_baseline()
    _read_stable(scale)
    _prompt("Place the %.0f g reference weight DIRECTLY on the pan "
            "(no container, no tare)" % _REF_G)
    reading = _read_stable(scale)
    print("Reference reading:", reading)
    assert reading.weight_gross_kg is not None
    assert abs(reading.weight_gross_kg - REF_KG) <= TOLERANCE_KG, (
        "expected ~%.3f kg, got %.3f kg" % (REF_KG, reading.weight_gross_kg)
    )


def test_04_tare_workflow(scale):
    """HIL-04: tare a container to zero, then added goods read as net weight.

    Exercises the whole tare path: the NET flag, the stored tare value, and the
    gross = net + tare relationship, end to end.
    """
    _banner("HIL-04", "tare workflow")
    _prompt_baseline()
    _read_stable(scale)

    _prompt("Place an EMPTY container on the pan, then press TARE "
            "(the NET indicator turns on and the display returns to zero)")
    tared = _read_stable(scale)
    print("After taring the container:", tared)
    assert tared.is_net, "expected NET mode (tare active) after taring"
    assert tared.weight_net_kg is not None
    assert abs(tared.weight_net_kg) <= TOLERANCE_KG, (
        "net should be ~0 right after taring, got %.3f kg" % tared.weight_net_kg
    )
    assert tared.weight_tare_kg and tared.weight_tare_kg > 0, (
        "tare weight should reflect the container mass, got %s" % tared.weight_tare_kg
    )

    _prompt("Leaving the container in place, add the %.0f g reference weight "
            "INTO the container" % _REF_G)
    loaded = _read_stable(scale)
    print("After adding the load:", loaded)
    assert loaded.weight_net_kg is not None
    assert abs(loaded.weight_net_kg - REF_KG) <= TOLERANCE_KG, (
        "net should equal the added goods (%.3f kg), got %.3f kg"
        % (REF_KG, loaded.weight_net_kg)
    )
    assert loaded.weight_gross_kg is not None
    assert abs(loaded.weight_gross_kg - (loaded.weight_net_kg + loaded.weight_tare_kg)) <= 1e-6


def test_05_total_price_consistency(scale):
    """HIL-05: total_price == net_weight x unit_price (given the price base).

    Cross-checks our field offsets against the scale's own arithmetic. Requires
    a unit price to be programmed (a PLU selected); skips cleanly otherwise.
    """
    _banner("HIL-05", "total-price consistency")
    _prompt_baseline()
    _read_stable(scale)
    _prompt("Make sure a PLU / unit price is selected on the scale, then place "
            "the %.0f g reference weight (or any priced item) on the pan" % _REF_G)
    reading = _read_stable(scale)
    print("Pricing reading:", reading)

    if not reading.unit_price:
        pytest.skip("no unit price programmed (select a PLU on the scale to run HIL-05)")

    expected = _expected_total(reading)
    assert expected is not None
    # Net weight is displayed rounded to ~1 g, so allow that times the unit
    # price, plus a small margin for the scale's own total rounding.
    tolerance = abs(reading.unit_price) * 0.001 + 0.05
    assert abs(reading.total_price - expected) <= tolerance, (
        "total %.3f but net x unit implies %.3f (base %s)"
        % (reading.total_price, expected, reading.price_base)
    )


def test_06_stream_tracks_continuous_load(scale):
    """HIL-06: continuously read while the operator varies the load.

    The "goods are on the scale and measurements track correctly" case: stream()
    must keep producing valid readings that follow a load that is actively
    changing (not just settled discrete weights).
    """
    _banner("HIL-06", "continuous load")
    _prompt_baseline()
    _prompt(
        "Place a load and keep changing it SLOWLY and CONTINUOUSLY "
        "(pour material in/out, or press gently) until %d readings are collected"
        % STREAM_COUNT
    )
    print("Streaming %d readings..." % STREAM_COUNT)
    weights = []
    for reading in scale.stream(interval=0.1, count=STREAM_COUNT, ignore_errors=True):
        assert reading.raw_hex, "every streamed reading should carry a raw frame"
        if reading.weight_gross_kg is not None:
            weights.append(reading.weight_gross_kg)
    print("  collected %d weights, range %.3f..%.3f kg"
          % (len(weights), min(weights), max(weights)))

    assert len(weights) >= STREAM_COUNT // 2, "too many unreadable frames"
    spread = max(weights) - min(weights)
    assert spread > TOLERANCE_KG, (
        "expected the load to vary during streaming; saw only %.3f kg spread" % spread
    )


def test_07_watch_detects_distinct_weights(scale):
    """HIL-07: the change-watch fires once per distinct settled weight.

    Uses a weight-only ChangeFilter so only actual weight moves count — a
    zero-sign flag flip on an empty pan must NOT be reported as a change.
    """
    _banner("HIL-07", "change watch")
    _prompt_baseline()
    print(
        "\nNow place a load, let it SETTLE, then remove it — repeat with "
        "different items. Watching for 4 distinct settled weights..."
    )
    changes = []
    weight_changes = ChangeFilter.weight(min_delta_kg=0.01, stable_only=True)
    for reading in scale.watch(interval=0.2, change_filter=weight_changes, count=4):
        print("  change #%d: %.3f kg" % (len(changes) + 1, reading.weight_gross_kg or 0.0))
        changes.append(reading)

    assert len(changes) == 4
    weights = [round(c.weight_gross_kg, 3) for c in changes if c.weight_gross_kg is not None]
    assert len(set(weights)) > 1, "expected the reported weights to actually differ"


@pytest.mark.skipif(
    not RUN_PRICE_CHANGE,
    reason="set PYDIGI_HIL_TEST_PRICE_CHANGE=1 to run HIL-08 (it reprograms the price)",
)
def test_08_unit_price_change_is_detected(scale):
    """HIL-08: changing the programmed unit price shows up in the next reading."""
    _banner("HIL-08", "unit-price change")
    _prompt("Make sure a PLU / unit price is selected on the scale")
    before = _read_stable(scale)
    if not before.unit_price:
        pytest.skip("no unit price programmed to change (select a PLU first)")
    print("Unit price before: %s" % before.unit_price)

    _prompt("Change the scale's unit price (select a different PLU or edit it)")
    after = _read_stable(scale)
    print("Unit price after:  %s" % after.unit_price)

    assert after.unit_price is not None
    assert after.unit_price != before.unit_price, (
        "unit price did not change: still %s" % after.unit_price
    )
