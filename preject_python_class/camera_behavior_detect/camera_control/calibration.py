"""Collect a continuous stable, fully visible natural standing baseline."""

from dataclasses import dataclass
from statistics import median

from .config import Config
from .features import ANKLES, CORE, HIPS, NOSE, SHOULDERS, WRISTS, Features


@dataclass(frozen=True)
class CalibrationProfile:
    body_center_x: float
    hip_center_y: float
    shoulder_width: float
    body_height: float
    hip_knee_gap: float


class Calibrator:
    def __init__(self, config: Config):
        self.config = config
        self.profile: CalibrationProfile | None = None
        self.samples: list[tuple[int, Features]] = []
        self.progress = 0.0
        self.hint = "请全身站入框内，双臂自然下垂"

    def reset(self) -> None:
        self.profile = None
        self.reject("请全身站入框内，双臂自然下垂")

    def reject(self, hint: str) -> None:
        self.samples.clear()
        self.progress = 0.0
        self.hint = hint

    def consume(self, f: Features, timestamp_ms: int) -> CalibrationProfile | None:
        c = self.config
        if self.profile is not None:
            return self.profile
        required = (NOSE,) + CORE + ANKLES
        if f.confidence < c.calibration_confidence or not f.valid(required, c.calibration_confidence):
            self.reject("请确保头、肩、双手和双脚都清晰可见")
            return None
        if not all(c.calibration_x_min <= f.points[i].x <= c.calibration_x_max
                   and c.calibration_y_min <= f.points[i].y <= c.calibration_y_max for i in required):
            self.reject("请退后一些，让全身进入中央框内")
            return None
        if (f.body_height < c.calibration_min_body_height
                or f.shoulder_width < c.calibration_min_shoulder_width or f.hip_knee_gap <= 0):
            self.reject("请面向摄像头，调整站立距离")
            return None
        shoulder_x = sum(f.points[i].x for i in SHOULDERS) / 2
        hip_x = sum(f.points[i].x for i in HIPS) / 2
        shoulder_y = sum(f.points[i].y for i in SHOULDERS) / 2
        if (min(f.knee_angle(0), f.knee_angle(1)) < c.calibration_min_knee_angle
                or abs(shoulder_x - hip_x) / f.shoulder_width > c.calibration_max_torso_lean
                or shoulder_y >= f.hip_center_y):
            self.reject("请站直身体、伸直双腿，保持自然站立")
            return None
        if any(f.points[w].y < f.points[s].y + c.calibration_wrists_below_shoulder
               * f.shoulder_width * f.aspect_ratio for s, w in zip(SHOULDERS, WRISTS)):
            self.reject("请双臂自然下垂后保持不动")
            return None
        if self.samples and timestamp_ms - self.samples[-1][0] > c.calibration_max_gap_ms:
            self.reject("追踪中断，请重新保持站立")
        if self.samples:
            baseline = self.samples[0][1]
            moving = (
                abs(f.body_center_x - baseline.body_center_x) / baseline.shoulder_width > c.calibration_max_center_motion
                or abs(f.hip_center_y - baseline.hip_center_y) / baseline.body_height > c.calibration_max_hip_motion
                or abs(f.shoulder_width / baseline.shoulder_width - 1) > c.calibration_max_width_change
            )
            if moving:
                self.reject("身体移动了，请重新保持站立")
        self.samples.append((timestamp_ms, f))
        self.progress = min(1.0, (timestamp_ms - self.samples[0][0]) / c.calibration_duration_ms)
        self.hint = "保持自然站立，正在校准…"
        if self.progress >= 1:
            self.profile = CalibrationProfile(**{
                key: median(getattr(sample, key) for _, sample in self.samples)
                for key in CalibrationProfile.__dataclass_fields__
            })
            self.samples.clear()
            self.hint = "校准完成，请依次向左、回中、向右验证"
        return self.profile
