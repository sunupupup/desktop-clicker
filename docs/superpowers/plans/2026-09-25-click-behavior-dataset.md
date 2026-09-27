# Desktop Click Region Implementation Plan

## Goal

Build a Windows desktop clicker around one floating, movable rectangle or ellipse with a generated click plan and active/inactive control.

## Components

- `src/clicktrace/models.py`: validated shape and click strategy settings, event records, and metadata.
- `src/clicktrace/generator.py`: reproducible random plans constrained to the chosen shape.
- `src/clicktrace/desktop_input.py`: virtual-desktop mouse input, overlay click-through mode, and overlay movement.
- `src/clicktrace/app.py`: configuration UI, floating region, pause/resume control, log, and export actions.
- `README.md`: launch and operation guide.

## Behavior

- Generating creates/replaces the overlay and plan without sending clicks.
- The inactive overlay receives mouse input and can be dragged.
- The active overlay is click-through; planned clicks target the window beneath the current region.
- Switching inactive pauses the schedule and preserves remaining clicks; switching active resumes it.
- Completion returns to inactive. Errors pause the run and preserve completed records.

## Validation

Review the implementation and run `git diff --check`. Do not run automated tests unless requested.
