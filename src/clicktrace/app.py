from __future__ import annotations

import time
import random
import os
import tkinter as tk
from dataclasses import dataclass, replace
from tkinter import filedialog, messagebox, ttk

from .android_input import AndroidTouchClicker
from .desktop_input import (
    move_overlay,
    post_left_click,
    primary_screen_bounds,
    set_overlay_click_through,
    top_level_window,
    virtual_desktop_bounds,
    window_context_at,
)
from .exporters import export_csv, export_json
from .generator import build_schedule
from .models import ClickEvent, ClickSettings, ScheduledClick, settings_metadata
from .uia_input import UIAutomationClicker


TRANSPARENT_COLOR = "#01FEFD"


@dataclass
class ClickRegion:
    region_id: int
    settings: ClickSettings
    schedule: list[ScheduledClick]
    x: int
    y: int
    overlay: tk.Toplevel | None = None
    canvas: tk.Canvas | None = None
    hwnd: int | None = None
    schedule_index: int = 0
    after_id: str | None = None
    running: bool = False
    active_segment_started: float = 0.0
    elapsed_offset_ms: int = 0
    drag_mode: str | None = None
    drag_pointer_origin: tuple[int, int] = (0, 0)
    drag_region_origin: tuple[int, int] = (0, 0)
    drag_settings_origin: ClickSettings | None = None
    drag_schedule_origin: list[ScheduledClick] | None = None
    uia_clicker: UIAutomationClicker | None = None
    android_clicker: AndroidTouchClicker | None = None


class ClickTraceApp:
    PREVIEW_LIMIT = 2_000
    RESIZE_HANDLE_SIZE = 14

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("桌面区域点击器")
        self.root.geometry("820x900+24+24")
        # Allow the main window to shrink to half of its previous minimum size.
        self.root.minsize(370, 380)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.events: list[ClickEvent] = []
        self.preview_rows: dict[int, str] = {}
        self.regions: dict[int, ClickRegion] = {}
        self.next_region_id = 1

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=(
                "不调用 Windows 鼠标输入、不切换系统前台窗口。MuMu 区域使用 Android 触摸事件；其他窗口优先 UI Automation，随后投递窗口消息。"
            ),
            wraplength=780,
        ).pack(anchor="w", pady=(0, 10))

        settings_frame = ttk.LabelFrame(outer, text="新区域设置（间隔可同步到已有区域）", padding=10)
        settings_frame.pack(fill="x")
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)

        self.shape_var = tk.StringVar(value="矩形")
        self.count_var = tk.StringVar(value="10000")
        self.width_var = tk.StringVar(value="240")
        self.height_var = tk.StringVar(value="140")
        self.seed_var = tk.StringVar(value="20260925")
        self.interval_min_var = tk.StringVar(value="1")
        self.interval_max_var = tk.StringVar(value="2")
        self.pair_probability_var = tk.StringVar(value="0")
        self.pair_min_var = tk.StringVar(value="1")
        self.pair_max_var = tk.StringVar(value="2")

        self._add_combo(settings_frame, "区域形状", self.shape_var, 0, 0, ("矩形", "椭圆"))
        self._add_field(settings_frame, "点击数", self.count_var, 0, 2)
        self._add_field(settings_frame, "宽度 (px)", self.width_var, 1, 0)
        self._add_field(settings_frame, "高度 (px)", self.height_var, 1, 2)
        self._add_field(settings_frame, "随机种子", self.seed_var, 2, 0)
        self._add_field(settings_frame, "间隔最短 (秒)", self.interval_min_var, 2, 2)
        self._add_field(settings_frame, "间隔最长 (秒)", self.interval_max_var, 3, 0)
        self._add_field(settings_frame, "追加点击概率 (%)", self.pair_probability_var, 3, 2)
        self._add_field(settings_frame, "追加间隔最短 (秒)", self.pair_min_var, 4, 0)
        self._add_field(settings_frame, "追加间隔最长 (秒)", self.pair_max_var, 4, 2)
        ttk.Button(
            settings_frame,
            text="同步间隔到全部区域",
            command=self.apply_intervals_to_existing_regions,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(10, 4))
        ttk.Button(controls, text="新增区域", command=self.generate_region).pack(side="left")
        self.active_button = ttk.Button(
            controls, text="激活所选区域", command=self.toggle_selected_region, state="disabled"
        )
        self.active_button.pack(side="left", padx=(8, 0))
        self.delete_button = ttk.Button(
            controls, text="删除所选区域", command=self.delete_selected_region, state="disabled"
        )
        self.delete_button.pack(side="left", padx=(8, 0))
        self.delete_all_button = ttk.Button(
            controls, text="删除全部区域", command=self.delete_all_regions, state="disabled"
        )
        self.delete_all_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="导出 JSON", command=self.save_json).pack(side="left", padx=(16, 0))
        ttk.Button(controls, text="导出 CSV", command=self.save_csv).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="清空记录", command=self.clear_events).pack(side="right")

        region_frame = ttk.LabelFrame(outer, text="区域列表", padding=8)
        region_frame.pack(fill="x", pady=(6, 0))
        region_columns = ("id", "shape", "size", "position", "interval", "state", "progress")
        self.region_table = ttk.Treeview(
            region_frame, columns=region_columns, show="headings", height=4, selectmode="browse"
        )
        for name, title, width in (
            ("id", "编号", 55),
            ("shape", "形状", 70),
            ("size", "尺寸", 130),
            ("position", "屏幕位置", 170),
            ("interval", "间隔", 90),
            ("state", "状态", 90),
            ("progress", "已调用/投递", 120),
        ):
            self.region_table.heading(name, text=title)
            self.region_table.column(name, width=width, anchor="center", stretch=name == "position")
        self.region_table.pack(fill="x", expand=True)
        self.region_table.bind("<<TreeviewSelect>>", self._selection_changed)
        self.region_table.bind("<Double-1>", lambda _event: self.toggle_selected_region())

        self.region_info_var = tk.StringVar(value="尚未生成区域。")
        ttk.Label(outer, textvariable=self.region_info_var).pack(anchor="w", pady=(6, 2))
        self.status_var = tk.StringVar(value="设置好形状和策略，点击“新增区域”。")
        ttk.Label(outer, textvariable=self.status_var, wraplength=780).pack(anchor="w", pady=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="输入调用记录（不代表目标应用已响应）", padding=8)
        log_frame.pack(fill="both", expand=True)
        columns = ("sequence", "region", "scheduled", "elapsed", "delay", "x", "y", "mode", "type")
        self.table = ttk.Treeview(log_frame, columns=columns, show="headings", height=8)
        for name, title, width in (
            ("sequence", "序号", 55),
            ("region", "区域", 55),
            ("scheduled", "计划 (ms)", 85),
            ("elapsed", "调用/投递 (ms)", 100),
            ("delay", "延迟 (ms)", 75),
            ("x", "X", 75),
            ("y", "Y", 75),
            ("mode", "方式（*仅投递）", 125),
            ("type", "事件", 110),
        ):
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
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(parent, textvariable=variable, width=11).grid(
            row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=4
        )

    @staticmethod
    def _add_combo(
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=4)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=10).grid(
            row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=4
        )

    def _settings_from_form(self) -> ClickSettings:
        try:
            settings = ClickSettings(
                shape="ellipse" if self.shape_var.get() == "椭圆" else "rectangle",
                input_mode="window_message",
                event_count=int(self.count_var.get().strip()),
                seed=int(self.seed_var.get().strip()),
                interval_min_ms=round(float(self.interval_min_var.get()) * 1_000),
                interval_max_ms=round(float(self.interval_max_var.get()) * 1_000),
                pair_probability_percent=int(self.pair_probability_var.get().strip()),
                pair_gap_min_ms=round(float(self.pair_min_var.get()) * 1_000),
                pair_gap_max_ms=round(float(self.pair_max_var.get()) * 1_000),
                region_width=int(self.width_var.get().strip()),
                region_height=int(self.height_var.get().strip()),
            )
        except (ValueError, OverflowError) as error:
            raise ValueError("请检查设置：所有选项都需要填写有效数字。") from error
        settings.validate()
        return settings

    def generate_region(self) -> None:
        try:
            settings = self._settings_from_form()
            schedule = build_schedule(settings)
            left, top, screen_width, screen_height = primary_screen_bounds()
            if settings.region_width > screen_width or settings.region_height > screen_height:
                raise ValueError("区域宽高不能超过主屏尺寸。")
        except (ValueError, RuntimeError, OSError) as error:
            messagebox.showerror("区域设置有误", str(error), parent=self.root)
            return

        region_id = self.next_region_id
        self.next_region_id += 1
        gap = 24
        columns = max(1, (screen_width - 40 + gap) // (settings.region_width + gap))
        rows = max(1, (screen_height - 90 + gap) // (settings.region_height + gap))
        slot = (region_id - 1) % (columns * rows)
        column = slot % columns
        row = slot // columns
        x = left + screen_width - settings.region_width - 40 - column * (settings.region_width + gap)
        y = top + screen_height - settings.region_height - 90 - row * (settings.region_height + gap)
        region = ClickRegion(region_id, settings, schedule, x, y)
        try:
            self._create_overlay(region)
        except (tk.TclError, OSError, RuntimeError) as error:
            self._destroy_overlay(region)
            messagebox.showerror("无法创建区域浮层", str(error), parent=self.root)
            return

        self.regions[region_id] = region
        iid = str(region_id)
        self.region_table.insert("", "end", iid=iid, values=self._region_row(region))
        self.region_table.selection_set(iid)
        self.region_table.focus(iid)
        self._selection_changed()
        self.status_var.set(
            f"已新增区域 {region_id}（主屏坐标 {x}, {y}）。可继续新增其他区域。"
        )

    def apply_intervals_to_existing_regions(self) -> None:
        if not self.regions:
            self.status_var.set("当前没有已有区域；新增区域会使用表单中的间隔。")
            return
        try:
            interval_min_ms = round(float(self.interval_min_var.get()) * 1_000)
            interval_max_ms = round(float(self.interval_max_var.get()) * 1_000)
            pair_gap_min_ms = round(float(self.pair_min_var.get()) * 1_000)
            pair_gap_max_ms = round(float(self.pair_max_var.get()) * 1_000)
            if interval_min_ms < 100 or interval_max_ms < interval_min_ms:
                raise ValueError("随机间隔无效；最短间隔至少为 0.1 秒且不能大于最长间隔。")
            if pair_gap_min_ms < 100 or pair_gap_max_ms < pair_gap_min_ms:
                raise ValueError("追加间隔无效；最短间隔至少为 0.1 秒且不能大于最长间隔。")
        except (ValueError, OverflowError) as error:
            messagebox.showerror("间隔设置有误", str(error), parent=self.root)
            return

        for region in self.regions.values():
            settings = replace(
                region.settings,
                interval_min_ms=interval_min_ms,
                interval_max_ms=interval_max_ms,
                pair_gap_min_ms=pair_gap_min_ms,
                pair_gap_max_ms=pair_gap_max_ms,
            )
            settings.validate()
            elapsed = region.elapsed_offset_ms
            if region.running:
                elapsed += round((time.monotonic() - region.active_segment_started) * 1_000)

            updated_schedule = list(region.schedule[: region.schedule_index])
            next_elapsed = elapsed
            rng = random.Random((settings.seed + region.schedule_index) & 0xFFFFFFFF)
            for offset, click in enumerate(region.schedule[region.schedule_index :]):
                if region.schedule_index == 0 and offset == 0:
                    scheduled_elapsed = next_elapsed
                else:
                    if click.event_type == "paired_click":
                        minimum, maximum = settings.pair_gap_min_ms, settings.pair_gap_max_ms
                    else:
                        minimum, maximum = settings.interval_min_ms, settings.interval_max_ms
                    next_elapsed += rng.randint(minimum, maximum)
                    scheduled_elapsed = next_elapsed
                updated_schedule.append(
                    ScheduledClick(scheduled_elapsed, click.x, click.y, click.event_type)
                )

            region.settings = settings
            region.schedule = updated_schedule
            if region.running:
                if region.after_id is not None:
                    try:
                        self.root.after_cancel(region.after_id)
                    except tk.TclError:
                        pass
                    region.after_id = None
                self._schedule_next(region)
            self._sync_region_row(region)

        self.status_var.set(
            f"已将 {interval_min_ms / 1_000:g}–{interval_max_ms / 1_000:g} 秒间隔同步到 {len(self.regions)} 个已有区域的剩余计划。"
        )

    def _create_overlay(self, region: ClickRegion) -> None:
        overlay = tk.Toplevel(self.root)
        region.overlay = overlay
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-transparentcolor", TRANSPARENT_COLOR)
        overlay.attributes("-alpha", 0.34)
        overlay.geometry(f"{region.settings.region_width}x{region.settings.region_height}")
        canvas = tk.Canvas(
            overlay,
            width=region.settings.region_width,
            height=region.settings.region_height,
            background=TRANSPARENT_COLOR,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        region.canvas = canvas
        overlay.update_idletasks()
        region.hwnd = top_level_window(overlay.winfo_id())
        self._draw_region(region)
        canvas.bind("<ButtonPress-1>", lambda event, item=region: self._drag_start(item, event))
        canvas.bind("<B1-Motion>", lambda event, item=region: self._drag_move(item, event))
        canvas.bind("<ButtonRelease-1>", lambda event, item=region: self._drag_end(item, event))
        move_overlay(region.hwnd, region.x, region.y)
        overlay.deiconify()
        overlay.lift()
        set_overlay_click_through(region.hwnd, False)

    def _draw_region(self, region: ClickRegion) -> None:
        if region.canvas is None:
            return
        canvas = region.canvas
        canvas.delete("all")
        width = region.settings.region_width
        height = region.settings.region_height
        is_ellipse = region.settings.shape == "ellipse"
        draw_shape = canvas.create_oval if is_ellipse else canvas.create_rectangle
        draw_shape(
            0,
            0,
            width,
            height,
            fill="#b6e3ff" if region.running else "#ffd966",
            outline="#176b9b" if region.running else "#cc7a00",
            width=3,
        )
        canvas.create_text(
            width // 2,
            14,
            text=f"区域 {region.region_id} · {'活跃' if region.running else '非活跃'}",
            fill="#17324d" if region.running else "#3b2b00",
            anchor="n",
        )
        handle = self.RESIZE_HANDLE_SIZE
        canvas.create_rectangle(
            width - handle,
            height - handle,
            width - 2,
            height - 2,
            fill="#3b2b00",
            outline="#ffffff",
            width=1,
        )
        canvas.create_line(
            width - handle + 4,
            height - 4,
            width - 4,
            height - handle + 4,
            fill="#ffffff",
            width=1,
        )

    def _region_row(self, region: ClickRegion) -> tuple[object, ...]:
        shape = "椭圆" if region.settings.shape == "ellipse" else "矩形"
        state = "活跃" if region.running else "非活跃"
        progress = f"{region.schedule_index}/{len(region.schedule)}"
        return (
            region.region_id,
            shape,
            f"{region.settings.region_width} × {region.settings.region_height}",
            f"({region.x}, {region.y})",
            f"{region.settings.interval_min_ms / 1_000:g}–{region.settings.interval_max_ms / 1_000:g} 秒",
            state,
            progress,
        )

    def _sync_region_row(self, region: ClickRegion) -> None:
        iid = str(region.region_id)
        if self.region_table.exists(iid):
            self.region_table.item(iid, values=self._region_row(region))
        selected = self._selected_region()
        if selected is not None and selected.region_id == region.region_id:
            self.region_info_var.set(self._region_description(region))
            self.active_button.configure(text="暂停所选区域" if region.running else "激活所选区域")

    def _selected_region(self) -> ClickRegion | None:
        selection = self.region_table.selection()
        if not selection:
            return None
        try:
            return self.regions.get(int(selection[0]))
        except ValueError:
            return None

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        region = self._selected_region()
        available = region is not None
        self.active_button.configure(state="normal" if available else "disabled")
        self.delete_button.configure(state="normal" if available else "disabled")
        self.delete_all_button.configure(state="normal" if self.regions else "disabled")
        if region is None:
            self.region_info_var.set("尚未选中区域。")
            self.active_button.configure(text="激活所选区域")
            return
        self.region_info_var.set(self._region_description(region))
        self.active_button.configure(text="暂停所选区域" if region.running else "激活所选区域")

    @staticmethod
    def _region_description(region: ClickRegion) -> str:
        shape = "椭圆" if region.settings.shape == "ellipse" else "矩形"
        return (
            f"区域 {region.region_id}：{shape} {region.settings.region_width} × "
            f"{region.settings.region_height} px，间隔 {region.settings.interval_min_ms / 1_000:g}–"
            f"{region.settings.interval_max_ms / 1_000:g} 秒，左上角 ({region.x}, {region.y})。"
        )

    def toggle_selected_region(self) -> None:
        region = self._selected_region()
        if region is None:
            return
        if region.running:
            self._set_region_inactive(region)
        else:
            self._set_region_active(region)

    def _set_region_active(self, region: ClickRegion) -> None:
        if region.region_id not in self.regions:
            return
        if region.schedule_index >= len(region.schedule):
            messagebox.showinfo("计划已完成", "修改新区域设置并新增区域可创建新计划。", parent=self.root)
            return
        if region.hwnd is None:
            return
        try:
            set_overlay_click_through(region.hwnd, True)
        except OSError as error:
            messagebox.showerror("区域激活失败", str(error), parent=self.root)
            return
        region.running = True
        region.active_segment_started = time.monotonic()
        self._draw_region(region)
        self._sync_region_row(region)
        self.status_var.set(f"区域 {region.region_id} 已活跃；系统鼠标光标保持不动。")
        self._schedule_next(region)

    def _set_region_inactive(self, region: ClickRegion, *, completed: bool = False) -> None:
        if region.running:
            region.elapsed_offset_ms += round((time.monotonic() - region.active_segment_started) * 1_000)
        region.running = False
        if region.after_id is not None:
            try:
                self.root.after_cancel(region.after_id)
            except tk.TclError:
                pass
            region.after_id = None
        if region.hwnd is not None:
            try:
                set_overlay_click_through(region.hwnd, False)
            except OSError as error:
                self.status_var.set(f"区域 {region.region_id} 输入状态更新失败：{error}")
        self._draw_region(region)
        self._sync_region_row(region)
        if completed:
            self.status_var.set(f"区域 {region.region_id} 的调用计划已完成。")
        elif region.schedule_index:
            self.status_var.set(
                f"区域 {region.region_id} 已暂停，剩余 "
                f"{len(region.schedule) - region.schedule_index} 个计划事件。"
            )

    def _schedule_next(self, region: ClickRegion) -> None:
        if not region.running:
            return
        if region.schedule_index >= len(region.schedule):
            self._set_region_inactive(region, completed=True)
            return
        click = region.schedule[region.schedule_index]
        elapsed = region.elapsed_offset_ms + round(
            (time.monotonic() - region.active_segment_started) * 1_000
        )
        region.after_id = self.root.after(
            max(0, click.elapsed_ms - elapsed),
            self._fire_click,
            region.region_id,
            region.schedule_index,
        )

    def _fire_click(self, region_id: int, index: int) -> None:
        region = self.regions.get(region_id)
        if region is None:
            return
        region.after_id = None
        if not region.running or index >= len(region.schedule):
            return
        click = region.schedule[index]
        x, y = region.x + click.x, region.y + click.y
        try:
            process_id, image_path, target_hwnd = window_context_at(x, y)
            if process_id == os.getpid():
                raise RuntimeError("点击坐标命中了连点器自身窗口，请将区域移到其他应用上。")
        except (OSError, RuntimeError) as error:
            self._pause_after_click_failure(region, region_id, error)
            return
        if os.path.basename(image_path).casefold() == "mumunxdevice.exe":
            if region.android_clicker is None:
                region.android_clicker = AndroidTouchClicker()
            region.android_clicker.request(
                target_hwnd,
                process_id,
                x,
                y,
                lambda result: self._uia_click_finished(region_id, index, click, x, y, result),
            )
            return
        # Keep each region's UIA calls isolated. A blocked provider for one
        # target must not serialize every other region behind the same worker.
        if region.uia_clicker is None:
            region.uia_clicker = UIAutomationClicker(own_process_id=os.getpid())
        region.uia_clicker.request(
            x,
            y,
            lambda result: self._uia_click_finished(region_id, index, click, x, y, result),
        )

    def _uia_click_finished(
        self,
        region_id: int,
        index: int,
        click: ScheduledClick,
        x: int,
        y: int,
        result: str,
    ) -> None:
        try:
            self.root.after(
                0,
                self._complete_click,
                region_id,
                index,
                click,
                x,
                y,
                result,
            )
        except tk.TclError:
            return

    def _complete_click(
        self,
        region_id: int,
        index: int,
        click: ScheduledClick,
        x: int,
        y: int,
        result: str,
    ) -> None:
        region = self.regions.get(region_id)
        if region is None or not region.running or region.schedule_index != index:
            return
        origins = {
            "INVOKED": "uia_invoke",
            "TOGGLED": "uia_toggle",
            "SELECTED": "uia_select",
            "ANDROID_TAP": "android_adb_touch",
        }
        origin = origins.get(result)
        if result == "NO_PATTERN":
            try:
                excluded_hwnds = tuple(
                    handle
                    for handle in (self.root.winfo_id(), *(item.hwnd for item in self.regions.values()))
                    if handle is not None
                )
                post_left_click(x, y, excluded_hwnds=excluded_hwnds)
                origin = "window_message"
            except (OSError, RuntimeError, ValueError) as error:
                self._pause_after_click_failure(region, region_id, error)
                return
        elif origin is None:
            message = {
                "SELF": "点击坐标命中了连点器自身窗口。",
                "TIMEOUT": "UI Automation 响应超时，已暂停该区域，未重复投递点击。",
            }.get(result, "无法触发目标输入，已暂停该区域。")
            if result.startswith("ERROR:"):
                message = result.removeprefix("ERROR:")
            self._pause_after_click_failure(region, region_id, RuntimeError(message))
            return

        actual_elapsed_ms = region.elapsed_offset_ms + round(
            (time.monotonic() - region.active_segment_started) * 1_000
        )
        lateness_ms = max(0, actual_elapsed_ms - click.elapsed_ms)
        if lateness_ms:
            region.schedule = [
                ScheduledClick(
                    item.elapsed_ms + lateness_ms if position > index else item.elapsed_ms,
                    item.x,
                    item.y,
                    item.event_type,
                )
                for position, item in enumerate(region.schedule)
            ]
        self._record_event(
            region_id=region.region_id,
            scenario=region.settings.scenario,
            seed=region.settings.seed,
            scheduled_elapsed_ms=click.elapsed_ms,
            elapsed_ms=actual_elapsed_ms,
            x=x,
            y=y,
            event_type=click.event_type,
            origin=origin,
        )
        region.schedule_index += 1
        self._sync_region_row(region)
        dispatch_label = {
            "uia_invoke": "UIA 控件调用",
            "uia_toggle": "UIA 切换控件",
            "uia_select": "UIA 选择控件",
            "window_message": "窗口消息已投递（未确认目标响应）",
            "android_adb_touch": "MuMu Android 触摸事件已注入",
        }[origin]
        self.status_var.set(f"区域 {region_id}：{dispatch_label} {region.schedule_index}/{len(region.schedule)}。")
        self._schedule_next(region)

    def _pause_after_click_failure(self, region: ClickRegion, region_id: int, error: Exception) -> None:
        self._set_region_inactive(region)
        self.status_var.set(f"区域 {region_id} 输入调用失败，已暂停：{error}")
        messagebox.showerror("输入调用失败", str(error), parent=self.root)

    def _drag_start(self, region: ClickRegion, event: tk.Event) -> None:
        if region.running:
            return
        width = region.settings.region_width
        height = region.settings.region_height
        region.drag_mode = (
            "resize"
            if event.x >= width - self.RESIZE_HANDLE_SIZE
            and event.y >= height - self.RESIZE_HANDLE_SIZE
            else "move"
        )
        region.drag_pointer_origin = (event.x_root, event.y_root)
        region.drag_region_origin = (region.x, region.y)
        region.drag_settings_origin = region.settings
        region.drag_schedule_origin = list(region.schedule)

    def _drag_move(self, region: ClickRegion, event: tk.Event) -> None:
        if region.running or region.hwnd is None or region.drag_mode is None:
            return
        left, top, desktop_width, desktop_height = virtual_desktop_bounds()
        dx = event.x_root - region.drag_pointer_origin[0]
        dy = event.y_root - region.drag_pointer_origin[1]
        if region.drag_mode == "resize":
            origin = region.drag_settings_origin
            if origin is None:
                return
            max_width = min(5_000, left + desktop_width - region.x)
            max_height = min(5_000, top + desktop_height - region.y)
            width = min(max(20, origin.region_width + dx), max_width)
            height = min(max(20, origin.region_height + dy), max_height)
            region.settings = replace(origin, region_width=width, region_height=height)
            self.width_var.set(str(width))
            self.height_var.set(str(height))
            try:
                assert region.overlay is not None
                region.overlay.geometry(f"{width}x{height}")
                if region.canvas is not None:
                    region.canvas.configure(width=width, height=height)
                move_overlay(region.hwnd, region.x, region.y)
            except (tk.TclError, OSError) as error:
                self.status_var.set(f"区域 {region.region_id} 调整大小失败：{error}")
                return
            self._draw_region(region)
            self._sync_region_row(region)
            return

        x = min(max(left, region.drag_region_origin[0] + dx), left + desktop_width - region.settings.region_width)
        y = min(max(top, region.drag_region_origin[1] + dy), top + desktop_height - region.settings.region_height)
        try:
            move_overlay(region.hwnd, x, y)
        except OSError as error:
            self.status_var.set(f"区域 {region.region_id} 移动失败：{error}")
            return
        region.x, region.y = x, y
        self._sync_region_row(region)

    def _drag_end(self, region: ClickRegion, _event: tk.Event) -> None:
        if region.drag_mode == "resize" and region.drag_settings_origin is not None:
            original = region.drag_settings_origin
            if (
                region.settings.region_width != original.region_width
                or region.settings.region_height != original.region_height
            ):
                try:
                    coordinates = build_schedule(region.settings)
                    prior = region.drag_schedule_origin or region.schedule
                    region.schedule = [
                        ScheduledClick(old.elapsed_ms, new.x, new.y, old.event_type)
                        for old, new in zip(prior, coordinates)
                    ]
                except ValueError as error:
                    self.status_var.set(f"区域 {region.region_id} 点击坐标更新失败：{error}")
        region.drag_mode = None
        region.drag_settings_origin = None
        region.drag_schedule_origin = None
        self._sync_region_row(region)

    def delete_selected_region(self) -> None:
        region = self._selected_region()
        if region is not None:
            self._delete_region(region)

    def delete_all_regions(self) -> None:
        for region in list(self.regions.values()):
            self._delete_region(region, refresh=False)
        self._selection_changed()
        self.status_var.set("全部区域已删除；已有点击记录保留。")

    def _delete_region(self, region: ClickRegion, *, refresh: bool = True) -> None:
        if region.region_id not in self.regions:
            return
        self._set_region_inactive(region)
        if region.uia_clicker is not None:
            region.uia_clicker.close()
            region.uia_clicker = None
        if region.android_clicker is not None:
            region.android_clicker.close()
            region.android_clicker = None
        self._destroy_overlay(region)
        self.regions.pop(region.region_id, None)
        iid = str(region.region_id)
        if self.region_table.exists(iid):
            self.region_table.delete(iid)
        if refresh:
            self._selection_changed()
            self.status_var.set(f"区域 {region.region_id} 已删除；已有点击记录保留。")

    @staticmethod
    def _destroy_overlay(region: ClickRegion) -> None:
        if region.overlay is not None:
            try:
                region.overlay.destroy()
            except tk.TclError:
                pass
        region.overlay = None
        region.canvas = None
        region.hwnd = None

    def _record_event(
        self,
        *,
        region_id: int,
        scenario: str,
        seed: int,
        scheduled_elapsed_ms: int,
        elapsed_ms: int,
        x: int,
        y: int,
        event_type: str,
        origin: str,
    ) -> None:
        event = ClickEvent(
            scenario=scenario,
            seed=seed,
            sequence=len(self.events) + 1,
            scheduled_elapsed_ms=scheduled_elapsed_ms,
            elapsed_ms=elapsed_ms,
            dispatch_delay_ms=max(0, elapsed_ms - scheduled_elapsed_ms),
            x=x,
            y=y,
            event_type=event_type,
            origin=origin,
            region_id=region_id,
        )
        self.events.append(event)
        mode_label = {
            "uia_invoke": "UIA 调用",
            "uia_toggle": "UIA 切换",
            "uia_select": "UIA 选择",
            "window_message": "消息投递*",
            "android_adb_touch": "Android 触摸",
        }.get(origin, origin)
        row_id = self.table.insert(
            "",
            "end",
            values=(
                event.sequence,
                region_id,
                event.scheduled_elapsed_ms,
                event.elapsed_ms,
                event.dispatch_delay_ms,
                event.x,
                event.y,
                mode_label,
                event.event_type,
            ),
        )
        self.preview_rows[event.sequence] = row_id
        if len(self.preview_rows) > self.PREVIEW_LIMIT:
            oldest = min(self.preview_rows)
            self.table.delete(self.preview_rows.pop(oldest))
        self.table.see(row_id)

    def _metadata(self) -> dict[str, object]:
        return {
            "generator_version": "3.4",
            "coordinate_note": "x/y are absolute desktop pixel coordinates.",
            "dispatch_note": "scheduled_elapsed_ms is the planned due time; elapsed_ms is when UI Automation returned, window messages were posted, or an Android touch injection command completed; dispatch_delay_ms is dispatch lateness. These records do not confirm target application completion. An origin/mode labeled with * is an unconfirmed PostMessage delivery.",
            "region_count": len(self.regions),
            "regions": [
                {
                    "region_id": region.region_id,
                    "settings": settings_metadata(region.settings),
                    "position": {"x": region.x, "y": region.y},
                    "active": region.running,
                    "completed_dispatches": region.schedule_index,
                }
                for region in self.regions.values()
            ],
            "event_count": len(self.events),
        }

    def _save(self, kind: str) -> None:
        if not self.events:
            messagebox.showinfo("没有记录", "还没有点击输入记录可导出。", parent=self.root)
            return
        extension = ".json" if kind == "json" else ".csv"
        path = filedialog.asksaveasfilename(
            parent=self.root,
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
            messagebox.showerror("导出失败", f"无法写入文件：\n{error}", parent=self.root)
            return
        self.status_var.set(f"已导出 {len(self.events)} 条记录：{path}")

    def save_json(self) -> None:
        self._save("json")

    def save_csv(self) -> None:
        self._save("csv")

    def clear_events(self) -> None:
        self.events.clear()
        self.preview_rows.clear()
        for row in self.table.get_children():
            self.table.delete(row)
        self.status_var.set("输入调用记录已清空；区域计划继续运行。")

    def close(self) -> None:
        for region in list(self.regions.values()):
            self._set_region_inactive(region)
            if region.uia_clicker is not None:
                region.uia_clicker.close()
                region.uia_clicker = None
            if region.android_clicker is not None:
                region.android_clicker.close()
                region.android_clicker = None
            self._destroy_overlay(region)
        self.regions.clear()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    ClickTraceApp().run()
