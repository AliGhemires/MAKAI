"""Find the drop-off stations (bin, laundry basket) in the front camera's image.

Two ways to mark a station, chosen by `perception.stations.kind`:

- `tape` (`TapeStationDetector`): a strip of grey tape on the front of a cardboard box,
  horizontal on one box, vertical on the other. No printer needed. The strip tells which box
  it is by its direction, and how far it is by its size in the image.
- `pattern` (`UPatternDetector`): one station only, marked with a white U in a dark square
  (the pattern lent by another team on 15 Nov, or one made by hand). Seen by the robot's
  camera, where the tape strips are not (docs/DEBUG_ODOMETRY.md, 11.3).
- `aruco` (`StationDetector`): a printed ArUco marker taped vertically on the front of each
  station. `solvePnP` gives its position and its orientation, which tells which way the
  station faces. Print markers with:  uv run python scripts/make_markers.py

Both give `StationSighting`s in the base frame. Only the ArUco marker gives `facing_rad`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import cv2
import numpy as np

from makai.contracts import Category, StationSighting
from makai.perception.geometry import CameraModel

DICTIONARY = cv2.aruco.DICT_4X4_50


class StationDetector:
    def __init__(self, camera: CameraModel, marker_ids: Mapping[int, Category], marker_size_m: float = 0.10):
        self.camera = camera
        self.marker_ids = dict(marker_ids)
        self._detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY))
        half = marker_size_m / 2.0
        # Corner order returned by OpenCV: top-left, top-right, bottom-right, bottom-left.
        self._corners_3d = np.array(
            [[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], dtype=np.float64
        )

    def detect(self, image_rgb: np.ndarray) -> dict[Category, StationSighting]:
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        sightings: dict[Category, StationSighting] = {}
        if ids is None:
            return sightings
        for marker_corners, marker_id in zip(corners, ids.flatten(), strict=True):
            category = self.marker_ids.get(int(marker_id))
            if category is None:
                continue
            ok, rvec, tvec = cv2.solvePnP(
                self._corners_3d,
                marker_corners.reshape(4, 2).astype(np.float64),
                self.camera.matrix,
                None,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if ok:
                centre = self.camera.camera_to_base(tvec)
                # The marker's z axis comes out of its face, towards whoever looks at it.
                normal = cv2.Rodrigues(rvec)[0][:, 2]
                ahead = self.camera.camera_to_base(tvec.reshape(3) + 0.1 * normal) - centre
                facing = math.atan2(float(ahead[1]), float(ahead[0]))
                sightings[category] = StationSighting(category, float(centre[0]), float(centre[1]), facing)
        return sightings


@dataclass(frozen=True)
class Strip:
    """A strip of tape found in an image, in pixels."""

    kind: str  # "horizontal" or "vertical"
    u: float  # centre
    v: float
    length_px: float  # along the strip, as far as the image shows it
    thickness_px: float  # across it
    cut_start: bool  # the strip runs out of the image at its left (or top) end
    cut_end: bool  # ... at its right (or bottom) end
    box: tuple[int, int, int, int]  # x, y, width, height


class TapeStationDetector:
    """Stations marked with a strip of grey tape on a cardboard box.

    What makes a strip, in the image:
    - grey (hardly any colour) and darker than the cardboard and the floor around;
    - long and thin, lying flat or standing upright;
    - cardboard along both of its long sides. A grey wall, a door frame, a can on the floor
      have something else beside them;
    - at the right height. The camera is low: a strip stuck across a box sits at about the
      height of the lens, so it shows near the horizon line of the image wherever the box is,
      and an upright strip crosses that line. Things lying on the floor stay below it;
    - of the right shape. Tape stuck on the floor is seen at a grazing angle: a piece lying
      across looks far thinner than its length allows, and a line running away from the robot
      climbs towards the horizon without ever passing it.

    How far it is: a thing of known size looks smaller the further it is. The length of the
    strip is used while the image shows it whole, the width of the tape once it does not
    (close to the box the strip is wider than the picture).
    """

    def __init__(
        self,
        camera: CameraModel,
        kinds: Mapping[str, Category],  # "horizontal" / "vertical" -> what that box takes
        tape_width_m: float = 0.048,
        lengths_m: Mapping[str, float | None] | None = None,  # length of each strip, when measured
        widths_m: Mapping[str, float | None] | None = None,  # its visible width, if not the tape's (crumpled)
        grey_chroma: float = 12.0,  # colourfulness (Lab) below which a pixel is surely grey tape
        max_chroma: float = 18.0,  # ... below which it may be, next to one that surely is (a crease, a shadow)
        min_flank_chroma: float = 19.0,  # ... from which it is cardboard, or floor
        min_area_px: int = 150,
        horizon_margin_px: float | None = 45.0,  # None: no check of the height (a hand-held photo)
        min_height_m: float = 0.03,  # a strip lower than this above the floor is tape on the floor
    ):
        self.camera, self.kinds = camera, dict(kinds)
        self.tape_width_m, self.lengths_m = tape_width_m, dict(lengths_m or {})
        self.widths_m = dict(widths_m or {})
        self.grey_chroma, self.max_chroma, self.min_flank_chroma = grey_chroma, max_chroma, min_flank_chroma
        self.min_area_px, self.horizon_margin_px = min_area_px, horizon_margin_px
        self.min_height_m = min_height_m

    # ------------------------------------------------------------------ in the image
    def find_strips(self, image_rgb: np.ndarray) -> list[Strip]:
        """The best strip of each direction, if any."""
        # Half the size is enough to see a strip, and four times quicker: this runs at every image.
        shrink = 2 if image_rgb.shape[1] >= 480 else 1
        if shrink > 1:
            image_rgb = cv2.resize(
                image_rgb, None, fx=1 / shrink, fy=1 / shrink, interpolation=cv2.INTER_AREA
            )
        lab = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        light = lab[..., 0]
        chroma = np.hypot(lab[..., 1] - 128.0, lab[..., 2] - 128.0)
        coloured = chroma >= self.min_flank_chroma
        if coloured.mean() < 0.02:
            return []  # nothing that could be cardboard
        # How light the cardboard and the floor are here (one pixel in sixteen is enough to tell).
        reference = float(np.median(light[::4, ::4][coloured[::4, ::4]]))
        # Darker than the cardboard, but not black: a black sock lying on the floor is not tape.
        dark = (light < reference - 12.0) & (light > 0.28 * reference)
        # Surely grey pixels, grown into their not-so-grey neighbours: tape is creased and shiny.
        maybe = ((chroma < self.max_chroma) & dark).astype(np.uint8)
        groups_count, groups = cv2.connectedComponents(maybe, connectivity=8)
        keep = np.zeros(groups_count, dtype=np.uint8)
        keep[groups[(chroma < self.grey_chroma) & dark]] = 1
        keep[0] = 0  # the background
        grey = keep[groups]
        grey = cv2.morphologyEx(grey, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))  # glints on the tape
        height, width = grey.shape
        horizon = self.camera.height / 2.0 - self.camera.focal_px * math.tan(
            math.radians(self.camera.pitch_deg)
        )
        horizon *= height / self.camera.height
        margin = (
            None if self.horizon_margin_px is None else self.horizon_margin_px * height / self.camera.height
        )
        strips = []
        for kind in ("horizontal", "vertical"):
            # Work on a picture where the strip lies flat: an upright one is turned on its side.
            flat, around = (grey, coloured) if kind == "horizontal" else (grey.T, coloured.T)
            # Number of cardboard-coloured pixels above each pixel, to count them in any band at once.
            above = np.zeros((around.shape[0] + 1, around.shape[1]), dtype=np.int32)
            np.cumsum(around, axis=0, out=above[1:])
            # Keep only runs of grey at least this long: a strip, not a gap between two boxes.
            run = max(15, flat.shape[1] // 16)
            runs = cv2.morphologyEx(np.ascontiguousarray(flat), cv2.MORPH_OPEN, np.ones((1, run), np.uint8))
            count, labels, stats, _ = cv2.connectedComponentsWithStats(runs, connectivity=8)
            best: tuple[float, Strip] | None = None
            for label in range(1, count):
                x, y, w, h, area = (int(v) for v in stats[label])
                if area < self.min_area_px / shrink**2:
                    continue
                found = self._measure(labels[y : y + h, x : x + w] == label, above, x, y)
                if found is None:
                    continue
                start, end, thickness, across, low, high = found
                length = end - start
                limit = flat.shape[1]
                whole = start > 1 and end < limit - 1
                # Long and thin. A strip that runs out of the image only shows part of its length.
                slender = (
                    (3.5 if kind == "horizontal" else 2.2)
                    if whole
                    else (1.5 if kind == "horizontal" else 1.2)
                )
                if length / thickness < slender:
                    continue
                known = self.lengths_m.get(kind)
                beside = low <= 1 or high >= flat.shape[0] - 1  # cut along its length by the image's edge
                if whole and known and not beside:
                    # Seen whole, a strip keeps its proportions. Tape on the floor does not.
                    expected = known / (self.widths_m.get(kind) or self.tape_width_m)
                    if not 0.45 * expected <= length / thickness <= 2.3 * expected:
                        continue
                if margin is not None:
                    scale = height / self.camera.height
                    if kind == "horizontal":
                        if across > horizon + margin:
                            continue  # too low in the image: something lying on the floor
                        # How high above the floor a strip at that distance and that row would be.
                        focal = self.camera.focal_px * scale
                        size = known if (whole and known) else (self.widths_m.get(kind) or self.tape_width_m)
                        depth = focal * size / (length if (whole and known) else thickness)
                        if self.camera.height_m - (across - horizon) * depth / focal < self.min_height_m:
                            continue
                    elif start > horizon - 6 * scale or end < horizon + 6 * scale:
                        continue  # an upright strip starts on the floor and passes the height of the lens
                along = (start + end) / 2.0
                box = (
                    (start, low, length, high - low)
                    if kind == "horizontal"
                    else (low, start, high - low, length)
                )
                u, v = (along, across) if kind == "horizontal" else (across, along)
                strip = Strip(  # in pixels of the image as it was given
                    kind,
                    u * shrink,
                    v * shrink,
                    float(length * shrink),
                    thickness * shrink,
                    start <= 1,
                    end >= limit - 1,
                    tuple(int(side * shrink) for side in box),
                )
                if best is None or length * thickness > best[0]:
                    best = (length * thickness, strip)
            if best is not None:
                strips.append(best[1])
        return strips

    def _measure(
        self, mask: np.ndarray, coloured_above: np.ndarray, x0: int, y0: int
    ) -> tuple[int, int, float, float, int, int] | None:
        """A grey shape lying flat, column by column: keep the stretch that has cardboard just
        above and just below it. Returns where it starts and ends (columns of the picture), its
        mean thickness, its mean row, and its lowest and highest rows. None if there is none.
        `coloured_above[r, c]`: how many cardboard-coloured pixels column c has above row r."""
        rows, columns = mask.shape
        filled = mask.sum(axis=0)
        if not filled.any():
            return None
        top = np.argmax(mask, axis=0)
        bottom = rows - np.argmax(mask[::-1], axis=0)  # one past the last grey row of each column
        reach = max(4, int(round(0.8 * float(np.median(filled[filled > 0])))))
        limit = coloured_above.shape[0] - 1
        at = x0 + np.arange(columns)

        def cardboard(first: np.ndarray, last: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            """Per column: is the band of rows [first, last) there at all, and mostly cardboard?"""
            first, last = np.clip(first, 0, limit), np.clip(last, 0, limit)
            size = last - first
            count = coloured_above[last, at] - coloured_above[first, at]
            return size >= 2, count >= 0.5 * size

        over, over_ok = cardboard(y0 + top - reach, y0 + top - 1)
        under, under_ok = cardboard(y0 + bottom + 1, y0 + bottom + reach)
        # Cardboard on both sides; on one side only where the other is out of the picture.
        valid = (filled > 0) & (over | under) & (over_ok | ~over) & (under_ok | ~under)
        # The longest stretch of such columns, small holes forgiven (a crease, a glint on the tape).
        best, start, holes = (0, 0), None, 0
        for c in range(columns + 1):
            if c < columns and valid[c]:
                start, holes = (c if start is None else start), 0
            elif start is not None:
                holes += 1
                if holes > 5 or c == columns:
                    end = c - holes + 1
                    if end - start > best[1] - best[0]:
                        best = (start, end)
                    start, holes = None, 0
        start, end = best
        if end - start < 8:
            return None
        inside = valid[start:end]
        thickness = float(filled[start:end][inside].mean())
        across = float(((top[start:end] + bottom[start:end]) / 2.0)[inside].mean())
        return (
            x0 + start,
            x0 + end,
            thickness,
            y0 + across,
            y0 + int(top[start:end][inside].min()),
            y0 + int(bottom[start:end][inside].max()),
        )

    # ------------------------------------------------------------------ on the floor
    def locate(self, strip: Strip, image_width: int) -> tuple[float, float, float]:
        """Where the strip is: depth along the camera's axis (m), and its centre in the image."""
        scale = image_width / self.camera.width
        focal = self.camera.focal_px * scale
        length = self.lengths_m.get(strip.kind)
        whole = not (strip.cut_start or strip.cut_end)
        if whole and length:
            depth = focal * length / strip.length_px
        else:
            depth = focal * (self.widths_m.get(strip.kind) or self.tape_width_m) / strip.thickness_px
        u = strip.u
        if strip.kind == "horizontal" and length and strip.cut_start != strip.cut_end:
            # One end is out of the image: the middle of the strip is half its length from the other.
            half = focal * length / depth / 2.0
            x, _, w, _ = strip.box
            u = (x + w - half) if strip.cut_start else (x + half)
        return depth, u / scale, strip.v / scale

    def detect(self, image_rgb: np.ndarray) -> dict[Category, StationSighting]:
        sightings: dict[Category, StationSighting] = {}
        for strip in self.find_strips(image_rgb):
            category = self.kinds.get(strip.kind)
            if category is None:
                continue
            depth, u, v = self.locate(strip, image_rgb.shape[1])
            f = self.camera.focal_px
            point = self.camera.camera_to_base(
                np.array(
                    [
                        (u - self.camera.width / 2.0) * depth / f,
                        (v - self.camera.height / 2.0) * depth / f,
                        depth,
                    ]
                )
            )
            sightings[category] = StationSighting(category, float(point[0]), float(point[1]))
        return sightings


class UPatternDetector:
    """One station marked with a white U inside a dark square, stuck on its front face.

    The pattern lent by another team on 15 Nov; one can be made by hand: a white U (paper, or
    the paper left bare) in a square of black or dark grey tape. Its "black" may be as dark as
    the tape around it: what stands out is the U. What makes it, in the image: a bright U shape,
    10 to 220 px wide, dark all around, with a dark notch in its top middle. How far it is: from
    the width of the U, as for a strip of tape. It does not tell which way the station faces.

    On the robot's front camera (15 Nov, at 0.9 and 1.2 m): found in 40 frames out of 40,
    direction steady to 0.01 degree.
    """

    def __init__(
        self,
        camera: CameraModel,
        category: Category,
        u_width_m: float = 0.044,
        min_height_m: float = 0.03,  # height of the U's centre above the floor: stuck at about 10 cm
        max_height_m: float = 0.20,
    ):
        self.camera, self.category, self.u_width_m = camera, category, u_width_m
        self.min_height_m, self.max_height_m = min_height_m, max_height_m

    def find(self, image_rgb: np.ndarray) -> list[tuple[float, float, float, float]]:
        """Candidates in the image: (u, v, width_px, contrast), best first."""
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        light = float(np.median(gray))
        bright = (gray > max(165.0, 1.1 * light)).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
        rows, columns = gray.shape
        found = []
        for label in range(1, count):
            x, y, w, h, area = (int(v) for v in stats[label])
            if not (10 <= w <= 220 and 10 <= h <= 220 and 0.7 <= w / h <= 1.45):
                continue
            if not 0.3 <= area / (w * h) <= 0.7:  # a U, not a filled patch nor a thin line
                continue
            m = max(2, w // 6)  # a ring around it: dark (the square, the tape)
            if x - m < 0 or y - m < 0 or x + w + m > columns or y + h + m > rows:
                continue
            ring = np.concatenate(
                [
                    gray[y - m : y, x : x + w].ravel(),
                    gray[y : y + h, x - m : x].ravel(),
                    gray[y : y + h, x + w : x + w + m].ravel(),
                ]
            )
            notch = gray[y : y + int(0.55 * h), x + int(0.35 * w) : x + int(0.65 * w)]
            if notch.size == 0 or np.median(ring) > 0.7 * light or notch.mean() > 0.7 * light:
                continue
            found.append((x + w / 2.0, y + h / 2.0, float(w), light - float(np.median(ring))))
        return sorted(found, key=lambda c: -c[3])

    def locate(self, u: float, v: float, width: float, image_width: int) -> np.ndarray:
        """Where a U of that width at that pixel is, in the base frame (x, y, height above floor)."""
        scale = image_width / self.camera.width
        u, v, width = u / scale, v / scale, width / scale
        f = self.camera.focal_px
        depth = f * self.u_width_m / width
        return self.camera.camera_to_base(
            np.array(
                [(u - self.camera.width / 2.0) * depth / f, (v - self.camera.height / 2.0) * depth / f, depth]
            )
        )

    def detect(self, image_rgb: np.ndarray) -> dict[Category, StationSighting]:
        # The first U at the height it is stuck at. Its size tells how far it is, so where it sits
        # in the image tells how high: a window pane framed by dark bars, seen behind the zone,
        # comes out a metre up (15 Nov: the robot steered on such a U, then lost it).
        for u, v, width, _ in self.find(image_rgb):
            point = self.locate(u, v, width, image_rgb.shape[1])
            if self.min_height_m <= point[2] <= self.max_height_m:
                return {self.category: StationSighting(self.category, float(point[0]), float(point[1]))}
        return {}


def build_station_detector(perception_cfg: Mapping, camera: CameraModel):
    """The station detector of `perception.stations` in the config: tape strips, a U pattern,
    or ArUco markers."""
    cfg = perception_cfg["stations"]
    if cfg.get("kind", "aruco") == "pattern":
        pattern = cfg.get("pattern", {})
        return UPatternDetector(
            camera, Category(pattern.get("category", "trash")), float(pattern.get("u_width_m", 0.044))
        )
    if cfg.get("kind", "aruco") == "tape":
        tape = cfg.get("tape", {})
        kinds = {kind: Category(tape[kind]) for kind in ("horizontal", "vertical") if tape.get(kind)}
        return TapeStationDetector(
            camera,
            kinds,
            tape_width_m=float(tape.get("width_m", 0.048)),
            lengths_m={
                "horizontal": tape.get("horizontal_length_m"),
                "vertical": tape.get("vertical_length_m"),
            },
            widths_m={
                "horizontal": tape.get("horizontal_width_m"),
                "vertical": tape.get("vertical_width_m"),
            },
        )
    marker_ids = {int(marker): Category(category) for marker, category in cfg["marker_ids"].items()}
    return StationDetector(camera, marker_ids, cfg["marker_size_m"])
