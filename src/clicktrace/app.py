from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .exporters import export_csv, export_json
from .generator import build_schedule
from .models import ClickEvent, ClickSettings, ScheduledClick, settings_metadata


class ClickTraceApp:
    CANVAS_WIDTH = 420
    CANVAS_HEIGHT = 260
    PREVIEW_LIMIT = 2_000

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("被测 App")
        # The single button's client area matches the controller's 420 x 260 canvas.
        self.root.geometry("452x292")
        self.root.resizable(False, False)
        self.started_at = time.monotonic()
        self.events: list[ClickEvent] = []
        self.last_settings: ClickSettings | None = None
        self.click_count = 0
        self.physical_point: tuple[int, int] | None = None
        self.pending_simulated: tuple[ClickSettings, ScheduledClick] | None = None
        self.schedule: list[ScheduledClick] = []
        self.schedule_index = 0
        self.schedule_started_at = 0.0
        self.schedule_elapsed_offset_ms = 0
        self.after_id: str | None = None
        self.running = False
        self.preview_rows: dict[int, str] = {}
        self.mask = [60, 50, 230, 150]

        # The target window intentionally contains only the button under test.
        self.target_button = ttk.Button(
            self.root,
            text="测试按钮\n已点击 0 次",
            command=self._on_target_button,
        )
        self.target_button.pack(fill="both", expand=True, padx=16, pady=16)
        self.target_button.bind("<Button-1>", self._capture_physical_point, add="+")

        self.controller = tk.Toplevel(self.root)
        self.controller.title("随机点击测试控制台")
        self.controller.geometry("760x690")
        self.controller.minsize(700, 620)
        self._build_controller()
        self.controller.protocol("WM_DELETE_WINDOW", self.close)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_controller(self) -> None:
        outer = ttk.Frame(self.controller, padding=12)
        outer.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(outer, text="随机点击设置", padding=10)
        settings.pack(fill="x")

        self.count_var = tk.StringVar(value="30")
        self.seed_var = tk.StringVar(value="20260925")
        self.interval_min_var = tk.StringVar(value="10")
        self.interval_max_var = tk.StringVar(value="20")
        self.pair_probability_var = tk.StringVar(value="20")
        self.pair_min_var = tk.StringVar(value="1")
        self.pair_max_var = tk.StringVar(value="2")

        self._add_field(settings, "总点击数", self.count_var, 0, 0, width=10)
        self._add_field(settings, "随机种子", self.seed_var, 0, 2, width=14)
        self._add_field(settings, "间隔最短 (秒)", self.interval_min_var, 1, 0, width=10)
        self._add_field(settings, "间隔最长 (秒)", self.interval_max_var, 1, 2, width=10)
        self._add_field(settings, "双击簇概率 (%)", self.pair_probability_var, 2, 0, width=10)
        self._add_field(settings, "簇内最短 (秒)", self.pair_min_var, 2, 2, width=10)
        self._add_field(settings, "簇内最长 (秒)", self.pair_max_var, 3, 0, width=10)

        mask_frame = ttk.LabelFrame(outer, text="点击蒙板区域", padding=10)
        mask_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(
            mask_frame,
            text="在画布上拖动蒙板移动，拖右下角调整大小；点空白处可重画。坐标只用于本演示程序。",
        ).pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(
            mask_frame,
            width=self.CANVAS_WIDTH,
            height=self.CANVAS_HEIGHT,
            background="#f5f7fa",
            highlightthickness=1,
            highlightbackground="#ccd4df",
        )
        self.canvas.pack(anchor="w")
        self.canvas.bind("<ButtonPress-1>", self._mask_press)
        self.canvas.bind("<B1-Motion>", self._mask_drag)
        self.canvas.bind("<ButtonRelease-1>", self._mask_release)
        self.drag_mode: str | None = None
        self.drag_origin = (0, 0)
        self.drag_mask_origin = (0, 0, 0, 0)
        self.mask_item = 0
        self.handle_item = 0
        self._draw_mask()

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(10, 6))
        self.start_button = ttk.Button(buttons, text="开始随机点击", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="导出 JSON", command=self.save_json).pack(side="left", padx=(18, 0))
        ttk.Button(buttons, text="导出 CSV", command=self.save_csv).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="清空记录", command=self.clear_events).pack(side="right")

        self.status_var = tk.StringVar(value="就绪：随机点击只会触发左侧演示窗口中的按钮。")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.LabelFrame(outer, text="点击行为记录", padding=8)
        log_frame.pack(fill="both", expand=True)
        columns = ("sequence", "scenario", "origin", "elapsed", "x", "y", "type")
        self.table = ttk.Treeview(log_frame, columns=columns, show="headings", height=10)
        headers = {
            "sequence": ("序号", 55),
            "scenario": ("策略", 130),
            "origin": ("来源", 75),
            "elapsed": ("运行时间 (ms)", 120),
            "x": ("X", 55),
            "y": ("Y", 55),
            "type": ("事件", 100),
        }
        for name, (title, width) in headers.items():
            self.table.heading(name, text=title)
            self.table.column(name, width=width, anchor="center", stretch=False)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    @staticmethod
    def _add_field(
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        *,
        width: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(parent, textvariable=variable, width=width).grid(
            row=row, column=column + 1, sticky="w", padx=(0, 22), pady=3
        )

    def _settings_from_form(self) -> ClickSettings:
        try:
            settings = ClickSettings(
                event_count=int(self.count_var.get().strip()),
                seed=int(self.seed_var.get().strip()),
                interval_min_ms=round(float(self.interval_min_var.get()) * 1_000),
                interval_max_ms=round(float(self.interval_max_var.get()) * 1_000),
                pair_probability_percent=int(self.pair_probability_var.get().strip()),
                pair_gap_min_ms=round(float(self.pair_min_var.get()) * 1_000),
                pair_gap_max_ms=round(float(self.pair_max_var.get()) * 1_000),
                region_x=self.mask[0],
                region_y=self.mask[1],
                region_width=self.mask[2],
                region_height=self.mask[3],
            )
        except (ValueError, OverflowError) as error:
            raise ValueError("请检查设置项：需要填写有效的数字。") from error
        settings.validate()
        return settings

    def _draw_mask(self) -> None:
        self.canvas.delete("all")
        x, y, width, height = self.mask
        self.mask_item = self.canvas.create_rectangle(
            x,
            y,
            x + width,
            y + height,
            fill="#5b9bd5",
            stipple="gray25",
            outline="#1769aa",
            width=2,
        )
        self.canvas.create_text(
            x + 8,
            y + 8,
            text=f"随机点击区域  {width} × {height}",
            anchor="nw",
            fill="#102a43",
        )
        self.handle_item = self.canvas.create_rectangle(
            x + width - 8,
            y + height - 8,
            x + width + 2,
            y + height + 2,
            fill="#1769aa",
            outline="#ffffff",
        )

    def _mask_press(self, event: tk.Event) -> None:
        x, y, width, height = self.mask
        px, py = event.x, event.y
        self.drag_origin = (px, py)
        self.drag_mask_origin = tuple(self.mask)
        if x + width - 14 <= px <= x + width + 4 and y + height - 14 <= py <= y + height + 4:
            self.drag_mode = "resize"
        elif x <= px <= x + width and y <= py <= y + height:
            self.drag_mode = "move"
        else:
            self.drag_mode = "draw"
            self.drag_mask_origin = (px, py, 1, 1)
            self.mask = [px, py, 1, 1]
            self._draw_mask()

    def _mask_drag(self, event: tk.Event) -> None:
        if not self.drag_mode:
            return
        x0, y0, width0, height0 = self.drag_mask_origin
        dx, dy = event.x - self.drag_origin[0], event.y - self.drag_origin[1]
        if self.drag_mode == "move":
            new_x = min(max(0, x0 + dx), self.CANVAS_WIDTH - width0)
            new_y = min(max(0, y0 + dy), self.CANVAS_HEIGHT - height0)
            self.mask = [new_x, new_y, width0, height0]
        elif self.drag_mode == "resize":
            new_width = min(max(20, width0 + dx), self.CANVAS_WIDTH - x0)
            new_height = min(max(20, height0 + dy), self.CANVAS_HEIGHT - y0)
            self.mask = [x0, y0, new_width, new_height]
        else:
            current_x = min(max(0, event.x), self.CANVAS_WIDTH)
            current_y = min(max(0, event.y), self.CANVAS_HEIGHT)
            left, right = sorted((x0, current_x))
            top, bottom = sorted((y0, current_y))
            if right - left < 20:
                if current_x >= x0:
                    right = min(self.CANVAS_WIDTH, left + 20)
                else:
                    left = max(0, right - 20)
            if bottom - top < 20:
                if current_y >= y0:
                    bottom = min(self.CANVAS_HEIGHT, top + 20)
                else:
                    top = max(0, bottom - 20)
            self.mask = [left, top, right - left, bottom - top]
        self._draw_mask()

    def _mask_release(self, _event: tk.Event) -> None:
        self.drag_mode = None

    def start(self) -> None:
        if self.running:
            return
        try:
            settings = self._settings_from_form()
            schedule = build_schedule(settings)
        except ValueError as error:
            messagebox.showerror("设置有误", str(error), parent=self.controller)
            return

        self.last_settings = settings
        self.schedule = schedule
        self.schedule_index = 0
        self.schedule_started_at = time.monotonic()
        self.schedule_elapsed_offset_ms = round((self.schedule_started_at - self.started_at) * 1_000)
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set(f"运行中：{len(schedule)} 次；场景={settings.scenario}；seed={settings.seed}")
        self._schedule_next()

    def _schedule_next(self) -> None:
        if not self.running:
            return
        if self.schedule_index >= len(self.schedule):
            self.stop(completed=True)
            return
        click = self.schedule[self.schedule_index]
        elapsed_ms = round((time.monotonic() - self.schedule_started_at) * 1_000)
        delay_ms = max(0, click.elapsed_ms - elapsed_ms)
        self.after_id = self.root.after(delay_ms, self._fire_click, self.schedule_index)

    def _fire_click(self, index: int) -> None:
        self.after_id = None
        if not self.running or index >= len(self.schedule):
            return
        settings = self.last_settings
        if settings is None:
            self.stop()
            return
        click = self.schedule[index]
        self.pending_simulated = (settings, click)
        # Generate a Tk event on the in-process target widget so its normal button
        # press/release bindings and command handler run. No OS input is injected.
        self.target_button.event_generate("<ButtonPress-1>", x=click.x, y=click.y)
        self.target_button.event_generate("<ButtonRelease-1>", x=click.x, y=click.y)
        self.pending_simulated = None
        self.schedule_index += 1
        self.status_var.set(
            f"运行中：{self.schedule_index}/{len(self.schedule)}；随机坐标只记录在本地测试日志。"
        )
        self._schedule_next()

    def stop(self, *, completed: bool = False) -> None:
        self.running = False
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if completed:
            self.status_var.set("完成：本次随机点击已记录，可导出 JSON 或 CSV。")
        elif self.schedule:
            self.status_var.set(f"已停止：记录中保留本次已完成的 {self.schedule_index} 次模拟点击。")

    def _capture_physical_point(self, event: tk.Event) -> None:
        self.physical_point = (int(event.x), int(event.y))

    def _on_target_button(self) -> None:
        self.click_count += 1
        self.target_button.configure(text=f"测试按钮\n已点击 {self.click_count} 次")
        if self.pending_simulated is not None:
            settings, click = self.pending_simulated
            self.physical_point = None
            self._record_event(
                scenario=settings.scenario,
                seed=settings.seed,
                x=click.x,
                y=click.y,
                event_type=click.event_type,
                origin="simulated",
                elapsed_override=self.schedule_elapsed_offset_ms + click.elapsed_ms,
            )
        else:
            x, y = self.physical_point or (0, 0)
            self.physical_point = None
            self._record_event(
                scenario="manual",
                seed=0,
                x=x,
                y=y,
                event_type="button_click",
                origin="manual",
            )

    def _record_event(
        self,
        *,
        scenario: str,
        seed: int,
        x: int,
        y: int,
        event_type: str,
        origin: str,
        elapsed_override: int | None = None,
    ) -> None:
        event = ClickEvent(
            scenario=scenario,
            seed=seed,
            sequence=len(self.events) + 1,
            elapsed_ms=(
                elapsed_override
                if elapsed_override is not None and origin == "simulated"
                else round((time.monotonic() - self.started_at) * 1_000)
            ),
            x=x,
            y=y,
            event_type=event_type,
            origin=origin,
        )
        self.events.append(event)
        row_id = self.table.insert(
            "",
            "end",
            values=(
                event.sequence,
                event.scenario,
                "模拟" if event.origin == "simulated" else "手动",
                event.elapsed_ms,
                event.x,
                event.y,
                event.event_type,
            ),
        )
        self.preview_rows[event.sequence] = row_id
        if len(self.preview_rows) > self.PREVIEW_LIMIT:
            oldest = min(self.preview_rows)
            self.table.delete(self.preview_rows.pop(oldest))
        self.table.see(row_id)

    def _metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "generator_version": "1.0",
            "coordinate_note": (
                "For simulated events x/y are relative to the controller mask canvas; "
                "for manual events x/y are local to the single target button."
            ),
            "dispatch_note": "Simulated activations call only the in-process demo button.",
            "event_count": len(self.events),
        }
        if self.last_settings is not None:
            metadata["last_simulation"] = settings_metadata(self.last_settings)
        return metadata

    def _save(self, kind: str) -> None:
        if not self.events:
            messagebox.showinfo("没有记录", "先手动点击演示按钮，或运行一次随机点击。", parent=self.controller)
            return
        extension = ".json" if kind == "json" else ".csv"
        path = filedialog.asksaveasfilename(
            parent=self.controller,
            title=f"导出 {kind.upper()} 点击记录",
            defaultextension=extension,
            filetypes=[(f"{kind.upper()} 文件", f"*{extension}"), ("所有文件", "*.*")],
            initialfile=f"click-trace{extension}",
        )
        if not path:
            return
        try:
            exporter = export_json if kind == "json" else export_csv
            exporter(path, self._metadata(), list(self.events))
        except OSError as error:
            messagebox.showerror("导出失败", f"无法写入文件：\n{error}", parent=self.controller)
            return
        self.status_var.set(f"已导出 {len(self.events)} 条记录：{path}")

    def save_json(self) -> None:
        self._save("json")

    def save_csv(self) -> None:
        self._save("csv")

    def clear_events(self) -> None:
        if self.running:
            self.stop()
        self.events.clear()
        self.preview_rows.clear()
        for row in self.table.get_children():
            self.table.delete(row)
        self.status_var.set("记录已清空。")

    def close(self) -> None:
        self.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    app = ClickTraceApp()
    app.run()
