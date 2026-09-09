"""Small, validated feature set derived from MediaPipe-compatible landmarks."""

from dataclasses import dataclass
import math
from typing import Sequence

NOSE = 0
SHOULDERS = (11, 12)
WRISTS = (15, 16)
HIPS = (23, 24)
KNEES = (25, 26)
ANKLES = (27, 28)
TORSO = SHOULDERS + HIPS
CORE = TORSO + KNEES + WRISTS


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    visibility: float
    presence: float

    def valid(self, minimum: float) -> bool:
        return (0 <= self.x <= 1 and 0 <= self.y <= 1
                and self.visibility >= minimum and self.presence >= minimum)


@dataclass(frozen=True)
class Features:
    points: dict[int, Point]
    confidence: float
    body_center_x: float
    hip_center_y: float
    shoulder_width: float
    body_height: float
    hip_knee_gap: float
    aspect_ratio: float

    def valid(self, indices: tuple[int, ...], minimum: float) -> bool:
        return all(self.points[i].valid(minimum) for i in indices)

    def knee_angle(self, side: int) -> float:
        hip, knee, ankle = (self.points[pair[side]] for pair in (HIPS, KNEES, ANKLES))
        a = ((hip.x - knee.x) * self.aspect_ratio, hip.y - knee.y)
        b = ((ankle.x - knee.x) * self.aspect_ratio, ankle.y - knee.y)
        length = math.hypot(*a) * math.hypot(*b)
        if length <= 1e-8:
            return 0.0
        cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / length))
        return math.degrees(math.acos(cosine))


def extract_features(landmarks: Sequence[object] | None,
                     aspect_ratio: float = 16 / 9) -> Features | None:
    if landmarks is None or len(landmarks) <= max(ANKLES):
        return None
    if not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
        raise ValueError("aspect_ratio must be positive and finite")
    points = {}
    for index in (NOSE,) + CORE + ANKLES:
        raw = landmarks[index]
        try:
            x, y = float(raw.x), float(raw.y)
            visibility = float(getattr(raw, "visibility", 0.0) or 0.0)
            # Some compatible landmark producers omit presence entirely.
            presence_raw = getattr(raw, "presence", None)
            presence = visibility if presence_raw is None else float(presence_raw)
        except (AttributeError, TypeError, ValueError):
            return None
        if not all(math.isfinite(v) for v in (x, y, visibility, presence)):
            return None
        points[index] = Point(x, y, max(0.0, min(1.0, visibility)),
                              max(0.0, min(1.0, presence)))
    mean = lambda indices, axis: sum(getattr(points[i], axis) for i in indices) / len(indices)
    hip_y = mean(HIPS, "y")
    return Features(
        points=points,
        confidence=sum(points[i].visibility for i in CORE) / len(CORE),
        body_center_x=mean(TORSO, "x"),
        hip_center_y=hip_y,
        shoulder_width=abs(points[11].x - points[12].x),
        body_height=mean(ANKLES, "y") - points[NOSE].y,
        hip_knee_gap=mean(KNEES, "y") - hip_y,
        aspect_ratio=aspect_ratio,
    )
