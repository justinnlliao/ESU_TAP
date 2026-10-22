#!/usr/bin/env python3
"""Receipt-time benchmark for all revisions; no physical/RF timing claim.

Both timestamps are captured on the PC. State can arrive BEFORE the service
response. No fixed response-plus-5-ms relationship is assumed. ON and OFF are
timed separately, and every sample (warmup included, labeled) is written to a
raw CSV so results can be re-analyzed rather than only summarized.
"""

import csv
import math
import os
import re
import statistics
import time
from datetime import datetime

from pedal_controller.bench_runtime import BenchNode, run_bench
from pedal_controller.protocol import require_channel

CSV_HEADER = ['trial_id', 'board', 'firmware', 'channel', 'iteration', 'phase',
              'on_ack_ms', 'on_state_ms', 'off_ack_ms', 'off_state_ms']


class LatencyTest(BenchNode):
    def __init__(self):
        super().__init__('latency_test')
        for name, default in (('iterations', 100), ('warmup', 5),
                              ('channel', 'cut'), ('settle_ms', 60),
                              ('trial_id', ''), ('output_dir', os.path.expanduser('~/pedal_logs'))):
            self.declare_parameter(name, default)
        self.iterations = self.get_parameter('iterations').value
        self.warmup = self.get_parameter('warmup').value
        self.channel = self.get_parameter('channel').value
        self.settle_s = float(self.get_parameter('settle_ms').value) / 1000.0
        self.trial_id = self.get_parameter('trial_id').value
        self.output_dir = self.get_parameter('output_dir').value

    def prepare(self):
        require_channel(self.channel, self.channels)
        if (self.iterations <= 0 or self.warmup < 0
                or not math.isfinite(self.settle_s) or self.settle_s < 0):
            raise ValueError('Invalid iterations, warmup, or settle_ms')
        if not re.fullmatch(r'[A-Za-z0-9_-]{0,64}', self.trial_id):
            raise ValueError('trial_id: letters, digits, _ and - only (max 64)')
        super().prepare()

    @staticmethod
    def _delays(response, observation):
        """(ack, state) delays in ms, both from the PC send time."""
        return ((response.received_at - response.sent_at) * 1000,
                (observation.received_at - response.sent_at) * 1000)

    def _one_iteration(self):
        on = off = None
        try:
            on = self.transition(self.channel, True)
        finally:
            # A failed release aborts the benchmark, rather than being excluded
            # from latency statistics while further activations continue.
            off = self.transition(self.channel, False)
        return self._delays(*on) + self._delays(*off)

    def _open_csv(self):
        os.makedirs(self.output_dir, exist_ok=True)
        name = ('latency_' + (self.trial_id + '_' if self.trial_id else '') + self.channel + '_'
                + datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv')
        path = os.path.join(self.output_dir, name)
        handle = open(path, 'x', newline='')
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        return path, handle, writer

    def run(self):
        print('DISCONNECTED FIXTURE/MOCK ONLY. Release all pedals; no other command clients.')
        info = self.device.info or {}
        path, handle, writer = self._open_csv()
        samples = {key: [] for key in CSV_HEADER[6:]}
        try:
            for i in range(self.warmup + self.iterations):
                row = self._one_iteration()
                phase = 'warmup' if i < self.warmup else 'measured'
                writer.writerow([self.trial_id, info.get('board', ''), info.get('firmware', ''),
                                 self.channel, i, phase, *(f'{v:.3f}' for v in row)])
                handle.flush()
                if phase == 'measured':
                    for key, value in zip(samples, row):
                        samples[key].append(value)
                time.sleep(self.settle_s)
        finally:
            handle.close()   # Rows written so far survive an aborted run.
        self._report('ON  service response receipt (ms)', samples['on_ack_ms'])
        self._report('ON  state message receipt (ms)', samples['on_state_ms'])
        self._report('OFF service response receipt (ms)', samples['off_ack_ms'])
        self._report('OFF state message receipt (ms)', samples['off_state_ms'])
        print('Raw samples: ' + path)
        print('No contact/RF timing measured. These software checks do not validate fault shutdown.')
        return True

    @staticmethod
    def _report(label, samples):
        ordered = sorted(samples)
        def percentile(p):
            k = (len(ordered) - 1) * p
            lo = int(k)
            hi = min(lo + 1, len(ordered) - 1)
            return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)
        print(f'{label}: n={len(samples)}, min={min(samples):.3f}, '
              f'mean={statistics.mean(samples):.3f}, median={statistics.median(samples):.3f}, '
              f'p95={percentile(.95):.3f}, p99={percentile(.99):.3f}, max={max(samples):.3f}')


def main(args=None):
    run_bench(LatencyTest, args)


if __name__ == '__main__':
    main()
