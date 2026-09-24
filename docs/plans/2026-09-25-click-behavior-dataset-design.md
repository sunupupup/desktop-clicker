# Click Behavior Dataset Simulator Design

## Goal

Build a local Windows desktop utility with a target window containing only one button and a separate clicker control window. The button records clicks; the clicker draws a draggable, resizable mask region and triggers random synthetic clicks only against that demo button so the owner can analyze their own app's click logging.

## Scope

- Provide a target Tkinter window containing a single button. Physical button presses and simulated button activations are recorded in the controller's local event log.
- Provide a separate Tkinter controller window with a draggable and resizable mask region.
- Generate random-interval clicks with integer coordinates constrained to the current mask, with optional paired clicks after a configurable long pause.
- Attach scenario labels, seed, sequence number, elapsed time, x/y coordinates, and origin (`manual` or `simulated`) to each event.
- Preview recent events and export JSON or CSV locally.

## Safety boundary

The controller dispatches simulated Tk press/release events only to the single demo button in this same process. The mask is confined to the controller canvas and does not overlay or control other desktop windows. The program will not inject system mouse or keyboard events, inspect other windows, control browsers, evade detection, or interact with accounts or external services. Scenario names and configuration remain explicit in exported data so detector results can be analyzed against known labels.

## Architecture

Use Python's standard library and Tkinter. Keep trace generation as a pure module independent of the UI, with an application module that validates settings, presents the single-button target and controller window, displays recent events, and exports generated rows. Use a seeded `random.Random` instance per generation so a run can be reproduced without global random state. Schedule local Tk press/release events with Tkinter's event loop and cancel outstanding callbacks on stop or close.

## Data format

Each event contains `scenario`, `seed`, `sequence`, `elapsed_ms`, `x`, `y`, `event_type`, and `origin`. The export includes a metadata object (scenario parameters and generator version) and an `events` array in JSON; CSV places the same metadata in leading comment rows and emits one event per row.

## Failure behavior

Reject negative or reversed intervals, malformed seeds, event counts outside the configured limit, and mask sizes without positive width/height before starting. Canceling a save dialog leaves the event log intact. File-write errors are surfaced in the UI without losing the event log. Stop and window close cancel pending timer callbacks.

## Deferred

Desktop-wide overlays, real input injection, browser integration, detector tuning, and online account testing are outside this project.
