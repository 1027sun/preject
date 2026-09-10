from ..config import Config


class LaneDetector:
    def __init__(self, config: Config):
        self.config = config
        self.lane = 0
        self.candidate_lane = 0
        self.since_ms: int | None = None

    def hold(self) -> int:
        self.candidate_lane = self.lane
        self.since_ms = None
        return self.lane

    def update(self, normalized_dx: float, timestamp_ms: int) -> int:
        c = self.config
        candidate = self.lane
        if normalized_dx < -c.lane_enter_threshold:
            candidate = -1
        elif normalized_dx > c.lane_enter_threshold:
            candidate = 1
        elif abs(normalized_dx) <= c.lane_center_threshold:
            candidate = 0
        if candidate == self.lane:
            self.hold()
        elif candidate != self.candidate_lane:
            self.candidate_lane = candidate
            self.since_ms = timestamp_ms
        elif self.since_ms is not None and timestamp_ms - self.since_ms >= c.lane_confirm_ms:
            self.lane = candidate
            self.hold()
        return self.lane
