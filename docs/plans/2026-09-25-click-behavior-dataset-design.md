# Draggable Desktop Click Region Design

## Goal

Replace the in-process demo-button clicker with one movable desktop region for browser click-behavior testing.

## User flow

Choose a rectangle or ellipse, enter its dimensions and click strategy, then generate the region. Generation creates a visible floating overlay and deterministic finite click plan without clicking. While inactive, the user can drag the region. Activating it makes the overlay click-through and dispatches the planned clicks to the window below it. Deactivating pauses the plan; reactivation resumes the remaining clicks. Completion automatically returns the region to inactive. Generating again replaces the region and plan.

## Design

- Keep one controller window for shape, dimensions, count, seed, random interval, and optional paired-click settings.
- Show one borderless, semi-transparent, topmost overlay using the selected shape.
- In inactive mode the overlay accepts pointer input for dragging. In active mode the Windows extended transparent style passes pointer input through; the clicker resolves each desktop coordinate to its underlying window and posts mouse messages without moving the system cursor.
- Store generated points relative to the region. Resolve them to desktop coordinates at dispatch time so moving the region before or between active segments remains correct.
- Record absolute desktop coordinates and export the event log as JSON or CSV.

## Error handling

Validate settings and ensure the region fits the virtual desktop before generation. Report unsupported Windows overlay behavior, missing target windows, and `PostMessage` failures in the controller. Stop or pause on dispatch failure; preserve completed records. Posted messages may not be handled by every target application.

## Limits

This version handles one region at a time and supports rectangles and ellipses. The overlay can be moved while inactive. Windows may block input to applications running at a higher integrity level.
