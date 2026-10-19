"""Explicitly armed lease renewals; not an independent emergency stop.

send(channel, bool) and set_arm(bool) perform bounded acknowledged calls.
All I/O is serialized so an OFF cannot be overtaken by a queued renewal.

One missed renewal is tolerated: the next one, refresh_s later, still lands
inside the firmware's lease. Two consecutive misses, or any unacknowledged
explicit command, disarm and require a deliberate re-arm. The firmware lease
stays the authority: if it expires first, the next renewal is refused.
"""
import threading


class CommandSession:
    def __init__(self, channels, send, set_arm, refresh_s):
        self.channels = tuple(channels)
        self.send = send
        self.set_arm = set_arm
        self.refresh_s = refresh_s
        self.desired = set()
        self.armed = False
        self.fault = None
        self.missed_renewals = 0
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None

    def start(self):
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _disarm_locked(self):
        self.desired.clear()
        self.armed = False
        # Best effort; no auto-rearm on recovery.
        return self.set_arm(False)

    def arm(self):
        with self.lock:
            if self.desired:
                return False
            self.armed = bool(self.set_arm(True))
            if self.armed:
                self.fault = None
                self.missed_renewals = 0
            return self.armed

    def command(self, channel, on):
        if channel not in self.channels:
            raise ValueError('Unavailable channel; no substitution')
        with self.lock:
            if on and not self.armed:
                return False
            if not on:
                self.desired.discard(channel)
            if not self.send(channel, on):
                self.fault = 'Command not acknowledged; computer control disarmed'
                self._disarm_locked()
                return False
            if on:
                self.desired.add(channel)
            return True

    def renew_once(self):
        with self.lock:
            if not self.desired:
                self.missed_renewals = 0
                return True
            ok = True
            for channel in tuple(self.desired):
                ok = self.send(channel, True) and ok
            if ok:
                self.missed_renewals = 0
                return True
            self.missed_renewals += 1
            if self.missed_renewals >= 2:
                self.fault = 'Two renewals in a row failed; explicit re-arm required'
                self._disarm_locked()
            return False

    def all_off(self):
        with self.lock:
            ok = self._disarm_locked()
            # Try every OFF even if disarm failed. OFF cannot suppress a held pedal.
            for ch in self.channels:
                ok = self.send(ch, False) and ok
            return ok

    def _run(self):
        try:
            while not self.stop.wait(self.refresh_s):
                if not self.renew_once():
                    continue
        except Exception as exc:
            with self.lock:
                self.fault = str(exc)
                self.desired.clear()
                self.armed = False
            # No further renewals; firmware lease expires even if cleanup cannot run.

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=3.0)
        return self.all_off()
