"""Wait for async responses while a separate executor thread owns spinning."""

from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class CallResult:
    success: bool
    sent_at: float
    received_at: float | None
    message: str


def call_service(client, request, timeout):
    event = threading.Event()
    response_time = []
    sent_at = time.monotonic()
    try:
        future = client.call_async(request)

        def completed(_future):
            response_time.append(time.monotonic())
            event.set()

        future.add_done_callback(completed)
        if not event.wait(max(0.0, timeout - (time.monotonic() - sent_at))):
            # Cancellation is local bookkeeping, NOT cancellation on the ESP32.
            future.cancel()
            return CallResult(False, sent_at, None, 'timeout; physical state unknown')
        response = future.result()
        if response is None:
            return CallResult(False, sent_at, response_time[0], 'no response')
        return CallResult(bool(response.success), sent_at, response_time[0], response.message)
    except Exception as exc:
        return CallResult(False, sent_at, None, f'service failure: {exc}')
