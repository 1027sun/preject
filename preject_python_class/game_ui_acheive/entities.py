from dataclasses import dataclass

@dataclass
class Obstacle:
    lane: int; kind: str; z: float = 0.0; checked: bool = False

@dataclass
class Coin:
    lane: int; z: float = 0.0; phase: float = 0.0

