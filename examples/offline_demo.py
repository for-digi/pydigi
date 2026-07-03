#!/usr/bin/env python3
"""Try pydigi with NO hardware.

Uses LoopbackTransport to feed synthetic DS-781 frames, simulating weight being
added to the pan. Run it directly:

    .virtualenv/bin/python examples/offline_demo.py
"""

from pydigi import DigiDS781, LoopbackTransport


def frame(net_weight):
    """Build a minimal, well-formed Type B frame for a given net-weight string.

    ``net_weight`` must be a 6-character field, e.g. "00.100".
    """
    return (
        bytes([0x42, 0x42, 0x0D, 0x30]) + net_weight.encode("ascii")   # status, cond, CR, '0' + net
        + bytes([0x0D, 0x34]) + b"00.000"                              # CR, '4' + tare
        + bytes([0x0D, 0x55]) + b"01.500"                              # CR, 'U' + unit price
        + bytes([0x0D, 0x54]) + b"000.000"                             # CR, 'T' + total price
        + bytes([0x0D, 0x0A])                                          # CR, LF
    )


def main():
    # A little script of "weights on the pan": some repeats (no change), some moves.
    script = ["00.000", "00.000", "00.100", "00.100", "00.250"]
    frames = iter(script)

    def scale_responder():
        try:
            return frame(next(frames))
        except StopIteration:
            return frame("00.250")

    with DigiDS781.bind(LoopbackTransport(scale_responder)) as scale:
        print("Simulated data-change watch (no hardware):")
        for reading in scale.watch(interval=0, count=3):
            print("  changed -> %.3f kg" % reading.weight_net_kg)


if __name__ == "__main__":
    main()
