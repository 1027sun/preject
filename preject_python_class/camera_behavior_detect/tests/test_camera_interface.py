"""Camera interface behavior with controlled frames; no physical device is opened."""

from unittest import TestCase, main
from unittest.mock import MagicMock, patch
import time

import numpy as np

from camera_control.camera_controller import CameraController
from camera_control.capture import CameraCapture, now_ms
from camera_control.control_state import ControlState


class CameraInterfaceTests(TestCase):
    def test_preview_is_rgb_scaled_independent_and_does_not_consume_jump(self):
        controller = CameraController()
        controller._running = True
        # BGR blue frame must become RGB (0, 0, 255).
        controller._frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        controller._frame[:, :, 0] = 255
        controller._camera_times.append(now_ms())
        controller._last_pose_timestamp = now_ms()
        controller._store.publish(ControlState(jump_triggered=True, tracking_confidence=1.0))
        preview = controller.get_preview_frame()
        self.assertEqual(preview.shape, (180, 320, 3))
        self.assertEqual(preview[0, 0].tolist(), [0, 0, 255])
        preview[:] = 0
        self.assertEqual(controller._frame[0, 0].tolist(), [255, 0, 0])
        self.assertTrue(controller.get_state().jump_triggered)
        self.assertFalse(controller.get_state().jump_triggered)

    def test_preview_unavailable_for_stopped_failed_or_stale_capture(self):
        controller = CameraController()
        self.assertIsNone(controller.get_preview_frame())
        controller._running = True
        controller._frame = np.zeros((480, 640, 3), dtype=np.uint8)
        controller._camera_times.append(now_ms() - 1000)
        self.assertIsNone(controller.get_preview_frame())
        controller._camera_times.append(now_ms())
        self.assertEqual(controller.get_preview_frame(320).shape, (240, 320, 3))
        controller._error = "disconnected"
        self.assertIsNone(controller.get_preview_frame())
        with self.assertRaises(ValueError):
            controller.get_preview_frame(0)

    def test_stale_pose_clears_actions_but_keeps_last_lane(self):
        controller = CameraController()
        controller._running = True
        controller._last_pose_timestamp = now_ms() - 500
        controller._store.publish(ControlState(-1, True, True, True, True, 1.0))
        self.assertEqual(controller.get_state(), ControlState(lane=-1))

    def test_start_stop_start_failure_releases_model_and_camera(self):
        failed_device = MagicMock()
        failed_device.isOpened.return_value = False
        capture = CameraCapture()
        capture._camera = MagicMock()  # Previously stopped instance.
        capture.stop()
        self.assertIsNone(capture._camera)
        with patch("camera_control.capture.cv2.VideoCapture", return_value=failed_device):
            with self.assertRaisesRegex(RuntimeError, "无法打开摄像头"):
                capture.start(lambda *_: None, lambda *_: None)
        self.assertIsNone(capture._camera)

        with patch("camera_control.camera_controller.PoseEstimator") as estimator:
            controller = CameraController()
            with patch.object(controller._camera, "start", side_effect=RuntimeError("busy")):
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    controller.start()
            estimator.return_value.close.assert_called_once()
            self.assertFalse(controller._running)
            self.assertEqual(controller.get_state(), ControlState())

    def test_get_state_does_not_wait_for_capture_or_inference(self):
        controller = CameraController()
        controller._running = True
        controller._last_pose_timestamp = now_ms()
        controller._store.publish(ControlState(tracking_confidence=0.9))
        with patch.object(controller._camera, "start", side_effect=AssertionError("capture called")):
            begin = time.perf_counter()
            for _ in range(1000):
                controller.get_state()
            self.assertLess(time.perf_counter() - begin, 0.3)


    def test_annotated_preview_draws_skeleton_on_a_copy(self):
        from types import SimpleNamespace
        controller = CameraController()
        self.assertIsNone(controller.get_annotated_preview())
        controller._running = True
        controller._frame = np.zeros((360, 640, 3), dtype=np.uint8)
        controller._camera_times.append(now_ms())
        controller._last_pose_timestamp = now_ms()
        plain = controller.get_preview_frame(320)
        self.assertFalse(plain.any())
        controller._landmarks = [SimpleNamespace(x=0.5, y=0.5, visibility=0.9)] * 33
        annotated = controller.get_annotated_preview(320)
        self.assertEqual(annotated.shape, plain.shape)
        self.assertTrue(annotated.any())
        # The plain preview must stay untouched, and no landmarks means no bones.
        self.assertFalse(controller.get_preview_frame(320).any())
        controller._landmarks = None
        self.assertFalse(controller.get_annotated_preview(320).any())

    def test_draw_pose_ignores_empty_input_and_low_visibility(self):
        from types import SimpleNamespace
        from camera_control.pose_view import draw_pose
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        draw_pose(frame, None)
        self.assertFalse(frame.any())
        draw_pose(frame, [SimpleNamespace(x=0.5, y=0.5, visibility=0.1)] * 33)
        self.assertFalse(frame.any())
        draw_pose(frame, [SimpleNamespace(x=0.5, y=0.5, visibility=0.9)] * 33, scale=0.5)
        self.assertTrue(frame.any())


if __name__ == "__main__":
    main()
