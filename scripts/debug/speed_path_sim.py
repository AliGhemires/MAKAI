"""How wrong can host-mode odometry be when it integrates Present_Velocity?

Model, from what we measured on this robot: the servo reports its speed in multiples of
50 steps/s, i.e. the number of encoder steps over a 20 ms window. The host reads it once per
loop (30 Hz) and the laptop integrates it until the next reading (as navigation/odometry.py).
The wheels themselves are assumed perfect: no slip, exact geometry. Any error below is created
by the measurement chain alone. Four exact quarter turns with makai.robot.moves.GoTo, closed on
that odometry, as in the tests of 15 Nov. Evidence for docs/DEBUG_ODOMETRY.md, section 10.1.

    uv run python scripts/debug/speed_path_sim.py 30      # 30 draws of each case, about a minute
"""

import math
import random
import statistics
import sys

from makai.robot.moves import GoTo, GoToTuning

STEPS_PER_RAD_WHEEL = 4096 / (2 * math.pi)
R_BASE, R_WHEEL = 0.125, 0.05


def run(seed, window_s=0.020, host_hz=30.0, encoder=False, cruise=0.6, laptop_hz=50.0, win_clock=True):
    rng = random.Random(seed)
    dt = 0.0005
    t = 0.0
    yaw_true = 0.0  # rad, from the wheels: no slip
    wheel_pos = [rng.random() * 4096 for _ in range(3)]  # float encoder positions
    last_win_pos = [math.floor(p) for p in wheel_pos]
    reg = [0, 0, 0]  # Present_Velocity registers, steps/s
    next_win = [rng.random() * window_s for _ in range(3)]  # each servo has its own clock
    host_period = 1 / host_hz + rng.uniform(0.0, 0.0015)  # sleep overshoot
    next_host = rng.random() * host_period
    next_laptop = rng.random() / laptop_hz
    cmd_host = 0.0  # rad/s the wheels are executing
    cmd_laptop = 0.0
    latest = (0.0, None)  # (theta.vel measured, encoder positions) as last received by the laptop
    in_flight = []  # (arrival time, payload)
    odo_yaw, odo_stamp = 0.0, None
    enc_last = None
    tuning = GoToTuning(max_ang_rad_s=cruise)
    goals = [math.radians(a) for a in (90, 180, 270, 360)]
    goto = None
    pause_until = 0.5
    while True:
        # wheels: pure rotation, the three wheels turn alike
        wheel_rate = cmd_host * R_BASE / R_WHEEL * STEPS_PER_RAD_WHEEL  # steps/s
        yaw_true += cmd_host * dt
        for i in range(3):
            wheel_pos[i] += wheel_rate * dt
            if t >= next_win[i]:
                now_pos = math.floor(wheel_pos[i])
                reg[i] = round((now_pos - last_win_pos[i]) / window_s)
                last_win_pos[i] = now_pos
                next_win[i] += window_s
        if t >= next_host:  # host loop: apply the latest command, read, send
            cmd_host = cmd_laptop
            theta_vel = statistics.fmean(reg) / STEPS_PER_RAD_WHEEL * R_WHEEL / R_BASE
            in_flight.append(
                (t + rng.uniform(0.012, 0.030), (theta_vel, [math.floor(p) % 4096 for p in wheel_pos]))
            )
            next_host += host_period + rng.uniform(-0.001, 0.001)
        if t >= next_laptop:  # console tick
            while in_flight and in_flight[0][0] <= t:
                latest = in_flight.pop(0)[1]
            stamp = math.floor(t / 0.015625) * 0.015625 if win_clock else t  # Windows clock: 15.6 ms steps
            if encoder:
                if enc_last is not None and latest[1] is not None:
                    d = [((a - b + 2048) % 4096) - 2048 for a, b in zip(latest[1], enc_last, strict=False)]
                    odo_yaw += statistics.fmean(d) / STEPS_PER_RAD_WHEEL * R_WHEEL / R_BASE
                enc_last = latest[1] or enc_last
            else:
                if odo_stamp is not None:
                    odo_yaw += latest[0] * max(0.0, stamp - odo_stamp)
                odo_stamp = stamp
            if goto is None and t >= pause_until:
                if not goals:
                    break
                goto = GoTo("turn", (0.0, 0.0, goals.pop(0)), (0.0, 0.0, odo_yaw), stamp, tuning)
            if goto is not None:
                v = goto.step((0.0, 0.0, odo_yaw), stamp)
                if v is None:
                    goto, cmd_laptop, pause_until = None, 0.0, t + 0.6
                else:
                    cmd_laptop = v.theta
            next_laptop += (
                1 / laptop_hz + (rng.choice([0.0, 0.0156]) if win_clock else 0.0) * rng.random() * 0.3
            )
        t += dt
        if t > 120:
            break
    return math.degrees(yaw_true), math.degrees(odo_yaw)


def report(label, **kw):
    errs = []
    for seed in range(int(sys.argv[1]) if len(sys.argv) > 1 else 30):
        true, odo = run(seed, **kw)
        errs.append(true - odo)
    errs.sort()
    print(
        f"{label:58s} real - odometry over 4 quarter turns: mean {statistics.fmean(errs):+6.2f} deg, "
        f"spread {statistics.pstdev(errs):5.2f}, from {errs[0]:+6.2f} to {errs[-1]:+6.2f}"
    )


report("speed readings (as today), cruise 0.6 rad/s")
report("speed readings, cruise 0.3 rad/s", cruise=0.3)
report("speed readings, cruise 0.45 rad/s", cruise=0.45)
report("speed readings, exact laptop clock", win_clock=False)
report("encoder positions through the host", encoder=True)
