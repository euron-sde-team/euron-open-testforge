# A probe that runs inside the sandbox only (never collected here: its file name is not test_*).
# Runs inside the sandbox, one test per run (selected by node id). Each crosses a limit.
import os
import threading
import time


def test_spin_forever():
    n = 0
    while True:
        n += 1


def test_sleep_forever():
    time.sleep(600)


def test_allocate_four_gigabytes():
    block = bytearray(4 * 1024**3)
    assert len(block) > 0


def test_flood_output():
    line = b"x" * 1023 + b"\n"
    for _ in range(200_000):
        os.write(1, line)


def test_start_ten_thousand_threads():
    stop = threading.Event()
    threads = []
    try:
        for _ in range(10_000):
            t = threading.Thread(target=stop.wait, args=(30,))
            t.start()
            threads.append(t)
    finally:
        stop.set()
        for t in threads:
            t.join()
