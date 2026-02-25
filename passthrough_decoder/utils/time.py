import time


def sleep_s(s: float):
    """
    Sleep for approximately ``s`` seconds.
    This function uses a combination of time.sleep and a busy-wait loop to improve timing accuracy,
    Parameters
    ----------
    s : float
        Target duration in seconds.
    Returns
    -------
    None
    """
    start = time.perf_counter_ns()

    while time.perf_counter_ns() - start < (s * 1e9 * 0.9):
        time.sleep(s / 10)

    # sleep the rest
    while time.perf_counter_ns() - start < s * 1e9:
        pass
