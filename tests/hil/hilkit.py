"""Shared toolkit for the data-driven HIL cases.

Loads the case matrix (``cases.yaml``), reads/writes frame dumps, and checks a
list of readings against a case's declared expectations. Used by both the
recorder (``scripts/hil_record.py``) for live pass/fail feedback and the SIL
replay test (``test_replay_dumps.py``) so the two agree by construction.
"""

import json
import os
from datetime import datetime

from pydigi import TypeBProtocol, PriceBase
from pydigi.exceptions import PyDigiError

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASES = os.path.join(HERE, "cases.yaml")

# Dumps are per-model artifacts (a DS-781 frame is not a DS-782 frame), so they
# live under a model-named subdirectory of this root.
DUMPS_ROOT = os.path.join(HERE, "dumps")


def model_dumps_dir(catalog, root=DUMPS_ROOT):
    """Directory holding the dumps for the catalogue's model, e.g. dumps/ds781."""
    return os.path.join(root, catalog.model)

_KG_PER_LB = 0.45359237


# --- catalogue ------------------------------------------------------------

class Case(object):
    def __init__(self, raw, catalog):
        self.raw = raw
        self.catalog = catalog
        self.id = raw["id"]
        self.title = raw.get("title", "")
        self.polarity = raw.get("polarity", "positive")
        self.steps = raw.get("steps", [])
        self.expect = raw.get("expect", {})
        self.requires_weight = raw.get("requires_weight")
        self.requires_plu = raw.get("requires_plu", False)
        self.optional = raw.get("optional", False)
        self.synthetic = raw.get("synthetic", False)
        self.tags = raw.get("tags", [])
        self.prerequisites = raw.get("prerequisites", [])

    def all_prerequisites(self):
        """Everything the operator must gather, structured + free-text.

        Derived from the declared fields so cases don't have to restate what is
        already implied by ``requires_weight`` / ``requires_plu``.
        """
        items = []
        if self.required_mass() is not None:
            items.append("reference weight '%s' = %.3f kg"
                         % (self.requires_weight, self.required_mass()))
        items.extend(self.prerequisites)
        if self.requires_plu:
            items.append("a PLU / unit price programmed on the scale")
        return items

    def setting(self, key):
        """A per-case override, falling back to the catalogue defaults."""
        if key in self.raw:
            return self.raw[key]
        return self.catalog.defaults.get(key)

    def required_mass(self):
        if self.requires_weight is None:
            return None
        return self.catalog.weights.get(self.requires_weight)


class Catalog(object):
    def __init__(self, data):
        self.weights = data.get("weights", {})
        self.defaults = data.get("defaults", {})
        self.meta = data.get("meta", {})
        self.model = self.meta.get("model", "unknown")
        self.cases = [Case(c, self) for c in data.get("cases", [])]

    def get(self, case_id):
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError("no such case: %s" % case_id)


def load_catalog(path=DEFAULT_CASES):
    import yaml  # optional dep; only HIL tooling needs it
    with open(path) as handle:
        return Catalog(yaml.safe_load(handle))


# --- dumps ----------------------------------------------------------------

def dump_path(case_id, dumps_dir):
    """Path to a case's dump inside an already model-scoped ``dumps_dir``."""
    return os.path.join(dumps_dir, case_id + ".json")


def write_dump(case, frames, port, dumps_dir):
    if not os.path.isdir(dumps_dir):
        os.makedirs(dumps_dir)
    payload = {
        "case_id": case.id,
        "title": case.title,
        "polarity": case.polarity,
        "model": case.catalog.model,
        "port": port,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "frames": frames,
    }
    path = dump_path(case.id, dumps_dir)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    return path


def read_dump(path):
    with open(path) as handle:
        return json.load(handle)


def readings_from_frames(frames):
    """Re-parse the raw hex in a frame list into ScaleReading objects.

    Re-parsing (rather than trusting the stored ``parsed`` block) is deliberate:
    the replay test then exercises the *current* parser against real bytes.
    """
    protocol = TypeBProtocol()
    readings = []
    for frame in frames:
        raw_hex = frame.get("raw_hex")
        if not raw_hex:
            continue
        try:
            readings.append(protocol.parse(bytes.fromhex(raw_hex)))
        except PyDigiError:
            continue  # a garbled frame is not a reading
    return readings


def readings_from_dump(dump):
    return readings_from_frames(dump.get("frames", []))


# --- expectation checking -------------------------------------------------

def _expected_total(reading):
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


def _resolve_near(value, weights):
    """A ``near`` target: a number, or ``{weight: name}`` -> that mass."""
    if isinstance(value, dict):
        if "weight" in value:
            return float(weights[value["weight"]])
        raise ValueError("unsupported near spec: %r" % value)
    return float(value)


def precondition_skip(case, readings):
    """Reason to skip (not fail) this case, or None if it should be checked."""
    if not readings:
        return None
    if case.requires_plu and not readings[-1].unit_price:
        return "case requires a programmed unit price (PLU); none present"
    return None


def check(case, readings):
    """Check ``readings`` against ``case.expect``. Return a list of failures."""
    default_tol = case.setting("tolerance_kg") or 0.02
    return _check_expect(case.expect, readings, case.catalog.weights, default_tol)


def _check_expect(expect, readings, weights, default_tol):
    # Forms that must be handled before the "no readings" guard:
    if expect.get("no_parseable_frames"):
        # Negative case where the scale is expected to go silent (e.g. overload).
        if readings:
            return ["expected no parseable frames, but %d parsed" % len(readings)]
        return []
    if "any_of" in expect:
        # Pass if ANY alternative expectation holds (hardware may behave two ways).
        collected = []
        for alternative in expect["any_of"]:
            failures = _check_expect(alternative, readings, weights, default_tol)
            if not failures:
                return []
            collected.append(failures)
        return ["none of the any_of alternatives held: %s" % collected]

    if not readings:
        return ["no frames were captured or parsed"]

    last = readings[-1]
    failures = []

    def near_check(name, value, spec):
        target = _resolve_near(spec["near"], weights)
        tol = spec.get("tol", default_tol)
        if value is None or abs(value - target) > tol:
            failures.append("%s=%s not within %s of %s" % (name, value, tol, target))

    if "stable" in expect and bool(last.is_stable) != bool(expect["stable"]):
        failures.append("is_stable=%s, expected %s" % (last.is_stable, expect["stable"]))
    if "is_net" in expect and bool(last.is_net) != bool(expect["is_net"]):
        failures.append("is_net=%s, expected %s" % (last.is_net, expect["is_net"]))
    if "is_zero" in expect and bool(last.is_zero) != bool(expect["is_zero"]):
        failures.append("is_zero=%s, expected %s" % (last.is_zero, expect["is_zero"]))
    if "gross_kg" in expect:
        near_check("gross_kg", last.weight_gross_kg, expect["gross_kg"])
    if "net_kg" in expect:
        near_check("net_kg", last.weight_net_kg, expect["net_kg"])
    if "tare_kg_gt" in expect:
        threshold = expect["tare_kg_gt"]
        if last.weight_tare_kg is None or not (last.weight_tare_kg > threshold):
            failures.append("tare_kg=%s, expected > %s" % (last.weight_tare_kg, threshold))
    if expect.get("total_price_consistent"):
        expected = _expected_total(last)
        if last.total_price is None or expected is None:
            failures.append("no price data to check consistency")
        else:
            tol = abs(last.unit_price or 0.0) * 0.001 + 0.05
            if abs(last.total_price - expected) > tol:
                failures.append("total=%s but net x unit implies %.3f" % (last.total_price, expected))
    if expect.get("unit_price_absent"):
        if last.unit_price not in (None, 0, 0.0):
            failures.append("unit_price present (%s), expected absent" % last.unit_price)
    for attr, value in expect.get("any", {}).items():
        if not any(getattr(r, attr) == value for r in readings):
            failures.append("no captured frame had %s == %s" % (attr, value))
    for attr, value in expect.get("all", {}).items():
        if not all(getattr(r, attr) == value for r in readings):
            failures.append("not every captured frame had %s == %s" % (attr, value))
    if "varies_kg_gt" in expect:
        grosses = [r.weight_gross_kg for r in readings if r.weight_gross_kg is not None]
        spread = (max(grosses) - min(grosses)) if len(grosses) >= 2 else 0.0
        if spread <= expect["varies_kg_gt"]:
            failures.append("gross spread %.3f kg, expected > %s" % (spread, expect["varies_kg_gt"]))
    if "min_valid_frames" in expect:
        valid = sum(1 for r in readings if r.weight_gross_kg is not None)
        if valid < expect["min_valid_frames"]:
            failures.append("%d valid frames, expected >= %s" % (valid, expect["min_valid_frames"]))

    return failures
