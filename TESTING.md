# Testing pydigi

pydigi is tested in two tiers:

| Tier | What it is | Needs hardware? | When it runs |
|---|---|---|---|
| **SIL** — software-in-the-loop | The automated suite. Drives the whole library through an in-memory `LoopbackTransport`, so no serial port is ever opened. | No | Every change / CI |
| **HIL** — hardware-in-the-loop | Operator-guided tests against a real DIGI DS-781: place weights, tare, vary the load. | Yes (a scale) | On demand, by a person |

The two tiers share the same code paths — HIL uses a real `SerialTransport`
where SIL uses `LoopbackTransport` — so a green SIL run means the parsing,
watching, and CLI logic is already exercised; HIL confirms it against physical
reality (timing, real frames, the scale's own arithmetic).

---

## Running the SIL tests

Everything runs with no hardware and finishes in well under a second.

```bash
make test                       # or:
.virtualenv/bin/python -m pytest
```

Useful variants:

```bash
.virtualenv/bin/python -m pytest -q                 # quiet
.virtualenv/bin/python -m pytest -k tare            # only tests matching "tare"
.virtualenv/bin/python -m pytest tests/test_cli.py  # one file
```

The SIL suite covers frame parsing and framing edge cases, the reading model,
tare/net semantics, the transport layer, the `ChangeFilter` change-watch logic,
the CLI, and cross-platform behaviour — all against synthetic frames. It **also
replays any recorded HIL dumps** (see "Recorded HIL" below) through the current
parser, so real captured frames become permanent regression cases. You do not
need to know the individual tests to run them; the command above runs them all.
Interactive HIL tests are collected too but **skip automatically** unless a scale
is configured (see below), so a plain `pytest` run is always safe.

---

There are two ways to test against real hardware, and they are complementary:

- **Interactive HIL** (below) — live assertions against the scale *right now*.
  Best for a quick end-to-end confidence check, and it exercises the live client
  (polling, retries, `watch()`/`stream()` timing) that a recording can't.
- **Recorded HIL** (further below) — a declarative case matrix you record into
  frame dumps, which then replay in the hardware-free suite forever. Best for
  covering many scenarios and building a regression corpus.

---

## Interactive HIL tests

These require a real scale and a person to follow prompts. They live in
[tests/hil/test_hil_ds781.py](tests/hil/test_hil_ds781.py) and are **skipped**
unless `PYDIGI_HIL_PORT` is set.

### 1. Prepare

- A DIGI DS-781 powered on and connected via an RS-232/USB serial adapter.
- A **reference weight** of known mass (default 100 g).
- A small **empty container** (for the tare test).
- Optional: a **PLU / unit price** programmed on the scale (for the price tests).

### 2. Configure

| Variable | Default | Purpose |
|---|---|---|
| `PYDIGI_HIL_PORT` | — (**required**) | Serial device, e.g. `/dev/ttyUSB0`, `/dev/cu.usbserial-XXXX`, `COM3`. |
| `PYDIGI_HIL_BAUD` | `9600` | Baud rate. |
| `PYDIGI_HIL_REF_KG` | `0.100` | Mass of your reference weight (kg). |
| `PYDIGI_HIL_TOLERANCE_KG` | `0.02` | Accepted weight error (kg). |
| `PYDIGI_HIL_STREAM_COUNT` | `20` | Readings to collect in HIL-06. |
| `PYDIGI_HIL_TEST_PRICE_CHANGE` | off | `1`/`true`/`yes`/`on` to also run HIL-08. |

### 3. Run

```bash
PYDIGI_HIL_PORT=/dev/cu.usbserial-111420 PYDIGI_HIL_REF_KG=0.134 \
PYDIGI_HIL_TOLERANCE_KG=0.01 \
.virtualenv/bin/python -m pytest tests/hil -s -v
```

- **`-s` is required** — the tests prompt you and wait for Enter; without `-s`
  pytest swallows the prompts.
- `-v` prints each `HIL-NN` id as it runs.
- Run a single test with `-k test_04` (the tare workflow), etc.

Each test prints a banner (`========== HIL-04: tare workflow ==========`) and
**every test first returns the scale to a clean baseline** — because pytest may
run them in any order and they share one physical scale, no test assumes what a
previous one left on the pan.

### 4. The procedure, step by step

Follow the on-screen prompts; this is what each test asks of you and what it
asserts. `REF` = your reference weight, `TOL` = tolerance.

**HIL-01 — connect + read.** _No action._ Confirms the scale answers `ENQ` with
a parseable frame.
Pass: a frame comes back.

**HIL-02 — empty pan reads ~0.**
1. Remove everything from the pan and cancel any tare (ZERO/CLEAR) → clean zero.

Pass: gross weight within ±TOL of 0.

**HIL-03 — reference weight.**
1. Baseline reset (clear pan + tare).
2. Place `REF` directly on the pan — no container, no tare.

Pass: gross ≈ `REF` within ±TOL.

**HIL-04 — tare workflow.**
1. Baseline reset.
2. Place an **empty container**, then press **TARE** (NET turns on, display re-zeros).
   → asserts NET mode active, net ≈ 0, tare > 0.
3. Leaving the container, add `REF` **into** it.
   → asserts net ≈ `REF`, and gross = net + tare.

Pass: all of the above.

**HIL-05 — total-price consistency.**
1. Baseline reset.
2. Make sure a **PLU / unit price is selected**, then place `REF` (or any priced item).

Pass: `total_price` ≈ `net × unit_price` (accounting for the price base).
_Skips_ if no unit price is programmed.

**HIL-06 — continuous load.**
1. Baseline reset.
2. Place a load and keep changing it **slowly and continuously** (pour in/out, or
   press gently) until the readings are collected (`PYDIGI_HIL_STREAM_COUNT`).

Pass: most frames parse and the observed weight spread exceeds TOL — i.e. the
stream tracked a changing load.

**HIL-07 — change watch.**
1. Baseline reset.
2. Place a load, let it **settle**, then remove it; repeat with different items
   until 4 distinct settled weights are captured.

Pass: exactly 4 changes reported, and the weights actually differ (a zero-sign
flag flip on the empty pan must **not** count — this verifies the weight-only
`ChangeFilter`).

**HIL-08 — unit-price change.** _(opt-in: `PYDIGI_HIL_TEST_PRICE_CHANGE=1`)_
1. Make sure a PLU / unit price is selected.
2. When prompted, **change** the unit price (select a different PLU or edit it).

Pass: the new `unit_price` differs from the first reading.
_Skips_ unless opted in and a price is programmed. It is opt-in because it
**mutates the scale's programmed state**, which you must restore afterwards.

---

## Recorded HIL: the case matrix

For breadth — many scenarios, different weights, positive and negative — the HIL
cases are **declared as data** in [tests/hil/cases.yaml](tests/hil/cases.yaml)
and turned into replayable frame dumps. This scales far better than one hand
written test per scenario, and every recording becomes a permanent regression
case in the hardware-free suite.

### The matrix

Edit the `weights:` block in `cases.yaml` to the masses you actually own; cases
refer to them by name (`small`, `medium`, ...), so the matrix adapts to your kit.

| Case | Polarity | Verifies |
|---|---|---|
| `P01-empty-pan` | + | empty pan reads ~0 |
| `P02-ref-small` / `P03-ref-medium` / `P04-ref-large` | + | different reference weights read back within tolerance |
| `P05-tare-container` | + | tare a container, goods read as net |
| `P06-pricing` | + | total = net × unit price (needs a PLU) |
| `P07-continuous-ramp` | + | a continuously varied load is tracked |
| `N01-overload` | − | over-capacity load is flagged (optional) |
| `N02-negative-net` | − | removing a tared container → negative net |
| `N03-motion-unstable` | − | a moving load reads not-stable |
| `N04-no-plu` | − | no PLU → prices absent |
| `EXAMPLE-synthetic` | + | synthetic frame; validates the pipeline in CI (no hardware) |

Run `python scripts/hil_record.py --list` for the live list, and open
`cases.yaml` for each case's exact steps and expectations.

### Record (the timed recorder)

[scripts/hil_record.py](scripts/hil_record.py) walks you through a case with
**timed, on-screen instructions** (a countdown per step), captures the scale's
real frames during each `record` window, checks them against the case's
expectations for immediate PASS/FAIL, and writes a dump under the model's
folder `tests/hil/dumps/<model>/` (dumps are per-model artifacts).

```bash
pip install '.[hil]'                             # PyYAML for the case files

python scripts/hil_record.py --list              # show the matrix
python scripts/hil_record.py --all --dry-run     # rehearse prompts, no scale
python scripts/hil_record.py --port /dev/ttyUSB0 --all          # record all
python scripts/hil_record.py --port /dev/ttyUSB0 --case P02-ref-small
```

Before each case you get `[Enter] record / [s] skip / [q] quit`. Dumps land in
[tests/hil/dumps/](tests/hil/dumps/) under a model subfolder (e.g. `ds781/`),
one JSON per case, and are committed.

### Replay (hardware-free, in CI)

[tests/hil/test_replay_dumps.py](tests/hil/test_replay_dumps.py) re-parses every
committed dump with the current parser and re-checks its expectations — no scale
needed. It runs as part of `make test`. A change that breaks real-frame decoding
fails here.

---

## Managing HIL tests: plot → code → do

Adding or changing HIL coverage follows one loop:

### Plot — design the case as data
Add an entry to [cases.yaml](tests/hil/cases.yaml). Decide, on paper first:
- **Intent & polarity:** the one property, positive or negative.
- **Weights:** which reference masses it needs (add them to `weights:`).
- **Steps:** the operator actions as `{say, wait}` / `{say, record}`, always
  opening with a baseline reset instruction.
- **Expectations:** the machine-checkable `expect:` block (see the vocabulary at
  the top of `cases.yaml`) and its tolerance.
- **Skip conditions:** `requires_plu`, `optional`.

### Code — only if a new *kind* of check is needed
The declarative case usually needs no code. If you introduced a new expectation
keyword, implement it once in [tests/hil/hilkit.py](tests/hil/hilkit.py)
(`check()`), which both the recorder and the replay test share, so live and
replayed results stay identical by construction.

### Do — record, verify, commit
- `python scripts/hil_record.py --port … --case <id>` and follow the timed
  prompts; read the live PASS/FAIL.
- On failure decide **hardware** (wrong weight, drift, loose cable) vs **code**
  (bad offset/tolerance/expectation).
- Commit the dump under `tests/hil/dumps/<model>/`. From then on the case is enforced in
  CI via the replay test — traceable by its case id, no scale required.

---

## Review & suggested improvements

The current split (fast SIL everywhere + interactive & recorded HIL) is sound.
Worth adding as the project grows:

1. **CI matrix.** A `tox.ini` / GitHub Actions job running the SIL suite on
   CPython 3.8–3.13 and on Linux/macOS/Windows would make the "cross-platform,
   all 3.x" claim real rather than aspirational. *(Planned as the next step.)*
2. **Golden real-frame corpus.** *(Done — the recorded-HIL matrix, dumps, and
   the replay test.)* Grow it by recording the real cases on hardware and
   committing their dumps.
3. **Coverage + lint.** `pytest --cov` to find untested branches, and `ruff`/
   `flake8` in CI.
4. **Property-based parsing tests** (`hypothesis`) to fuzz value fields and
   malformed frames beyond the hand-picked cases.
5. **Additional-parity validation** once DIGI's exact algorithm is known (see
   [DESIGN.md](DESIGN.md) §9) — then add a HIL check that a parity-bearing frame
   verifies.
