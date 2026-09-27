from __future__ import annotations

import random

from .models import ClickSettings, ScheduledClick


def _random_point(rng: random.Random, settings: ClickSettings) -> tuple[int, int]:
    while True:
        x = rng.randrange(settings.region_width)
        y = rng.randrange(settings.region_height)
        if settings.shape == "rectangle":
            return x, y
        radius_x = settings.region_width / 2
        radius_y = settings.region_height / 2
        offset_x = (x + 0.5 - radius_x) / radius_x
        offset_y = (y + 0.5 - radius_y) / radius_y
        if offset_x * offset_x + offset_y * offset_y <= 1:
            return x, y


def build_schedule(settings: ClickSettings) -> list[ScheduledClick]:
    """Build a reproducible schedule whose points stay inside the selected shape."""
    settings.validate()
    rng = random.Random(settings.seed)
    x, y = _random_point(rng, settings)
    schedule = [ScheduledClick(elapsed_ms=0, x=x, y=y, event_type="click")]
    elapsed_ms = 0

    while len(schedule) < settings.event_count:
        elapsed_ms += rng.randint(settings.interval_min_ms, settings.interval_max_ms)
        x, y = _random_point(rng, settings)
        schedule.append(
            ScheduledClick(elapsed_ms=elapsed_ms, x=x, y=y, event_type="click")
        )
        if (
            len(schedule) < settings.event_count
            and settings.pair_probability_percent
            and rng.randrange(100) < settings.pair_probability_percent
        ):
            elapsed_ms += rng.randint(settings.pair_gap_min_ms, settings.pair_gap_max_ms)
            x, y = _random_point(rng, settings)
            schedule.append(
                ScheduledClick(
                    elapsed_ms=elapsed_ms,
                    x=x,
                    y=y,
                    event_type="paired_click",
                )
            )

    return schedule
