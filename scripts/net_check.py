"""Measure the network between this laptop and the LeKiwi Pi. Never sends a command.

    uv run python scripts/net_check.py                      # Pi address from configs (robot.remote_ip)
    uv run python scripts/net_check.py --ip 192.168.137.50  # another network

1. Round trip: 50 TCP connections to the Pi's SSH port (needs no host).
2. Stream: if the host is running, 20 s of observations (gaps, size, throughput).
   Stop the teleop first: two clients share the stream and both get half of it.
"""

import argparse
import socket
import statistics as st
import time

import numpy as np

from makai.config import load_config

N_PINGS = 50
STREAM_S = 20


def summary(values_ms: list[float]) -> str:
    v = np.asarray(values_ms)
    return (
        f"median {st.median(v):6.1f} ms   p90 {np.percentile(v, 90):6.1f}   "
        f"p99 {np.percentile(v, 99):6.1f}   max {v.max():6.1f}"
    )


def round_trip(ip: str) -> None:
    times, lost = [], 0
    for _ in range(N_PINGS):
        t0 = time.perf_counter()
        try:
            socket.create_connection((ip, 22), timeout=2).close()
            times.append((time.perf_counter() - t0) * 1000)
        except OSError:
            lost += 1
        time.sleep(0.1)
    print(f"round trip ({len(times)}/{N_PINGS} answered): " + (summary(times) if times else "no answer"))


def stream(ip: str, cfg: dict) -> None:
    from makai.robot.lekiwi import make_client

    cfg["robot"]["remote_ip"] = ip
    robot = make_client(cfg)
    arrivals, sizes = [], []
    poll = robot._poll_and_get_latest_message

    def spy():
        msg = poll()
        if msg is not None:
            arrivals.append(time.perf_counter())
            sizes.append(sum(len(f) for f in msg))
        return msg

    robot._poll_and_get_latest_message = spy
    try:
        robot.connect()
    except Exception as e:  # noqa: BLE001 - any failure here just means "no host"
        print(
            f"stream: host not reachable ({e.__class__.__name__}), start it on the Pi to measure the stream"
        )
        return
    end = time.perf_counter() + STREAM_S
    while time.perf_counter() < end:
        robot.get_observation()
        time.sleep(0.005)
    robot.disconnect()
    gaps = np.diff(arrivals) * 1000
    print(f"stream: {len(arrivals) / STREAM_S:.1f} observations/s, gaps " + summary(gaps))
    print(f"        gaps > 100 ms: {(gaps > 100).sum()}   > 200 ms: {(gaps > 200).sum()}   in {STREAM_S} s")
    print(
        f"        {st.median(sizes) / 1000:.0f} kB per observation, {sum(sizes) * 8 / STREAM_S / 1e6:.1f} Mbit/s"
    )


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ip", default=cfg["robot"]["remote_ip"])
    ip = parser.parse_args().ip
    print(f"Pi at {ip}")
    round_trip(ip)
    stream(ip, cfg)


if __name__ == "__main__":
    main()
