"""The client: orchestrate a transport + protocol into readings.

:class:`Scale` is what most code touches. It sends a poll request through the
transport, reads one frame, parses it, and applies a retry policy. On top of the
single :meth:`read` it offers :meth:`stream` (every poll) and :meth:`watch`
(only meaningful changes).
"""

import logging
import time
from dataclasses import dataclass

from .exceptions import PyDigiError, ScaleTimeout, TransportError, FrameError
from .watch import ChangeFilter

logger = logging.getLogger("pydigi")


@dataclass
class PollPolicy:
    """How aggressively to poll and retry.

    :param retries: total attempts per :meth:`Scale.read` before giving up.
    :param retry_delay: seconds to wait between attempts.
    :param poll_delay: seconds to wait after sending the request before reading
        (usually 0 — the transport's read timeout already paces us).
    """

    retries: int = 3
    retry_delay: float = 0.2
    poll_delay: float = 0.0


class Scale:
    """A DIGI scale reachable over some transport, speaking some protocol.

    Prefer a model factory (e.g. :meth:`DigiDS781.open`) which wires sensible
    defaults; construct :class:`Scale` directly only for custom setups.
    """

    def __init__(self, transport, protocol, policy=None, max_weight_kg=None):
        self._transport = transport
        self._protocol = protocol
        self._policy = policy or PollPolicy()
        self._max_weight_kg = max_weight_kg

    # -- lifecycle ---------------------------------------------------------

    def open(self):
        self._transport.open()
        logger.info("Scale opened via %s", type(self._transport).__name__)
        return self

    def close(self):
        self._transport.close()
        logger.info("Scale closed")

    @property
    def is_open(self):
        return self._transport.is_open

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc_info):
        self.close()

    # -- reading -----------------------------------------------------------

    def read(self):
        """Poll once and return a :class:`~pydigi.reading.ScaleReading`.

        Retries transient failures (timeouts, transport hiccups, the occasional
        garbled frame) per the :class:`PollPolicy`. Raises the last error once
        the attempts are exhausted.
        """
        if not self._transport.is_open:
            raise TransportError("Scale is not open; call open() first")

        policy = self._policy
        last_error = None

        for attempt in range(1, policy.retries + 1):
            try:
                self._transport.reset_input()
                self._transport.write(self._protocol.poll_request())
                if policy.poll_delay:
                    time.sleep(policy.poll_delay)
                raw = self._protocol.read_frame(self._transport)
                reading = self._protocol.parse(raw)
                self._sanity_check(reading)
                return reading
            except (ScaleTimeout, TransportError, FrameError) as error:
                last_error = error
                # Per-attempt failures are retry noise (a transient short read or
                # timeout usually recovers on the next attempt). Log at DEBUG; the
                # final, exhausted failure is raised for the caller to handle.
                logger.debug(
                    "Poll attempt %d/%d failed: %s", attempt, policy.retries, error
                )
                if attempt < policy.retries and policy.retry_delay:
                    time.sleep(policy.retry_delay)

        raise last_error or ScaleTimeout("Scale did not respond")

    def stream(self, interval=0.2, count=None, ignore_errors=False, on_error=None):
        """Continuously yield readings — the raw continuous-reading loop.

        :param interval: seconds to sleep between polls.
        :param count: stop after this many readings (``None`` = forever).
        :param ignore_errors: keep going when a poll raises, instead of stopping.
        :param on_error: called with the exception when ``ignore_errors`` is set.
        """
        emitted = 0
        while count is None or emitted < count:
            try:
                reading = self.read()
            except PyDigiError as error:
                if not ignore_errors:
                    raise
                if on_error is not None:
                    on_error(error)
                time.sleep(interval)
                continue
            yield reading
            emitted += 1
            if interval:
                time.sleep(interval)

    def watch(
        self,
        interval=0.2,
        change_filter=None,
        count=None,
        ignore_errors=False,
        on_error=None,
    ):
        """Yield a reading only when it *changes* — the data-change watch.

        Which fields count as a change is decided by ``change_filter``, a
        :class:`~pydigi.watch.ChangeFilter`. The default watches net weight only
        (``ChangeFilter.weight()``), so flag- or price-only transitions — like
        the zero-sign flag flipping on an empty pan — are ignored. Pass a filter
        that ticks other fields (tare, prices, ...) to widen it.

        :param change_filter: a :class:`ChangeFilter`; defaults to weight-only.
        :param count: stop after this many *reported changes* (``None`` = forever).
        """
        if change_filter is None:
            change_filter = ChangeFilter.weight()

        previous = None
        reported = 0
        for reading in self.stream(
            interval=interval, ignore_errors=ignore_errors, on_error=on_error
        ):
            if change_filter.changed(previous, reading):
                previous = reading
                yield reading
                reported += 1
                if count is not None and reported >= count:
                    return

    # -- diagnostics -------------------------------------------------------

    def _sanity_check(self, reading):
        if not reading.is_stable:
            logger.debug("Reading not stable yet")
        if reading.weight_overflow:
            logger.warning("Weight overflow reported by scale")
        if reading.weight_underflow:
            logger.warning("Weight underflow reported by scale")
        if reading.total_price_overflow:
            logger.warning("Total price overflow reported by scale")
        if reading.is_negative:
            logger.warning("Negative net weight: tare may exceed gross")
        if (
            self._max_weight_kg is not None
            and reading.weight_gross_kg is not None
            and reading.weight_gross_kg > self._max_weight_kg
        ):
            logger.warning(
                "Gross weight %.3f kg exceeds model maximum %.3f kg",
                reading.weight_gross_kg,
                self._max_weight_kg,
            )
