import tkinter.messagebox as messagebox

import customtkinter as ctk
import yaml


class SettingsPanel(ctk.CTkToplevel):
    def __init__(self, master, config_path: str, icon_path: str, on_reload, on_appearance_change):
        super().__init__(master)
        self.title("Sentinel Settings")
        self.geometry("700x550")
        self.attributes("-topmost", True)
        
        if icon_path:
            self.after(200, lambda: self.iconbitmap(icon_path))
            
        self.config_path = config_path
        self.on_reload = on_reload
        self.on_appearance_change = on_appearance_change
        
        # Parse current config
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = yaml.safe_load(f) or {}
        except Exception as e:
            self.config_data = {}
            messagebox.showerror("Config Error", f"Could not parse config.yaml:\n{e}")
            
        self._ensure_defaults()
        
        # Main Layout
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=(20, 10), fill="both", expand=True)
        
        self.tab_paths = self.tabview.add("Paths")
        self.tab_engine = self.tabview.add("Engine")
        self.tab_rules = self.tabview.add("Rules")
        self.tab_appearance = self.tabview.add("Appearance")
        
        self._build_paths_tab()
        self._build_engine_tab()
        self._build_rules_tab()
        self._build_appearance_tab()
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)
        
        save_btn = ctk.CTkButton(btn_frame, text="Save & Reload", command=self._save_and_reload)
        save_btn.pack(side="right")
        
    def _ensure_defaults(self):
        # Ensure dicts exist
        if "paths" not in self.config_data: self.config_data["paths"] = {}
        if "watched" not in self.config_data["paths"]: self.config_data["paths"]["watched"] = []
        if "deep_storage" not in self.config_data["paths"]: self.config_data["paths"]["deep_storage"] = ""
        
        if "settings" not in self.config_data: self.config_data["settings"] = {}
        if "gui" not in self.config_data: self.config_data["gui"] = {}
        if "keyword_rules" not in self.config_data: self.config_data["keyword_rules"] = {}
        if "extension_rules" not in self.config_data: self.config_data["extension_rules"] = {}

    def _build_paths_tab(self):
        # Watched folders
        ctk.CTkLabel(self.tab_paths, text="Watched Folders (one per line):", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        self.txt_watched = ctk.CTkTextbox(self.tab_paths, height=100)
        self.txt_watched.pack(fill="x", padx=10, pady=(0, 15))
        self.txt_watched.insert("1.0", "\n".join(self.config_data["paths"]["watched"]))
        
        # Deep storage
        ctk.CTkLabel(self.tab_paths, text="Deep Storage Path:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(0, 5))
        self.ent_deep = ctk.CTkEntry(self.tab_paths)
        self.ent_deep.pack(fill="x", padx=10, pady=(0, 10))
        self.ent_deep.insert(0, self.config_data["paths"]["deep_storage"])
        
    def _build_engine_tab(self):
        settings = self.config_data["settings"]
        
        frame = ctk.CTkFrame(self.tab_engine, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        def add_setting_row(parent, label, default, row):
            ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", pady=10, padx=(0, 20))
            entry = ctk.CTkEntry(parent, width=150)
            entry.grid(row=row, column=1, sticky="w", pady=10)
            entry.insert(0, str(settings.get(default, "")))
            return entry
            
        self.ent_archive = add_setting_row(frame, "Archive After Days:", "archive_after_days", 0)
        self.ent_retry = add_setting_row(frame, "Retry Attempts:", "retry_attempts", 1)
        self.ent_scan = add_setting_row(frame, "Scan Interval (mins):", "temporal_scan_interval_minutes", 2)
        
    def _build_rules_tab(self):
        # Use two textboxes for rules mapping
        frame = ctk.CTkFrame(self.tab_rules, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="Keyword Rules", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(frame, text="Extension Rules", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        
        ctk.CTkLabel(frame, text="Format: Destination: word1, word2", font=("Segoe UI", 10), text_color="gray").grid(row=2, column=0, sticky="w")
        ctk.CTkLabel(frame, text="Format: Destination: .jpg, .png", font=("Segoe UI", 10), text_color="gray").grid(row=2, column=1, sticky="w", padx=10)
        
        self.txt_keywords = ctk.CTkTextbox(frame, wrap="none")
        self.txt_keywords.grid(row=1, column=0, sticky="nsew", pady=5, padx=(0, 5))
        
        self.txt_extensions = ctk.CTkTextbox(frame, wrap="none")
        self.txt_extensions.grid(row=1, column=1, sticky="nsew", pady=5, padx=(5, 0))
        
        # Populate
        kw_text = ""
        for dest, keywords in self.config_data["keyword_rules"].items():
            kw_text += f"{dest}: {', '.join(keywords)}\n"
        self.txt_keywords.insert("1.0", kw_text)
        
        ext_text = ""
        for dest, exts in self.config_data["extension_rules"].items():
            ext_text += f"{dest}: {', '.join(exts)}\n"
        self.txt_extensions.insert("1.0", ext_text)
        
    def _build_appearance_tab(self):
        gui_settings = self.config_data["gui"]
        
        ctk.CTkLabel(self.tab_appearance, text="Theme Mode:").pack(anchor="w", padx=20, pady=(20, 5))
        self.theme_var = ctk.StringVar(value=gui_settings.get("theme", ctk.get_appearance_mode()))
        theme_menu = ctk.CTkOptionMenu(
            self.tab_appearance, 
            variable=self.theme_var, 
            values=["System", "Dark", "Light"], 
            command=self._change_theme
        )
        theme_menu.pack(anchor="w", padx=20)
        
        ctk.CTkLabel(self.tab_appearance, text="Accent Color:").pack(anchor="w", padx=20, pady=(20, 5))
        self.accent_var = ctk.StringVar(value=gui_settings.get("color_accent", "blue"))
        accent_menu = ctk.CTkOptionMenu(
            self.tab_appearance, 
            variable=self.accent_var, 
            values=["blue", "green", "dark-blue"]
        )
        accent_menu.pack(anchor="w", padx=20)
        
        ctk.CTkLabel(self.tab_appearance, text="Changes to Theme apply immediately.\nChanges to Accent require restart.", font=("Segoe UI", 11), text_color="gray").pack(anchor="w", padx=20, pady=20)
        
    def _change_theme(self, choice: str):
        ctk.set_appearance_mode(choice)
        if self.on_appearance_change:
            self.on_appearance_change(choice)
            
    def _parse_rules_textbox(self, textbox):
        result = {}
        lines = textbox.get("1.0", "end-1c").splitlines()
        for line in lines:
            if ":" not in line: continue
            parts = line.split(":", 1)
            dest = parts[0].strip()
            items = [x.strip() for x in parts[1].split(",") if x.strip()]
            if dest and items:
                result[dest] = items
        return result

    def _save_and_reload(self):
        try:
            # 1. Paths
            watched_raw = self.txt_watched.get("1.0", "end-1c").splitlines()
            self.config_data["paths"]["watched"] = [x.strip() for x in watched_raw if x.strip()]
            self.config_data["paths"]["deep_storage"] = self.ent_deep.get().strip()
            
            # 2. Engine
            self.config_data["settings"]["archive_after_days"] = int(self.ent_archive.get())
            self.config_data["settings"]["retry_attempts"] = int(self.ent_retry.get())
            self.config_data["settings"]["temporal_scan_interval_minutes"] = int(self.ent_scan.get())
            
            # 3. Rules
            self.config_data["keyword_rules"] = self._parse_rules_textbox(self.txt_keywords)
            self.config_data["extension_rules"] = self._parse_rules_textbox(self.txt_extensions)
            
            # 4. Appearance
            self.config_data["gui"]["theme"] = self.theme_var.get().lower()
            self.config_data["gui"]["color_accent"] = self.accent_var.get().lower()
            
            # Write out
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config_data, f, sort_keys=False, default_flow_style=False)
                
            if self.on_reload:
                self.on_reload()
            self.destroy()
            
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Please ensure Engine settings are valid numbers.\n{e}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config:\n{e}")
