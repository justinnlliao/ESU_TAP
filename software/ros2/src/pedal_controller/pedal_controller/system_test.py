#!/usr/bin/env python3
"""Interactive per-revision dummy-fixture checks; not a safety acceptance test."""

from pedal_controller.bench_runtime import BenchNode, run_bench


class SystemTest(BenchNode):
    def __init__(self):
        super().__init__('system_test')

    def run(self):
        print('DISCONNECTED DUMMY FIXTURE ONLY. Release all pedals.')
        print('Measure contact continuity independently; telemetry is inferred.')
        input('ENTER to test each selected-revision channel...')
        for channel in self.channels:
            try:
                self.transition(channel, True)
                answer = input(f'{channel}: ONLY the intended contact closed? [y/N] ')
                if answer.strip().lower() != 'y':
                    return False
            finally:
                # Attempt OFF even if ON telemetry or operator confirmation fails.
                self.transition(channel, False)
            if input(f'{channel}: contact now released? [y/N] ').strip().lower() != 'y':
                return False

        for channel in self.channels:
            idx = self.channels.index(channel)
            for active, verb in ((1, 'press and HOLD'), (0, 'release')):
                mark = self.history.mark()
                input(f'{channel}: {verb} the pedal, THEN press ENTER...')
                expected = tuple(active if i == idx else 0 for i in range(len(self.channels)))
                observation = self.history.wait(
                    lambda item: item.states == expected and item.source == 0, mark)
                if observation is None:
                    raise RuntimeError(f'{channel}: fresh pedal {active} telemetry not observed')
                if input('Independent contact measurement matches? [y/N] ').strip().lower() != 'y':
                    return False
        print('Selected channel checks passed. Fault recovery and clinical safety NOT validated.')
        return True


def main(args=None):
    run_bench(SystemTest, args)


if __name__ == '__main__':
    main()
