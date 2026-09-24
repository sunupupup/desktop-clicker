# Click Behavior Dataset Simulator Implementation Plan

> **For agentic workers:** Use inline execution in the current task and implement each task in order.

**Goal:** Build a local Windows GUI with a single-button target window and a clicker controller whose draggable, resizable mask triggers random simulated clicks only on that target button.

**Architecture:** A pure standard-library module will produce seeded random click schedules and event records. The Tkinter main window contains only the target button; a separate controller window edits a confined mask, starts/stops scheduled activations, shows recent records, and exports JSON or CSV. The schedule invokes the in-process target button callback and never injects system input.

**Tech Stack:** Python 3 standard library, Tkinter, `random.Random`, `json`, `csv`.

---

## File Structure

- `src/clicktrace/models.py`: typed click settings and event record definitions.
- `src/clicktrace/generator.py`: deterministic random schedule generation and validation.
- `src/clicktrace/exporters.py`: JSON and CSV serialization.
- `src/clicktrace/app.py`: target window, controller window, draggable/resizable mask, scheduler, event log, and save flow.
- `src/clicktrace/__main__.py`: runnable package entry point.
- `README.md`: setup, operation, format, and safety boundary.

## Tasks

### Task 1: Build the click model and seeded random schedule generator

**Files:**
- Create: `src/clicktrace/models.py`
- Create: `src/clicktrace/generator.py`

- [ ] Define `ClickSettings` with event limit, seed, mask rectangle, random interval bounds, and paired-click probability/gap bounds.
- [ ] Define an event record with scenario, seed, sequence, elapsed milliseconds, x/y, event type, and origin.
- [ ] Validate interval ordering, seed, event limit, and positive mask dimensions before starting.
- [ ] Use a local seeded `random.Random` for all interval and coordinate choices.
- [ ] Implement random intervals and optional paired clicks while preserving explicit scenario labels.

### Task 2: Add local trace exporters

**Files:**
- Create: `src/clicktrace/exporters.py`

- [ ] Serialize metadata and events to readable JSON.
- [ ] Serialize event columns to CSV with metadata in leading comment rows.
- [ ] Ensure exports use the same records shown by the UI preview.

### Task 3: Build the single-button target and clicker controller windows

**Files:**
- Create: `src/clicktrace/app.py`
- Create: `src/clicktrace/__main__.py`

- [ ] Create a target window whose only widget is one button; record manual presses in the controller's event log.
- [ ] Create a controller window with validated event count, seed, interval, and pair-gap fields.
- [ ] Draw a mask rectangle on a controller canvas; allow dragging the rectangle and resizing it from its lower-right handle.
- [ ] Schedule seeded random coordinates inside the mask; activate only the target button's in-process callback and record every activation.
- [ ] Provide start/stop controls and cancel pending callbacks on stop or close.
- [ ] Show a bounded event preview and add JSON/CSV save dialogs that preserve the log if canceled or writing fails.
- [ ] Surface validation and file errors in the controller without terminating the UI.
- [ ] Do not add operating-system input-injection APIs.

### Task 4: Document setup and use

**Files:**
- Create: `README.md`

- [ ] Document Python/Tkinter prerequisites and the launch command `python -m src.clicktrace`.
- [ ] Explain the single-button target, controller mask, random interval/pair behavior, seed-based reproducibility, and JSON/CSV schemas.
- [ ] State that simulated activations stay inside the demo program and are not dispatched as desktop or browser input.

## Validation Note

Do not add or run automated tests unless the user requests testing or verification. Keep generator logic isolated and inspect the implementation for deterministic seed use and bounds validation during development.
