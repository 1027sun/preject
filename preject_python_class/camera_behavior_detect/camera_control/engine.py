"""Pose-to-ControlState boundary, with no camera or inference dependency."""

from dataclasses import replace
from typing import Sequence

from .calibration import Calibrator
from .config import Config
from .control_state import ControlState
from .detectors.arms_open_detector import ArmsOpenDetector
from .detectors.crouch_detector import CrouchDetector
from .detectors.hands_up_detector import HandsUpDetector
from .detectors.jump_detector import JumpDetector
from .detectors.lane_detector import LaneDetector
from .features import HIPS, KNEES, TORSO, extract_features
from .smoothing import EMA


class ActionEngine:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.calibration = Calibrator(self.config)
        self._last_update_ms: int | None = None
        self._low_since_ms: int | None = None
        self._continuous_tracking = False
        self._state = ControlState()
        self._center_filter = EMA(self.config.pose_ema_alpha, self.config.nominal_frame_ms)
        self._hip_filter = EMA(self.config.pose_ema_alpha, self.config.nominal_frame_ms)
        self._gap_filter = EMA(self.config.pose_ema_alpha, self.config.nominal_frame_ms)
        self._lane = LaneDetector(self.config)
        self._jump = JumpDetector(self.config)
        self._crouch = CrouchDetector(self.config)
        self._arms = ArmsOpenDetector(self.config)
        self._hands = HandsUpDetector(self.config)
        self._metrics = {"normalized_dx": 0.0, "body_center_x": 0.5,
                         "hip_center_y": 0.0}

    @property
    def calibrated(self) -> bool:
        return self.calibration.profile is not None

    @property
    def diagnostics(self) -> dict:
        return dict(self._metrics, calibrated=self.calibrated,
                    calibration_progress=self.calibration.progress,
                    calibration_hint=self.calibration.hint,
                    jump_height=self._jump.height, vertical_speed=self._jump.speed,
                    candidate_lane=self._lane.candidate_lane,
                    last_jump_ms=self._jump.last_jump_ms)

    def request_calibration(self) -> None:
        self.calibration.reset()
        self._lane = LaneDetector(self.config)
        self._jump = JumpDetector(self.config)
        self._clear_actions()
        self._interrupt_tracking()
        self._low_since_ms = None
        self._state = ControlState()

    def _clear_actions(self) -> None:
        for detector in (self._crouch, self._arms, self._hands):
            detector.reset()

    def _interrupt_tracking(self) -> None:
        self._continuous_tracking = False
        self._center_filter.reset()
        self._hip_filter.reset()
        self._gap_filter.reset()
        self._jump.interrupt()
        self._lane.hold()

    def _unreliable(self, timestamp_ms: int, confidence: float) -> ControlState:
        self._interrupt_tracking()
        if not self.calibrated:
            self.calibration.reject("请全身站入框内，等待稳定追踪")
        if self._low_since_ms is None:
            self._low_since_ms = timestamp_ms
        for detector in (self._crouch, self._arms, self._hands):
            detector.cancel_pending()
        if timestamp_ms - self._low_since_ms >= self.config.tracking_lost_ms:
            self._clear_actions()
        self._state = ControlState(self._lane.lane, False, self._crouch.value,
                                   self._arms.value, self._hands.value,
                                   confidence if self.calibrated else 0.0)
        return self._state

    def update(self, landmarks: Sequence[object] | None, timestamp_ms: int,
               aspect_ratio: float = 16 / 9) -> ControlState:
        # Ignore late callbacks; a duplicate must never repeat a jump pulse.
        if self._last_update_ms is not None and timestamp_ms <= self._last_update_ms:
            return replace(self._state, jump_triggered=False)
        if (self._last_update_ms is not None
                and timestamp_ms - self._last_update_ms >= self.config.tracking_lost_ms):
            self.tick(timestamp_ms)
        self._last_update_ms = timestamp_ms
        f = extract_features(landmarks, aspect_ratio)
        if f is None or f.confidence < self.config.min_valid_confidence:
            return self._unreliable(timestamp_ms, 0.0 if f is None else f.confidence)
        self._low_since_ms = None
        if not self.calibrated:
            profile = self.calibration.consume(f, timestamp_ms)
            if profile is None:
                self._state = ControlState()
                return self._state
            self._interrupt_tracking()
        calibration = self.calibration.profile
        good = f.confidence >= self.config.good_tracking_confidence
        torso_valid = f.valid(TORSO, self.config.keypoint_confidence)
        if good and torso_valid:
            if not self._continuous_tracking:
                self._center_filter.reset()
                self._hip_filter.reset()
                self._gap_filter.reset()
                self._jump.interrupt()
            f = replace(f,
                        body_center_x=self._center_filter.update(f.body_center_x, timestamp_ms),
                        hip_center_y=self._hip_filter.update(f.hip_center_y, timestamp_ms),
                        # Same EMA weight keeps the hip/knee distance temporally
                        # consistent with hip position during fast transitions.
                        hip_knee_gap=self._gap_filter.update(f.hip_knee_gap, timestamp_ms))
            self._continuous_tracking = True
        else:
            self._interrupt_tracking()
        dx = (f.body_center_x - calibration.body_center_x) / calibration.shoulder_width
        self._metrics.update(normalized_dx=dx, body_center_x=f.body_center_x,
                             hip_center_y=f.hip_center_y)
        lane = self._lane.update(dx, timestamp_ms) if good and torso_valid else self._lane.hold()
        crouch = self._crouch.detect(f, calibration, timestamp_ms, good)
        arms = self._arms.detect(f, calibration, timestamp_ms, good)
        hands = self._hands.detect(f, calibration, timestamp_ms, good)
        jump_valid = good and torso_valid and f.valid(HIPS + KNEES, self.config.keypoint_confidence)
        if jump_valid:
            jump = self._jump.update(f, calibration, timestamp_ms)
        else:
            self._jump.interrupt()
            jump = False
        self._state = ControlState(lane, jump, crouch, arms, hands, f.confidence)
        return self._state

    def tick(self, timestamp_ms: int) -> ControlState:
        """Expire held actions even when no inference callback arrives."""
        if self._last_update_ms is None:
            return ControlState()
        age = timestamp_ms - self._last_update_ms
        if not self.calibrated and age > self.config.calibration_max_gap_ms:
            self.calibration.reject("追踪中断，请重新保持站立")
        if age >= self.config.tracking_lost_ms:
            self._clear_actions()
            if self._low_since_ms is None:
                self._low_since_ms = self._last_update_ms
            return self._unreliable(timestamp_ms, 0.0)
        # Pulses belong to pose updates, never to timer updates.
        return replace(self._state, jump_triggered=False)
