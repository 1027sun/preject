"""The six-field game interface shared by real and simulated controllers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlState:
    lane: int = 0
    jump_triggered: bool = False
    crouch: bool = False
    arms_open: bool = False
    hands_up: bool = False
    tracking_confidence: float = 0.0
