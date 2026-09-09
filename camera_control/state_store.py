"""Thread-safe latest state with short-lived, per-consumer jump delivery."""

from dataclasses import replace
import threading
import time

from .control_state import ControlState


class StateStore:
    """Continuous controls use the newest frame; jumps survive skipped frames.

    ``game`` is registered immediately. Other consumers should register before
    polling; their first registration skips events published before they joined.
    Timestamps use ``time.monotonic() * 1000`` (milliseconds).
    """

    def __init__(self, jump_ttl_ms: float = 350.0) -> None:
        self._lock = threading.Lock()
        self._state = ControlState()
        self._jump_sequence = 0
        self._jump_at_ms: float | None = None
        self._consumers: dict[str, int] = {"game": 0}
        self._jump_ttl_ms = jump_ttl_ms

    def publish(self, state: ControlState, timestamp_ms: float | None = None) -> None:
        timestamp_ms = time.monotonic() * 1000 if timestamp_ms is None else timestamp_ms
        with self._lock:
            self._state = state
            if state.tracking_confidence < 0.7:
                self._jump_at_ms = None
                self._state = replace(state, jump_triggered=False)
            elif state.jump_triggered:
                self._jump_sequence += 1
                self._jump_at_ms = timestamp_ms

    def register_consumer(self, consumer: str) -> None:
        """Register once, without replaying a jump from before registration."""
        with self._lock:
            self._consumers.setdefault(consumer, self._jump_sequence)

    def forget_consumer(self, consumer: str) -> None:
        with self._lock:
            self._consumers.pop(consumer, None)

    def _jump_is_fresh(self) -> bool:
        return (
            self._jump_at_ms is not None
            and time.monotonic() * 1000 - self._jump_at_ms <= self._jump_ttl_ms
        )

    def get_state(self, consumer: str = "game") -> ControlState:
        """Consume the latest fresh jump once for this consumer, never a queue."""
        with self._lock:
            seen = self._consumers.setdefault(consumer, self._jump_sequence)
            jump = seen < self._jump_sequence and self._jump_is_fresh()
            self._consumers[consumer] = self._jump_sequence
            return replace(self._state, jump_triggered=jump)

    def peek_state(self) -> ControlState:
        """Inspect the current frame without consuming any consumer's jump."""
        with self._lock:
            return replace(
                self._state,
                jump_triggered=self._state.jump_triggered and self._jump_is_fresh(),
            )
