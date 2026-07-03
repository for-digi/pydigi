# PyDIGI — Design Notes

This document records the architecture of `pydigi` and, more importantly, *why*
each decision was made. Read it before extending the library so you extend it
along the grain rather than against it.

## 1. Goals

1. Read weight / price / status from DIGI retail scales over RS-232.
2. Be **easy to read and extend** — a maintenance engineer should understand a
   frame parser without a datasheet open on the other monitor.
3. Be **testable without hardware**, so unit and CI tests run anywhere.
4. Be **extensible to more DIGI models and protocol variants** (Type A/B/C)
   without rewriting the client.
5. Ship both a **library** and a small **`pydigi` CLI**.

## 2. Scope & the DIGI protocol

DIGI scales speak a family of serial protocols. The DS-781 datasheet
(`doc/DS-781_Communication.pdf`, transcribed in
`doc/DIGI-RS232-PROTOCOL.md`) documents **Type B (Standard command)**:

- **Polled / command-response.** The scale is silent until the host sends one
  `ENQ` byte (`0x05`); it then replies with a 37-byte frame (38 with the
  optional additional-parity byte). It never streams on its own.
- Serial defaults: **9600 8N1**, no flow control (3-wire) when `SPEC3.3 = 1`.
- The frame carries net weight, tare weight, unit price, total price, plus two
  flag bytes (status + weight condition).

Only Type B is documented here, so only Type B is *implemented*. The layering
below reserves clean seams for Type A/C and other models when datasheets arrive.

## 3. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| **Python support** | **3.8+** (modern 3 only) | See §8. Old-Python (2.4/2.6/2.7) is impractical and would forbid the readable `dataclasses`/`enum`/`typing` style asked for elsewhere. |
| **Transport** | **Pluggable interface**, pyserial-backed default + in-memory loopback | Lets unit tests run with no hardware; opens the door to TCP/serial-bridge backends. |
| **Scope** | **Framework**, DS-781 as first concrete model | Protocol / transport / model are separate layers; adding a model or Type is additive, not invasive. |
| **Distribution** | **Library + `pydigi` CLI**, published to [PyPI](https://pypi.org/project/pydigi/); Docker build also emits artifacts to a local `dist/` | `pip install pydigi`; releases cut by the GitHub Actions workflow. |

## 4. Architecture — three layers plus glue

```
            ┌─────────────────────────────────────────────┐
   CLI ───► │                  Scale                       │  ← client / orchestration
            │  read() · stream() · watch() · retries       │
            └───────────────┬───────────────┬─────────────┘
                            │               │
                    uses    │               │  uses
                            ▼               ▼
                  ┌───────────────┐   ┌───────────────┐
                  │   Protocol    │   │   Transport   │
                  │ build request │   │ open/close    │
                  │ read + parse  │   │ read/write    │
                  │ → ScaleReading│   │ reset_input   │
                  └───────┬───────┘   └───────┬───────┘
                          │                   │
              TypeBProtocol             SerialTransport (pyserial)
              (future: A/C)             LoopbackTransport (tests)
                                        (future: TcpTransport)
```

- **`transport.py` — moving bytes.** `Transport` ABC: `open/close/write/read/
  reset_input`, context manager. `SerialTransport` wraps pyserial.
  `LoopbackTransport` replays scripted byte responses for tests and demos.
  Transport knows nothing about frames.
- **`protocol.py` — bytes ⇄ meaning.** `Protocol` ABC: `poll_request() -> bytes`
  and `read_frame(transport) -> bytes` and `parse(raw) -> ScaleReading`.
  `TypeBProtocol` implements the DS-781 framing. Protocol knows nothing about
  serial ports.
- **`reading.py` — the data model.** `ScaleReading` dataclass + `StatusFlag` /
  `WeightConditionFlag` (`IntFlag`) + `PriceBase` enum. Immutable, printable,
  self-describing.
- **`scale.py` — orchestration.** `Scale` binds a `Transport` + `Protocol` +
  `PollPolicy` (retries/timeouts). Public methods: `read`, `stream`, `watch`,
  `open/close`, context manager.
- **`models/` — concrete devices.** A model = a `Protocol` choice + serial
  defaults + a registry name. Models subclass **`ScaleModel`** (`models/base.py`),
  which implements `config`/`bind`/`open` from class attributes, so a new model
  is *data only* — no factory code to re-implement. `DigiDS781` is the first;
  `models.registry` maps `"ds781" -> class`, which the CLI uses for `--model`
  (and `register` rejects nameless models and name collisions).
- **`exceptions.py`** — one hierarchy (see §6).

## 5. Public API (what users import)

```python
from pydigi import DigiDS781, ChangeFilter, Field
from pydigi import PyDigiError, ScaleTimeout, FrameError

# Simplest path — model factory picks protocol + serial defaults:
with DigiDS781.open("/dev/ttyUSB0") as scale:      # single reading
    print(scale.read().weight_net_kg)

    for reading in scale.stream(interval=0.2, count=5):   # next 5 polls
        print(reading.weight_net_kg)

    # change-watch: yields only when a ticked field changes
    watch_weight = ChangeFilter.weight(min_delta_kg=0.002, stable_only=True)
    for reading in scale.watch(interval=0.2, change_filter=watch_weight):
        print("changed:", reading.weight_net_kg)
```

### `read()` vs `stream()` vs `watch()`

- **`read()`** → one `ScaleReading` (one ENQ/response, with retries).
- **`stream(interval, count=None)`** → generator yielding *every* poll. Raw
  continuous reading.
- **`watch(interval, change_filter, ...)`** → generator that yields only when
  the reading **changes** in a field you care about. What counts as a change is
  a `ChangeFilter` — you *tick the fields* to watch:

  ```python
  from pydigi import ChangeFilter, Field

  ChangeFilter.weight(min_delta_kg=0.005, stable_only=True)   # default: net weight only
  ChangeFilter([Field.NET, Field.TARE])                       # weight and tare
  ChangeFilter([Field.UNIT_PRICE, Field.TOTAL_PRICE])         # pricing changes
  ChangeFilter.everything()                                   # any field, incl. flags
  ```

  Weight fields (`NET`/`TARE`/`GROSS`) compare with the `min_delta_kg` tolerance;
  every other field compares exactly. `stable_only` drops unstable readings.
  The default is **weight-only**, so flag- or price-only transitions — like the
  zero-sign flag flipping on an empty pan, which real hardware emits — are
  ignored unless you tick those fields. This is the "data change watch" from the
  roadmap and backs `examples/continuous_reading.py`.

The change decision lives entirely in `ChangeFilter.changed(prev, cur)`, a pure,
I/O-free method, so it is unit-testable on its own. A filter is also callable
(`filter(prev, cur)`).

## 6. Errors

```
PyDigiError                     (base — catch-all)
├── TransportError              (open/read/write failed; wraps serial errors)
│   └── ScaleTimeout            (no bytes within timeout / after retries)
└── FrameError                  (a frame arrived but is malformed)
    ├── ShortFrameError         (fewer bytes than the frame needs)
    ├── HeaderError             (a header/terminator byte was wrong)
    ├── FieldParseError         (a value field isn't valid ASCII decimal)
    └── ParityError             (additional-parity byte mismatch)
```

Rationale: callers can catch `PyDigiError` broadly, `ScaleTimeout` to retry,
or `FrameError` to log-and-skip a garbled frame in a stream without tearing
down the port.

## 7. Edge cases handled (roadmap #5)

- **Optional 38th parity byte.** Frame length depends on status-flag bit 0.
  `read_frame` reads the 37-byte body, inspects bit 0, and reads one more byte
  only when present — no fixed over-read, no under-read.
- **Overflow / underflow / blank fields.** `OF`, `UF`, and all-spaces value
  fields parse to `None` (not `0.0`), and the relevant condition flags are
  surfaced as booleans on the reading.
- **Prices: zero vs absent.** A *blank* price field (all spaces — e.g. total
  price during an overflow) parses to `None`. A transmitted **zero**, which is
  what the scale sends when no PLU is programmed, stays `0.0` (a real value). So
  `None` means "not sent", not "zero" — verified against a real no-PLU capture.
- **Gross weight isn't transmitted** — it is derived as `net + tare` and is
  `None` if either operand is `None`.
- **Partial / multi-frame reads.** The protocol reads exactly one frame by
  structure (body + optional parity), not a fixed `read(64)` that could split or
  merge frames.
- **Price base OCR fix.** The datasheet transcription rendered `$/lb` as `$/1b`;
  we use a typed `PriceBase` enum (`PER_KG`, `PER_100G`, `PER_LB`,
  `PER_QUARTER_LB`) with clean labels.
- **Parity algorithm underspecified.** The datasheet gives the collision
  substitution but not the exact parity computation, so the appended byte is
  read and skipped, **not verified**. `ParityError` is defined and reserved for
  when the algorithm is known (see §9); we don't guess a check that could reject
  valid frames.

## 8. Python support — why 3.8+ only

The roadmap asked to *try* 2.4 / 2.6 / 2.7 and to explain if not possible. It is
not practical:

- **pyserial**: the maintained line (3.x) requires **2.7+/3.4+**; there is no
  supported pyserial on 2.4/2.6.
- **Language/stdlib**: 2.4 predates the `with` statement, `bytearray`, the
  `bytes` type, `enum`, and modern `str.format`; 2.6 lacks `enum`, dict/set
  comprehensions land at 2.7, etc. A single readable source across 2.4→3.13 is
  not achievable without heavy compatibility shims that fight goal #2.
- **Readability**: the chosen model (`dataclasses`, `enum.IntFlag`, type hints)
  is what makes the parser legible. Those require 3.7+.

**Decision: target CPython 3.8–3.13** (3.8 chosen as floor: it has
`dataclasses`, positional-only-free typing, and is the oldest 3.x still seen in
the field). The pure-parsing layer avoids 3.10+-only syntax so the floor could
later drop to 3.7 if ever needed. Genuine 2.x support would mean a separate,
vendored build with its own old pyserial pin and compatibility shims — out of
scope for this codebase, not a supported configuration.

## 9. Known gaps / future work

- **Additional-parity validation** — needs the exact algorithm from DIGI;
  currently parsed and skipped, not verified.
- **Type A / Type C protocols** and **more models** — add a `Protocol` subclass
  and a `models/` entry; no client changes required.
- **Command-response assumption (conscious boundary).** `Scale.read()` is a
  poll: `reset_input` → send `poll_request` → read one frame. This fits Type B
  perfectly. A *streaming* protocol (a scale that pushes frames unprompted)
  would not — it needs a "read mode" abstraction on `Scale` rather than a poll
  per reading. We chose not to build that speculatively for a format we can't
  test; the `Protocol` seam already isolates framing, so adding it later means
  extending `Scale`, not rewriting the parser, transport, or models.
- **Async transport** — the layering permits an async `Scale` later; not built.

## 10. Testing strategy (roadmap #2–#4)

- **Unit** (`tests/`): frame parsing against captured/synthetic frames, flag
  decoding, change-watch predicate, error paths — all via `LoopbackTransport`,
  zero hardware, run on every push.
- **Cross-platform** (roadmap #3): tests avoid OS-specific paths; the transport
  seam means no real serial device is touched. The GitHub Actions matrix
  (`.github/workflows/test.yml`) runs the suite on Linux/macOS/Windows across
  3.8–3.13, alongside a `pyflakes` lint.
- **HIL** (`tests/hil/`, roadmap #4): opt-in (`PYDIGI_HIL_PORT=...`), prompts the
  operator through manual steps ("place the 100 g reference weight", "clear the
  pan") and asserts the scale's readings track reality. Skipped by default.
- **Recorded-frame corpus**: real frames captured from hardware live in
  `tests/hil/dumps/<model>/` and are replayed through the current parser in the
  hardware-free suite (`tests/hil/test_replay_dumps.py`), so real-world decoding
  is a permanent regression guard. Declared as a data-driven case matrix
  (`tests/hil/cases.yaml`); see TESTING.md.

## 11. Build & packaging (roadmap #13)

`pyproject.toml` defines the `pydigi` package, the `pydigi` console entry point,
and the pyserial dependency (version comes from `pydigi/version.py`).

pydigi is **pure Python and ships a wheel only** — no sdist. A `py3-none-any`
wheel installs on every OS and every supported Python, so the sdist's usual role
(building on a platform without a matching wheel) never applies; the full source
lives on GitHub, so there's no `MANIFEST.in` and no design docs, datasheets, or
examples inside the distribution. `Dockerfile` builds the wheel in an isolated
image and `scripts/docker-build.sh` copies it to the host `dist/`. Releases are
published to PyPI by `.github/workflows/release.yml` (trusted publishing / OIDC)
when `version.py` moves to an untagged version; the same run tags the commit and
attaches the wheel to a GitHub release.
