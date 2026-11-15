"""Run the sweeping mission from the control page, on the page's own control loop.

The page's `DriveLoop` owns the robot: every robot call happens on its thread. A mission is
therefore not a second thread fighting for the robot; while one runs, the loop calls the
mission's `step()` instead of listening to the sticks. Everything the mission observes and
commands still feeds the page (cameras, speeds, arm), through `Tap`.

Stopping: the page's STOP (emergency stop) ends the mission at the next observation, even in
the middle of a pick, because `Tap` refuses to hand out observations once it is pressed.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from makai.contracts import BaseVelocity, Observation
from makai.navigation.zone import zone_from_markers, zone_from_trail
from makai.orchestrator.mission import TERMINAL
from makai.orchestrator.sweep import USES

log = logging.getLogger("makai.autopilot")

SNAPSHOT_PERIOD_S = 0.1
TRACE_PERIOD_S = 0.1  # while the zone is traced, how often the robot's position is noted
TRACE_STEP_M = 0.02


class MissionAborted(Exception):
    """Raised inside the mission when the page asked it to stop."""


class Tap:
    """The robot as the mission sees it. Every observation and command also feeds the page, and
    a stop request cuts the mission short wherever it is."""

    def __init__(self, robot: Any, loop: Any, stop_requested: Callable[[], bool]):
        self._robot, self._loop, self._stop_requested = robot, loop, stop_requested

    def get_observation(self) -> Observation:
        if self._stop_requested():
            raise MissionAborted
        obs = self._robot.get_observation()
        self._loop.observed(obs)
        return obs

    def drive(self, velocity: BaseVelocity) -> None:
        self._robot.drive(velocity)
        self._loop.note_command(velocity)

    def stop(self) -> None:
        self._robot.stop()
        self._loop.note_command(BaseVelocity())

    def __getattr__(self, name: str) -> Any:  # move_arm, client, raw_observation, dt...
        return getattr(self._robot, name)


class MissionRunner:
    """Starts, steps and stops one mission at a time, and keeps what the page shows about it.

    `build(robot, use)` returns a ready mission for one of the two uses ("vacuum" or "scan",
    `orchestrator.sweep.USES`); it may take seconds (loading the detector and the policies),
    so it runs on its own thread while the page shows "loading".
    `preview()` returns the plan (room, route, stations) to draw before any mission has run.

    The runner also traces the zone to sweep (`navigation.zone`): between `trace()` and
    `trace_done()` the pilot drives the robot around the zone, and the path becomes the room of
    the next missions. `use_zone(room)` applies a traced room; `use_zone(None)` forgets it.
    """

    def __init__(
        self,
        loop: Any,
        driver: Any,
        build: Callable[[Any, str], Any],
        preview: Callable[[], dict[str, Any]],
        reset: Callable[[], None] | None = None,
        simulated: bool = False,
        use_zone: Callable[..., None] | None = None,
        see_markers: Callable[[], dict] | None = None,
        prepare: Callable[[Any], None] | None = None,
    ):
        self.loop, self.driver, self._build, self._preview, self._reset = loop, driver, build, preview, reset
        # Played once on the loop's thread before the first step of each mission, with the
        # mission's robot: the console puts the arm in its home pose there (scripts/drive.py).
        self._prepare, self._prepare_pending, self._tap = prepare, False, None
        self.simulated = simulated
        self.use = USES[0]  # the use of the last mission started, and of the next by default
        self._use_zone = use_zone  # use_zone(room, stations=None); use_zone(None) forgets the zone
        self._see_markers = see_markers  # the station markers the front camera sees right now
        self._trace: list[tuple[float, float]] | None = None  # the path driven while tracing the zone
        self._trace_yaw = 0.0
        self.status = "idle"  # idle, loading, running, done, failed, stopped
        self.message = ""
        self.mission: Any = None
        self._shot: dict[str, Any] | None = None
        self._shot_at = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._why = ""
        self.runs = 0

    # ------------------------------------------------------------ from the page
    def start(self, use: str | None = None) -> None:
        """Start a mission, for this use (default: the last one). ValueError, with the reason,
        if it cannot."""
        if use is not None and use not in USES:
            raise ValueError(f"The use must be one of {', '.join(USES)}.")
        if self.driver.estopped:
            raise ValueError("Emergency stop is on: resume first.")
        if self._trace is not None:
            raise ValueError("The zone is being traced: end the trace first.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("A mission is already running.")
            self.status, self.message = "loading", "loading the detector and the policies"
            self.use = use or self.use
            self._stop.clear()
        threading.Thread(target=self._load, name="mission-load", daemon=True).start()

    def stop(self, why: str = "stopped from the page") -> None:
        self._why = why
        self._stop.set()
        with self._lock:
            if self.status == "loading":
                self.status, self.message = "stopped", why

    def reset(self) -> None:
        """Simulation only: put the objects back on the floor and the robot at the origin."""
        if self._reset is None:
            raise ValueError("Only the simulation can be reset.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("Stop the mission first.")
        self._reset()
        self.mission, self._shot = None, None
        self.status, self.message = "idle", ""

    # ------------------------------------------------------------ the zone, traced by driving
    def trace(self) -> None:
        """Start tracing the zone: the robot is at the start pose, and the pilot will drive it
        around the zone. ValueError, with the reason, if it cannot start."""
        if self._use_zone is None:
            raise ValueError("The zone cannot be traced here.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("Stop the mission first.")
        if self._reset is not None:
            self._reset()  # simulation: the robot back at the start pose
        elif not self.loop.reset_odometry():  # the start pose is the origin of the zone
            raise ValueError("A precise move is running: wait for it to end.")
        self.mission, self._shot = None, None
        self.status, self.message = "idle", ""
        self._trace, self._trace_yaw = [(0.0, 0.0)], 0.0
        threading.Thread(target=self._follow, name="zone-trace", daemon=True).start()

    def trace_done(self) -> None:
        """End the trace: the rectangle around the path becomes the zone of the next missions.
        ValueError if the path is too short to be a zone; the trace then goes on."""
        if self._trace is None or self._use_zone is None:
            raise ValueError("No trace is running.")
        room = zone_from_trail(self._trace)
        self._trace = None
        self._use_zone(room)
        self.message = (
            f"zone traced: {room['length_m']:.2f} m deep, {room['width_m']:.2f} m wide. "
            "Put the robot back at the start pose before starting."
        )

    def trace_cancel(self) -> None:
        self._trace = None

    def zone_from_marker(self) -> None:
        """Set the zone without driving: the robot is at the start pose and the bin stands
        across the zone, its marker facing the robot. The camera reads where the marker is.
        ValueError, with the reason, if it cannot."""
        if self._use_zone is None or self._see_markers is None:
            raise ValueError("The zone cannot be read on a marker here.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("Stop the mission first.")
        room, stations = zone_from_markers(self._see_markers(), self._preview()["room"])
        self._trace = None
        self._use_zone(room, stations)
        self.mission, self._shot = None, None
        self.status = "idle"
        far = ", ".join(f"{name} {place['x']:.2f} m ahead" for name, place in stations.items())
        self.message = f"zone read on the marker: {far}; zone {room['length_m']:.2f} m deep."

    def zone_forget(self) -> None:
        """Drop the traced zone and go back to the room of the config."""
        if self._use_zone is None:
            raise ValueError("The zone cannot be traced here.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("Stop the mission first.")
        self._trace = None
        self._use_zone(None)
        self.message = ""

    def trace_sample(self) -> None:
        """Note where the robot is now, if the zone is being traced."""
        trace = self._trace
        if trace is None:
            return
        pose = self.loop.snapshot()["pose"]
        point = (pose["x"], pose["y"])
        if math.dist(trace[-1], point) >= TRACE_STEP_M:
            trace.append(point)
        self._trace_yaw = math.radians(pose["yaw_deg"])

    def _follow(self) -> None:
        """Note where the robot goes while the pilot drives it around the zone."""
        while self._trace is not None:
            self.trace_sample()
            time.sleep(TRACE_PERIOD_S)

    def _zone(self) -> dict[str, Any] | None:
        if self._use_zone is None:
            return None
        trace = self._trace
        if trace is None:
            return {"tracing": False}
        trail = list(trace)
        box = zone_from_trail(trail, check=False)
        # Room to draw around a trace that has barely begun.
        box["length_m"], box["width_m"] = max(box["length_m"], 1.0), max(box["width_m"], 1.0)
        return {
            "tracing": True,
            "trail": trail[:: max(1, len(trail) // 400)] + trail[-1:],
            "pose": {"x": trail[-1][0], "y": trail[-1][1], "yaw": round(self._trace_yaw, 3)},
            "box": box,
            "size": zone_from_trail(trail, check=False),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "simulated": self.simulated,
            "use": self.use,
            "runs": self.runs,
            "mission": self._shot,
            "plan": self._preview(),
            "zone": self._zone(),
        }

    # ------------------------------------------------------------ on the loop's thread
    def step(self) -> None:
        mission = self.mission
        try:
            if self._prepare_pending:  # before the robot moves: the stop and the e-stop still apply
                self._prepare_pending = False
                self._prepare(self._tap)
            state = mission.step()
        except MissionAborted:
            self._finish("stopped", "emergency stop" if self.driver.estopped else self._why or "stopped")
            return
        except Exception as error:  # noqa: BLE001 - anything: the page must show it and the robot must stop
            log.exception("mission failed")
            self._finish("failed", f"{type(error).__name__}: {error}")
            return
        now = time.monotonic()
        if state in TERMINAL or now - self._shot_at >= SNAPSHOT_PERIOD_S:
            self._shot, self._shot_at = mission.snapshot(), now
        if state in TERMINAL:
            reason = mission.events[-1].reason if mission.events else ""
            self._finish("done" if state.value == "done" else "failed", reason)

    # ------------------------------------------------------------ internals
    def _load(self) -> None:
        try:
            robot = Tap(self.loop.robot, self.loop, lambda: self._stop.is_set() or self.driver.estopped)
            mission = self._build(robot, self.use)
        except Exception as error:  # noqa: BLE001 - a missing model or calibration: say which
            log.exception("mission could not be prepared")
            with self._lock:
                self.status, self.message = "failed", f"{type(error).__name__}: {error}"
            return
        with self._lock:
            if self._stop.is_set():  # stopped while loading
                return
            self.mission, self._shot = mission, mission.snapshot()
            self._tap, self._prepare_pending = robot, self._prepare is not None
            self.status, self.message = "running", ""
            self.runs += 1
        self.loop.autopilot = self.step

    def _finish(self, status: str, message: str) -> None:
        self.loop.autopilot = None
        try:
            self.loop.robot.stop()
        except Exception:  # noqa: BLE001 - the link may be the reason we are stopping
            log.exception("could not stop the base")
        self.loop.note_command(BaseVelocity())
        self.driver.reset_motion()
        if self.mission is not None:
            self._shot = self.mission.snapshot()
        with self._lock:
            self.status, self.message = status, message
        log.info("mission %s: %s", status, message)
