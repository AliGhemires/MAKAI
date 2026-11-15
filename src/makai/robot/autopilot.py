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
import threading
import time
from collections.abc import Callable
from typing import Any

from makai.contracts import BaseVelocity, Observation
from makai.orchestrator.mission import TERMINAL

log = logging.getLogger("makai.autopilot")

SNAPSHOT_PERIOD_S = 0.1


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

    `build(robot)` returns a ready mission; it may take seconds (loading the detector and the
    policies), so it runs on its own thread while the page shows "loading".
    `preview()` returns the plan (room, lanes, stations) to draw before any mission has run.
    """

    def __init__(
        self,
        loop: Any,
        driver: Any,
        build: Callable[[Any], Any],
        preview: Callable[[], dict[str, Any]],
        reset: Callable[[], None] | None = None,
        simulated: bool = False,
    ):
        self.loop, self.driver, self._build, self._preview, self._reset = loop, driver, build, preview, reset
        self.simulated = simulated
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
    def start(self) -> None:
        """Start a mission. ValueError, with the reason, if it cannot."""
        if self.driver.estopped:
            raise ValueError("Emergency stop is on: resume first.")
        with self._lock:
            if self.status in ("loading", "running"):
                raise ValueError("A mission is already running.")
            self.status, self.message = "loading", "loading the detector and the policies"
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

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "simulated": self.simulated,
            "runs": self.runs,
            "mission": self._shot,
            "plan": self._preview(),
        }

    # ------------------------------------------------------------ on the loop's thread
    def step(self) -> None:
        mission = self.mission
        try:
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
            mission = self._build(robot)
        except Exception as error:  # noqa: BLE001 - a missing model or calibration: say which
            log.exception("mission could not be prepared")
            with self._lock:
                self.status, self.message = "failed", f"{type(error).__name__}: {error}"
            return
        with self._lock:
            if self._stop.is_set():  # stopped while loading
                return
            self.mission, self._shot = mission, mission.snapshot()
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
