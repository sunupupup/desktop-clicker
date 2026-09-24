# Click Behavior Dataset Simulator Implementation Plan

> **For agentic workers:** Use inline execution in the current task and implement each task in order.

**Goal:** Build a local Windows GUI that generates reproducible labeled click traces for validating an owned app's anti-automation detector.

**Architecture:** A pure standard-library trace-generation module will produce synthetic event records. A Tkinter UI will collect scenario parameters, display a preview, and export JSON or CSV. No system input will be injected.

**Tech Stack:** Python 3 standard library, Tkinter, `random.Random`, `json`, `csv`.

---

## File Structure

- `src/clicktrace/models.py`: typed settings and event record definitions.
- `src/clicktrace/generator.py`: deterministic, labeled trace generation and validation.
- `src/clicktrace/exporters.py`: JSON and CSV serialization.
- `src/clicktrace/app.py`: Tkinter form, preview, and save flow.
- `src/clicktrace/__main__.py`: runnable package entry point.
- `README.md`: setup, operation, format, and safety boundary.

## Tasks

### Task 1: Build the deterministic trace model and generator

**Files:**
- Create: `src/clicktrace/models.py`
- Create: `src/clicktrace/generator.py`

- [ ] Define `TraceSettings` with scenario, event count, seed, rectangle coordinates, interval bounds in milliseconds, and paired-click gap bounds.
- [ ] Define an event record with scenario, seed, sequence, elapsed milliseconds, x, y, and event type.
- [ ] Validate scenario parameters and rectangle dimensions before generating events.
- [ ] Use a local seeded `random.Random` for all interval and coordinate choices.
- [ ] Implement fixed, uniform-range, and paired-cluster timing while preserving explicit scenario labels.

### Task 2: Add local trace exporters

**Files:**
- Create: `src/clicktrace/exporters.py`

- [ ] Serialize metadata and events to readable JSON.
- [ ] Serialize event columns to CSV with metadata in leading comment rows.
- [ ] Ensure exports use the same records shown by the UI preview.

### Task 3: Build the Tkinter application

**Files:**
- Create: `src/clicktrace/app.py`
- Create: `src/clicktrace/__main__.py`

- [ ] Provide scenario selection and validated numeric fields for event count, seed, rectangle, and intervals.
- [ ] Generate a trace on demand and show a bounded preview with event count and scenario metadata.
- [ ] Add JSON and CSV save dialogs; preserve preview state if the dialog is canceled or writing fails.
- [ ] Surface validation and file errors in the application without terminating the UI.
- [ ] Keep the application entirely offline and do not add input-injection APIs.

### Task 4: Document setup and use

**Files:**
- Create: `README.md`

- [ ] Document Python/Tkinter prerequisites and the launch command `python -m src.clicktrace`.
- [ ] Explain each scenario, seed-based reproducibility, coordinate bounds, and JSON/CSV schemas.
- [ ] State that generated records are synthetic and are not dispatched as desktop or browser input.

## Validation Note

Do not add or run automated tests unless the user requests testing or verification. Keep generator logic isolated and inspect the implementation for deterministic seed use and bounds validation during development.
