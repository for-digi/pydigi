# Recorded HIL frame dumps

Dumps are **per-model artifacts** — a DS-781 Type B frame is not the same as any
other model's — so they are stored one directory per model:

```
dumps/
  <model>/            e.g. ds781/  (from `meta.model` in ../cases.yaml)
    <case-id>.json
```

Each `*.json` is a capture of real (or, for `EXAMPLE-synthetic`, synthetic)
frames for one case in [../cases.yaml](../cases.yaml), written by
[scripts/hil_record.py](../../../scripts/hil_record.py) into the model's folder.

They are **committed on purpose**: [../test_replay_dumps.py](../test_replay_dumps.py)
resolves the model's dump directory from the catalogue and replays every dump
through the parser in the normal (hardware-free) suite, so a change that breaks
real-frame decoding is caught without a scale attached.

Format (one file per case):

```json
{
  "case_id": "P02-ref-small",
  "title": "...",
  "polarity": "positive",
  "model": "ds781",
  "port": "/dev/ttyUSB0",
  "recorded_at": "2026-07-03T16:40:00",
  "frames": [
    {"t": 0.0, "raw_hex": "4242...0a", "parsed": { ... }},
    {"t": 0.1, "error": "..."}
  ]
}
```

`raw_hex` is the source of truth (re-parsed on replay); `parsed` is a convenience
snapshot. To (re)record, see [../../../TESTING.md](../../../TESTING.md).
