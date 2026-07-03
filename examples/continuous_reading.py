#!/usr/bin/env python3
"""Continuous reading with a data-change watch.

`watch()` polls the scale continuously but only yields when the reading changes
meaningfully. With `stable_only=True` you get exactly one notification per
settled weight -- ideal for a "place item, read, remove, place next" workflow.

Press Ctrl-C to stop.
"""

import logging

from pydigi import DigiDS781, ChangeFilter

logging.basicConfig(level=logging.WARNING)

PORT = "/dev/cu.usbserial-1140"


def main():
    # Tick the fields that should count as a change. Here: net weight only,
    # settled, ignoring moves under 5 g. To also watch tare and price, use e.g.
    #   ChangeFilter([Field.NET, Field.TARE, Field.UNIT_PRICE], stable_only=True)
    watch_weight = ChangeFilter.weight(min_delta_kg=0.005, stable_only=True)

    with DigiDS781.open(PORT) as scale:
        print("Watching for weight changes (Ctrl-C to stop)...")
        for reading in scale.watch(interval=0.2, change_filter=watch_weight):
            if reading.weight_gross_kg is None:
                print("out of range")
            else:
                print("weight -> %.3f kg" % reading.weight_gross_kg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
