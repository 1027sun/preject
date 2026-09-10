"""Obstacle wave patterns.

Every obstacle and coin still spawns at z = 0 so the road perspective stays
correct; a pattern only decides *when* each piece appears. A wave therefore
carries relative delays, and the next wave is scheduled after the current one
has finished plus a difficulty gap. A wave that would force a jump directly
into a crouch gets an extra floor on that gap.
"""
from dataclasses import dataclass

from entities import Coin, Obstacle

JUMP = "jump"
CROUCH = "crouch"
COIN = "coin"

LANES = (-1, 0, 1)
JUMP_KINDS = ("wall", "gap")
CROUCH_KINDS = ("tunnel", "sign")

#: 同一波内两个障碍的间隔，略长于 0.8 秒的跳跃。
BEAT = 1.15


@dataclass(frozen=True)
class Event:
    delay: float
    kind: str
    lane: int


@dataclass(frozen=True)
class Wave:
    name: str
    events: tuple
    actions: frozenset
    locks: frozenset


def _kind(rng, action):
    return rng.choice(JUMP_KINDS if action == JUMP else CROUCH_KINDS)


def _trail(lane, count, spacing=0.20, lead=0.90):
    """Coins that arrive *before* the wave anchor, used as a path hint."""
    return [Event(-(lead - i * spacing), COIN, lane) for i in range(count)]


def _crowd(rng, player_lane, chance=0.45):
    """Bias single-lane patterns onto the lane the player already occupies."""
    if player_lane in LANES and rng.random() < chance:
        return player_lane
    return rng.choice(LANES)


def pattern_single(rng, player_lane):
    action = rng.choice((JUMP, CROUCH))
    lane = _crowd(rng, player_lane)
    events = [Event(0.0, _kind(rng, action), lane)]
    others = [value for value in LANES if value != lane]
    if rng.random() < 0.62:
        events += _trail(rng.choice(others), rng.choice((3, 4, 5)))
    return Wave("single", tuple(events), frozenset({action}), frozenset({action}))


def pattern_pair(rng, player_lane):
    """两条道被封、留一条安全道，两条道的动作相同，跳或蹲都能过。"""
    action = rng.choice((JUMP, CROUCH))
    blocked = rng.sample(LANES, 2)
    free = [value for value in LANES if value not in blocked][0]
    events = [Event(0.0, _kind(rng, action), lane) for lane in blocked]
    events += _trail(free, 4, 0.20, 0.80)
    return Wave("pair", tuple(events), frozenset({action}), frozenset({action}))


def pattern_corridor(rng, player_lane):
    """金币铺出安全路线，引导玩家提前换道。"""
    action = rng.choice((JUMP, CROUCH))
    lane = rng.choice(LANES)
    free = [value for value in LANES if value != lane]
    events = [Event(0.0, _kind(rng, action), lane)]
    events += _trail(rng.choice(free), 6, 0.18, 1.30)
    if rng.random() < 0.5:
        events.append(Event(BEAT, _kind(rng, action), lane))
    return Wave("corridor", tuple(events), frozenset({action}), frozenset({action}))


def pattern_slalom(rng, player_lane):
    """三条道依次各来一个，必须走出 S 形路线。"""
    order = rng.sample(LANES, 3)
    events = []
    for index, lane in enumerate(order):
        action = rng.choice((JUMP, CROUCH))
        events.append(Event(index * BEAT, _kind(rng, action), lane))
        if index + 1 < len(order):
            events += _trail(order[index + 1], 2, 0.25, 0.30)
    return Wave("slalom", tuple(events), frozenset(), frozenset())


def pattern_gauntlet(rng, player_lane):
    """同一条道连续三个障碍，形成节奏。"""
    action = rng.choice((JUMP, CROUCH))
    lane = _crowd(rng, player_lane, 0.40)
    events = [Event(index * BEAT, _kind(rng, action), lane) for index in range(3)]
    events += [Event(0.18 + index * BEAT, COIN, lane) for index in range(3)]
    return Wave("gauntlet", tuple(events), frozenset({action}), frozenset({action}))


def pattern_combo(rng, player_lane):
    """同一条道先跳后蹲（或先蹲后跳），考验动作切换。"""
    lane = rng.choice(LANES)
    first, second = rng.choice(((JUMP, CROUCH), (CROUCH, JUMP)))
    events = [Event(0.0, _kind(rng, first), lane),
              Event(BEAT + 0.10, _kind(rng, second), lane)]
    events += [Event(0.35, COIN, lane), Event(BEAT + 0.45, COIN, lane)]
    return Wave("combo", tuple(events), frozenset({JUMP, CROUCH}),
                frozenset({JUMP, CROUCH}))


def pattern_split(rng, player_lane):
    """两条道分别要跳和蹲，第三条道是空的：看清后选动作或换道。"""
    blocked = rng.sample(LANES, 2)
    free = [value for value in LANES if value not in blocked][0]
    events = [Event(0.0, _kind(rng, JUMP), blocked[0]),
              Event(0.0, _kind(rng, CROUCH), blocked[1])]
    events += _trail(free, 4, 0.20, 0.85)
    return Wave("split", tuple(events), frozenset({JUMP, CROUCH}),
                frozenset({JUMP, CROUCH}))


def pattern_wave3(rng, player_lane):
    """三道同时封死，只能跳或只能蹲，无法靠换道躲开。"""
    action = rng.choice((JUMP, CROUCH))
    events = [Event(0.0, _kind(rng, action), lane) for lane in LANES]
    events += _trail(rng.choice(LANES), 3, 0.16, 0.55)
    return Wave("wave3", tuple(events), frozenset({action}), frozenset({action}))


PATTERNS = {
    "single": pattern_single,
    "pair": pattern_pair,
    "corridor": pattern_corridor,
    "slalom": pattern_slalom,
    "gauntlet": pattern_gauntlet,
    "split": pattern_split,
    "combo": pattern_combo,
    "wave3": pattern_wave3,
}


def build_wave(name, rng, player_lane):
    return PATTERNS[name](rng, player_lane)


def conflicts(previous, current):
    """跳跃的 0.8 秒硬直和紧随其后的下蹲互相冲突。"""
    return ((JUMP in previous and CROUCH in current)
            or (CROUCH in previous and JUMP in current))


class LevelSpawner:
    """Feeds obstacles and coins into the world on a difficulty schedule."""

    FIRST_WAVE_DELAY = 2.2

    def __init__(self, cfg, rng, preset):
        self.cfg = cfg
        self.rng = rng
        self.preset = preset
        self.reset()

    def set_difficulty(self, preset):
        self.preset = preset

    def reset(self):
        self._queue = []
        self._cooldown = self.FIRST_WAVE_DELAY
        self._previous = frozenset()
        self.waves = 0
        self.last_wave = ""
        self.last_gap = 0.0

    @property
    def pending(self):
        return len(self._queue)

    def update(self, dt, player_lane, obstacles, coins):
        """Spawn due events, then schedule the next wave when the gap expires."""
        if not getattr(self.cfg, "spawn", True):
            return
        due = []
        for item in self._queue:
            item[0] -= dt
            if item[0] <= 0:
                due.append(item)
        if due:
            self._queue = [item for item in self._queue if item[0] > 0]
            for _, kind, lane in due:
                if kind == COIN:
                    coins.append(Coin(lane, 0.0, self.rng.random() * 6.283))
                else:
                    obstacles.append(Obstacle(lane, kind))
        self._cooldown -= dt
        if self._cooldown <= 0:
            self._emit(player_lane)

    def _emit(self, player_lane):
        names = [name for name, _ in self.preset.patterns]
        weights = [weight for _, weight in self.preset.patterns]
        wave = build_wave(self.rng.choices(names, weights=weights)[0],
                          self.rng, player_lane)
        shift = -min(0.0, min(event.delay for event in wave.events))
        latest = 0.0
        for event in wave.events:
            delay = event.delay + shift
            latest = max(latest, delay)
            self._queue.append([delay, event.kind, event.lane])
        low, high = self.preset.gap
        gap = self.rng.uniform(low, high) * (0.58 / max(0.35, self.cfg.density))
        if conflicts(self._previous, wave.locks):
            # 0.8 秒跳跃硬直 + 0.25 秒起身 / 下蹲余量，密度再高也要留出来。
            gap = max(gap, 1.05)
        self._cooldown = latest + gap
        self._previous = wave.locks
        self.waves += 1
        self.last_wave = wave.name
        self.last_gap = gap
        return wave
