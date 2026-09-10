from ..calibration import CalibrationProfile
from ..config import Config
from ..features import Features


class JumpDetector:
    def __init__(self, config: Config):
        self.config = config
        self.last_jump_ms: int | None = None
        self.height = 0.0
        self.speed = 0.0
        self.interrupt()

    def interrupt(self) -> None:
        """Require a fresh standing interval after any unreliable tracking."""
        self.armed = False
        self.grounded_since_ms: int | None = None
        self.previous_hip_y: float | None = None
        self.previous_ms: int | None = None
        self.speed = 0.0

    def update(self, f: Features, calibration: CalibrationProfile,
               timestamp_ms: int) -> bool:
        c = self.config
        self.height = (calibration.hip_center_y - f.hip_center_y) / calibration.body_height
        self.speed = 0.0
        if self.previous_ms is not None and timestamp_ms > self.previous_ms:
            dt = (timestamp_ms - self.previous_ms) / 1000
            self.speed = (self.previous_hip_y - f.hip_center_y) / dt / calibration.body_height
        self.previous_hip_y, self.previous_ms = f.hip_center_y, timestamp_ms
        # Keep a grounded player's eligibility through the preparatory knee dip.
        # Ordinary squat-to-stand ends at height=0; a jump must rise ABOVE that
        # original standing baseline with enough upward speed.
        grounded = abs(self.height) <= c.jump_landing_height
        if grounded:
            if self.grounded_since_ms is None:
                self.grounded_since_ms = timestamp_ms
            if timestamp_ms - self.grounded_since_ms >= c.jump_rearm_ms:
                self.armed = True
        else:
            self.grounded_since_ms = None
        cooled_down = self.last_jump_ms is None or timestamp_ms - self.last_jump_ms >= c.jump_cooldown_ms
        if (self.armed and cooled_down and self.height >= c.jump_height_threshold
                and self.speed >= c.jump_speed_threshold):
            self.armed = False
            self.last_jump_ms = timestamp_ms
            return True
        return False
