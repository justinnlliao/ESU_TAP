"""Versioned wire contract and receipt-time observations; no ROS dependency."""

from collections import deque
from dataclasses import dataclass
from numbers import Integral
import threading
import time

CHANNELS = ('cut', 'coag', 'bipolar', 'ligasure')
# Serial baud of every firmware profile. Must equal firmware/shared/
# board_profile.hpp `baud` and software/esu.py BAUD (enforced by a test).
BAUD = 115200


def revision_channels(revision):
    if revision not in ('v1', 'v2', 'v3'):
        raise ValueError('board_version must be v1, v2, or v3')
    return CHANNELS[:{'v1': 2, 'v2': 3, 'v3': 4}[revision]]


def require_channel(channel, available):
    if channel not in available:
        raise ValueError(f'Channel {channel!r} unavailable; refusing substitution')
    return channel


def parse_state(data, channel_count=None):
    """Accept either the packed-Int32 wire format or the legacy array format.

    Packed Int32 (current firmware): a single integer with
        bit 0    : cut
        bit 1    : coag
        bit 2    : bipolar
        bit 3    : ligasure
        bits 4-5 : source (0 pedal, 1 computer, 2 baseline, 3 takeover)
    Passed in as a 1-element sequence [packed] or a bare int.

    Legacy array (older firmware): [cut, coag, (bipolar,) (ligasure,) source],
    i.e. 3, 4, or 5 elements with source last.

    Returns (channel_states_tuple, source).
    """
    # Bare int or 1-element sequence -> packed format.
    if isinstance(data, Integral):
        packed = int(data)
    else:
        values = tuple(data)
        if len(values) == 1:
            if not isinstance(values[0], Integral):
                raise ValueError('Packed state must be an integer')
            packed = int(values[0])
        else:
            # Legacy array path.
            if len(values) not in (3, 4, 5):
                raise ValueError('Expected packed int or 3/4/5 array fields')
            if any(not isinstance(v, Integral) for v in values):
                raise ValueError('State fields must be integers')
            if any(v not in (0, 1) for v in values[:-1]) or values[-1] not in (0, 1, 2):
                raise ValueError('Invalid channel state or source')
            if channel_count is not None and len(values) != channel_count + 1:
                raise ValueError('Telemetry does not match selected board_version')
            return values[:-1], values[-1]
    # Decode packed int. Channels are bits 0..3; source is bits 4-5.
    # Schema sanity check, not an integrity check: out-of-range values may
    # indicate corruption OR a mismatched publisher. In-range corruption and
    # missing messages cannot be detected by this mask.
    if packed < 0 or packed > 0x3F:
        raise ValueError(f'Out-of-range packed state {packed}')
    cut = packed & 1
    coag = (packed >> 1) & 1
    bipolar = (packed >> 2) & 1
    ligasure = (packed >> 3) & 1
    source = (packed >> 4) & 0x3
    # 3 = a computer channel released because a pedal press ended autonomous control.
    if source not in (0, 1, 2, 3):
        raise ValueError('Invalid source in packed state')
    states = (cut, coag, bipolar, ligasure)
    if channel_count is not None:
        if channel_count not in (2, 3, 4) or any(states[channel_count:]):
            raise ValueError('Unsupported channel active in telemetry')
        states = states[:channel_count]
    return states, source


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
        states, source = parse_state(data, self.channel_count)
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
