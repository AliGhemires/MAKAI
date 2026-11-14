"""LeKiwi host with smoother arm motion. Runs ON THE PI, in place of
`python -m lerobot.robots.lekiwi.lekiwi_host`, with the same --robot.* / --host.* arguments.

LeRobot sets every servo to maximum acceleration (254). Over Wi-Fi, commands arrive in
bursts, so the arm freezes then snaps to the latest target. A lower `Acceleration` on the
arm servos makes them ramp instead. The wheels keep 254 so the base still stops at once.

    scp scripts/lekiwi_host.py kiwi@<pi>:~/makai_host.py
    python ~/makai_host.py --arm_acceleration=50 --robot.id=makai_kiwi ...

--arm_acceleration: 1 (very soft, laggy) to 254 (LeRobot default, snappy). Unit: 100 steps/s².
"""

import sys

from lerobot.robots.lekiwi import lekiwi, lekiwi_host

DEFAULT_ARM_ACCELERATION = 50


def _pop_arm_acceleration() -> int:
    """Read and remove our own flag so that draccus only sees LeRobot's arguments."""
    value = DEFAULT_ARM_ACCELERATION
    for arg in list(sys.argv[1:]):
        if arg.startswith("--arm_acceleration="):
            value = int(arg.split("=", 1)[1])
            sys.argv.remove(arg)
    if not 1 <= value <= 254:
        raise SystemExit(f"--arm_acceleration must be in 1..254, got {value}")
    return value


ARM_ACCELERATION = _pop_arm_acceleration()
_stock_configure = lekiwi.LeKiwi.configure


def _configure(self) -> None:
    _stock_configure(self)
    self.bus.disable_torque(self.arm_motors)
    for motor in self.arm_motors:
        self.bus.write("Acceleration", motor, ARM_ACCELERATION)
    self.bus.enable_torque(self.arm_motors)
    print(f"Arm acceleration set to {ARM_ACCELERATION} (LeRobot default 254)")


lekiwi.LeKiwi.configure = _configure

if __name__ == "__main__":
    lekiwi_host.main()
