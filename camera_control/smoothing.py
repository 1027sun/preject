"""Time-based EMA and transition confirmation; independent of capture FPS."""

import math


class EMA:
    def __init__(self, alpha: float, nominal_frame_ms: float):
        self.alpha = alpha
        self.nominal_frame_ms = nominal_frame_ms
        self.value: float | None = None
        self.timestamp_ms: int | None = None

    def reset(self) -> None:
        self.value = None
        self.timestamp_ms = None

    def update(self, value: float, timestamp_ms: int) -> float:
        if self.value is None or self.timestamp_ms is None:
            self.value = value
        else:
            elapsed = max(0, timestamp_ms - self.timestamp_ms)
            weight = 1 - math.pow(1 - self.alpha, elapsed / self.nominal_frame_ms)
            self.value += weight * (value - self.value)
        self.timestamp_ms = timestamp_ms
        return self.value


class ConfirmedBoolean:
    def __init__(self, enter_ms: int, exit_ms: int):
        self.enter_ms = enter_ms
        self.exit_ms = exit_ms
        self.value = False
        self.pending: bool | None = None
        self.since_ms: int | None = None
        self.invalid_since_ms: int | None = None

    def reset(self) -> None:
        self.value = False
        self.cancel_pending()
        self.invalid_since_ms = None

    def cancel_pending(self) -> None:
        self.pending = None
        self.since_ms = None

    def update(self, candidate: bool, timestamp_ms: int, allow_enter: bool = True) -> bool:
        self.invalid_since_ms = None
        if not allow_enter and not self.value:
            self.cancel_pending()
            return False
        if candidate == self.value:
            self.cancel_pending()
        elif self.pending != candidate:
            self.pending = candidate
            self.since_ms = timestamp_ms
        elif timestamp_ms - self.since_ms >= (self.enter_ms if candidate else self.exit_ms):
            self.value = candidate
            self.cancel_pending()
        return self.value

    def missing(self, timestamp_ms: int, timeout_ms: int) -> bool:
        self.cancel_pending()
        if self.invalid_since_ms is None:
            self.invalid_since_ms = timestamp_ms
        if timestamp_ms - self.invalid_since_ms >= timeout_ms:
            self.value = False
        return self.value
