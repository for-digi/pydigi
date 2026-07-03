## DIGI DS-781 RS-232 Protocol (Type B — Standard Command)

### Serial Port Settings

| Parameter | Value |
|---|---|
| Baud Rate | 1200 / 2400 / 4800 / **9600** / 19200 / 38400 |
| Data Bits | 7 or **8** |
| Stop Bits | 1 or 2 |
| Parity | Even / Odd / **None** |
| Flow Control | RTS/CTS (only when SPEC3.3 = 0), otherwise **none** |

---

### Communication Method

Type B is a **polled (command-response)** protocol. The scale is silent until the host sends a single enquiry byte. It will not transmit on its own.

```
Host  →  Scale :  0x05 (ENQ)
Scale →  Host  :  37 or 38 byte frame
```

---

### Request

Send a single byte `0x05` (ENQ) to trigger a response.

---

### Response Frame Layout

The frame is **37 bytes** without additional parity, or **38 bytes** with it.

```
Byte(s)   Length   Content
───────────────────────────────────────────────────
0         1        Status Flag
1         1        Weight Condition Flag
2         1        CR (0x0d)
3         1        Header '0' (0x30) — Net Weight
4–9       6        Net Weight value
10        1        CR (0x0d)
11        1        Header '4' (0x34) — Tare Weight
12–17     6        Tare Weight value
18        1        CR (0x0d)
19        1        Header 'U' (0x55) — Unit Price
20–25     6        Unit Price value
26        1        CR (0x0d)
27        1        Header 'T' (0x54) — Total Price
28–34     7        Total Price value
35        1        CR (0x0d)
36        1        LF (0x0a)
37        1        Additional Parity (optional, see Status Flag bit 0)
```

---

### Data Fields

All value fields are ASCII-encoded decimal with a decimal point.

| Field | Length | Example | Notes |
|---|---|---|---|
| Net Weight | 6 bytes | `001.708` | kg, after tare subtraction |
| Tare Weight | 6 bytes | `001.200` | kg, stored tare value |
| Unit Price | 6 bytes | `001.500` | per price base unit (see Status Flag bits 3–4) |
| Total Price | 7 bytes | `0005.184` | net weight × unit price, computed by scale |

**Special values** in weight fields:

| Value | Meaning |
|---|---|
| `OF` + spaces | Overflow — weight exceeds scale maximum |
| `UF` + spaces | Underflow — weight below scale minimum |
| spaces only | Data error or empty |

---

### Status Flag (byte 0)

| Bit | Meaning |
|---|---|
| 7 | Not used. Always 0 |
| 6 | Fixed to 1 |
| 5 | Not used |
| 4–3 | Price Base: `00` = $/kg, `01` = $/100g, `10` = $/1lb, `11` = $/1/41lb |
| 2 | Total Price Overflow: 1 when total price overflows |
| 1 | Net: 1 when tare subtraction is active |
| 0 | Additional Parity: 1 when extra parity byte is appended at byte 37 |

---

### Weight Condition Flag (byte 1)

| Bit | Meaning |
|---|---|
| 7 | Not used. Always 0 |
| 6 | Fixed to 1 |
| 5 | Not used |
| 4 | Weight Underflow: 1 when weight is below minimum |
| 3 | Weight Overflow: 1 when weight exceeds maximum |
| 2 | Negative Net Weight: 1 when tare exceeds gross |
| 1 | Weight Stable: 1 when reading is stable and valid |
| 0 | Zero Sign: 1 when zero sign is set |

---

### Additional Parity

When Status Flag bit 0 is set, a parity byte is appended at position 37. If the computed parity value would equal `0x0d`, `0x0a`, or `0x00`, it is replaced with `0x1d`, `0x1a`, or `0x10` respectively to avoid collision with frame terminators.

---

### Example Frame

```
Net weight = 3.456 kg   Tare = 1.200 kg   Unit price = 1.500 $/kg
Total price = 5.184     Status: stable, tare active
```

```
42 42 0d 30 30 33 2e 34 35 36 0d
         ↑  └──── 003.456 ─────┘
         '0' = net weight header

34 30 31 2e 32 30 30 0d
↑  └───── 01.200 ────┘
'4' = tare weight header

55 30 31 2e 35 30 30 0d
↑  └───── 01.500 ────┘
'U' = unit price header

54 30 30 35 2e 31 38 34 0d 0a
↑  └────── 005.184 ──────┘
'T' = total price header
```

Status Flag `0x42` = `0b01000010` → fixed-1 bit set, Net active  
Weight Condition Flag `0x42` = `0b01000010` → fixed-1 bit set, Weight Stable

---

### Overflow Frame Example

When weight overflows, weight value fields contain `OF` padded with spaces. Total price is transmitted as all spaces.

---

### Notes

- The scale only responds to `ENQ` when in **Type B (Standard command)** mode (data transmission standard `00011`)
- Price fields are only meaningful when a **PLU / unit price is programmed** on the scale. Both will read zero otherwise.
- Gross weight is not transmitted directly — it must be computed as `net + tare`
- RTS/CTS handshaking is only active when `SPEC3.3 = 0`. With default settings it is disabled and a simple 3-wire connection (TXD, RXD, GND) is sufficient
