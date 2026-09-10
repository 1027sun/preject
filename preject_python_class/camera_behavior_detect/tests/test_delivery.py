from dataclasses import FrozenInstanceError, asdict
import time
import unittest

from camera_control.control_state import ControlState
from camera_control.fake_controller import FakeCameraController
from camera_control.state_store import StateStore


class StateDeliveryTests(unittest.TestCase):
    def test_interface_has_exactly_six_fields_and_is_immutable(self):
        state = ControlState()
        self.assertEqual(asdict(state), {
            "lane": 0, "jump_triggered": False, "crouch": False,
            "arms_open": False, "hands_up": False, "tracking_confidence": 0.0,
        })
        with self.assertRaises(FrozenInstanceError):
            state.lane = 1

    def test_jump_survives_newer_frames_and_each_consumer_gets_it_once(self):
        store = StateStore()
        store.register_consumer("debug")
        store.publish(ControlState(jump_triggered=True, tracking_confidence=0.95))
        store.publish(ControlState(lane=1, arms_open=True, tracking_confidence=0.95))
        self.assertFalse(store.peek_state().jump_triggered)
        game = store.get_state()
        self.assertTrue(game.jump_triggered)
        self.assertEqual(game.lane, 1)
        self.assertTrue(game.arms_open)
        self.assertFalse(store.get_state().jump_triggered)
        self.assertTrue(store.get_state("debug").jump_triggered)
        self.assertFalse(store.get_state("debug").jump_triggered)

    def test_late_consumer_skips_previous_jump(self):
        store = StateStore()
        store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        store.register_consumer("late")
        self.assertFalse(store.get_state("late").jump_triggered)
        self.assertFalse(store.get_state("unregistered").jump_triggered)
        self.assertTrue(store.get_state().jump_triggered)
        store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        self.assertTrue(store.get_state("late").jump_triggered)
        store.forget_consumer("late")
        store.register_consumer("late")
        self.assertFalse(store.get_state("late").jump_triggered)

    def test_expired_or_low_confidence_jumps_are_not_replayed(self):
        store = StateStore()
        store.publish(
            ControlState(jump_triggered=True, tracking_confidence=1.0),
            timestamp_ms=time.monotonic() * 1000 - 400,
        )
        self.assertFalse(store.get_state().jump_triggered)
        self.assertFalse(store.peek_state().jump_triggered)
        store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        store.publish(ControlState(tracking_confidence=0.69))
        store.publish(ControlState(tracking_confidence=1.0))
        self.assertFalse(store.get_state().jump_triggered)
        store.publish(ControlState(jump_triggered=True, tracking_confidence=0.69))
        self.assertFalse(store.get_state().jump_triggered)

    def test_multiple_unread_jumps_do_not_form_a_backlog(self):
        store = StateStore()
        store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        self.assertTrue(store.get_state().jump_triggered)
        self.assertFalse(store.get_state().jump_triggered)


class FakeControllerTests(unittest.TestCase):
    def test_fake_preview_has_no_image_and_preserves_jump(self):
        controller = FakeCameraController()
        self.assertIsNone(controller.get_preview_frame())
        controller.start()
        controller.trigger_jump()
        self.assertIsNone(controller.get_preview_frame(width=640))
        self.assertTrue(controller.get_state().jump_triggered)
        controller.stop()
        self.assertIsNone(controller.get_preview_frame())

    def test_fake_control_and_debug_do_not_steal_game_jump(self):
        controller = FakeCameraController()
        self.assertFalse(controller.calibrate())
        controller.start()
        controller.set_lane(-1)
        controller.toggle_action("hands_up")
        controller.trigger_jump()
        debug = controller.get_debug_snapshot()
        self.assertTrue(debug["calibrated"])
        self.assertIsNone(debug["frame"])
        self.assertTrue(debug["state"].jump_triggered)
        state = controller.get_state()
        self.assertTrue(state.jump_triggered)
        self.assertTrue(state.hands_up)
        self.assertEqual(state.lane, -1)
        self.assertFalse(controller.get_state().jump_triggered)
        controller.trigger_jump()
        self.assertTrue(controller.calibrate())
        self.assertFalse(controller.get_state().jump_triggered)
        self.assertEqual(controller.get_state().lane, 0)
        controller.stop()
        self.assertEqual(controller.get_state(), ControlState())
        self.assertFalse(controller.get_debug_snapshot()["calibrated"])

    def test_invalid_fake_actions_are_rejected(self):
        controller = FakeCameraController()
        with self.assertRaises(ValueError):
            controller.set_lane(4)
        with self.assertRaises(ValueError):
            controller.toggle_action("unknown")


if __name__ == "__main__":
    unittest.main()
