# Datasheets & protocol notes

Reference material for the scales pydigi talks to.

| File | What it is |
|---|---|
| [DIGI-RS232-PROTOCOL.md](DIGI-RS232-PROTOCOL.md) | Human-readable transcription of the DS-781 **Type B** serial protocol: frame layout, status/condition flags, field formats, worked examples. This is the source of truth the parser is built against. |
| [DS-781_Communication.pdf](DS-781_Communication.pdf) | Original DIGI DS-781 communication datasheet (vendor PDF). |

## Notes for implementers

- Only **Type B (Standard command)** is documented and implemented. Type A/C
  would each be a new `Protocol` subclass — see [../DESIGN.md](../DESIGN.md).
- The **additional-parity** byte's exact computation is not specified in the
  material we have (only the collision-avoidance substitution is). pydigi reads
  and skips it rather than guessing a validation — tracked as a known gap in
  DESIGN.md §9.
- The datasheet transcription renders the price base `$/lb` as `$/1b` in one
  place (OCR artifact); pydigi uses the corrected `PriceBase` enum.
