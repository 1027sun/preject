"""World tuning plus the three difficulty presets."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Difficulty:
    key: str
    label: str
    speed_scale: float
    gap: tuple          # 波次之间的间隔（秒），越小越密集
    patterns: tuple     # ((pattern, weight), ...)
    hint: bool          # 是否提示前方障碍需要的动作
    note: str


DIFFICULTY_ORDER = ("easy", "normal", "hard")

DIFFICULTIES = {
    "easy": Difficulty(
        key="easy", label="简单", speed_scale=0.80, gap=(2.4, 3.4),
        patterns=(("single", 6), ("corridor", 3), ("pair", 1)),
        hint=True, note="速度最慢，以单点障碍和金币引导为主，并提示动作"),
    "normal": Difficulty(
        key="normal", label="普通", speed_scale=1.00, gap=(1.7, 2.5),
        patterns=(("single", 5), ("corridor", 3), ("pair", 3), ("split", 2),
                  ("slalom", 2), ("gauntlet", 2), ("combo", 1)),
        hint=False, note="标准速度，加入斜向连续与同车道连续障碍"),
    "hard": Difficulty(
        key="hard", label="困难", speed_scale=1.25, gap=(1.15, 1.80),
        patterns=(("single", 2), ("corridor", 2), ("pair", 3), ("split", 3),
                  ("slalom", 3), ("gauntlet", 3), ("combo", 3), ("wave3", 3)),
        hint=False, note="速度最快，会出现三道全封与跳蹲连招"),
}


def difficulty(key):
    """Look a preset up, falling back to 普通."""
    return DIFFICULTIES.get(str(key), DIFFICULTIES["normal"])


@dataclass
class GameConfig:
    density: float = .58          # 0.58 为基准，越大波次越密集
    start_speed: float = 300.0
    end_speed: float = 190.0
    energy_max: float = 100.0
    energy_recovery: float = 1.25
    calories_per_action: float = 0.2   # 体态结算：每个动作折算的千卡
    spawn: bool = True            # False = 静止关卡，供自测使用
