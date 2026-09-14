#!/usr/bin/env python3
"""Receipt-time benchmark for all revisions; no physical/RF timing claim.

Both timestamps are captured on the PC. State can arrive BEFORE the service
response. No fixed response-plus-5-ms relationship is assumed.
"""

import math
import statistics
import time

from pedal_controller.bench_runtime import BenchNode, run_bench
from pedal_controller.protocol import require_channel


class LatencyTest(BenchNode):
    def __init__(self):
        super().__init__('latency_test')
        for name, default in (('iterations', 100), ('warmup', 5),
                              ('channel', 'cut'), ('settle_ms', 60)):
            self.declare_parameter(name, default)
        self.iterations = self.get_parameter('iterations').value
        self.warmup = self.get_parameter('warmup').value
        self.channel = self.get_parameter('channel').value
        self.settle_s = float(self.get_parameter('settle_ms').value) / 1000.0

    def prepare(self):
        require_channel(self.channel, self.channels)
        if (self.iterations <= 0 or self.warmup < 0
                or not math.isfinite(self.settle_s) or self.settle_s < 0):
            raise ValueError('Invalid iterations, warmup, or settle_ms')
        super().prepare()

    def _one_iteration(self):
        try:
            response, observation = self.transition(self.channel, True)
        finally:
            # A failed release aborts the benchmark, rather than being excluded
            # from latency statistics while further activations continue.
            self.transition(self.channel, False)
        return (response.received_at - response.sent_at,
                observation.received_at - response.sent_at)

    def run(self):
        print('DISCONNECTED FIXTURE/MOCK ONLY. Release all pedals; no other command clients.')
        rtts, states = [], []
        for i in range(self.warmup + self.iterations):
            rt, state = self._one_iteration()
            if i >= self.warmup:
                rtts.append(rt * 1000)
                states.append(state * 1000)
            time.sleep(self.settle_s)
        self._report('Service response receipt (ms)', rtts)
        self._report('State message receipt (ms)', states)
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
