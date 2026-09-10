"""Synthetic geometry tests of the game-facing behavior; no camera required."""

from copy import deepcopy
import math
from types import SimpleNamespace
import unittest

from camera_control.config import Config
from camera_control.engine import ActionEngine
from camera_control.features import CORE, extract_features


def standing(confidence=0.96):
    points = [SimpleNamespace(x=0.5, y=0.5, z=0.0, visibility=confidence,
                              presence=confidence) for _ in range(33)]
    positions = {
        0: (0.50, 0.12), 11: (0.42, 0.30), 12: (0.58, 0.30),
        15: (0.37, 0.55), 16: (0.63, 0.55),
        23: (0.455, 0.54), 24: (0.545, 0.54),
        25: (0.455, 0.72), 26: (0.545, 0.72),
        27: (0.455, 0.90), 28: (0.545, 0.90),
    }
    for index, (x, y) in positions.items():
        points[index].x, points[index].y = x, y
    return points


def translate(points, x=0.0, y=0.0):
    result = deepcopy(points)
    for point in result:
        point.x += x
        point.y += y
    return result


def arms_open(confidence=0.96):
    points = standing(confidence)
    points[15].x, points[15].y = 0.20, 0.30
    points[16].x, points[16].y = 0.80, 0.30
    return points


def hands_up(confidence=0.96):
    points = standing(confidence)
    points[15].y = points[16].y = 0.13
    return points


def crouching(confidence=0.96):
    points = standing(confidence)
    for index in (0, 11, 12, 15, 16):
        points[index].y += 0.10
    for index in (23, 24):
        points[index].y += 0.10
    for index in (25, 26):
        points[index].y += 0.02
    points[25].x, points[26].x = 0.36, 0.64
    return points


class Rig:
    def __init__(self, config=None):
        self.engine = ActionEngine(config)
        self.time = -40
        self.events = []

    def frame(self, points, elapsed=40, aspect_ratio=16 / 9):
        self.time += elapsed
        state = self.engine.update(points, self.time, aspect_ratio)
        if state.jump_triggered:
            self.events.append(self.time)
        return state

    def hold(self, points, duration=400, step=40, aspect_ratio=16 / 9):
        state = None
        for _ in range(max(1, math.ceil(duration / step))):
            state = self.frame(points, step, aspect_ratio)
        return state

    def calibrate(self):
        self.hold(standing(), 2200)
        assert self.engine.calibrated
        return self


class CalibrationTests(unittest.TestCase):
    def test_requires_full_stable_1800ms_and_returns_safe_state_until_ready(self):
        rig = Rig()
        state = rig.hold(standing(), 1800)
        self.assertFalse(rig.engine.calibrated)
        self.assertEqual(state.tracking_confidence, 0)
        self.assertLess(rig.engine.diagnostics["calibration_progress"], 1)
        state = rig.frame(standing())
        self.assertTrue(rig.engine.calibrated)
        self.assertAlmostEqual(state.tracking_confidence, 0.96)
        self.assertEqual(rig.engine.diagnostics["calibration_progress"], 1)

    def test_needs_visible_head_ankles_and_straight_legs(self):
        for alteration in ("head", "ankle", "crouch", "lean", "raised_hands"):
            with self.subTest(alteration=alteration):
                points = standing()
                if alteration == "head":
                    points[0].y = -0.1
                elif alteration == "ankle":
                    points[27].visibility = 0.2
                elif alteration == "crouch":
                    points = crouching()
                elif alteration == "lean":
                    points[11].x += 0.10
                    points[12].x += 0.10
                else:
                    points = hands_up()
                rig = Rig()
                state = rig.hold(points, 2400)
                self.assertFalse(rig.engine.calibrated)
                self.assertEqual(state.tracking_confidence, 0)

    def test_center_box_and_movement_restart_collection(self):
        rig = Rig()
        rig.hold(standing(), 1000)
        rig.frame(translate(standing(), x=0.06))
        self.assertEqual(rig.engine.diagnostics["calibration_progress"], 0)
        rig.hold(translate(standing(), x=0.24), 2000)
        self.assertFalse(rig.engine.calibrated)

    def test_brief_occlusion_or_frame_gap_restart_collection(self):
        for gap in (False, True):
            with self.subTest(gap=gap):
                rig = Rig()
                rig.hold(standing(), 1400)
                if gap:
                    rig.frame(standing(), 280)
                else:
                    rig.frame(None)
                    rig.frame(standing())
                self.assertEqual(rig.engine.diagnostics["calibration_progress"], 0)
                rig.hold(standing(), 800)
                self.assertFalse(rig.engine.calibrated)

    def test_recalibration_clears_previous_controls(self):
        rig = Rig().calibrate()
        rig.hold(translate(arms_open(), x=-0.12))
        rig.engine.request_calibration()
        state = rig.frame(standing())
        self.assertFalse(rig.engine.calibrated)
        self.assertEqual(state.lane, 0)
        self.assertFalse(state.arms_open)
        self.assertEqual(state.tracking_confidence, 0)


class LaneTests(unittest.TestCase):
    def test_confirm_duration_hysteresis_and_return_to_center(self):
        rig = Rig(Config(pose_ema_alpha=1.0)).calibrate()
        left = translate(standing(), x=-0.10)
        self.assertEqual(rig.frame(left).lane, 0)
        self.assertEqual(rig.frame(left, 149).lane, 0)
        self.assertEqual(rig.frame(left, 1).lane, -1)
        self.assertEqual(rig.hold(translate(standing(), x=-0.07)).lane, -1)
        self.assertEqual(rig.hold(standing()).lane, 0)
        self.assertEqual(rig.hold(translate(standing(), x=0.12)).lane, 1)

    def test_small_sway_and_brief_boundary_excursion_do_not_change_lane(self):
        rig = Rig().calibrate()
        for index in range(60):
            state = rig.frame(translate(standing(), x=0.025 * math.sin(index),
                                        y=0.008 * math.cos(index)))
            self.assertEqual(state.lane, 0)
            self.assertFalse(state.jump_triggered)
            self.assertFalse(state.crouch)
        rig.hold(translate(standing(), x=0.13), 80)
        self.assertEqual(rig.hold(standing()).lane, 0)

    def test_arm_movement_does_not_change_torso_lane(self):
        rig = Rig().calibrate()
        self.assertEqual(rig.hold(arms_open()).lane, 0)
        self.assertEqual(rig.hold(hands_up()).lane, 0)


class ActionTests(unittest.TestCase):
    def test_crouch_holds_then_exits_without_jump_when_standing(self):
        rig = Rig().calibrate()
        self.assertTrue(rig.hold(crouching(), 600).crouch)
        self.assertTrue(rig.hold(crouching(), 500).crouch)
        # A normal fast stand reaches the original baseline, with minor sway.
        rig.hold(translate(standing(), y=-0.010), 200)
        state = rig.hold(standing(), 600)
        self.assertFalse(state.crouch)
        self.assertEqual(rig.events, [])

    def test_preparatory_knee_dip_can_rise_into_one_jump(self):
        rig = Rig().calibrate()
        rig.hold(crouching(), 240)
        rig.hold(translate(standing(), y=-0.09), 600)
        self.assertEqual(len(rig.events), 1)
        rig.hold(standing(), 600)
        self.assertFalse(rig.frame(standing()).jump_triggered)
        # A later jump after landing is eligible again, including another dip.
        rig.hold(crouching(), 240)
        rig.hold(translate(standing(), y=-0.09), 600)
        self.assertEqual(len(rig.events), 2)

    def test_bowing_with_straight_legs_does_not_crouch(self):
        rig = Rig().calibrate()
        points = standing()
        for index in (0, 11, 12):
            points[index].y += 0.12
        self.assertFalse(rig.hold(points).crouch)

    def test_single_jump_pulse_landing_rearm_and_cooldown(self):
        rig = Rig().calibrate()
        rig.hold(translate(standing(), y=-0.085), 600)
        self.assertEqual(len(rig.events), 1)
        rig.hold(translate(standing(), y=-0.10), 600)
        self.assertEqual(len(rig.events), 1)
        rig.hold(standing(), 500)
        rig.hold(translate(standing(), y=-0.085), 500)
        self.assertEqual(len(rig.events), 2)
        self.assertGreaterEqual(rig.events[1] - rig.events[0], 500)

    def test_slow_rising_does_not_trigger_jump(self):
        rig = Rig().calibrate()
        for index in range(50):
            rig.frame(translate(standing(), y=-index * 0.002), 80)
        self.assertEqual(rig.events, [])

    def test_jump_requires_reliable_individual_knees(self):
        rig = Rig().calibrate()
        points = translate(standing(), y=-0.09)
        points[25].visibility = 0.1
        state = rig.hold(points)
        self.assertGreater(state.tracking_confidence, 0.7)
        self.assertEqual(rig.events, [])

    def test_arms_open_and_two_hands_up_are_distinct(self):
        rig = Rig().calibrate()
        state = rig.hold(arms_open())
        self.assertTrue(state.arms_open)
        self.assertFalse(state.hands_up)
        state = rig.hold(hands_up())
        self.assertTrue(state.hands_up)
        self.assertFalse(state.arms_open)
        points = hands_up()
        points[16].y = 0.55
        state = rig.hold(points)
        self.assertFalse(state.hands_up)

    def test_anatomical_left_right_can_appear_on_either_screen_side(self):
        rig = Rig().calibrate()
        points = arms_open()
        for point in points:
            point.x = 1 - point.x
        self.assertTrue(rig.hold(points).arms_open)

    def test_vertical_arm_threshold_uses_pixel_aspect_ratio(self):
        rig = Rig().calibrate()
        points = arms_open()
        points[15].y += 0.065
        points[16].y += 0.065
        # 0.065 * H is < 0.30 * (0.16 * W) only in the wider frame.
        self.assertTrue(rig.hold(points, aspect_ratio=16 / 9).arms_open)
        rig.hold(standing())
        self.assertFalse(rig.hold(points, aspect_ratio=1.0).arms_open)

    def test_brief_arms_or_hands_gesture_does_not_enter(self):
        rig = Rig().calibrate()
        self.assertFalse(rig.hold(arms_open(), 80).arms_open)
        rig.hold(standing())
        self.assertFalse(rig.hold(hands_up(), 80).hands_up)


class TrackingTests(unittest.TestCase):
    def test_confidence_is_mean_of_eight_core_visibility_values(self):
        points = standing()
        for index, value in zip(CORE, (0.2, 0.4, 0.6, 0.8, 1.0, 0.9, 0.8, 0.7)):
            points[index].visibility = value
        self.assertAlmostEqual(extract_features(points).confidence, 0.675)

    def test_medium_confidence_disallows_new_actions_and_lane_changes(self):
        rig = Rig().calibrate()
        state = rig.hold(translate(hands_up(0.60), x=0.12, y=-0.06), 600)
        self.assertEqual(state.lane, 0)
        self.assertFalse(state.hands_up)
        self.assertEqual(rig.events, [])
        rig.hold(arms_open())
        self.assertTrue(rig.hold(arms_open(0.60)).arms_open)
        self.assertFalse(rig.hold(standing(0.60)).arms_open)

    def test_one_bad_or_offscreen_wrist_cannot_trigger_a_two_hand_action(self):
        for bad in ("visibility", "presence", "offscreen"):
            with self.subTest(bad=bad):
                rig = Rig().calibrate()
                points = hands_up()
                if bad == "offscreen":
                    points[15].y = -0.1
                else:
                    setattr(points[15], bad, 0.1)
                state = rig.hold(points)
                self.assertGreater(state.tracking_confidence, 0.7)
                self.assertFalse(state.hands_up)

    def test_loss_300ms_clears_actions_retains_lane_and_no_recovery_jump(self):
        rig = Rig().calibrate()
        state = rig.hold(translate(arms_open(), x=-0.12), 600)
        self.assertEqual(state.lane, -1)
        self.assertTrue(state.arms_open)
        state = rig.frame(None)
        self.assertTrue(state.arms_open)
        state = rig.frame(None, 299)
        self.assertTrue(state.arms_open)
        state = rig.frame(None, 1)
        self.assertFalse(state.arms_open)
        self.assertEqual(state.lane, -1)
        self.assertEqual(state.tracking_confidence, 0)
        rig.hold(translate(standing(), x=-0.12, y=-0.10), 600)
        self.assertEqual(rig.events, [])

    def test_tick_expires_actions_when_inference_stops(self):
        rig = Rig().calibrate()
        rig.hold(hands_up())
        self.assertTrue(rig.engine.tick(rig.time + 299).hands_up)
        state = rig.engine.tick(rig.time + 300)
        self.assertFalse(state.hands_up)
        self.assertEqual(state.tracking_confidence, 0)
        self.assertFalse(state.jump_triggered)

    def test_individual_keypoint_occlusion_expires_existing_action(self):
        rig = Rig().calibrate()
        self.assertTrue(rig.hold(hands_up()).hands_up)
        points = hands_up()
        points[15].visibility = 0.1
        state = rig.hold(points, 400)
        self.assertGreater(state.tracking_confidence, 0.7)
        self.assertFalse(state.hands_up)

    def test_duplicate_timestamp_never_repeats_jump(self):
        rig = Rig(Config(pose_ema_alpha=1)).calibrate()
        points = translate(standing(), y=-0.085)
        self.assertTrue(rig.frame(points).jump_triggered)
        self.assertFalse(rig.engine.update(points, rig.time).jump_triggered)
        self.assertFalse(rig.engine.tick(rig.time).jump_triggered)

    def test_nonfinite_landmarks_are_rejected_safely(self):
        rig = Rig().calibrate()
        points = standing()
        points[11].x = float("nan")
        state = rig.frame(points)
        self.assertEqual(state.tracking_confidence, 0)
        self.assertFalse(state.jump_triggered)


if __name__ == "__main__":
    unittest.main()
