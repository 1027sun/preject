from ..calibration import CalibrationProfile
from ..config import Config
from ..features import SHOULDERS, WRISTS, Features
from ..smoothing import ConfirmedBoolean


class ArmsOpenDetector(ConfirmedBoolean):
    def __init__(self, config: Config):
        super().__init__(config.arms_open_confirm_ms, config.action_exit_ms)
        self.config = config

    def detect(self, f: Features, calibration: CalibrationProfile,
               timestamp_ms: int, allow_enter: bool) -> bool:
        c = self.config
        if not f.valid(SHOULDERS + WRISTS, c.keypoint_confidence):
            return self.missing(timestamp_ms, c.tracking_lost_ms)
        margin = c.arms_open_exit_margin if self.value else c.arms_open_margin
        tolerance = c.arms_open_exit_vertical_tolerance if self.value else c.arms_open_vertical_tolerance
        shoulder_center = sum(f.points[i].x for i in SHOULDERS) / 2
        extended = []
        for shoulder_index, wrist_index in zip(SHOULDERS, WRISTS):
            shoulder, wrist = f.points[shoulder_index], f.points[wrist_index]
            # Anatomical LEFT may appear on either image side after mirroring.
            direction = -1 if shoulder.x < shoulder_center else 1
            extended.append(
                direction * (wrist.x - shoulder.x) > margin * calibration.shoulder_width
                and abs(wrist.y - shoulder.y) < tolerance * calibration.shoulder_width * f.aspect_ratio
            )
        return self.update(all(extended), timestamp_ms, allow_enter)
