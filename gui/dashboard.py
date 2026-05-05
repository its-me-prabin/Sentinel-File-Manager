import json
import logging
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import customtkinter as ctk

from config_loader import load_config, SentinelConfig
from gui.settings_panel import SettingsPanel
from gui.theme import get_tag_colors
from retry_worker import RetryWorker
from sweeper import start_scheduler, run_initial_sweep
from watcher import start_observer


def _get_icon_path():
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    icon_path = base_path / "assets" / "sentinel_icon.ico"
    return str(icon_path) if icon_path.exists() else None


class DashboardApp(ctk.CTk):
    def __init__(self, config_path: str, config: SentinelConfig, logger: logging.Logger):
        super().__init__()
        
        self.config_path = config_path
        self.config = config
        self.logger = logger
        
        ctk.set_appearance_mode(self.config.theme)
        ctk.set_default_color_theme(self.config.color_accent)
        
        self.title("Sentinel - File Manager")
        self.geometry(f"{self.config.window_width}x{self.config.window_height}")
        
        icon_path = _get_icon_path()
        if icon_path:
            self.iconbitmap(icon_path)
            self.icon_path = icon_path
        else:
            self.icon_path = None
        
        # Make the background look like the mockup (Dark UI)
        if self.config.theme.lower() == "dark":
            self.configure(fg_color="#18181b")
            
        self.gui_event_bus = queue.Queue()
        self._engines_running = False
        self._closing = False
        
        self.watcher = None
        self.scheduler = None
        self.retry_worker = None
        
        self.stats = {"moved": 0, "archived": 0, "skipped": 0, "retry": 0}
        self.last_event_time = "Never"
        
        self._build_ui()
        self._update_status_bar()
        self._load_history()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_events)

    def _build_decorative_dots(self, parent):
        """
        Decorative Mac-style window control dots.
        These have no functionality — the OS title bar manages the window.
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        for color in ("#ff5f57", "#febc2e", "#28c840"):
            dot = ctk.CTkLabel(frame, text="", width=12, height=12,
                               fg_color=color, corner_radius=6)
            dot.pack(side="left", padx=4)
        return frame

    def _build_ui(self):
        # Main Layout: 3 Rows (Header, Content, Footer)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Main Area
        self.grid_rowconfigure(2, weight=0) # Footer
        self.grid_columnconfigure(0, weight=1)
        
        # ── Header ──
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        header_frame.grid_columnconfigure(1, weight=1) # Push start button to right
        
        left_header = ctk.CTkFrame(header_frame, fg_color="transparent")
        left_header.grid(row=0, column=0, sticky="w")
        
        dots = self._build_decorative_dots(left_header)
        dots.pack(side="left", padx=(0, 20))
        
        title_label = ctk.CTkLabel(left_header, text="Sentinel", font=("Segoe UI", 18, "bold"), text_color="white")
        title_label.pack(side="left")
        
        subtitle_label = ctk.CTkLabel(left_header, text="— File Manager", font=("Segoe UI", 16), text_color="gray")
        subtitle_label.pack(side="left", padx=(5, 0))
        
        # Status Header (Row 1 inside a top container, or just part of header_frame)
        status_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        status_frame.grid_columnconfigure(1, weight=1)
        
        self.lbl_status_indicator = ctk.CTkLabel(status_frame, text="● Stopped", text_color="gray", fg_color="#2b2b2b", corner_radius=12, padx=10, pady=2, font=("Segoe UI", 12))
        self.lbl_status_indicator.grid(row=0, column=0, sticky="w")
        
        version_label = ctk.CTkLabel(status_frame, text="Sentinel v1.0", font=("Segoe UI", 14), text_color="white")
        version_label.grid(row=0, column=0, sticky="w", padx=(100, 0))
        
        right_status_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        right_status_frame.grid(row=0, column=1, sticky="e")
        
        self.status_folders_label = ctk.CTkLabel(right_status_frame, text="Watching 0 folders", text_color="gray", font=("Segoe UI", 12))
        self.status_folders_label.pack(side="left", padx=15)
        
        self.btn_start = ctk.CTkButton(right_status_frame, text="▶ Start", command=self.toggle_engines, width=100, border_width=1, border_color="gray", fg_color="transparent", hover_color="#2b2b2b")
        self.btn_start.pack(side="left")
        
        # Add tooltip-like label below the button in case it's disabled
        self.lbl_start_tooltip = ctk.CTkLabel(right_status_frame, text="", text_color="red", font=("Segoe UI", 10))
        
        # ── Main Area (Sidebar + Feed) ──
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=0)
        main_area.grid_columnconfigure(0, weight=0, minsize=250) # Sidebar
        main_area.grid_columnconfigure(1, weight=1) # Feed
        main_area.grid_rowconfigure(0, weight=1)
        
        # Separator line between header and main area
        sep1 = ctk.CTkFrame(self, height=1, fg_color="#333333")
        sep1.grid(row=0, column=0, sticky="ew", pady=(85, 0)) # Absolute positioning workaround or just pack it properly. Actually, putting it in main_area is easier.
        
        # --- Left Sidebar ---
        sidebar = ctk.CTkFrame(main_area, fg_color="transparent")
        sidebar.grid(row=0, column=0, sticky="nsew", pady=10)
        
        lbl_stats_header = ctk.CTkLabel(sidebar, text="STATISTICS", text_color="gray", font=("Segoe UI", 11, "bold"))
        lbl_stats_header.pack(anchor="w", pady=(0, 10))
        
        self._build_stat_row(sidebar, "Moved today", "lbl_stat_moved", "0", "#4da3ff")
        self._build_stat_row(sidebar, "Archived today", "lbl_stat_arch", "0", "white")
        self._build_stat_row(sidebar, "Retry queue", "lbl_stat_retry", "0", "#ffc107")
        self._build_stat_row(sidebar, "Skipped today", "lbl_stat_skip", "0", "white")
        
        ctk.CTkFrame(sidebar, height=1, fg_color="#333333").pack(fill="x", pady=20)
        
        self._build_stat_row(sidebar, "Last sweep", "lbl_last_sweep", "--:--:--", "gray")
        self._build_stat_row(sidebar, "Next sweep", "lbl_next_sweep", "--:--:--", "gray")
        
        ctk.CTkFrame(sidebar, height=1, fg_color="#333333").pack(fill="x", pady=20)
        
        self.btn_sweep = ctk.CTkButton(sidebar, text="↻ Run Sweep Now", command=self.run_sweep_now, fg_color="transparent", border_width=1, border_color="gray", hover_color="#2b2b2b")
        self.btn_sweep.pack(fill="x", pady=5)
        
        self.btn_log = ctk.CTkButton(sidebar, text="📄 Open Log File", command=self._open_log_file, fg_color="transparent", border_width=1, border_color="gray", hover_color="#2b2b2b")
        self.btn_log.pack(fill="x", pady=5)
        
        self.btn_settings = ctk.CTkButton(sidebar, text="⚙ Settings", command=self._open_settings, fg_color="transparent", border_width=1, border_color="gray", hover_color="#2b2b2b")
        self.btn_settings.pack(fill="x", pady=5)
        
        # Vertical Separator
        v_sep = ctk.CTkFrame(main_area, width=1, fg_color="#333333")
        v_sep.grid(row=0, column=0, sticky="nse", padx=(240, 0))
        
        # --- Right Activity Feed ---
        feed_frame = ctk.CTkFrame(main_area, fg_color="transparent")
        feed_frame.grid(row=0, column=1, sticky="nsew", padx=(20, 0), pady=10)
        
        feed_header = ctk.CTkFrame(feed_frame, fg_color="transparent")
        feed_header.pack(fill="x", pady=(0, 10))
        
        lbl_feed = ctk.CTkLabel(feed_header, text="ACTIVITY FEED", text_color="gray", font=("Segoe UI", 11, "bold"))
        lbl_feed.pack(side="left")
        
        btn_clear = ctk.CTkButton(feed_header, text="Clear", command=self._clear_feed, width=60, fg_color="transparent", border_width=1, border_color="gray", hover_color="#2b2b2b")
        btn_clear.pack(side="right")
        
        # Treeview for Feed
        style = ttk.Style()
        style.theme_use("default")
        bg_color = "#18181b" if self.config.theme.lower() == "dark" else "#ebebeb"
        fg_color = "white" if self.config.theme.lower() == "dark" else "black"
        style.configure("Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color, borderwidth=0, font=("Consolas", 10))
        style.configure("Treeview.Heading", background=bg_color, foreground="gray", font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})]) # Remove borders
        style.map("Treeview", background=[("selected", "#2b2b2b")])
        
        self.tree = ttk.Treeview(feed_frame, columns=("Time", "File", "Rule", "Matched", "Destination"), show="headings")
        self.tree.heading("Time", text="TIME", anchor="w")
        self.tree.heading("File", text="FILENAME", anchor="w")
        self.tree.heading("Rule", text="RULE", anchor="w")
        self.tree.heading("Matched", text="MATCHED", anchor="w")
        self.tree.heading("Destination", text="DESTINATION", anchor="w")
        
        self.tree.column("Time", width=80, stretch=False, anchor="w")
        self.tree.column("File", width=200, stretch=True, anchor="w")
        self.tree.column("Rule", width=100, stretch=False, anchor="w")
        self.tree.column("Matched", width=120, stretch=False, anchor="w")
        self.tree.column("Destination", width=150, stretch=True, anchor="w")
        
        scrollbar = ttk.Scrollbar(feed_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self._apply_appearance(self.config.theme)
        
        # ── Footer ──
        footer_frame = ctk.CTkFrame(self, fg_color="#1e1e24", height=30, corner_radius=0)
        footer_frame.grid(row=2, column=0, sticky="ew")
        
        self.lbl_footer = ctk.CTkLabel(footer_frame, text="Watching 0 folders  |  Engines: watchdog + sweeper  |  Last event: Never", font=("Segoe UI", 11), text_color="gray")
        self.lbl_footer.pack(side="left", padx=20, pady=5)

    def _build_stat_row(self, parent, label_text, attr_name, default_val, val_color):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=4)
        lbl_name = ctk.CTkLabel(frame, text=label_text, text_color="gray", font=("Segoe UI", 13))
        lbl_name.pack(side="left")
        lbl_val = ctk.CTkLabel(frame, text=default_val, text_color=val_color, font=("Segoe UI", 14, "bold"))
        lbl_val.pack(side="right")
        setattr(self, attr_name, lbl_val)

    def _update_status_bar(self):
        """Derives watched folder count directly from live config. No counter state."""
        n = len(self.config.watched_folders)
        folder_text = f"Watching {n} folder{'s' if n != 1 else ''}"
        self.status_folders_label.configure(text=folder_text)
        
        footer_text = f"{folder_text}  |  Engines: watchdog + sweeper  |  Last event: {self.last_event_time}"
        self.lbl_footer.configure(text=footer_text)
        
        if n == 0:
            self.btn_start.configure(state="disabled", text="▶ Start", fg_color=("gray70", "gray30"))
            self.lbl_start_tooltip.configure(text="Add a folder in Settings to start", text_color="red")
            self.lbl_start_tooltip.place(in_=self.btn_start, relx=0.5, rely=1.5, anchor="center")
        else:
            if not self._engines_running:
                self.btn_start.configure(state="normal", text="▶ Start", fg_color="transparent")
            self.lbl_start_tooltip.place_forget()

    def _apply_appearance(self, mode: str):
        colors = get_tag_colors(mode)
        for tag, color in colors.items():
            self.tree.tag_configure(tag, foreground=color)
            
        style = ttk.Style()
        bg_color = "#18181b" if mode.lower() == "dark" else "#ebebeb"
        fg_color = "white" if mode.lower() == "dark" else "black"
        style.configure("Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color)
        style.configure("Treeview.Heading", background=bg_color)

    def _open_settings(self):
        SettingsPanel(
            master=self,
            config_path=self.config_path,
            icon_path=self.icon_path,
            on_reload=self.reload_config,
            on_appearance_change=self._apply_appearance,
        )

    def reload_config(self):
        """Called by SettingsPanel on the main thread after background parse."""
        try:
            self.config = load_config(self.config_path)
            if self.watcher:
                self.watcher.event_handler.config = self.config
            
            self.gui_event_bus.put({"type": "config_reloaded"})
        except Exception as e:
            self.logger.error(f"Failed to reload config: {e}")

    def toggle_engines(self):
        if self._engines_running:
            self.stop_engines()
        else:
            self.start_engines()

    def start_engines(self):
        self.btn_start.configure(text="Starting...", state="disabled")
        threading.Thread(target=self._start_engines_worker, daemon=True).start()

    def stop_engines(self):
        self.btn_start.configure(text="Stopping...", state="disabled")
        threading.Thread(target=self._stop_engines_worker, daemon=True).start()

    def _start_engines_worker(self):
        self.retry_worker = RetryWorker(
            backoff_seconds=self.config.retry_backoff_seconds,
            max_attempts=self.config.retry_attempts,
            logger=self.logger,
            gui_event_bus=self.gui_event_bus
        )
        self.retry_worker.start()
        
        self.watcher = start_observer(self.config, self.logger, self.retry_worker, self.gui_event_bus)
        self.scheduler = start_scheduler(self.config, self.logger, self.retry_worker, self.gui_event_bus)
        
        self.gui_event_bus.put({"type": "engines_started"})

    def _stop_engines_worker(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher.join(timeout=5)
            self.watcher = None
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
        if self.retry_worker:
            self.retry_worker.stop()
            self.retry_worker = None
            
        self.gui_event_bus.put({"type": "engines_stopped"})

    def run_sweep_now(self):
        if self._engines_running and self.retry_worker:
            self.btn_sweep.configure(state="disabled")
            threading.Thread(target=self._sweep_worker, daemon=True).start()
            
    def _sweep_worker(self):
        run_initial_sweep(self.config, self.logger, self.retry_worker, self.gui_event_bus)
        
    def _on_close(self):
        self._closing = True
        if self._engines_running:
            self.stop_engines()
        else:
            self.destroy()

    def _poll_events(self):
        while not self.gui_event_bus.empty():
            event = self.gui_event_bus.get_nowait()
            self._handle_event(event)
        self.after(100, self._poll_events)

    def _handle_event(self, event: dict):
        evt_type = event.get("type")
        
        if evt_type == "engines_stopped":
            self._engines_running = False
            if self._closing:
                self.destroy()
                return
            self.lbl_status_indicator.configure(text="● Stopped", text_color="gray")
            self._update_status_bar() # Will reset Start button
            
        elif evt_type == "engines_started":
            self._engines_running = True
            self.lbl_status_indicator.configure(text="● Running", text_color="#20c997")
            self.btn_start.configure(text="■ Stop", state="normal")
            
        elif evt_type == "config_reloaded":
            self._update_status_bar()
            self.insert_feed_row("", "Config reloaded", "System", "", "System", tag="unclassified")
            
        elif evt_type == "sweep_complete":
            self.btn_sweep.configure(state="normal")
            count = event.get("count", 0)
            archived = event.get("archived", 0)
            timestamp = event.get("timestamp", "")
            self.lbl_last_sweep.configure(text=timestamp if timestamp else "Just now")
            self.insert_feed_row(timestamp, f"Sweep Complete: {count} scanned, {archived} archived", "System", "", "sweeper", tag="temporal")
            
        elif evt_type in ["moved", "skip", "retry_failed"]:
            if evt_type == "moved":
                self.stats["moved"] += 1
                if event.get("match_type") == "temporal":
                    self.stats["archived"] += 1
                rule_text = event.get("match_type", "")
                matched_text = event.get("matched", "") # using 'matched' from projected dict
            elif evt_type == "skip":
                self.stats["skipped"] += 1
                rule_text = "skipped"
                matched_text = event.get("reason", "")
            elif evt_type == "retry_failed":
                self.stats["retry"] += 1
                rule_text = "retry_failed"
                matched_text = "Max Attempts"
                
            self.update_stats()
            timestamp = event.get("timestamp", "")
            if timestamp:
                self.last_event_time = timestamp
                self._update_status_bar()
                
            self.insert_feed_row(
                timestamp,
                event.get("filename", ""),
                rule_text,
                matched_text,
                event.get("destination", ""),
                tag=event.get("match_type", "unclassified") if evt_type == "moved" else evt_type
            )

    def update_stats(self):
        self.lbl_stat_moved.configure(text=f"{self.stats['moved']}")
        self.lbl_stat_arch.configure(text=f"{self.stats['archived']}")
        self.lbl_stat_skip.configure(text=f"{self.stats['skipped']}")
        self.lbl_stat_retry.configure(text=f"{self.stats['retry']}")

    def insert_feed_row(self, time_str, filename, rule, matched, dest, tag=""):
        self.tree.insert("", 0, values=(time_str, filename, rule, matched, dest), tags=(tag,))
        # Enforce limit
        children = self.tree.get_children()
        if len(children) > self.config.activity_feed_limit:
            self.tree.delete(children[-1])

    def _clear_feed(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _open_log_file(self):
        log_path = Path(self.config.log_file).resolve()
        if log_path.exists():
            if os.name == 'nt':
                os.startfile(log_path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.call(('open', log_path))
            else:
                import subprocess
                subprocess.call(('xdg-open', log_path))

    def _load_history(self):
        """Bonus feature: Parse last N lines of sentinel_history.jsonl and populate treeview."""
        log_path = Path(self.config.log_file).resolve()
        if not log_path.exists():
            return
            
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            limit = self.config.activity_feed_limit
            recent_lines = lines[-limit:]
            
            for line in recent_lines:
                try:
                    entry = json.loads(line)
                    # Project log entry to GUI dict
                    src = Path(entry.get("source", ""))
                    dst = Path(entry.get("destination", ""))
                    
                    # Convert ISO8601 to display time
                    timestamp_raw = entry.get("timestamp", "")
                    time_display = ""
                    if timestamp_raw:
                        try:
                            # Handle standard ISO8601 strings (may end with 'Z')
                            dt = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                            time_display = dt.strftime("%H:%M:%S")
                        except ValueError:
                            time_display = timestamp_raw[:8] # Fallback
                    
                    filename = (src.name[:30] + "…") if len(src.name) > 30 else src.name
                    matched = entry.get("matched_keyword") or src.suffix
                    destination = dst.parent.name if dst.parent else str(dst)
                    
                    self.insert_feed_row(
                        time_display,
                        filename,
                        entry.get("match_type", "moved"),
                        matched,
                        destination,
                        tag=entry.get("match_type", "unclassified")
                    )
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            self.logger.error(f"Failed to load history: {e}")
