from ..calibration import CalibrationProfile
from ..config import Config
from ..features import HIPS, KNEES, Features
from ..smoothing import ConfirmedBoolean


class CrouchDetector(ConfirmedBoolean):
    def __init__(self, config: Config):
        super().__init__(config.crouch_confirm_ms, config.action_exit_ms)
        self.config = config

    def detect(self, f: Features, calibration: CalibrationProfile,
               timestamp_ms: int, allow_enter: bool) -> bool:
        c = self.config
        if not f.valid(HIPS + KNEES, c.keypoint_confidence):
            return self.missing(timestamp_ms, c.tracking_lost_ms)
        drop = (f.hip_center_y - calibration.hip_center_y) / calibration.body_height
        shrink = 1 - f.hip_knee_gap / calibration.hip_knee_gap
        drop_threshold = c.crouch_exit_threshold if self.value else c.crouch_drop_threshold
        bend_threshold = c.crouch_knee_exit_threshold if self.value else c.crouch_knee_bend_threshold
        return self.update(drop > drop_threshold and shrink > bend_threshold,
                           timestamp_ms, allow_enter)
