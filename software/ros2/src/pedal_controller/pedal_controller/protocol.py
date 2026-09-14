"""Versioned wire contract and receipt-time observations; no ROS dependency."""

from collections import deque
from dataclasses import dataclass
from numbers import Integral
import threading
import time

CHANNELS = ('cut', 'coag', 'bipolar', 'ligasure')


def revision_channels(revision):
    if revision not in ('v1', 'v2', 'v3'):
        raise ValueError('board_version must be v1, v2, or v3')
    return CHANNELS[:{'v1': 2, 'v2': 3, 'v3': 4}[revision]]


def require_channel(channel, available):
    if channel not in available:
        raise ValueError(f'Channel {channel!r} unavailable; refusing substitution')
    return channel


def parse_state(data):
    values = tuple(data)
    if len(values) not in (3, 4, 5):
        raise ValueError('Expected 3, 4, or 5 state fields')
    if any(not isinstance(v, Integral) for v in values):
        raise ValueError('State fields must be integers')
    if any(v not in (0, 1) for v in values[:-1]) or values[-1] not in (0, 1, 2):
        raise ValueError('Invalid channel state or source')
    return values[:-1], values[-1]


@dataclass(frozen=True)
class Observation:
    sequence: int
    received_at: float
    states: tuple
    source: int


class StateHistory:
    """Retain fresh messages even when they precede a service response."""

    def __init__(self, channel_count):
        self.channel_count = channel_count
        self._condition = threading.Condition()
        self._sequence = 0
        self._items = deque(maxlen=2048)

    def mark(self):
        with self._condition:
            return self._sequence

    def record(self, data, received_at=None):
        received_at = time.monotonic() if received_at is None else received_at
        states, source = parse_state(data)
        if len(states) != self.channel_count:
            raise ValueError('Telemetry does not match selected board_version')
        with self._condition:
            self._sequence += 1
            item = Observation(self._sequence, received_at, states, source)
            self._items.append(item)
            self._condition.notify_all()
            return item

    def wait(self, predicate, after, timeout=1.0, not_before=0.0):
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                for item in self._items:
                    if (item.sequence > after and item.received_at >= not_before
                            and predicate(item)):
                        return item
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
