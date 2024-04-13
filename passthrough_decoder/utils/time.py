import time


def sleep_s(s: float):
    start = time.perf_counter_ns()

    while time.perf_counter_ns() - start < (s * 1e9 * 0.9):
        time.sleep(s / 10)

    # sleep the rest
    while time.perf_counter_ns() - start < s * 1e9:
        pass
