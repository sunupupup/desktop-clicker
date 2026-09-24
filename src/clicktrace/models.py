from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Scenario = Literal["random", "random_with_pairs"]


@dataclass(frozen=True)
class ClickSettings:
    event_count: int
    seed: int
    interval_min_ms: int
    interval_max_ms: int
    pair_probability_percent: int
    pair_gap_min_ms: int
    pair_gap_max_ms: int
    region_x: int
    region_y: int
    region_width: int
    region_height: int

    @property
    def scenario(self) -> Scenario:
        return "random_with_pairs" if self.pair_probability_percent else "random"

    def validate(self) -> None:
        if not 1 <= self.event_count <= 10_000:
            raise ValueError("点击次数必须在 1 到 10000 之间。")
        if not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("随机种子必须在 0 到 4294967295 之间。")
        if self.interval_min_ms < 100 or self.interval_max_ms < self.interval_min_ms:
            raise ValueError("随机间隔范围无效；最短间隔至少为 0.1 秒，且不能大于最长间隔。")
        if self.pair_probability_percent not in range(0, 101):
            raise ValueError("双击簇概率必须在 0 到 100 之间。")
        if self.pair_gap_min_ms < 100 or self.pair_gap_max_ms < self.pair_gap_min_ms:
            raise ValueError("双击间隔范围无效；最短间隔至少为 0.1 秒。")
        if self.region_width <= 0 or self.region_height <= 0:
            raise ValueError("蒙板区域的宽度和高度必须大于 0。")
        if self.region_x < 0 or self.region_y < 0:
            raise ValueError("蒙板区域不能超出画布左侧或上侧。")
        if self.region_x + self.region_width > 420 or self.region_y + self.region_height > 260:
            raise ValueError("蒙板区域必须完整留在 420 × 260 的画布内。")


@dataclass(frozen=True)
class ClickEvent:
    scenario: str
    seed: int
    sequence: int
    elapsed_ms: int
    x: int
    y: int
    event_type: str
    origin: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScheduledClick:
    elapsed_ms: int
    x: int
    y: int
    event_type: str


def settings_metadata(settings: ClickSettings) -> dict[str, object]:
    return {
        "generator_version": "1.0",
        "scenario": settings.scenario,
        "settings": asdict(settings),
        "coordinate_note": "x/y are synthetic coordinates relative to the controller mask canvas.",
        "dispatch_note": "Simulated activations call only the in-process demo button.",
    }
