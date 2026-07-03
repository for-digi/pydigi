"""The ``pydigi`` command-line interface.

    pydigi --port /dev/ttyUSB0 read
    pydigi --port /dev/ttyUSB0 read --json
    pydigi --port /dev/ttyUSB0 watch --stable-only
    pydigi --port /dev/ttyUSB0 watch --field tare --field unit-price
    pydigi --port /dev/ttyUSB0 watch --all-fields
    pydigi --port COM3 stream --interval 0.5 --count 10
    pydigi list-models

Thin by design: it parses arguments, builds a scale from the model registry, and
prints readings. All real work lives in the library.
"""

import argparse
import json
import logging
import sys

from . import __version__
from .exceptions import PyDigiError
from .models import get_model, available_models
from .watch import ChangeFilter, Field

# Short CLI names -> ChangeFilter field constants.
_WATCH_FIELDS = {
    "net": Field.NET,
    "tare": Field.TARE,
    "gross": Field.GROSS,
    "unit-price": Field.UNIT_PRICE,
    "total-price": Field.TOTAL_PRICE,
    "price-base": Field.PRICE_BASE,
    "stable": Field.STABLE,
    "zero": Field.ZERO,
    "net-mode": Field.NET_MODE,
    "negative": Field.NEGATIVE,
    "overflow": Field.WEIGHT_OVERFLOW,
    "underflow": Field.WEIGHT_UNDERFLOW,
    "total-price-overflow": Field.TOTAL_PRICE_OVERFLOW,
}


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="pydigi",
        description="Read weight and price from DIGI scales over RS-232.",
    )
    parser.add_argument("--version", action="version", version="pydigi " + __version__)
    parser.add_argument(
        "--model", default="ds781",
        help="scale model (default: ds781). See 'pydigi list-models'.",
    )
    parser.add_argument("--port", help="serial device, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--baudrate", type=int, default=None, help="override baud rate")
    parser.add_argument("--json", action="store_true", help="emit readings as JSON lines")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="-v for info, -vv for debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("read", help="take a single reading and exit")

    watch = sub.add_parser("watch", help="print a reading only when it changes")
    watch.add_argument("--interval", type=float, default=0.2, help="seconds between polls")
    watch.add_argument("--min-delta", type=float, default=0.0,
                       help="weight change (kg) needed to report")
    watch.add_argument("--stable-only", action="store_true",
                       help="report only stable readings")
    watch.add_argument("--field", action="append", dest="fields",
                       choices=sorted(_WATCH_FIELDS),
                       help="field to watch for changes (repeatable); default: net")
    watch.add_argument("--all-fields", action="store_true",
                       help="watch every field, not just weight")
    watch.add_argument("--count", type=int, default=None,
                       help="stop after N reported changes")

    stream = sub.add_parser("stream", help="print every reading continuously")
    stream.add_argument("--interval", type=float, default=0.2, help="seconds between polls")
    stream.add_argument("--count", type=int, default=None, help="stop after N readings")

    sub.add_parser("list-models", help="list known scale models and exit")

    return parser


def _configure_logging(verbosity):
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _emit(reading, as_json):
    if as_json:
        print(json.dumps(reading.as_dict()))
    else:
        print(reading)
    sys.stdout.flush()


def _open_scale(args):
    model = get_model(args.model)
    return model.open(args.port, baudrate=args.baudrate)


def _build_filter(args):
    if args.all_fields:
        return ChangeFilter.everything(min_delta_kg=args.min_delta, stable_only=args.stable_only)
    if args.fields:
        fields = [_WATCH_FIELDS[name] for name in args.fields]
        return ChangeFilter(fields, min_delta_kg=args.min_delta, stable_only=args.stable_only)
    return ChangeFilter.weight(min_delta_kg=args.min_delta, stable_only=args.stable_only)


def main(argv=None):
    """Entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "list-models":
        print("Available models: %s" % ", ".join(available_models()))
        return 0
    if args.command is None:
        print("No command given. Try 'pydigi --port PORT read'.", file=sys.stderr)
        return 2
    if not args.port:
        print("--port is required for '%s'." % args.command, file=sys.stderr)
        return 2
    try:
        get_model(args.model)  # validate up front so an unknown model isn't a traceback
    except KeyError as error:
        print("Error: %s" % error, file=sys.stderr)
        return 2

    try:
        with _open_scale(args) as scale:
            if args.command == "read":
                _emit(scale.read(), args.json)
            elif args.command == "stream":
                for reading in scale.stream(interval=args.interval, count=args.count):
                    _emit(reading, args.json)
            elif args.command == "watch":
                for reading in scale.watch(
                    interval=args.interval,
                    change_filter=_build_filter(args),
                    count=args.count,
                ):
                    _emit(reading, args.json)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except PyDigiError as error:
        print("Error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
