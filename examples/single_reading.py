#!/usr/bin/env python3
"""Take one reading from a DIGI DS-781 and print it.

Change PORT to your device:
    Linux   /dev/ttyUSB0
    macOS   /dev/cu.usbserial-XXXX
    Windows COM3
"""

import logging

from pydigi import DigiDS781

logging.basicConfig(level=logging.INFO)

PORT = "/dev/cu.usbserial-111420"


def main():
    with DigiDS781.open(PORT) as scale:
        reading = scale.read()
        print(reading)

        if reading.weight_net_kg is None:
            print("No valid weight (overflow/underflow or empty).")
        else:
            print("Net weight:   %.3f kg" % reading.weight_net_kg)
            print("Gross weight: %.3f kg" % reading.weight_gross_kg)
            print("Stable:       %s" % reading.is_stable)


if __name__ == "__main__":
    main()
