"""Non-blocking game interface around camera capture and asynchronous inference."""

from collections import deque
import threading
import time

import cv2

from .capture import CameraCapture, now_ms
from .control_state import ControlState
from .engine import ActionEngine
from .pose_view import draw_pose
from .pose_estimator import PoseEstimator
from .state_store import StateStore


def _fps(samples):
    if len(samples) < 2 or samples[-1] == samples[0]:
        return 0.0
    return (len(samples) - 1) * 1000 / (samples[-1] - samples[0])


class CameraController:
    def __init__(self, camera_index=0, width=1280, height=720, model_path=None, config=None):
        self._camera = CameraCapture(camera_index, width, height)
        self._model_path = model_path
        self._engine = ActionEngine(config)
        self._store = StateStore()
        self._store.register_consumer("debug")
        self._lock = threading.RLock()
        self._estimator = None
        self._running = False
        self._frame = None
        self._landmarks = None
        self._aspect_ratio = width / height
        self._camera_times = deque(maxlen=60)
        self._pose_times = deque(maxlen=60)
        self._last_pose_timestamp = None
        self._latency_ms = 0.0
        self._error = None
        self._ignore_before_ms = 0

    def start(self):
        """Open the camera/model and begin automatic standing calibration."""
        if self._running:
            return
        self.request_calibration()
        self._error = None
        self._camera_times.clear()
        self._pose_times.clear()
        try:
            self._estimator = PoseEstimator(self._on_pose, self._model_path)
            self._running = True
            self._camera.start(self._on_frame, self._on_error)
        except Exception:
            self.stop()
            raise

    def _on_frame(self, frame, timestamp_ms):
        with self._lock:
            if not self._running:
                return
            self._frame = frame
            self._aspect_ratio = frame.shape[1] / frame.shape[0]
            self._camera_times.append(timestamp_ms)
        self._estimator.submit(frame, timestamp_ms)

    def _on_pose(self, result, output_image, timestamp_ms):
        try:
            with self._lock:
                if not self._running or timestamp_ms < self._ignore_before_ms:
                    return
                current = now_ms()
                # A delayed inference must not restore confidence after tracking expires.
                if current - timestamp_ms > 300:
                    self._engine.tick(current)
                    self._store.publish(ControlState(lane=self._store.peek_state().lane))
                    return
                self._last_pose_timestamp = timestamp_ms
                self._latency_ms = current - timestamp_ms
                self._pose_times.append(current)
                self._landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
                state = self._engine.update(self._landmarks, timestamp_ms, self._aspect_ratio)
                self._store.publish(state, timestamp_ms=timestamp_ms)
        except Exception as exc:
            self._on_error(f"姿态处理失败：{exc}")

    def _on_error(self, message):
        with self._lock:
            self._error = message
            self._landmarks = None
            self._store.publish(ControlState(lane=self._store.peek_state().lane))

    def request_calibration(self):
        """Reset calibration immediately; subsequent pose callbacks collect samples."""
        with self._lock:
            self._ignore_before_ms = now_ms()
            self._engine.request_calibration()
            self._store.publish(ControlState())
            self._last_pose_timestamp = None
            self._landmarks = None

    def calibrate(self, timeout=15.0):
        """Wait for standing calibration. Call once before the game loop, never per frame."""
        if not self._running:
            raise RuntimeError("请先调用 start() 再进行校准。")
        self.request_calibration()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self._running:
            with self._lock:
                if self._error:
                    return False
                if self._engine.calibrated:
                    return True
            time.sleep(0.02)
        return False

    def _check_freshness(self):
        current = now_ms()
        if (not self._running or self._error or self._last_pose_timestamp is None
                or current - self._last_pose_timestamp > 300):
            self._engine.tick(current)
            self._store.publish(ControlState(lane=self._store.peek_state().lane))
            self._landmarks = None
        return current

    def get_state(self, consumer="game"):
        """Return immediately. Each jump is consumed once by this reader."""
        with self._lock:
            self._check_freshness()
            return self._store.get_state(consumer)

    def peek_state(self):
        """A diagnostic snapshot, not a game event consumer."""
        with self._lock:
            self._check_freshness()
            return self._store.peek_state()

    def register_consumer(self, consumer):
        self._store.register_consumer(consumer)

    def forget_consumer(self, consumer):
        self._store.forget_consumer(consumer)

    def get_preview_frame(self, width=320):
        """Latest mirrored RGB uint8 image (H, W, 3), or None if unavailable.

        The returned buffer is independent of capture. Drawing it doesn't run
        inference or consume ControlState events. Aspect ratio is preserved.
        """
        if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
            raise ValueError("width 必须为正整数。")
        with self._lock:
            if (not self._running or self._error or self._frame is None
                    or not self._camera_times or now_ms()-self._camera_times[-1] > 300):
                return None
            frame = self._frame
        h, w = frame.shape[:2]
        preview = cv2.resize(frame, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)

    def get_annotated_preview(self, width=320):
        """Latest frame with the tracked skeleton drawn, or ``None``.

        Same contract as :meth:`get_preview_frame` (mirrored RGB, aspect kept,
        never consumes ControlState events). The joints come from the most
        recent pose result, so the skeleton disappears while tracking is stale.
        """
        frame = self.get_preview_frame(width)
        if frame is None:
            return None
        with self._lock:
            landmarks = self._landmarks
        if not landmarks:
            return frame
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        draw_pose(bgr, landmarks, scale=max(1.0, frame.shape[1] / 320))
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def get_debug_snapshot(self):
        with self._lock:
            current = self._check_freshness()
            return {
                "frame": self._frame,
                "landmarks": self._landmarks,
                "state": self._store.get_state("debug"),
                "camera_fps": _fps(self._camera_times) if self._camera_times and current-self._camera_times[-1]<1000 else 0.0,
                "pose_fps": _fps(self._pose_times) if self._pose_times and current-self._pose_times[-1]<1000 else 0.0,
                "latency_ms": self._latency_ms,
                "pose_age_ms": current-self._last_pose_timestamp if self._last_pose_timestamp is not None else 0.0,
                "error": self._error,
                "calibrated": self._engine.calibrated,
                "diagnostics": dict(self._engine.diagnostics),
            }

    def stop(self):
        # No controller lock while closing: close waits for callbacks which use it.
        self._running = False
        try:
            self._camera.stop()
        finally:
            if self._estimator:
                self._estimator.close()
                self._estimator = None
            with self._lock:
                self._frame = None
                self._landmarks = None
                self._store.publish(ControlState())

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
