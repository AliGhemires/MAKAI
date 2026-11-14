import math

import pytest

from makai.contracts import BaseVelocity
from makai.navigation.approach import ApproachConfig, ApproachController


def simulate(x: float, y: float, cfg: ApproachConfig, dt: float = 1 / 30, max_ticks: int = 3000):
    """Closed loop: apply the commanded velocity to a point fixed in the world."""
    ctrl = ApproachController(cfg)
    for tick in range(max_ticks):
        vel, arrived = ctrl.step(x, y)
        if arrived:
            return x, y, tick
        # Moving the base by (vx, vy) and turning by w moves the point the opposite way.
        x, y = x - vel.x * dt, y - vel.y * dt
        c, s = math.cos(-vel.theta * dt), math.sin(-vel.theta * dt)
        x, y = c * x - s * y, s * x + c * y
    raise AssertionError(f"did not converge, point still at ({x:.3f}, {y:.3f})")


@pytest.mark.parametrize(
    "start", [(1.5, 0.0), (1.0, 0.8), (0.6, -0.5), (0.25, 0.08), (0.15, 0.0), (-0.5, 0.6)]
)
def test_converges_to_the_pre_grasp_pose(start):
    cfg = ApproachConfig()
    x, y, _ = simulate(*start, cfg)
    assert abs(x - cfg.goal_x_m) <= cfg.tol_x_m and abs(y - cfg.goal_y_m) <= cfg.tol_y_m


def test_respects_speed_limits():
    cfg = ApproachConfig()
    vel, _ = ApproachController(cfg).step(3.0, 2.0)
    assert abs(vel.x) <= cfg.max_lin and abs(vel.theta) <= cfg.max_ang


def test_turns_towards_the_point_when_far():
    left, _ = ApproachController().step(1.0, 1.0)
    right, _ = ApproachController().step(1.0, -1.0)
    assert left.theta > 0 > right.theta


def test_arrival_needs_consecutive_settled_ticks():
    cfg = ApproachConfig(settle_ticks=3)
    ctrl = ApproachController(cfg)
    assert ctrl.step(cfg.goal_x_m, cfg.goal_y_m) == (BaseVelocity(), False)
    assert ctrl.step(cfg.goal_x_m, cfg.goal_y_m)[1] is False
    assert ctrl.step(cfg.goal_x_m + 0.1, 0.0)[1] is False  # disturbed: counter restarts
    assert [ctrl.step(cfg.goal_x_m, cfg.goal_y_m)[1] for _ in range(3)] == [False, False, True]
