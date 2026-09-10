from ..calibration import CalibrationProfile
from ..config import Config
from ..features import SHOULDERS, WRISTS, Features
from ..smoothing import ConfirmedBoolean


class HandsUpDetector(ConfirmedBoolean):
    def __init__(self, config: Config):
        super().__init__(config.hands_up_confirm_ms, config.action_exit_ms)
        self.config = config

    def detect(self, f: Features, calibration: CalibrationProfile,
               timestamp_ms: int, allow_enter: bool) -> bool:
        c = self.config
        if not f.valid(SHOULDERS + WRISTS, c.keypoint_confidence):
            return self.missing(timestamp_ms, c.tracking_lost_ms)
        margin = c.hands_up_exit_margin if self.value else c.hands_up_margin
        up = all(f.points[w].y < f.points[s].y - margin * calibration.shoulder_width * f.aspect_ratio
                 for s, w in zip(SHOULDERS, WRISTS))
        return self.update(up, timestamp_ms, allow_enter)
