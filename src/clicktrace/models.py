from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Shape = Literal["rectangle", "ellipse"]
Scenario = Literal["random", "random_with_pairs"]
InputMode = Literal["window_message"]


@dataclass(frozen=True)
class ClickSettings:
    shape: Shape
    input_mode: InputMode
    event_count: int
    seed: int
    interval_min_ms: int
    interval_max_ms: int
    pair_probability_percent: int
    pair_gap_min_ms: int
    pair_gap_max_ms: int
    region_width: int
    region_height: int

    @property
    def scenario(self) -> Scenario:
        return "random_with_pairs" if self.pair_probability_percent else "random"

    def validate(self) -> None:
        if self.shape not in ("rectangle", "ellipse"):
            raise ValueError("区域形状必须是矩形或椭圆。")
        if self.input_mode != "window_message":
            raise ValueError("点击方式无效。")
        if not 1 <= self.event_count <= 10_000:
            raise ValueError("点击次数必须在 1 到 10000 之间。")
        if not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("随机种子必须在 0 到 4294967295 之间。")
        if self.interval_min_ms < 100 or self.interval_max_ms < self.interval_min_ms:
            raise ValueError("随机间隔无效；最短间隔至少为 0.1 秒且不能大于最长间隔。")
        if self.pair_probability_percent not in range(0, 101):
            raise ValueError("双击簇概率必须在 0 到 100 之间。")
        if self.pair_gap_min_ms < 100 or self.pair_gap_max_ms < self.pair_gap_min_ms:
            raise ValueError("簇内间隔无效；最短间隔至少为 0.1 秒。")
        if not 20 <= self.region_width <= 5_000 or not 20 <= self.region_height <= 5_000:
            raise ValueError("区域宽高必须在 20 到 5000 像素之间。")


@dataclass(frozen=True)
class ClickEvent:
    scenario: str
    seed: int
    sequence: int
    scheduled_elapsed_ms: int
    elapsed_ms: int
    dispatch_delay_ms: int
    x: int
    y: int
    event_type: str
    origin: str
    region_id: int = 1
    target_response_confirmed: bool = False

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
        "generator_version": "3.1",
        "scenario": settings.scenario,
        "settings": asdict(settings),
        "coordinate_note": "Event x/y are absolute desktop pixel coordinates.",
    }
