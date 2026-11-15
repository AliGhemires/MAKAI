"""Dead-reckoning: integrate base velocity to know roughly where we are.

Drifts (omni wheels slip), so it is only used for coarse moves such as "go back
towards where the mission started". Anything precise is done with the camera.
"""

from __future__ import annotations

import math

from makai.contracts import BaseVelocity

# Observations come 10 to 50 times a second. A silence of more than a second is a blocking skill (a pick lasts
# 8 to 20 s, base stopped) or a lost link: the velocity of the next observation says nothing
# about it. Integrating it over the whole gap turned one noisy speed reading into a jump of
# several degrees after every pick (15 Nov).
MAX_GAP_S = 1.0


class Odometry:
    """Pose of the base in the frame it had at the first update (the 'home' frame)."""

    def __init__(self) -> None:
        self.x = self.y = self.yaw = 0.0
        self._stamp: float | None = None

    def update(self, velocity: BaseVelocity, stamp: float) -> None:
        if self._stamp is not None and stamp - self._stamp <= MAX_GAP_S:
            dt = max(0.0, stamp - self._stamp)
            c, s = math.cos(self.yaw), math.sin(self.yaw)
            self.x += (c * velocity.x - s * velocity.y) * dt
            self.y += (s * velocity.x + c * velocity.y) * dt
            self.yaw += velocity.theta * dt
        self._stamp = stamp

    def home_in_base(self) -> tuple[float, float]:
        """Where the starting point is, seen from the robot now."""
        c, s = math.cos(-self.yaw), math.sin(-self.yaw)
        return c * -self.x - s * -self.y, s * -self.x + c * -self.y

    @property
    def distance_from_home(self) -> float:
        return math.hypot(self.x, self.y)
