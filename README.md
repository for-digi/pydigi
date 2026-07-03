# PyDIGI — read DIGI scales from Python

`pydigi` reads weight, price and status from DIGI retail scales over RS-232.

- **Supported models:** DIGI DS-781 (Type B / Standard command protocol).
- **Python:** 3.8+ (see [DESIGN.md §8](DESIGN.md) for why 2.x is out of scope).
- **Dependency:** [pyserial](https://pypi.org/project/pyserial/) (only for real ports).
- Layered so more models, protocol types, and transports slot in **without
  rewrites** — see [Extending](#extending) and [DESIGN.md](DESIGN.md).

## Install

```bash
pip install .                 # library + pyserial
pip install '.[test]'         # + pytest, PyYAML (to run the test suite)
pip install '.[hil]'          # + PyYAML (for the hardware-in-the-loop tooling)
```

Or build a wheel/sdist (see [Development](#development)) and
`pip install dist/pydigi-*.whl`. Not published to PyPI.

## Quick start

```python
from pydigi import DigiDS781

with DigiDS781.open("/dev/ttyUSB0") as scale:      # COM3 on Windows
    r = scale.read()
    print(r.weight_net_kg, "kg", "stable" if r.is_stable else "moving")
```

`DigiDS781.open(port, baudrate=..., parity=..., stopbits=..., timeout=...,
rtscts=...)` — extra keywords pass through to the serial config. `open()`
returns a ready scale and is also a context manager.

## What a reading contains

`scale.read()` returns an immutable `ScaleReading`:

| Field | Meaning |
|---|---|
| `weight_net_kg` / `weight_tare_kg` | net (post-tare) and stored tare weight |
| `weight_gross_kg` | derived `net + tare` (always consistent) |
| `unit_price` / `total_price` | price per `price_base`, and net × unit |
| `price_base` | `PriceBase` enum (`$/kg`, `$/100g`, `$/lb`, `$/(1/4)lb`) |
| `is_stable` `is_net` `is_zero` `is_negative` | condition booleans |
| `weight_overflow` `weight_underflow` `total_price_overflow` | range flags |
| `raw_hex` | the source frame, for diagnostics |

Values the scale did not send (overflow, underflow, no PLU) are **`None`**,
never a fake `0.0`. `reading.as_dict()` gives a JSON-friendly view.

## Continuous reading & change-watch

```python
for reading in scale.stream(interval=0.2):          # every poll
    print(reading.weight_gross_kg)
```

`watch()` yields only when a field you care about changes — you **tick the
fields** with a `ChangeFilter`:

```python
from pydigi import ChangeFilter, Field

watch_weight = ChangeFilter.weight(min_delta_kg=0.005, stable_only=True)  # the default
for reading in scale.watch(interval=0.2, change_filter=watch_weight):
    print("weight ->", reading.weight_gross_kg, "kg")

ChangeFilter([Field.NET, Field.TARE, Field.UNIT_PRICE])   # several fields
ChangeFilter.everything()                                 # any field, flags included
```

For long-running loops, `stream(..., ignore_errors=True, on_error=cb)` keeps
going through transient timeouts instead of raising.

Runnable examples: [single_reading.py](examples/single_reading.py),
[continuous_reading.py](examples/continuous_reading.py), and
[offline_demo.py](examples/offline_demo.py) (no hardware).

## Errors

All exceptions derive from `PyDigiError`:

```
PyDigiError
├── TransportError        # port open/read/write failed
│   └── ScaleTimeout      # no response within timeout / after retries
└── FrameError            # a frame arrived but was malformed
    ├── ShortFrameError · HeaderError · FieldParseError · ParityError
```

Catch `PyDigiError` broadly, `ScaleTimeout` to retry, or `FrameError` to
log-and-skip a garbled frame in a stream without tearing down the port.

## Testing without hardware

The serial layer is a pluggable `Transport`. Swap in `LoopbackTransport` (which
replays canned bytes) and `bind()` to a scale — no port required:

```python
from pydigi import DigiDS781, LoopbackTransport

with DigiDS781.bind(LoopbackTransport(my_frame_bytes)) as scale:
    print(scale.read().weight_net_kg)
```

This is exactly how the test suite runs. A complete, runnable version (which
synthesises frames) is [examples/offline_demo.py](examples/offline_demo.py); the
testing workflow is in [TESTING.md](TESTING.md).

## Command line

```bash
pydigi --port /dev/ttyUSB0 read                       # one reading
pydigi --port /dev/ttyUSB0 read --json                # machine-readable
pydigi --port /dev/ttyUSB0 stream --interval 0.5 --count 10
pydigi --port /dev/ttyUSB0 watch --stable-only        # weight changes only
pydigi --port /dev/ttyUSB0 watch --field tare --field unit-price
pydigi --port /dev/ttyUSB0 watch --all-fields
pydigi --model ds781 --port COM3 read                 # -v / -vv for logging
pydigi list-models
```

## Extending

The library is three seams; a new device touches only one and needs **no changes
to existing code**:

- **New model** (same protocol, different defaults) — subclass `ScaleModel`,
  set the class attributes, `@register`:

  ```python
  from pydigi import ScaleModel, register
  from pydigi import TypeBProtocol

  @register
  class DigiDS782(ScaleModel):
      name = "ds782"
      protocol_class = TypeBProtocol
      default_baudrate = 9600
      max_weight_kg = 15.0
  ```
  `DigiDS782.open(port)` and `pydigi --model ds782` work immediately.

- **New protocol** (Type A/C, another vendor) — subclass `Protocol`
  (`poll_request` / `read_frame` / `parse`) and point a model at it.
- **New transport** (TCP bridge, USB HID) — subclass `Transport` and pass it to
  `Model.bind(transport)`.

Details and rationale in [DESIGN.md](DESIGN.md).

> `Scale` is not thread-safe — a serial port is a single shared resource. Use one
> `Scale` per thread, or guard it with your own lock.

## Development

```bash
make test           # hardware-free test suite
make build          # sdist + wheel into ./dist
make docker-build   # same, isolated in Docker
```

Testing (hardware-free **and** on a real scale) is documented in
[TESTING.md](TESTING.md); architecture in [DESIGN.md](DESIGN.md).

## License

MIT — see [LICENSE](LICENSE).
