"""Keyboard-driven controller for integration and demonstrations without a camera."""

from dataclasses import replace
import threading

from .control_state import ControlState
from .state_store import StateStore


class FakeCameraController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store = StateStore()
        self._store.register_consumer("debug")
        self._running = False
        self._state = ControlState()

    def start(self) -> None:
        with self._lock:
            if not self._running:
                self._running = True
                self.calibrate()

    def calibrate(self, timeout: float = 15.0) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._store.publish(ControlState())
            self._state = ControlState(tracking_confidence=1.0)
            self._store.publish(self._state)
            return True

    def request_calibration(self) -> bool:
        return self.calibrate()

    def set_lane(self, lane: int) -> None:
        if lane not in (-1, 0, 1):
            raise ValueError("lane must be -1, 0, or 1")
        with self._lock:
            if self._running:
                self._state = replace(self._state, lane=lane)
                self._store.publish(self._state)

    def trigger_jump(self) -> None:
        with self._lock:
            if self._running:
                self._store.publish(replace(self._state, jump_triggered=True))

    def toggle_action(self, name: str) -> None:
        if name not in ("crouch", "arms_open", "hands_up"):
            raise ValueError("action must be crouch, arms_open, or hands_up")
        with self._lock:
            if self._running:
                self._state = replace(self._state, **{name: not getattr(self._state, name)})
                self._store.publish(self._state)

    def get_state(self, consumer: str = "game") -> ControlState:
        return self._store.get_state(consumer)

    def peek_state(self) -> ControlState:
        return self._store.peek_state()

    def get_preview_frame(self, width: int = 320) -> None:
        """Simulation has no camera image; it never consumes a game event."""
        return None

    def register_consumer(self, consumer: str) -> None:
        self._store.register_consumer(consumer)

    def forget_consumer(self, consumer: str) -> None:
        self._store.forget_consumer(consumer)

    def get_debug_snapshot(self) -> dict:
        with self._lock:
            return {
                "frame": None,
                "landmarks": None,
                "calibrated": self._running,
                "diagnostics": {},
                "camera_fps": 0.0,
                "pose_fps": 0.0,
                "latency_ms": 0.0,
                "pose_age_ms": 0.0,
                "error": None,
                "state": self.get_state("debug"),
            }

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._state = ControlState()
            self._store.publish(self._state)
