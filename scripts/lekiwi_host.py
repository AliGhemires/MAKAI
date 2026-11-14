"""LeKiwi host with smoother arm motion. Runs ON THE PI, in place of
`python -m lerobot.robots.lekiwi.lekiwi_host`, with the same --robot.* / --host.* arguments.

LeRobot sets every servo to maximum acceleration (254). Over Wi-Fi, commands arrive in
bursts, so the arm freezes then snaps to the latest target. A lower `Acceleration` on the
arm servos makes them ramp instead. The wheels keep 254 so the base still stops at once.

    scp scripts/lekiwi_host.py kiwi@<pi>:~/makai_host.py
    python ~/makai_host.py --arm_acceleration=50 --robot.id=makai_kiwi ...

--arm_acceleration: 1 (very soft, laggy) to 254 (LeRobot default, snappy). Unit: 100 steps/s².
--jpeg_quality: 30 to 100, default 90 (what LeRobot sends). Two 640x480 cameras at 30 Hz weigh
    about 60 Mbit/s at 90: when the Wi-Fi does not carry that, images arrive late. 75 sends
    about 40 % less. Choose it BEFORE recording and keep it for the demo: the policy must see
    the same pictures as in its training data.
"""

import sys

import cv2
from lerobot.robots.lekiwi import lekiwi, lekiwi_host

DEFAULT_ARM_ACCELERATION = 50
DEFAULT_JPEG_QUALITY = 90


def _pop_flag(name: str, default: int, low: int, high: int) -> int:
    """Read and remove one of our own flags so that draccus only sees LeRobot's arguments."""
    value = default
    for arg in list(sys.argv[1:]):
        if arg.startswith(f"--{name}="):
            value = int(arg.split("=", 1)[1])
            sys.argv.remove(arg)
    if not low <= value <= high:
        raise SystemExit(f"--{name} must be in {low}..{high}, got {value}")
    return value


ARM_ACCELERATION = _pop_flag("arm_acceleration", DEFAULT_ARM_ACCELERATION, 1, 254)
JPEG_QUALITY = _pop_flag("jpeg_quality", DEFAULT_JPEG_QUALITY, 30, 100)
_stock_configure = lekiwi.LeKiwi.configure


def _configure(self) -> None:
    _stock_configure(self)
    self.bus.disable_torque(self.arm_motors)
    for motor in self.arm_motors:
        self.bus.write("Acceleration", motor, ARM_ACCELERATION)
    self.bus.enable_torque(self.arm_motors)
    print(f"Arm acceleration set to {ARM_ACCELERATION} (LeRobot default 254)")


lekiwi.LeKiwi.configure = _configure

if JPEG_QUALITY != DEFAULT_JPEG_QUALITY:
    # LeRobot's host loop hard-codes quality 90 in its call to cv2.imencode.
    _stock_imencode = cv2.imencode

    def _imencode(ext, image, params=None):
        return _stock_imencode(ext, image, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])

    cv2.imencode = _imencode
    print(f"Camera images sent at JPEG quality {JPEG_QUALITY} (LeRobot default 90)")

if __name__ == "__main__":
    lekiwi_host.main()
