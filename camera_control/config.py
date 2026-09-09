"""Detection thresholds. Distances are normalized by the calibrated body size."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    min_valid_confidence: float = 0.50
    good_tracking_confidence: float = 0.70
    keypoint_confidence: float = 0.55
    tracking_lost_ms: int = 300
    pose_ema_alpha: float = 0.35
    nominal_frame_ms: float = 1000 / 30

    calibration_confidence: float = 0.75
    calibration_duration_ms: int = 1800
    calibration_max_gap_ms: int = 250
    calibration_x_min: float = 0.15
    calibration_x_max: float = 0.85
    calibration_y_min: float = 0.05
    calibration_y_max: float = 0.95
    calibration_min_body_height: float = 0.35
    calibration_min_shoulder_width: float = 0.07
    calibration_min_knee_angle: float = 155.0
    calibration_max_torso_lean: float = 0.45
    calibration_max_center_motion: float = 0.18
    calibration_max_hip_motion: float = 0.035
    calibration_max_width_change: float = 0.15
    calibration_wrists_below_shoulder: float = 0.05

    lane_enter_threshold: float = 0.55
    lane_center_threshold: float = 0.30
    lane_confirm_ms: int = 150

    jump_height_threshold: float = 0.065
    jump_speed_threshold: float = 0.32
    jump_cooldown_ms: int = 500
    jump_landing_height: float = 0.025
    jump_rearm_ms: int = 140

    crouch_drop_threshold: float = 0.075
    crouch_exit_threshold: float = 0.045
    crouch_knee_bend_threshold: float = 0.20
    crouch_knee_exit_threshold: float = 0.12
    crouch_confirm_ms: int = 120
    action_exit_ms: int = 100

    arms_open_margin: float = 0.45
    arms_open_exit_margin: float = 0.30
    arms_open_vertical_tolerance: float = 0.30
    arms_open_exit_vertical_tolerance: float = 0.42
    arms_open_confirm_ms: int = 120
    hands_up_margin: float = 0.40
    hands_up_exit_margin: float = 0.25
    hands_up_confirm_ms: int = 120
