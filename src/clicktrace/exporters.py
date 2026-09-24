from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import ClickEvent


def export_json(path: str | Path, metadata: dict[str, object], events: Iterable[ClickEvent]) -> None:
    payload = {"metadata": metadata, "events": [event.to_dict() for event in events]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_csv(path: str | Path, metadata: dict[str, object], events: Iterable[ClickEvent]) -> None:
    event_rows = [event.to_dict() for event in events]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as output:
        output.write("# metadata=" + json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "\n")
        writer = csv.DictWriter(
            output,
            fieldnames=["scenario", "seed", "sequence", "elapsed_ms", "x", "y", "event_type", "origin"],
        )
        writer.writeheader()
        writer.writerows(event_rows)
