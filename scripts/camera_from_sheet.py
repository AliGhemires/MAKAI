"""Measure the front camera (field of view, height, tilt) from ONE A4 sheet on the floor.

No ruler, no printer. The sheet goes anywhere in front of the robot, flat and fully in the image;
its position does not matter, only its shape (210 x 297 mm) is used.

1. Lay one A4 sheet flat on the floor in the lower middle of the image, long side pointing away
   from the robot (portrait). Black corners drawn with a felt pen make it easier to read.
2. Save a front image: with the console running, http://localhost:8000/api/camera/front.jpg?download=1
3. Read the 4 corner pixels in Paint, in this order: near-left, near-right, far-right, far-left
   (near = bottom of the image).
4. Run:

    uv run python scripts/camera_from_sheet.py front.jpg "112,400 470,395 430,210 170,214"
    uv run python scripts/camera_from_sheet.py front.jpg "..." --landscape   # long side across

It prints the `perception.camera_model` values to put in configs/makai.yaml (they belong to the
robot: commit them) and writes front_camera_check.jpg with a 10 cm floor grid drawn from them.
Several photos with the sheet moved give several results: they should agree within ~1 degree.
The floor mapping then comes from this camera model, so configs/ground_plane.yaml must NOT exist.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

from makai.config import CONFIG_DIR, load_config
from makai.perception.geometry import CameraModel

A4_LONG, A4_SHORT = 0.297, 0.210


def intrinsics(f: float, width: int, height: int) -> np.ndarray:
    return np.array([[f, 0.0, width / 2.0], [0.0, f, height / 2.0], [0.0, 0.0, 1.0]])


def solve(pixels: np.ndarray, sheet: np.ndarray, f: float, size: tuple[int, int]):
    ok, rvec, tvec = cv2.solvePnP(sheet, pixels, intrinsics(f, *size), None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return math.inf, rvec, tvec
    back = cv2.projectPoints(sheet, rvec, tvec, intrinsics(f, *size), None)[0].reshape(-1, 2)
    return float(np.linalg.norm(back - pixels, axis=1).mean()), rvec, tvec


def fit_camera(pixels: np.ndarray, along: float, across: float, size: tuple[int, int]) -> dict:
    """Focal length by search, then the floor plane seen from the camera: height, tilt, roll.

    `along`: rectangle side pointing away from the robot; `across`: the other side, in metres.
    """
    # Sheet frame, same corner order as the pixels: near-left, near-right, far-right, far-left.
    sheet = np.array([[0, across, 0], [0, 0, 0], [along, 0, 0], [along, across, 0]], dtype=np.float64)
    width = size[0]
    focals = [(width / 2) / math.tan(math.radians(h) / 2) for h in np.arange(30.0, 80.0, 0.25)]
    best = min(((*solve(pixels, sheet, f, size), f) for f in focals), key=lambda r: r[0])
    for f in np.linspace(best[3] * 0.985, best[3] * 1.015, 61):
        candidate = (*solve(pixels, sheet, f, size), f)
        if candidate[0] < best[0]:
            best = candidate
    error, rvec, tvec, f = best
    normal, t = cv2.Rodrigues(rvec)[0][:, 2], tvec.reshape(3)
    up = normal if normal @ t < 0 else -normal  # floor normal pointing at the camera (camera frame)
    return {
        "hfov_deg": math.degrees(2 * math.atan((width / 2) / f)),
        "height_m": float(abs(normal @ t)),
        "pitch_deg": math.degrees(math.asin(-up[2])),
        "roll_deg": math.degrees(math.asin(float(np.clip(up[0], -1.0, 1.0)))),
        "error_px": error,
    }


def draw_grid(image: np.ndarray, camera: CameraModel) -> np.ndarray:
    out, plane = image.copy(), camera.ground_plane()

    def pixel(x: float, y: float) -> tuple[int, int] | None:
        p = plane.ground_to_image @ np.array([x, y, 1.0])
        return (int(round(p[0] / p[2])), int(round(p[1] / p[2]))) if p[2] > 1e-9 else None

    for x in np.arange(0.1, 2.01, 0.1):
        a, b = pixel(x, -1.0), pixel(x, 1.0)
        if a and b:
            cv2.line(out, a, b, (0, 255, 255) if abs(x - round(x * 2) / 2) < 1e-6 else (150, 150, 150), 1)
    for y in np.arange(-1.0, 1.01, 0.1):
        a, b = pixel(0.1, y), pixel(2.0, y)
        if a and b:
            cv2.line(out, a, b, (150, 150, 150), 1)
    return out


def read_points(path: Path) -> list[tuple[str, float, float, float, float]]:
    """Lines `u, v, x_m, y_m[, name]`; lines with an empty u or v are skipped."""
    points = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line[0].isalpha():
            continue
        f = [c.strip() for c in line.replace(";", ",").split(",")]
        if len(f) >= 4 and f[0] and f[1]:
            name = f[4] if len(f) > 4 else str(len(points) + 1)
            points.append((name, *(float(c) for c in f[:4])))
    return points


def check_against_marks(camera: CameraModel, points: list) -> float:
    """Compare the camera model with tape marks measured from the base centre; return the x shift."""
    plane = camera.ground_plane()
    rows = [(name, x, y, *plane.pixel_to_ground(u, v)) for name, u, v, x, y in points]
    shift = float(np.mean([x - px for _, x, _, px, _ in rows]))
    side = float(np.mean([y - py for _, _, y, _, py in rows]))
    print()
    print("mark   measured x, y   |  camera x, y    | error   | after the x shift")
    after = []
    for name, x, y, px, py in rows:
        e0, e1 = np.hypot(px - x, py - y), np.hypot(px + shift - x, py - y)
        after.append(e1)
        print(
            f"{name:5s} {x:6.3f} {y:+6.3f}  | {px:6.3f} {py:+6.3f}  | {e0 * 100:4.1f} cm | {e1 * 100:4.1f} cm"
        )
    print(f"origin shift along x: {shift * 100:+.1f} cm (added to x_offset_m below)")
    print(f"mean error after the shift: {np.mean(after) * 100:.1f} cm, worst {max(after) * 100:.1f} cm")
    if abs(side) > 0.015:
        print(f"[WARN] marks are {side * 100:+.1f} cm to the side on average: camera off-centre or turned")
    if np.mean(after) > 0.02:
        print(
            "[WARN] more than 2 cm after the shift: re-read the pixels, re-measure, or redo the sheet photo"
        )
    return shift


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("image", type=Path, help="front camera image with the sheet")
    parser.add_argument("corners", help='"u,v u,v u,v u,v": near-left, near-right, far-right, far-left')
    parser.add_argument(
        "--size",
        default=f"{A4_LONG},{A4_SHORT}",
        metavar="ALONG,ACROSS",
        help="rectangle sides in metres: pointing away from the robot, then across (default: A4 portrait)",
    )
    parser.add_argument("--landscape", action="store_true", help="A4 with its long side across the image")
    parser.add_argument(
        "--check",
        type=Path,
        metavar="CSV",
        help="tape marks measured from the base centre (u, v, x_m, y_m[, name]): checks the model, sets x_offset_m",
    )
    parser.add_argument(
        "--from-camera",
        nargs="?",
        const=-1.0,
        type=float,
        metavar="AHEAD_M",
        help="the marks were measured from the floor point under the lens; the lens is AHEAD_M metres "
        "ahead of the base centre (default: the current x_offset_m)",
    )
    args = parser.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"cannot read {args.image}")
    size = (image.shape[1], image.shape[0])
    pixels = np.array([[float(c) for c in p.split(",")] for p in args.corners.split()], dtype=np.float64)
    if pixels.shape != (4, 2):
        raise SystemExit("give exactly 4 corners: near-left, near-right, far-right, far-left")
    along, across = (float(c) for c in args.size.split(","))
    if args.landscape:
        along, across = across, along

    cam = fit_camera(pixels, along, across, size)
    print(f"image {size[0]}x{size[1]}, rectangle {along * 100:.1f} x {across * 100:.1f} cm, ", end="")
    print(f"corners re-projected within {cam['error_px']:.2f} px")
    print(f"field of view {cam['hfov_deg']:.1f} deg, lens height {cam['height_m'] * 100:.1f} cm, ", end="")
    print(f"tilt {cam['pitch_deg']:.1f} deg down, roll {cam['roll_deg']:+.1f} deg")
    if cam["error_px"] > 2.0:
        print("[WARN] the corners do not fit the rectangle: check their order, --size, and that it lies flat")
    if abs(cam["roll_deg"]) > 2.0:
        print("[WARN] the camera leans sideways by more than 2 degrees: the model ignores it")

    cfg = load_config()
    current = cfg["perception"]["camera_model"]
    camera = CameraModel(
        width=size[0],
        height=size[1],
        hfov_deg=cam["hfov_deg"],
        height_m=cam["height_m"],
        pitch_deg=cam["pitch_deg"],
        x_offset_m=current["x_offset_m"],
    )
    x_offset = current["x_offset_m"]
    if args.check:
        points = read_points(args.check)
        if len(points) < 2:
            raise SystemExit(f"{args.check}: fewer than 2 marks with a pixel filled in")
        if args.from_camera is not None:
            ahead = x_offset if args.from_camera < 0 else args.from_camera
            print(f"marks measured from under the lens, lens {ahead * 100:.1f} cm ahead of the base centre")
            points = [(name, u, v, x + ahead, y) for name, u, v, x, y in points]
        x_offset = round(x_offset + check_against_marks(camera, points), 3)
        camera = CameraModel(**{**camera.__dict__, "x_offset_m": x_offset})

    print()
    print("Put this in configs/makai.yaml, perception.camera_model:")
    print(f"    width: {size[0]}")
    print(f"    height: {size[1]}")
    print(f"    hfov_deg: {cam['hfov_deg']:.1f}")
    print(f"    height_m: {cam['height_m']:.3f}")
    print(f"    pitch_deg: {cam['pitch_deg']:.1f}")
    print(f"    x_offset_m: {x_offset}")
    if not args.check:
        print("    (x_offset_m unchanged: give --check with a few measured tape marks to set it)")
    print(
        f"(currently: hfov {current['hfov_deg']}, height {current['height_m']}, pitch {current['pitch_deg']})"
    )

    ground_file = CONFIG_DIR / cfg["perception"]["ground_plane_file"]
    if ground_file.exists():
        print(f"[WARN] {ground_file} exists and takes precedence over the camera model: delete it")

    check = args.image.with_name(args.image.stem + "_camera_check.jpg")
    cv2.imwrite(str(check), draw_grid(image, camera))
    print(f"check image: {check} (grey lines every 10 cm, yellow every 50 cm)")


if __name__ == "__main__":
    main()
