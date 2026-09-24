from __future__ import annotations

import random

from .models import ClickSettings, ScheduledClick


def build_schedule(settings: ClickSettings) -> list[ScheduledClick]:
    """Build a reproducible random schedule without dispatching any input."""
    settings.validate()
    rng = random.Random(settings.seed)
    schedule = [
        ScheduledClick(
            elapsed_ms=0,
            x=rng.randint(settings.region_x, settings.region_x + settings.region_width - 1),
            y=rng.randint(settings.region_y, settings.region_y + settings.region_height - 1),
            event_type="click",
        )
    ]
    elapsed_ms = 0

    while len(schedule) < settings.event_count:
        elapsed_ms += rng.randint(settings.interval_min_ms, settings.interval_max_ms)
        schedule.append(
            ScheduledClick(
                elapsed_ms=elapsed_ms,
                x=rng.randint(settings.region_x, settings.region_x + settings.region_width - 1),
                y=rng.randint(settings.region_y, settings.region_y + settings.region_height - 1),
                event_type="click",
            )
        )
        if (
            len(schedule) < settings.event_count
            and settings.pair_probability_percent
            and rng.randrange(100) < settings.pair_probability_percent
        ):
            elapsed_ms += rng.randint(settings.pair_gap_min_ms, settings.pair_gap_max_ms)
            schedule.append(
                ScheduledClick(
                    elapsed_ms=elapsed_ms,
                    x=rng.randint(settings.region_x, settings.region_x + settings.region_width - 1),
                    y=rng.randint(settings.region_y, settings.region_y + settings.region_height - 1),
                    event_type="paired_click",
                )
            )

    return schedule
