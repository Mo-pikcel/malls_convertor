"""
main.py — AdScreen Converter desktop app (Flet).
"""

import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

import flet as ft

from core import (
    BASE_DIR,
    INPUT_DIR,
    OUTPUT_DIR,
    PREVIEW_DIR,
    Template,
    FormatPlan,
    ffmpeg_available,
    generate_thumbnail,
    image_to_video,
    load_templates,
    plan_exports,
    probe_video,
    template_search_text,
    zip_outputs,
    export_format,
)

# ──────────────────────────────────────────────
# APP STATE
# ──────────────────────────────────────────────

@dataclass
class AppState:
    templates: dict = field(default_factory=dict)       # display_str -> Template
    search_index: dict = field(default_factory=dict)    # display_str -> search text
    selected_keys: list = field(default_factory=list)
    input_path: Path | None = None
    video_w: int = 0
    video_h: int = 0
    duration: float = 0.0
    export_jobs: list = field(default_factory=list)     # [(Template, FormatPlan)]
    output_files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    # Settings
    crf: int = 18
    preset: str = "slow"
    img_duration: int = 10
    use_smart_crop: bool = True
    importance_boxes: list = field(default_factory=list)
    # Export control
    abort_event: threading.Event = field(default_factory=threading.Event)


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def open_path(path: Path) -> None:
    if platform.system() == "Windows":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open", str(path)])


def open_folder(path: Path) -> None:
    if platform.system() == "Windows":
        subprocess.Popen(["explorer", str(path)])
    else:
        subprocess.Popen(["open", str(path)])


# ──────────────────────────────────────────────
# TEMPLATE SELECTOR COMPONENT
# ──────────────────────────────────────────────

class TemplateSelector(ft.Column):
    def __init__(self, templates: dict, on_selection_change):
        super().__init__(spacing=6)
        self._all = templates
        self._index = {k: template_search_text(v) for k, v in templates.items()}
        self._checked: set[str] = set()
        self._on_change = on_selection_change
        self._visible_keys: list[str] = sorted(templates.keys())

        self.search_field = ft.TextField(
            hint_text="Search by name, resolution, or tag…",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_search,
            expand=True,
            height=44,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        self.count_label = ft.Text("0 selected — 0 outputs", size=12, color=ft.Colors.SECONDARY)
        self.select_all_btn = ft.TextButton("Select all", on_click=self._select_all_visible)
        self.clear_btn = ft.TextButton("Clear", on_click=self._clear_all)

        self.list_view = ft.ListView(expand=True, spacing=2, item_extent=40)
        self._render_list(self._visible_keys)

        self.controls = [
            ft.Row([self.search_field]),
            ft.Row(
                [
                    self.count_label,
                    ft.Container(expand=True),
                    self.select_all_btn,
                    self.clear_btn,
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            ft.Container(
                content=self.list_view,
                height=340,
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=6,
                padding=ft.padding.symmetric(vertical=4),
            ),
        ]

    def _render_list(self, keys: list[str]) -> None:
        self.list_view.controls = [
            ft.Checkbox(
                label=k,
                value=k in self._checked,
                data=k,
                on_change=self._on_checkbox,
            )
            for k in sorted(keys)
        ]

    def _on_search(self, e) -> None:
        q = e.control.value.strip().lower()
        if q:
            self._visible_keys = [k for k, s in self._index.items() if q in s]
        else:
            self._visible_keys = sorted(self._all.keys())
        self._render_list(self._visible_keys)
        self.list_view.update()

    def _on_checkbox(self, e) -> None:
        key = e.control.data
        if e.control.value:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self._update_count()
        self._on_change(list(self._checked))

    def _select_all_visible(self, _) -> None:
        for key in self._visible_keys:
            self._checked.add(key)
        self._render_list(self._visible_keys)
        self.list_view.update()
        self._update_count()
        self._on_change(list(self._checked))

    def _clear_all(self, _) -> None:
        self._checked.clear()
        self._render_list(self._visible_keys)
        self.list_view.update()
        self._update_count()
        self._on_change([])

    def _update_count(self) -> None:
        n_tmpl = len(self._checked)
        n_out = sum(len(self._all[k].formats) for k in self._checked)
        self.count_label.value = f"{n_tmpl} selected — {n_out} outputs"
        self.count_label.update()

    @property
    def selected(self) -> list[str]:
        return list(self._checked)


# ──────────────────────────────────────────────
# MAIN APP
# ──────────────────────────────────────────────

def main(page: ft.Page) -> None:
    page.title = "AdScreen Converter"
    page.window.width = 1280
    page.window.height = 860
    page.window.min_width = 960
    page.window.min_height = 640
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.fonts = {}

    state = AppState()
    state.templates = load_templates()
    state.search_index = {k: template_search_text(v) for k, v in state.templates.items()}
    _ffmpeg_ok = ffmpeg_available()

    # ── Sidebar controls ───────────────────────

    logo_path = BASE_DIR / "img" / "primedia-malls.png"
    logo = ft.Image(
        src=str(logo_path) if logo_path.exists() else None,
        width=220,
        fit=ft.ImageFit.CONTAIN,
        visible=logo_path.exists(),
    )

    ffmpeg_status = ft.Row(
        [
            ft.Icon(
                ft.Icons.CHECK_CIRCLE if _ffmpeg_ok else ft.Icons.ERROR,
                color=ft.Colors.GREEN if _ffmpeg_ok else ft.Colors.RED,
                size=18,
            ),
            ft.Text(
                "FFmpeg ready" if _ffmpeg_ok else "FFmpeg not found",
                color=ft.Colors.GREEN if _ffmpeg_ok else ft.Colors.RED,
                size=13,
            ),
        ],
        spacing=6,
    )

    crf_label = ft.Text(f"CRF: {state.crf}  (lower = better quality)", size=12)

    def on_crf_change(e):
        state.crf = int(e.control.value)
        crf_label.value = f"CRF: {state.crf}  (lower = better quality)"
        crf_label.update()

    crf_slider = ft.Slider(
        min=12, max=28, value=state.crf, divisions=16,
        label="{value}", on_change=on_crf_change,
    )

    def on_preset_change(e):
        state.preset = e.control.value

    preset_dd = ft.Dropdown(
        value=state.preset,
        options=[ft.dropdown.Option(p) for p in ["ultrafast", "fast", "medium", "slow", "veryslow"]],
        on_change=on_preset_change,
        label="Encoding preset",
        dense=True,
    )

    def on_dur_change(e):
        try:
            state.img_duration = max(3, min(60, int(e.control.value)))
        except ValueError:
            pass

    dur_field = ft.TextField(
        value=str(state.img_duration),
        label="Image → Video duration (s)",
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=on_dur_change,
        dense=True,
        width=220,
    )

    def on_smart_crop_change(e):
        state.use_smart_crop = e.control.value

    smart_crop_toggle = ft.Switch(
        label="Smart Crop (AI)",
        value=state.use_smart_crop,
        on_change=on_smart_crop_change,
        tooltip="Detects faces, text, logos and packshots — adjusts crop to keep them in frame",
    )

    log_dlg = ft.AlertDialog(
        title=ft.Text("app.log"),
        content=ft.TextField(
            multiline=True, read_only=True, min_lines=20, max_lines=20,
            value="", expand=True,
        ),
        actions=[ft.TextButton("Close", on_click=lambda _: close_log_dlg())],
    )

    def close_log_dlg():
        log_dlg.open = False
        page.update()

    def show_log(_):
        try:
            log_dlg.content.value = Path("app.log").read_text()[-3000:]
        except FileNotFoundError:
            log_dlg.content.value = "No log file yet."
        log_dlg.open = True
        page.open(log_dlg)

    sidebar = ft.Container(
        width=270,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        padding=ft.padding.all(16),
        content=ft.Column(
            [
                logo,
                ft.Divider(),
                ft.Text("System", weight=ft.FontWeight.BOLD, size=13),
                ffmpeg_status,
                ft.Divider(),
                ft.Text("Export Settings", weight=ft.FontWeight.BOLD, size=13),
                smart_crop_toggle,
                crf_label,
                crf_slider,
                preset_dd,
                dur_field,
                ft.Divider(),
                ft.Text("Log", weight=ft.FontWeight.BOLD, size=13),
                ft.ElevatedButton("View app.log", icon=ft.Icons.ARTICLE, on_click=show_log),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    # ── Main content sections ──────────────────

    # --- FFmpeg missing banner ---
    ffmpeg_banner = ft.Container(
        visible=not _ffmpeg_ok,
        bgcolor=ft.Colors.ERROR_CONTAINER,
        border_radius=8,
        padding=ft.padding.all(16),
        content=ft.Column(
            [
                ft.Text("FFmpeg not found", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_ERROR_CONTAINER),
                ft.Text(
                    "FFmpeg and ffprobe must be installed and available on your PATH.",
                    color=ft.Colors.ON_ERROR_CONTAINER,
                ),
                ft.Text("Mac:  brew install ffmpeg", font_family="monospace", size=12),
                ft.Text("Windows:  winget install ffmpeg", font_family="monospace", size=12),
                ft.TextButton(
                    "Download from ffmpeg.org",
                    url="https://ffmpeg.org/download.html",
                ),
            ],
            spacing=6,
        ),
    )

    # --- Template selector section ---
    selector_section = ft.Column(visible=True, spacing=10)

    def on_template_selection_change(keys: list[str]):
        state.selected_keys = keys
        n_out = sum(len(state.templates[k].formats) for k in keys)
        sel_caption.value = (
            f"{len(keys)} template(s) selected — {n_out} output(s)" if keys else ""
        )
        sel_caption.update()
        file_section.visible = bool(keys)
        file_section.update()

    template_selector = TemplateSelector(state.templates, on_template_selection_change)
    sel_caption = ft.Text("", size=12, color=ft.Colors.SECONDARY)

    selector_section.controls = [
        ft.Text("Select Screen Templates", size=18, weight=ft.FontWeight.BOLD),
        template_selector,
        sel_caption,
        ft.Divider(),
    ]

    # --- File picker section ---
    file_section = ft.Column(visible=False, spacing=10)

    file_label = ft.Text("No file selected", size=13, color=ft.Colors.SECONDARY)

    def on_file_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        picked = Path(e.files[0].path)
        # Clear old input files before copying the new one
        for _old in INPUT_DIR.iterdir():
            try:
                _old.unlink()
            except Exception:
                pass
        dest = INPUT_DIR / picked.name
        if picked != dest:
            shutil.copy2(picked, dest)
        state.input_path = dest
        file_label.value = f"Selected: {picked.name}"
        file_label.update()
        preview_section.visible = False
        export_section.visible = False
        results_section.visible = False
        page.update()
        threading.Thread(target=process_input, daemon=True).start()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    file_section.controls = [
        ft.Text("Upload Master File", size=18, weight=ft.FontWeight.BOLD),
        ft.Row(
            [
                ft.ElevatedButton(
                    "Choose File",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=lambda _: file_picker.pick_files(
                        allowed_extensions=["mp4", "mov", "jpg", "jpeg", "png"],
                        allow_multiple=False,
                    ),
                ),
                file_label,
            ],
            spacing=12,
        ),
        ft.Divider(),
    ]

    # --- Preview section ---
    preview_section = ft.Column(visible=False, spacing=10)
    preview_spinner = ft.ProgressRing(width=32, height=32, visible=True)
    preview_status = ft.Text("Processing…", size=13)
    preview_img = ft.Image(width=260, height=160, fit=ft.ImageFit.CONTAIN, visible=False)
    preview_info = ft.Column([], spacing=4)

    preview_section.controls = [
        ft.Text("Source File", size=18, weight=ft.FontWeight.BOLD),
        ft.Row([preview_spinner, preview_status]),
        ft.Row(
            [
                ft.Container(content=preview_img, visible=True),
                preview_info,
            ],
            spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        ft.Divider(),
    ]

    def process_input():
        """Background thread: convert image if needed, probe, thumbnail."""
        preview_section.visible = True
        preview_spinner.visible = True
        preview_status.value = "Processing file…"
        preview_img.visible = False
        page.update()

        p = state.input_path
        ext = p.suffix.lower()

        # Image → video
        if ext in (".jpg", ".jpeg", ".png"):
            preview_status.value = f"Converting image to {state.img_duration}s video…"
            preview_status.update()
            video_path = INPUT_DIR / "converted_video.mp4"
            try:
                image_to_video(p, video_path, state.img_duration)
                state.input_path = video_path
                p = video_path
            except RuntimeError as exc:
                preview_spinner.visible = False
                preview_status.value = f"Conversion failed: {exc}"
                preview_spinner.update()
                preview_status.update()
                return

        # Probe
        try:
            preview_status.value = "Reading video metadata…"
            preview_status.update()
            w, h, dur = probe_video(p)
            state.video_w, state.video_h, state.duration = w, h, dur
        except RuntimeError as exc:
            preview_spinner.visible = False
            preview_status.value = f"Could not read video: {exc}"
            preview_spinner.update()
            preview_status.update()
            return

        # Thumbnail
        thumb = PREVIEW_DIR / "thumb.jpg"
        generate_thumbnail(p, thumb)

        # Smart crop detection — runs once, result reused for all export plans
        smart_crop_info = ""
        state.importance_boxes = []
        if state.use_smart_crop:
            preview_status.value = "Analysing content (faces, text, logos)…"
            preview_status.update()
            try:
                from smart_crop import extract_keyframes, detect_importance_regions, draw_detections
                frames = extract_keyframes(p)
                state.importance_boxes = detect_importance_regions(frames)
                if state.importance_boxes:
                    overlay = PREVIEW_DIR / "thumb_overlay.jpg"
                    if draw_detections(thumb, state.importance_boxes, overlay) and overlay.exists():
                        preview_img.src = str(overlay)
                    smart_crop_info = f"Smart crop: {len(state.importance_boxes)} region(s) detected"
                else:
                    smart_crop_info = "Smart crop: no regions found, using centre-crop"
            except Exception as exc:
                smart_crop_info = f"Smart crop unavailable: {exc}"

        # Update UI
        n_out = sum(len(state.templates[k].formats) for k in state.selected_keys)
        info_rows = [
            ft.Text("Source video info", weight=ft.FontWeight.BOLD),
            ft.Text(f"Resolution:  {w}×{h}"),
            ft.Text(f"Duration:  {dur:.1f}s") if dur else ft.Text("Duration: N/A"),
            ft.Text(f"Outputs to export:  {n_out}"),
        ]
        if smart_crop_info:
            info_rows.append(ft.Text(smart_crop_info, size=12, color=ft.Colors.SECONDARY))
        preview_info.controls = info_rows

        if thumb.exists() and not state.use_smart_crop:
            preview_img.src = str(thumb)
            preview_img.visible = True
        elif state.use_smart_crop:
            preview_img.visible = True

        preview_spinner.visible = False
        preview_status.value = "Ready to export"

        # Build export jobs
        state.export_jobs = []
        for key in state.selected_keys:
            tmpl = state.templates[key]
            for plan in plan_exports(tmpl, w, h, importance_boxes=state.importance_boxes or None):
                state.export_jobs.append((tmpl, plan))

        export_info_text.value = (
            f"{len(state.export_jobs)} output(s) ready across "
            f"{len(state.selected_keys)} template(s)"
        )
        export_section.visible = True
        export_btn.disabled = False
        page.update()

    # --- Export section ---
    export_section = ft.Column(visible=False, spacing=10)
    export_info_text = ft.Text("", size=13)
    export_progress = ft.ProgressBar(value=0, width=600, visible=False)
    export_status = ft.Text("", size=12, color=ft.Colors.SECONDARY, visible=False)

    export_btn = ft.ElevatedButton(
        "Export All Formats",
        icon=ft.Icons.ROCKET_LAUNCH,
        disabled=True,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.PRIMARY,
            color=ft.Colors.ON_PRIMARY,
            padding=ft.padding.symmetric(horizontal=24, vertical=14),
        ),
    )
    cancel_btn = ft.TextButton("Cancel", visible=False)

    def cancel_export(_):
        state.abort_event.set()
        cancel_btn.visible = False
        export_status.value = "Cancelling…"
        cancel_btn.update()
        export_status.update()

    cancel_btn.on_click = cancel_export

    def start_export(_):
        state.abort_event.clear()
        state.output_files = []
        state.errors = []
        # Clear old output and preview files before each export run
        for _old in OUTPUT_DIR.iterdir():
            try:
                _old.unlink()
            except Exception:
                pass
        for _old in PREVIEW_DIR.iterdir():
            try:
                _old.unlink()
            except Exception:
                pass
        export_btn.disabled = True
        export_progress.visible = True
        export_progress.value = 0
        export_status.visible = True
        export_status.value = "Starting…"
        cancel_btn.visible = True
        results_section.visible = False
        page.update()
        threading.Thread(target=run_export, daemon=True).start()

    export_btn.on_click = start_export

    export_section.controls = [
        ft.Text("Export", size=18, weight=ft.FontWeight.BOLD),
        export_info_text,
        ft.Row([export_btn, cancel_btn], spacing=12),
        export_progress,
        export_status,
        ft.Divider(),
    ]

    def run_export():
        """Background thread: run all ffmpeg export jobs."""
        total = len(state.export_jobs)
        for i, (tmpl, plan) in enumerate(state.export_jobs):
            if state.abort_event.is_set():
                break
            file_label = plan.label if plan.label else tmpl.name.replace(' ', '_')
            out = OUTPUT_DIR / f"{file_label}_{plan.width}x{plan.height}.mp4"
            export_status.value = (
                f"Exporting {tmpl.name}  {plan.width}×{plan.height}  ({i + 1}/{total})"
            )
            export_status.update()
            try:
                export_format(
                    src=state.input_path,
                    dst=out,
                    width=plan.width,
                    height=plan.height,
                    crop_x=plan.crop_x,
                    crop_y=plan.crop_y,
                    crf=state.crf,
                    preset=state.preset,
                )
                state.output_files.append(out)
            except RuntimeError as exc:
                state.errors.append(f"{tmpl.name} {plan.width}×{plan.height}: {exc}")
            export_progress.value = (i + 1) / total
            export_progress.update()

        export_status.value = "Done." if not state.abort_event.is_set() else "Cancelled."
        export_btn.disabled = False
        cancel_btn.visible = False
        export_status.update()
        export_btn.update()
        cancel_btn.update()
        show_results()

    # --- Results section ---
    results_section = ft.Column(visible=False, spacing=10)

    def show_results():
        results_section.controls.clear()
        results_section.controls.append(
            ft.Text("Results", size=18, weight=ft.FontWeight.BOLD)
        )

        n_ok = len(state.output_files)
        n_total = len(state.export_jobs)
        results_section.controls.append(
            ft.Text(
                f"{n_ok} of {n_total} format(s) exported successfully.",
                color=ft.Colors.GREEN if n_ok == n_total else ft.Colors.ORANGE,
                size=14,
            )
        )

        # Thumbnail grid
        if state.output_files:
            grid = ft.GridView(
                runs_count=4,
                max_extent=200,
                spacing=8,
                run_spacing=8,
                child_aspect_ratio=0.7,
            )
            for out_file in state.output_files:
                thumb = PREVIEW_DIR / f"thumb_{out_file.stem}.jpg"
                generate_thumbnail(out_file, thumb)
                size_mb = out_file.stat().st_size / 1_000_000

                tile = ft.Column(
                    [
                        ft.Image(
                            src=str(thumb) if thumb.exists() else None,
                            width=180,
                            height=100,
                            fit=ft.ImageFit.COVER,
                            border_radius=4,
                        )
                        if thumb.exists()
                        else ft.Icon(ft.Icons.VIDEO_FILE, size=80, color=ft.Colors.SECONDARY),
                        ft.Text(
                            f"{out_file.stem[-22:]}",
                            size=10,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(f"{size_mb:.1f} MB", size=10, color=ft.Colors.SECONDARY),
                        ft.TextButton(
                            "Open",
                            icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                            on_click=lambda _, p=out_file: open_path(p),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                )
                grid.controls.append(tile)

            results_section.controls.append(
                ft.Container(content=grid, height=340)
            )

            # Open folder + ZIP buttons
            action_row_controls = [
                ft.ElevatedButton(
                    "Open Output Folder",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=lambda _: open_folder(OUTPUT_DIR),
                ),
            ]
            if len(state.output_files) > 1:
                def make_zip(_):
                    zip_path = zip_outputs(state.output_files)
                    open_path(zip_path)

                action_row_controls.append(
                    ft.ElevatedButton(
                        "Download All as ZIP",
                        icon=ft.Icons.ARCHIVE,
                        on_click=make_zip,
                    )
                )
            results_section.controls.append(ft.Row(action_row_controls, spacing=12))

        # Errors
        if state.errors:
            results_section.controls.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        f"{len(state.errors)} format(s) failed",
                        color=ft.Colors.ERROR,
                    ),
                    controls=[
                        ft.ListTile(title=ft.Text(e, size=12, color=ft.Colors.ERROR))
                        for e in state.errors
                    ],
                )
            )

        # Export Again button
        results_section.controls.append(
            ft.TextButton(
                "Export Again",
                icon=ft.Icons.REFRESH,
                on_click=reset_to_export,
            )
        )

        results_section.visible = True
        page.update()

    def reset_to_export(_):
        export_progress.value = 0
        export_status.value = ""
        export_btn.disabled = False
        export_progress.visible = False
        export_status.visible = False
        results_section.visible = False
        page.update()

    # ── Assemble main content ──────────────────

    main_content = ft.Column(
        [
            ft.Container(
                padding=ft.padding.only(left=24, right=24, top=20, bottom=8),
                content=ft.Column(
                    [
                        ft.Text("Video Converter", size=28, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Automated multi-format video export for digital-out-of-home advertising",
                            size=13,
                            color=ft.Colors.SECONDARY,
                        ),
                    ],
                    spacing=2,
                ),
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24),
                content=ffmpeg_banner,
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24),
                content=selector_section,
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24),
                content=file_section,
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24),
                content=preview_section,
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24),
                content=export_section,
            ),
            ft.Container(
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                content=results_section,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=0,
    )

    page.add(
        ft.Row(
            [
                sidebar,
                ft.VerticalDivider(width=1),
                main_content,
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=0,
        )
    )


ft.app(target=main)
