"""Generate the printable markers into assets/markers/.

- ground_sheet.png: A4 sheet for `makai-calibrate-ground`. Print at 100 % (no "fit to page")
  and check with a ruler that a marker side is 60 mm.
- station_<id>_<category>.png: one per drop-off station, to tape on its front face.
"""

from pathlib import Path

import cv2
import numpy as np

from makai.config import REPO_ROOT, load_config
from makai.perception.calibration import render_sheet
from makai.perception.stations import DICTIONARY

out = Path(REPO_ROOT) / "assets" / "markers"
out.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out / "ground_sheet.png"), render_sheet())

stations = load_config()["perception"]["stations"]
dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
dpi = 300
side = int(round(stations["marker_size_m"] / 0.0254 * dpi))
for marker_id, category in stations["marker_ids"].items():
    margin = side // 5  # the white border is required for detection
    page = np.full((side + 2 * margin, side + 2 * margin), 255, dtype=np.uint8)
    page[margin:-margin, margin:-margin] = cv2.aruco.generateImageMarker(dictionary, int(marker_id), side)
    cv2.imwrite(str(out / f"station_{marker_id}_{category}.png"), page)
print(
    f"Markers written to {out} (station marker side: {stations['marker_size_m'] * 1000:.0f} mm at {dpi} dpi)"
)
