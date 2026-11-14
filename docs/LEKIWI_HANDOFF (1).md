# LeKiwi setup — handoff notes (from claude.ai chat, 2026-11-14)

Context for Claude Code: this summarizes what was set up and verified on the
real robot today. Reconcile with the repo's existing `docs/SETUP.md` and
`robot.drive()` rather than overwriting them.

## Hardware state (verified)
- Base: 3 omniwheels, Feetech STS3215 servos in velocity mode.
- Wheel motor IDs: **left = 7, back = 8, right = 9** (already set, no setup needed).
- Battery: 12.5 V reading (`Present_Voltage` = 125) → 12 V servo version.
- Arm (IDs 1–6) not attached yet. When it is: same bus, then
  `lerobot-calibrate --robot.type=lekiwi --robot.id=makai_kiwi` on the Pi.
- Wheels need no calibration.
- Spin test: each wheel turns individually. **Keyboard driving works on the Pi.**
- Still to verify on the floor: w = forward (camera side), a = left,
  q = counter-clockwise; measured speed vs commanded (0.15 m/s for 4 s ≈ 60 cm).

## Cables out of the robot
| Cable | What | Wired mode (laptop) | Pi mode |
|---|---|---|---|
| USB #1 | Motor driver board | `COM5` | `/dev/ttyACM0` |
| USB #2 | Front camera | OpenCV index `1` (0 = laptop webcam) | `/dev/video0` (YUYV 640x480 @30) |
| USB-C | 5 V power for the Pi | unplugged | Pi USB-C power port |

On the Pi, `/dev/video19+` are Pi 5 ISP/codec nodes, not cameras.
For a stable camera path use `/dev/v4l/by-id/...`.

## Software
- LeRobot **0.7.1** (source install, `pip install -e ".[lekiwi]"`) on laptop and Pi.
- Laptop: Windows, Miniforge, conda env `lerobot`, Python 3.12, ffmpeg 7.1.1.
- Pi 5: Raspberry Pi OS Lite 64-bit on 64 GB microSD, hostname `lekiwi`,
  user `kiwi`, `ssh kiwi@lekiwi.local` (IPv4 172.20.10.3 on the iPhone hotspot).
  conda env `lerobot`, repo at `~/lerobot`. User is in `dialout` group.

### Pi install gotchas
- `/tmp` is a 2 GB tmpfs → pip fails with "No space left on device" on the
  CUDA torch wheels. Fix:
  ```
  mkdir -p ~/tmp && export TMPDIR=~/tmp
  pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
  pip install --no-cache-dir -e ".[lekiwi]"
  ```
- After reconnecting: `conda activate lerobot && cd ~/lerobot`.

### Windows gotchas
- Python code must go in a `.py` file (`python file.py`), not typed into cmd.
- A Bonjour `mdnsNSP.dll` LSA warning during pip is unrelated, ignore.
- Allow Python through the firewall for Pi ↔ laptop ZeroMQ later.

## Notes
- `FeetechMotorsBus` prints a DeprecationWarning (use `SerialMotorsBus`); it still works in 0.7.1.
- Stock `lekiwi` robot class / `lekiwi_host` expects all 9 motors (arm + base),
  so base-only scripts talk to the bus directly.
- Kinematics used (from LeRobot's LeKiwi): wheel angles `(240, 0, 120) - 90` deg
  for (left, back, right), wheel radius 0.05 m, base radius 0.125 m,
  raw velocity = deg/s * 4096/360, clamped to ±3000.

## Scripts that were tested

### check_motors.py (reads position + voltage)
```python
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

bus = FeetechMotorsBus(
    port="COM5",
    motors={
        "left": Motor(7, "sts3215", MotorNormMode.RANGE_M100_100),
        "back": Motor(8, "sts3215", MotorNormMode.RANGE_M100_100),
        "right": Motor(9, "sts3215", MotorNormMode.RANGE_M100_100),
    },
)
bus.connect()
print(bus.sync_read("Present_Position", normalize=False))
print(bus.sync_read("Present_Voltage", normalize=False))
bus.disconnect()
```

### spin_test.py (each wheel 1.5 s, one at a time)
```python
import time
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

bus = FeetechMotorsBus(
    port="COM5",
    motors={
        "left": Motor(7, "sts3215", MotorNormMode.RANGE_M100_100),
        "back": Motor(8, "sts3215", MotorNormMode.RANGE_M100_100),
        "right": Motor(9, "sts3215", MotorNormMode.RANGE_M100_100),
    },
)
bus.connect()
bus.disable_torque()
for name in bus.motors:
    bus.write("Operating_Mode", name, OperatingMode.VELOCITY.value)
bus.enable_torque()

try:
    for name in ["left", "back", "right"]:
        print("Spinning", name)
        bus.write("Goal_Velocity", name, 500)
        time.sleep(1.5)
        bus.write("Goal_Velocity", name, 0)
        time.sleep(0.5)
finally:
    for name in bus.motors:
        bus.write("Goal_Velocity", name, 0)
    bus.disconnect()
```

### drive_pi.py (keyboard teleop over SSH, Linux) — verified working
```python
import math, time, sys, select, termios, tty
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

NAMES = ["left", "back", "right"]
bus = FeetechMotorsBus(
    port="/dev/ttyACM0",
    motors={
        "left": Motor(7, "sts3215", MotorNormMode.RANGE_M100_100),
        "back": Motor(8, "sts3215", MotorNormMode.RANGE_M100_100),
        "right": Motor(9, "sts3215", MotorNormMode.RANGE_M100_100),
    },
)

WHEEL_R, BASE_R = 0.05, 0.125
ANGLES = [math.radians(a - 90) for a in (240, 0, 120)]


def body_to_raw(x, y, theta_deg):
    th = math.radians(theta_deg)
    out = {}
    for n, a in zip(NAMES, ANGLES):
        v = math.cos(a) * x + math.sin(a) * y + BASE_R * th
        raw = math.degrees(v / WHEEL_R) * 4096 / 360
        out[n] = int(max(-3000, min(3000, round(raw))))
    return out


KEYS = {
    "w": (0.15, 0, 0),
    "s": (-0.15, 0, 0),
    "a": (0, 0.15, 0),
    "d": (0, -0.15, 0),
    "q": (0, 0, 45),
    "e": (0, 0, -45),
}


def get_key():
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1).lower()
    return None


bus.connect()
bus.disable_torque()
for n in NAMES:
    bus.write("Operating_Mode", n, OperatingMode.VELOCITY.value)
bus.enable_torque()

old = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())
print("w/s a/d q/e, space stop, x quit")
cmd, last = (0, 0, 0), time.time()
try:
    while True:
        k = get_key()
        if k == "x":
            break
        if k:
            cmd, last = KEYS.get(k, (0, 0, 0)), time.time()
        if time.time() - last > 0.6:
            cmd = (0, 0, 0)
        bus.sync_write("Goal_Velocity", body_to_raw(*cmd), normalize=False)
        time.sleep(0.05)
finally:
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
    bus.sync_write("Goal_Velocity", {n: 0 for n in NAMES}, normalize=False)
    bus.disconnect()
```

The Windows variant (`drive.py`) is identical except `port="COM5"` and it reads
keys with `msvcrt.kbhit()` / `msvcrt.getch()` instead of termios/select.
