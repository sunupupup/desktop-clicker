# Click Behavior Dataset Simulator Design

## Goal

Build a local Windows desktop utility for generating labeled synthetic click-behavior traces so the owner can analyze and validate their own app's anti-automation detector.

## Scope

- Provide a compact Tkinter desktop UI.
- Generate reproducible traces for fixed intervals, uniformly randomized intervals, and paired-click clusters with configurable long pauses.
- Constrain synthetic integer coordinates to a configurable rectangle.
- Attach scenario labels, seed, configuration, sequence number, elapsed time, and x/y coordinates to each event.
- Preview generated rows and export JSON or CSV locally.

## Safety boundary

This is an offline data generator. It will not inject mouse or keyboard events, inspect other windows, control browsers, evade detection, or interact with accounts or external services. Scenario names and configuration remain explicit in exported data so detector results can be analyzed against known labels.

## Architecture

Use Python's standard library and Tkinter. Keep trace generation as a pure module independent of the UI, with a small application module that validates settings, displays a preview, and exports generated rows. Use a seeded `random.Random` instance per generation so a run can be reproduced without global random state.

## Data format

Each event contains `scenario`, `seed`, `sequence`, `elapsed_ms`, `x`, `y`, and `event_type`. The export includes a metadata object (scenario parameters and generator version) and an `events` array in JSON; CSV places the same metadata in a companion header comment and emits one event per row.

## Failure behavior

Reject negative or reversed ranges, nonpositive event counts, malformed seeds, and rectangles without positive width/height before generating any output. Canceling a save dialog leaves the preview intact. File-write errors are surfaced in the UI without losing the generated trace.

## Deferred

Global desktop overlays, real input injection, browser integration, detector tuning, and online account testing are outside this project.
