"""How much does the robot REALLY turn when the odometry says 360 degrees? Measured with the
front camera on an ArUco marker: signed, repeated, no tape. Through the host.

Put the robot 1.2 to 2 m in front of a station marker (the bin's), facing it, on the floor of
the demo. Close the console first: both read the same stream. Ctrl+C stops the robot.

    uv run python scripts/turn_check.py                 # 3 full turns to the left, by quarter turns
    uv run python scripts/turn_check.py --turns 5 --speed 0.3
    uv run python scripts/turn_check.py --right         # the other way

Each trial: the direction of the marker is read, the robot turns 360 degrees by odometry (four
exact quarter turns, as the console's), the direction is read again. The robot has turned by
360 degrees plus what the marker moved in the image. If the marker is out of view after the
turn, the robot looks for it to each side.

It prints, per trial, what the odometry counted, what the robot really turned, and the ratio.
- The ratios agree (within 1 %): it is a scale. Put the proposed `angular_scale` in
  configs/makai.yaml (robot.odometry) and run again to check.
- They do not: the wheels slip on this floor by a different amount each time. No factor will
  fix it: turn less, turn slower (--speed), and re-anchor on the marker (docs/NAVIGATION.md).

The robot must turn on the spot: if it also drifts sideways, the marker moves in the image for
that reason too (5 cm at 1.5 m look like 2 degrees). The distance to the marker before and
after is printed for that.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import time

from makai.config import REPO_ROOT, load_config
from makai.contracts import Category
from makai.navigation.odometry import Odometry
from makai.perception.geometry import CameraModel
from makai.perception.stations import StationDetector
from makai.robot.lekiwi import LeKiwiRobot
from makai.robot.moves import GoTo, GoToTuning, wrap_angle

SEARCH_DEG = (15, -15, 30, -30, 45, -45, 60, -60)  # where to look when the marker is out of view


class Rig:
    """The robot, its odometry (as the console's) and the marker detector."""

    def __init__(self, robot: LeKiwiRobot, detector: StationDetector, camera: str):
        self.robot, self.detector, self.camera = robot, detector, camera
        self.odometry = Odometry()

    def observe(self):
        obs = self.robot.get_observation()
        self.odometry.update(obs.base_velocity, obs.stamp)
        return obs

    @property
    def pose(self) -> tuple[float, float, float]:
        return self.odometry.x, self.odometry.y, self.odometry.yaw

    def look(self, seconds: float = 1.0) -> tuple[float, float] | None:
        """Direction (deg, left positive) and distance (m) of the marker, over `seconds`."""
        self.robot.stop()
        bearings, distances, end = [], [], time.monotonic() + seconds
        while time.monotonic() < end:
            obs = self.observe()
            image = obs.images.get(self.camera)
            sightings = self.detector.detect(image) if image is not None else {}
            if sightings:
                sighting = next(iter(sightings.values()))
                bearings.append(math.degrees(math.atan2(sighting.y_m, sighting.x_m)))
                distances.append(sighting.distance_m)
            time.sleep(0.02)
        if len(bearings) < 5:
            return None
        return statistics.median(bearings), statistics.median(distances)

    def turn_to(self, yaw: float, tuning: GoToTuning) -> None:
        """One exact move to a heading, on the spot, as the console does it."""
        x, y, _ = self.pose
        goto = GoTo("turn", (x, y, yaw), self.pose, time.monotonic(), tuning)
        while True:
            obs = self.observe()
            velocity = goto.step(self.pose, obs.stamp)
            if velocity is None:
                break
            self.robot.drive(velocity)
            time.sleep(0.015)
        self.robot.stop()
        if goto.status != "done":
            raise SystemExit(f"The turn ended with '{goto.status}': check the robot.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--turns", type=int, default=3, help="number of full turns measured (default 3)")
    parser.add_argument("--right", action="store_true", help="turn clockwise instead")
    parser.add_argument(
        "--speed", type=float, default=GoToTuning().max_ang_rad_s, help="turning speed, rad/s"
    )
    parser.add_argument("--camera", default="front")
    args = parser.parse_args()

    cfg = load_config()
    p = cfg["perception"]
    detector = StationDetector(
        CameraModel(**p["camera_model"]),
        {int(marker): Category(category) for marker, category in p["stations"]["marker_ids"].items()},
        p["stations"]["marker_size_m"],
    )
    scale = float((cfg["robot"].get("odometry") or {}).get("angular_scale", 1.0))
    tuning = GoToTuning(max_ang_rad_s=args.speed)
    sign = -1.0 if args.right else 1.0
    robot = LeKiwiRobot.from_config(cfg, link="host")
    robot.connect()
    rig = Rig(robot, detector, args.camera)
    rows = []
    try:
        first = rig.look(1.5)
        print(
            f"odometry from: {robot.odometry_source or 'speed readings'}; angular_scale in the config: {scale}"
        )
        if first is None:
            raise SystemExit(
                "No marker in view. Put the robot 1.2 to 2 m in front of the bin's marker, facing it."
            )
        print(f"marker at {first[1]:.2f} m, {first[0]:+.1f} deg. Turning {'right' if args.right else 'left'}, "
              f"{args.turns} x 360 deg by quarter turns at {args.speed:.2f} rad/s. Ctrl+C stops.")  # fmt: skip
        if not 0.8 <= first[1] <= 2.5:
            print("  (1.2 to 2 m is best: closer, a sideways drift of the robot looks like a rotation)")
        for trial in range(1, args.turns + 1):
            before = rig.look(1.0)
            if before is None:
                raise SystemExit("Marker lost before the turn: put the robot back in front of it.")
            start = rig.pose[2]
            for quarter in range(1, 5):
                rig.turn_to(start + sign * quarter * math.pi / 2, tuning)
                time.sleep(0.5)
            nominal = rig.pose[2]
            after, offset = rig.look(1.0), 0.0
            for search in SEARCH_DEG if after is None else ():
                rig.turn_to(nominal + math.radians(search), GoToTuning(max_ang_rad_s=0.25))
                after = rig.look(0.6)
                if after is not None:
                    offset = math.degrees(wrap_angle(rig.pose[2] - nominal))
                    break
            counted = math.degrees(nominal - start)
            if after is None:
                print(
                    f"  {trial}: odometry {counted:+.1f} deg, marker not found within 60 deg: more than that off."
                )
                rows.append([trial, counted, "", "", before[1], ""])
                rig.turn_to(nominal, tuning)
                continue
            # Seen from the nominal heading, the marker would be `offset` further to the left.
            moved = (after[0] + offset) - before[0]
            real = sign * 360.0 - moved
            ratio = real / counted
            print(f"  {trial}: odometry {counted:+7.1f} deg, really {real:+7.1f} deg ({real - counted:+5.1f}), "
                  f"ratio {ratio:.3f}; marker at {before[1]:.2f} m before, {after[1]:.2f} m after")  # fmt: skip
            rows.append([trial, counted, real, ratio, before[1], after[1]])
            if offset:
                rig.turn_to(nominal - math.radians(moved), GoToTuning(max_ang_rad_s=0.25))  # face it again
    except KeyboardInterrupt:
        print("stopped")
    finally:
        robot.stop()
        robot.disconnect()

    ratios = [row[3] for row in rows if row[3] != ""]
    if rows:
        path = REPO_ROOT / "data" / "turn_check.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", newline="") as file:
            writer = csv.writer(file)
            if new:
                writer.writerow(["time", "trial", "direction", "speed_rad_s", "angular_scale", "odometry_source",
                                 "counted_deg", "real_deg", "ratio", "marker_before_m", "marker_after_m"])  # fmt: skip
            for row in rows:
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), row[0], "right" if args.right else "left",
                                 args.speed, scale, robot.odometry_source or "speed readings", *row[1:]])  # fmt: skip
        print(f"saved in {path}")
    if len(ratios) >= 2:
        mean, spread = statistics.fmean(ratios), max(ratios) - min(ratios)
        print(f"\nratio real / odometry: {mean:.3f} on average, from {min(ratios):.3f} to {max(ratios):.3f}")
        if spread <= 0.012:
            print(f"The trials agree: it is a scale. Set robot.odometry.angular_scale: {scale * mean:.3f} "
                  "in configs/makai.yaml, then run this again: the ratio must come out at 1.00.")  # fmt: skip
        else:
            print(f"The trials differ by {100 * spread:.1f} %: this is not a scale, the wheels slip differently each "
                  "time. Try --speed 0.3; if it stays, do not rely on turns: see docs/DEBUG_ODOMETRY.md.")  # fmt: skip


if __name__ == "__main__":
    main()
